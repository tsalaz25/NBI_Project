# Database Helpers... shared by the setup script, loader, and tests.
from __future__ import annotations
import time
import psycopg2
from src import config

#Open a connection. "Retries" wait for a container that is still starting
def connect(dbname: str | None = None, retries: int = 0):
    settings = config.db_settings(dbname)
    for attempt in range(retries + 1):
        try:
            return psycopg2.connect(**settings)
        except psycopg2.OperationalError as exc:
            if attempt == retries:
                raise SystemExit(
                    f"Could not connect to Postgres at "
                    f"{settings['host']}:{settings['port']} db={settings['dbname']}.\n"
                    f"Is it running? Try:  docker compose up -d\n\n{exc}"
                )
            time.sleep(1)


#Run every sql/NNN_*.sql file in order. Returns the Names Applied.
def apply_sql_files(conn) -> list[str]:
    files = sorted(config.SQL_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    with conn.cursor() as cur:
        for f in files:
            cur.execute(f.read_text(encoding="utf-8"))
    conn.commit()
    return [f.name for f in files]
