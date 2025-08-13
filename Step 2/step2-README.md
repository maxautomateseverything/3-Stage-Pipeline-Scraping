# Purpose
Collect all profile/detail page URLs from a paginated listing so later steps can scrape the details.

## Installation
```bash
pip install requests beautifulsoup4 lxml
```
## Usage
```
# Typical (auto-detect pagination)
python generic_collect_links.py \
  --start-url "https://example.com/profiles/" \
  --profile-regex "^/profile/[^/]+/?$" \
  --out links.txt

# With a known page template
python generic_collect_links.py \
  --start-url "https://example.com/profiles/" \
  --page-template "https://example.com/profiles/page:{page}/" \
  --profile-regex "^/profile/[^/]+/?$" \
  --out links.txt
```
## Before you run (best practice checklist)
- Read the site’s ToS & robots.txt

    - Check https://example.com/robots.txt for disallow rules and Crawl-delay. Respect them.

- Be polite

    - Randomized delays; retries with backoff; limit passes.

    - If you’ll run at scale, add an identifying UA like YourProject/1.0 (+email).

- Verify pagination style

    - Inspect the listing page: look for \<a rel="last">, .pagination, numbered links.

    - If it’s “Load more” / infinite scroll, the generalized HTML walker won’t see later items — prefer a JSON API (found via DevTools → Network).

- Define a precise --profile-regex

    - Sample 3–5 real profile URLs; craft a regex that matches them but not category/list pages.

    - Example patterns:

        - ^/profile/[^/]+/?$

        - ^/providers/[a-z0-9-]+/?$

        - ^/experts/[a-z-]+-[a-z-]+/\d+/?$

- Plan for normalization

    -  Decide whether to keep query params (many are tracking only).

    - Ensure http/https and trailing slash consistency if the site cares.

## How to find the information you need on a new site
1. Open the listing page.

2. Inspect pagination: Is there a next/last link? Are numbers visible? Are URLs ?page=2 or /page/2/?

3. Click a few profiles; copy their URLs; craft --profile-regex.

4. If infinite-scroll: in DevTools → Network, scroll; find the XHR/Fetch endpoint returning JSON; switch strategy to hitting the API directly (cursor/offset) and iterate until empty.

## Advantages of this approach
- Fast & lightweight for static HTML.

- Works on many CMSes (WordPress/Drupal/Magento) out of the box.

- Transparent behavior: prints how pagination was detected.

## Disadvantages / edge cases
- JS‑rendered content: needs Playwright/Selenium or JSON endpoints.

- Cursor‑based APIs: there may be no “total pages”; iterate until the endpoint returns no results.

- Exotic URL schemes: you may need to provide --page-template explicitly.

- Regex specificity: overly broad regex can collect non‑profile URLs; overly tight misses valid ones.

## Specific use cases (good fit)
- Directories, profile listings, blog/category archives, e‑commerce category pages with classic pagination.

## Not a good fit
- Infinite scroll without real page URLs and no rel="last"/numbers.

- Sites with heavy anti‑bot protections (aggressive WAF, JS challenges).

- Pages whose links are injected post‑render by JS.