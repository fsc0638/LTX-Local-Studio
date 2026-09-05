"""Production factory projects, shots and takes.

The store speaks the v2 work order (lib/production-factory.ts): what it returns is what the
browser already knows how to render, and what it accepts is what the export format produces.

It orchestrates only. Nothing here talks to a model, a file path or a shell; sending a shot means
handing its request to the existing /api/v1 admission path, which is the sole route to the GPU.
"""
from contextlib import contextmanager
import datetime
import json
import time
import uuid

from psycopg.types.json import Jsonb

import database

FORMAT = "ltx-production-factory"
VERSION = 2
MAX_SHOTS = 100
MAX_TITLE = 120
MAX_PROMPT = 4000
MAX_REQUEST_CHARS = 128_000

RUN_STATES = ("draft", "running", "paused", "completed")
SHOT_STATES = ("draft", "queued", "validating", "submitting", "running", "succeeded", "failed")
# States the scheduler treats as "still ours to finish"; anything else needs a person.
ACTIVE_SHOT_STATES = ("queued", "validating", "submitting", "running")
VERDICTS = ("pending", "accepted", "rejected", "overridden")


class FactoryError(ValueError):
    """Rejected input. The HTTP layer turns this into a 400 with `code`."""

    def __init__(self, code, message=None):
        super().__init__(message or code)
        self.code = code


def _identifier(value, label):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise FactoryError("invalid_id", f"{label} must be a UUID") from None


def _title(value, fallback=None):
    if value is None and fallback is not None:
        return fallback
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TITLE:
        raise FactoryError("invalid_title", f"Titles must be 1-{MAX_TITLE} characters")
    return value.strip()


def _request(value):
    if not isinstance(value, dict):
        raise FactoryError("invalid_request", "Shot request must be a JSON object")
    prompt = value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise FactoryError("invalid_prompt", f"Every shot needs a prompt of 1-{MAX_PROMPT} characters")
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) > MAX_REQUEST_CHARS:
        raise FactoryError("request_too_large", f"A shot request cannot exceed {MAX_REQUEST_CHARS} characters")
    return json.loads(encoded)


def _pinned(value):
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise FactoryError("invalid_pinned", "pinned must be a list of field names")
    return sorted(set(value))


def _bible(value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise FactoryError("invalid_bible", "bible must be a JSON object")
    return value


def _iso(epoch):
    return datetime.datetime.fromtimestamp(epoch, datetime.UTC).isoformat().replace("+00:00", "Z")


def project_json(row, shots):
    """The v2 plan shape, camelCase, exactly as lib/production-factory.ts restores it.

    Every uuid is stringified here: psycopg returns uuid.UUID objects, which json.dumps refuses.
    """
    return {
        "format": FORMAT,
        "version": VERSION,
        "id": str(row["id"]),
        "title": row["title"],
        "bible": row["bible"],
        "status": row["status"],
        # ISO strings, not epoch numbers: the v2 work order A1 froze uses strings, and
        # restoreFactoryPlan drops anything else, so a number would silently lose the timestamp.
        "createdAt": _iso(row["created_at"]),
        "updatedAt": _iso(row["updated_at"]),
        "shots": shots,
    }


def shot_json(row, take=None):
    shot = {
        "id": str(row["id"]),
        "title": row["title"],
        "request": row["request"],
        "pinned": row["pinned"],
        "status": row["status"],
        "idempotencyKey": row["idempotency_key"],
        "progress": 100 if row["status"] == "succeeded" else 0,
    }
    if take:
        shot["jobId"] = take["job_id"]
        shot["outputUrl"] = take["output_url"]
        shot["posterUrl"] = take["poster_url"]
        if take["reason"]:
            shot["error"] = take["reason"]
    return shot


class FactoryStore:
    def __init__(self, url=None):
        self.url = url or database.database_url()

    @contextmanager
    def connect(self):
        with database.connect(self.url) as db:
            yield db

    # ---------- projects ----------

    def create_project(self, owner_id, raw):
        now = time.time()
        project_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO projects(id,owner_id,title,status,bible,created_at,updated_at) "
                       "VALUES(%s,%s,%s,'draft',%s,%s,%s)",
                       (project_id, owner_id, _title(raw.get("title"), "UNTITLED PRODUCTION"),
                        Jsonb(_bible(raw.get("bible"))), now, now))
        return self.get_project(project_id, owner_id)

    def list_projects(self, owner_id):
        with self.connect() as db:
            rows = db.execute("SELECT p.*, "
                              "(SELECT count(*) FROM shots s WHERE s.project_id=p.id) AS shot_count "
                              "FROM projects p WHERE p.owner_id=%s ORDER BY p.updated_at DESC",
                              (owner_id,)).fetchall()
        return [{"id": str(r["id"]), "title": r["title"], "status": r["status"],
                 "shots": r["shot_count"], "updatedAt": r["updated_at"]} for r in rows]

    def get_project(self, project_id, owner_id):
        project_id = _identifier(project_id, "project id")
        with self.connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=%s AND owner_id=%s",
                             (project_id, owner_id)).fetchone()
            if not row:
                return None
            shots = db.execute("SELECT * FROM shots WHERE project_id=%s ORDER BY position",
                               (project_id,)).fetchall()
            # The newest take per shot carries the output the UI shows.
            takes = db.execute(
                "SELECT DISTINCT ON (shot_id) * FROM takes WHERE shot_id = ANY(%s) "
                "ORDER BY shot_id, created_at DESC",
                ([s["id"] for s in shots],)).fetchall() if shots else []
        latest = {t["shot_id"]: t for t in takes}
        return project_json(row, [shot_json(s, latest.get(s["id"])) for s in shots])

    def update_project(self, project_id, owner_id, raw):
        project_id = _identifier(project_id, "project id")
        sets, values = [], []
        if "title" in raw:
            sets.append("title=%s"); values.append(_title(raw["title"]))
        if "bible" in raw:
            sets.append("bible=%s"); values.append(Jsonb(_bible(raw["bible"])))
        if "status" in raw:
            if raw["status"] not in RUN_STATES:
                raise FactoryError("invalid_status", f"status must be one of {', '.join(RUN_STATES)}")
            sets.append("status=%s"); values.append(raw["status"])
        if not sets:
            return self.get_project(project_id, owner_id)
        sets.append("updated_at=%s"); values.append(time.time())
        with self.connect() as db:
            changed = db.execute(f"UPDATE projects SET {','.join(sets)} WHERE id=%s AND owner_id=%s",
                                 (*values, project_id, owner_id)).rowcount
        return self.get_project(project_id, owner_id) if changed else None

    def delete_project(self, project_id, owner_id):
        project_id = _identifier(project_id, "project id")
        with self.connect() as db:
            return db.execute("DELETE FROM projects WHERE id=%s AND owner_id=%s",
                              (project_id, owner_id)).rowcount > 0

    # ---------- shots ----------

    def replace_shots(self, project_id, owner_id, raw_shots):
        """Write the whole shot list at once. The browser edits a plan as a unit -- reordering,
        merging, splitting -- so one atomic replace beats a stream of per-shot patches that could
        leave the positions inconsistent halfway through."""
        project_id = _identifier(project_id, "project id")
        if not isinstance(raw_shots, list):
            raise FactoryError("invalid_shots", "shots must be a list")
        if len(raw_shots) > MAX_SHOTS:
            raise FactoryError("too_many_shots", f"A project holds at most {MAX_SHOTS} shots")
        now = time.time()
        prepared = []
        for index, raw in enumerate(raw_shots):
            if not isinstance(raw, dict):
                raise FactoryError("invalid_shots", "Each shot must be a JSON object")
            shot_id = str(uuid.uuid4()) if not raw.get("id") else _identifier(raw["id"], "shot id")
            prepared.append((shot_id, project_id, index,
                             _title(raw.get("title"), f"SHOT {index + 1:02d}"),
                             Jsonb(_request(raw.get("request"))), Jsonb(_pinned(raw.get("pinned"))),
                             raw.get("status") if raw.get("status") in SHOT_STATES else "draft",
                             raw.get("idempotencyKey") or f"factory-{shot_id}", now, now))
        with self.connect() as db:
            owned = db.execute("SELECT 1 FROM projects WHERE id=%s AND owner_id=%s",
                               (project_id, owner_id)).fetchone()
            if not owned:
                return None
            # Replace inside one transaction: a half-written list would leave gaps in position.
            db.execute("DELETE FROM shots WHERE project_id=%s", (project_id,))
            if prepared:
                with db.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO shots(id,project_id,position,title,request,pinned,status,"
                        "idempotency_key,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        prepared)
            db.execute("UPDATE projects SET updated_at=%s WHERE id=%s", (now, project_id))
        return self.get_project(project_id, owner_id)

    def next_queued_shot(self, project_id):
        """The next shot to send, locked so two scheduler passes cannot claim the same one."""
        with self.connect() as db:
            row = db.execute(
                "SELECT s.* FROM shots s JOIN projects p ON p.id=s.project_id "
                "WHERE s.project_id=%s AND p.status='running' AND s.status='queued' "
                "ORDER BY s.position LIMIT 1 FOR UPDATE OF s SKIP LOCKED",
                (project_id,)).fetchone()
            return dict(row) if row else None

    def running_projects(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM projects WHERE status='running' ORDER BY updated_at").fetchall()]

    def set_shot_status(self, shot_id, status, *, reason=None, pause_project=False):
        """Move a shot, and optionally stop the line, in one transaction: a shot recorded as failed
        while its project still reads 'running' would have the scheduler send the next one."""
        if status not in SHOT_STATES:
            raise FactoryError("invalid_status", f"status must be one of {', '.join(SHOT_STATES)}")
        now = time.time()
        with self.connect() as db:
            row = db.execute("UPDATE shots SET status=%s,updated_at=%s WHERE id=%s "
                             "RETURNING project_id", (status, now, shot_id)).fetchone()
            if not row:
                return None
            if pause_project:
                db.execute("UPDATE projects SET status='paused',updated_at=%s WHERE id=%s",
                           (now, row["project_id"]))
            if reason is not None:
                db.execute("UPDATE takes SET reason=%s WHERE shot_id=%s AND created_at="
                           "(SELECT max(created_at) FROM takes WHERE shot_id=%s)",
                           (reason, shot_id, shot_id))
            return row["project_id"]

    def record_take(self, shot_id, *, job_id=None, status, output_url=None, poster_url=None,
                    reason=None, pause_project=False):
        """Shot state, take and job link written together, as the work order requires."""
        if status not in SHOT_STATES:
            raise FactoryError("invalid_status", f"status must be one of {', '.join(SHOT_STATES)}")
        now = time.time()
        with self.connect() as db:
            row = db.execute("UPDATE shots SET status=%s,updated_at=%s WHERE id=%s "
                             "RETURNING project_id", (status, now, shot_id)).fetchone()
            if not row:
                return None
            existing = db.execute("SELECT id FROM takes WHERE shot_id=%s AND job_id=%s",
                                  (shot_id, job_id)).fetchone() if job_id else None
            if existing:
                db.execute("UPDATE takes SET output_url=%s,poster_url=%s,reason=%s WHERE id=%s",
                           (output_url, poster_url, reason, existing["id"]))
            else:
                db.execute("INSERT INTO takes(id,shot_id,job_id,output_url,poster_url,reason,created_at) "
                           "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                           (str(uuid.uuid4()), shot_id, job_id, output_url, poster_url, reason, now))
            if pause_project:
                db.execute("UPDATE projects SET status='paused',updated_at=%s WHERE id=%s",
                           (now, row["project_id"]))
            return row["project_id"]

    def takes(self, shot_id, owner_id):
        shot_id = _identifier(shot_id, "shot id")
        with self.connect() as db:
            owned = db.execute("SELECT 1 FROM shots s JOIN projects p ON p.id=s.project_id "
                               "WHERE s.id=%s AND p.owner_id=%s", (shot_id, owner_id)).fetchone()
            if not owned:
                return None
            rows = db.execute("SELECT * FROM takes WHERE shot_id=%s ORDER BY created_at DESC",
                              (shot_id,)).fetchall()
        return [{"id": str(r["id"]), "jobId": r["job_id"], "outputUrl": r["output_url"],
                 "posterUrl": r["poster_url"], "scores": r["scores"], "verdict": r["verdict"],
                 "reason": r["reason"], "createdAt": r["created_at"]} for r in rows]

    # ---------- run control ----------

    def start(self, project_id, owner_id):
        """Queue every shot that still needs work and set the line running."""
        project_id = _identifier(project_id, "project id")
        now = time.time()
        with self.connect() as db:
            owned = db.execute("SELECT 1 FROM projects WHERE id=%s AND owner_id=%s",
                               (project_id, owner_id)).fetchone()
            if not owned:
                return None
            db.execute("UPDATE shots SET status='queued',updated_at=%s "
                       "WHERE project_id=%s AND status IN ('draft','failed')", (now, project_id))
            db.execute("UPDATE projects SET status='running',updated_at=%s WHERE id=%s",
                       (now, project_id))
        return self.get_project(project_id, owner_id)

    def pause(self, project_id, owner_id=None):
        """Stop feeding the line. A shot already on the GPU is deliberately left alone: pausing
        must not throw away work that is nearly done."""
        project_id = _identifier(project_id, "project id")
        now = time.time()
        with self.connect() as db:
            clause = "AND owner_id=%s" if owner_id else ""
            values = (now, project_id, owner_id) if owner_id else (now, project_id)
            changed = db.execute(f"UPDATE projects SET status='paused',updated_at=%s "
                                 f"WHERE id=%s {clause}", values).rowcount
            if not changed:
                return None
            db.execute("UPDATE shots SET status='draft',updated_at=%s "
                       "WHERE project_id=%s AND status='queued'", (now, project_id))
        return self.get_project(project_id, owner_id) if owner_id else True

    def finish_if_done(self, project_id):
        """Mark a running project completed once nothing is left to send."""
        with self.connect() as db:
            remaining = db.execute(
                "SELECT count(*) AS total FROM shots WHERE project_id=%s AND status = ANY(%s)",
                (project_id, list(ACTIVE_SHOT_STATES))).fetchone()["total"]
            if remaining:
                return False
            db.execute("UPDATE projects SET status='completed',updated_at=%s "
                       "WHERE id=%s AND status='running'", (time.time(), project_id))
        return True

    def queued_count(self, owner_id):
        with self.connect() as db:
            return db.execute(
                "SELECT count(*) AS total FROM shots s JOIN projects p ON p.id=s.project_id "
                "WHERE p.owner_id=%s AND s.status = ANY(%s)",
                (owner_id, list(ACTIVE_SHOT_STATES))).fetchone()["total"]

    def recover(self):
        """After a restart, no shot can still be mid-flight in this process. Anything left in a
        transient state is put back in the queue so the scheduler picks it up; the idempotency key
        is unchanged, so a job that did reach the worker is replayed, not duplicated."""
        with self.connect() as db:
            return db.execute(
                "UPDATE shots SET status='queued',updated_at=%s "
                "WHERE status IN ('validating','submitting','running')",
                (time.time(),)).rowcount
