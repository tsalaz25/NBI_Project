# NBI_Project

## Roadmap and Plan
### Phase 0: Skeleton and Connectoin
File Structure
```text
NBI/
├── .gitignore                 
├── .env.example               
├── docker-compose.yml         
├── requirements.txt           
├── README.md                  
├── pytest.ini                 
├── src/
│   ├── __init__.py            
│   ├── config.py              
│   ├── db.py                 
│   ├── setup_db.py            
│   ├── parse.py               
│   ├── load.py                
│   ├── download.py            
│   ├── survival.py            
│   └── benchmark.py           
├── sql/
│   ├── 001_schema.sql          
│   ├── 002_reference_data.sql 
│   └── 003_queries.sql        
├── tests/
│   ├── __init__.py           
│   ├── test_parse.py          
│   ├── conftest.py            
│   ├── make_fixture.py        
│   ├── test_load.py           
│   ├── test_download.py       
│   └── test_queries.py        
├── queries/checks.sql         
├── docs/performance.md        
├── data/raw/                  
├── reports/                   
└── .vscode/                    
```
### Phase 1: Connect to DB
#### Tasks
- git init
- write `.gitignore`, `.env.example`, `docker-compose.yaml` (and example) and `requirments.txt`
#### Tests
- `docker compose up -d --wait`
- `docker exec -it nbi-postgres psql -U nbi -d nbi`

Chhecking to to see SQL Prompt... Screenshot Below

NEED TO FIX IMAGE

### Phase 1: Connnect To DB
#### Tasks
- Write `config.py`, `db.py`, `setup_db.py` and `001_schema.sql` (Schema Setup)
#### Tests
Run these commands in teminal in this order
- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- `docker compose up -d --wait`
- `python -m src.setup_db`
- Confirm Tables `docker compose exec db psql -U nbi -d nbi -c "\dt"` and `docker compose exec db psql -U nbi -d nbi -c "\d asset" `

### Phase 2: Parse 1 Real Year and Load it

#### Before Anything
Download 2 file manually, run commands from Phase 1 then:
-  `mkdir -p data/raw/2020` then  `curl -o data/raw/2020/NM20.txt https://www.fhwa.dot.gov/bridge/nbi/2020/delimited/NM20.txt`

- `mkdir -p data/raw/2009` then  `curl -o data/raw/2009/N090.txt https://www.fhwa.dot.gov/bridge/nbi/2009/delimited/NM09.txt`
- `wc -l data/raw/2020/NM20.txt`... Expect 4025
- `wc -l data/raw/2009/NM09.txt`... Expect 4595
- Look at Headers to Write `parse.py`

#### Tasks
- Write `parse.py` in this Order: `index_headers` > `_clean` and `_to_num` > `parse_inspection_date` > `count_data_lines` > `parse_file` 
- Double Check Schema and Make Tables in PSQL `002_reference_data.sql`
- Load in Data, Write `load.py`

#### Tests
GOAL: Make sure we can Load and Ingest 1 Real Year
- Write `test_parse.py`, `make_fixture.py`, `conftest.py`, and `test_load.py`

Run These Commands in Order (from beginning)
- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- `docker compose up -d --wait`
- `mkdir -p data/raw/2020 && mkdir -p data/raw/2009`
-  `curl -f -o data/raw/2020/NM20.txt https://www.fhwa.dot.gov/bridge/nbi/2020/delimited/NM20.txt`
- `curl -f -o data/raw/2009/NM09.txt https://www.fhwa.dot.gov/bridge/nbi/2009/delimited/NM09.txt`
- `touch tests/__init__.py`
- `printf "[pytest]\ntestpaths = tests\naddopts = -q\n" > pytest.ini`
- Tester: `python -m pytest tests/test_parse.py -v`



### Phase 3: Load in All Years
GOAL: Now that Parser works for both types of records, Load in Data from all 34 years

#### Tasks
- Write `download.py`, `queries/checks.sql` and `test_download.py`

#### Tests
Test with Following Commands
- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- `docker compose up -d --wait`
- `python -m src.setup_db`
- `python -m src.download --list 2024`
- `python -m src.download` (Takes a Few Minutes)
- `ls data/raw | wc -l`
- `python -m src.load` 
* Look for `2009 -> 4594 Rows | 0 Malformed | 689 Route Under`, `2010 -> 3903 Rows | 0 Malformed | 0 Route Under` and `2024 -> 4035 Rows`
- Table Checks
1. `docker compose exec -T db psql -U nbi -d nbi -c "SELECT data_year, data_lines, rows_read, rows_malformed, rows_route_under, rows_rejected, rows_undated, events_new + events_rereported AS bridges, measures_corrected FROM ingest_run ORDER BY data_year;"`
2. ` docker compose exec -T db psql -U nbi -d nbi -c "SELECT
  (SELECT count(*) FROM ingest_run) AS years_loaded,
  (SELECT count(*) FROM ingest_run WHERE data_lines <> rows_read + rows_malformed) AS lines_unaccounted,
  (SELECT count(*) FROM ingest_run WHERE data_year >= 2010 AND rows_route_under > 0) AS route_under_after_2010,
  (SELECT count(*) FROM ingest_run WHERE finished_at IS NULL) AS unfinished_runs;" `

  Expect `years_loaded -> 34 | lines_uncounted -> 0 | route_under_after_2010 -> 0 | unfinshed_runs -> 0`

  3. `docker compose exec -T db psql -U nbi -d nbi < queries/checks.sql`
  - Tester: `python -m pytest tests/test_load.py tests/test_download.py -v`



### Phase 4: Bitemporality

#### Tasks
- Check `supersede` Col in `001_schema.sql`... The `event_report`
- Write `003_queries.sql` and `test_queries.py`

#### Tests
From a Fresh Terminal, Run
- `python3 -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements.txt`
- `docker compose up -d --wait`
- `python -m src.setup_db`
- `python -m src.download --list 2024`
- `python -m src.download` 
- `python -m src.load` 

Tests Commands
1. Valid Time vs Transaction Time, Most Inspections shulde appear Twice: `docker compose exec -T db psql -U nbi -d nbi -c "SELECT reports, count(*) AS inspections FROM (SELECT event_id, count(*) AS reports FROM event_report GROUP BY event_id) t GROUP BY reports ORDER BY reports;"`
2. One Inpection in 3 Reports with Correction: ` docker compose exec -T db psql -U nbi -d nbi -c "
WITH pick AS (
    SELECT asset_id, observed_at, component, old_reported_year, new_reported_year
    FROM v_corrections
    WHERE new_reported_year = 2010
    ORDER BY new_value - old_value DESC
    LIMIT 1
)
SELECT p.asset_id, p.observed_at, p.component, y.as_of,
       a.value_numeric, a.value_from_report
FROM pick p
CROSS JOIN LATERAL (VALUES (p.old_reported_year - 1),
                           (p.old_reported_year),
                           (p.new_reported_year)) y(as_of)
LEFT JOIN LATERAL (
    SELECT * FROM measurement_as_of(y.as_of) a
    WHERE a.asset_id = p.asset_id
      AND a.observed_at = p.observed_at
      AND a.component = p.component
) a ON true
ORDER BY y.as_of;" `
3. One Current Val per Inspectoin and Method: `docker compose exec -T db psql -U nbi -d nbi -c "SELECT (SELECT count(*) FROM v_current_measurement) AS current_values, (SELECT count(DISTINCT (event_id, method_id)) FROM measurement) AS chains;"`
4. Test Files: `python -m pytest tests/test_queries.py -k as_of -v` and `python -m pytest tests/test_parse.py tests/test_load.py tests/test_download.py -q`


### Phase 5: Survivial Analysis

### Phase 6: Performance 