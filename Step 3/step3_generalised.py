#!/usr/bin/env python3
from __future__ import annotations
import csv, json, random, re, sys, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import yaml
import requests
from bs4 import BeautifulSoup

"""
Use the step3_redacted.py script to understand how to write a config.
And refer to the README to understand how to collect the data for the config.
"""

# ---------------- Core utilities ----------------

def choose_parser() -> str:
    try:
        import lxml  # noqa: F401
        return "lxml"
    except Exception:
        return "html.parser"

def session_with_policy(cfg: Dict[str, Any]) -> requests.Session:
    s = requests.Session()
    ua = cfg["politeness"].get("user_agent") or "Mozilla/5.0"
    s.headers.update({"User-Agent": ua, "Accept-Language": "en-GB,en;q=0.9"})
    return s

def polite_get(sess: requests.Session, url: str, cfg: Dict[str, Any]) -> Optional[str]:
    connect, read = cfg["politeness"].get("timeout", [5, 20])
    max_retries = cfg["politeness"].get("max_retries", 3)
    backoff_base = cfg["politeness"].get("backoff_base", 1.5)
    delay_lo, delay_hi = cfg["politeness"].get("delay_range", [0.7, 1.3])

    backoff = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            resp = sess.get(url, timeout=(connect, read))
            if resp.status_code in (429,) or 500 <= resp.status_code < 600:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt == max_retries:
                print(f"[error] {url}: {e}")
                return None
            wait = backoff + random.uniform(0, 0.5)
            print(f"[warn] {url}: {e} (retry {attempt}/{max_retries-1}) backoff~{wait:.1f}s")
            time.sleep(wait)
            backoff *= backoff_base
    return None

def sleep_politely(cfg: Dict[str, Any]) -> None:
    lo, hi = cfg["politeness"].get("delay_range", [0.7, 1.3])
    time.sleep(random.uniform(lo, hi))

# ---------------- JSON-LD helpers ----------------

def iter_jsonld(soup: BeautifulSoup) -> List[Any]:
    objs: List[Any] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.text or ""
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict):
            objs.append(data)
            if isinstance(data.get("@graph"), list):
                objs.extend(data["@graph"])
        elif isinstance(data, list):
            objs.extend(data)
    return objs

def jsonld_get_paths(obj: Any, keys: List[str]) -> Optional[str]:
    if not isinstance(obj, dict): return None
    for k in keys:
        v = obj.get(k)
        if isinstance(v, (str, int, float)): return str(v)
        if isinstance(v, dict) and "name" in v and isinstance(v["name"], str): return v["name"]
        if isinstance(v, list):
            texts = []
            for it in v:
                if isinstance(it, (str, int, float)):
                    texts.append(str(it))
                elif isinstance(it, dict) and isinstance(it.get("name"), str):
                    texts.append(it["name"])
            if texts: return ", ".join(texts)
    return None

def jsonld_identifier(obj: Any, providers: List[str]) -> Optional[str]:
    ident = obj.get("identifier") if isinstance(obj, dict) else None
    if ident is None: return None
    def dig(v: Any) -> Optional[str]:
        if isinstance(v, str):
            for p in providers:
                m = re.search(rf"\b{re.escape(p)}\b[:\s]*([0-9]{{4,10}})\b", v, flags=re.I)
                if m: return m.group(1)
        if isinstance(v, dict):
            pid = v.get("propertyID") or v.get("name") or ""
            val = v.get("value") or v.get("identifier") or v.get("id")
            if isinstance(pid, str) and any(p.lower() in pid.lower() for p in providers) and isinstance(val, (str, int)):
                return str(val)
        if isinstance(v, list):
            for it in v:
                got = dig(it)
                if got: return got
        return None
    return dig(ident)

# ---------------- Extraction engine ----------------

def extract_scalar(cfg_field: Dict[str, Any], soup: BeautifulSoup, html: str) -> str:
    steps = cfg_field.get("steps", [])
    default = cfg_field.get("default", "")
    for step in steps:
        if "jsonld" in step:
            keys = step["jsonld"]
            for obj in iter_jsonld(soup):
                val = jsonld_get_paths(obj, keys)
                if val: return val.strip()
        elif "jsonld_path" in step:
            path = step["jsonld_path"]
            for obj in iter_jsonld(soup):
                v = obj
                for key in path:
                    if isinstance(v, dict): v = v.get(key)
                    else: v = None; break
                if isinstance(v, (str, int, float)): return str(v)
        elif "jsonld_identifier" in step:
            for obj in iter_jsonld(soup):
                val = jsonld_identifier(obj, step["jsonld_identifier"]["providers"])
                if val: return val
        elif "css" in step:
            spec = step["css"]
            node = soup.select_one(spec["selector"])
            if not node: continue
            if spec.get("attr"):
                val = node.get(spec["attr"])
                if isinstance(val, str) and val.strip(): return val.strip()
            text = node.get_text(" ", strip=True) if spec.get("text") else ""
            if spec.get("text_re"):
                m = re.search(spec["text_re"], text or "")
                if m: return m.group(1)
            if text: return text
        elif "meta" in step:
            meta = soup.find("meta", property=step["meta"]["property"])
            if meta and meta.get("content"):
                val = meta["content"]
                suffix = step["meta"].get("strip_suffix")
                if suffix and suffix in val:
                    val = val.split(suffix)[0].strip()
                return val.strip()
        elif "regex_text" in step:
            m = re.search(step["regex_text"], soup.get_text(" ", strip=True), flags=re.I)
            if m: return m.group(1)
    return default

def extract_list(cfg_list: Dict[str, Any], soup: BeautifulSoup) -> List[str]:
    items = []
    for node in soup.select(cfg_list["selector"]):
        if cfg_list.get("text"):
            t = node.get_text(" ", strip=True)
        else:
            attr = cfg_list.get("attr")
            t = node.get(attr) if attr else node.get_text(" ", strip=True)
        if t:
            items.append(t)
    # de‑dupe while preserving order
    seen, out = set(), []
    for it in items:
        if it not in seen:
            out.append(it); seen.add(it)
    return out

def main():
    if len(sys.argv) < 2:
        print("Usage: python generalized_profiles.py config.yml")
        sys.exit(2)
    cfg_path = Path(sys.argv[1])
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))

    links_path = Path(cfg["input_links_file"])
    if not links_path.exists():
        print(f"[error] Missing {links_path}. Produce it in step 2.")
        sys.exit(1)
    links = [ln.strip() for ln in links_path.read_text(encoding="utf-8").splitlines() if ln.strip()]

    sess = session_with_policy(cfg)
    parser = choose_parser()

    # Prepare headers
    scalar_fields = list(cfg.get("fields", {}).keys())
    list_cfg = cfg.get("lists", {})
    # expand list columns
    list_columns: List[Tuple[str, int, str]] = []  # (logical_name, max_columns, prefix)
    for name, spec in list_cfg.items():
        list_columns.append((name, int(spec.get("max_columns", 5)), spec.get("column_prefix", f"{name}_")))

    headers = scalar_fields + [f"{prefix}{i}" for (name, n, prefix) in list_columns for i in range(1, n+1)]

    out_csv = Path(cfg["output_csv"])
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        got_names = 0
        for i, url in enumerate(links, 1):
            print(f"[info] ({i}/{len(links)}) GET {url}")
            html = polite_get(sess, url, cfg)
            if html is None:
                writer.writerow({h: "" for h in headers})
                continue
            soup = BeautifulSoup(html, parser)

            row: Dict[str, str] = {}
            for field_name, field_spec in cfg.get("fields", {}).items():
                try:
                    row[field_name] = extract_scalar(field_spec, soup, html)
                except Exception as e:
                    print(f"[warn] field '{field_name}' failed for {url}: {e}")
                    row[field_name] = field_spec.get("default", "")

            for (lname, ncols, prefix) in list_columns:
                vals = []
                try:
                    vals = extract_list(cfg["lists"][lname], soup)
                except Exception as e:
                    print(f"[warn] list '{lname}' failed for {url}: {e}")
                    vals = []
                # fan out
                for idx in range(1, ncols+1):
                    row[f"{prefix}{idx}"] = vals[idx-1] if idx-1 < len(vals) else ""

            if row.get("name"): got_names += 1
            writer.writerow(row)
            sleep_politely(cfg)

        print(f"[result] Wrote {len(links)} rows to {out_csv} (name present {got_names}/{len(links)})")

if __name__ == "__main__":
    main()
