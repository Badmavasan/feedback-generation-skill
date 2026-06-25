-- ===========================================================================
-- TABLE 1/5 : feedback (fact table)
-- One row per completed feedback record. All other dump tables join back to
-- this one on feedback_id.
--
-- Export to CSV with psql:
--   \copy (<paste this query>) TO 'feedback.csv' WITH (FORMAT csv, HEADER)
-- or:
--   psql "$DB_URL" -f 01_feedback.sql --csv -o feedback.csv
-- ===========================================================================

SELECT
    fr.id                         AS feedback_id,
    fr.platform_id,
    fr.level,                     -- error | error_exercise | exercise | task_type
    fr.mode,                      -- offline | live
    fr.language,
    fr.exercise_id,               -- FK → exercise table (string platform id)
    fr.kc_name,                   -- FK → task_type table
    (SELECT string_agg(c.val, '+' ORDER BY c.val)
       FROM jsonb_array_elements_text(fr.characteristics::jsonb) AS c(val)
    )                             AS characteristics_combo,
    fr.characteristics            AS characteristics_raw,
    fr.total_iterations,
    fr.status,
    fr.validation_status,         -- generated | validé
    fr.error_message,
    fr.created_at
FROM feedback_records fr
WHERE fr.status = 'completed'
  AND fr.result_xml IS NOT NULL
ORDER BY fr.created_at;
