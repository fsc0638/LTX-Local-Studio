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

import review_rules

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


def _keyframe_json(r):
    return {"id": str(r["id"]), "shotId": str(r["shot_id"]), "jobId": r["job_id"],
            "attempt": r["attempt"], "seed": r["seed"], "referenceId": r["reference_id"],
            "outputUrl": r["output_url"], "scores": r["scores"], "light": r["light"],
            "verdict": r["verdict"], "assetId": r["asset_id"], "reason": r["reason"],
            "createdAt": r["created_at"]}


def _take_json(r):
    return {"id": str(r["id"]), "shotId": str(r["shot_id"]), "jobId": r["job_id"],
            "outputUrl": r["output_url"], "posterUrl": r["poster_url"], "scores": r["scores"],
            "verdict": r["verdict"], "reason": r["reason"], "createdAt": r["created_at"],
            "deletedAt": r["deleted_at"], "overriddenBy": r.get("overridden_by"),
            "overriddenAt": r.get("overridden_at"), "opinion": r.get("opinion"),
            "post": r.get("post")}


def shot_json(row, take=None):
    shot = {
        "id": str(row["id"]),
        "title": row["title"],
        "request": row["request"],
        "pinned": row["pinned"],
        "status": row["status"],
        "idempotencyKey": row["idempotency_key"],
        "progress": 100 if row["status"] == "succeeded" else 0,
        "acceptedTakeId": str(row["accepted_take_id"]) if row.get("accepted_take_id") else None,
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
                "AND deleted_at IS NULL ORDER BY shot_id, created_at DESC",
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
        ids = [item[0] for item in prepared]
        if len(set(ids)) != len(ids):
            raise FactoryError("invalid_shots", "A shot id appears twice")
        with self.connect() as db:
            owned = db.execute("SELECT 1 FROM projects WHERE id=%s AND owner_id=%s",
                               (project_id, owner_id)).fetchone()
            if not owned:
                return None
            # An id that already belongs to another project is refused, not adopted: the upsert
            # below would otherwise move that shot - and its takes - across projects.
            foreign = db.execute("SELECT 1 FROM shots WHERE id = ANY(%s) AND project_id <> %s",
                                 (ids, project_id)).fetchone() if ids else None
            if foreign:
                raise FactoryError("invalid_shots", "A shot id belongs to another project")
            # Update in place and delete only what the client dropped. Takes cascade from shots,
            # so a delete-and-reinsert here silently threw away every take on every edit; the
            # verdicts and accepted takes of C2 have to outlive a reorder.
            db.execute("DELETE FROM shots WHERE project_id=%s AND NOT (id = ANY(%s))",
                       (project_id, ids or ["00000000-0000-0000-0000-000000000000"]))
            if prepared:
                with db.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO shots(id,project_id,position,title,request,pinned,status,"
                        "idempotency_key,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (id) DO UPDATE SET position=excluded.position, "
                        "title=excluded.title, request=excluded.request, pinned=excluded.pinned, "
                        "status=excluded.status, idempotency_key=excluded.idempotency_key, "
                        "updated_at=excluded.updated_at",
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

    def next_queued_shot_for(self, project_id, models):
        """The next queued shot whose model is one of `models`, in position order; None if none.

        This is what lets the scheduler keep the GPU on one station inside a plan that mixes
        keyframes and shots, instead of following the plan's order and switching at every step.
        """
        if not models:
            return None
        with self.connect() as db:
            row = db.execute(
                "SELECT s.* FROM shots s JOIN projects p ON p.id=s.project_id "
                "WHERE s.project_id=%s AND p.status='running' AND s.status='queued' "
                "AND COALESCE(s.request->>'model','ltx23-distilled') = ANY(%s) "
                "ORDER BY s.position LIMIT 1 FOR UPDATE OF s SKIP LOCKED",
                (project_id, list(models))).fetchone()
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

    def judge_context(self, shot_id):
        """The Bible behind a shot, for the server's own scoring pass.

        No owner argument, like set_shot_status and record_take: this is reached from the
        scheduler after a job the host itself ran, never from a request.
        """
        with self.connect() as db:
            return db.execute(
                """SELECT s.id AS shot_id, s.project_id, p.bible
                     FROM shots s JOIN projects p ON p.id = s.project_id
                    WHERE s.id = %s""", (shot_id,)).fetchone()

    def record_scores(self, shot_id, job_id, scores):
        """Attach judge numbers to a take that already exists.

        Separate from record_take because scoring happens after the take is final and takes far
        longer than recording it: the queue must not wait on a model. A take with scores NULL has
        not been scored yet; one holding {"status": "unscored"} was tried and could not be.
        """
        with self.connect() as db:
            row = db.execute(
                "UPDATE takes SET scores=%s WHERE shot_id=%s AND job_id=%s RETURNING id",
                (Jsonb(scores), shot_id, job_id)).fetchone()
        return row["id"] if row else None

    def rotate_key(self, shot_id):
        """Give a shot a fresh idempotency key so its next run is a new take.

        The worker replays a finished key rather than running it again, which is exactly what
        should happen for a retry of the *same* attempt. A new attempt therefore needs a new key,
        as docs/WORKER_API.md says: "新 take 使用新 key".
        """
        new_key = f"factory-{shot_id}-{uuid.uuid4().hex[:8]}"
        with self.connect() as db:
            db.execute("UPDATE shots SET idempotency_key=%s,updated_at=%s WHERE id=%s",
                       (new_key, time.time(), shot_id))
        return new_key

    def draft_context(self, shot_id, owner_id):
        """Everything the screenwriting draft is allowed to see, in one owner-checked read.

        The neighbours matter as much as the shot: a draft written without them repeats the
        previous shot's framing, which is exactly the thing a human would notice and rewrite.
        """
        with self.connect() as db:
            row = db.execute(
                """SELECT s.id, s.title, s.request, s.pinned, s.position, s.project_id,
                          p.bible, p.title AS project_title, p.draft_usage
                     FROM shots s JOIN projects p ON p.id = s.project_id
                    WHERE s.id = %s AND p.owner_id = %s""",
                (shot_id, owner_id)).fetchone()
            if row is None:
                return None
            neighbours = db.execute(
                """SELECT position, title, request FROM shots
                    WHERE project_id = %s AND position IN (%s, %s)
                    ORDER BY position""",
                (row["project_id"], row["position"] - 1, row["position"] + 1)).fetchall()
        before = next((n for n in neighbours if n["position"] < row["position"]), None)
        after = next((n for n in neighbours if n["position"] > row["position"]), None)
        return {"shot": row, "previous": before, "next": after,
                "bible": row["bible"] or {}, "usage": row["draft_usage"] or {}}

    def draft_context_usage(self, project_id):
        with self.connect() as db:
            row = db.execute("SELECT draft_usage FROM projects WHERE id=%s", (project_id,)).fetchone()
        return (row or {}).get("draft_usage") or {}

    def add_draft_usage(self, project_id, tokens):
        """Add a call's tokens to the project's running total and return the new total.

        Written with jsonb arithmetic in one statement so two drafts started at once cannot both
        read the old total and write back the same number - the cap would then never be reached.
        """
        with self.connect() as db:
            row = db.execute(
                """UPDATE projects
                      SET draft_usage = jsonb_build_object(
                            'total_tokens', COALESCE((draft_usage->>'total_tokens')::bigint, 0) + %s,
                            'calls', COALESCE((draft_usage->>'calls')::bigint, 0) + 1),
                          updated_at = %s
                    WHERE id = %s
                RETURNING draft_usage""",
                (int(tokens), time.time(), project_id)).fetchone()
        return (row or {}).get("draft_usage") or {}

    def takes(self, shot_id, owner_id):
        shot_id = _identifier(shot_id, "shot id")
        with self.connect() as db:
            owned = db.execute("SELECT 1 FROM shots s JOIN projects p ON p.id=s.project_id "
                               "WHERE s.id=%s AND p.owner_id=%s", (shot_id, owner_id)).fetchone()
            if not owned:
                return None
            rows = db.execute("SELECT * FROM takes WHERE shot_id=%s ORDER BY created_at DESC",
                              (shot_id,)).fetchall()
        return [_take_json(r) for r in rows]

    # ---------- verdicts (C2) ----------

    def _owned_take(self, db, take_id, owner_id):
        return db.execute(
            """SELECT t.*, s.project_id, s.request, s.pinned, s.accepted_take_id, s.title AS shot_title,
                      p.bible
                 FROM takes t JOIN shots s ON s.id = t.shot_id
                 JOIN projects p ON p.id = s.project_id
                WHERE t.id = %s AND p.owner_id = %s""",
            (_identifier(take_id, "take id"), owner_id)).fetchone()

    def accept_take(self, take_id, owner_id, strict=False):
        """Make this take the one that goes to assembly.

        The judge does not get a veto, but it gets a record: accepting a take with a red light is
        written as 'overridden' with who and when, so the cut can later say why this take is in
        it. The light is computed here from the stored scores and the thresholds in force, not
        taken from the client - the browser shows the same lights, but the verdict must not depend
        on what it claims to have shown.

        The shot's previously chosen take goes back to 'pending'. The roadmap's state machine
        reserves 'overridden' for a person overruling the judge, so a superseded take cannot use it;
        pending is honest - it is once again a take nobody has picked.

        Uniqueness of accepted_take_id is a table constraint, so two shots cannot claim the same
        take no matter how this is called.
        """
        now = time.time()
        with self.connect() as db:
            take = self._owned_take(db, take_id, owner_id)
            if take is None:
                return None
            if take["deleted_at"]:
                raise FactoryError("take_deleted", "This take's output was deleted")
            if take["job_id"] is None and not take["output_url"]:
                raise FactoryError("take_unfinished", "Only a finished take can be accepted")
            thresholds = review_rules.resolve_thresholds(take["bible"], take["request"], strict)
            red = review_rules.is_red(take["scores"], thresholds)
            db.execute("UPDATE takes SET verdict='pending', overridden_by=NULL, overridden_at=NULL "
                       "WHERE shot_id=%s AND verdict IN ('accepted','overridden') AND id<>%s",
                       (take["shot_id"], take["id"]))
            if red:
                db.execute("UPDATE takes SET verdict='overridden', overridden_by=%s, overridden_at=%s "
                           "WHERE id=%s", (owner_id, now, take["id"]))
            else:
                db.execute("UPDATE takes SET verdict='accepted', overridden_by=NULL, overridden_at=NULL "
                           "WHERE id=%s", (take["id"],))
            db.execute("UPDATE shots SET accepted_take_id=%s, updated_at=%s WHERE id=%s",
                       (take["id"], now, take["shot_id"]))
            db.execute("UPDATE projects SET updated_at=%s WHERE id=%s", (now, take["project_id"]))
        return take["project_id"]

    def take_context(self, take_id, owner_id):
        """A take with the shot and Bible behind it, for the VLM's one sentence."""
        with self.connect() as db:
            take = self._owned_take(db, take_id, owner_id)
        if take is None:
            return None
        thresholds = review_rules.resolve_thresholds(take["bible"], take["request"])
        return {**dict(take), "thresholds": thresholds,
                "lights": review_rules.lights(take["scores"], thresholds)}

    def record_opinion(self, take_id, opinion):
        with self.connect() as db:
            row = db.execute("UPDATE takes SET opinion=%s WHERE id=%s RETURNING id",
                             (Jsonb(opinion), _identifier(take_id, "take id"))).fetchone()
        return row["id"] if row else None

    def disagree_opinion(self, take_id, owner_id):
        """The reviewer rejects the sentence. It stays visible, struck through, with who said so."""
        now = time.time()
        with self.connect() as db:
            take = self._owned_take(db, take_id, owner_id)
            if take is None:
                return None
            if not take["opinion"]:
                raise FactoryError("no_opinion", "There is no opinion on this take to disagree with")
            opinion = {**take["opinion"], "disagreed_by": owner_id, "disagreed_at": now}
            db.execute("UPDATE takes SET opinion=%s WHERE id=%s", (Jsonb(opinion), take["id"]))
        return take["project_id"]

    def project_takes(self, project_id, owner_id):
        """Every take in the project, grouped by shot, with what the review page needs per take."""
        project_id = _identifier(project_id, "project id")
        with self.connect() as db:
            owned = db.execute("SELECT bible FROM projects WHERE id=%s AND owner_id=%s",
                               (project_id, owner_id)).fetchone()
            if not owned:
                return None
            rows = db.execute(
                """SELECT t.*, s.request FROM takes t JOIN shots s ON s.id = t.shot_id
                    WHERE s.project_id = %s ORDER BY s.position, t.created_at DESC""",
                (project_id,)).fetchall()
        grouped = {}
        for r in rows:
            thresholds = review_rules.resolve_thresholds(owned["bible"], r["request"])
            grouped.setdefault(str(r["shot_id"]), []).append(
                {**_take_json(r), "thresholds": thresholds,
                 "lights": review_rules.lights(r["scores"], thresholds)})
        return grouped



    def reject_take(self, take_id, owner_id, reason):
        """Send a take back and open the next one, with the reason carried into its prompt.

        The reason is appended as its own "避免：" line and earlier lines are kept: a second
        rejection must not erase what the first one learned. The prompt is pinned afterwards so a
        Bible reprojection cannot wash the accumulated notes away. The user can still edit it.
        """
        if not isinstance(reason, str) or not reason.strip():
            raise FactoryError("reason_required", "A rejection needs a reason")
        reason = reason.strip()[:300]
        now = time.time()
        with self.connect() as db:
            take = self._owned_take(db, take_id, owner_id)
            if take is None:
                return None
            request = dict(take["request"] or {})
            prompt = str(request.get("prompt") or "").rstrip()
            prompt = f"{prompt}\n避免：{reason}" if prompt else f"避免：{reason}"
            if len(prompt) > MAX_PROMPT:
                raise FactoryError("prompt_too_long",
                                   f"Adding this reason would push the prompt past {MAX_PROMPT} characters")
            request["prompt"] = prompt
            pinned = list(take["pinned"] or [])
            if "prompt" not in pinned:
                pinned.append("prompt")
            db.execute("UPDATE takes SET verdict='rejected', reason=%s WHERE id=%s",
                       (reason, take["id"]))
            # A new attempt needs a new key (see rotate_key); the shot goes back to draft so a
            # person confirms the amended prompt before GPU time is spent on it.
            db.execute(
                "UPDATE shots SET request=%s, pinned=%s, status='draft', idempotency_key=%s, "
                "accepted_take_id=CASE WHEN accepted_take_id=%s THEN NULL ELSE accepted_take_id END, "
                "updated_at=%s WHERE id=%s",
                (Jsonb(request), Jsonb(pinned), f"factory-{take['shot_id']}-{uuid.uuid4().hex[:8]}",
                 take["id"], now, take["shot_id"]))
            db.execute("UPDATE projects SET updated_at=%s WHERE id=%s", (now, take["project_id"]))
        return take["project_id"]

    def mark_take_deleted(self, job_id):
        """The recycle bin took this job's output. Only that take changes.

        No owner argument: the job deletion that calls this already checked ownership, and the
        take is found through the job, never through anything the caller names.
        """
        now = time.time()
        with self.connect() as db:
            rows = db.execute("UPDATE takes SET deleted_at=%s WHERE job_id=%s AND deleted_at IS NULL "
                              "RETURNING id, shot_id", (now, job_id)).fetchall()
            for row in rows:
                # A shot cannot keep an accepted take whose output no longer exists.
                db.execute("UPDATE shots SET accepted_take_id=NULL, updated_at=%s "
                           "WHERE id=%s AND accepted_take_id=%s", (now, row["shot_id"], row["id"]))
        return len(rows)

    # ---------- post versions (D3) ----------

    def take_file(self, take_id):
        """The output filename of a take, for the job runner. No owner: admission checked it."""
        try:
            take_id = _identifier(take_id, "take id")
        except FactoryError:
            return None
        with self.connect() as db:
            row = db.execute("SELECT output_url FROM takes WHERE id=%s AND deleted_at IS NULL", (take_id,)).fetchone()
        if not row or not row["output_url"]:
            return None
        return str(row["output_url"]).rsplit("/", 1)[-1]

    def record_post_take(self, shot_id, *, job_id, post, output_url=None, poster_url=None, reason=None):
        """A new take that is a post version of another. The shot is not touched.

        record_take moves the shot's status because it records a generation the line is waiting
        on. A post version is made from a take the shot already accepted; flipping the shot back
        to running would make the review page think the shot is still being shot.
        """
        take_id = str(uuid.uuid4())
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM shots WHERE id=%s", (shot_id,)).fetchone():
                return None
            db.execute("INSERT INTO takes(id,shot_id,job_id,output_url,poster_url,reason,post,created_at) "
                       "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       (take_id, shot_id, job_id, output_url, poster_url, reason, Jsonb(post), time.time()))
        return take_id

    # ---------- keyframes (D2) ----------

    def project_for_keyframes(self, project_id):
        """The project and its shots for the batch thread. No owner: the thread was started by an
        owner-checked request and carries the owner it was given."""
        project_id = _identifier(project_id, "project id")
        with self.connect() as db:
            project = db.execute("SELECT * FROM projects WHERE id=%s", (project_id,)).fetchone()
            if not project:
                return None, []
            shots = db.execute("SELECT * FROM shots WHERE project_id=%s ORDER BY position",
                               (project_id,)).fetchall()
        return project, shots

    def set_keyframe_run(self, project_id, state):
        with self.connect() as db:
            db.execute("UPDATE projects SET keyframe_run=%s, updated_at=%s WHERE id=%s",
                       (Jsonb(state), time.time(), project_id))

    def keyframe_run(self, project_id):
        with self.connect() as db:
            row = db.execute("SELECT keyframe_run FROM projects WHERE id=%s", (project_id,)).fetchone()
        return (row or {}).get("keyframe_run") or {}

    def insert_keyframe(self, shot_id, *, seed, attempt=1, reference_id=None, job_id=None):
        keyframe_id = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO keyframes(id,shot_id,job_id,attempt,seed,reference_id,created_at) "
                       "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                       (keyframe_id, shot_id, job_id, attempt, int(seed), reference_id, time.time()))
        return keyframe_id

    def update_keyframe(self, keyframe_id, **fields):
        allowed = {"job_id", "output_url", "scores", "light", "verdict", "reason", "asset_id"}
        unknown = set(fields) - allowed
        if unknown:
            raise FactoryError("invalid_keyframe", f"unknown keyframe fields: {', '.join(sorted(unknown))}")
        if not fields:
            return
        sets, values = [], []
        for key, value in fields.items():
            sets.append(f"{key}=%s")
            values.append(Jsonb(value) if key == "scores" and value is not None else value)
        values.append(keyframe_id)
        with self.connect() as db:
            db.execute(f"UPDATE keyframes SET {', '.join(sets)} WHERE id=%s", values)

    def list_keyframes(self, project_id, owner_id):
        project_id = _identifier(project_id, "project id")
        with self.connect() as db:
            owned = db.execute("SELECT keyframe_run FROM projects WHERE id=%s AND owner_id=%s",
                               (project_id, owner_id)).fetchone()
            if not owned:
                return None
            rows = db.execute(
                """SELECT k.* FROM keyframes k JOIN shots s ON s.id = k.shot_id
                    WHERE s.project_id = %s ORDER BY s.position, k.created_at DESC""",
                (project_id,)).fetchall()
        grouped = {}
        for r in rows:
            grouped.setdefault(str(r["shot_id"]), []).append(_keyframe_json(r))
        return {"run": owned["keyframe_run"] or {}, "keyframes": grouped}

    def _owned_keyframe(self, db, keyframe_id, owner_id):
        return db.execute(
            """SELECT k.*, s.project_id, s.request, s.pinned, p.owner_id
                 FROM keyframes k JOIN shots s ON s.id = k.shot_id
                 JOIN projects p ON p.id = s.project_id
                WHERE k.id = %s AND p.owner_id = %s""",
            (_identifier(keyframe_id, "keyframe id"), owner_id)).fetchone()

    def keyframe_context(self, keyframe_id, owner_id):
        with self.connect() as db:
            row = self._owned_keyframe(db, keyframe_id, owner_id)
        return dict(row) if row else None

    def approve_keyframe(self, keyframe_id, owner_id, asset_id):
        """The keyframe becomes the shot's picture.

        The shot's image_id is set to the promoted asset and pinned, so a Bible reprojection cannot
        put the reference back; keyframe_id on the request is what the UI reads as "from a
        keyframe". A previously approved keyframe for the shot is marked superseded, not deleted.
        """
        now = time.time()
        with self.connect() as db:
            row = self._owned_keyframe(db, keyframe_id, owner_id)
            if row is None:
                return None
            if row["verdict"] == "failed" or not row["output_url"]:
                raise FactoryError("keyframe_unfinished", "Only a generated keyframe can be approved")
            request = dict(row["request"] or {})
            request["image_id"] = asset_id
            request["keyframe_id"] = str(row["id"])
            pinned = list(row["pinned"] or [])
            if "image_id" not in pinned:
                pinned.append("image_id")
            db.execute("UPDATE keyframes SET verdict='rejected', reason='superseded' "
                       "WHERE shot_id=%s AND verdict='approved' AND id<>%s", (row["shot_id"], row["id"]))
            db.execute("UPDATE keyframes SET verdict='approved', asset_id=%s, reason=NULL WHERE id=%s",
                       (asset_id, row["id"]))
            db.execute("UPDATE shots SET request=%s, pinned=%s, updated_at=%s WHERE id=%s",
                       (Jsonb(request), Jsonb(pinned), now, row["shot_id"]))
            db.execute("UPDATE projects SET updated_at=%s WHERE id=%s", (now, row["project_id"]))
        return row["project_id"]

    def reject_keyframe(self, keyframe_id, owner_id, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise FactoryError("reason_required", "A rejection needs a reason")
        with self.connect() as db:
            row = self._owned_keyframe(db, keyframe_id, owner_id)
            if row is None:
                return None
            db.execute("UPDATE keyframes SET verdict='rejected', reason=%s WHERE id=%s",
                       (reason.strip()[:300], row["id"]))
        return row["project_id"]

    # ---------- workstation (D4) ----------

    def queued_models(self, owner_id=None):
        """Queued shots of running projects, counted by model. Owner-scoped for the page,
        global for the scheduler."""
        where = "p.status='running' AND s.status='queued'"
        values = ()
        if owner_id is not None:
            where += " AND p.owner_id=%s"
            values = (owner_id,)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT COALESCE(s.request->>'model','ltx23-distilled') AS model, count(*) AS n "
                f"FROM shots s JOIN projects p ON p.id=s.project_id WHERE {where} GROUP BY 1", values).fetchall()
        return {r["model"]: int(r["n"]) for r in rows}

    def inflight_any(self):
        """Any shot on the GPU in any running project: the slot is taken."""
        with self.connect() as db:
            row = db.execute(
                "SELECT s.id, s.project_id, s.title, s.request, s.updated_at, t.job_id, p.title AS project_title "
                "FROM shots s JOIN projects p ON p.id=s.project_id "
                "LEFT JOIN LATERAL (SELECT job_id FROM takes WHERE shot_id=s.id ORDER BY created_at DESC LIMIT 1) t ON true "
                "WHERE p.status='running' AND s.status IN ('validating','submitting','running') "
                "ORDER BY s.updated_at LIMIT 1").fetchone()
        return dict(row) if row else None

    def remaining_models(self, project_id):
        """Models of the shots a project still has to run, in position order."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT COALESCE(request->>'model','ltx23-distilled') AS model FROM shots "
                "WHERE project_id=%s AND status NOT IN ('succeeded') ORDER BY position", (project_id,)).fetchall()
        return [r["model"] for r in rows]

    def project_runtime_seconds(self, project_id):
        """GPU seconds the project has actually spent: runtime_seconds of every take's job."""
        with self.connect() as db:
            row = db.execute(
                "SELECT COALESCE(sum((j.snapshot->>'runtime_seconds')::double precision), 0) AS seconds "
                "FROM takes t JOIN shots s ON s.id=t.shot_id JOIN jobs j ON j.id=t.job_id "
                "WHERE s.project_id=%s AND j.snapshot->>'runtime_seconds' IS NOT NULL", (project_id,)).fetchone()
        return round(float(row["seconds"] or 0), 1)

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
