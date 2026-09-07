"""D3: the post tools end to end - the real post service module in fake mode, ffmpeg for real.

A source take is a real clip ffmpeg draws (24 fps, 320x180, one second). Upscale doubles its
width and height and keeps every frame and the rate; clean keeps its geometry and takes a mask
that must belong to the caller; interpolate is refused while RIFE has no weights and the refusal
reaches the take as a reason. The new take belongs to the same shot, does not move the shot's
status, and goes to the judge like any other.
"""
import importlib.util
import json
import os
import subprocess
import threading
import time
import unittest
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import gpu_lease
import local_backend as backend
import model_registry as registry
import test_accounts
import test_backend
from factory_store import FactoryStore
from production_store import ProductionStore
from test_worker import run_job_implementation

SERVER = Path(__file__).resolve().parents[1] / "services/post/server.py"
MOTION = {"media": {"kind": "video", "frozen_ratio": 0.05, "black_ratio": 0.0}, "consistency": None,
          "style": None, "motion": {"median": 1.1, "p90": 2.0, "method": "raft_large"}}


def load_service():
    os.environ["LTX_POST_FAKE"] = "1"
    spec = importlib.util.spec_from_file_location("post_server", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PostAdapterTests(unittest.TestCase):
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
        import local_adapters.post as adapters
        registry.register(adapters.ADAPTER)
        self.service = load_service()
        root = Path(backend.WORK_DIR).parent
        self.service.INPUT_ROOTS = (root, Path(backend.OUTPUT_DIR))
        self.service.OUTPUT_ROOTS = (root,)
        self.service.MASK_ROOTS = (Path(backend.media_store.UPLOAD_DIR), root)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), self.service.Handler)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.factory = FactoryStore()
        for item in (patch.dict(os.environ, {"LTX_POST_SERVICE": self.url}),
                     patch.object(backend, "POST_SERVICE", self.url),
                     patch.object(backend, "FACTORY", self.factory),
                     patch.object(backend, "RUNTIME", {"cuda_available": True, "device": "test"}),
                     patch.object(backend, "GPU_LEASE", gpu_lease.GpuLease("http://127.0.0.1:9", backend.ltx_job_active, evict_timeout=1, poll=0.05)),
                     patch.object(backend, "judge_service", lambda payload, timeout=None: MOTION),
                     # The fixture stubs the background job thread; admit for real, then run the job.
                     patch.object(backend, "start_post_watch", lambda shot_id, job_id, post: backend.post_watch(shot_id, job_id, post))):
            item.start()
            self.addCleanup(item.stop)
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

    def api(self, method, path, payload=None, **headers):
        return self.call(method, path, payload, cookie=self.cookie, csrf=self.csrf, **headers)

    def source_take(self, owner=None):
        """A real one-second clip as a succeeded take on a shot the owner has."""
        owner = owner or self.owner
        plan = self.factory.create_project(owner, {"title": "MV"})
        plan = self.factory.replace_shots(plan["id"], owner, [{"title": "A", "request": {"prompt": "x"}}])
        shot = plan["shots"][0]
        job_id = uuid.uuid4().hex[:12]
        filename = f"ltx-ui-test-{job_id}.mp4"
        path = Path(backend.OUTPUT_DIR) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24",
                        "-t", "1", "-pix_fmt", "yuv420p", str(path)], check=True, timeout=60)
        job = {"id": job_id, "status": "succeeded", "filename": filename, "output_url": f"/generated/{filename}",
               "created_at": time.time(), "owner_id": owner, "audio": False, "media_type": "video",
               "measured_media": {"width": 320, "height": 180, "fps": 24.0, "frames": 24}}
        ProductionStore().record(job)
        backend.JOBS[job_id] = job
        self.factory.record_take(shot["id"], job_id=job_id, status="succeeded", output_url=job["output_url"])
        take = self.factory.takes(shot["id"], owner)[0]
        return plan, shot, take

    def upload_mask(self, cookie=None, csrf=None):
        from PIL import Image
        import io as _io
        mask = Image.new("L", (320, 180), 0)
        for x in range(100, 200):
            for y in range(60, 120):
                mask.putpixel((x, y), 255)
        buffer = _io.BytesIO()
        mask.convert("RGB").save(buffer, "PNG")
        status, _, body = self.fixture.request(
            "POST", "/api/assets?name=mask.png", buffer.getvalue(),
            {"Content-Type": "image/png", "Origin": "http://localhost:3000",
             "Cookie": cookie or self.cookie, "X-CSRF-Token": csrf or self.csrf})
        self.assertEqual(status, 201, body)
        return json.loads(body)["id"]

    def post(self, take_id, **body):
        return self.api("POST", f"/api/v1/factory/takes/{take_id}/post", body)

    def test_upscale_doubles_the_frame_keeps_the_rate_and_becomes_a_new_take(self):
        plan, shot, take = self.source_take()
        status, _, body = self.post(take["id"], op="upscale", scale=2)
        self.assertEqual(status, 202, body)
        takes = self.factory.takes(shot["id"], self.owner)
        self.assertEqual(len(takes), 2)
        new = next(t for t in takes if t["id"] != take["id"])
        self.assertEqual(new["post"]["op"], "upscale")
        self.assertEqual(new["post"]["source_take_id"], take["id"])
        self.assertEqual(new["post"]["parameters"]["width"], 640)
        job = backend.JOBS[new["jobId"]]
        self.assertEqual(job["status"], "succeeded", job.get("error"))
        self.assertTrue(job["quality_control"]["passed"], job["quality_control"])
        self.assertEqual((job["measured_media"]["width"], job["measured_media"]["height"]), (640, 360))
        self.assertEqual(job["measured_media"]["frames"], 24)
        self.assertAlmostEqual(job["measured_media"]["fps"], 24.0, places=2)
        # The judge saw it: MQ numbers on the new take, and the shot's status did not move.
        self.assertEqual(new["scores"]["motion"]["method"], "raft_large")
        self.assertEqual(self.factory.get_project(plan["id"], self.owner)["shots"][0]["status"], "succeeded")

    def test_clean_needs_a_mask_the_caller_owns_and_keeps_the_geometry(self):
        plan, shot, take = self.source_take()
        self.assertEqual(self.post(take["id"], op="clean")[0], 400, "a clean without a mask is refused")
        other_cookie, other_csrf = self.account("bob")
        theirs = self.upload_mask(other_cookie, other_csrf)
        status, _, body = self.post(take["id"], op="clean", mask_image_id=theirs)
        self.assertEqual(status, 400, body)
        mine = self.upload_mask()
        status, _, body = self.post(take["id"], op="clean", mask_image_id=mine)
        self.assertEqual(status, 202, body)
        new = next(t for t in self.factory.takes(shot["id"], self.owner) if t["id"] != take["id"])
        job = backend.JOBS[new["jobId"]]
        self.assertEqual(job["status"], "succeeded", job.get("error"))
        self.assertEqual((job["measured_media"]["width"], job["measured_media"]["height"]), (320, 180))
        self.assertEqual(new["post"]["parameters"]["mask_image_id"], mine)

    def test_interpolate_is_refused_without_rife_weights_and_the_take_says_why(self):
        plan, shot, take = self.source_take()
        self.assertFalse(self.service.rife_available())
        status, _, body = self.post(take["id"], op="interpolate", target_fps=48)
        # The job is admitted; the refusal comes from the service and lands on the take.
        self.assertEqual(status, 202, body)
        new = next(t for t in self.factory.takes(shot["id"], self.owner) if t["id"] != take["id"])
        self.assertTrue(new["post"].get("failed"))
        self.assertEqual(backend.JOBS[new["jobId"]]["status"], "failed")
        self.assertIn("generation_failed", new["reason"])
        self.assertEqual(new["post"]["parameters"]["frames"], 48, "the expected geometry doubled the frames")

    def test_a_take_of_another_account_cannot_be_processed(self):
        _, _, theirs = self.source_take(owner="someone-else")
        status, _, body = self.post(theirs["id"], op="upscale", scale=2)
        self.assertEqual(status, 404, body)

    def test_the_post_model_takes_no_paths_and_no_images(self):
        plan, shot, take = self.source_take()
        for bad in ({"parameters": {"op": "upscale", "take_id": "/tmp/x.mp4"}},
                    {"parameters": {"op": "upscale", "take_id": take["id"], "input": "/etc/passwd"}},
                    {"image_id": "a" * 32, "parameters": {"op": "upscale", "take_id": take["id"]}}):
            status, _, body = self.api("POST", "/api/v1/validate", {"model": "post-vx", "prompt": "x", "mode": "post", **bad})
            self.assertEqual(status, 400, (bad, body))

    def test_the_post_job_holds_no_gpu_lease(self):
        plan, shot, take = self.source_take()
        self.post(take["id"], op="upscale", scale=2)
        self.assertEqual([h[1] for h in backend.GPU_LEASE.history], [], "post tools are not lease tenants")

    def test_the_listing_groups_post_versions_and_reports_the_service(self):
        plan, shot, take = self.source_take()
        self.post(take["id"], op="upscale", scale=2)
        status, _, body = self.api("GET", f"/api/v1/factory/projects/{plan['id']}/post")
        self.assertEqual(status, 200, body)
        listing = json.loads(body)
        versions = listing["versions"][shot["id"]]
        self.assertEqual(len(versions), 1, "the source take is not a version; the upscale is")
        self.assertEqual(versions[0]["post"]["op"], "upscale")
        self.assertTrue(listing["service"]["available"])
        self.assertFalse(listing["service"]["rife_available"])
        other_cookie, other_csrf = self.account("dave")
        self.assertEqual(self.call("GET", f"/api/v1/factory/projects/{plan['id']}/post", cookie=other_cookie, csrf=other_csrf)[0], 404)

    def test_the_service_refuses_paths_outside_its_roots(self):
        with self.assertRaisesRegex(ValueError, "must be inside"):
            self.service.process({"op": "upscale", "input": "/etc/passwd", "output": str(Path(backend.WORK_DIR) / "o.mp4")})


if __name__ == "__main__":
    unittest.main()
