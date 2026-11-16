-- Production factory: projects, their shots, and the takes each shot produced.
--
-- Until now a plan lived in one browser's localStorage, so closing the tab stopped the line.
-- These tables move it to the host; the browser becomes a client.
--
-- Shapes follow the v2 work order (lib/production-factory.ts): bible, request and pinned are the
-- same JSON the export format carries, so a plan can round-trip through the API unchanged.

CREATE TABLE IF NOT EXISTS projects (
    id         uuid PRIMARY KEY,
    owner_id   text NOT NULL,
    title      text NOT NULL,
    -- Mirrors FactoryRunState in lib/production-factory.ts.
    status     text NOT NULL DEFAULT 'draft'
               CHECK (status IN ('draft', 'running', 'paused', 'completed')),
    bible      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at double precision NOT NULL,
    updated_at double precision NOT NULL
);
-- The owner is the tenant boundary; every listing filters on it.
CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects (owner_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS shots (
    id              uuid PRIMARY KEY,
    -- Deleting a project takes its shots and, through them, its takes.
    project_id      uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    position        integer NOT NULL,
    title           text NOT NULL,
    request         jsonb NOT NULL,
    -- Fields the user overrode by hand; reprojecting the Bible must skip them.
    pinned          jsonb NOT NULL DEFAULT '[]'::jsonb,
    status          text NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'queued', 'validating', 'submitting',
                                      'running', 'succeeded', 'failed')),
    -- Unique across the whole table: the key is what stops a retry from burning a second GPU run.
    idempotency_key text NOT NULL UNIQUE,
    created_at      double precision NOT NULL,
    updated_at      double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shots_project ON shots (project_id, position);
-- The scheduler asks for the next shot to send; this keeps that lookup off a sequential scan.
CREATE INDEX IF NOT EXISTS idx_shots_status ON shots (status, project_id);

CREATE TABLE IF NOT EXISTS takes (
    id         uuid PRIMARY KEY,
    shot_id    uuid NOT NULL REFERENCES shots (id) ON DELETE CASCADE,
    -- A real foreign key into the job store, which is why both live in one database. Deleting a
    -- job through the recoverable-media path clears the link without discarding the take.
    job_id     text REFERENCES jobs (id) ON DELETE SET NULL,
    output_url text,
    poster_url text,
    -- Written by the judges in phase C; null until then.
    scores     jsonb,
    verdict    text NOT NULL DEFAULT 'pending'
               CHECK (verdict IN ('pending', 'accepted', 'rejected', 'overridden')),
    reason     text,
    created_at double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_takes_shot ON takes (shot_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_takes_job ON takes (job_id);
