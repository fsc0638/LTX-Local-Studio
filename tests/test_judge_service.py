"""Judge service tests.

The unit tests are pure Python: path containment, argument checking and the HTTP surface, with
frame extraction stubbed. They run in the interpreter that runs this suite.

Anything that loads a model - or even decodes a frame, since cv2 lives only in the vision venv -
is skipped unless that venv is running the file:

    LTX_JUDGE_INTEGRATION=1 /opt/studio/venvs/vision/bin/python -m unittest tests.test_judge_service

The direction tests there use flat colour blocks. Two pictures of the same colour must score
higher than two of different colours; the absolute numbers are deliberately not asserted, because
the service returns numbers and does not judge. Turning a number into a verdict needs a
calibrated threshold, which is C4.
"""
import importlib.util
import json
import os
import tempfile
import threading
import time
import unittest
import uuid
import urllib.error
from pathlib import Path
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1] / "services/judge/server.py"

_spec = importlib.util.spec_from_file_location("judge_server", SERVER)
judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge)

try:
    import cv2  # noqa: F401
    import numpy as np

    HAS_VISION = True
except ImportError:
    HAS_VISION = False

INTEGRATION = HAS_VISION and os.environ.get("LTX_JUDGE_INTEGRATION") == "1"


class PathTests(unittest.TestCase):
    """The service is handed paths ltx-api already resolved; it still checks them itself."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "uploads").mkdir()
        (self.root / "data").mkdir()
        self.inside = self.root / "uploads/frame.png"
        self.inside.write_bytes(b"not really a png")
        self.outside = self.root / "secret.txt"
        self.outside.write_text("password")
        patches = [patch.object(judge, "SITE_ROOT", self.root),
                   patch.object(judge, "ALLOWED_ROOTS",
                                (self.root / "uploads", self.root / "data"))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_a_path_inside_an_allowed_root_resolves(self):
        self.assertEqual(judge.resolved_path("uploads/frame.png"), self.inside.resolve())
        self.assertEqual(judge.resolved_path(str(self.inside)), self.inside.resolve())

    def test_a_path_outside_every_root_is_refused(self):
        with self.assertRaisesRegex(ValueError, "must be inside"):
            judge.resolved_path(str(self.outside))
        with self.assertRaisesRegex(ValueError, "must be inside"):
            judge.resolved_path("/etc/passwd")

    def test_traversal_and_symlinks_are_resolved_before_the_check_not_after(self):
        with self.assertRaisesRegex(ValueError, "must be inside"):
            judge.resolved_path("uploads/../secret.txt")
        link = self.root / "uploads/escape.png"
        link.symlink_to(self.outside)
        # The symlink sits inside uploads/, so a check that ran before resolving would pass it.
        with self.assertRaisesRegex(ValueError, "must be inside"):
            judge.resolved_path(str(link))

    def test_an_empty_or_missing_path_is_refused(self):
        with self.assertRaisesRegex(ValueError, "is required"):
            judge.resolved_path("")
        with self.assertRaisesRegex(ValueError, "is required"):
            judge.resolved_path(None)
        with self.assertRaisesRegex(ValueError, "readable file"):
            judge.resolved_path("uploads/absent.png")

    def test_the_label_names_the_field_that_was_wrong(self):
        with self.assertRaisesRegex(ValueError, "style_anchor_path"):
            judge.resolved_path("/etc/passwd", "style_anchor_path")


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "uploads").mkdir()
        self.media = self.root / "uploads/take.mp4"
        self.media.write_bytes(b"stub")
        for index in range(3):
            (self.root / f"uploads/ref{index}.png").write_bytes(b"stub")
        patches = [patch.object(judge, "SITE_ROOT", self.root),
                   patch.object(judge, "ALLOWED_ROOTS", (self.root / "uploads",)),
                   # Decoding needs cv2; these tests are about the request, not the pixels.
                   patch.object(judge, "frames_of", return_value=(["frame"], [None], {"kind": "image"})),
                   patch.object(judge, "consistency", return_value=None),
                   patch.object(judge, "style", return_value=None),
                   patch.object(judge, "motion", return_value=None)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_scoring_needs_a_media_path(self):
        with self.assertRaisesRegex(ValueError, "media_path is required"):
            judge.score({})

    def test_references_are_capped(self):
        many = [f"uploads/ref{i % 3}.png" for i in range(judge.MAX_REFERENCES + 1)]
        with self.assertRaisesRegex(ValueError, "at most"):
            judge.score({"media_path": "uploads/take.mp4", "references": many})
        with self.assertRaisesRegex(ValueError, "must be a list"):
            judge.score({"media_path": "uploads/take.mp4", "references": "uploads/ref0.png"})

    def test_a_reference_outside_the_roots_is_refused_like_the_media(self):
        with self.assertRaisesRegex(ValueError, "references"):
            judge.score({"media_path": "uploads/take.mp4", "references": ["/etc/passwd"]})

    def test_the_style_anchor_is_optional(self):
        result = judge.score({"media_path": "uploads/take.mp4"})
        self.assertIsNone(result["style"])
        self.assertEqual(result["scored_by"], "ltx-judge/1.0")

    def test_the_service_reports_scores_and_never_a_verdict(self):
        result = judge.score({"media_path": "uploads/take.mp4"})
        flattened = json.dumps(result)
        for word in ("pass", "fail", "ok", "approved", "rejected", "threshold"):
            self.assertNotIn(f'"{word}"', flattened)


class HelperTests(unittest.TestCase):
    def test_the_median_ignores_frames_that_could_not_be_scored(self):
        self.assertEqual(judge.median([0.5, None, 0.9, 0.7]), 0.7)
        self.assertIsNone(judge.median([None, None]))
        self.assertIsNone(judge.median([]))

    def test_similarity_against_no_references_is_unknown_not_zero(self):
        # Zero would read as "completely different"; None says "not measured".
        self.assertIsNone(judge.best_similarity(None, []))
        self.assertIsNone(judge.best_similarity("vector", []))


@unittest.skipUnless(INTEGRATION, "needs the vision venv and LTX_JUDGE_INTEGRATION=1")
class DirectionTests(unittest.TestCase):
    """Flat colour blocks: same must beat different. No absolute number is asserted."""

    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        (cls.root / "uploads").mkdir()
        cls.red = cls.write("red.png", (32, 32, 200))
        cls.red_again = cls.write("red2.png", (36, 30, 205))
        cls.blue = cls.write("blue.png", (200, 40, 30))

    @classmethod
    def write(cls, name, bgr):
        path = cls.root / "uploads" / name
        cv2.imwrite(str(path), np.full((256, 256, 3), bgr, dtype=np.uint8))
        return path

    def score(self, media, references=(), anchor=None):
        with patch.object(judge, "SITE_ROOT", self.root), \
             patch.object(judge, "ALLOWED_ROOTS", (self.root / "uploads",)):
            payload = {"media_path": str(media), "references": [str(r) for r in references]}
            if anchor is not None:
                payload["style_anchor_path"] = str(anchor)
            return judge.score(payload)

    def test_an_image_against_itself_scores_at_the_top_of_the_scale(self):
        result = self.score(self.red, [self.red])
        self.assertEqual(result["media"]["kind"], "image")
        self.assertGreater(result["consistency"]["median"], 0.99)
        # No face in a colour block, so it falls back and says so.
        self.assertEqual(result["consistency"]["method_per_frame"], ["dinov2_large"])
        self.assertEqual(result["consistency"]["faces_found"], 0)

    def test_the_same_subject_scores_above_a_different_one(self):
        same = self.score(self.red, [self.red_again])["consistency"]["median"]
        different = self.score(self.red, [self.blue])["consistency"]["median"]
        self.assertGreater(same, different,
                           f"same={same} did not beat different={different}")

    def test_the_best_matching_reference_is_the_one_that_counts(self):
        # A mixed reference table must score on the match, not be dragged down by the mismatch.
        mixed = self.score(self.red, [self.blue, self.red_again])["consistency"]["median"]
        worst = self.score(self.red, [self.blue])["consistency"]["median"]
        self.assertGreater(mixed, worst)

    def test_style_similarity_moves_the_same_way(self):
        same = self.score(self.red, anchor=self.red_again)["style"]["median"]
        different = self.score(self.red, anchor=self.blue)["style"]["median"]
        self.assertGreater(same, different, f"same={same} did not beat different={different}")

    def test_a_still_image_reports_no_motion_rather_than_zero(self):
        # Zero motion would be a measurement; a still has none to measure.
        self.assertIsNone(self.score(self.red)["motion"])


if __name__ == "__main__":
    unittest.main()


# The backend half: scoring is attached to a take without ever touching the job. These need
# psycopg and the backend, so they are skipped in the vision venv the way the direction tests are
# skipped in the LTX venv. Between the two interpreters everything runs.
try:
    import local_backend as backend
    import test_factory_api

    HAS_BACKEND = True
except ImportError:
    HAS_BACKEND = False


@unittest.skipUnless(HAS_BACKEND, "needs the backend and psycopg")
class ScoringTests(test_factory_api.FactoryAPITests if HAS_BACKEND else unittest.TestCase):
    """A judge that is down, slow or wrong must not change what happened to the job."""

    def shot_and_job(self):
        """A real jobs row: takes.job_id points at it, so a made-up id fails the foreign key."""
        from production_store import ProductionStore

        plan = self.new_project(shots=[test_factory_api.shot("first")])
        shot = plan["shots"][0]
        job = {"id": uuid.uuid4().hex, "status": "succeeded",
               "output_url": "/generated/take.mp4", "created_at": time.time()}
        ProductionStore().record(job)
        return shot, job

    def test_a_finished_take_is_recorded_before_the_judge_is_asked(self):
        shot, job = self.shot_and_job()
        started = threading.Event()
        with patch.object(backend, "judge_service",
                          side_effect=lambda *a, **k: started.set() or {"media": {}}):
            with patch.object(backend, "output_location", return_value=Path(__file__)):
                backend.record_succeeded_take(shot["id"], job)
                started.wait(timeout=10)
        takes = self.factory.takes(shot["id"], "@service")
        self.assertEqual(len(takes), 1)
        self.assertEqual(takes[0]["status"] if "status" in takes[0] else "succeeded", "succeeded")

    def test_the_scores_land_on_the_take(self):
        shot, job = self.shot_and_job()
        self.factory.record_take(shot["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"])
        with patch.object(backend, "judge_service", return_value={"consistency": {"median": 0.87}}):
            with patch.object(backend, "output_location", return_value=Path(__file__)):
                backend.score_take(shot["id"], job["id"], job["output_url"])
        stored = self.factory.takes(shot["id"], "@service")[0]
        self.assertEqual(stored["scores"]["consistency"]["median"], 0.87)

    def test_a_judge_that_is_down_leaves_the_take_unscored_and_succeeded(self):
        shot, job = self.shot_and_job()
        self.factory.record_take(shot["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"])
        with patch.object(backend, "judge_service", side_effect=urllib.error.URLError("down")):
            with patch.object(backend, "output_location", return_value=Path(__file__)):
                backend.score_take(shot["id"], job["id"], job["output_url"])
        stored = self.factory.takes(shot["id"], "@service")[0]
        self.assertEqual(stored["scores"], {"status": "unscored", "reason": "judge_unavailable"})
        # The take, and so the shot, is still a success: a judge that is down is not a verdict.
        project_id = self.factory.judge_context(shot["id"])["project_id"]
        self.assertEqual(
            self.factory.get_project(project_id, "@service")["shots"][0]["status"], "succeeded")

    def test_a_missing_output_is_reported_rather_than_scored(self):
        shot, job = self.shot_and_job()
        self.factory.record_take(shot["id"], job_id=job["id"], status="succeeded",
                                 output_url=job["output_url"])
        with patch.object(backend, "judge_service") as asked:
            with patch.object(backend, "output_location", return_value=Path("/nonexistent.mp4")):
                backend.score_take(shot["id"], job["id"], job["output_url"])
        self.assertFalse(asked.called, "a missing file must not be sent to the judge")
        stored = self.factory.takes(shot["id"], "@service")[0]
        self.assertEqual(stored["scores"]["reason"], "output_missing")

    def test_references_the_user_deleted_are_skipped_not_fatal(self):
        bible = {"character": {"name": "A", "description": "d",
                               "references": [{"image_id": "0" * 32, "view": "front"}]}}
        references, anchor = backend.judge_inputs(bible)
        self.assertEqual(references, [])
        self.assertIsNone(anchor)
