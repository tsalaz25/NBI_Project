# Parse 1yr from  NBI Delmited File
# Details this File Handles
#
#1. Header Names can Drift... Cols are resolved by NBI ITEM NUMBER suffix 
#   (DECK_COND_058 -> item '058').
#   Expected Cols that are absent recorded as Drift
#
#2. Item 90 (Inspection_Date) is MMYY in the delimited files: 
#   Feb-22 is '222' 
#   Treating only 4-digit values as valid would discard inspection
#   from January through September.
#
#3. Text is wrapped in Single Quotes ('xxx')... Some Loaction fields use
#   an apostrophe as a Foot Mark (ex. '500' E OF WASHINGTION AVE') 
#   A strict CSV reader decides the field ends after 500, looks for the next
#   quote on the FOLLOWING line... so it  merges 2 rows
#   (ex. 2009: 44 rows lost, none reported). 
#    pandas' default C reader treats the stray apostrophe as a literal, which keeps every row.
#    Loss is measured directly: non-blank lines in the file minus rows parsed.
#
#4. Before 2010, files also contain records for roads passing UNDER a
#   bridge (ex. Item 5A = 2 or A-Z). They repeat the bridge's structure
#   number but are not bridges. Only item 5A = '1' is kept; the rest
#   are counted in rows_route_under.
#
# Nothing is dropped silently...every discarded row is counted in one of
# rows_malformed / rows_route_under / rows_rejected / rows_undated.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
import pandas as pd
from src import config


@dataclass
class ParseResult:
    frame: pd.DataFrame          # 1-Row/ Bridge, with 'observed_at'
    data_lines: int              # non-blank lines, minus header
    rows_read: int               # rows the CSV reader produced
    rows_malformed: int          # data_lines - rows_read
    rows_route_under: int        # Item 5A != '1'
    rows_rejected: int           # no structure number, or duplicate bridge
    rows_undated: int            # no usable inspection date
    columns_missing: list[str] = field(default_factory=list)
    resolved: dict[str, str] = field(default_factory=dict)

_ITEM_SUFFIX = re.compile(r"_(\d{3}[A-Z]?)$")

# Map NBI Item # -> Column Name 
def index_headers(columns) -> dict[str, str]:
    out: dict[str, str] = {}
    for col in columns:
        m = _ITEM_SUFFIX.search(str(col).strip().upper())
        if m:
            out.setdefault(m.group(1), col)
    return out

#Strip Whitespace, Stray Quotes, blanks become NA
def _clean(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().str.strip("'").str.strip()
    return s.mask(s == "")

#Condition ratings:  0-9, carry 'N' (not applicable)
def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(_clean(series), errors="coerce")


# Item 90 -> first-of-month date, or NaT. Accepts 'MMYY' or 'MYY'
# Two-digit years above 60 are 19xx, otherwise 20xx
# A date later than the report year, or before 1960, is treated as invalid
# Plain object/float dtypes: pandas' nullable types raise on NA inside .where()... blanks are expected here
def parse_inspection_date(series: pd.Series, year: int) -> pd.Series:
    s = _clean(series).astype(object).fillna("").astype(str)
    s = s.str.replace(r"\D", "", regex=True)
    s = s.where(s.str.len().isin([3, 4]), "").str.zfill(4)
    mm = pd.to_numeric(s.str[:2], errors="coerce").astype("float64")
    yy = pd.to_numeric(s.str[2:], errors="coerce").astype("float64")
    yyyy = yy.where(yy > 60, yy + 100) + 1900
    ok = (mm.between(1, 12) & yyyy.between(1960, year)).fillna(False)
    return pd.to_datetime(
        pd.DataFrame({"year": yyyy.where(ok), "month": mm.where(ok), "day": 1}),
        errors="coerce",
    )

# Non-blank lines after the header... row count
def count_data_lines(path: Path) -> int:
    with open(path, encoding="latin-1") as fh:
        next(fh, None)
        return sum(1 for line in fh if line.strip())

# Default C reader: lenient about stray apostrophes (3)
# Lines with too many fields are skipped, and show up as data_lines - rows_read
def parse_file(path: Path, year: int, state: str) -> ParseResult:
    data_lines = count_data_lines(path)
    df = pd.read_csv(
        path,
        sep=",",
        quotechar="'",
        dtype=str,
        keep_default_na=False,
        encoding="latin-1",
        on_bad_lines="skip",
    )
    df.columns = [str(c).strip() for c in df.columns]
    rows_read = len(df)
    by_item = index_headers(df.columns)

    missing: list[str] = []
    resolved: dict[str, str] = {}
    out = pd.DataFrame(index=df.index)

    for item, target in config.INVENTORY_ITEMS.items():
        col = by_item.get(item)
        if col is None:
            missing.append(f"{target}({item})")
            out[target] = pd.NA
        else:
            resolved[target] = col
            out[target] = _clean(df[col])

    for item, component in config.CONDITION_ITEMS.items():
        col = by_item.get(item)
        key = f"cond_{component.lower()}"
        if col is None:
            missing.append(f"{component}({item})")
            out[key] = pd.NA
        else:
            resolved[key] = col
            out[key] = _to_num(df[col])

    # Keep Bridges only (4)
    route_under = 0
    if "record_type" in resolved:
        is_bridge = out["record_type"] == "1"
        route_under = int((~is_bridge.fillna(False)).sum())
        out = out[is_bridge.fillna(False)].copy()

    # Reject unkeaybale Rows
    before = len(out)
    out = out[out["structure_number"].notna()].copy()
    out["asset_id"] = state.upper() + "-" + out["structure_number"].astype(str)
    out = out.drop_duplicates(subset=["asset_id"], keep="first")
    rejected = before - len(out)

    # Numeric Coercions
    for c in ("year_built", "year_reconstructed", "main_unit_spans",
              "inspect_freq_months", "structure_length_m"):
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # Item 106 uses 0 for "never reconstructed"
    out.loc[out["year_reconstructed"] == 0, "year_reconstructed"] = pd.NA

    # Inspection Date
    out["observed_at"] = parse_inspection_date(out["inspection_date"], year)
    undated = int(out["observed_at"].isna().sum())

    out["age_years"] = out["observed_at"].dt.year - out["year_built"]
    out.loc[out["age_years"] < 0, "age_years"] = pd.NA

    out["data_year"] = year
    out["spec_name"] = config.spec_for_year(year)

    return ParseResult(
        frame=out.reset_index(drop=True),
        data_lines=data_lines,
        rows_read=rows_read,
        rows_malformed=max(data_lines - rows_read, 0),
        rows_route_under=route_under,
        rows_rejected=int(rejected),
        rows_undated=undated,
        columns_missing=missing,
        resolved=resolved,
    )
