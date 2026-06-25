-- ===========================================================================
-- TABLE 3/5 : task_type  (type of task / knowledge component)
-- The KC targeted by each feedback. When level = 'task_type' the KC *is* the
-- task type itself; for the other levels it is the KC the feedback drills into.
-- One row per feedback; joins to feedback on feedback_id.
--
-- For the de-duplicated dimension (distinct task types only), use the
-- DISTINCT variant at the bottom of this file instead.
--
-- Export to CSV with psql:
--   psql "$DB_URL" -f 03_task_type.sql --csv -o task_type.csv
-- ===========================================================================

SELECT
    fr.id                                   AS feedback_id,
    fr.kc_name                              AS task_type_code,
    fr.kc_description                       AS task_type_description,
    (fr.level = 'task_type')                AS is_task_type_level
FROM feedback_records fr
WHERE fr.status = 'completed'
  AND fr.result_xml IS NOT NULL
ORDER BY fr.id;

-- --- Distinct dimension (uncomment to dump unique task types instead) -------
-- SELECT
--     fr.kc_name                AS task_type_code,
--     max(fr.kc_description)    AS task_type_description,
--     count(*)                  AS feedback_count
-- FROM feedback_records fr
-- WHERE fr.status = 'completed' AND fr.result_xml IS NOT NULL
-- GROUP BY fr.kc_name
-- ORDER BY fr.kc_name;
