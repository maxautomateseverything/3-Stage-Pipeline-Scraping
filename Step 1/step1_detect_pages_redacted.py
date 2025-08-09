"""
step1_detect_pages.py

Plain English:
- Download the first listing page.
- Save the HTML to disk so we can inspect it.
- Scan all links for '.../page:<number>/' and report the largest number we find.

Technical:
- Uses requests.get with a realistic User-Agent and timeout.
- Parses HTML via BeautifulSoup (prefers 'lxml', falls back to 'html.parser').
- Uses a regex to extract page numbers from hrefs.
"""

from __future__ import annotations  
"""
Changes how python interprets hints like x:MyClass, by storing all annotations as stirngs.
This lets use reference classes, functions, or types, before they are defined in our file wihtout quotes
and without causing NameErrors.
"""

import re 
"""
Python's regular expressions module that is used for pattern matching in strings.
In this script it is used to match page:<number> URLs to detect patterns like page:12 or page:345 in text or URLs.
When trying to identify the same pattern many times, it allows us to compile the pattern first in a reges with 
re.compile(<pattern>) to make the code faster and cleaner.
"""

from pathlib import Path   
"""
Allows for object-oriented (OO) filesystem paths meanign instead of calling the os.path fucntions on strings, 
you get a path object with methods and peroperties for common path operations.
while os.path requires function calls with strings, pathlib is more readable, less error prone,
and works consistently across different operating systems.
"""

import sys     
"""
Gives access to sys specific functions - here we use sys.exit() to end the program immediately.
Allows the signal a failure in the script with a non-zero return code where sys.exit(0) is success and sys.exit(1) is failure.
Without this the script might fail silently but still return a success code, 
which would cause the system to beleive everything worked.
"""

import time 
"""
Used python built-in time module to pause executions using time.sleep(<seconds>).
Makes the program wait for politeness by avoiding overloading servers or APIs.
We assigned a jitter variable to create random delays that makes the traffic pattern less robotic 
to reduce the chance of triggering rate limits or bot detection.
"""               

import requests              
from bs4 import BeautifulSoup  
"""
Popular HTTP client (requests) and HTML parser (BeautifulSoup) that are highly used in static HTML scraping, 
but less applicable for dynamic websites generated wiht JavaScript
The client fetches the HTML from the internet and the parser parses the HTML so we can query it.
We use requests.get(url, timeout=...) so the script doesnt hang forever if the site is slow or unresponsive.
We use requests.Session() to reuse TCP connections for efficiency, as well as to set retry logic.
We use the lxml parser because it is faster and more robust than the built-in html.parser.
"""


# ---------- Config you can tweak later ----------
LISTING_URL = "<***The start URL for pages to scrape***>"
"""
The start URL for scraping whcih tends ot the page 1.
The other pages will liekly follow the same pattern meaning they can be accessed by appending /page:2/ or /page:3/ etc.
Using the variable keeps it configurable as opposed to hardcoding the URL into the code, allowing us to change the start URL.
"""

OUTPUT_HTML = Path("first_listing_page.html")
"""
Creates a path object pointing to a file called first_listing_page.html in the current working directory.
This is where the program will save HTML it fetches and will contain the exact HTML from the website scraped.
Saving it locally means we dont have to keep hitting the website to tinker with parsing and selectors.
Saving the raw HTML allows us to reproduce the results if the website changes or goes offline and debig parsing issues 
without re-fetching.
"""

REQUEST_TIMEOUT = 20 #seconds
"""
If the total request takes longer than 20 seconds, it is stopped (timed out).
This avoids the program for waiting forever if the server never responds.
"""

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}
"""
User-agent tells the server what kind of client is making the request.
Wihtout setting a user-agent Python libraries like requests send python-requests to the server 
which many sites see as a scraper and will block or throttle.
Accept-Languauge says what language the client prefers for the response.
In this case we prefer British English but use Generic English as a fallback.
"""
# ---------- End config ----------


def fetch_html(url: str) -> str:
    """
    The first line is type hinting where url:str means the functions is expecting url to be a string 
    and -> str means it will return a string.
    The resp variable when called sends a GET request to url using HEADERS (user-agent configuration) 
    and REQUEST_TIMEOUT (timout configuration).
    Then identifies the HTTP status code and raises a HTTP error if 4xx (client error) or 5xx (server error) instead 
    of returning a bad HTML.
    Then returns the string as text / string for further processing.
    """
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()  
    return resp.text


def choose_parser() -> str:
    """
    Uses the faster BeautifulSoup parser (lxml) if available, which is faster and more robust as it handles broken 
    HTMLs better, otherwise uses the built-in parser allowing the code to still run if lxml is not installed.
    """
    try:
        import lxml  
        return "lxml"
    except Exception:
        return "html.parser"


def parse_total_pages(html: str) -> int:
    """
    This is a pagination parser that is meant to detect how many pages are in the listing by looking at either:
    - Links in the HTML that contain page numbers (the preferred method)
    - Visible text like "Page 1 of N" (as a fallback)
    """
    parser = choose_parser()
    soup = BeautifulSoup(html, parser)
    """
    Uses our choose_parser function to select a parser (lxml if present, otherwise html.parser) to turn the 
    raw HTML into a searchable object using BeautifulSoup.
    """

    hrefs = [a.get("href", "") for a in soup.find_all("a") if a.get("href")]
    """
    Finds all <a> tags that actually have a href attribute, then creates a list of only the href values.
    """

    
    pattern = re.compile(r"<***beginning of pattern***>/page:(\d+)/?")
    """
    Creates a regex that matches URLs and captures the number at the end of the pattern which indicates the page number.
    """

    page_numbers = []

    for href in hrefs:
        m = pattern.search(href)
        if m:
            try:
                page_numbers.append(int(m.group(1)))
            except ValueError:
                pass

    if page_numbers:
        return max(page_numbers)
    """
    Loops through all the hrefs and if they match the pattern in the regex, it grabs the page number.
    It then returnss the largest page number found as it will be the total number of pages.
    """

    m2 = re.search(r"of\s+(\d{1,3})\b", soup.get_text(" "), flags=re.IGNORECASE)
    if m2:
        try:
            return int(m2.group(1))
        except ValueError:
            pass
    """
    The fallback method that searches the text content of the page for "of  N" where N is up to 3 digits, 
    and if found returns N.
    """

    print("[warn] Could not detect total pages. Defaulting to 1.")
    return 1
    """
    If all else fails, then the script defaults to return 1.
    """


def main() -> None:
    time.sleep(0.5)
    """
    Addds small 0.5 second delay before starting for politeness to the server and void hammering instantly.
    """

    print("[info] Fetching first listing page...") 
    try:
        html = fetch_html(LISTING_URL)
    except requests.HTTPError as e:
        print(f"[error] HTTP error: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"[error] Network error: {e}")
        sys.exit(1)
    """
    Prints a status message to us so we knwo what is happening.
    Calls the function to download the HTML for the first page (LISTING_URL) that we defined earlier.
    If the server responds with a bad HTTP request (4xx, 5xx) it prints an error 
    and exists the program with code 1 signalling a failure.
    If any other network errors occur, it handles it in the same way as a bad HTTP request.
    """

    # plain: save the HTML locally for inspection
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"[info] Saved HTML to {OUTPUT_HTML.resolve()}")
    """
    Saves the fetched HTML to a a file we defined earlier in OUTPUT_HTML to be used for later inspection or debugging.
    Prints a message to the us to indicate success and where the file was saved.
    """

    total_pages = parse_total_pages(html)
    print(f"[result] Detected total pages: {total_pages}")
    """
    Runs the function to extract the totla number of pages from the HTML so that future scripts know how many pages to scrape.
    Then prints the reuslt of this step to us whci will the total number of pages to scrape.
    """

if __name__ == "__main__":
    main()
"""
Every Python file has a built-in variable called __name__ that is set to the name of the file.
If the file is the main program that is being run, __name__ will be set to "__main__".
If the file is being imported as a module, __name__ will be set to the name of the file.
This allows us to run the main function only if the file is being run directly, not when it is imported as a module.
This is useful for testing and debugging.
"""


