-- D3: a take can be a post version of another take. The op, its parameters and the source are
-- kept on the row so the review page can say "upscaled x2 from take 3" instead of showing two
-- takes that look alike for no visible reason.
ALTER TABLE takes
    ADD COLUMN IF NOT EXISTS post jsonb;
