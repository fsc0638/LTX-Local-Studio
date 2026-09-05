"""Test database wiring.

The stores used to isolate themselves by writing to a per-test SQLite file. With one PostgreSQL
database that isolation has to come from somewhere else, and it cannot be a shared transaction:
BackendTests starts a ThreadingHTTPServer, so request handlers touch the stores from other
threads. A psycopg connection is not safe to drive concurrently, and nesting transactions across
those threads fails with OutOfOrderTransactionNesting.

So each test starts from an empty database instead: one TRUNCATE of every table in setUp. Stores
keep opening their own connections exactly as they do in production, which also means the tests
exercise the real connection path rather than a patched one.

The name follows pytest's convention, but nothing here depends on pytest: the suite runs under
`python3 -m unittest discover`, so tests import this module explicitly.

Requires LTX_TEST_DATABASE_URL, for example:

    LTX_TEST_DATABASE_URL=postgresql:///ltx_studio_test?host=/var/run/postgresql \
        PYTHONPATH=tests python3 -m unittest discover -s tests -p 'test_*.py'
"""
import os
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database

TEST_URL_VARIABLE = "LTX_TEST_DATABASE_URL"

# Every table the baseline migration owns. schema_migrations is deliberately absent: wiping it
# would make the next connection re-run the migrations.
TABLES = ("sessions", "email_tokens", "cloudflare_enrollments", "rate_limits", "users", "jobs")

_ready = False


def test_database_url():
    url = os.environ.get(TEST_URL_VARIABLE, "").strip()
    if not url:
        raise RuntimeError(
            f"{TEST_URL_VARIABLE} is required to run the suite. Point it at a throwaway database: "
            "every test truncates every table in it."
        )
    # Parse rather than split on '/': the DSN carries host=/var/run/postgresql in its query.
    name = urlsplit(url).path.lstrip("/")
    if "test" not in name:
        raise RuntimeError(
            f"Refusing to run against database {name!r}: its name must contain 'test'. "
            "The suite truncates every table."
        )
    return url


def prepare():
    """Apply migrations once per process, then hand back the URL."""
    global _ready
    url = test_database_url()
    if not _ready:
        database.apply_migrations(url)
        _ready = True
    return url


def reset(url):
    # One statement so foreign keys never dictate the order.
    with database.connect(url) as db:
        db.execute("TRUNCATE " + ", ".join(TABLES) + " CASCADE")


class DatabaseFixture:
    """Mixin for unittest.TestCase. Call `self.start_database()` first thing in setUp."""

    def start_database(self):
        url = prepare()
        # Stores built with no argument read this, so a test never depends on the caller having
        # exported LTX_DATABASE_URL as well.
        patcher = patch.object(database, "database_url", lambda variable="LTX_DATABASE_URL": url)
        patcher.start()
        self.addCleanup(patcher.stop)
        reset(url)
        self.database_url = url
