-- Extract a randomized sample of 18 completed feedback records covering:
--   • at least one row per distinct characteristics combination
--   • at least 2 robot feedback with an annotated image
--   • at least one exercise of each type (console / robot / design)
--   • at least one task_type-level feedback per task type (kc_name)
-- Rows satisfying several quotas at once are counted once (deduped by id).
-- If the quotas alone exceed 18, lower-priority buckets are trimmed first.

WITH d_series_types(platform_exercise_id, exercise_type) AS (
    -- Series D exercise → type mapping (from exercises.json; consoleDisplay → console)
    VALUES
        ('116', 'robot'),  ('109', 'robot'),  ('115', 'robot'),
        ('110', 'design'), ('108', 'design'), ('112', 'design'),
        ('56',  'design'), ('106', 'design'),
        ('111', 'console'), ('113', 'console'), ('118', 'console'),
        ('117', 'console'), ('114', 'console'), ('96',  'console'),
        ('163', 'console'), ('129', 'console'), ('130', 'console'),
        ('126', 'console'), ('41',  'console'), ('92',  'console'),
        ('131', 'console'), ('107', 'console'), ('128', 'console'),
        ('124', 'console')
),

base AS (
    SELECT
        fr.id,
        fr.platform_id,
        fr.level,
        fr.mode,
        fr.language,
        fr.kc_name,
        fr.kc_description,
        fr.exercise_id,
        COALESCE(dt.exercise_type, ex.exercise_type)          AS exercise_type,
        ex.title                                              AS exercise_title,
        ex.description                                        AS exercise_description,
        fr.characteristics,
        (SELECT string_agg(c.val, '+' ORDER BY c.val)
           FROM jsonb_array_elements_text(fr.characteristics::jsonb) AS c(val)
        )                                                     AS characteristics_combo,
        fr.request_payload::jsonb -> 'error' ->> 'tag'        AS error_tag,
        fr.request_payload::jsonb -> 'error' ->> 'description' AS error_description,
        CASE WHEN fr.level = 'task_type' THEN fr.kc_name END  AS task_type_key,
        (fr.result_xml LIKE '%<image_url>%')                  AS has_image,
        fr.validation_status,
        fr.created_at,
        fr.result_xml
    FROM feedback_records fr
    LEFT JOIN d_series_types dt ON dt.platform_exercise_id = fr.exercise_id
    LEFT JOIN exercises       ex ON ex.exercise_id          = fr.exercise_id
    WHERE fr.status = 'completed'
      AND fr.result_xml IS NOT NULL
),

candidates AS (
    -- P1: one random row per characteristics combination
    SELECT id, 1 AS priority FROM (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY characteristics_combo
                                      ORDER BY random()) AS rn
        FROM base
    ) t WHERE rn = 1

    UNION ALL

    -- P2: two random robot feedback with an annotated image
    SELECT id, 2 FROM (
        SELECT id, ROW_NUMBER() OVER (ORDER BY random()) AS rn
        FROM base
        WHERE exercise_type = 'robot' AND has_image
    ) t WHERE rn <= 2

    UNION ALL

    -- P3: one random row per exercise type (console / robot / design)
    SELECT id, 3 FROM (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY exercise_type
                                      ORDER BY random()) AS rn
        FROM base
        WHERE exercise_type IN ('console', 'robot', 'design')
    ) t WHERE rn = 1

    UNION ALL

    -- P4: one random row per task type (kc_name at task_type level)
    SELECT id, 4 FROM (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY task_type_key
                                      ORDER BY random()) AS rn
        FROM base
        WHERE task_type_key IS NOT NULL
    ) t WHERE rn = 1

    UNION ALL

    -- P5: random filler to reach 18
    SELECT id, 5 FROM base
),

final_ids AS (
    SELECT id
    FROM (SELECT id, MIN(priority) AS priority
          FROM candidates
          GROUP BY id) picked
    ORDER BY priority, random()
    LIMIT 18
)

SELECT
    b.id,
    b.level,
    b.characteristics_combo,
    b.characteristics,
    b.exercise_id,
    b.exercise_type,
    b.exercise_title,
    b.task_type_key       AS task_type,
    b.error_tag,
    b.error_description,
    b.kc_name,
    b.kc_description,
    b.language,
    b.mode,
    b.has_image,
    b.validation_status,
    b.created_at,
    b.result_xml
FROM base b
JOIN final_ids f USING (id)
ORDER BY b.level, b.exercise_type NULLS LAST, b.characteristics_combo;
