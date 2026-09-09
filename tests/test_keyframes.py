"""D2: keyframes end to end - the real imagegen service module in fake mode, a scripted judge.

A keyframe for every shot, in order; the reference chosen by the shot's angle; red generated once
more with a derived seed and then left to a person; a mismatched character stays red; approval
promotes the picture into a real asset, sets the shot's image_id, pins it, and marks the shot as
coming from a keyframe.
"""
import importlib.util
import json
import os
import threading
import time
import unittest
import unittest.mock
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import gpu_lease
import local_backend as backend
import model_registry as registry
import review_rules
import test_accounts
import test_backend
from factory_store import FactoryStore
from test_worker import run_job_implementation

SERVER = Path(__file__).resolve().parents[1] / "services/imagegen/server.py"
GREEN = {"media": {"kind": "image"}, "consistency": {"median": 0.91, "per_frame": [0.91], "method_per_frame": ["face_facenet"]},
         "style": {"median": 0.9}, "motion": None}
YELLOW = {**GREEN, "consistency": {**GREEN["consistency"], "median": 0.77, "per_frame": [0.77]}}
RED = {**GREEN, "consistency": {**GREEN["consistency"], "median": 0.55, "per_frame": [0.55]}}


def load_service():
    os.environ["LTX_IMAGEGEN_FAKE"] = "1"
    spec = importlib.util.spec_from_file_location("imagegen_server_kf", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KeyframeTests(unittest.TestCase):
    request = test_backend.BackendTests.request
    call = test_accounts.AccountTests.call
    register = test_accounts.AccountTests.register
    account = test_accounts.AccountTests.account

    def setUp(self):
        self.fixture = test_accounts.AccountTests(methodName="test_verification_is_single_use_and_never_creates_a_session")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        for key, value in vars(self.fixture).items():
            if not key.startswith("_"):
                setattr(self, key, value)
        registry_patch = patch.dict(registry.ADAPTERS)
        registry_patch.start()
        self.addCleanup(registry_patch.stop)
        import local_adapters.imagegen as adapters
        registry.register(adapters.QWEN)
        registry.register(adapters.ZIMAGE)
        self.service = load_service()
        self.service.REFERENCE_ROOTS = (Path(backend.media_store.UPLOAD_DIR), Path(backend.WORK_DIR).parent)
        self.service.OUTPUT_ROOTS = (Path(backend.WORK_DIR).parent,)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), self.service.Handler)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        for item in (patch.dict(os.environ, {"LTX_IMAGEGEN_SERVICE": self.url}),
                     patch.object(backend, "KEYFRAME_BUSY_RETRIES", 6),
                     patch.object(backend, "KEYFRAME_BUSY_SLEEP", 0.5),
                     patch.object(backend, "KEYFRAME_WAIT_SECONDS", 60),
                     patch.object(backend, "GPU_LEASE", gpu_lease.GpuLease(self.url, backend.ltx_job_active, evict_timeout=5, poll=0.05)),
                     patch.object(backend, "RUNTIME", {"cuda_available": True, "device": "test"})):
            item.start()
            self.addCleanup(item.stop)
        self.factory = FactoryStore()
        factory_patch = patch.object(backend, "FACTORY", self.factory)
        factory_patch.start()
        self.addCleanup(factory_patch.stop)
        # The fixture stubs the background job thread (see test_worker), so a submitted job would
        # stay queued forever. Admit through the real submit_job, then run the job synchronously -
        # the same order the thread would have used, minus the thread.
        real_submit = backend.submit_job

        def submit_and_run(payload, **kwargs):
            status, result = real_submit(payload, **kwargs)
            if status == 202 and "id" in result:
                run_job_implementation(result["id"], payload)
            return status, result
        submit_patch = patch.object(backend, "submit_job", submit_and_run)
        submit_patch.start()
        self.addCleanup(submit_patch.stop)
        self.cookie, self.csrf = self.account()
        self.owner = json.loads(self.call("GET", "/api/auth/session", cookie=self.cookie)[2])["user"]["id"]
        self.judge_script = []
        self.judged = []

        def judge(payload, timeout=None):
            self.judged.append(payload)
            return self.judge_script.pop(0) if self.judge_script else GREEN
        judge_patch = patch.object(backend, "judge_service", judge)
        judge_patch.start()
        self.addCleanup(judge_patch.stop)

    def api(self, method, path, payload=None, **headers):
        return self.call(method, path, payload, cookie=self.cookie, csrf=self.csrf, **headers)

    def upload_png(self, name, cookie=None, csrf=None):
        from PIL import Image
        import io as _io
        buffer = _io.BytesIO()
        Image.new("RGB", (64, 64), (10, 200, 30)).save(buffer, "PNG")
        status, _, body = self.fixture.request(
            "POST", f"/api/assets?name={name}", buffer.getvalue(),
            {"Content-Type": "image/png", "Origin": "http://localhost:3000",
             "Cookie": cookie or self.cookie, "X-CSRF-Token": csrf or self.csrf})
        self.assertEqual(status, 201, body)
        return json.loads(body)["id"]

    def project(self, shots, references=("front", "left_three_quarter"), character=True):
        refs = [{"image_id": self.upload_png(f"{view}.png"), "view": view} for view in references]
        bible = {"character": {"name": "美佳", "description": "sanshin player", "references": refs}} if character else {}
        plan = self.factory.create_project(self.owner, {"title": "MV", "bible": bible})
        plan = self.factory.replace_shots(plan["id"], self.owner, shots)
        return plan, refs

    def run_batch(self, plan):
        backend.keyframe_batch(plan["id"], self.owner)
        listing = json.loads(self.api("GET", f"/api/v1/factory/projects/{plan['id']}/keyframes")[2])
        return listing

    # ---- the batch ----

    def test_every_shot_gets_a_keyframe_in_order_and_the_run_reports_its_estimate(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "dawn"}}, {"title": "B", "request": {"prompt": "dusk"}}])
        listing = self.run_batch(plan)
        self.assertEqual(listing["run"]["status"], "done")
        self.assertEqual(listing["run"]["done"], 2)
        self.assertEqual(listing["run"]["estimate_seconds"], 336 + 2 * 26)
        for shot in plan["shots"]:
            entries = listing["keyframes"][shot["id"]]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["light"], "green")
            self.assertEqual(entries[0]["verdict"], "pending", "a green keyframe still waits for a person")
            self.assertTrue(entries[0]["outputUrl"].endswith(".png"))
        self.assertEqual(self.service.status()["loads"], 1, "the whole batch pays for one load")

    def test_the_reference_is_chosen_by_the_shots_angle(self):
        plan, refs = self.project([{"title": "A", "request": {"prompt": "x", "directing": {"angle": "left_three_quarter"}}},
                                   {"title": "B", "request": {"prompt": "y", "directing": {"angle": "front"}}}])
        listing = self.run_batch(plan)
        by_view = {r["view"]: r["image_id"] for r in refs}
        self.assertEqual(listing["keyframes"][plan["shots"][0]["id"]][0]["referenceId"], by_view["left_three_quarter"])
        self.assertEqual(listing["keyframes"][plan["shots"][1]["id"]][0]["referenceId"], by_view["front"])

    def test_a_red_keyframe_is_generated_once_more_with_a_different_seed(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x", "seed": 100}}])
        self.judge_script = [RED, GREEN]
        listing = self.run_batch(plan)
        entries = sorted(listing["keyframes"][plan["shots"][0]["id"]], key=lambda k: k["attempt"])
        self.assertEqual([e["attempt"] for e in entries], [1, 2])
        self.assertEqual(entries[0]["light"], "red")
        self.assertEqual(entries[0]["verdict"], "rejected")
        self.assertEqual(entries[0]["reason"], "red_retry")
        self.assertNotEqual(entries[0]["seed"], entries[1]["seed"])
        self.assertEqual(entries[1]["light"], "green")
        self.assertEqual(entries[1]["verdict"], "pending")

    def test_a_mismatched_character_stays_red_after_the_retry_and_waits_for_a_person(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x"}}])
        self.judge_script = [RED, RED]
        listing = self.run_batch(plan)
        entries = sorted(listing["keyframes"][plan["shots"][0]["id"]], key=lambda k: k["attempt"])
        self.assertEqual(len(entries), 2, "exactly one automatic retry")
        self.assertEqual(entries[1]["light"], "red")
        self.assertEqual(entries[1]["verdict"], "pending")
        self.assertIsNone(self.factory.get_project(plan["id"], self.owner)["shots"][0]["request"].get("keyframe_id"),
                          "a red keyframe never becomes the shot's picture on its own")

    def test_yellow_is_not_retried(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x"}}])
        self.judge_script = [YELLOW]
        listing = self.run_batch(plan)
        entries = listing["keyframes"][plan["shots"][0]["id"]]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["light"], "yellow")

    def test_a_shot_with_no_reference_fails_alone_and_the_batch_continues(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x"}}, {"title": "B", "request": {"prompt": "y"}}], character=False)
        listing = self.run_batch(plan)
        self.assertEqual(listing["run"]["status"], "done")
        for shot in plan["shots"]:
            self.assertEqual(listing["keyframes"][shot["id"]][0]["verdict"], "failed")
            self.assertEqual(listing["keyframes"][shot["id"]][0]["reason"], "no_reference")

    def test_the_judge_being_down_leaves_the_keyframe_unscored_not_red(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x"}}])
        import urllib.error
        with patch.object(backend, "judge_service", side_effect=urllib.error.URLError("down")):
            listing = self.run_batch(plan)
        entry = listing["keyframes"][plan["shots"][0]["id"]][0]
        self.assertIsNone(entry["light"])
        self.assertEqual(entry["scores"]["status"], "unscored")
        self.assertEqual(entry["verdict"], "pending")

    # ---- the endpoints ----

    def test_run_is_refused_while_running_and_without_shots(self):
        plan, _ = self.project([])
        status, _, body = self.api("POST", f"/api/v1/factory/projects/{plan['id']}/keyframes/run", {})
        self.assertEqual(status, 400, body)
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x"}}])
        self.factory.set_keyframe_run(plan["id"], {"status": "running"})
        status, _, body = self.api("POST", f"/api/v1/factory/projects/{plan['id']}/keyframes/run", {})
        self.assertEqual(status, 409, body)

    def test_approval_promotes_the_picture_to_an_asset_and_pins_it_on_the_shot(self):
        plan, refs = self.project([{"title": "A", "request": {"prompt": "x"}}])
        listing = self.run_batch(plan)
        keyframe = listing["keyframes"][plan["shots"][0]["id"]][0]
        status, _, body = self.api("POST", f"/api/v1/factory/keyframes/{keyframe['id']}/approve", {})
        self.assertEqual(status, 200, body)
        shot = json.loads(body)["shots"][0]
        asset_id = shot["request"]["image_id"]
        self.assertNotEqual(asset_id, refs[0]["image_id"], "the shot now starts from the keyframe, not the reference")
        self.assertEqual(shot["request"]["keyframe_id"], keyframe["id"])
        self.assertIn("image_id", shot["pinned"], "a reprojection must not put the reference back")
        # It is a real asset: the owner can fetch it, another account cannot.
        self.assertEqual(self.api("GET", f"/api/assets/{asset_id}/file")[0], 200)
        other_cookie, other_csrf = self.account("bob")
        self.assertEqual(self.call("GET", f"/api/assets/{asset_id}/file", cookie=other_cookie, csrf=other_csrf)[0], 404)
        after = self.factory.list_keyframes(plan["id"], self.owner)["keyframes"][plan["shots"][0]["id"]][0]
        self.assertEqual(after["verdict"], "approved")
        self.assertEqual(after["assetId"], asset_id)

    def test_an_approved_shot_still_passes_the_worker_contract(self):
        """keyframe_id stays on the stored request for the UI, but the worker refuses unknown
        fields: sending the shot must strip it and carry the keyframe picture as image_id."""
        plan, refs = self.project([{"title": "A", "request": {"prompt": "x"}}])
        listing = self.run_batch(plan)
        keyframe = listing["keyframes"][plan["shots"][0]["id"]][0]
        self.assertEqual(self.api("POST", f"/api/v1/factory/keyframes/{keyframe['id']}/approve", {})[0], 200)
        self.assertEqual(self.api("POST", f"/api/v1/factory/projects/{plan['id']}/run", {})[0], 200)
        mine = [p for p in self.factory.running_projects() if str(p["id"]) == plan["id"]]
        picked = backend.scheduler_pick(projects=mine)
        self.assertIsNotNone(picked, "the approved shot is queued and pickable")
        project, shot = picked
        self.assertEqual(shot["request"]["keyframe_id"], keyframe["id"])
        sent, real_submit = {}, backend.submit_job
        def spy_submit(payload, **kwargs):
            sent.update(payload)
            return real_submit(payload, **kwargs)
        with patch.object(backend, "submit_job", spy_submit):
            backend.factory_send(project, shot)
        takes = self.factory.project_takes(plan["id"], self.owner)
        takes = takes.get("takes", takes)
        take = takes[str(shot["id"])][-1]
        self.assertIsNone(take.get("reason"), "the worker contract must not refuse the shot")
        self.assertTrue(take.get("jobId"), "the shot was handed to the worker")
        self.assertEqual(sent.get("image_id"), shot["request"]["image_id"], "the keyframe picture is what the shot starts from")
        self.assertNotIn("keyframe_id", sent)
        self.assertEqual(sent.get("mode"), "i2v")

    def test_a_plain_shot_and_a_keyframe_shot_share_the_cuts_geometry(self):
        """The assembler refuses a cut of mixed sizes. A keyframe shot takes its picture's size (the
        Bible's aspect); a shot that says nothing about size must land on the same geometry, not the
        worker's 768x512 default. A shot that spells its own size is left alone."""
        plan, refs = self.project([{"title": "A", "request": {"prompt": "x"}},
                                   {"title": "B", "request": {"prompt": "y"}},
                                   {"title": "C", "request": {"prompt": "z", "width": 512, "height": 320}}])
        listing = self.run_batch(plan)
        first = listing["keyframes"][plan["shots"][0]["id"]][0]
        self.assertEqual(self.api("POST", f"/api/v1/factory/keyframes/{first['id']}/approve", {})[0], 200)
        for other in (plan["shots"][1]["id"], plan["shots"][2]["id"]):
            for k in listing["keyframes"][other]:
                self.api("POST", f"/api/v1/factory/keyframes/{k['id']}/reject", {"reason": "plain shot"})
        self.assertEqual(self.api("POST", f"/api/v1/factory/projects/{plan['id']}/run", {})[0], 200)
        project = [p for p in self.factory.running_projects() if str(p["id"]) == plan["id"]][0]
        sent, real_submit = {}, backend.submit_job
        def spy_submit(payload, **kwargs):
            sent[kwargs["external"]["shot_id"]] = payload
            return real_submit(payload, **kwargs)
        with patch.object(backend, "submit_job", spy_submit):
            for _ in plan["shots"]:
                picked = backend.scheduler_pick(projects=[project])
                if picked is None:
                    break
                backend.factory_send(*picked)
        a, b, c = (sent[s["id"]] for s in plan["shots"])
        self.assertEqual(a["mode"], "i2v")
        self.assertEqual((a["width"], a["height"]), (b["width"], b["height"]), "plain shot follows the keyframe shot")
        self.assertNotEqual((b["width"], b["height"]), (768, 512), "not the worker default")
        self.assertEqual((c["width"], c["height"]), (512, 320), "an explicit size is respected")

    def test_approving_another_candidate_supersedes_the_first(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x", "seed": 3}}])
        self.judge_script = [RED, GREEN]
        listing = self.run_batch(plan)
        entries = sorted(listing["keyframes"][plan["shots"][0]["id"]], key=lambda k: k["attempt"])
        self.api("POST", f"/api/v1/factory/keyframes/{entries[1]['id']}/approve", {})
        # A person may still prefer the red one - the judge does not veto.
        status, _, body = self.api("POST", f"/api/v1/factory/keyframes/{entries[0]['id']}/approve", {})
        self.assertEqual(status, 200, body)
        after = {k["id"]: k for k in self.factory.list_keyframes(plan["id"], self.owner)["keyframes"][plan["shots"][0]["id"]]}
        self.assertEqual(after[entries[0]["id"]]["verdict"], "approved")
        self.assertEqual(after[entries[1]["id"]]["verdict"], "rejected")
        self.assertEqual(after[entries[1]["id"]]["reason"], "superseded")

    def test_rejection_needs_a_reason_and_a_failed_keyframe_cannot_be_approved(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x"}}], character=False)
        listing = self.run_batch(plan)
        keyframe = listing["keyframes"][plan["shots"][0]["id"]][0]
        status, _, body = self.api("POST", f"/api/v1/factory/keyframes/{keyframe['id']}/approve", {})
        self.assertEqual(status, 400, body)
        status, _, body = self.api("POST", f"/api/v1/factory/keyframes/{keyframe['id']}/reject", {"reason": "  "})
        self.assertEqual(status, 400, body)
        self.assertEqual(json.loads(body)["code"], "reason_required")

    def test_keyframes_are_owner_scoped(self):
        plan, _ = self.project([{"title": "A", "request": {"prompt": "x"}}])
        self.assertIsNone(self.factory.list_keyframes(plan["id"], "someone-else"))
        other_cookie, other_csrf = self.account("carol")
        self.assertEqual(self.call("GET", f"/api/v1/factory/projects/{plan['id']}/keyframes", cookie=other_cookie, csrf=other_csrf)[0], 404)


class LightRuleTests(unittest.TestCase):
    def test_the_python_light_matches_the_browser_rule(self):
        t = review_rules.resolve_thresholds({"thresholds": {"cj": 0.80}})
        self.assertEqual(review_rules.keyframe_light(GREEN, t), "green")
        self.assertEqual(review_rules.keyframe_light(YELLOW, t), "yellow")
        self.assertEqual(review_rules.keyframe_light(RED, t), "red")
        self.assertIsNone(review_rules.keyframe_light({"status": "unscored"}, t))


if __name__ == "__main__":
    unittest.main()


class ServiceOwnerTests(unittest.TestCase):
    """A service-owned project must reach admission with owner None, like every other path."""

    def test_the_service_owner_is_not_passed_as_an_account(self):
        seen = {}

        def fake_submit(payload, **kwargs):
            seen.update(kwargs)
            return 202, {"id": "abcdef012345"}
        context = {"id": "11111111-1111-1111-1111-111111111111", "project_id": "p", "bible": {},
                   "request": {"prompt": "x"}, "title": "S"}
        with patch.object(backend, "submit_job", fake_submit), \
             patch.object(backend, "keyframe_wait", return_value={"status": "failed", "error": {"code": "stub"}}), \
             patch.object(backend, "FACTORY", unittest.mock.MagicMock()), \
             patch.object(backend.worker, "parse_request", lambda raw, pp: (raw, raw.get("external"), None)):
            with self.assertRaises(ValueError):
                backend.keyframe_generate({"id": "p", "bible": {}}, {"id": "s", "request": {"prompt": "x"}, "title": "S"},
                                          backend.SERVICE_OWNER, "kf1", 1, "a" * 32, "1280x720")
            self.assertIsNone(seen.get("owner_id"))
            with self.assertRaises(ValueError):
                backend.keyframe_generate({"id": "p", "bible": {}}, {"id": "s", "request": {"prompt": "x"}, "title": "S"},
                                          "user-1", "kf2", 1, "a" * 32, "1280x720")
            self.assertEqual(seen.get("owner_id"), "user-1")
