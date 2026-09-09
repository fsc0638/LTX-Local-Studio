-- D5: the state of a project's cut - which job holds it, when it ran, how it ended - lives on the
-- project, like the keyframe run. The cut itself is an ordinary job in the job store, so the
-- existing serving, deletion and provenance apply to it unchanged.
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS assembly jsonb NOT NULL DEFAULT '{}'::jsonb;
