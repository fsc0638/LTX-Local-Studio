"""One GPU, two heavy tenants: LTX video and the imagegen service.

The job queue already runs one job at a time, so two *jobs* never overlap. What the queue does
not see is memory held between jobs: the imagegen service keeps its model resident for a while
after a request (61 GB for Qwen), and an LTX job started into that is how the machine goes out of
memory. The lease is the one place that is decided.

- Before an LTX job runs, the imagegen model is evicted (POST /release) and the lease waits until
  the service reports nothing loaded. A service that is not running holds nothing.
- Before an imagegen job runs, no LTX job may be active - the queue already guarantees it, and
  the lease checks anyway, because the guarantee lives in another module.
- The judge, audio and post services are not tenants: they are small, and were sized to sit
  beside either of the two.

Nothing here talks to the GPU. It talks to the imagegen service over loopback and to the job
table through a callback, so the tests can stand up a fake service and a fake job table.
"""
import json
import threading
import time
import urllib.error
import urllib.request

TENANTS = ("ltx", "imagegen")


class LeaseRefused(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class GpuLease:
    def __init__(self, imagegen_url, ltx_active, *, evict_timeout=120.0, poll=0.5):
        self.imagegen_url = imagegen_url.rstrip("/")
        self.ltx_active = ltx_active            # () -> bool: is an LTX job queued or running?
        self.evict_timeout = evict_timeout
        self.poll = poll
        self._lock = threading.Lock()
        self.holder = None
        self.history = []                      # (time, event, detail) - the last few handovers

    # ---- the imagegen service, seen from here ----

    def _call(self, path, *, post=False, timeout=10):
        request = urllib.request.Request(
            f"{self.imagegen_url}{path}", data=b"{}" if post else None,
            headers={"Content-Type": "application/json"} if post else {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)

    def imagegen_loaded(self):
        """Model ids the service holds, or [] when it is down: a service that is not running
        cannot be holding memory."""
        try:
            return list(self._call("/health").get("loaded") or [])
        except (OSError, ValueError, urllib.error.URLError):
            return []

    def evict_imagegen(self):
        """Ask the service to drop its model and wait until it says it has.

        Returns (evicted, seconds). The flag is separate from the time because a fake or a fast
        service can release in less than a rounding step, and "it was quick" must not read as
        "it never happened".
        """
        started = time.monotonic()
        if not self.imagegen_loaded():
            return False, 0.0
        try:
            self._call("/release", post=True, timeout=60)
        except (OSError, ValueError, urllib.error.URLError):
            pass  # if it is gone, it holds nothing; if it is stuck, the wait below says so
        while self.imagegen_loaded():
            if time.monotonic() - started > self.evict_timeout:
                raise LeaseRefused("gpu_lease_timeout",
                                   "The image service did not release the GPU in time")
            time.sleep(self.poll)
        return True, round(time.monotonic() - started, 2)

    # ---- the lease ----

    def acquire(self, tenant):
        if tenant not in TENANTS:
            raise ValueError(f"unknown tenant {tenant}")
        with self._lock:
            if self.holder is not None and self.holder != tenant:
                # The queue should have made this impossible; refusing is cheaper than an OOM.
                raise LeaseRefused("worker_busy", f"GPU is held by {self.holder}")
            if tenant == "imagegen" and self.ltx_active():
                raise LeaseRefused("worker_busy", "An LTX job is active; the image service must wait")
            if tenant == "ltx":
                evicted, waited = self.evict_imagegen()
                if evicted:
                    self._note("evicted imagegen", f"{waited}s")
            self.holder = tenant
            self._note("acquired", tenant)
        return tenant

    def release(self, tenant):
        with self._lock:
            if self.holder == tenant:
                self.holder = None
                self._note("released", tenant)

    def _note(self, event, detail):
        self.history = (self.history + [(time.time(), event, detail)])[-20:]

    def describe(self):
        with self._lock:
            return {"holder": self.holder, "imagegen_loaded": self.imagegen_loaded(),
                    "ltx_active": bool(self.ltx_active()),
                    "history": [{"at": at, "event": e, "detail": d} for at, e, d in self.history]}
