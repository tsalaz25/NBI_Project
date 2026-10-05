/*
Checks after a load. 
  Open in VS Code with SQLTools and run a statement with Cmd+E Cmd+E (macOS),
  OR paste into the psql shell task.
*/

/*
1. 1-Row/ Year. 
   Look for Years with odd counts: A "succeeding" with far fewer rows than its neighbours is suspect.
*/
SELECT data_year, spec_name, data_lines, rows_read, rows_malformed,
       rows_route_under, rows_rejected, rows_undated, events_new, events_rereported,
       measures_new, measures_corrected, measures_unchanged
FROM ingest_run
ORDER BY data_year;

/*
2. Schema Drift: Which expected Cols missing, by year.
*/
SELECT data_year, columns_missing
FROM ingest_run
WHERE columns_missing IS NOT NULL
ORDER BY data_year;

/*
3. How often is an inspection re-published in a later report? 
   With 24-month cycles inspections should twice.
*/
SELECT reports, count(*) AS inspections
FROM (SELECT event_id, count(*) AS reports FROM event_report GROUP BY event_id) t
GROUP BY reports
ORDER BY reports;

/*
4. Corrections: Same Incpectoin, Diff Val in later report.
*/
SELECT *
FROM v_corrections
ORDER BY new_reported_year, asset_id
LIMIT 50;

/*
5. Correction Rate by Report Year.
*/
SELECT ir.data_year,
       ir.measures_corrected,
       round(100.0 * ir.measures_corrected
             / nullif(ir.measures_corrected + ir.measures_unchanged, 0), 2) AS pct_of_rereported
FROM ingest_run ir
ORDER BY ir.data_year;

/*
 6. Current Rating Distribution by Component.
*/
SELECT component, value_numeric AS rating, count(*)
FROM v_current_measurement
GROUP BY component, value_numeric
ORDER BY component, rating;
