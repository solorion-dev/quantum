-- PROPOSED, NOT APPLIED. For later review (Scotty/Cooper) before any change to the live tracker schema.
-- The API already derives `project` from the top-level parent; if this column exists and is non-empty the
-- API uses it instead. Numbered 002 per request; the in-code 002_people_link is a separate, local-only step.
ALTER TABLE items ADD COLUMN project TEXT DEFAULT '';
-- Backfill = top-level ancestor id (recursive CTE over parent_id).
WITH RECURSIVE up(id, cur) AS (
  SELECT id, id FROM items
  UNION ALL
  SELECT up.id, i.parent_id FROM up JOIN items i ON i.id = up.cur WHERE i.parent_id <> '' AND i.parent_id <> up.id
)
UPDATE items SET project = (
  SELECT u.cur FROM up u JOIN items p ON p.id = u.cur WHERE u.id = items.id AND p.parent_id = '' LIMIT 1);
-- A parentless item with no children is not a project (matches the API): clear it.
UPDATE items SET project = '' WHERE parent_id = '' AND NOT EXISTS (SELECT 1 FROM items k WHERE k.parent_id = items.id);
