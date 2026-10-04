/*
 Reference Data: Methods and Comparability

   CODING_GUIDE_1995  "Recording and Coding Guide for the Structure Inventory and Appraisal of the Nation's Bridges"
                       Last submittal in this format: 2025-03-15.

   SNBI_2022          "Specifications for the National Bridge Inventory" (FHWA-HIF-22-017). 
                        First submittal: 2026-03-15, as a transitioned/hybrid dataset in JSON.

OPEN QUESTION: Data Years 1992-1995 were coded under the 1988 edition of the Coding Guide, not the 1995 edition. 
valid_from is set to 1992 so every loaded year maps to a method. 
If items 58-62 changed between editions, split them into CODING_GUIDE_1988 rows and add comparability rows, 
exactly as for the SNBI transition.

SNBI item numbers verified against the SNBI table of contents:
B.C.01 Deck, B.C.02 Superstructure, B.C.03 Substructure,B.C.04 Culvert.

TODO: Replace PROVISIONAL Comp-Rows with the FHWA Data Crosswalk and Cite
*/

INSERT INTO method
    (spec_name, item_code, component, scale_min, scale_max, unit_of_measure, valid_from, valid_to, notes)
VALUES
    ('CODING_GUIDE_1995', '058', 'DECK',           0, 9, 'condition_rating', '1992-01-01', '2025-03-15', 'Item 58 Deck Condition Rating, 0-9; N = not applicable'),
    ('CODING_GUIDE_1995', '059', 'SUPERSTRUCTURE', 0, 9, 'condition_rating', '1992-01-01', '2025-03-15','Item 59 Superstructure Condition Rating, 0-9'),
    ('CODING_GUIDE_1995', '060', 'SUBSTRUCTURE',   0, 9, 'condition_rating', '1992-01-01', '2025-03-15','Item 60 Substructure Condition Rating, 0-9'),
    ('CODING_GUIDE_1995', '062', 'CULVERT',        0, 9, 'condition_rating', '1992-01-01', '2025-03-15','Item 62 Culvert Condition Rating, 0-9; N for non-culverts'),

    ('SNBI_2022', 'B.C.01', 'DECK',           0, 9, 'condition_rating', '2026-03-15', NULL,'SNBI Deck Condition Rating'),
    ('SNBI_2022', 'B.C.02', 'SUPERSTRUCTURE', 0, 9, 'condition_rating', '2026-03-15', NULL,'SNBI Superstructure Condition Rating'),
    ('SNBI_2022', 'B.C.03', 'SUBSTRUCTURE',   0, 9, 'condition_rating', '2026-03-15', NULL,'SNBI Substructure Condition Rating'),
    ('SNBI_2022', 'B.C.04', 'CULVERT',        0, 9, 'condition_rating', '2026-03-15', NULL,'SNBI Culvert Condition Rating')
ON CONFLICT (spec_name, item_code) DO NOTHING;

/*
Cross-Spec Pairs, both directions. 
PROVISIONAL until the crosswalk is loaded...Query must state the assumption.
*/
WITH pairs AS (
    SELECT a.method_id AS a_id, b.method_id AS b_id
    FROM method a
    JOIN method b
      ON a.component = b.component
     AND a.spec_name = 'CODING_GUIDE_1995'
     AND b.spec_name = 'SNBI_2022'
)
INSERT INTO comparability (method_a, method_b, comparable, transform, source)
SELECT a_id, b_id, TRUE, NULL,
       'PROVISIONAL - same 0-9 scale; verify against FHWA Data Crosswalk'
FROM pairs
UNION ALL
SELECT b_id, a_id, TRUE, NULL,
       'PROVISIONAL - same 0-9 scale; verify against FHWA Data Crosswalk'
FROM pairs
ON CONFLICT DO NOTHING;

/*
Methods always comparable with self.
*/
INSERT INTO comparability (method_a, method_b, comparable, transform, source)
SELECT method_id, method_id, TRUE, NULL, 'identity'
FROM method
ON CONFLICT DO NOTHING;
