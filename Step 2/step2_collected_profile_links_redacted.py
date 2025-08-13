"""
step2_collect_profile_links.py

Plain English:
- Reuses the page count detection from step 1 script.
- Visit every listing page (1..N).
- Grab every profile link that looks like '/***__***/<slug>'.
- Repeat the whole sweep several times (stability passes) because the site may reshuffle profileson pages.
- Stop once we stop discovering new links (or after MAX_PASSES).
- Save the unique list of profile URLs to 'links.txt' for the next step.

Technical:
- Uses requests + BeautifulSoup to fetch and parse HTML.
- Link extraction is regex-based ('/***__***/<slug>/') to avoid brittle selectors.
- Rate limiting with a randomized delay to be polite.
- Simple "fixpoint" loop: keep sweeping pages until the set of URLs no longer grows.
"""

from __future__ import annotations
"""
Changes how python interprets hints like x:MyClass, by storing all annotations as stirngs.
This lets use reference classes, functions, or types, before they are defined in our file wihtout quotes
and without causing NameErrors.
"""

import random
import re
import sys
import time
"""
random used for generating random number or making random choices.
re is regular expressions for pattern matching in text.
sys allows for system level operations like exiting with a status code.
time allows for time related functions like sleeping for a certain duration.
They help for randomness in polite delays, regex matching, exiting when an error occurs in the client or server.
"""

from pathlib import Path
from typing import Iterable, Set, List
"""
Path enables an object-orientated way to work with file and directory paths.
Iterable, Set and List are type hints fro python's typing system to make our code 
more understandable and help with static type checking.
"""

import requests
from bs4 import BeautifulSoup

# -----------------------
# Config (easy to tweak)
# -----------------------

BASE_URL = "***scheme, subdomain and domain***"
SPECIALTY_PATH = "***path to listing page***"  
LISTING_URL = f"{BASE_URL}{SPECIALTY_PATH}"
"""
Defines where to start and how the pages are built.
Allows for further paths to be appeneded to the listing URL to access other pages.
Enables flexibility if you want to go to a different listing page set.
"""

REQUEST_TIMEOUT = 20  # seconds
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}
"""
Same as seen in step 1.
Used to prevent hangs and avoids trivial blocking through a realistic user-agent.
"""


REQUEST_DELAY_RANGE = (0.7, 1.3)
MAX_PASSES = 5
OUTPUT_LINKS_FILE = Path("links.txt")
"""
Randomises delays between requests to avoid bein detected by bot detectors.
Max passes is the number of times the page is reloaded and swept in the situations 
where the links are shuffled each time the page is loaded, which ensures that we collect all the profile links.
We store the list of profile URLs in the text file 'links.txt' for the next step.
"""





# -----------------------
# Utilities
# -----------------------

def sleep_a_bit() -> None:
    low, high = REQUEST_DELAY_RANGE
    time.sleep(random.uniform(low, high))
"""
Jittered delay per request to reduce bot-like behaviour and reduce rate spike.
It aims to add extra delays when we have retries.
"""


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text
"""
Defines the fetch_html function and takes a URL string and returns a string (type hints).
Makes a single GET HTTP request to the URL, sending some custom headers for the User-Agent and stopping if it 
takes longer than REQUEST_TIMEOUT.
If the HTTP status code is an error (4xx or 5xx) then it raises an exception instaed of returning a page.
Upon a successful response, it returns the HTML or other text content.

"""


def choose_parser() -> str:
    try:
        import lxml  # noqa: F401
        return "lxml"
    except Exception:
        return "html.parser"
"""
Defines a function to choose the HTML parser.
It first tries the lxml parser which is faster and more robust.
Uses the built-in html.parser if lxml is not available.
"""

def detect_total_pages(html: str) -> int:
    soup = BeautifulSoup(html, choose_parser())
    hrefs = [a.get("href", "") for a in soup.find_all("a") if a.get("href")]
    pattern = re.compile(r"/***profiles***/page:(\d+)/?")
    nums = []
    for h in hrefs:
        m = pattern.search(h)
        if m:
            try:
                nums.append(int(m.group(1)))
            except ValueError:
                pass
    return max(nums) if nums else 1
"""
Defines a function to detect the total number of profile listing pages.
Uses a site specific regex on anchor hrefs to find the page numbers.
Finds the largest page number, which should be the total number of pages, and returns that value.
This is the same process used in step 1.
"""

def build_listing_page_url(page: int) -> str:
    if page <= 1:
        return LISTING_URL
    return f"{BASE_URL}{SPECIALTY_PATH}page:{page}/"
"""
Defines a function to construct and return the URLs of the individual pages.
This was specific to the site this code was used on that did not follow the same pattern for page 1, 
but followed a pattern for page 2 and onwards.
"""

def extract_profile_links(html: str) -> Set[str]:
    soup = BeautifulSoup(html, choose_parser())
    links: Set[str] = set()
    hrefs = [a.get("href", "") for a in soup.find_all("a") if a.get("href")]

    profile_re = re.compile(r"^/profiles/[^/]+/?$")

    for href in hrefs:
        if href.startswith("http"):
            if href.startswith(f"{BASE_URL}/profile/"):
                if not href.endswith("/"):
                    href = href + "/"
                links.add(href)
            continue

        if profile_re.match(href):
            if not href.endswith("/"):
                href = href + "/"
            links.add(f"{BASE_URL}{href}")

    return links
"""
Defines a function that takes a string containing HTML markup and returns a set of strings contraining the profile links.
Parses the HTMl and uses the choose parser function.
Finds all <a> tags in the HTML and gets their href attributes if they exist.
A URL pattern is compiled for the profile URLs, in the example following /profiles/<name>, 
but not deeper paths like /profiles/<name>/<etc>
Loops through all the hrefs and if it starts with http then check whether it begins with the base URL and /profile/
then normalises it to end with / then adds it to links set.
A second check is done where if the profile matches the compiled regex then it is a profile link 
then it is normalised and added to the link set, this may result in duplciates but is handled in the next function.
We are then returned a set of profile URLs.
"""

def save_links(links: Iterable[str], path: Path) -> None:
    text = "\n".join(sorted(set(links)))
    path.write_text(text, encoding="utf-8")
"""
Function that accepts a collection of links (the URLs)
The links are converted to a set to remove duplciates then ordered alphabetically, 
then they are all joined into one big string with each URL given its own line.
The text is then written to the file specified by path, using UTF-8 encoding.
"""

def load_links(path: Path) -> Set[str]:
    """
    Plain: Read URLs from a text file (if it exists).
    Tech: Returns a set for de-duplication between runs.
    """
    if not path.exists():
        return set()
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return set()
    return set(line.strip() for line in content.splitlines() if line.strip())
"""
Defines function that points to a file that should contain the URLs and returns it as a set of strings.
If the file does not exist then it returns an empty set.
If the file does exist then the text file is read as UTF-8 text, then the white spaces are removed and assigns it to content.
If the file is empty after stripping then return an empty string.
The content is then split into lines and another check for whitespaces is done, 
ignoring blank lines, before it is returned as a set to remove duplcaites.
"""

# -----------------------
# Main collection logic
# -----------------------

def collect_all_profile_links(max_passes: int = MAX_PASSES) -> List[str]:
    print("[info] Fetching first page to detect total pages...")
    html_first = fetch_html(build_listing_page_url(1))
    sleep_a_bit()
    """
    Fetches the HTML of the first page.
    """

    total_pages = detect_total_pages(html_first)
    print(f"[info] Detected total pages: {total_pages}")
    """
    Uses the HTML of the first page to detect the total number of pages.
    """

    discovered: Set[str] = load_links(OUTPUT_LINKS_FILE)
    if discovered:
        print(f"[info] Loaded {len(discovered)} existing links from {OUTPUT_LINKS_FILE}")
    """
    Loads any existing links from the output file, if it exists (avoiding duplcaition and resuming scraping).
    Allows for the script to be run multiple times wihtout starting from scratch, 
    e.g., if initial number of runs did not collect all profiles, 
    the script can be ran again to start from where you left off.
    """

    for p in range(1, max_passes + 1):
        print(f"[info] === Pass {p}/{max_passes} ===")
        pass_start_count = len(discovered)
        """
        Runs multiple passes over each page, aiming to overcome shuffling and collect all profiles.
        Assigns the number of links found so far to pass_start_count.
        """

        for page in range(1, total_pages + 1):
            url = build_listing_page_url(page)
            print(f"[info] Page {page}/{total_pages}: GET {url}")
            try:
                html = fetch_html(url)
            except requests.HTTPError as e:
                print(f"[warn] HTTP error on page {page}: {e}")
                continue
            except requests.RequestException as e:
                print(f"[warn] Network error on page {page}: {e}")
                continue
            """
            For each page up till the total number of pages it builds the URL of the page.
            Displays its progress out of the total number of pages.
            Fetches the HTMl of the page URL.
            Displays error but passes as exception if HTTP or Network error occurs.
            """

            new_links = extract_profile_links(html)
            before = len(discovered)
            discovered.update(new_links)
            after = len(discovered)
            found_now = after - before
            print(f"[info]   Found {len(new_links)} links on this page, +{found_now} new (total {after})")
            """
            Extracts the profile links from the HTML of the page.
            Shows the number of new profile links found on that pass of the page 
            and updates the set of links with any new ones found.
            """

            sleep_a_bit()
            """
            For politeness.
            """

        save_links(discovered, OUTPUT_LINKS_FILE)
        print(f"[info] Saved {len(discovered)} unique links to {OUTPUT_LINKS_FILE}")
        """
        After each pass the full set of links is written to the output file, acting as a checkpoint.
        """

        pass_gain = len(discovered) - pass_start_count
        print(f"[info] Pass {p} discovered +{pass_gain} new links")

        if pass_gain == 0:
            print("[info] No new links this pass. Stopping early.")
            break
        """
        Tracks the number of new links found in the pass and determines whether to pass again or stop early.
        """

    return sorted(discovered)
"""
Function that takes the maximum number of passes as an input, ensuring it is type integer, 
and returns a list of strings (the profile URLs).
"""

def main() -> None:
    try:
        links = collect_all_profile_links(MAX_PASSES)
    except requests.RequestException as e:
        print(f"[error] Request failure: {e}")
        sys.exit(1)

    print(f"[result] Total unique profile links collected: {len(links)}")

    for sample in links[:5]:
        print(f"  - {sample}")
"""
Defines a main function with a type hint that it returns nothing.
It first runs the collect_all_profile_links function with the MAX_PASSES value.
Catches the network/request related errors nad exits the program with an error code.
Prints a summary of the number of unique profile links collected.
Prints a sample of the first 5 links.
"""

if __name__ == "__main__":
    main()
"""
Run main() only if the scipt is run directly not imported.
"""