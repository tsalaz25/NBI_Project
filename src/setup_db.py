# Creates (or re-creates) the Schema... Replaces running psql
# USAGE
#   pythom -m src.setup_db
#
# NOTE: sql/001_schema.sql uses DROP TABLE... erases any loaded data... Is a hard Reset

from __future__ import annotations

import sys

from src import db

def main() -> int:
    conn = db.connect(retries=15)  # give a just-started container time
    try:
        applied = db.apply_sql_files(conn)
    finally:
        conn.close()
    for name in applied:
        print(f"applied  {name}")
    print("schema ready")
    return 0

if __name__ == "__main__":
    sys.exit(main())