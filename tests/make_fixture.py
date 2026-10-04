# Generate synthetic NBI Files so the pipeline can be verified without downloading anything. Headers match the real delimited files.
#
# Reproduces properties observed in 2020 New Mexico file:
#  - Inspections run on 12- or 24-month cycle, but a file is published every year,Same Inspection appears in consecutive Files
#  - Item 90 dates have no leading zero ('222' = Feb-22)
#  - Structure # are left-padded with spaces
#  - Culverts Rate Items 58/59/60 as 'N' and Rate Item 62 instead
#
# Before 2010, extra records for roads passing UNDER a bridge  repeat the bridge's structure number
#  - Here they are written BEFORE the Bridge Row, same keep-the-first-duplicate logic
#    would pick the wrong record
#  - Location text uses an apostrophe as a Foot Mark, inside a field
#    that is itself wrapped in apostrophes(ex. '500' E OF MAIN ST')
# 
# Other Things the Loader must Handle
#  - About 1% of re-reported inspections carry a CHANGED rating (a correction)
#  - Item 106 is absent before 1998 (SYNTHETIC drift, for the drift check)
#  - 1 malformed line, 1 undated row
#
# Usage:  python -m tests.make_fixture [--bridges 300]

from __future__ import annotations
import argparse
import numpy as np
import pandas as pd
from src import config
YEARS = list(range(1992, 2026))


def _mmyy(year: int, month: int) -> str:
    return f"{month}{year % 100:02d}"          # no leading zero


def build(n_bridges: int = 300, out_dir=None, seed: int = 7) -> int:
    rng = np.random.default_rng(seed)
    out_dir = out_dir or config.RAW_DIR

    built = rng.integers(1920, 2012, n_bridges)
    kind = rng.choice(["1", "2", "3", "5"], n_bridges)
    is_culvert = rng.random(n_bridges) < 0.15
    typ = np.where(is_culvert, "19", rng.choice(["02", "04", "05"], n_bridges))
    freq = np.where(rng.random(n_bridges) < 0.1, 12, 24)
    start = 8.3 + rng.normal(0, 0.3, n_bridges)
    rate = rng.uniform(0.02, 0.09, n_bridges)
    spans = rng.integers(1, 6, n_bridges)
    length = np.round(rng.uniform(8, 200, n_bridges), 1)
    struct_no = [f"{i:>15}" for i in range(1000, 1000 + n_bridges)]   # Padded

    # Every Incpection each Bridge gets, with its ratings
    inspections: list[list[tuple]] = []
    for b in range(n_bridges):
        m = int(rng.integers(1, 13))
        y = int(max(built[b], 1989))
        rows = []
        while (y, m) <= (2025, 2):
            age = max(y - built[b], 0)
            base = np.clip(start[b] - rate[b] * age + rng.normal(0, 0.25), 2, 9)
            r = [int(np.clip(round(base + rng.normal(0, 0.35)), 2, 9)) for _ in range(4)]
            rows.append((y, m, r))
            m += int(freq[b])
            y += (m - 1) // 12
            m = (m - 1) % 12 + 1
        inspections.append(rows)

    corrections = 0
    last_reported: dict[int, tuple] = {}   # Bridge -> Inspection
    for year in YEARS:
        rows, row_bridge = [], []
        for b in range(n_bridges):
            if built[b] > year:
                continue

            # Latest Inspection on or before February of the Report Year
            known = [i for i in inspections[b] if (i[0], i[1]) <= (year, 2)]
            if not known:
                continue
            iy, im, (deck, sup, sub, culv) = known[-1]

            # A Re-Repor, Occasionally Changes. Culverts change Item 62, Item 58
            rereport = last_reported.get(b) == (iy, im)
            last_reported[b] = (iy, im)
            if rereport and rng.random() < 0.01:
                delta = int(rng.choice([-1, 1]))

                # Never let Clipping turn a "correction" to "No Change" at the top, step down instead
                if is_culvert[b]:
                    culv = culv + delta if 0 <= culv + delta <= 9 else culv - delta
                else:
                    deck = deck + delta if 0 <= deck + delta <= 9 else deck - delta
                corrections += 1
            if year < 2010 and b % 15 == 0:        # Route-Under Record 1st
                rows.append({
                    "STATE_CODE_001": "35",
                    "STRUCTURE_NUMBER_008": struct_no[b],
                    "RECORD_TYPE_005A": "2",
                    "LOCATION_009": "'UNDER ROUTE'",
                    "YEAR_BUILT_027": int(built[b]),
                    "DECK_COND_058": 1, "SUPERSTRUCTURE_COND_059": 1,
                    "SUBSTRUCTURE_COND_060": 1, "CULVERT_COND_062": "N",
                    "DATE_OF_INSPECT_090": "",
                })
                row_bridge.append(b)
            location = f"'{b}00' E OF MAIN ST'" if b % 20 == 0 else f"'NEAR MP {b}'"
            row = {
                "STATE_CODE_001": "35",
                "STRUCTURE_NUMBER_008": struct_no[b],
                "RECORD_TYPE_005A": "1",
                "LOCATION_009": location,
                "OWNER_022": "01",
                "YEAR_BUILT_027": int(built[b]),
                "STRUCTURE_KIND_043A": kind[b],
                "STRUCTURE_TYPE_043B": typ[b],
                "MAIN_UNIT_SPANS_045": int(spans[b]),
                "STRUCTURE_LEN_MT_049": float(length[b]),
                "DECK_COND_058": "N" if is_culvert[b] else deck,
                "SUPERSTRUCTURE_COND_059": "N" if is_culvert[b] else sup,
                "SUBSTRUCTURE_COND_060": "N" if is_culvert[b] else sub,
                "CULVERT_COND_062": culv if is_culvert[b] else "N",
                "DATE_OF_INSPECT_090": _mmyy(iy, im),
                "INSPECT_FREQ_MONTHS_091": int(freq[b]),
            }
            if year >= 1998:                       # SYNTHETIC drift
                row["YEAR_RECONSTRUCTED_106"] = 0
            rows.append(row)
            row_bridge.append(b)

        df = pd.DataFrame(rows)
        if year == 2010:
            df.loc[0, "DATE_OF_INSPECT_090"] = ""   # Undated Row, Not Reported
            last_reported.pop(row_bridge[0], None)  

        path = out_dir / str(year) / f"{config.STATE}{year % 100:02d}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Location Vals carry their own apostrophes, like real files...write them raw (the '"' quotechar is never used)

        df.to_csv(path, index=False, quotechar='"')
        if year == 2003:                           # malformed line
            with open(path, "a", encoding="latin-1") as fh:
                fh.write("35,BROKEN,ROW," + ",".join(["x"] * 20) + "\n")

    print(f"wrote {len(YEARS)} synthetic years x {n_bridges} bridges to {out_dir}")
    print(f"injected {corrections} rating corrections on re-reported inspections")
    return corrections


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridges", type=int, default=300)
    build(ap.parse_args().bridges)
