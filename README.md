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
- `python -m pytest tests/test_parse.py -v`



### Phase 3: Load in all Years

### Phase 4: Bitemporality

### Phase 5: Survivial Analysis

### Phase 6: Performance 

### Phase 7: VSC 