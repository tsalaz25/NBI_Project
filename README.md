# NBI_Project

## Roadmap and Plan
### Phase 0: Skeleton and Connectoin
File Structure............................................. Phase
```text
NBI/
├── .gitignore                 0
├── .env.example               0
├── docker-compose.yml         0
├── requirements.txt           0
├── README.md                  0-9
├── pytest.ini                 2
├── src/
│   ├── __init__.py            1
│   ├── config.py              1
│   ├── db.py                  1
│   ├── setup_db.py            1
│   ├── parse.py               2
│   ├── load.py                3
│   ├── download.py            5
│   ├── survival.py            7
│   └── benchmark.py           8
├── sql/
│   ├── 001_schema.sql         1 
│   ├── 002_reference_data.sql 3
│   └── 003_queries.sql        6
├── tests/
│   ├── __init__.py            2
│   ├── test_parse.py          2
│   ├── conftest.py            4
│   ├── make_fixture.py        4
│   ├── test_load.py           4
│   ├── test_download.py       5
│   └── test_queries.py        6
├── queries/checks.sql         5
├── docs/performance.md        8
├── data/raw/                  0
├── reports/                   7
└── .vscode/                   9 
```

#### Checks
- `docker compose up -d --wait`
- `docker exec -it nbi-postgres psql -U nbi -d nbi`

Chhecking to to see SQL Prompt
![alt text](<Screenshot 2026-10-01 at 5.58.39 PM.png>)

### Phase 1: Connnect To DB