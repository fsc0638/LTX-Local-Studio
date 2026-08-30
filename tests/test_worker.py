import concurrent.futures
import json
import io
import os
from pathlib import Path
import sqlite3
import threading
import time
from unittest.mock import patch

import test_backend
import local_backend as backend
from production_store import ProductionStore
import worker_contract as contract

run_job_implementation = backend.run_job


class WorkerTests(test_backend.BackendTests):
    def setUp(self):
        super().setUp()
        self.store = ProductionStore(Path(self.temp.name) / "worker/jobs.sqlite3")
        self.worker_patches = [patch.object(backend, "STORE", self.store),
                               patch.object(backend, "STORE_ERROR", ""),
                               patch.object(contract, "api_key", return_value="a" * 48),
                               patch.object(backend, "generation_provenance", return_value={"source": "test"}),
                               patch.object(backend, "run_job")]
        for item in self.worker_patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.worker_patches):
            item.stop()
        super().tearDown()

    def call(self, method, path, payload=None, key="test-request-001", **headers):
        return self.request(method, path, json.dumps(payload) if payload is not None else None,
                            {"Authorization": "Bearer " + "a" * 48, "Content-Type": "application/json",
                             "Idempotency-Key": key, **headers})

    @staticmethod
    def payload(**extra):
        return {"prompt": "An ocean sunrise", "external": {"project_id": "mv-project", "shot_id": "S01"},
                "audio": False, **extra}

    def test_fail_closed_auth_and_capabilities(self):
        for method, path in (("GET", "/api/v1/capabilities"), ("POST", "/api/v1/jobs"), ("POST", "/api/v1/assets"), ("GET", "/api/v1/jobs/abcdef012345/video")):
            self.assertEqual(self.request(method, path)[0], 401)
        self.assertEqual(self.call("GET", "/api/v1/capabilities", Authorization="Bearer invalid")[0], 401)
        caps = json.loads(self.call("GET", "/api/v1/capabilities")[2])
        self.assertEqual(caps["limits"]["max_frames"], 257)
        self.assertFalse(caps["automatic_training"])
        self.assertFalse(caps["tenant_isolation"])
        with patch.object(contract, "api_key", return_value=""):
            self.assertEqual(self.call("GET", "/api/v1/capabilities")[0], 503)

    def test_submit_poll_replay_conflict_and_busy(self):
        status, _, body = self.call("POST", "/api/v1/jobs", self.payload(duration_seconds=2))
        self.assertEqual(status, 202, body)
        job = json.loads(body)
        self.assertEqual(job["frames"], 49)
        self.assertEqual(job["external"]["shot_id"], "S01")
        self.assertEqual(job["artifacts"], [])
        self.assertEqual(self.call("GET", job["status_url"])[0], 200)
        status, _, body = self.call("POST", "/api/v1/jobs", self.payload(duration_seconds=2))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["id"], job["id"])
        self.assertTrue(json.loads(body)["idempotent_replay"])
        changed = self.call("POST", "/api/v1/jobs", self.payload(duration_seconds=4))
        self.assertEqual(json.loads(changed[2])["code"], "idempotency_conflict")
        busy = self.call("POST", "/api/v1/jobs", self.payload(), key="new-request-002")
        self.assertEqual(busy[0], 409)
        self.assertEqual(busy[1]["Retry-After"], "5")
        self.assertEqual(self.store.list_jobs()["total"], 1)
        with patch.object(backend, "RUNTIME", {"cuda_available": False}):
            self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload(duration_seconds=2))[0], 200)

    def test_concurrent_duplicate_only_one_admission(self):
        def submit(_index):
            return self.call("POST", "/api/v1/jobs", self.payload())
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(submit, range(4)))
        self.assertEqual(sorted(r[0] for r in responses), [200, 200, 200, 202])
        self.assertEqual(len({json.loads(r[2])["id"] for r in responses}), 1)
        self.assertEqual(self.store.list_jobs()["total"], 1)

    def test_duration_validation_no_silent_clamping(self):
        for fps in (8, 16, 24, 30, 60):
            for duration in (0.1, 1, 2, 4):
                payload, _, _ = contract.parse_request(self.payload(duration_seconds=duration, fps=fps), backend.parse_payload)
                self.assertGreaterEqual(payload["frames"] / fps, duration)
                self.assertEqual((payload["frames"] - 1) % 8, 0)
        for extra in ({"duration_seconds": 10, "fps": 30}, {"duration_seconds": 20},
                      {"duration_seconds": 0}, {"duration_seconds": -2}, {"duration_seconds": float("nan")},
                      {"duration_seconds": None},
                      {"duration_seconds": 2, "frames": 49}, {"width": 768.1}, {"frames": True},
                      {"fps": 0}, {"audio": "false"}, {"model": "other"}, {"mode": "v2v"},
                      {"callback_url": "http://localhost/private"}, {"external": {"project_id": "../../secret"}}):
            response = self.call("POST", "/api/v1/jobs", self.payload(**extra))
            self.assertEqual(response[0], 400, (extra, response))
        self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload(), key="")[0], 400)
        self.assertEqual(self.store.list_jobs()["total"], 0)

    def test_restart_recovers_status_and_idempotency(self):
        job = json.loads(self.call("POST", "/api/v1/jobs", self.payload())[2])
        backend.JOBS.clear()
        recovered = ProductionStore(self.store.path)
        recovered.recover(self.output)
        with patch.object(backend, "STORE", recovered):
            self.assertEqual(json.loads(self.call("GET", job["status_url"])[2])["status"], "interrupted")
            status, _, body = self.call("POST", "/api/v1/jobs", self.payload())
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["status"], "interrupted")
        recovered.recover(self.output)
        self.assertEqual(recovered.list_jobs()["total"], 1)

    def test_artifact_download_range_head_and_restart(self):
        job = json.loads(self.call("POST", "/api/v1/jobs", self.payload())[2])
        self.assertEqual(self.call("GET", job["status_url"] + "/video")[0], 409)
        saved = backend.JOBS[job["id"]]
        saved.update(status="succeeded", progress=100, size_bytes=10, artifact_sha256="mock-checksum")
        (self.output / saved["filename"]).write_bytes(b"0123456789")
        self.store.record(saved)
        backend.JOBS.clear()
        response = json.loads(self.call("GET", job["status_url"])[2])
        url = response["artifacts"][0]["url"]
        status, headers, data = self.call("GET", url, Range="bytes=2-5")
        self.assertEqual((status, data), (206, b"2345"))
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(self.call("HEAD", url)[2], b"")
        self.assertEqual(self.request("GET", url)[0], 401)
        self.assertEqual(self.call("GET", "/api/v1/jobs/../../secret/video")[0], 404)

    def test_store_failure_and_gpu_failure_do_not_accept(self):
        with patch.object(self.store, "record", side_effect=sqlite3.OperationalError("disk full")):
            self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload())[0], 503)
        self.assertEqual(backend.JOBS, {})
        with patch.object(backend, "RUNTIME", {"cuda_available": False}):
            self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload())[0], 503)
        with patch.object(backend, "STORE", None):
            self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload())[0], 503)

    def test_legacy_import_and_completed_sidecar_repair(self):
        job = {"id": "abcdef012345", "status": "succeeded", "filename": "test.mp4", "frames": 49, "fps": 24}
        (self.output / "test.mp4").write_bytes(b"video")
        (self.output / "test.json").write_text(json.dumps(job))
        self.store.record({**job, "status": "running"}, key="stable-key", request_hash="request")
        self.store.recover(self.output)
        self.assertEqual(self.store.get(job["id"])["status"], "succeeded")
        self.assertEqual(self.store.by_key("stable-key")[1], "request")
        self.store.recover(self.output)
        self.assertEqual(self.store.list_jobs()["total"], 1)

    def test_both_apis_share_gpu_slot(self):
        self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload())[0], 202)
        response = self.request("POST", "/api/jobs", b'{"prompt":"test"}', {"Content-Type": "application/json"})
        self.assertEqual(response[0], 409)

    def test_authenticated_asset_upload_i2v(self):
        # Existing uploader performs real decode/signature validation.
        asset, data = self.upload()
        status, _, body = self.request("POST", "/api/v1/assets?name=reference.png", data,
                                       {"Authorization": "Bearer " + "a" * 48, "Content-Type": "image/png"})
        self.assertEqual(status, 201, body)
        uploaded = json.loads(body)
        self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload(mode="i2v", image_id=uploaded["id"]))[0], 202)

    def test_process_failure_persists_and_does_not_expose_artifact(self):
        job = json.loads(self.call("POST", "/api/v1/jobs", self.payload())[2])
        saved = backend.JOBS[job["id"]]
        from unittest.mock import MagicMock
        process = MagicMock()
        process.stdout = io.StringIO("Running denoising loop\nRuntimeError: failure\n")
        process.wait.return_value = 1
        process.poll.return_value = 1
        with patch.object(backend.subprocess, "Popen", return_value=process):
            run_job_implementation(job["id"], backend.parse_payload(self.payload()))
        persisted = self.store.get(job["id"])
        self.assertEqual(persisted["status"], "failed")
        self.assertIn("RuntimeError", persisted["message"])
        self.assertEqual(contract.describe_job(persisted)["artifacts"], [])
        self.assertNotIn("process", persisted)
        self.assertEqual(saved["status"], "failed")

    def test_setup_failure_is_durable_and_worker_key_not_forwarded(self):
        job = json.loads(self.call("POST", "/api/v1/jobs", self.payload())[2])
        with patch.object(backend, "job_environment", side_effect=ValueError("missing reference")):
            run_job_implementation(job["id"], backend.parse_payload(self.payload()))
        self.assertEqual(self.store.get(job["id"])["status"], "failed")
        with patch.dict(os.environ, {"LTX_WORKER_API_KEY": "test-private-key", "LTX_WORKER_API_KEY_FILE": "test-path"}):
            environment = backend.job_environment(backend.parse_payload(self.payload()))
            self.assertNotIn("LTX_WORKER_API_KEY", environment)
            self.assertNotIn("LTX_WORKER_API_KEY_FILE", environment)

    def test_projectless_contract_and_existing_idempotency_scope(self):
        import hashlib
        raw = {"prompt": "project independent", "duration_seconds": 1, "audio": False}
        status, _, body = self.call("POST", "/api/v1/jobs", raw)
        self.assertEqual(status, 202, body)
        job = json.loads(body)
        self.assertEqual(job["external"], {})
        self.assertEqual(job["resolved_parameters"]["profile"], "compat-v1")
        self.assertEqual(self.call("POST", "/api/v1/jobs", raw)[0], 200)
        key, _ = contract.validate_request(self.payload(), "stable-old-key")
        self.assertEqual(key, hashlib.sha256(json.dumps(["mv-project", "stable-old-key"]).encode()).hexdigest())

    def test_validation_profiles_and_strict_image_parameters_without_gpu(self):
        with patch.object(backend, "RUNTIME", {"cuda_available": False}), patch.object(backend, "STORE", None):
            for profile, defaults in contract.PROFILES.items():
                status, _, body = self.call("POST", "/api/v1/validate", {"prompt": "test", "profile": profile})
                self.assertEqual(status, 200, body)
                resolved = json.loads(body)["resolved_parameters"]
                for name, value in defaults.items():
                    self.assertEqual(resolved[name], value)
        self.assertEqual(self.store.list_jobs()["total"], 0)
        for extra in ({"profile": "latest"}, {"timeout_seconds": 0}, {"timeout_seconds": 7201},
                      {"timeout_seconds": True}, {"image_strength": 0.5}, {"image_id": "a" * 32},
                      {"external": None}, {"steps": 50}, {"guidance": 7.5}):
            self.assertEqual(self.call("POST", "/api/v1/validate", {"prompt": "test", **extra})[0], 400)
        asset, _ = self.upload()
        for strength in (0, 0.3, 1):
            raw = {"prompt": "test", "mode": "i2v", "image_id": asset["id"], "image_strength": strength}
            result = json.loads(self.call("POST", "/api/v1/validate", raw)[2])
            self.assertEqual(result["resolved_parameters"]["image_strength"], strength)
            parsed, _, _ = contract.parse_request(raw, backend.parse_payload)
            self.assertEqual(float(backend.job_environment(parsed)["LTX_IMAGE_STRENGTH"]), strength)
        for strength in (True, -1, 1.1, "0.8", None):
            self.assertEqual(self.call("POST", "/api/v1/validate", {**raw, "image_strength": strength})[0], 400)

    def test_cancel_queued_is_idempotent_and_durable(self):
        job = json.loads(self.call("POST", "/api/v1/jobs", self.payload())[2])
        path = job["status_url"] + "/cancel"
        self.assertEqual(self.request("POST", path)[0], 401)
        self.assertEqual(self.call("POST", path)[0], 202)
        self.assertTrue(self.store.get(job["id"])["cancel_requested"])
        self.assertEqual(self.call("POST", path)[0], 202)
        self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload(), key="new-pending-key")[0], 409)
        run_job_implementation(job["id"], backend.parse_payload(self.payload()))
        cancelled = json.loads(self.call("POST", path)[2])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["error"]["code"], "cancelled")
        self.assertEqual(self.call("POST", path)[0], 200)
        self.assertEqual(json.loads(self.call("POST", "/api/v1/jobs", self.payload())[2])["status"], "cancelled")
        self.assertEqual(json.loads(self.request("GET", f"/api/jobs/{job['id']}")[2])["status"], "failed")

    def test_openapi_history_and_authenticated_reference_download(self):
        from jsonschema import Draft202012Validator
        schema = json.loads(self.call("GET", "/api/v1/openapi.json")[2])
        self.assertEqual(schema["info"]["version"], contract.CONTRACT_VERSION)
        self.assertEqual(schema["components"]["schemas"]["JobRequest"]["required"], ["prompt"])
        self.assertIn("/api/v1/jobs/{id}/cancel", schema["paths"])
        job = json.loads(self.call("POST", "/api/v1/jobs", self.payload())[2])
        for name in ("Job", "JobRequest", "ResolvedParameters", "Validation"):
            Draft202012Validator.check_schema(schema["components"]["schemas"][name])
        validator = Draft202012Validator({"$ref": "#/components/schemas/Job", "components": schema["components"]})
        validator.validate(job)
        validator.validate(contract.describe_job({"id": "abcdef123456", "status": "succeeded", "frames": 49, "fps": 24}))
        request_validator = Draft202012Validator({"$ref": "#/components/schemas/JobRequest", "components": schema["components"]})
        request_validator.validate({"prompt": "test", "duration_seconds": 1, "profile": "preview-v1"})
        for raw in ({"prompt": "test", "frames": 12}, {"prompt": "test", "frames": 9, "duration_seconds": 1},
                    {"prompt": "test", "image_strength": 0.3}, {"prompt": "test", "mode": "i2v"}):
            self.assertFalse(request_validator.is_valid(raw), raw)
        listed = json.loads(self.call("GET", "/api/v1/jobs?limit=1")[2])
        self.assertEqual(listed["jobs"][0]["id"], job["id"])
        self.assertEqual(self.call("GET", "/api/v1/jobs?limit=101")[0], 400)
        asset, data = self.upload()
        path = f"/api/v1/assets/{asset['id']}/file"
        self.assertEqual(self.request("GET", path)[0], 401)
        self.assertEqual(self.call("GET", path)[2], data)
        self.assertEqual(json.loads(self.call("GET", "/api/v1/assets")[2])["assets"][0]["url"], path)

    def test_real_cpu_pipeline_rejects_bad_output_and_publishes_valid_output(self):
        from test_quality import create_video
        fixture = Path(self.temp.name) / "fixture.mp4"
        create_video(fixture)
        launcher = Path(__file__).parent / "fixtures/generator.sh"
        with patch.object(backend, "LAUNCHER", launcher), patch.dict(os.environ, {"LTX_TEST_FIXTURE": str(fixture)}):
            for prompt in ("broken", "valid"):
                raw = dict(prompt=prompt, width=256, height=256, frames=9, audio=False)
                job = json.loads(self.call("POST", "/api/v1/jobs", raw, key=f"cpu-check-{prompt}")[2])
                run_job_implementation(job["id"], backend.parse_payload(raw))
                saved = self.store.get(job["id"])
                path = self.output / saved["filename"]
                if prompt == "broken":
                    self.assertEqual(saved["status"], "failed", saved)
                    self.assertEqual(saved["error"]["code"], "quality_check_failed")
                    self.assertFalse(path.exists())
                    self.assertEqual(self.call("GET", job["status_url"] + "/video")[0], 409)
                else:
                    self.assertEqual(saved["status"], "succeeded", saved)
                    self.assertTrue(saved["quality_control"]["passed"])
                    self.assertTrue(path.exists())
                    self.assertTrue(path.with_suffix(".jpg").exists())
                    self.assertTrue(path.with_suffix(".json").exists())
                    self.assertEqual(len(saved["artifact_sha256"]), 64)

    def test_silent_process_deadline_and_running_cancellation(self):
        launcher = Path(__file__).parent / "fixtures/generator.sh"
        with patch.object(backend, "LAUNCHER", launcher):
            for cancel in (False, True):
                raw = dict(prompt="sleep", width=256, height=256, frames=9, audio=False)
                job = json.loads(self.call("POST", "/api/v1/jobs", raw, key=f"kill-check-{cancel}")[2])
                payload = backend.parse_payload(raw)
                # Test the watchdog quickly, without exposing sub-30s API timeouts.
                payload["timeout_seconds"] = 10 if cancel else 0.3
                runner = threading.Thread(target=run_job_implementation, args=(job["id"], payload))
                runner.start()
                deadline = time.monotonic() + 3
                while "process" not in backend.JOBS[job["id"]] and runner.is_alive() and time.monotonic() < deadline:
                    time.sleep(0.02)
                process = backend.JOBS[job["id"]].get("process")
                self.assertIsNotNone(process)
                if cancel:
                    self.assertEqual(self.call("POST", job["status_url"] + "/cancel")[0], 202)
                runner.join(timeout=5)
                self.assertFalse(runner.is_alive())
                self.assertIsNotNone(process.poll())
                saved = self.store.get(job["id"])
                self.assertEqual(saved["error"]["code"], "cancelled" if cancel else "generation_timeout", saved)
                self.assertEqual(contract.describe_job(saved)["artifacts"], [])

    def test_cancellation_during_quality_check_never_publishes(self):
        from test_quality import create_video
        fixture = Path(self.temp.name) / "fixture.mp4"
        create_video(fixture)
        popen = backend.subprocess.Popen
        def delayed_qc(command, **kwargs):
            if any(str(arg).endswith("check_output.py") for arg in command):
                command = ["sleep", "30"]
            return popen(command, **kwargs)
        raw = dict(prompt="valid", width=256, height=256, frames=9, audio=False)
        job = json.loads(self.call("POST", "/api/v1/jobs", raw)[2])
        with patch.object(backend, "LAUNCHER", Path(__file__).parent / "fixtures/generator.sh"), patch.dict(os.environ, {"LTX_TEST_FIXTURE": str(fixture)}), patch.object(backend.subprocess, "Popen", side_effect=delayed_qc):
            runner = threading.Thread(target=run_job_implementation, args=(job["id"], backend.parse_payload(raw)))
            runner.start()
            deadline = time.monotonic() + 3
            while backend.JOBS[job["id"]].get("phase") != "validation" and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(self.call("POST", job["status_url"] + "/cancel")[0], 202)
            runner.join(timeout=5)
            self.assertFalse(runner.is_alive())
        saved = self.store.get(job["id"])
        self.assertEqual(saved["status"], "cancelled", saved)
        self.assertFalse((self.output / saved["filename"]).exists())

    def test_low_disk_and_shutdown_fail_closed_before_admission(self):
        from types import SimpleNamespace
        with patch.object(backend.shutil, "disk_usage", return_value=SimpleNamespace(free=100)):
            result = self.call("POST", "/api/v1/jobs", self.payload())
            self.assertEqual(result[0], 503)
            self.assertEqual(json.loads(result[2])["code"], "insufficient_disk")
        with patch.object(backend, "STOPPING", True):
            self.assertEqual(self.call("POST", "/api/v1/jobs", self.payload())[0], 503)
        self.assertEqual(self.store.list_jobs()["total"], 0)
