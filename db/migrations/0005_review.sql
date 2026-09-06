-- C3: the review page.
--
-- overridden_by / overridden_at record a person accepting a take the judge lit red. The verdict
-- alone says it happened; these say who and when, which is what an audit of "why is this in the
-- cut" needs. Both stay NULL for an ordinary acceptance.
--
-- opinion holds the VLM's one sentence about the take and, if the reviewer pressed "I disagree",
-- who did and when. It is kept on the take, not regenerated, because it was paid for once.
ALTER TABLE takes
    ADD COLUMN IF NOT EXISTS overridden_by text,
    ADD COLUMN IF NOT EXISTS overridden_at double precision,
    ADD COLUMN IF NOT EXISTS opinion jsonb;
