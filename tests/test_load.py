# Loader Tests against  Postgres  DB, Skipped automatically if Postgres is not running

import psycopg2
import pytest
from src import config, load
from tests import make_fixture

def _count(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]

def _load_all(conn, raw_dir):
    for year in make_fixture.YEARS:
        path = raw_dir / str(year) / f"{config.STATE}{year % 100:02d}.txt"
        load.load_year(conn, path, year, config.STATE)

@pytest.fixture
def fixture_dir(tmp_path):
    injected = make_fixture.build(n_bridges=60, out_dir=tmp_path, seed=11)
    return tmp_path, injected

def test_loader_finds_exactly_the_injected_corrections(conn, fixture_dir):
    raw, injected = fixture_dir
    _load_all(conn, raw)
    assert _count(conn, "SELECT count(*) FROM v_corrections") == injected

def test_reloading_changes_nothing(conn, fixture_dir):
    raw, _ = fixture_dir
    _load_all(conn, raw)
    before = _count(conn, "SELECT count(*) FROM measurement")
    _load_all(conn, raw)
    assert _count(conn, "SELECT count(*) FROM measurement") == before

def test_one_current_value_per_inspection_and_method(conn, fixture_dir):
    raw, _ = fixture_dir
    _load_all(conn, raw)
    current = _count(conn, "SELECT count(*) FROM v_current_measurement")
    distinct = _count(conn, "SELECT count(DISTINCT (event_id, method_id)) FROM measurement")
    assert current == distinct

def test_measurements_cannot_be_updated_or_deleted(conn, fixture_dir):
    raw, _ = fixture_dir
    load.load_year(conn, raw / "1992" / f"{config.STATE}92.txt", 1992, config.STATE)
    for stmt in ("UPDATE measurement SET value_numeric = 0",
                 "DELETE FROM measurement"):
        with pytest.raises(psycopg2.errors.RaiseException):
            with conn.cursor() as cur:
                cur.execute(stmt)
        conn.rollback()

def test_years_must_load_in_order(conn, fixture_dir):
    raw, _ = fixture_dir
    load.load_year(conn, raw / "2000" / f"{config.STATE}00.txt", 2000, config.STATE)
    with pytest.raises(SystemExit):
        load.load_year(conn, raw / "1999" / f"{config.STATE}99.txt", 1999, config.STATE)

def test_undated_and_malformed_rows_are_recorded(conn, fixture_dir):
    raw, _ = fixture_dir
    _load_all(conn, raw)
    assert _count(conn, "SELECT rows_undated FROM ingest_run WHERE data_year = 2010") == 1
    assert _count(conn, "SELECT rows_malformed FROM ingest_run WHERE data_year = 2003") == 1

    # every line in every file is accounted for

    assert _count(conn, """
        SELECT count(*) FROM ingest_run
        WHERE data_lines <> rows_read + rows_malformed
    """) == 0


def test_route_under_records_counted_and_never_loaded(conn, fixture_dir):
    raw, _ = fixture_dir
    _load_all(conn, raw)
    assert _count(conn, "SELECT sum(rows_route_under) FROM ingest_run WHERE data_year < 2010") > 0
    assert _count(conn, "SELECT sum(rows_route_under) FROM ingest_run WHERE data_year >= 2010") == 0
    assert _count(conn, "SELECT sum(rows_rejected) FROM ingest_run") == 0


def test_spec_for_year_agrees_with_method_table(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT spec_name, valid_from, valid_to FROM method")
        rows = cur.fetchall()
    for year in range(1992, 2031):
        submitted = __import__("datetime").date(year, 3, 15)
        specs = {s for s, start, end in rows
                 if start <= submitted and (end is None or submitted <= end)}
        assert specs == {config.spec_for_year(year)}, year
