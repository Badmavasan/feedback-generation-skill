-- ===========================================================================
-- TABLE 2/5 : feedback_component
-- One row per feedback component, exploded out of feedback_records.result_xml.
-- Joins to feedback on feedback_id.
--
-- result_xml shape:
--   <feedback>
--     <components>
--       <component characteristic="..." type="text|image">
--         <iterations>..</iterations>
--         <content>..</content>            (text components)
--         <image_url>..</image_url>         (image components)
--         <caption>..</caption>
--         <quality_score>..</quality_score> (optional)
--         <evaluation_notes>..</evaluation_notes> (optional)
--       </component> ...
--
-- Export to CSV with psql:
--   psql "$DB_URL" -f 02_components.sql --csv -o feedback_component.csv
-- ===========================================================================

SELECT
    fr.id                          AS feedback_id,
    row_number() OVER (PARTITION BY fr.id) AS component_index,
    c.characteristic,
    c.type,                        -- text | image
    c.iterations,
    c.content,                     -- NULL for image components
    c.image_url,                   -- NULL for text components
    c.caption,
    c.quality_score,
    c.evaluation_notes
FROM feedback_records fr
CROSS JOIN LATERAL
    xmltable(
        '/feedback/components/component'
        PASSING xmlparse(document fr.result_xml)
        COLUMNS
            characteristic   text    PATH '@characteristic',
            type             text    PATH '@type',
            iterations       int     PATH 'iterations',
            content          text    PATH 'content',
            image_url        text    PATH 'image_url',
            caption          text    PATH 'caption',
            quality_score    numeric PATH 'quality_score',
            evaluation_notes text    PATH 'evaluation_notes'
    ) AS c
WHERE fr.status = 'completed'
  AND fr.result_xml IS NOT NULL
ORDER BY fr.id, component_index;
