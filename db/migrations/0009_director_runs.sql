-- Whole-song director analysis can outlive an HTTP request.  Keep its state and completed
-- result on the project so a browser refresh or tunnel timeout cannot lose paid model work.
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS director_run jsonb NOT NULL DEFAULT '{}'::jsonb;
