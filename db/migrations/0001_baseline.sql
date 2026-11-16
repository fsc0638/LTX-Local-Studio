-- Baseline: the SQLite schema of jobs.sqlite3 and accounts.sqlite3, in one PostgreSQL database.
--
-- Shapes are preserved on purpose so the stores keep returning what callers already expect:
--   * epoch seconds stay `double precision`, not timestamptz -- the app compares them as floats
--   * `disabled` stays an integer 0/1 rather than boolean, for the same reason
-- The one deliberate change is TEXT -> jsonb for job snapshots, which is what makes the
-- expression indexes below possible without SQLite's json_extract().

CREATE TABLE IF NOT EXISTS jobs (
    id              text PRIMARY KEY,
    snapshot        jsonb NOT NULL,
    updated_at      double precision NOT NULL,
    idempotency_key text UNIQUE,
    request_hash    text
);
CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs (updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_owner ON jobs ((snapshot ->> 'owner_id'), updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_filename ON jobs ((snapshot ->> 'filename'));

CREATE TABLE IF NOT EXISTS users (
    id            text PRIMARY KEY,
    name          text NOT NULL,
    username      text NOT NULL UNIQUE,
    email         text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    created_at    double precision NOT NULL,
    verified_at   double precision,
    disabled      integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash text PRIMARY KEY,
    user_id    text NOT NULL REFERENCES users (id),
    expires_at double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);

CREATE TABLE IF NOT EXISTS email_tokens (
    token_hash text PRIMARY KEY,
    user_id    text NOT NULL REFERENCES users (id),
    kind       text NOT NULL,
    created_at double precision NOT NULL,
    expires_at double precision NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens (user_id, kind);

CREATE TABLE IF NOT EXISTS rate_limits (
    scope      text PRIMARY KEY,
    count      integer NOT NULL,
    expires_at double precision NOT NULL
);

-- Enrollment history outlives the account: a dashboard removal is final and must never be
-- reconstructed from users, so there is no cascade here.
CREATE TABLE IF NOT EXISTS cloudflare_enrollments (
    email      text PRIMARY KEY,
    user_id    text NOT NULL UNIQUE,
    target     text NOT NULL,
    state      text NOT NULL CHECK (state IN ('pending', 'adding', 'synced', 'review')),
    last_error text NOT NULL DEFAULT '',
    created_at double precision NOT NULL,
    updated_at double precision NOT NULL
);
