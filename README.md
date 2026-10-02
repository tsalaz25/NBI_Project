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
![alt text](<Screenshot 2026-10-01 at 5.58.39 PM.png>)

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

### Phase 2: Parse Real Data

### Phase 3: Load in 1 Year and Test

### Phase 4: Load in all Years

### Phase 5: Bitemporality

### Phase 6: Survivial Analysis

### Phase 7: Performance 

### Phase 8: VSC 