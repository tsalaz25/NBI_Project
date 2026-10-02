#Configuration. Everything Tunable
#
#Values come from ENV variables, which are read from the
#project's .env file (copy .env.example to .env). 
#Not dependant on the current working directory, so it behaves the same from wherever you run.

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

#Override=False -> A var is already set in env
#.env.  Test suite relies on this to point to seperte DB
load_dotenv(ROOT / ".env", override = False)
RAW_DIR = ROOT / "data" / "raw"
INTERIM_DIR = ROOT / "data" / "interim"
SQL_DIR = ROOT / "sql"

for d in (RAW_DIR, INTERIM_DIR):
    d.mkdir(parents = True, exist_ok = True)

# DB
def db_settings(dbname : str | None = None) -> dict:
    
    #Connection Settings, Read from env for each call
    return dict(
        host = os.getenv("PGHOST", "localhost"),
        port = int(os.getenv("PGPORT", "5433")),
        dbname = dbname or os.getenv("PGDATABASE", "nbi"),
        user = os.getenv("PGUSER", "nbi"),
        password = os.getenv("PGPASSWORD", "nbi"),
    )

# SCOPE: NM has ~4000 bridges, 1992-2025 is full run of annual reports
ATE = os.getenv("NBI_STATE", "NM").upper()
YEAR_START = int(os.getenv("NBI_YEAR_START", "1992"))
YEAR_END = int(os.getenv("NBI_YEAR_END", "2025"))
YEARS = list(range(YEAR_START, YEAR_END + 1))

NBI_BASE = "https://www.fhwa.dot.gov/bridge/nbi/"
NBI_PAGE = NBI_BASE + "ascii{year}.cfm"

# ITEMS ingested... Delimited Headers -> NAME_ITEM matched on item-# suffix
# make parser tolerant of File name changes
CONDITION_ITEMS ={
    "058": "DECK",
    "059": "SUPERSTRUCTURE",
    "060": "SUBSTRUCTURE",
    "062": "CULVERT",
}
# 1 = Bridge,  2, A-Z = a route UNDER it
INVENTORY_ITEMS = {
    "001": "state_code",
    "005A": "record_type",       
    "008": "structure_number",
    "022": "owner_code",
    "027": "year_built",
    "043A": "structure_kind",
    "043B": "structure_type",
    "045": "main_unit_spans",
    "049": "structure_length_m",
    "090": "inspection_date",
    "091": "inspect_freq_months",
    "106": "year_reconstructed",
}

# REPORTING Specification... NBI data for a year Y inputted on 3/15/Y
SNBI_FIRST_DATA_YEAR = 2026
def spec_for_year(year: int) -> str:
    return "SNBI_2022" if year >= SNBI_FIRST_DATA_YEAR else "CODING_GUIDE_1995"
    