"""PostgreSQL connection settings and the migration runner.

The DSN comes from the environment and there is no SQLite fallback: a host that has not been
migrated must fail loudly at startup rather than quietly write to a second, divergent store.
"""
from contextlib import contextmanager
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = Path(__file__).resolve().parent / "db" / "migrations"


def database_url(variable="LTX_DATABASE_URL"):
    url = os.environ.get(variable, "").strip()
    if not url:
        raise RuntimeError(
            f"{variable} is required. PostgreSQL replaced the SQLite stores; "
            "see docs/PRODUCTION_ROADMAP.md (B0) for the host setup."
        )
    if not url.startswith("postgres"):
        raise RuntimeError(f"{variable} must be a PostgreSQL URL, got {url.split(':', 1)[0]!r}")
    return url


@contextmanager
def connect(url=None, autocommit=False):
    """A connection whose rows are dicts, so callers index by column name as they did with
    sqlite3.Row. Commits on a clean exit, rolls back on an exception."""
    with psycopg.connect(url or database_url(), row_factory=dict_row, autocommit=autocommit) as db:
        yield db


def migration_files():
    return sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))


def apply_migrations(url=None):
    """Apply every migration not yet recorded, each in its own transaction. Returns the names
    applied. Safe to call on every start: it is the only thing that changes the schema."""
    applied = []
    with connect(url) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        db.commit()
        known = {row["name"] for row in db.execute("SELECT name FROM schema_migrations")}
        for path in migration_files():
            if path.name in known:
                continue
            # One transaction per migration: a failure leaves the earlier ones applied and
            # recorded, so a rerun resumes instead of starting over.
            db.execute(path.read_text(encoding="utf-8"))
            db.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
            db.commit()
            applied.append(path.name)
    return applied
