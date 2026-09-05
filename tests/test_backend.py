import base64
import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import local_backend as backend
import conftest
import media_store as media


class BackendTests(conftest.DatabaseFixture, unittest.TestCase):
    def setUp(self):
        self.start_database()
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.output = root / "generated"
        self.output.mkdir()
        self.patches = [patch.object(backend, "OUTPUT_DIR", self.output),
                        patch.object(backend, "USER_AUTH_ENABLED", False),
                        patch.object(backend, "LEGACY_OUTPUT_DIR", root / "legacy-generated"),
                        patch.object(backend, "WORK_DIR", root / "private-work"),
                        patch.object(media, "UPLOAD_DIR", root / "uploads"),
                        patch.object(backend, "LTX_PYTHON", Path(sys.executable)),
                        patch.object(backend, "RUNTIME", {"cuda_available": True, "device": "test"}),
                        patch.object(backend, "JOBS", {})]
        for item in self.patches:
            item.start()
        self.server = backend.ThreadingHTTPServer(("127.0.0.1", 0), backend.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def upload(self):
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        status, _, body = self.request("POST", "/api/assets?name=test.png", png, {"Content-Type": "image/png"})
        self.assertEqual(status, 201, body)
        return json.loads(body), png

    def test_upload_list_preview_download_and_i2v(self):
        asset, data = self.upload()
        self.assertEqual(json.loads(self.request("GET", "/api/assets")[2])["assets"][0]["id"], asset["id"])
        status, headers, downloaded = self.request("GET", asset["url"] + "?download=1")
        self.assertEqual(status, 200)
        self.assertEqual(downloaded, data)
        self.assertIn("attachment", headers["Content-Disposition"])
        payload = backend.parse_payload({"prompt": "test", "mode": "i2v", "image_id": asset["id"]})
        self.assertEqual(payload["image_id"], asset["id"])

    def test_generated_range_head_and_traversal(self):
        (self.output / "test.mp4").write_bytes(b"0123456789")
        status, headers, body = self.request("GET", "/generated/test.mp4", headers={"Range": "bytes=2-5"})
        self.assertEqual((status, body), (206, b"2345"))
        self.assertEqual(headers["Content-Range"], "bytes 2-5/10")
        self.assertEqual(headers["Cache-Control"], "private, no-store")
        self.assertEqual(self.request("GET", "/generated/test.mp4", headers={"Range": "bytes=-2"})[2], b"89")
        self.assertEqual(self.request("GET", "/generated/test.mp4", headers={"Range": "bytes=10-"})[0], 416)
        self.assertEqual(self.request("GET", "/generated/test.mp4", headers={"Range": "bytes=-0"})[0], 416)
        self.assertEqual(self.request("HEAD", "/generated/test.mp4")[2], b"")
        for path in ("/generated/../local_backend.py", "/generated/%2e%2e/local_backend.py", "/generated/secrets.json", "/generated/job.log"):
            self.assertEqual(self.request("GET", path)[0], 404)
        (self.output / "link.mp4").symlink_to(self.output / "test.mp4")
        self.assertEqual(self.request("GET", "/generated/link.mp4")[0], 404)

    def test_reject_uploads_and_untrusted_origin(self):
        self.assertEqual(self.request("POST", "/api/assets", b"x", {"Content-Type": "text/html"})[0], 415)
        self.assertEqual(self.request("POST", "/api/assets", b"not png", {"Content-Type": "image/png"})[0], 400)
        self.assertEqual(self.request("POST", "/api/assets", b"x", {"Content-Type": "image/png", "Content-Length": str(media.MAX_UPLOAD + 1)})[0], 413)
        self.assertEqual(self.request("POST", "/api/jobs", b"{}", {"Content-Type": "application/json", "Origin": "https://untrusted.invalid"})[0], 403)

    def test_cuda_failure_and_payload_validation(self):
        with patch.object(backend, "RUNTIME", {"cuda_available": False}):
            self.assertEqual(self.request("POST", "/api/jobs", b'{"prompt":"test"}', {"Content-Type": "application/json"})[0], 503)
        for changes in ({"width": 288}, {"frames": 16}, {"mode": "v2v"}, {"audio": "false"}, {"seed": -1}, {"mode": "i2v", "image_id": "../../secret"}):
            with self.assertRaises(ValueError):
                backend.parse_payload({"prompt": "test", **changes})
        with self.assertRaises(ValueError):
            backend.parse_payload([])

    def test_progress_is_stage_based_and_partial_output_hidden(self):
        job = {"progress": 3}
        backend.update_progress(job, "Running denoising loop (8 steps)")
        backend.update_progress(job, "100%")
        self.assertEqual(job["progress"], 49)
        backend.update_progress(job, "Building video encoder + spatial upsampler")
        backend.update_progress(job, "Running denoising loop (3 steps)")
        self.assertEqual(job["phase"], "refine")
        backend.update_progress(job, "100%")
        self.assertEqual(job["progress"], 91)
        (self.output / "partial.mp4").write_bytes(b"unfinished")
        self.assertEqual(json.loads(self.request("GET", "/api/outputs")[2])["outputs"], [])


if __name__ == "__main__":
    unittest.main()
