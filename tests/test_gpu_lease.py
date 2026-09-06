"""D1: the GPU lease, against a fake imagegen service and a fake job table.

What is proved: an LTX job evicts a resident imagegen model and waits for it to be gone; an
imagegen job is refused while an LTX job is active; a service that is down holds nothing; a
service that will not let go times out instead of letting LTX start into it.
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import gpu_lease


class FakeImagegen:
    """Records /release calls; `loaded` is what /health reports; `stuck` ignores releases."""

    def __init__(self):
        self.loaded = []
        self.releases = 0
        self.stuck = False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: A002
                pass

            def send(self, payload):
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                self.send({"ok": True, "loaded": fake.loaded})

            def do_POST(self):  # noqa: N802
                fake.releases += 1
                if not fake.stuck:
                    fake.loaded = []
                self.send({"released": True, "loaded": fake.loaded})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeImagegen()
        self.addCleanup(self.fake.close)
        self.ltx_active = False
        self.lease = gpu_lease.GpuLease(self.fake.url, lambda: self.ltx_active, evict_timeout=2, poll=0.05)

    def test_an_ltx_job_evicts_the_resident_image_model_and_waits_for_it(self):
        self.fake.loaded = ["qwen-image-edit-2509"]
        self.assertEqual(self.lease.acquire("ltx"), "ltx")
        self.assertEqual(self.fake.releases, 1)
        self.assertEqual(self.fake.loaded, [])
        self.assertEqual(self.lease.holder, "ltx")
        self.assertEqual(self.lease.history[0][1], "evicted imagegen")

    def test_nothing_loaded_means_nothing_to_evict(self):
        self.lease.acquire("ltx")
        self.assertEqual(self.fake.releases, 0)

    def test_a_service_that_is_down_holds_nothing(self):
        lease = gpu_lease.GpuLease("http://127.0.0.1:9", lambda: False, evict_timeout=1, poll=0.05)
        self.assertEqual(lease.acquire("ltx"), "ltx")
        self.assertEqual(lease.imagegen_loaded(), [])

    def test_a_service_that_will_not_let_go_stops_ltx_from_starting(self):
        self.fake.loaded = ["qwen-image-edit-2509"]
        self.fake.stuck = True
        with self.assertRaises(gpu_lease.LeaseRefused) as refused:
            self.lease.acquire("ltx")
        self.assertEqual(refused.exception.code, "gpu_lease_timeout")
        self.assertIsNone(self.lease.holder, "a refused lease is not held")

    def test_an_image_job_is_refused_while_ltx_is_active(self):
        self.ltx_active = True
        with self.assertRaises(gpu_lease.LeaseRefused) as refused:
            self.lease.acquire("imagegen")
        self.assertEqual(refused.exception.code, "worker_busy")
        self.ltx_active = False
        self.assertEqual(self.lease.acquire("imagegen"), "imagegen")

    def test_the_lease_hands_over_only_after_release(self):
        self.lease.acquire("imagegen")
        with self.assertRaises(gpu_lease.LeaseRefused):
            self.lease.acquire("ltx")
        self.lease.release("imagegen")
        self.assertEqual(self.lease.acquire("ltx"), "ltx")
        # Releasing a tenant that does not hold it changes nothing.
        self.lease.release("imagegen")
        self.assertEqual(self.lease.holder, "ltx")

    def test_reacquiring_as_the_same_tenant_is_allowed(self):
        self.lease.acquire("ltx")
        self.assertEqual(self.lease.acquire("ltx"), "ltx")

    def test_describe_is_what_the_loopback_endpoint_shows(self):
        self.fake.loaded = ["z-image-turbo"]
        state = self.lease.describe()
        self.assertEqual(state["imagegen_loaded"], ["z-image-turbo"])
        self.assertIsNone(state["holder"])
        self.assertFalse(state["ltx_active"])

    def test_unknown_tenants_are_rejected(self):
        with self.assertRaises(ValueError):
            self.lease.acquire("judge")


if __name__ == "__main__":
    unittest.main()
