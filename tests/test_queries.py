# Tests for sql/003_queries.sql: measurement_as_of() and refresh_lifecycle()
import pytest
from src import config, load
from tests import make_fixture

def _rows(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# measurement_as_of: the same inspection, seen from two report years
def test_as_of_returns_value_known_at_each_report_year(conn, tmp_path):
    make_fixture.build(n_bridges=60, out_dir=tmp_path, seed=11)
    for year in make_fixture.YEARS:
        load.load_year(conn, tmp_path / str(year) / f"{config.STATE}{year % 100:02d}.txt",
                       year, config.STATE)

    corrections = _rows(conn, """
        SELECT asset_id, observed_at, component, old_value, old_reported_year,
               new_value, new_reported_year
        FROM v_corrections
    """)
    assert corrections, "fixture should contain corrections"

    for asset, observed, comp, old_v, old_y, new_v, new_y in corrections:
        q = """SELECT value_numeric FROM measurement_as_of(%s)
               WHERE asset_id = %s AND observed_at = %s AND component = %s"""
        assert _rows(conn, q, (old_y, asset, observed, comp)) == [(old_v,)]
        assert _rows(conn, q, (new_y, asset, observed, comp)) == [(new_v,)]
        # before the inspection was ever reported, it is unknown
        assert _rows(conn, q, (old_y - 3, asset, observed, comp)) == []


# refresh_lifecycle: hand-built bridges with known right answers
BRIDGES = {
    # name: (year_built, year_reconstructed, [(year, superstructure rating), ...])
    "FAILS":     (1950, None, [(1992, 6), (1994, 5), (1996, 4), (1998, 6)]),
    "CENSORED":  (1980, None, [(1992, 7), (1994, 7), (1996, 6)]),
    "PREVALENT": (1940, None, [(1992, 3), (1994, 3)]),
    "REBUILT":   (1960, 1995, [(1992, 6), (1994, 6), (1996, 3)]),
    "ONE_LOOK":  (1970, None, [(1992, 7)]),
    "OLD_REBUILD": (1930, 1985, [(1992, 7), (1994, 4)]),
}


@pytest.fixture
def handmade(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ingest_run (source_file, state_code, data_year, spec_name, data_lines, rows_read)
            VALUES ('handmade', 'XX', 1992, 'CODING_GUIDE_1995', 0, 0) RETURNING run_id
        """)
        run_id = cur.fetchone()[0]
        cur.execute("""SELECT method_id FROM method
                       WHERE spec_name = 'CODING_GUIDE_1995' AND component = 'SUPERSTRUCTURE'""")
        method_id = cur.fetchone()[0]
        for name, (built, rebuilt, obs) in BRIDGES.items():
            cur.execute("""
                INSERT INTO asset (asset_id, state_code, structure_number, year_built,
                                   year_reconstructed, first_seen_year, last_seen_year)
                VALUES (%s, 'XX', %s, %s, %s, 1992, 1998)
            """, (name, name, built, rebuilt))
            for year, rating in obs:
                cur.execute("""
                    INSERT INTO observation_event (asset_id, observed_at, first_reported_year)
                    VALUES (%s, make_date(%s, 6, 1), %s) RETURNING event_id
                """, (name, year, year))
                event_id = cur.fetchone()[0]
                cur.execute("""
                    INSERT INTO measurement (event_id, method_id, value_numeric, reported_year, run_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (event_id, method_id, rating, year, run_id))
        cur.execute("SELECT refresh_lifecycle(4)")
    conn.commit()
    rows = _rows(conn, """
        SELECT asset_id, origin_year, entry_age, duration_years, event_observed, excluded_reason
        FROM lifecycle WHERE component = 'SUPERSTRUCTURE'
    """)
    return {r[0]: r[1:] for r in rows}

# built 1950, entered 1992 at 42, first rated 4 in 1996 at 46.
# The later 6 (a repair) does not undo the failure.
def test_failure_is_first_inspection_at_threshold(handmade):
    assert handmade["FAILS"] == (1950, 42, 46, True, None)


def test_never_failing_bridge_is_right_censored_at_last_inspection(handmade):
    assert handmade["CENSORED"] == (1980, 12, 16, False, None)


def test_bridge_already_failed_when_first_seen_is_excluded_not_dropped(handmade):
    assert handmade["PREVALENT"][-1] == "at threshold when first seen"

# rebuilt 1995: the 1996 rating of 3 belongs to the NEW superstructure.
# The original was last seen in 1994, above threshold -> censored at 34.
def test_rebuild_during_window_censors_the_original_component(handmade):
    assert handmade["REBUILT"] == (1960, 32, 34, False, None)


def test_single_inspection_has_no_follow_up(handmade):
    assert handmade["ONE_LOOK"][-1] == "no follow-up"


def test_rebuild_before_observation_restarts_the_clock(handmade):
    # rebuilt 1985, before the 1992 entry: age counts from 1985.
    assert handmade["OLD_REBUILD"] == (1985, 7, 9, True, None)


def test_every_asset_component_gets_a_row(handmade):
    assert set(handmade) == set(BRIDGES)
