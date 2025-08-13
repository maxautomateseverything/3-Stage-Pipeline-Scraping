"""
step3_scrape_profiles.py

What this script does (plain English)
- Reads profile URLs from links.txt (created in Step 2).
- For each profile page, downloads the HTML (politely, with small delays and retries).
- Extracts the configured fields from the profile.
- Writes all rows to profile.csv with one row per profile.

What this script does (technical)
- requests + BeautifulSoup (lxml when available) to fetch and parse HTML.
- Field registry pattern for simple scalar fields (strings/bools).
- A dedicated extractor for LOCATIONS that returns a list[str], expanded into N CSV columns.
- Robustness: HTML-first selectors (based on your DevTools info), JSON-LD fallback for rating/count, regex fallback for profile_id.
"""

from __future__ import annotations
"""
Enables type hints for all annotations to be stored as plain strings, instead of objects,
until they are actually needed.
"""

import csv
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional, Any, List, Tuple
"""
Standrd libraries for CSV I/O, JSON-LD parsing, polite delays, regex, edit codes, type safety and paths.
"""

import requests
from bs4 import BeautifulSoup
"""
HTTP client and HTML parser.
"""


# =========================
# Config (easy to edit)
# =========================

INPUT_LINKS_FILE = Path("links.txt")
OUTPUT_CSV = Path("profile.csv")

LOCATIONS_COLUMNS = 8
"""
How many locations columns to create.
Can be used to define any lists on a profile that you want stored as columns.
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
DELAY_RANGE = (0.7, 1.3)    
MAX_RETRIES = 3             
BACKOFF_BASE = 1.5          
"""
Set max wait time for page to load.
Uses more realistic user agent to prevent simple bot detection.
Uses randomised delays between page requests to avoid bot detection.
Maximum tries to request a profile.
Exponential backoff factor between retries.
"""

VERBOSE = True
"""
Enables extra logging which is useful to see what is happening, especially when debugging.
"""


# =========================
# Helpers
# =========================

def sleep_a_bit() -> None:
    low, high = DELAY_RANGE
    time.sleep(random.uniform(low, high))
"""
Jittered delay per request, choosing randomely from a uniform distribution.
"""

def choose_parser() -> str:
    try:
        import lxml  # noqa: F401
        return "lxml"
    except Exception:
        return "html.parser"
"""
Use lxml if installed, otherwise use the default HTML parser.
"""


def safe_get(url: str) -> Optional[str]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            wait = (BACKOFF_BASE ** (attempt - 1)) + random.uniform(0, 0.5)
            if VERBOSE:
                print(f"[warn] Fetch failed (attempt {attempt}/{MAX_RETRIES}) for {url}: {e}")
                print(f"[info] Backing off ~{wait:.1f}s before retry")
            time.sleep(wait)
    if VERBOSE:
        print(f"[error] Giving up on {url} after {MAX_RETRIES} attempts")
    return None
"""
GET request with restries, exponential back and jutter.
Swallows errors after MAX_RETRIES.
"""


def load_links(path: Path) -> List[str]:
    if not path.exists():
        print(f"[error] Cannot find {path}. Run step 2 first.")
        sys.exit(1)
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
"""
Dependent on step 2 for file links.txt to exist.
Loads and reads the file to retrieve a list of profile URLs.
"""


# =========================
# JSON-LD utilities
# =========================

def _iter_jsonld_objects(soup: BeautifulSoup) -> List[Any]:
    objs: List[Any] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.text or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict):
            objs.append(data)
            graph = data.get("@graph")
            if isinstance(graph, list):
                objs.extend(graph)
        elif isinstance(data, list):
            objs.extend(data)
    return objs
"""
Function for extractin and parsing JSON-LD data from a HTML page.
Given a BeautifulSoup object, find all the embedded JSON-LD objects, then returns a list of parsed JSON objects.
First create empty list to store extracted JSON-LD objects.
Loops through every JDON-LD tag in the html, which often contain metadata.
Tries to get the JSON text inside the script tag, using .string first then .text as a fallback, 
defaulting to an empty string if neither is present.
Attempts to parse the raw string into a python object using json.loads, 
and skips to the next tag if the parsing fails (i.e., invalid JSON).
If parsed data is a dictionary, it adds it to the list.
If it contains a @graph key, it adds the contents of @graph to the list.
If parsed data is a list, it adds the entire list to the list.
Then returns the full list of structured data objects found in the page.
"""

def _json_get(obj: Any, key: str) -> Any:
    return obj.get(key) if isinstance(obj, dict) else None
"""
Tiny helper to safely get a key from a dict-like JSON-LD node.
"""

# =========================
# Field registry (scalar)
# =========================

Extractor = Callable[[BeautifulSoup, str, str], str]

@dataclass
class Field:
    name: str
    extractor: Extractor
"""
Defines a type alias called Extractor.
The funcation can be called, and takes three arguments: a BeautifulSoup object, 
a string of HTML, and a string of the URL, and returns a string.
@dataclass automatically generates boilerplae methods for the class.
"""

# =========================
# Individual extractors
# =========================

def extract_name(soup: BeautifulSoup, html: str, url: str) -> str:
    
    for obj in _iter_jsonld_objects(soup):
        n = _json_get(obj, "name")
        if isinstance(n, str) and n.strip():
            return n.strip()
    """
    Loops over JSON-LD on the page, and if it finds a name field that is non-empty it return it imemdiately.
    This is preferred source since JSON-LD contain clean, machine readable data.
    """

    for selector in ["h1", "header h1", ".profile-name h1", ".title.is-1"]:
        node = soup.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            if text:
                return text
    """
    HTML elememmts used as a fallback, if JSON-LD is not present.
    Tries to find the name in common header elements (<h1>) and uses 
    get_text(" ", strip=True) to clean the whitespaces and get visible text.
    """

    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        val = re.sub(r"\s*\|\s*Top profiles.*$", "", meta["content"]).strip()
        return val
    return ""
    """
    Last fallback to open graph meta tag (og:title) whic many sites use for social sharing.
    Removes trailing text like "Top profiles" from the title, to keep name clean.
    """


def extract_speciality(soup: BeautifulSoup, html: str, url: str) -> str:
    specific_specialty_keywords = ("coder", "marketing", "science")
    for obj in _iter_jsonld_objects(soup):
        for key in ("Specialty", "specialty", "speciality", "specialties"):
            val = _json_get(obj, key)
            def norm(s: str) -> str:
                return re.sub(r"\s+", " ", s).strip()
            if isinstance(val, str) and val.strip():
                return norm(val)
            if isinstance(val, list):
                texts = []
                for it in val:
                    if isinstance(it, str) and it.strip():
                        texts.append(norm(it))
                    elif isinstance(it, dict):
                        n = it.get("name")
                        if isinstance(n, str) and n.strip():
                            texts.append(norm(n))
                if texts:
                    for t in texts:
                        if any(k in t.lower() for k in specific_specialty_keywords):
                            return t
                    return ", ".join(texts)

    # HTML guesses (safe, generic; we prefer JSON-LD when present)
    for selector in [".tags .tag", ".specialties", ".specialities", ".profile-specialties", ".subtitle", ".title + .subtitle"]:
        nodes = soup.select(selector)
        texts = [n.get_text(" ", strip=True) for n in nodes if n.get_text(strip=True)]
        specific_specialty_ish = [t for t in texts if any(k in t.lower() for k in specific_specialty_keywords)]
        if specific_specialty_ish:
            return ", ".join(sorted(set(specific_specialty_ish)))
        if texts:
            return ", ".join(sorted(set(texts[:3])))
    return ""
"""
Similar to name, first looks for JSON-Ld structured data fields, then tries to parse the HTML badges 
and if there are multiple matches, prefers to collect the ones that are most closely related 
to the specific specialty keywords.
"""

def extract_profile_id(soup: BeautifulSoup, html: str, url: str) -> str:
    # JSON-LD
    for obj in _iter_jsonld_objects(soup):
        ident = _json_get(obj, "identifier")
        def dig(v: Any) -> Optional[str]:
            if isinstance(v, str):
                m = re.search(r"\bprofile_id\b[:\s]*([0-9]{5,8})\b", v, flags=re.I)
                return m.group(1) if m else None
            if isinstance(v, dict):
                pid = v.get("propertyID") or v.get("name")
                val = v.get("value") or v.get("identifier") or v.get("id")
                if isinstance(pid, str) and "profile_id" in pid.lower() and isinstance(val, (str, int)):
                    return str(val)
            if isinstance(v, list):
                for it in v:
                    got = dig(it)
                    if got:
                        return got
            return None
        got = dig(ident)
        if got:
            return got

    # Text fallbacks
    text = soup.get_text(" ", strip=True)
    m = re.search(r"\bprofile_id(?:\s*number)?\b[:\s]*([0-9]{5,8})\b", text, flags=re.I)
    if m:
        return m.group(1)
    m2 = re.search(r"profile_id[^0-9]{0,20}([0-9]{5,8})", html, flags=re.I | re.S)
    if m2:
        return m2.group(1)
    return ""
"""
Uses JSON-LD to find profile id, then falls back to regex then raw HTMl search.
"""


def extract_review_rating(soup: BeautifulSoup, html: str, url: str) -> str:
    node = soup.select_one("span.text-average-rating")
    if node:
        txt = node.get_text(" ", strip=True)
        # expected like "5.0 |"
        m = re.match(r"(\d+(?:\.\d+)?)", txt)
        if m:
            return m.group(1)

    # JSON-LD fallback
    for obj in _iter_jsonld_objects(soup):
        agg = _json_get(obj, "aggregateRating")
        if isinstance(agg, dict):
            rv = agg.get("ratingValue")
            if isinstance(rv, (int, float)):
                return str(rv)
            if isinstance(rv, str) and rv.strip():
                m = re.match(r"(\d+(?:\.\d+)?)", rv.strip())
                if m:
                    return m.group(1)

    return "None"
"""
Review rating:
- HTML (per your DevTools): <span class="text-average-rating">5.0 | &nbsp; </span>
    -> We take the leading number.
- Fallback: JSON-LD aggregateRating.ratingValue, if present.
- If missing: return "None" (string), as requested for empty cases.
"""


def extract_review_count(soup: BeautifulSoup, html: str, url: str) -> str:
    node = soup.select_one("a.review-count")
    if node:
        txt = node.get_text(" ", strip=True)
        m = re.search(r"\d+", txt)
        if m:
            return m.group(0)

    for obj in _iter_jsonld_objects(soup):
        agg = _json_get(obj, "aggregateRating")
        if isinstance(agg, dict):
            rc = agg.get("reviewCount")
            if isinstance(rc, (int, float)):
                return str(int(rc))
            if isinstance(rc, str) and rc.strip():
                m = re.search(r"\d+", rc)
                if m:
                    return m.group(0)

    return "None"
"""
Review count:
- HTML (per your DevTools): <a class="review-count">37 ...</a>
    -> We extract the integer.
- Fallback: JSON-LD aggregateRating.reviewCount.
- If missing: return "None".
"""


def extract_LOCATIONS_list(soup: BeautifulSoup, html: str, url: str) -> List[str]:
    LOCATIONS: List[str] = []
    # container
    ul = soup.select_one("ul.office-wrapper")
    if not ul:
        return LOCATIONS

    # items
    for li in ul.select("li.office"):
        h3 = li.select_one("h3.main-title")
        if not h3:
            # be a bit tolerant if class names vary slightly
            h3 = li.find("h3")
        if h3:
            name = h3.get_text(" ", strip=True)
            if name:
                LOCATIONS.append(name)
    return LOCATIONS
"""
LOCATIONS list (each LOCATIONS in separate CSV columns later):
- HTML per your DevTools:
    <ul class="office-wrapper">
        <li class="office"> ... <h3 class="main-title ...">Example Location</h3> ... </li>
    </ul>
- We collect *all* h3.main-title under li.office within ul.office-wrapper.
- Return a list of LOCATIONS names (strings). The writer layer will fan these into LOCATIONS_1..LOCATIONS_N.
"""


def extract_econsultations(soup: BeautifulSoup, html: str, url: str) -> str:
    for span in soup.select("span.action-button-text"):
        text = span.get_text(" ", strip=True)
        if text.lower() == "e-consultation":
            return "True"
    return "False"
"""
E-consultations (True/False):
- Presence of: <span class="action-button-text ...">e-Consultation</span>
- Case-insensitive match on the inner text 'e-Consultation'.
- If present -> "True"; otherwise "False".
"""


def extract_online_booking(soup: BeautifulSoup, html: str, url: str) -> str:
    # first, the simple/text-robust check
    for btn in soup.find_all("button"):
        span = btn.find("span", class_="action-button-text")
        if span:
            text = span.get_text(" ", strip=True)
            if text.lower() == "book":
                # optional: ensure it's actually actionable
                classes = btn.get("class", [])
                if isinstance(classes, list):
                    # If 'is-clickable' is there, this is very likely enabled
                    if "is-clickable" in classes:
                        return "True"
                    # If not present, still treat as True for now; tighten later if needed
                    return "True"
                return "True"
    return "False"
"""
Online booking (True/False):
- Presence of a clickable 'Book' button per your DevTools:
    <button class="... is-clickable ..."><span class="action-button-text">Book</span></button>
- We'll check for a <button> containing a span.action-button-text with text 'Book'.
- If present -> "True", else "False".
- If you notice false positives/negatives later, we can tighten with an 'is-clickable' class check.
"""

# =========================
# Field registry (scalar fields only)
# =========================

FIELD_REGISTRY: Dict[str, Extractor] = {
    "name": extract_name,
    "speciality": extract_speciality,
    "profile_id": extract_profile_id,
    "review_rating": extract_review_rating,
    "review_count": extract_review_count,
    "e_consultations": extract_econsultations,
    "online_booking": extract_online_booking,
}
# NOTE: LOCATIONS are handled separately (list expanded to N columns).


# =========================
# Main
# =========================

def scrape_profile(url: str) -> Tuple[Dict[str, str], List[str]]:
    row = {k: "" for k in FIELD_REGISTRY.keys()}
    html = safe_get(url)
    if html is None:
        return row, []

    soup = BeautifulSoup(html, choose_parser())

    for field, func in FIELD_REGISTRY.items():
        try:
            row[field] = func(soup, html, url) or ""
        except Exception as e:
            if VERBOSE:
                print(f"[warn] Extractor '{field}' failed for {url}: {e}")
            row[field] = ""

    LOCATIONS = []
    try:
        LOCATIONS = extract_LOCATIONS_list(soup, html, url)
    except Exception as e:
        if VERBOSE:
            print(f"[warn] LOCATIONS extractor failed for {url}: {e}")
        LOCATIONS = []

    return row, LOCATIONS
"""
Function that takes a URL as a string and returns a tuple with a dictionary and list of strings.
Creates an empty row, then fetches the JTML from the URL and parses it.
Extracts each of the configured fields, and if there is an error, it will print a warning.
Extracts the locations or your chosen list data seperately, and returns a tuple with the row and the locations.
"""


def main() -> None:
    links = load_links(INPUT_LINKS_FILE)
    if VERBOSE:
        print(f"[info] Loaded {len(links)} profile URLs from {INPUT_LINKS_FILE}")

    # Build CSV headers:
    # - scalar fields from FIELD_REGISTRY in order
    # - plus LOCATIONS_1 ... LOCATIONS_N
    LOCATIONS_headers = [f"LOCATIONS_{i}" for i in range(1, LOCATIONS_COLUMNS + 1)]
    fieldnames = list(FIELD_REGISTRY.keys()) + LOCATIONS_headers

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        have_name = 0
        for i, url in enumerate(links, start=1):
            print(f"[info] ({i}/{len(links)}) GET {url}")
            row, LOCATIONS = scrape_profile(url)

            # Expand LOCATIONS list into fixed columns (pad/truncate to LOCATIONS_COLUMNS)
            expanded = {}
            for idx in range(LOCATIONS_COLUMNS):
                val = LOCATIONS[idx] if idx < len(LOCATIONS) else ""
                expanded[f"LOCATIONS_{idx+1}"] = val

            writer.writerow({**row, **expanded})

            if row.get("name"):
                have_name += 1

            sleep_a_bit()

        print(f"[result] Wrote {len(links)} rows to {OUTPUT_CSV} (name found for {have_name}/{len(links)})")
"""
Main function that loads the links, builds the CSV headers, and writes the data to the CSV file.
Processes each link one by one to scrape the data, and ensures the locations fit into the predefined locations column.
Writes the combined rows to the CSV and keeps track of how many profiels have names.
Sleeps briefly between requests and prints the final result summary.
"""


if __name__ == "__main__":
    main()
"""
The script can only be excecuted directly, not imported as a module.
"""
