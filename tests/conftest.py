# Shared test setup
# Database Tests Run against a SEPARATE DB (nbi_test by default) o running the suite never touches laded data
# This must run before anything imports src.config, lives at the top of conftest.py.

import os
os.environ["PGDATABASE"] = os.environ.get("NBI_TEST_DATABASE", "nbi_test")
import psycopg2             # noqa: E402
import pytest               # noqa: E402
from src import config, db  # noqa: E402


def _ensure_test_database() -> None:
    settings = config.db_settings("postgres")
    conn = psycopg2.connect(**settings)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                    (os.environ["PGDATABASE"],))
        if cur.fetchone() is None:
            cur.execute(f'CREATE DATABASE "{os.environ["PGDATABASE"]}"')
    conn.close()


@pytest.fixture
def conn():
    """A freshly built schema in the test database, for one test."""
    try:
        _ensure_test_database()
        c = psycopg2.connect(**config.db_settings())
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Postgres not reachable (start it with `docker compose up -d`): {exc}")
    db.apply_sql_files(c)
    yield c
    c.close()
