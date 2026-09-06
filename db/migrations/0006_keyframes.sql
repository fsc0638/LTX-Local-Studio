-- D2: keyframes. One row per generated candidate, so a regeneration is a second row rather than
-- an overwrite and the review page can show what the first attempt looked like.
--
-- A keyframe that is approved becomes the shot's image_id. That id is a real asset (copied into
-- uploads/ with a sidecar), because everything downstream - i2v, references, the judge - resolves
-- image ids through the asset store and nothing else.
CREATE TABLE IF NOT EXISTS keyframes (
    id            uuid PRIMARY KEY,
    shot_id       uuid NOT NULL REFERENCES shots (id) ON DELETE CASCADE,
    job_id        text REFERENCES jobs (id) ON DELETE SET NULL,
    attempt       integer NOT NULL DEFAULT 1,
    seed          integer NOT NULL,
    -- The Bible reference the generation started from, chosen by directing.angle.
    reference_id  text,
    output_url    text,
    scores        jsonb,
    -- green / yellow / red from the consistency judge; null until scored.
    light         text CHECK (light IN ('green', 'yellow', 'red')),
    verdict       text NOT NULL DEFAULT 'pending'
                  CHECK (verdict IN ('pending', 'approved', 'rejected', 'failed')),
    -- Set on approval: the asset the keyframe was promoted to.
    asset_id      text,
    reason        text,
    created_at    double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS keyframes_shot_id_idx ON keyframes (shot_id, created_at DESC);
-- The batch run's state lives on the project: which shot it is on, when it started, how it ended.
ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS keyframe_run jsonb NOT NULL DEFAULT '{}'::jsonb;
