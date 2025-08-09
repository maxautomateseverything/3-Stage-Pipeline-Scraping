# Web Scraper – Multi-Step Collection and Extraction

## Overview

This project is a **three-stage web scraping pipeline** that:

1. **Detects how many listing pages** exist for a given category.
2. **Collects all unique profile links** across those pages, even when the site changes the order or contents between page loads.
3. **Scrapes structured data** from each profile page, writing it to a CSV file for easy use in spreadsheet software.

The scraper is designed for **reliability** (to avoid missing any profiles) and **politeness** (with delays and retries), and is built to be **easily customizable** if you want to change what information is collected.

---
## Features

- Automatically detects the **total number of listing pages**.
- Collects all unique profile URLs using **multiple passes** to capture shuffled or dynamic listings.
- Extracts structured fields from each profile page
 Outputs clean, UTF-8 CSV files that open directly in Excel or similar tools.
- Modular design — each extractor is a separate, clearly commented function.
- Resilient parsing using **BeautifulSoup** with `lxml` fallback and HTML or JSON-LD detection.

## Requirements

- **Python** 3.10+ (tested with Python 3.13)
- Packages:
  - `requests` – HTTP client
  - `beautifulsoup4` – HTML parser
  - `lxml` *(optional but faster)*

### Install dependencies
```bash
pip install requests beautifulsoup4 lxml
```
---
## Files
There are **3 folders** representing each step. Each step contains:
- **Fully commented script** I used, redacting private information.
- **Generalised** script following the same logic.
- **README** file for the generalised script guiding users in how to apply it.