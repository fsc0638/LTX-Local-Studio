"""Durable worker jobs. Creative assets and review decisions belong upstream."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time


FIELDS = ("id", "status", "progress", "phase", "created_at", "started_at", "finished_at",
          "filename", "output_url", "poster_url", "prompt", "width", "height", "frames", "fps",
          "seed", "mode", "image_id", "audio", "offload", "model", "device", "runtime_seconds",
          "size_bytes", "message", "provenance", "measured_media", "external", "requested_duration_seconds", "artifact_sha256",
          "profile", "image_strength", "timeout_seconds", "contract_version", "error", "quality_control", "cancel_requested", "owner_id",
          "parameters", "media_type", "content_type")


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def file_fingerprint(path, digest=False):
    path = Path(path)
    if not path.is_file():
        return {"file": path.name, "missing": True}
    stat = path.stat()
    result = {"file": path.name, "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
              "identity_method": "stat_only"}
    if digest:
        checksum = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                checksum.update(chunk)
        result.update(sha256=checksum.hexdigest(), identity_method="sha256")
    return result


class ProductionStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, updated_at REAL NOT NULL,
                idempotency_key TEXT UNIQUE, request_hash TEXT)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_owner ON jobs(json_extract(snapshot,'$.owner_id'),updated_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_filename ON jobs(json_extract(snapshot,'$.filename'))")
            db.execute("PRAGMA optimize")
            db.execute("PRAGMA user_version=1")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, job, *, key=None, request_hash=None, only_if_missing=False):
        if not isinstance(job, dict) or not re.fullmatch(r"[a-f0-9]{12,32}", str(job.get("id", ""))):
            raise ValueError("Invalid job ID")
        snapshot = {field: job[field] for field in FIELDS if field in job}
        now = job.get("finished_at") or job.get("created_at") or time.time()
        conflict = "DO NOTHING" if only_if_missing else "DO UPDATE SET snapshot=excluded.snapshot, updated_at=excluded.updated_at"
        # Updates deliberately preserve the original idempotency key and hash.
        with self.connect() as db:
            db.execute(f"INSERT INTO jobs(id,snapshot,updated_at,idempotency_key,request_hash) VALUES(?,?,?,?,?) ON CONFLICT(id) {conflict}",
                       (job["id"], encode(snapshot), now, key, request_hash))

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM jobs WHERE id=?", (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def by_key(self, key):
        with self.connect() as db:
            row = db.execute("SELECT snapshot,request_hash FROM jobs WHERE idempotency_key=?", (key,)).fetchone()
        return (json.loads(row[0]), row[1]) if row else None

    def list_jobs(self, limit=30, offset=0, owner_id=None):
        if limit < 1 or limit > 100 or offset < 0:
            raise ValueError("Invalid pagination")
        with self.connect() as db:
            where = "WHERE json_extract(snapshot,'$.owner_id')=?" if owner_id else ""
            values = (owner_id,) if owner_id else ()
            rows = db.execute(f"SELECT snapshot FROM jobs {where} ORDER BY updated_at DESC,id LIMIT ? OFFSET ?", (*values, limit, offset)).fetchall()
            total = db.execute(f"SELECT count(*) FROM jobs {where}", values).fetchone()[0]
        return {"jobs": [json.loads(row[0]) for row in rows], "total": total, "offset": offset, "limit": limit}

    def by_filename(self, filename):
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM jobs WHERE json_extract(snapshot,'$.filename')=?", (filename,)).fetchone()
        return json.loads(row[0]) if row else None

    def recent_count(self, owner_id, since):
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM jobs WHERE json_extract(snapshot,'$.owner_id')=? AND json_extract(snapshot,'$.created_at')>=?", (owner_id, since)).fetchone()[0]

    def recover(self, output_dir):
        # Import old metadata once. If an interrupted record has a completed
        # sidecar, repair its status without changing its idempotency mapping.
        for metadata in Path(output_dir).glob("*.json"):
            try:
                if metadata.is_symlink() or metadata.stat().st_size > 128_000:
                    continue
                job = json.loads(metadata.read_text(encoding="utf-8"))
                if not isinstance(job, dict) or job.get("status") != "succeeded":
                    continue
                filename = job.get("filename", "")
                if not re.fullmatch(r"[A-Za-z0-9_-]+\.(mp4|png|txt)", filename):
                    continue
                video = Path(output_dir) / filename
                if video.is_symlink() or not video.is_file():
                    continue
                previous = self.get(job.get("id", ""))
                if previous and previous.get("status") == "succeeded":
                    continue
                job.setdefault("provenance", {"source": "legacy_output", "reproducibility": "incomplete"})
                job.update(progress=100, output_url=f"/generated/{filename}")
                if not re.fullmatch(r"/generated/[\w-]+\.(jpg|png)", str(job.get("poster_url", ""))):
                    job.pop("poster_url", None)
                self.record(job)
            except (OSError, ValueError, TypeError):
                continue
        with self.connect() as db:
            rows = db.execute("SELECT id,snapshot FROM jobs WHERE json_extract(snapshot,'$.status') IN ('running','queued')").fetchall()
            for row in rows:
                snapshot = json.loads(row["snapshot"])
                snapshot.update(status="interrupted", message="Worker restarted before completion; resubmit with a NEW idempotency key.",
                                error={"code": "worker_restarted", "retryable": True}, finished_at=time.time())
                db.execute("UPDATE jobs SET snapshot=?,updated_at=? WHERE id=?", (encode(snapshot), time.time(), row["id"]))
