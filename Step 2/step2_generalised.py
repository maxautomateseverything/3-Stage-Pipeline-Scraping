#!/usr/bin/env python3
"""
generic_collect_links.py

Collect profile/detail links from a paginated listing.

Examples:
  python generic_collect_links.py \
    --start-url "https://example.com/profile/" \
    --profile-regex "^/profile/[^/]+/?$" \
    --out links.txt

  # With explicit page template and known pattern:
  python generic_collect_links.py \
    --start-url "https://example.com/profile/" \
    --page-template "https://example.com/profile/page:{page}/" \
    --profile-regex "^/profile/[^/]+/?$" \
    --out links.txt
"""

from __future__ import annotations
import argparse, random, re, sys, time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Set, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup

# --------- Defaults (tweakable) ---------
REQUEST_TIMEOUT = (5, 20)      # (connect, read) seconds
MAX_RETRIES = 3
BACKOFF_BASE = 1.0
DELAY_RANGE = (0.7, 1.4)
MAX_PASSES = 4
STRIP_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
# ----------------------------------------

@dataclass
class Detection:
    pages: List[str]     # absolute listing page URLs to visit
    method: str          # 'rel=last', 'numbered-links', 'template', 'single'

def choose_parser() -> str:
    try:
        import lxml  # noqa
        return "lxml"
    except Exception:
        return "html.parser"

def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; LinkCollector/1.0; +contact@example.com)",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    return s

def get_html(sess: requests.Session, url: str) -> str:
    backoff = BACKOFF_BASE
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = sess.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(backoff + random.uniform(0, 0.5))
            backoff *= 2

def sleep_politely():
    time.sleep(random.uniform(*DELAY_RANGE))

def strip_tracking(u: str) -> str:
    """Remove common tracking params and fragments for canonicalization."""
    pu = urlparse(u)
    q = [(k, v) for k, v in parse_qsl(pu.query, keep_blank_values=True) if k not in STRIP_PARAMS]
    return urlunparse((pu.scheme, pu.netloc, pu.path.rstrip("/"), pu.params, urlencode(q), ""))

def detect_pages(sess: requests.Session, start_url: str, page_template: Optional[str]) -> Detection:
    if page_template:
        # Simple numeric pagination template; try to discover the max page by inspecting first page
        html = get_html(sess, start_url)
        soup = BeautifulSoup(html, choose_parser())

        # Try rel=last or numbered links to guess N
        last_href = None
        for el in soup.find_all(["link", "a"], rel=lambda v: v and "last" in v):
            if el.get("href"):
                last_href = urljoin(start_url, el["href"])
                break

        max_n = 1
        if last_href:
            m = re.search(r"(?:page|p)[:/]=?(\d+)", last_href)
            if not m:
                m = re.search(r"/page[:/](\d+)", last_href)
            if m:
                max_n = int(m.group(1))

        if max_n == 1:
            # Fall back to scanning page for numbered links
            nums = set()
            for a in soup.find_all("a"):
                t = (a.get_text() or "").strip()
                if t.isdigit():
                    nums.add(int(t))
            if nums:
                max_n = max(nums)

        pages = [page_template.format(page=i) for i in range(1, max_n + 1)]
        return Detection(pages=pages, method="template" if max_n == 1 else "template+detectN")

    # No template: derive pages from the DOM of start page
    html = get_html(sess, start_url)
    soup = BeautifulSoup(html, choose_parser())

    # 1) rel=last
    last = None
    for el in soup.find_all(["link", "a"], rel=lambda v: v and "last" in v):
        if el.get("href"):
            last = urljoin(start_url, el["href"]); break
    if last:
        # collect all numbered page links to fill in between 1..N
        nums = set([1])
        for a in soup.find_all("a"):
            href = a.get("href")
            if not href: continue
            href = urljoin(start_url, href)
            # common patterns
            for pat in (r"[?&](?:page|p)=(\d+)", r"/page[:/](\d+)(?:/|$)"):
                m = re.search(pat, href)
                if m:
                    nums.add(int(m.group(1)))
        N = max(nums) if nums else 1
        # build plausible page URLs from the observed pattern; simplest approach is to take
        # the start_url as page 1 and try to mutate with common patterns
        # Prefer query param pattern if seen; else path pattern.
        has_query = any(re.search(r"[?&](?:page|p)=\d+", a.get("href") or "") for a in soup.find_all("a"))
        if has_query:
            base_no_q = strip_tracking(start_url)
            pages = [f"{base_no_q}{'&' if '?' in base_no_q else '?'}page={i}" if i > 1 else start_url for i in range(1, N+1)]
        else:
            # path style /page/<n>/
            # Ensure trailing slash on base for consistency
            if not start_url.endswith("/"): start_url_slash = start_url + "/"
            else: start_url_slash = start_url
            pages = [start_url_slash if i == 1 else urljoin(start_url_slash, f"page/{i}/") for i in range(1, N+1)]
        return Detection(pages=pages, method="rel=last")

    # 2) numbered links inside pagination
    candidates = set([start_url])
    for css in ["nav", ".pagination", ".page-numbers", ".pager"]:
        for a in soup.select(f"{css} a"):
            href = a.get("href")
            if not href: continue
            candidates.add(urljoin(start_url, href))
    # filter to pages that differ by common page patterns
    pages = sorted({u for u in candidates if re.search(r"(?:[?&](?:page|p)=\d+)|(?:/page[:/]\d+/?)", u)})
    if pages:
        # normalize into 1..N order by extracting numbers
        pairs = []
        for u in pages:
            m = re.search(r"(?:[?&](?:page|p)=(\d+))|(?:/page[:/](\d+))", u)
            if m:
                n = int(next(g for g in m.groups() if g))
                pairs.append((n, u))
        pairs.sort()
        pages_in_order = [start_url] + [u for n, u in pairs if n > 1]
        return Detection(pages=list(dict.fromkeys(pages_in_order)), method="numbered-links")

    # 3) fallback: just the start page
    return Detection(pages=[start_url], method="single")

def extract_links(html: str, base_url: str, profile_regex: re.Pattern) -> Set[str]:
    soup = BeautifulSoup(html, choose_parser())
    found: Set[str] = set()
    for a in soup.find_all("a"):
        href = a.get("href")
        if not href: continue
        absu = urljoin(base_url, href)
        if profile_regex.search(absu) or profile_regex.search(urlparse(absu).path):
            found.add(strip_tracking(absu))
    return found

def save_links(links: Iterable[str], out: Path) -> None:
    out.write_text("\n".join(sorted(set(links))), encoding="utf-8")

def load_links(out: Path) -> Set[str]:
    if not out.exists(): return set()
    txt = out.read_text(encoding="utf-8").strip()
    return set(l for l in txt.splitlines() if l.strip())

def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-url", required=True, help="First listing page URL")
    ap.add_argument("--page-template", help="Optional template with {page}, e.g. https://x/cat/page:{page}/")
    ap.add_argument("--profile-regex", required=True, help=r"Regex for profile URLs, e.g. ^/profile/[^/]+/?$")
    ap.add_argument("--out", default="links.txt", help="Output file")
    ap.add_argument("--max-passes", type=int, default=MAX_PASSES)
    args = ap.parse_args(argv[1:])

    profile_re = re.compile(args.profile_regex)

    sess = session()
    det = detect_pages(sess, args.start_url, args.page_template)
    print(f"[info] Listing pages: {len(det.pages)} (method={det.method})")

    discovered = load_links(Path(args.out))
    if discovered:
        print(f"[info] Loaded {len(discovered)} existing links from {args.out}")

    for p in range(1, args.max_passes + 1):
        start_count = len(discovered)
        print(f"[info] === Pass {p}/{args.max_passes} ===")
        for i, page_url in enumerate(det.pages, start=1):
            try:
                html = get_html(sess, page_url)
            except requests.RequestException as e:
                print(f"[warn] {page_url}: {e}")
                continue
            new = extract_links(html, page_url, profile_re)
            before = len(discovered)
            discovered.update(new)
            after = len(discovered)
            print(f"[info] Page {i}/{len(det.pages)}: +{after-before} new (found {len(new)} on page, total {after})")
            sleep_politely()
        save_links(discovered, Path(args.out))
        print(f"[info] Saved {len(discovered)} links → {args.out}")
        if len(discovered) == start_count:
            print("[info] Converged; stopping.")
            break

    # Sample
    print(f"[result] Total unique links: {len(discovered)}")
    for u in list(sorted(discovered))[:5]:
        print("  -", u)
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
