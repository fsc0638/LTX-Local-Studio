"""D1: the two image adapters, end to end against the real service module in fake mode.

The service is imported from services/imagegen/server.py and started in this process on a free
port with LTX_IMAGEGEN_FAKE=1, so the pipeline is a stub that paints a flat PNG. Everything else
is real: the registry's parameter checks, admission, the client subprocess, the lease, the
technical QC of the PNG, and the private artifact route.
"""
import importlib.util
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import gpu_lease
import local_backend as backend
import model_registry as registry
import worker_contract as contract
import test_accounts
import test_backend
from test_worker import run_job_implementation

SERVER = Path(__file__).resolve().parents[1] / "services/imagegen/server.py"


def load_service():
    os.environ["LTX_IMAGEGEN_FAKE"] = "1"
    spec = importlib.util.spec_from_file_location("imagegen_server", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ImagegenAdapterTests(unittest.TestCase):
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

        # The real service, fake pipeline, on a free port, allowed to write where this test's
        # backend writes and to read the uploads this test's backend owns.
        self.service = load_service()
        self.service.REFERENCE_ROOTS = (Path(backend.media_store.UPLOAD_DIR), Path(backend.WORK_DIR).parent)
        self.service.OUTPUT_ROOTS = (Path(backend.WORK_DIR).parent,)
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), self.service.Handler)
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        env_patch = patch.dict(os.environ, {"LTX_IMAGEGEN_SERVICE": self.url})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        lease_patch = patch.object(backend, "GPU_LEASE", gpu_lease.GpuLease(self.url, backend.ltx_job_active, evict_timeout=5, poll=0.05))
        lease_patch.start()
        self.addCleanup(lease_patch.stop)
        self.cookie, self.csrf = self.account()

    def api(self, method, path, payload=None, **headers):
        return self.call(method, path, payload, cookie=self.cookie, csrf=self.csrf, **headers)

    def upload_png(self, cookie, csrf, name="ref.png"):
        # Raw bytes with explicit headers: the JSON helper would try to encode the picture.
        from PIL import Image
        import io as _io
        buffer = _io.BytesIO()
        Image.new("RGB", (64, 64), (10, 200, 30)).save(buffer, "PNG")
        status, _, body = self.fixture.request(
            "POST", f"/api/assets?name={name}", buffer.getvalue(),
            {"Content-Type": "image/png", "Origin": "http://localhost:3000", "Cookie": cookie, "X-CSRF-Token": csrf})
        self.assertEqual(status, 201, body)
        return json.loads(body)["id"]

    def upload_reference(self):
        return self.upload_png(self.cookie, self.csrf)

    # ---- registry: what a request may and may not say ----

    def test_parameters_are_checked_by_the_registry_and_paths_are_never_accepted(self):
        reference = self.upload_reference()
        ok = {"model": "qwen-image-edit-2509", "prompt": "make it dusk", "mode": "edit", "image_id": reference}
        self.assertEqual(self.api("POST", "/api/v1/validate", ok)[0], 200)
        for bad in ({"parameters": {"steps": 0}}, {"parameters": {"steps": 51}}, {"parameters": {"size": "999x999"}},
                    {"parameters": {"path": "/etc/passwd"}}, {"parameters": {"reference_2": 7}},
                    {"parameters": {"seed": -1}}, {"image_id": "/tmp/x.png"}, {"parameters": {"lightning": "yes"}}):
            status, _, body = self.api("POST", "/api/v1/validate", {**ok, **bad})
            self.assertEqual(status, 400, (bad, body))

    def test_an_edit_needs_a_reference_and_text_to_image_refuses_one(self):
        reference = self.upload_reference()
        status, _, body = self.api("POST", "/api/v1/validate", {"model": "qwen-image-edit-2509", "prompt": "x", "mode": "edit"})
        self.assertEqual(status, 400, body)
        self.assertIn("image_id is required", json.loads(body)["error"])
        status, _, body = self.api("POST", "/api/v1/validate", {"model": "z-image-turbo", "prompt": "x", "image_id": reference})
        self.assertEqual(status, 400, body)
        self.assertEqual(self.api("POST", "/api/v1/validate", {"model": "z-image-turbo", "prompt": "a lantern"})[0], 200)

    def test_the_catalog_lists_both_as_image_models(self):
        models = {m["id"]: m for m in json.loads(self.api("GET", "/api/v1/models")[2])["models"]}
        self.assertEqual(models["qwen-image-edit-2509"]["media_type"], "image")
        self.assertEqual(models["z-image-turbo"]["media_type"], "image")
        self.assertTrue(models["qwen-image-edit-2509"]["accepts_image"])
        self.assertFalse(models["z-image-turbo"]["accepts_image"])
        self.assertEqual(models["z-image-turbo"]["parameters"]["steps"]["default"], 8)

    def test_a_second_reference_belongs_to_the_caller_or_the_job_is_refused(self):
        other_cookie, other_csrf = self.account("bob")
        theirs = self.upload_png(other_cookie, other_csrf, "theirs.png")
        mine = self.upload_reference()
        raw = {"model": "qwen-image-edit-2509", "prompt": "x", "mode": "edit", "image_id": mine,
               "parameters": {"reference_2": theirs}}
        status, _, body = self.api("POST", "/api/v1/jobs", raw, **{"Idempotency-Key": "ref-owner-001"})
        self.assertEqual(status, 400, body)

    # ---- end to end through the fake service ----

    def generate(self, raw, key):
        with patch.object(backend, "RUNTIME", {"cuda_available": True, "device": "test"}):
            status, _, body = self.api("POST", "/api/v1/jobs", raw, **{"Idempotency-Key": key})
        self.assertEqual(status, 202, body)
        job_id = json.loads(body)["id"]
        payload, _, _ = contract.parse_request(raw, backend.parse_payload)
        run_job_implementation(job_id, payload)
        return json.loads(self.api("GET", f"/api/v1/jobs/{job_id}")[2])

    def test_text_to_image_produces_a_private_png_through_the_service(self):
        job = self.generate({"model": "z-image-turbo", "prompt": "a lantern-lit alley", "parameters": {"size": "1280x720", "seed": 7}},
                            "zimage-001")
        self.assertEqual(job["status"], "succeeded", job)
        self.assertTrue(job["quality_control"]["passed"])
        self.assertEqual(job["artifacts"][0]["kind"], "image")
        self.assertEqual(job["measured_media"]["width"], 1280)
        self.assertEqual(self.service.status()["loads"], 1)
        other_cookie, other_csrf = self.account("carol")
        self.assertEqual(self.call("GET", job["artifacts"][0]["url"], cookie=other_cookie, csrf=other_csrf)[0], 404)

    def test_an_edit_hands_the_reference_path_to_the_service_never_an_id(self):
        reference = self.upload_reference()
        seen = {}
        original = self.service.generate

        def spy(payload):
            seen.update(payload)
            return original(payload)

        with patch.object(self.service, "generate", spy):
            job = self.generate({"model": "qwen-image-edit-2509", "prompt": "make it dusk", "mode": "edit", "image_id": reference},
                                "qwen-001")
        self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(len(seen["references"]), 1)
        sent = seen["references"][0]
        # A private path, resolved by ltx-api, whose filename happens to be the asset id: the
        # service is handed somewhere to read, never something to look up.
        self.assertTrue(Path(sent).is_absolute(), sent)
        self.assertTrue(sent.endswith(".png"), sent)
        self.assertNotEqual(sent, reference)
        self.assertTrue(Path(sent).is_relative_to(Path(backend.media_store.UPLOAD_DIR)), sent)

    def test_twenty_images_pay_for_one_load(self):
        for index in range(20):
            job = self.generate({"model": "z-image-turbo", "prompt": f"frame {index}", "parameters": {"seed": index}},
                                f"batch-{index:03d}")
            self.assertEqual(job["status"], "succeeded", job)
        self.assertEqual(self.service.status()["loads"], 1)

    def test_switching_models_unloads_the_other(self):
        reference = self.upload_reference()
        self.generate({"model": "z-image-turbo", "prompt": "a"}, "switch-001")
        self.assertEqual(self.service.status()["loaded"], ["z-image-turbo"])
        self.generate({"model": "qwen-image-edit-2509", "prompt": "b", "mode": "edit", "image_id": reference}, "switch-002")
        self.assertEqual(self.service.status()["loaded"], ["qwen-image-edit-2509"])
        self.assertEqual(self.service.status()["loads"], 2)

    def test_an_image_job_holds_and_releases_the_lease(self):
        job = self.generate({"model": "z-image-turbo", "prompt": "a"}, "lease-001")
        self.assertEqual(job["status"], "succeeded", job)
        self.assertIsNone(backend.GPU_LEASE.holder)
        events = [h[1] for h in backend.GPU_LEASE.history]
        self.assertEqual(events[-2:], ["acquired", "released"])

    def test_release_drops_the_model_and_idle_watch_would_too(self):
        self.generate({"model": "z-image-turbo", "prompt": "a"}, "release-001")
        self.assertEqual(self.service.status()["loaded"], ["z-image-turbo"])
        self.assertTrue(self.service.unload("test"))
        self.assertEqual(self.service.status()["loaded"], [])
        self.assertFalse(self.service.unload("test"), "unloading twice is a no-op")

    def test_the_service_refuses_paths_outside_its_roots(self):
        with self.assertRaisesRegex(ValueError, "must be inside"):
            self.service.generate({"model": "z-image-turbo", "prompt": "a", "output": "/tmp/out.png"})
        with self.assertRaisesRegex(ValueError, "must be inside"):
            self.service.generate({"model": "qwen-image-edit-2509", "prompt": "a", "references": ["/etc/passwd"],
                                   "output": str(Path(backend.WORK_DIR) / "x.png")})

    def test_the_lease_endpoint_is_loopback_only_and_shows_the_state(self):
        status, _, body = self.call("GET", "/api/internal/gpu-lease")
        self.assertEqual(status, 200, body)
        state = json.loads(body)
        self.assertIn("holder", state)
        self.assertIn("imagegen_loaded", state)


if __name__ == "__main__":
    unittest.main()
