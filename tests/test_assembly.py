"""D5: the cut. Only accepted takes, in shot order, on the Bible's music; a manifest that
restores every request. The takes are real clips ffmpeg draws; the assembler and the technical
check are the real ones."""
import json
import subprocess
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import local_backend as backend
import test_accounts
import test_backend
from factory_store import FactoryStore
from production_store import ProductionStore


class AssemblyTests(unittest.TestCase):
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
        self.factory = FactoryStore()
        self.store = ProductionStore()
        for item in (patch.object(backend, "FACTORY", self.factory),
                     patch.object(backend, "STORE", self.store),
                     patch.object(backend, "RUNTIME", {"cuda_available": True, "device": "test"}),
                     # The cut runs on a thread in production; here it runs before the request returns.
                     patch.object(backend, "start_assembly", lambda project_id, owner, job: backend.assemble_project(project_id, owner, job))):
            item.start()
            self.addCleanup(item.stop)
        self.cookie, self.csrf = self.account()
        self.owner = json.loads(self.call("GET", "/api/auth/session", cookie=self.cookie)[2])["user"]["id"]

    def api(self, method, path, payload=None, **headers):
        return self.call(method, path, payload, cookie=self.cookie, csrf=self.csrf, **headers)

    def clip_take(self, shot_id, seconds=1, size="320x180", accept=True):
        job_id = uuid.uuid4().hex[:12]
        filename = f"ltx-ui-test-{job_id}.mp4"
        path = Path(backend.OUTPUT_DIR) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=24",
                        "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)], check=True, timeout=60)
        width, height = (int(v) for v in size.split("x"))
        job = {"id": job_id, "status": "succeeded", "filename": filename, "output_url": f"/generated/{filename}",
               "created_at": time.time(), "owner_id": self.owner, "audio": False, "media_type": "video",
               "model": "ltx23-distilled", "seed": 7, "prompt": f"shot {shot_id[:4]}",
               "provenance": {"source": "test", "references": [{"sha256": "ref" * 8}]}, "artifact_sha256": "art" * 8,
               "measured_media": {"width": width, "height": height, "fps": 24.0, "frames": 24 * seconds}}
        self.store.record(job)
        backend.JOBS[job_id] = job
        self.factory.record_take(shot_id, job_id=job_id, status="succeeded", output_url=job["output_url"])
        take = self.factory.takes(shot_id, self.owner)[0]
        if accept:
            self.factory.accept_take(take["id"], self.owner)
        return take

    def project(self, n=2, bible=None):
        plan = self.factory.create_project(self.owner, {"title": "沖縄 MV", "bible": bible or {}})
        plan = self.factory.replace_shots(plan["id"], self.owner, [{"title": f"S{i}", "request": {"prompt": f"p{i}", "seed": i}} for i in range(n)])
        return plan

    def test_the_cut_joins_accepted_takes_in_order_and_passes_the_technical_check(self):
        plan = self.project(2)
        for shot in plan["shots"]:
            self.clip_take(shot["id"])
        status, _, body = self.api("POST", f"/api/v1/factory/projects/{plan['id']}/assemble", {})
        self.assertEqual(status, 202, body)
        job_id = json.loads(body)["job"]["id"]
        job = backend.JOBS[job_id]
        self.assertEqual(job["status"], "succeeded", job.get("error"))
        self.assertTrue(job["quality_control"]["passed"], job["quality_control"])
        self.assertEqual(job["measured_media"]["frames"], 48)
        self.assertEqual((job["measured_media"]["width"], job["measured_media"]["height"]), (320, 180))
        self.assertEqual(job["owner_id"], self.owner)
        # The owner can fetch the cut; another account cannot.
        self.assertEqual(self.api("GET", job["output_url"])[0], 200)
        other_cookie, other_csrf = self.account("bob")
        self.assertEqual(self.call("GET", job["output_url"], cookie=other_cookie, csrf=other_csrf)[0], 404)
        view = json.loads(self.api("GET", f"/api/v1/factory/projects/{plan['id']}/assembly")[2])
        self.assertEqual(view["assembly"]["status"], "done")
        self.assertEqual(view["assembly"]["frames"], 48)

    def test_the_manifest_restores_every_request_and_records_each_take(self):
        plan = self.project(2)
        takes = [self.clip_take(shot["id"]) for shot in plan["shots"]]
        self.api("POST", f"/api/v1/factory/projects/{plan['id']}/assemble", {})
        manifest = json.loads(self.api("GET", f"/api/v1/factory/projects/{plan['id']}/assembly")[2])["manifest"]
        self.assertEqual(manifest["format"], "ltx-production-factory")
        self.assertEqual(manifest["version"], 2)
        # A1-compatible: each shot carries exactly what the importer accepts, and the request is whole.
        for index, shot in enumerate(manifest["shots"]):
            self.assertEqual(set(shot), {"title", "request", "pinned"})
            self.assertEqual(shot["request"], plan["shots"][index]["request"])
        edl = manifest["edl"]
        self.assertEqual([e["take_id"] for e in edl], [t["id"] for t in takes])
        self.assertEqual(edl[0]["verdict"], "accepted")
        self.assertEqual(edl[0]["seed"], 7)
        self.assertEqual(edl[0]["provenance"]["references"][0]["sha256"], "ref" * 8)
        self.assertEqual(edl[0]["model"], "ltx23-distilled")
        self.assertEqual((edl[0]["start_seconds"], edl[0]["end_seconds"]), (0.0, 1.0))
        self.assertEqual((edl[1]["start_seconds"], edl[1]["end_seconds"]), (1.0, 2.0))
        self.assertEqual(manifest["assembled"]["frames"], 48)
        self.assertEqual(manifest["assembled"]["fps"], 24)
        # And it imports: the same normaliser the browser uses accepts the plan part.
        self.assertEqual(len(manifest["shots"]), 2)

    def test_a_shot_without_an_accepted_take_disables_the_cut_and_is_named(self):
        plan = self.project(3)
        self.clip_take(plan["shots"][0]["id"])
        self.clip_take(plan["shots"][1]["id"], accept=False)
        status, _, body = self.api("POST", f"/api/v1/factory/projects/{plan['id']}/assemble", {})
        self.assertEqual(status, 400, body)
        refused = json.loads(body)
        self.assertEqual(refused["code"], "shots_without_take")
        self.assertEqual([m["title"] for m in refused["missing"]], ["S1", "S2"])
        view = json.loads(self.api("GET", f"/api/v1/factory/projects/{plan['id']}/assembly")[2])
        self.assertFalse(view["readiness"]["ready"])
        self.assertEqual([m["index"] for m in view["readiness"]["missing"]], [1, 2])

    def test_a_take_of_a_different_size_fails_the_cut_with_the_shot_named(self):
        plan = self.project(2)
        self.clip_take(plan["shots"][0]["id"])
        self.clip_take(plan["shots"][1]["id"], size="640x360")
        status, _, body = self.api("POST", f"/api/v1/factory/projects/{plan['id']}/assemble", {})
        self.assertEqual(status, 202, body)
        view = json.loads(self.api("GET", f"/api/v1/factory/projects/{plan['id']}/assembly")[2])
        self.assertEqual(view["assembly"]["status"], "failed")
        self.assertIn("S1", view["assembly"]["error"])

    def test_the_song_is_laid_under_the_cut_from_the_bible(self):
        wav = Path(backend.WORK_DIR).parent / "bed.wav"
        wav.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-ar", "48000", "-ac", "2", str(wav)], check=True, timeout=60)
        status, _, body = self.fixture.request("POST", "/api/assets?name=bed.wav", wav.read_bytes(),
            {"Content-Type": "audio/wav", "Origin": "http://localhost:3000", "Cookie": self.cookie, "X-CSRF-Token": self.csrf})
        self.assertEqual(status, 201, body)
        audio_id = json.loads(body)["id"]
        plan = self.project(2, bible={"music": {"audio_id": audio_id, "audio_start_seconds": 0.5, "audio_mode": "bed",
                                                "lrc": "", "lrc_timebase": "output"}})
        for shot in plan["shots"]:
            self.clip_take(shot["id"])
        status, _, body = self.api("POST", f"/api/v1/factory/projects/{plan['id']}/assemble", {})
        self.assertEqual(status, 202, body)
        job = backend.JOBS[json.loads(body)["job"]["id"]]
        self.assertEqual(job["status"], "succeeded", job.get("error"))
        manifest = json.loads(self.api("GET", f"/api/v1/factory/projects/{plan['id']}/assembly")[2])["manifest"]
        self.assertEqual(manifest["audio"]["audio_id"], audio_id)
        self.assertEqual(manifest["audio"]["audio_start_seconds"], 0.5)
        self.assertIn("sha256", manifest["audio"]["fingerprint"])

    def test_another_account_sees_nothing(self):
        plan = self.project(1)
        self.clip_take(plan["shots"][0]["id"])
        other_cookie, other_csrf = self.account("carol")
        self.assertEqual(self.call("POST", f"/api/v1/factory/projects/{plan['id']}/assemble", {}, cookie=other_cookie, csrf=other_csrf)[0], 404)
        self.assertEqual(self.call("GET", f"/api/v1/factory/projects/{plan['id']}/assembly", cookie=other_cookie, csrf=other_csrf)[0], 404)


if __name__ == "__main__":
    unittest.main()
