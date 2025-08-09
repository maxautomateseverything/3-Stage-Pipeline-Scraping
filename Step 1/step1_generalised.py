#!/usr/bin/env python3
"""
generic_detect_pages.py

Detect total number of pages for a listing URL using multiple heuristics.

Usage:
    python generic_detect_pages.py https://example.com/products/
"""

from __future__ import annotations

import re
import sys
import time
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin, parse_qs

import requests
from bs4 import BeautifulSoup

# ---------- Config ----------
REQUEST_TIMEOUT = (5, 20)  # (connect, read) seconds
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
SAVE_HTML_TO: Optional[Path] = None  # set to Path("first.html") to save
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
}
# ---------- End config ----------

@dataclass
class DetectionResult:
    total_pages: int
    method: str           # which heuristic succeeded (rel=last, numbered links, query param, text, default)
    pattern_example: str  # example URL or text evidence (if available)

def choose_parser() -> str:
    try:
        import lxml  # noqa: F401
        return "lxml"
    except Exception:
        return "html.parser"

def session_with_retries() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def get_html(url: str, session: requests.Session) -> str:
    backoff = INITIAL_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                raise
            # exponential backoff with jitter
            sleep_s = backoff + random.uniform(0, 0.5)
            time.sleep(sleep_s)
            backoff *= 2
    raise RuntimeError("Unreachable")

def extract_numbers_from_links(soup: BeautifulSoup, base_url: str) -> tuple[int, Optional[str]]:
    """
    Inspect <nav>/<ul class=...pagination...> areas and all <a> for numeric page links.
    Returns (max_page, example_href or None)
    """
    max_num = 0
    example = None

    # Prefer obvious pagination containers, but fall back to all links.
    link_candidates = []
    for css in ["nav", ".pagination", ".pager", ".paginations", ".page-numbers", ".paginacao"]:
        link_candidates.extend(soup.select(f"{css} a"))
    if not link_candidates:
        link_candidates = soup.find_all("a")

    number_re = re.compile(r"(?<!\d)(\d{1,5})(?!\d)")
    for a in link_candidates:
        href = a.get("href") or ""
        text = (a.get_text() or "").strip()

        # If the link text is a number, it's very likely a page index.
        if text.isdigit():
            n = int(text)
            if n > max_num:
                max_num, example = n, href
            continue

        # Otherwise, try to pull a trailing number from the URL
        m = number_re.search(href)
        if m:
            try:
                n = int(m.group(1))
                if n > max_num:
                    max_num, example = n, href
            except ValueError:
                pass

    return max_num, (urljoin(base_url, example) if example else None)

def rel_last_href(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    # <link rel="last" href="..."> (HTML head)
    for link in soup.find_all("link", rel=lambda v: v and "last" in v):
        href = link.get("href")
        if href:
            return urljoin(base_url, href)
    # <a rel="last"> (in body)
    for a in soup.find_all("a", rel=lambda v: v and "last" in v):
        href = a.get("href")
        if href:
            return urljoin(base_url, href)
    return None

def try_common_patterns(href: str) -> Optional[int]:
    """
    Try to parse an integer page index from a URL with common patterns.
    """
    # ...?page=12 or ...?p=12
    qs = parse_qs(urlparse(href).query)
    for key in ("page", "p"):
        if key in qs:
            try:
                return int(qs[key][0])
            except (ValueError, IndexError):
                pass

    # /page/12/   /page:12/   /p/12/
    m = re.search(r"/(?:page|p)[:/](\d+)(?:/|$)", href)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    # WordPress-style .../page/12?foo=bar (already handled by regex above)
    return None

def parse_page_count_text(soup: BeautifulSoup) -> Optional[int]:
    """
    Parse visible text like 'Page 1 of 25' in English + a couple of variants.
    """
    text = soup.get_text(" ").strip()

    patterns = [
        r"\bPage\s+\d+\s+of\s+(\d{1,5})\b",            # English
        r"\bSeite\s+\d+\s+von\s+(\d{1,5})\b",          # German
        r"\bPágina\s+\d+\s+de\s+(\d{1,5})\b",          # ES/PT basic
        r"\bPagina\s+\d+\s+di\s+(\d{1,5})\b",          # Italian
        r"\bPage\s+(\d{1,5})\s*/\s*\d{1,5}\b",         # 'Page 25 / 300' (less common)
        r"\bof\s+(\d{1,5})\b",                         # very broad, last resort
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None

def detect_total_pages(url: str) -> DetectionResult:
    parser = choose_parser()
    sess = session_with_retries()
    html = get_html(url, sess)
    if SAVE_HTML_TO:
        Path(SAVE_HTML_TO).write_text(html, encoding="utf-8")

    soup = BeautifulSoup(html, parser)

    # 1) rel="last"
    last = rel_last_href(soup, url)
    if last:
        n = try_common_patterns(last)
        if n:
            return DetectionResult(n, "rel=last", last)

    # 2) numbered links inside pagination
    max_num, example = extract_numbers_from_links(soup, url)
    if max_num > 0:
        # if we have an example href, try to confirm with common patterns
        if example:
            n2 = try_common_patterns(example)
            if n2 and n2 == max_num:
                return DetectionResult(max_num, "numbered-links+pattern", example)
        return DetectionResult(max_num, "numbered-links", example or "")

    # 3) visible "Page 1 of N"
    n = parse_page_count_text(soup)
    if n:
        return DetectionResult(n, "page-count-text", "visible text")

    # 4) default
    return DetectionResult(1, "default", "")
    
def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python generic_detect_pages.py <LISTING_URL>")
        return 2
    url = argv[1]
    # small polite delay for repeated runs
    time.sleep(0.4 + random.uniform(0, 0.4))
    try:
        res = detect_total_pages(url)
    except requests.RequestException as e:
        print(f"[error] Network/HTTP error: {e}")
        return 1
    print(f"[result] total_pages={res.total_pages} method={res.method} evidence={res.pattern_example}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
