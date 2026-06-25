-- ===========================================================================
-- TABLE 5/5 : error
-- The error the feedback addresses. Stored inside feedback_records.request_payload
-- (JSON) under the "error" key, and mirrored into result_xml/<error_context> when
-- the error_pointed component was generated. One row per feedback; joins to
-- feedback on feedback_id. Feedback at non-error levels has no error → NULL tag.
--
-- Export to CSV with psql:
--   psql "$DB_URL" -f 05_error.sql --csv -o error.csv
-- ===========================================================================

SELECT
    fr.id                                                AS feedback_id,
    fr.request_payload::jsonb -> 'error' ->> 'tag'       AS error_tag,
    fr.request_payload::jsonb -> 'error' ->> 'description' AS error_description,
    -- error_context as actually emitted in the feedback XML (may be absent even
    -- when an error tag exists, if the error_pointed component was not produced)
    (xpath('/feedback/error_context/tag/text()',
           xmlparse(document fr.result_xml)))[1]::text   AS error_tag_in_xml,
    (xpath('/feedback/error_context/description/text()',
           xmlparse(document fr.result_xml)))[1]::text   AS error_description_in_xml
FROM feedback_records fr
WHERE fr.status = 'completed'
  AND fr.result_xml IS NOT NULL
ORDER BY fr.id;

-- --- Distinct dimension (uncomment to dump unique error tags referenced) -----
-- SELECT
--     fr.request_payload::jsonb -> 'error' ->> 'tag'         AS error_tag,
--     max(fr.request_payload::jsonb -> 'error' ->> 'description') AS error_description,
--     count(*)                                               AS feedback_count
-- FROM feedback_records fr
-- WHERE fr.status = 'completed' AND fr.result_xml IS NOT NULL
--   AND fr.request_payload::jsonb -> 'error' ->> 'tag' IS NOT NULL
-- GROUP BY 1
-- ORDER BY 1;
