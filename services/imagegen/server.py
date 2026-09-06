#!/usr/bin/env python3
"""Image generation (Qwen-Image-Edit-2509, Z-Image-Turbo) over loopback.

Runs in /opt/studio/venvs/imagegen. Like the audio and judge services it binds 127.0.0.1 only and
touches only paths ltx-api resolved for it: references under uploads/ or data/, output under
data/. It never sees an asset id, an account or a URL.

One model is resident at a time. Qwen-Image-Edit is 61 GB and Z-Image 23 GB; the machine has
128 GB shared with LTX, so loading the second alongside the first is how an OOM starts. Loading
one unloads the other. After LTX_IMAGEGEN_IDLE_MINUTES without a request the resident model is
released, and ltx-api can ask for that early with POST /release before it starts an LTX job.

    /opt/studio/venvs/imagegen/bin/python services/imagegen/server.py

LTX_IMAGEGEN_FAKE=1 swaps the pipelines for a stub that paints a flat PNG. That is for the test
suite and for exercising the lease without 61 GB; it is never what the unit file runs.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

HOST = os.environ.get("LTX_IMAGEGEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("LTX_IMAGEGEN_PORT", "8792"))
SITE_ROOT = Path(os.environ.get("LTX_SITE_ROOT", Path(__file__).resolve().parents[2]))
REFERENCE_ROOTS = (SITE_ROOT / "uploads", SITE_ROOT / "data")
OUTPUT_ROOTS = (SITE_ROOT / "data",)
IDLE_SECONDS = float(os.environ.get("LTX_IMAGEGEN_IDLE_MINUTES", "10")) * 60
DEVICE = os.environ.get("LTX_IMAGEGEN_DEVICE", "cuda")
FAKE = os.environ.get("LTX_IMAGEGEN_FAKE") == "1"
# ltx-api answers on loopback whether any job is queued or running. Loading 61 GB into a GPU
# that an LTX job is using is the one thing this service must never do, so it asks first.
API_URL = os.environ.get("LTX_API_URL", "http://127.0.0.1:8787")
MAX_BODY = 64 * 1024
LIGHTNING_LORA = os.environ.get(
    "LTX_QWEN_LIGHTNING",
    "lightx2v/Qwen-Image-Lightning:Qwen-Image-Edit-2509/Qwen-Image-Edit-2509-Lightning-8steps-V1.0-bf16.safetensors")

MODELS = {
    # Edit: references in, image out. Lightning LoRA makes 8 steps enough.
    "qwen-image-edit-2509": {"repo": "Qwen/Qwen-Image-Edit-2509", "kind": "edit", "min_references": 1},
    # Text to image, already distilled: no LoRA, no references.
    "z-image-turbo": {"repo": "Tongyi-MAI/Z-Image-Turbo", "kind": "t2i", "min_references": 0},
}
SIZES = {"1024x1024": (1024, 1024), "1280x720": (1280, 720), "720x1280": (720, 1280),
         "1536x864": (1536, 864), "864x1536": (864, 1536)}

_state = {"model": None, "pipeline": None, "loaded_at": None, "last_used": time.time(),
          "busy": False, "loads": 0}
_lock = threading.Lock()          # who may touch the pipeline
_generate_lock = threading.Lock() # one image at a time; a second request waits, it does not OOM
_progress: dict = {}


def contained(raw, roots, label, must_exist=True):
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{label} is required")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = SITE_ROOT / candidate
    candidate = candidate.resolve()  # resolve first: a symlink out of the tree must fail, not pass
    if not any(candidate.is_relative_to(root.resolve()) for root in roots if root.exists()):
        raise ValueError(f"{label} must be inside {', '.join(r.name for r in roots)}")
    if must_exist and not candidate.is_file():
        raise ValueError(f"{label} does not name a readable file")
    return candidate


def unload(reason):
    """Drop the resident model and give the memory back. Idempotent."""
    with _lock:
        if _state["pipeline"] is None:
            return False
        name = _state["model"]
        _state.update(model=None, pipeline=None, loaded_at=None)
    if not FAKE:
        import gc
        import torch

        gc.collect()
        torch.cuda.empty_cache()
    sys.stderr.write(f"[ltx-imagegen] unloaded {name} ({reason})\n")
    return True


def ltx_jobs_active():
    """Ask ltx-api. Unreachable means unknown, and unknown is treated as busy: the cost of a
    wrong "free" is an OOM, the cost of a wrong "busy" is a retry."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"{API_URL}/api/internal/active-jobs", timeout=5) as response:
            return int(json.load(response).get("count", 0)) > 0
    except (OSError, ValueError):
        return True


def load(model_id):
    """Make `model_id` the resident pipeline, unloading whatever was there. Returns the pipeline."""
    with _lock:
        if _state["model"] == model_id and _state["pipeline"] is not None:
            return _state["pipeline"]
    if not FAKE and os.environ.get("LTX_IMAGEGEN_SKIP_ACTIVE_CHECK") != "1" and ltx_jobs_active():
        raise ValueError("An LTX job is active; refusing to load a model beside it")
    unload("switching model")
    spec = MODELS[model_id]
    started = time.time()
    if FAKE:
        pipeline = FakePipeline(model_id)
    else:
        import torch
        from diffusers import QwenImageEditPlusPipeline, ZImagePipeline

        if spec["kind"] == "edit":
            pipeline = QwenImageEditPlusPipeline.from_pretrained(spec["repo"], torch_dtype=torch.bfloat16)
            repo, _, filename = LIGHTNING_LORA.partition(":")
            pipeline.load_lora_weights(repo, weight_name=filename)
            pipeline.fuse_lora()
        else:
            pipeline = ZImagePipeline.from_pretrained(spec["repo"], torch_dtype=torch.bfloat16)
        pipeline.to(DEVICE)
        pipeline.set_progress_bar_config(disable=True)
    with _lock:
        _state.update(model=model_id, pipeline=pipeline, loaded_at=time.time(), loads=_state["loads"] + 1)
    sys.stderr.write(f"[ltx-imagegen] loaded {model_id} in {time.time() - started:.1f}s\n")
    return pipeline


class FakePipeline:
    """Paints a flat image whose colour follows the seed. Enough to prove the plumbing."""

    def __init__(self, model_id):
        self.model_id = model_id

    def __call__(self, *, prompt, width, height, num_inference_steps, generator_seed, images, on_step):
        from PIL import Image

        for step in range(num_inference_steps):
            on_step(step + 1, num_inference_steps)
        shade = (generator_seed * 37) % 200 + 30
        return Image.new("RGB", (width, height), (shade, 90, 140))


def generate(payload):
    model_id = payload.get("model")
    if model_id not in MODELS:
        raise ValueError("model must be one of " + ", ".join(MODELS))
    spec = MODELS[model_id]
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
        raise ValueError("prompt must contain 1-4000 characters")
    steps = payload.get("steps", 8)
    if type(steps) is not int or not 1 <= steps <= 50:
        raise ValueError("steps must be 1-50")
    seed = payload.get("seed", 42)
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError("seed must be a non-negative 31-bit integer")
    size = payload.get("size", "1024x1024")
    if size not in SIZES:
        raise ValueError("size must be one of " + ", ".join(SIZES))
    raw_refs = payload.get("references") or []
    if not isinstance(raw_refs, list) or len(raw_refs) > 3:
        raise ValueError("references must be a list of at most 3 paths")
    references = [contained(item, REFERENCE_ROOTS, "references[]") for item in raw_refs]
    if len(references) < spec["min_references"]:
        raise ValueError(f"{model_id} needs at least {spec['min_references']} reference image")
    output = contained(payload.get("output"), OUTPUT_ROOTS, "output", must_exist=False)
    if output.suffix.lower() != ".png":
        raise ValueError("output must be a .png path")
    request_id = str(payload.get("request_id") or uuid.uuid4().hex)
    width, height = SIZES[size]

    _progress[request_id] = {"phase": "waiting", "progress": 0}
    with _generate_lock:
        _progress[request_id] = {"phase": "loading", "progress": 2}
        with _lock:
            _state["busy"] = True
        try:
            pipeline = load(model_id)
            _progress[request_id] = {"phase": "generating", "progress": 5}

            def on_step(step, total):
                _progress[request_id] = {"phase": "generating", "progress": 5 + round(90 * step / total)}

            started = time.time()
            if FAKE:
                image = pipeline(prompt=prompt, width=width, height=height, num_inference_steps=steps,
                                 generator_seed=seed, images=references, on_step=on_step)
            else:
                import torch
                from PIL import Image

                generator = torch.Generator(device=DEVICE).manual_seed(seed)

                def callback(pipe, step, timestep, kwargs):
                    on_step(step + 1, steps)
                    return kwargs

                if spec["kind"] == "edit":
                    images = [Image.open(path).convert("RGB") for path in references]
                    result = pipeline(image=images, prompt=prompt, num_inference_steps=steps,
                                      true_cfg_scale=1.0, height=height, width=width, generator=generator,
                                      callback_on_step_end=callback)
                else:
                    result = pipeline(prompt=prompt, num_inference_steps=steps, guidance_scale=0.0,
                                      height=height, width=width, generator=generator,
                                      callback_on_step_end=callback)
                image = result.images[0]
            output.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(output), "PNG")
            _progress[request_id] = {"phase": "done", "progress": 100}
            with _lock:
                _state["last_used"] = time.time()
            return {"output": str(output), "model": model_id, "seconds": round(time.time() - started, 2),
                    "loads": _state["loads"], "request_id": request_id}
        finally:
            with _lock:
                _state["busy"] = False


def idle_watch():
    """Release the resident model after IDLE_SECONDS without a request."""
    while True:
        time.sleep(15)
        with _lock:
            idle = time.time() - _state["last_used"]
            loaded = _state["pipeline"] is not None and not _state["busy"]
        if loaded and idle >= IDLE_SECONDS:
            unload(f"idle {idle / 60:.1f} min")


def status():
    with _lock:
        return {"ok": True, "service": "ltx-imagegen", "fake": FAKE,
                "loaded": [_state["model"]] if _state["pipeline"] is not None else [],
                "busy": _state["busy"], "loads": _state["loads"],
                "idle_seconds": round(time.time() - _state["last_used"], 1),
                "idle_limit_seconds": IDLE_SECONDS, "models": sorted(MODELS), "sizes": sorted(SIZES)}


class Handler(BaseHTTPRequestHandler):
    server_version = "LTXImagegen/1.0"

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        sys.stderr.write("[ltx-imagegen] %s\n" % (fmt % args))

    def send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_BODY:
            raise ValueError(f"body must be 1-{MAX_BODY} bytes")
        raw = json.loads(self.rfile.read(length))
        if not isinstance(raw, dict):
            raise ValueError("body must be a JSON object")
        return raw

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self.send_json(200, status())
            return
        if self.path.startswith("/progress/"):
            request_id = self.path.rsplit("/", 1)[-1]
            self.send_json(200, _progress.get(request_id, {"phase": "unknown", "progress": 0}))
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):  # noqa: N802
        try:
            if self.path == "/generate":
                self.send_json(200, generate(self.body()))
            elif self.path == "/release":
                self.send_json(200, {"released": unload("released by ltx-api"), **status()})
            else:
                self.send_json(404, {"error": "Not found"})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)[:300], "code": "invalid_request"})
        except MemoryError:
            unload("out of memory")
            self.send_json(503, {"error": "Not enough memory", "code": "unavailable"})
        except Exception as exc:  # noqa: BLE001 - one bad request must not take the service down
            self.log_message("generation failed: %s", str(exc)[:200])
            self.send_json(500, {"error": "Generation failed", "code": "generation_failed"})


def main():
    if HOST not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit(f"Refusing to bind {HOST}: this service is loopback-only.")
    threading.Thread(target=idle_watch, name="idle-watch", daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"LTX imagegen service: http://{HOST}:{PORT} (fake={FAKE}, idle {IDLE_SECONDS / 60:.0f} min)",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        unload("shutdown")
        server.server_close()


if __name__ == "__main__":
    main()
