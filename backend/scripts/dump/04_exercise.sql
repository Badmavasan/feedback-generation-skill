-- ===========================================================================
-- TABLE 4/5 : exercise
-- The exercise each feedback applies to (console / design / robot), pulled from
-- the exercises table. One row per feedback; joins to feedback on feedback_id.
-- exercise_id may be NULL (task_type-level feedback is not exercise-bound) — a
-- LEFT JOIN keeps those rows with empty exercise columns.
--
-- For the de-duplicated dimension (distinct exercises only), use the DISTINCT
-- variant at the bottom of this file instead.
--
-- Export to CSV with psql:
--   psql "$DB_URL" -f 04_exercise.sql --csv -o exercise.csv
-- ===========================================================================

SELECT
    fr.id                 AS feedback_id,
    fr.exercise_id        AS exercise_platform_id,
    ex.title              AS exercise_title,
    ex.exercise_type,     -- console | design | robot
    ex.description        AS exercise_description,
    ex.robot_map,         -- only for robot exercises
    ex.possible_solutions,
    ex.kc_names
FROM feedback_records fr
LEFT JOIN exercises ex ON ex.exercise_id = fr.exercise_id
WHERE fr.status = 'completed'
  AND fr.result_xml IS NOT NULL
ORDER BY fr.id;

-- --- Distinct dimension (uncomment to dump unique referenced exercises) -----
-- SELECT
--     ex.exercise_id  AS exercise_platform_id,
--     ex.title        AS exercise_title,
--     ex.exercise_type,
--     ex.description  AS exercise_description,
--     ex.robot_map,
--     ex.possible_solutions,
--     ex.kc_names
-- FROM exercises ex
-- WHERE ex.exercise_id IN (
--     SELECT DISTINCT exercise_id FROM feedback_records
--     WHERE status = 'completed' AND result_xml IS NOT NULL
--       AND exercise_id IS NOT NULL
-- )
-- ORDER BY ex.exercise_id;
