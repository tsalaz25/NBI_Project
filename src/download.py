# Download  NM's NBI File from 1992-2025
#
# FHWA's site Structure
#   ascii{YEAR}.cfm
#     -> Delimited Link: disclaim.cfm?nbiYear={YEAR}/delimited&nbiState={ST}{YY}
#       -> "Proceed to Data" link: {YEAR}/delimited/{ST}{YY}.txt
#
# The links go through a disclaimer page...so we follow them
# If a year has no per-state Dlim Link, Use the "all states, individual files, delimited" zip and extract our NM.

# Usage:
#    python -m src.download                 every configured year
#    python -m src.download --year 2024     one year
#    python -m src.download --list 2024     show the links found, download nothing

from __future__ import annotations
import argparse
import html
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin
import requests
from src import config

HEADERS = {"User-Agent": "nbi-surveillance-analogue/0.2 (academic project)"}
HREF_RE = re.compile(r'href\s*=\s*"([^"]+)"', re.IGNORECASE)


# Find File Functions

# De-Duplicate Every href on the page  and Make absolute
def extract_links(page_html: str, base_url: str) -> list[str]:
    seen, out = set(), []
    for raw in HREF_RE.findall(page_html):
        url = urljoin(base_url, html.unescape(raw).strip())
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out

 # disclaim.cfm?nbiYear=YYYY/delimited&nbiState=STYY
def find_state_delimited_link(links: list[str], year: int, state: str) -> str | None:
    target = f"nbistate={state.lower()}{year % 100:02d}"
    for u in links:
        lu = u.lower()
        if "disclaim" in lu and "delimited" in lu and target in lu:
            return u
    return None

# disclaim.cfm?nbiYear=YYYYdel&nbiZip=zip Individual State Files
def find_all_states_delimited_zip(links: list[str], year: int) -> str | None:
    target = f"nbiyear={year}del&"
    for u in links:
        if target in u.lower() and "nbizip=zip" in u.lower():
            return u
    return None

# On Disclaimer page use 'Proceed to Data' Link 
def find_data_link(links: list[str]) -> str | None:
    for u in links:
        path = u.lower().split("?", 1)[0]
        if path.endswith((".txt", ".zip")) and "/bridge/nbi/" in u.lower():
            return u
    return None


# Networking Functions
def _get(url: str, **kw) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=kw.pop("timeout", 60), **kw)
    r.raise_for_status()
    return r

def _follow_disclaimer(disclaim_url: str) -> str:
    links = extract_links(_get(disclaim_url).text, disclaim_url)
    data = find_data_link(links)
    if not data:
        raise RuntimeError(f"no data link on disclaimer page {disclaim_url}")
    return data

def _save(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with _get(url, timeout=300, stream=True) as r, open(dest, "wb") as fh:
        for chunk in r.iter_content(chunk_size=1 << 20):
            fh.write(chunk)
    print(f"  saved   {dest.relative_to(config.ROOT)} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest

def _extract_state_from_zip(zip_path: Path, state: str, dest: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        members = [n for n in zf.namelist()
                   if Path(n).name.upper().startswith(state.upper())]
        if not members:
            raise RuntimeError(f"{state} not found in {zip_path.name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(members[0]))
    print(f"  extract {members[0]} -> {dest.relative_to(config.ROOT)}")
    return dest

def download_year(year: int, state: str) -> Path | None:
    dest = config.RAW_DIR / str(year) / f"{state.upper()}{year % 100:02d}.txt"
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached  {dest.relative_to(config.ROOT)}")
        return dest

    page_url = config.NBI_PAGE.format(year=year)
    links = extract_links(_get(page_url).text, page_url)

    per_state = find_state_delimited_link(links, year, state)
    if per_state:
        return _save(_follow_disclaimer(per_state), dest)

    all_zip = find_all_states_delimited_zip(links, year)
    if all_zip:
        print("  note    no per-state link; using the all-states zip")
        zpath = config.RAW_DIR / "_zips" / f"nbi{year}del.zip"
        if not zpath.exists():
            _save(_follow_disclaimer(all_zip), zpath)
        return _extract_state_from_zip(zpath, state, dest)

    print("  !! no delimited download found on this year's page")
    return None

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int)
    ap.add_argument("--list", type=int, metavar="YEAR")
    ap.add_argument("--state", default=config.STATE)
    args = ap.parse_args(argv)

    if args.list:
        url = config.NBI_PAGE.format(year=args.list)
        links = extract_links(_get(url).text, url)
        print("per-state delimited:", find_state_delimited_link(links, args.list, args.state))
        print("all-states zip     :", find_all_states_delimited_zip(links, args.list))
        return 0

    failures = []
    for year in ([args.year] if args.year else config.YEARS):
        print(f"[{year}]")
        try:
            if download_year(year, args.state) is None:
                failures.append(year)
        except Exception as exc:  # keep going; report at the end
            print(f"  !! {exc}")
            failures.append(year)
        time.sleep(1)  # be polite to a .gov host

    if failures:
        print(f"\nFailed years: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
