import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import local_backend as backend
import model_registry as registry
import worker_contract as contract
import test_backend
import test_accounts
from test_worker import run_job_implementation
from service_layout import check_private_layout


def fixture_command(payload, output, context):
    return [str(context["python"]), str(Path(__file__).parent / "fixtures/media_generator.py"),
            "invalid" if payload["prompt"] == "broken" else payload["media_type"], str(output)]


class ModelAdapterTests(unittest.TestCase):
    request = test_backend.BackendTests.request
    call = test_accounts.AccountTests.call
    register = test_accounts.AccountTests.register
    account = test_accounts.AccountTests.account

    def setUp(self):
        # Reuse fixtures, not the inherited account test methods.
        self.fixture = test_accounts.AccountTests(methodName="test_verification_is_single_use_and_never_creates_a_session")
        self.fixture.setUp()
        for key, value in vars(self.fixture).items():
            if not key.startswith("_"):
                setattr(self, key, value)
        self.registry_patch = patch.dict(registry.ADAPTERS)
        self.registry_patch.start()
        registry.register(registry.MediaAdapter("test-image", "Test-only image", "image", fixture_command, requires_cuda=False,
            parameters={"width": {"type": "integer", "default": 64, "minimum": 8, "maximum": 128}, "height": {"type": "integer", "default": 48}}))
        registry.register(registry.MediaAdapter("test-text", "Test-only text", "text", fixture_command, requires_cuda=False,
            parameters={"temperature": {"type": "number", "default": 0.6, "minimum": 0, "maximum": 2}}))
        self.cookie, self.csrf = self.account()

    def tearDown(self):
        self.registry_patch.stop()
        self.fixture.tearDown()

    def api(self, method, path, payload=None, **headers):
        return self.call(method, path, payload, cookie=self.cookie, csrf=self.csrf, **headers)

    def test_catalog_and_strict_parameters_without_gpu(self):
        self.assertEqual(self.call("GET", "/api/v1/models")[0], 401)
        with patch.object(backend, "RUNTIME", {"cuda_available": False}):
            models = json.loads(self.api("GET", "/api/v1/models")[2])["models"]
        self.assertFalse(next(m for m in models if m["id"] == "ltx23-distilled")["available"])
        self.assertTrue(next(m for m in models if m["id"] == "test-image")["available"])
        for extra in ({"model": "uninstalled"}, {"parameters": {"width": True}}, {"parameters": {"width": 256}},
                      {"parameters": {"command": "something"}}, {"image_id": "a" * 32}, {"width": 64}):
            result = self.api("POST", "/api/v1/validate", {"model": "test-image", "prompt": "ok", **extra})
            self.assertEqual(result[0], 400, result)
        self.assertEqual(self.api("POST", "/api/v1/validate", {"model": "test-image", "prompt": "ok"})[0], 200)

    def test_image_and_text_real_cpu_pipeline_private_artifacts_and_schema(self):
        from jsonschema import Draft202012Validator
        schema = json.loads(self.api("GET", "/api/v1/openapi.json")[2])
        validator = lambda name: Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": schema["components"]})
        other_cookie, other_csrf = self.account("bob")
        for kind, mime in (("image", "image/png"), ("text", "text/plain; charset=utf-8")):
            raw = {"model": f"test-{kind}", "prompt": "ok"}
            validator("JobRequest").validate(raw)
            with patch.object(backend, "RUNTIME", {"cuda_available": False}):
                result = self.api("POST", "/api/v1/jobs", raw, **{"Idempotency-Key": f"fixture-{kind}-001"})
            self.assertEqual(result[0], 202, result)
            job_id = json.loads(result[2])["id"]
            payload, _, _ = contract.parse_request(raw, backend.parse_payload)
            run_job_implementation(job_id, payload)
            job = json.loads(self.api("GET", f"/api/v1/jobs/{job_id}")[2])
            self.assertEqual(job["status"], "succeeded", job)
            validator("Job").validate(job)
            self.assertTrue(job["quality_control"]["passed"])
            self.assertEqual(job["artifacts"][0]["kind"], kind)
            url = job["artifacts"][0]["url"]
            self.assertEqual(self.api("GET", url)[1]["Content-Type"], mime)
            self.assertEqual(self.call("GET", url, cookie=other_cookie, csrf=other_csrf)[0], 404)
            self.assertEqual(self.api("GET", f"/api/v1/jobs/{job_id}/video")[0], 404)
            backend.JOBS.clear()
            self.assertEqual(self.api("HEAD", url)[0], 200)

    def test_bad_adapter_output_never_published(self):
        raw = {"model": "test-image", "prompt": "broken"}
        result = self.api("POST", "/api/v1/jobs", raw, **{"Idempotency-Key": "broken-image-001"})
        job_id = json.loads(result[2])["id"]
        run_job_implementation(job_id, contract.parse_request(raw, backend.parse_payload)[0])
        job = json.loads(self.api("GET", f"/api/v1/jobs/{job_id}")[2])
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["artifacts"], [])
        self.assertFalse(list(self.output.iterdir()))

    def test_secrets_not_inherited_and_public_build_preflight(self):
        with patch.dict(os.environ, {"LTX_SMTP_PASSWORD": "test-secret", "LTX_SMTP_PASSWORD_FILE": "/test/private", "LTX_WORKER_API_KEY": "private"}):
            env = backend.job_environment(registry.get("test-text").normalize({"prompt": "ok"}))
            self.assertNotIn("LTX_WORKER_API_KEY", env)
            self.assertFalse(any(name.startswith("LTX_SMTP_") for name in env))
        root = Path(self.temp.name) / "layout"
        (root / "dist/client/generated").mkdir(parents=True)
        check_private_layout(root)
        (root / "dist/client/generated/private.mp4").write_bytes(b"test")
        with self.assertRaises(ValueError):
            check_private_layout(root)
