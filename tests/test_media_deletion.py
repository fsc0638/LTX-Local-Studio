import base64
import fcntl
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import local_backend as backend
import media_store
from media_deletion import prepare_archive
from production_store import ProductionStore
import test_accounts


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_accounts.AccountTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = Path(self.fixture.temp.name)
        self.trash = self.root / "trash"
        self.patch = patch.object(backend, "TRASH_DIR", self.trash)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.call = self.fixture.call
        self.cookie, self.csrf = self.fixture.account()

    def job(self, **overrides):
        job = {"id": "abcdef123456", "filename": "test-abcdef123456.mp4", "status": "succeeded",
               "created_at": time.time(), "finished_at": time.time(), "progress": 100,
               "owner_id": json.loads(self.call("GET", "/api/auth/session", cookie=self.cookie)[2])["user"]["id"],
               "output_url": "/generated/test-abcdef123456.mp4", "model": "ltx23-distilled", **overrides}
        backend.JOBS[job["id"]] = job
        self.fixture.store.record(job, key="deletion-key-123", request_hash="test-hash")
        for suffix, data in ((".mp4", b"video"), (".jpg", b"poster"), (".json", json.dumps(job).encode())):
            (self.fixture.output / Path(job["filename"]).with_suffix(suffix)).write_bytes(data)
        return job

    def remove(self, kind, identity, **headers):
        return self.call("DELETE", f"/api/v1/{kind}/{identity}", cookie=self.cookie, csrf=self.csrf, **headers)

    def upload(self):
        data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        result = self.fixture.request("POST", "/api/assets?name=test.png", data,
            {"Content-Type": "image/png", "Origin": "http://localhost:3000", "Cookie": self.cookie, "X-CSRF-Token": self.csrf})
        self.assertEqual(result[0], 201, result)
        return json.loads(result[2])

    def test_output_removed_and_tombstone_survives_recovery_and_replay(self):
        job = self.job()
        original = dict(job)
        result = self.remove("jobs", job["id"])
        self.assertEqual(result[0], 200, result)
        self.assertEqual(list(self.fixture.output.iterdir()), [])
        for path in (f"/api/v1/jobs/{job['id']}", f"/api/v1/jobs/{job['id']}/artifact", job["output_url"], job["output_url"].replace(".mp4", ".jpg")):
            self.assertEqual(self.call("GET", path, cookie=self.cookie)[0], 404)
        self.assertEqual(json.loads(self.call("GET", "/api/outputs", cookie=self.cookie)[2])["outputs"], [])
        self.assertEqual(json.loads(self.call("GET", "/api/v1/jobs", cookie=self.cookie)[2])["total"], 0)
        self.assertEqual(self.fixture.store.recent_count(job["owner_id"], time.time()-100), 1)
        self.fixture.store.record(original)
        self.assertTrue(self.fixture.store.get(job["id"])["deleted_at"])
        # Even stale files copied back into an output folder cannot resurrect it.
        (self.fixture.output / job["filename"]).write_bytes(b"old")
        (self.fixture.output / Path(job["filename"]).with_suffix(".json")).write_text(json.dumps(original))
        self.fixture.store.recover(self.fixture.output)
        with patch.object(backend, "JOBS", {}):
            self.assertEqual(self.call("GET", job["output_url"], cookie=self.cookie)[0], 404)
            self.assertEqual(backend.replay_job("deletion-key-123", "test-hash")[0], 410)
        self.assertEqual(self.remove("jobs", job["id"])[0], 200)
        manifests = list(self.trash.glob("*/manifest.json"))
        self.assertEqual(len(manifests), 1)
        saved = json.loads(manifests[0].read_text())
        self.assertEqual(len(saved["files"]), 3)
        self.assertEqual(self.trash.stat().st_mode & 0o777, 0o700)
        for entry in saved["files"]:
            self.assertTrue((manifests[0].parent / entry["archive"]).is_file())

    def test_auth_csrf_origin_owner_and_active_job(self):
        job = self.job(status="running")
        path = f"/api/v1/jobs/{job['id']}"
        self.assertEqual(self.call("DELETE", path)[0], 401)
        self.assertEqual(self.call("DELETE", path, cookie=self.cookie)[0], 403)
        self.assertEqual(self.remove("jobs", job["id"], Origin="https://evil.invalid")[0], 403)
        other, csrf = self.fixture.account("bob")
        self.assertEqual(self.call("DELETE", path, cookie=other, csrf=csrf)[0], 404)
        self.assertEqual(self.remove("jobs", job["id"])[0], 409)
        self.assertFalse(self.trash.exists())
        with patch.object(backend, "USER_AUTH_ENABLED", False), patch.object(backend.worker, "api_key", return_value="test-service-key"):
            self.assertEqual(self.call("DELETE", path)[0], 401)
            self.assertEqual(self.call("DELETE", path, Authorization="Bearer test-service-key")[0], 409)
            job["status"] = "failed"
            self.assertEqual(self.call("DELETE", path, Authorization="Bearer test-service-key")[0], 200)
            self.assertEqual(self.call("GET", job["output_url"], Authorization="Bearer test-service-key")[0], 404)

    def test_asset_in_use_and_isolation_then_deletion(self):
        asset = self.upload()
        other, csrf = self.fixture.account("bob")
        self.assertEqual(self.call("DELETE", f"/api/v1/assets/{asset['id']}", cookie=other, csrf=csrf)[0], 404)
        job = self.job(status="queued", image_id=asset["id"])
        self.assertEqual(self.remove("assets", asset["id"])[0], 409)
        job["status"] = "succeeded"
        self.assertEqual(self.remove("assets", asset["id"])[0], 200)
        self.assertEqual(list(media_store.UPLOAD_DIR.iterdir()), [])
        self.assertEqual(self.call("GET", asset["url"], cookie=self.cookie)[0], 404)
        self.assertEqual(json.loads(self.call("GET", "/api/assets", cookie=self.cookie)[2])["assets"], [])
        self.assertEqual(self.remove("assets", asset["id"])[0], 404)
        with self.assertRaises(ValueError):
            backend.submit_job({"image_id": asset["id"]})

    def test_archive_or_store_failure_keeps_original_files(self):
        job = self.job()
        with patch.object(backend, "prepare_archive", side_effect=OSError()):
            self.assertEqual(self.remove("jobs", job["id"])[0], 503)
        with patch.object(self.fixture.store, "record", side_effect=sqlite3.OperationalError()):
            self.assertEqual(self.remove("jobs", job["id"])[0], 503)
        self.assertEqual((self.fixture.output / job["filename"]).read_bytes(), b"video")
        self.assertNotIn("deleted_at", self.fixture.store.get(job["id"]))

    def test_unlink_failure_still_denies_download(self):
        job = self.job()
        with patch("media_deletion.MediaArchive.remove_sources", side_effect=OSError()):
            result = self.remove("jobs", job["id"])
        self.assertTrue(json.loads(result[2])["cleanup_pending"])
        self.assertEqual(self.call("GET", job["output_url"], cookie=self.cookie)[0], 404)


class ArchiveTests(unittest.TestCase):
    def test_symlink_and_changed_source_are_not_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "asset.png"
            source.write_bytes(b"original")
            link = root / "link.png"
            link.symlink_to(source)
            with self.assertRaises(ValueError):
                prepare_archive([link], root / "trash", {})
            archive = prepare_archive([source], root / "trash", {})
            replacement = root / "replacement.png"
            replacement.write_bytes(b"new")
            replacement.replace(source)
            with self.assertRaises(ValueError):
                archive.remove_sources()
            self.assertEqual(source.read_bytes(), b"new")
            self.assertEqual(archive.entries[0][1].read_bytes(), b"original")

    def test_bulk_cleanup_scope_lock_and_restart(self):
        spec = importlib.util.spec_from_file_location("clear_media", Path(__file__).resolve().parents[1] / "scripts/clear-media.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = root / "data/worker"
            store = ProductionStore(state / "jobs.sqlite3")
            store.record({"id": "abcdef123456", "status": "succeeded", "filename": "old.mp4"})
            output = state / "outputs"
            output.mkdir()
            (output / "old.mp4").write_bytes(b"video")
            (state / "accounts.sqlite3").write_bytes(b"do not touch")
            public = root / "public/generated"
            public.mkdir(parents=True)
            (public / ".gitkeep").write_bytes(b"")
            self.assertEqual(module.clear(root)["files"], 1)
            with (state / "instance.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(ValueError):
                    module.clear(root, apply=True)
            result = module.clear(root, apply=True)
            self.assertEqual(result["files"], 1)
            self.assertEqual(store.list_jobs()["total"], 0)
            self.assertEqual((state / "accounts.sqlite3").read_bytes(), b"do not touch")
            self.assertTrue((public / ".gitkeep").exists())
            backup = sqlite3.connect(Path(result["archive"]) / "jobs-before.sqlite3")
            self.assertNotIn("deleted_at", json.loads(backup.execute("SELECT snapshot FROM jobs").fetchone()[0]))
            backup.close()
            self.assertEqual(module.clear(root, apply=True)["files"], 0)


if __name__ == "__main__":
    unittest.main()
