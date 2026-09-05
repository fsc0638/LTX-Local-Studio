#!/usr/bin/env python3
"""One-way import of the legacy SQLite stores into PostgreSQL.

Reads jobs.sqlite3 and accounts.sqlite3, writes them into the database named by
LTX_DATABASE_URL, then compares row counts table by table and prints a report.

It never deletes or edits the SQLite files: they stay as the rollback. Nothing here decides when
production switches over -- that is a separate, human decision about restarting ltx-api with
LTX_DATABASE_URL set.

    # look, change nothing
    LTX_DATABASE_URL=postgresql:///ltx_studio?host=/var/run/postgresql \\
        python3 scripts/migrate-sqlite-to-postgres.py --dry-run

    # import (the API must be stopped: its instance lock is checked)
    LTX_DATABASE_URL=postgresql:///ltx_studio?host=/var/run/postgresql \\
        python3 scripts/migrate-sqlite-to-postgres.py
"""
import argparse
import fcntl
import json
from pathlib import Path
import sqlite3
import sys

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import database

# (sqlite file, table, columns). Order matters: users before anything referencing it.
PLAN = (
    ("jobs.sqlite3", "jobs", ("id", "snapshot", "updated_at", "idempotency_key", "request_hash")),
    ("accounts.sqlite3", "users",
     ("id", "name", "username", "email", "password_hash", "created_at", "verified_at", "disabled")),
    ("accounts.sqlite3", "sessions", ("token_hash", "user_id", "expires_at")),
    ("accounts.sqlite3", "email_tokens", ("token_hash", "user_id", "kind", "created_at", "expires_at")),
    ("accounts.sqlite3", "rate_limits", ("scope", "count", "expires_at")),
    ("accounts.sqlite3", "cloudflare_enrollments",
     ("email", "user_id", "target", "state", "last_error", "created_at", "updated_at")),
)

# jobs.snapshot is TEXT in SQLite and jsonb in PostgreSQL; every other column carries across as is.
JSON_COLUMNS = {("jobs", "snapshot")}


def source_rows(state, filename, table, columns):
    path = state / filename
    if not path.is_file():
        raise SystemExit(f"Missing source database: {path}")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    try:
        db.row_factory = sqlite3.Row
        return [tuple(row[column] for column in columns)
                for row in db.execute(f"SELECT {','.join(columns)} FROM {table}")]
    finally:
        db.close()


def adapt(table, columns, row):
    return tuple(Jsonb(json.loads(value)) if (table, column) in JSON_COLUMNS and value is not None else value
                 for column, value in zip(columns, row))


def migrate(root, *, apply=False):
    state = Path(root) / "data/worker"
    url = database.database_url()

    if apply:
        # The API holds this lock while running; importing under a live writer would race with it.
        lock_path = state / "instance.lock"
        with lock_path.open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SystemExit("Stop ltx-api first; its instance lock is held.") from None
            return _import(state, url, apply=True)
    return _import(state, url, apply=False)


def _import(state, url, *, apply):
    database.apply_migrations(url)
    report = {"applied": apply, "database": url, "tables": [], "mismatches": []}
    with database.connect(url) as db:
        for filename, table, columns in PLAN:
            rows = source_rows(state, filename, table, columns)
            before = db.execute(f"SELECT count(*) AS total FROM {table}").fetchone()["total"]
            if apply and rows:
                # ON CONFLICT DO NOTHING makes a rerun safe: an interrupted import resumes
                # instead of failing on the rows it already wrote.
                placeholders = ",".join(["%s"] * len(columns))
                with db.cursor() as cursor:  # executemany lives on the cursor in psycopg 3
                    cursor.executemany(
                        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders}) "
                        "ON CONFLICT DO NOTHING",
                        [adapt(table, columns, row) for row in rows])
            after = db.execute(f"SELECT count(*) AS total FROM {table}").fetchone()["total"]
            entry = {"table": table, "sqlite": len(rows), "postgres_before": before,
                     "postgres_after": after}
            report["tables"].append(entry)
            # After a real import every source row must be present. Extra rows are fine: the
            # target may already hold records SQLite never had.
            if apply and after < len(rows):
                report["mismatches"].append(
                    f"{table}: {len(rows)} rows in SQLite but only {after} in PostgreSQL")
    report["ok"] = not report["mismatches"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true",
                        help="Count both sides and report; write nothing. This is the default.")
    parser.add_argument("--apply", action="store_true",
                        help="Import the rows. Requires ltx-api to be stopped.")
    args = parser.parse_args()
    if args.dry_run and args.apply:
        raise SystemExit("--dry-run and --apply are mutually exclusive.")
    try:
        result = migrate(ROOT, apply=args.apply)
    except (OSError, ValueError, psycopg.Error, sqlite3.Error) as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["ok"]:
        sys.exit(1)
    if not result["applied"]:
        print("\nNothing was written. Re-run with --apply once ltx-api is stopped.", file=sys.stderr)
