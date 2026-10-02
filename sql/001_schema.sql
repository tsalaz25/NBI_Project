/*
NBI Surveillance Analog -- core schema

   asset              Serialized Unit... 1-Row / Bridge

   ingest_run         1-Row / (state, data_year) [Annual Report]
                      Analogous to TRANSACTION TIME ["when did we know it"]

   observation_event  1-Row / Physical Inspection
                      Keyed on the inspection date A
                      Analogous to  VALID TIME ["when did it happen"]

   event_report       Which Annual Reports carried which inspection.
                      Inspections run on a 24-month cycle but FHWA publishes every year
                      So one inspection usuallyappears in two consecutive reports.

   measurement        1 value from 1 method at 1 inspection as asserted by 1 report. 
                      APPEND-ONLY

   method             Versioned Reference data for the reporting spec

   comparability      which methods may be compared across a spec change

   lifecycle          survival-analysis table: duration + censoring

 Rules enforced by the database
   * measurement rows can never be UPDATE'd or DELETE'd
   * a correction is a NEW row whose `supersedes` points at the row
     it replaces each row can be superseded at most once (UNIQUE)
   * every measurement names the method revision that produced it
*/
DROP VIEW  IF EXISTS v_current_measurement CASCADE;
DROP VIEW  IF EXISTS v_corrections        CASCADE;
DROP TABLE IF EXISTS measurement          CASCADE;
DROP TABLE IF EXISTS event_report         CASCADE;
DROP TABLE IF EXISTS observation_event    CASCADE;
DROP TABLE IF EXISTS lifecycle            CASCADE;
DROP TABLE IF EXISTS comparability        CASCADE;
DROP TABLE IF EXISTS method               CASCADE;
DROP TABLE IF EXISTS asset                CASCADE;
DROP TABLE IF EXISTS ingest_run           CASCADE;
DROP FUNCTION IF EXISTS forbid_measurement_mutation() CASCADE;
DROP FUNCTION IF EXISTS measurement_as_of(int) CASCADE;
DROP FUNCTION IF EXISTS refresh_lifecycle(int) CASCADE;

/*
PROVENANCE / TRANSACTION TIME.
1-Row /Annual Report  
The whole year loads in one transaction, so if this row exists, the year loaded completely.
The counts make a failure visible: a year that "succeeds" with 40% of the expected rows stands out.
*/
CREATE TABLE ingest_run (
    run_id              bigserial PRIMARY KEY,
    source_file         text        NOT NULL,
    state_code          text        NOT NULL,
    data_year           int         NOT NULL,
    spec_name           text        NOT NULL,
    data_lines          int         NOT NULL,             -- non-blank lines in the file, minus header
    rows_read           int         NOT NULL,             -- rows the CSV reader produced
    rows_malformed      int         NOT NULL DEFAULT 0,   -- data_lines - rows_read: lines lost in parsing
    rows_route_under    int         NOT NULL DEFAULT 0,   -- item 5A != '1': a road UNDER a bridge, not a bridge
    rows_rejected       int         NOT NULL DEFAULT 0,   -- no structure number / duplicate bridge
    rows_undated        int         NOT NULL DEFAULT 0,   -- no usable inspection date
    assets_upserted     int         NOT NULL DEFAULT 0,
    events_new          int         NOT NULL DEFAULT 0,   -- first time we saw this inspection
    events_rereported   int         NOT NULL DEFAULT 0,   -- inspection already known from an earlier report
    measures_new        int         NOT NULL DEFAULT 0,
    measures_corrected  int         NOT NULL DEFAULT 0,   -- same inspection, different value than before
    measures_unchanged  int         NOT NULL DEFAULT 0,   -- same inspection, same value: no new row
    columns_missing     text[],                           -- schema drift, captured as data
    started_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz,
    UNIQUE (state_code, data_year)
);

/*
THE UNIT
1-Row / Physical Bridge
*/ 
CREATE TABLE asset (
    asset_id            text PRIMARY KEY,      -- state || '-' || structure_number
    state_code          text NOT NULL,
    structure_number    text NOT NULL,
    year_built          int,
    year_reconstructed  int,
    owner_code          text,
    structure_kind      text,                  -- item 43A: material
    structure_type      text,                  -- item 43B: design
    main_unit_spans     int,
    structure_length_m  numeric,
    first_seen_year     int  NOT NULL,
    last_seen_year      int  NOT NULL,
    UNIQUE (state_code, structure_number)
);
CREATE INDEX idx_asset_built ON asset (year_built);
CREATE INDEX idx_asset_kind  ON asset (structure_kind, structure_type);

/*
VERSIONED METHOD REFERENCE
"valid_from" and "valid_to" are SUBMITTAL dates... NBI Data for year Y is submitted on 3/15/Y
    1995 Coding Guide: last submittal 3/15/25... data years <= 2025
    SNBI             : last submittal 3/15/26... data years >= 2026
config.spec_for_year mehotd must agree 
*/
CREATE TABLE method (
    method_id       serial PRIMARY KEY,
    spec_name       text NOT NULL,
    item_code       text NOT NULL,
    component       text NOT NULL,      -- DECK | SUPERSTRUCTURE | SUBSTRUCTURE | CULVERT
    scale_min       numeric,
    scale_max       numeric,
    unit_of_measure text,
    valid_from      date NOT NULL,
    valid_to        date,
    notes           text,
    UNIQUE (spec_name, item_code),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

/*
COMPARABILITY MAPPING
Encodes whether 2 method may be compared... Under what Transformation.
*/
CREATE TABLE comparability (
    method_a    int  NOT NULL REFERENCES method(method_id),
    method_b    int  NOT NULL REFERENCES method(method_id),
    comparable  boolean NOT NULL,
    transform   text,               -- NULL = identity, when comparable
    source      text NOT NULL,      -- cite the crosswalk row
    PRIMARY KEY (method_a, method_b)
);

/*
OBSERVATOIN EVENT
A Physical Inspectoin Happened
Keyed on (asset, inspection date)
Item 90 is M/Y only... observed_at is the 1st of that Month
*/
CREATE TABLE observation_event (
    event_id              bigserial PRIMARY KEY,
    asset_id              text NOT NULL REFERENCES asset(asset_id),
    observed_at           date NOT NULL,          -- item 90 (valid time)
    inspect_freq_months   int,                    -- item 91, as first reported
    age_years             int,                    -- observed year - year_built
    first_reported_year   int  NOT NULL,          -- earliest report that carried it
    UNIQUE (asset_id, observed_at)
);
CREATE INDEX idx_event_observed ON observation_event (observed_at);

/*
Which Annual Reports carried which Inspection(s)... "n-n" cardinality 
*/
CREATE TABLE event_report (
    event_id    bigint NOT NULL REFERENCES observation_event(event_id),
    run_id      bigint NOT NULL REFERENCES ingest_run(run_id),
    data_year   int    NOT NULL,
    PRIMARY KEY (event_id, data_year)
);
CREATE INDEX idx_event_report_year ON event_report (data_year);

/*
MEASURMENT
Append only
reported_year = annual repost that 1st asserted value
adds a new row whose superdedes points to old one
CURRENT = A row with no supersedes
AS KNOWN in Yr Y = Walk the Chain... Stopping at reported_year
*/
CREATE TABLE measurement (
    measurement_id  bigserial PRIMARY KEY,
    event_id        bigint  NOT NULL REFERENCES observation_event(event_id),
    method_id       int     NOT NULL REFERENCES method(method_id),
    value_numeric   numeric,
    value_text      text,
    supersedes      bigint  UNIQUE REFERENCES measurement(measurement_id),
    reported_year   int     NOT NULL,
    run_id          bigint  NOT NULL REFERENCES ingest_run(run_id),
    recorded_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL),
    CHECK (supersedes IS NULL OR supersedes < measurement_id)
);
CREATE INDEX idx_meas_event_method ON measurement (event_id, method_id);
CREATE INDEX idx_meas_method       ON measurement (method_id);

/*
Append Only enforcement
TRUNCATE (only used by full reset) is sperate and not blocked
*/
CREATE FUNCTION forbid_measurement_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
      'measurement is append-only: % is not allowed. Insert a new row with supersedes = % instead.',
      TG_OP, OLD.measurement_id;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_measurement_append_only
    BEFORE UPDATE OR DELETE ON measurement
    FOR EACH ROW EXECUTE FUNCTION forbid_measurement_mutation();

/*
SURVIVAL TABLE
Filled by refresh_lifecycle() in [add queries file later]
1-Row / (Asset, Component)... including ones that cannot be used...
    those carry an exluded_reaosn and arent dropped

origin_year = year the clock starts... year_builtn is year of reconstruction that
    happened before obervation began age
duratoin_years = age at the event or at the end of follow up
event observed = false -> right-censored
*/
CREATE TABLE lifecycle (
    asset_id          text NOT NULL REFERENCES asset(asset_id),
    component         text NOT NULL,
    origin_year       int,
    entry_age         int,
    duration_years    int,
    event_observed    boolean,
    threshold_rating  int  NOT NULL,
    excluded_reason   text,
    computed_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, component),
    CHECK (excluded_reason IS NOT NULL
           OR (entry_age >= 0 AND duration_years > entry_age AND event_observed IS NOT NULL))
);

/* Current value of every inspection (inspection, method)*/
CREATE VIEW v_current_measurement AS
SELECT
    e.asset_id,
    e.observed_at,
    e.age_years,
    m.component,
    m.spec_name,
    m.item_code,
    x.value_numeric,
    x.reported_year,
    x.measurement_id
FROM measurement x
JOIN observation_event e ON e.event_id  = x.event_id
JOIN method            m ON m.method_id = x.method_id
WHERE NOT EXISTS (
    SELECT 1 FROM measurement newer WHERE newer.supersedes = x.measurement_id
);

/*Every Correction: Inspection whose value changed between reports*/
CREATE VIEW v_corrections AS
SELECT
    e.asset_id,
    e.observed_at,
    m.component,
    old.value_numeric  AS old_value,
    old.reported_year  AS old_reported_year,
    new.value_numeric  AS new_value,
    new.reported_year  AS new_reported_year
FROM measurement new
JOIN measurement old       ON old.measurement_id = new.supersedes
JOIN observation_event e   ON e.event_id  = new.event_id
JOIN method m              ON m.method_id = new.method_id;
