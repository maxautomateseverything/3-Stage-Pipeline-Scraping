# Purpose
Extract structured data from a set of profile pages into a clean CSV, robustly and politely, with site‑specific extraction rules in a simple config file.

## Quick start
```
pip install requests beautifulsoup4 lxml pyyaml
python generalized_profiles.py config.example.yml
```
## What to check before scraping (best practice)
- Legality & ethics

    - Read the site’s Terms of Service and robots.txt. Respect Disallow and any Crawl-delay.

    - If data is personal/sensitive, make sure you have a lawful basis to process it.

- Politeness

    - Set a realistic User‑Agent; optionally identify your project.

    - Use randomized delays, timeouts, and exponential backoff.

    - Cap concurrency (this script is single‑threaded by design).

- Stability

    - Prefer JSON‑LD or well‑labeled meta where present.

    - Save HTML samples during development to iterate selectors (you can add a debug flag).

    - Write small unit tests for extractors if you’ll run this regularly.

- Data hygiene

    - Decide how to treat missing values ("" vs "None").

    - Normalize whitespace and strip tracking query params if needed.

## How to find the info for the config (DevTools workflow)
1. Open a real profile page.

2. View source/Inspect:

    - Search for \<script type="application/ld+json"> and look for yours keys, e.g., name, description, etc.

    - If present, prefer JSON‑LD: add a jsonld or jsonld_path step.

3. If no JSON‑LD, inspect the element(s) visually:

    - Right‑click → Inspect the node (e.g., the H1).

    - Copy a stable CSS selector (avoid long, brittle chains—prefer IDs, semantic classes).

4. For booleans (buttons/badges), match the text of a nearby label (.action-button-text:contains("Book") → since we can’t use :contains in CSS, select the node and compare the text in code as done above).

5. For lists, identify a container and the repeated child (e.g., ul.office-wrapper li.office h3).

6. Test on 3–5 different profiles (varied content) and refine.

## When to use this approach (use cases)
- Server‑rendered pages with stable HTML and/or JSON‑LD (most CMS sites, directories, blogs).

- Moderate volume runs where single‑threaded politeness is acceptable.

- Fields with clear DOM anchors (headings, labels, badges, lists).

## Advantages
- Fast and lightweight (Requests + BS4, no browser overhead).

- Configurable (no code edits to port to a new site).

- Robust (multi‑step fallbacks; ignores extractor failures per field).

- CSV‑friendly (list expansion into fixed columns).

## Disadvantages / not a good fit
- JavaScript‑heavy/SPAs where key content is injected - client‑side (ratings, booking widgets). Use Playwright/- Selenium or call the site’s JSON API (inspect DevTools → Network).

- Highly dynamic UIs where classes/structure change per release.

- Cursor‑based backends where data lives behind a paginated API (the right approach is to page the API until empty, not scrape HTML).

## Tips
- If a field is numeric in downstream analysis, keep the CSV value blank "" for missing (instead of "None"), then cast to numeric with NA handling.

- If LOCATIONS can exceed the column budget regularly, either (a) increase max_columns, or (b) store a separate one‑to‑many CSV keyed by profile URL.