"""Durable worker jobs. Creative assets and review decisions belong upstream."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import time

from psycopg.types.json import Jsonb

import database


FIELDS = ("id", "status", "progress", "phase", "created_at", "started_at", "finished_at",
          "filename", "output_url", "poster_url", "prompt", "width", "height", "frames", "fps",
          "seed", "mode", "image_id", "audio", "offload", "model", "device", "runtime_seconds",
          "size_bytes", "message", "provenance", "measured_media", "external", "requested_duration_seconds", "artifact_sha256",
          "profile", "image_strength", "timeout_seconds", "contract_version", "error", "quality_control", "cancel_requested", "owner_id",
          "parameters", "media_type", "content_type", "deleted_at", "aspect_ratio",
          "render_mode", "directing", "timeline", "segments", "segment_seconds", "duration_seconds", "source_geometry",
          "segment_index", "segment_count", "timeline_warnings")


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
    """Jobs in PostgreSQL. The schema is owned by db/migrations and applied once at API startup;
    a store that created its own tables would drift from that history."""

    def __init__(self, url=None):
        self.url = url or database.database_url()

    @contextmanager
    def connect(self):
        with database.connect(self.url) as db:
            yield db

    def record(self, job, *, key=None, request_hash=None, only_if_missing=False):
        if not isinstance(job, dict) or not re.fullmatch(r"[a-f0-9]{12,32}", str(job.get("id", ""))):
            raise ValueError("Invalid job ID")
        snapshot = {field: job[field] for field in FIELDS if field in job}
        now = job.get("finished_at") or job.get("created_at") or time.time()
        conflict = ("DO NOTHING" if only_if_missing else
                    "DO UPDATE SET snapshot=excluded.snapshot, updated_at=excluded.updated_at "
                    "WHERE jobs.snapshot->>'deleted_at' IS NULL")
        # Updates deliberately preserve the original idempotency key and hash.
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs(id,snapshot,updated_at,idempotency_key,request_hash) "
                f"VALUES(%s,%s,%s,%s,%s) ON CONFLICT(id) {conflict}",
                (job["id"], Jsonb(snapshot), now, key, request_hash))

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM jobs WHERE id=%s", (job_id,)).fetchone()
        return row["snapshot"] if row else None

    def by_key(self, key):
        with self.connect() as db:
            row = db.execute("SELECT snapshot,request_hash FROM jobs WHERE idempotency_key=%s", (key,)).fetchone()
        return (row["snapshot"], row["request_hash"]) if row else None

    def list_jobs(self, limit=30, offset=0, owner_id=None):
        if limit < 1 or limit > 100 or offset < 0:
            raise ValueError("Invalid pagination")
        with self.connect() as db:
            where = "WHERE snapshot->>'deleted_at' IS NULL"
            if owner_id:
                where += " AND snapshot->>'owner_id'=%s"
            values = (owner_id,) if owner_id else ()
            rows = db.execute(
                f"SELECT snapshot FROM jobs {where} ORDER BY updated_at DESC,id LIMIT %s OFFSET %s",
                (*values, limit, offset)).fetchall()
            total = db.execute(f"SELECT count(*) AS total FROM jobs {where}", values).fetchone()["total"]
        return {"jobs": [row["snapshot"] for row in rows], "total": total, "offset": offset, "limit": limit}

    def by_filename(self, filename):
        with self.connect() as db:
            row = db.execute("SELECT snapshot FROM jobs WHERE snapshot->>'filename'=%s", (filename,)).fetchone()
        return row["snapshot"] if row else None

    def recent_count(self, owner_id, since):
        with self.connect() as db:
            # created_at is a JSON number; ->> yields text, so cast before comparing.
            return db.execute(
                "SELECT count(*) AS total FROM jobs WHERE snapshot->>'owner_id'=%s "
                "AND (snapshot->>'created_at')::double precision >= %s",
                (owner_id, since)).fetchone()["total"]

    def recover(self, output_dir):
        # Import old metadata once. If an interrupted record has a completed
        # sidecar, repair its status without changing its idempotency mapping.
        for metadata in Path(output_dir).glob("*.json"):
            try:
                if metadata.is_symlink() or metadata.stat().st_size > 4 * 1024 * 1024:
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
                if previous and (previous.get("deleted_at") or previous.get("status") == "succeeded"):
                    continue
                job.setdefault("provenance", {"source": "legacy_output", "reproducibility": "incomplete"})
                job.update(progress=100, output_url=f"/generated/{filename}")
                if not re.fullmatch(r"/generated/[\w-]+\.(jpg|png)", str(job.get("poster_url", ""))):
                    job.pop("poster_url", None)
                self.record(job)
            except (OSError, ValueError, TypeError):
                continue
        with self.connect() as db:
            rows = db.execute("SELECT id,snapshot FROM jobs WHERE snapshot->>'status' IN ('running','queued')").fetchall()
            for row in rows:
                snapshot = dict(row["snapshot"])
                snapshot.update(status="interrupted", message="Worker restarted before completion; resubmit with a NEW idempotency key.",
                                error={"code": "worker_restarted", "retryable": True}, finished_at=time.time())
                db.execute("UPDATE jobs SET snapshot=%s,updated_at=%s WHERE id=%s",
                           (Jsonb(snapshot), time.time(), row["id"]))
