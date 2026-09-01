#!/usr/bin/env python3
"""Offline, recoverable cleanup of this service's explicitly scoped media only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from media_deletion import prepare_archive, regular_file


MEDIA_DIRS = (
    "data/worker/outputs", "data/worker/legacy-outputs",
    "data/worker/legacy-media", "data/worker/legacy-build-generated",
    "data/worker/legacy-build-media", "data/worker/work", "uploads",
    "outputs/worker-acceptance", "public/generated", "public/media",
)


def inventory(root):
    files, counts = [], {}
    for relative in MEDIA_DIRS:
        directory = root / relative
        if any(p.is_symlink() for p in (directory, *directory.parents)):
            raise ValueError("Refusing a symlinked media directory")
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise ValueError("Expected media directory")
        items = []
        for parent, directories, names in os.walk(directory, followlinks=False):
            if any((Path(parent) / name).is_symlink() for name in directories):
                raise ValueError("Refusing nested symlinked media directories")
            for name in sorted(names):
                if name == ".gitkeep":
                    continue
                path = Path(parent) / name
                if regular_file(path):
                    items.append(path)
        counts[relative] = {"files": len(items), "bytes": sum(p.stat().st_size for p in items)}
        files.extend(items)
    return files, counts


def clear(root, *, apply=False):
    root = Path(root).absolute()
    files, counts = inventory(root)
    result = {"applied": False, "directories": counts, "files": len(files),
              "bytes": sum(p.stat().st_size for p in files)}
    if not apply:
        return result
    state = root / "data/worker"
    database = state / "jobs.sqlite3"
    if not regular_file(database):
        raise ValueError("Existing jobs database required")
    lock_path = state / "instance.lock"
    if lock_path.exists() or lock_path.is_symlink():
        regular_file(lock_path)
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Stop the API first; its instance lock is held") from None
        db = sqlite3.connect(f"file:{database}?mode=rw", uri=True, timeout=10)
        try:
            active = db.execute("SELECT count(*) FROM jobs WHERE json_extract(snapshot,'$.status') IN ('queued','running')").fetchone()[0]
            if active:
                raise ValueError("Active jobs remain; finish/cancel them before cleanup")
            # Re-enumerate only after excluding all service writes.
            files, counts = inventory(root)
            pending = db.execute("SELECT count(*) FROM jobs WHERE json_extract(snapshot,'$.deleted_at') IS NULL").fetchone()[0]
            if not files and not pending:
                return {**result, "applied": True, "jobs_hidden": 0, "archive": None}
            archive = prepare_archive(files, state / "trash", {"kind": "bulk_cleanup", "directories": counts})
            backup_path = archive.directory / "jobs-before.sqlite3"
            backup = sqlite3.connect(backup_path)
            os.chmod(backup_path, 0o600)
            try:
                db.backup(backup)
            finally:
                backup.close()
            with backup_path.open("rb") as saved:
                os.fsync(saved.fileno())
            now = time.time()
            with db:
                db.execute("UPDATE jobs SET snapshot=json_set(snapshot,'$.deleted_at',?),updated_at=? WHERE json_extract(snapshot,'$.deleted_at') IS NULL", (now, now))
            # Tombstones deny downloads before any original paths are removed.
            archive.remove_sources()
            return {"applied": True, "directories": counts, "files": len(files),
                    "bytes": sum(p.stat().st_size for _, p in archive.entries),
                    "jobs_hidden": pending, "archive": str(archive.directory)}
        finally:
            db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Archive/remove media; requires stopped API. Default is inventory only.")
    args = parser.parse_args()
    try:
        print(json.dumps(clear(ROOT, apply=args.apply), ensure_ascii=False, indent=2))
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Cleanup stopped: {error}", file=sys.stderr)
        sys.exit(1)
