/*
BITEMPORALITY Implementation
Reusable queries, installed by `python -m src.setup_db`.

   measurement_as_of (year)       WHAT did we know as of report year Y
   refresh_lifecycle (threshold)  Rebuild Survivial Table
*/


/*
Every value an Annual Report asserts is in `measurement`.
Corrections are new Rows, No Overwrites. So the value "as known in report year Y" is 
the latest row in each (inspection, method) chain whose reported_year <= Y.

SELECT * FROM measurement_as_of(2009) WHERE asset_id = 'NM-...';
SELECT * FROM measurement_as_of(2010) WHERE asset_id = 'NM-...';

The same inspection can return different values for 2009 and
2010: The Correction is Preserved.
*/
CREATE FUNCTION measurement_as_of(as_of_year int)
RETURNS TABLE (
    asset_id          text,
    observed_at       date,
    component         text,
    value_numeric     numeric,
    value_from_report int,
    measurement_id    bigint
)
LANGUAGE sql STABLE AS $$
    SELECT DISTINCT ON (x.event_id, x.method_id)
           e.asset_id, e.observed_at, m.component,
           x.value_numeric, x.reported_year, x.measurement_id
    FROM measurement x
    JOIN observation_event e ON e.event_id  = x.event_id
    JOIN method            m ON m.method_id = x.method_id
    WHERE x.reported_year <= as_of_year
    ORDER BY x.event_id, x.method_id, x.reported_year DESC
$$;


/*
SURVIVAL TABLE.
Failure = 1st Incpection where a Componenet's rating is <= `threshold` 
(Default 4: FHWA classifies a Bridge as Poor when Lowest Component Rating <= 4).

Follow-up Window for each (Bridge, Component) Tuple:
    -starts at the 1st Inspection 
    -ends   at the last Inspection of the ORIGINAL component. If Reconstructed during
            window, Inspections after are a Different Physical Object, Ignored  
    -event  1st Inspection <= threshold
            True Failure time is somewhere between Previous Incpection, Use Inspection Year for Approx. 
    -censor Last Inspection >= Threshold
    -clock  Starts at year_built OR at Reconstruction Predating 1st Inspection

Exclusions are recorded, not dropped:
    -'no year_built'                  Cant Compute Age
    -'built after first inspection'   Inconsistent Dates
    -'at threshold when first seen'   Already Failed before recording, LEFT-CENSORED, Unknown Failure Age
    -'no follow-up'                   Nothing Observed after entry

Uses current/corrected) Vals
Known Limitation: asset keeps only the most recently reported reconstruction year.
*/
CREATE FUNCTION refresh_lifecycle(threshold int DEFAULT 4)
RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
    n bigint;
BEGIN
    DELETE FROM lifecycle;

    INSERT INTO lifecycle
        (asset_id, component, origin_year, entry_age, duration_years,
         event_observed, threshold_rating, excluded_reason)
    WITH obs AS (
        SELECT c.asset_id, c.component, c.observed_at,
               extract(year FROM c.observed_at)::int AS obs_year,
               c.value_numeric AS rating,
               a.year_built, a.year_reconstructed
        FROM v_current_measurement c
        JOIN asset a ON a.asset_id = c.asset_id
    ),
    bounds AS (
        SELECT asset_id, component, year_built, year_reconstructed,
               min(obs_year) AS first_obs,
               max(obs_year) AS last_obs
        FROM obs
        GROUP BY asset_id, component, year_built, year_reconstructed
    ),
    windowed AS (
        SELECT b.*,
               (b.year_reconstructed > b.first_obs
                AND b.year_reconstructed <= b.last_obs)       AS rebuilt_in_window,
               CASE WHEN b.year_reconstructed <= b.first_obs
                    THEN b.year_reconstructed
                    ELSE b.year_built END                     AS origin_year
        FROM bounds b
    ),
    in_window AS (      -- inspections of the ORIGINAL component only
        SELECT o.*
        FROM obs o
        JOIN windowed w USING (asset_id, component)
        WHERE NOT coalesce(w.rebuilt_in_window, false)
           OR o.obs_year < w.year_reconstructed
    ),
    per AS (
        SELECT asset_id, component,
               min(obs_year)                                   AS first_obs,
               max(obs_year)                                   AS last_obs,
               min(obs_year) FILTER (WHERE rating <= threshold) AS first_fail,
               (array_agg(rating ORDER BY observed_at))[1]     AS first_rating
        FROM in_window
        GROUP BY asset_id, component
    ),
    shaped AS (
        SELECT w.asset_id, w.component, w.origin_year,
               p.first_obs - w.origin_year AS entry_age,
               -- failure: first inspection at/below threshold.
               -- censoring: the last inspection of the original component,
               -- the last time we actually saw it above threshold.
               coalesce(p.first_fail, p.last_obs) - w.origin_year AS duration_years,
               p.first_fail IS NOT NULL AS event_observed,
               p.first_rating
        FROM windowed w
        JOIN per p USING (asset_id, component)
    ),
    labeled AS (
        SELECT s.*,
               CASE
                   WHEN origin_year IS NULL            THEN 'no year_built'
                   WHEN entry_age < 0                  THEN 'built after first inspection'
                   WHEN first_rating <= threshold      THEN 'at threshold when first seen'
                   WHEN duration_years <= entry_age    THEN 'no follow-up'
               END AS excluded_reason
        FROM shaped s
    )
    SELECT asset_id, component, origin_year,
           CASE WHEN excluded_reason IS NULL THEN entry_age END,
           CASE WHEN excluded_reason IS NULL THEN duration_years END,
           CASE WHEN excluded_reason IS NULL THEN event_observed END,
           threshold,
           excluded_reason
    FROM labeled;

    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;
