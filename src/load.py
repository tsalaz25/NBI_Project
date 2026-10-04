# Load Parsed NBI years into Postgres.
#
# Per Year, in ONE transaction:
#
#   1. Open 'ingest_run' Row                 Provenance... Transaction Time
#   2. Upsert Assets                         Unit
#   3. COPY Year to Temp Staging Tables
#   4. Insert New Inspections                observation_event... Valid Time
#   5. Link Inspections to report            event_report
#   6. Insert Measurements:
#       - No Current Val              -> New Row
#       - Same Val as Current         -> Nothing (Report Repeats It)
#       - Diff Val                    -> New Row that supersedes Old
#   7. Close Run with Row Vounts             Failure Detection
#
# Re-running is safe: a Year that already has an 'ingest_run' row is skipped. 
# Years must load in order
#
# Usage:
#   python -m src.load              # every year found in data/raw
#   python -m src.load --year 2024

from __future__ import annotations
import argparse
import io
import sys
from pathlib import Path
import pandas as pd
from psycopg2.extras import execute_values
from src import config, db, parse

# COPY Rows to a Table. None -> NULL
def _copy(cur, table: str, columns: list[str], rows) -> int:
    buf = io.StringIO()
    n = 0
    for row in rows:
        buf.write("\t".join(r"\N" if v is None else str(v) for v in row))
        buf.write("\n")
        n += 1
    buf.seek(0)
    cur.copy_expert(
        f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT text)", buf
    )
    return n

def _int(v):
    return None if v is None or pd.isna(v) else int(v)

def _float(v):
    return None if v is None or pd.isna(v) else float(v)

def _str(v):
    if v is None or pd.isna(v):
        return None
    s = str(v).strip()
    return s or None

def already_loaded(cur, state: str, year: int) -> bool:
    cur.execute(
        "SELECT 1 FROM ingest_run WHERE state_code = %s AND data_year = %s",
        (state, year),
    )
    return cur.fetchone() is not None


def latest_loaded_year(cur, state: str) -> int | None:
    cur.execute("SELECT max(data_year) FROM ingest_run WHERE state_code = %s", (state,))
    return cur.fetchone()[0]

def load_year(conn, path: Path, year: int, state: str) -> dict | None:
    state = state.upper()
    print(f"[{year}] {path.name}")

    with conn.cursor() as cur:
        if already_loaded(cur, state, year):
            print("  skip    already loaded (run `python -m src.setup_db` to reset)")
            return None
        latest = latest_loaded_year(cur, state)
        if latest is not None and year < latest:
            raise SystemExit(
                f"Refusing to load {year} after {latest} is already loaded: "
                f"corrections are ordered by report year. Reset the schema "
                f"(python -m src.setup_db) and load all years in order."
            )

    res = parse.parse_file(path, year, state)
    df = res.frame
    print(f"  parsed  {res.data_lines:,} lines -> {res.rows_read:,} rows | "
          f"{res.rows_malformed} malformed | {res.rows_route_under} route-under | "
          f"{res.rows_rejected} rejected | {res.rows_undated} undated")
    if res.columns_missing:
        print(f"  DRIFT   missing items: {', '.join(res.columns_missing)}")
    if df.empty:
        print("  !! nothing to load")
        return None

    spec = config.spec_for_year(year)
    stats: dict[str, int] = {}

    try:
        with conn.cursor() as cur:
            # Provenance Row
            cur.execute(
                """
                INSERT INTO ingest_run
                    (source_file, state_code, data_year, spec_name, data_lines,
                     rows_read, rows_malformed, rows_route_under, rows_rejected,
                     rows_undated, columns_missing)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING run_id
                """,
                (path.name, state, year, spec, res.data_lines, res.rows_read,
                 res.rows_malformed, res.rows_route_under, res.rows_rejected,
                 res.rows_undated, res.columns_missing or None),
            )
            run_id = cur.fetchone()[0]

            # Assets 
            asset_rows = [
                (r.asset_id, state, str(r.structure_number),
                 _int(r.year_built), _int(r.year_reconstructed),
                 _str(r.owner_code), _str(r.structure_kind), _str(r.structure_type),
                 _int(r.main_unit_spans), _float(r.structure_length_m), year, year)
                for r in df.itertuples()
            ]
            execute_values(
                cur,
                """
                INSERT INTO asset
                  (asset_id, state_code, structure_number, year_built,
                   year_reconstructed, owner_code, structure_kind, structure_type,
                   main_unit_spans, structure_length_m, first_seen_year, last_seen_year)
                VALUES %s
                ON CONFLICT (asset_id) DO UPDATE SET
                  year_built         = COALESCE(asset.year_built, EXCLUDED.year_built),
                  year_reconstructed = COALESCE(EXCLUDED.year_reconstructed, asset.year_reconstructed),
                  structure_kind     = COALESCE(asset.structure_kind, EXCLUDED.structure_kind),
                  structure_type     = COALESCE(asset.structure_type, EXCLUDED.structure_type),
                  first_seen_year    = LEAST(asset.first_seen_year, EXCLUDED.first_seen_year),
                  last_seen_year     = GREATEST(asset.last_seen_year, EXCLUDED.last_seen_year)
                """,
                asset_rows, page_size=5000,
            )
            stats["assets_upserted"] = len(asset_rows)

            # Staging
            dated = df[df["observed_at"].notna()]
            cur.execute("""
                CREATE TEMP TABLE stage_event (
                    asset_id text, observed_at date,
                    inspect_freq_months int, age_years int
                ) ON COMMIT DROP;
                CREATE TEMP TABLE stage_meas (
                    asset_id text, observed_at date,
                    component text, value numeric
                ) ON COMMIT DROP;
            """)
            _copy(cur, "stage_event",
                  ["asset_id", "observed_at", "inspect_freq_months", "age_years"],
                  ((r.asset_id, r.observed_at.date(), _int(r.inspect_freq_months),
                    _int(r.age_years)) for r in dated.itertuples()))

            def meas_rows():
                for r in dated.itertuples():
                    for component in config.CONDITION_ITEMS.values():
                        v = getattr(r, f"cond_{component.lower()}")
                        if v is not None and not pd.isna(v):
                            yield (r.asset_id, r.observed_at.date(), component, v)

            staged = _copy(cur, "stage_meas",
                           ["asset_id", "observed_at", "component", "value"],
                           meas_rows())
            
            # Temp Tables filled by COPY have no statistics until analyzed. Without,The Planner Guesses
            cur.execute("ANALYZE stage_event; ANALYZE stage_meas;")

            # New Inspections
            cur.execute(
                """
                INSERT INTO observation_event
                    (asset_id, observed_at, inspect_freq_months, age_years, first_reported_year)
                SELECT asset_id, observed_at, inspect_freq_months, age_years, %s
                FROM stage_event
                ON CONFLICT (asset_id, observed_at) DO NOTHING
                """,
                (year,),
            )
            stats["events_new"] = cur.rowcount

            # Carried Inspections
            cur.execute(
                """
                INSERT INTO event_report (event_id, run_id, data_year)
                SELECT e.event_id, %s, %s
                FROM stage_event s
                JOIN observation_event e
                  ON e.asset_id = s.asset_id AND e.observed_at = s.observed_at
                """,
                (run_id, year),
            )
            stats["events_rereported"] = cur.rowcount - stats["events_new"]

            # Measurements: New / Unchanged / Corrected
            # LEFT JOIN LATERAL: Each Incoming Val -> 1 Index lookup of the Current Val of that (inspection, method) chain
            # An earlier version joined against a "head" subquery instead; with no statistics on the staging tables the planner chose a
            #   nested loop that re-ran the subquery per row (12.5M index probes for 3.5k rows, 20 s per year, growing every year)
            # See docs/performance.md
            cur.execute(
                """
                INSERT INTO measurement
                    (event_id, method_id, value_numeric, supersedes, reported_year, run_id)
                SELECT e.event_id, m.method_id, s.value, cur_val.measurement_id,
                       %(year)s, %(run)s
                FROM stage_meas s
                JOIN observation_event e
                  ON e.asset_id = s.asset_id AND e.observed_at = s.observed_at
                JOIN method m
                  ON m.component = s.component AND m.spec_name = %(spec)s
                LEFT JOIN LATERAL (
                    SELECT x.measurement_id, x.value_numeric
                    FROM measurement x
                    WHERE x.event_id  = e.event_id
                      AND x.method_id = m.method_id
                      AND NOT EXISTS (
                          SELECT 1 FROM measurement newer
                          WHERE newer.supersedes = x.measurement_id
                      )
                ) cur_val ON true
                WHERE cur_val.measurement_id IS NULL
                   OR cur_val.value_numeric IS DISTINCT FROM s.value
                RETURNING supersedes
                """,
                {"spec": spec, "year": year, "run": run_id},
            )
            inserted = [row[0] for row in cur.fetchall()]
            stats["measures_new"] = sum(1 for s in inserted if s is None)
            stats["measures_corrected"] = sum(1 for s in inserted if s is not None)
            stats["measures_unchanged"] = staged - len(inserted)

            # Close Run
            cur.execute(
                """
                UPDATE ingest_run SET
                    assets_upserted = %(assets_upserted)s,
                    events_new = %(events_new)s,
                    events_rereported = %(events_rereported)s,
                    measures_new = %(measures_new)s,
                    measures_corrected = %(measures_corrected)s,
                    measures_unchanged = %(measures_unchanged)s,
                    finished_at = now()
                WHERE run_id = %(run_id)s
                """,
                {**stats, "run_id": run_id},
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    print(f"  loaded  {stats['assets_upserted']:,} assets | "
          f"events {stats['events_new']:,} new, {stats['events_rereported']:,} re-reported | "
          f"measurements {stats['measures_new']:,} new, "
          f"{stats['measures_corrected']:,} corrected, "
          f"{stats['measures_unchanged']:,} unchanged")
    return stats


def find_files(state: str, year: int | None = None) -> list[tuple[int, Path]]:
    files: list[tuple[int, Path]] = []
    for year_dir in sorted(config.RAW_DIR.glob("[0-9][0-9][0-9][0-9]")):
        y = int(year_dir.name)
        if year is not None and y != year:
            continue
        for f in sorted(year_dir.glob(f"{state.upper()}*.txt")):
            files.append((y, f))
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int)
    ap.add_argument("--state", default=config.STATE)
    args = ap.parse_args(argv)

    files = find_files(args.state, args.year)
    if not files:
        print(f"No files found under {config.RAW_DIR}.\n"
              f"Run  python -m src.download  first, or\n"
              f"     python -m tests.make_fixture  for synthetic test data.")
        return 1

    conn = db.connect()
    try:
        for year, path in files:
            load_year(conn, path, year, args.state)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
