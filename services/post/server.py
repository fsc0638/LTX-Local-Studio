#!/usr/bin/env python3
"""Post tools (VX) over loopback: upscale with Real-ESRGAN, clean with LaMa, interpolate with RIFE.

Runs in /opt/studio/venvs/vision, which holds realesrgan, basicsr and simple-lama-inpainting.
Like the other services it binds 127.0.0.1 only and touches only paths ltx-api resolved: the
input is a take under data/, the mask an asset under uploads/, the output under data/.

Frames move through ffmpeg and PIL, not through cv2's video writer: ffmpeg is on the host, keeps
the source's frame rate and audio exactly, and encodes what the technical check will decode.
The models see one PNG at a time.

RIFE needs weights the author publishes by download link (see infra/gb10/50-post.sh). Until they
sit in /opt/studio/tools/rife/train_log, /process refuses "interpolate" with rife_weights_missing
so a caller learns why rather than getting a job that dies half way.

    /opt/studio/venvs/vision/bin/python services/post/server.py

LTX_POST_FAKE=1 swaps the models for PIL stand-ins (resize, blur inside the mask, duplicate
frames). That is for the test suite; it is never what the unit file runs.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid

HOST = os.environ.get("LTX_POST_HOST", "127.0.0.1")
PORT = int(os.environ.get("LTX_POST_PORT", "8793"))
SITE_ROOT = Path(os.environ.get("LTX_SITE_ROOT", Path(__file__).resolve().parents[2]))
INPUT_ROOTS = (SITE_ROOT / "data",)
MASK_ROOTS = (SITE_ROOT / "uploads", SITE_ROOT / "data")
OUTPUT_ROOTS = (SITE_ROOT / "data",)
FAKE = os.environ.get("LTX_POST_FAKE") == "1"
DEVICE = os.environ.get("LTX_POST_DEVICE", "cuda")
FFMPEG = os.environ.get("LTX_FFMPEG", "ffmpeg")
ESRGAN_WEIGHTS = Path(os.environ.get("STUDIO_REALESRGAN_WEIGHTS", "/opt/studio/models/realesrgan/RealESRGAN_x4plus.pth"))
RIFE_ROOT = Path(os.environ.get("STUDIO_RIFE_ROOT", "/opt/studio/tools/rife"))
RIFE_WEIGHTS = RIFE_ROOT / "train_log"
MAX_BODY = 64 * 1024
OPS = ("upscale", "clean", "interpolate")

_models: dict = {}
_lock = threading.Lock()
_work_lock = threading.Lock()   # one video at a time: these tools are memory-heavy per frame
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


def rife_available():
    return RIFE_WEIGHTS.is_dir() and any(RIFE_WEIGHTS.iterdir())


def model(name, build):
    with _lock:
        if name not in _models:
            _models[name] = build()
        return _models[name]


def upscaler(scale):
    from realesrgan import RealESRGANer
    from basicsr.archs.rrdbnet_arch import RRDBNet

    def build():
        net = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        # tile keeps a 720p frame within a few GB instead of the whole frame at once.
        return RealESRGANer(scale=4, model_path=str(ESRGAN_WEIGHTS), model=net, tile=512, tile_pad=16,
                            half=True, device=DEVICE)
    return model("esrgan", build)


def inpainter():
    from simple_lama_inpainting import SimpleLama

    return model("lama", lambda: SimpleLama(device=DEVICE))


def probe(path):
    """Frame rate, frame count, size and whether there is audio, from ffprobe."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames",
                          "-of", "json", str(path)], capture_output=True, text=True, timeout=120, check=False)
    if out.returncode != 0:
        raise ValueError("input is not a readable video")
    stream = json.loads(out.stdout)["streams"][0]
    num, _, den = str(stream["r_frame_rate"]).partition("/")
    fps = float(num) / float(den or 1)
    audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, timeout=60, check=False)
    return {"width": int(stream["width"]), "height": int(stream["height"]), "fps": fps,
            "frames": int(stream.get("nb_read_frames") or 0), "audio": bool(audio.stdout.strip())}


def extract_frames(path, folder):
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(path), str(folder / "f%06d.png")],
                   check=True, timeout=1800)
    return sorted(folder.glob("f*.png"))


def encode(frames_folder, fps, output, audio_source):
    command = [FFMPEG, "-v", "error", "-y", "-framerate", f"{fps:.6f}", "-i", str(frames_folder / "f%06d.png")]
    if audio_source:
        # No -shortest: the worker's audio track can run a frame shorter than its video, and the
        # technical check counts frames, so the video decides the length and the audio is muxed as is.
        command += ["-i", str(audio_source), "-map", "0:v:0", "-map", "1:a:0?", "-c:a", "aac"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", "-r", f"{fps:.6f}", "-movflags", "+faststart", str(output)]
    subprocess.run(command, check=True, timeout=3600)


def op_upscale(frames, folder, scale, report):
    from PIL import Image
    import numpy as np

    for index, frame in enumerate(frames):
        image = Image.open(frame).convert("RGB")
        if FAKE:
            out = image.resize((image.width * scale, image.height * scale), Image.BICUBIC)
        else:
            enhanced, _ = upscaler(scale).enhance(np.array(image)[:, :, ::-1], outscale=scale)
            out = Image.fromarray(enhanced[:, :, ::-1])
        out.save(frame, "PNG")
        report(index + 1, len(frames))


def op_clean(frames, folder, mask_path, report):
    from PIL import Image, ImageFilter

    mask = Image.open(mask_path).convert("L")
    for index, frame in enumerate(frames):
        image = Image.open(frame).convert("RGB")
        m = mask.resize(image.size, Image.NEAREST)
        if FAKE:
            filled = image.filter(ImageFilter.GaussianBlur(12))
            out = Image.composite(filled, image, m)
        else:
            out = inpainter()(image, m).convert("RGB").resize(image.size)
        out.save(frame, "PNG")
        report(index + 1, len(frames))


def op_interpolate(path, folder, source, target_fps, report):
    """Double (or more) the frame rate with RIFE. Refused without weights."""
    if not rife_available():
        raise PermissionError("rife_weights_missing")
    if FAKE:
        from PIL import Image
        frames = sorted(folder.glob("f*.png"))
        factor = max(1, round(target_fps / source["fps"]))
        out_folder = folder / "interp"
        out_folder.mkdir()
        n = 0
        for frame in frames:
            for _ in range(factor):
                n += 1
                shutil.copyfile(frame, out_folder / f"f{n:06d}.png")
        report(1, 1)
        return out_folder
    # Practical-RIFE writes a video; ask it for the multiplier and re-extract to keep one encoder.
    factor = max(2, round(target_fps / source["fps"]))
    interp = folder / "rife.mp4"
    subprocess.run([sys.executable, str(RIFE_ROOT / "inference_video.py"), f"--multi={factor}",
                    f"--video={path}", f"--output={interp}", f"--model={RIFE_WEIGHTS}"],
                   cwd=str(RIFE_ROOT), check=True, timeout=3600)
    out_folder = folder / "interp"
    out_folder.mkdir()
    extract_frames(interp, out_folder)
    report(1, 1)
    return out_folder


def process(payload):
    op = payload.get("op")
    if op not in OPS:
        raise ValueError("op must be one of " + ", ".join(OPS))
    source_path = contained(payload.get("input"), INPUT_ROOTS, "input")
    output = contained(payload.get("output"), OUTPUT_ROOTS, "output", must_exist=False)
    if output.suffix.lower() != ".mp4":
        raise ValueError("output must be a .mp4 path")
    scale = payload.get("scale", 2)
    if op == "upscale" and (type(scale) is not int or scale not in (2, 4)):
        raise ValueError("scale must be 2 or 4")
    target_fps = payload.get("target_fps")
    if op == "interpolate" and (type(target_fps) not in (int, float) or not 1 < target_fps <= 120):
        raise ValueError("target_fps must be between 1 and 120")
    mask_path = contained(payload.get("mask"), MASK_ROOTS, "mask") if op == "clean" else None
    if op == "clean" and mask_path is None:
        raise ValueError("clean needs a mask")
    if op == "interpolate" and not rife_available():
        raise PermissionError("rife_weights_missing")
    request_id = str(payload.get("request_id") or uuid.uuid4().hex)
    _progress[request_id] = {"phase": "waiting", "progress": 0}

    with _work_lock:
        started = time.time()
        source = probe(source_path)
        _progress[request_id] = {"phase": "extracting", "progress": 3}
        with tempfile.TemporaryDirectory(dir=str(output.parent), prefix=".post-") as tmp:
            folder = Path(tmp)
            frames = extract_frames(source_path, folder)
            if not frames:
                raise ValueError("input has no frames")

            def report(done, total):
                _progress[request_id] = {"phase": op, "progress": 5 + round(85 * done / max(1, total))}

            fps = source["fps"]
            frames_folder = folder
            if op == "upscale":
                op_upscale(frames, folder, scale, report)
            elif op == "clean":
                op_clean(frames, folder, mask_path, report)
            else:
                frames_folder = op_interpolate(source_path, folder, source, target_fps, report)
                fps = float(target_fps)
            _progress[request_id] = {"phase": "encoding", "progress": 92}
            output.parent.mkdir(parents=True, exist_ok=True)
            encode(frames_folder, fps, output, source_path if source["audio"] else None)
        result = probe(output)
        _progress[request_id] = {"phase": "done", "progress": 100}
        return {"output": str(output), "op": op, "seconds": round(time.time() - started, 2),
                "source": source, "result": result, "request_id": request_id}


def status():
    return {"ok": True, "service": "ltx-post", "fake": FAKE, "loaded": sorted(_models),
            "ops": list(OPS), "rife_available": rife_available(),
            "esrgan_weights": ESRGAN_WEIGHTS.is_file(), "device": DEVICE}


class Handler(BaseHTTPRequestHandler):
    server_version = "LTXPost/1.0"

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        sys.stderr.write("[ltx-post] %s\n" % (fmt % args))

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
            self.send_json(200, _progress.get(self.path.rsplit("/", 1)[-1], {"phase": "unknown", "progress": 0}))
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):  # noqa: N802
        try:
            if self.path != "/process":
                self.send_json(404, {"error": "Not found"})
                return
            self.send_json(200, process(self.body()))
        except PermissionError as exc:
            self.send_json(503, {"error": "RIFE weights are not installed", "code": str(exc)})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)[:300], "code": "invalid_request"})
        except subprocess.CalledProcessError as exc:
            self.log_message("tool failed: %s", str(exc)[:200])
            self.send_json(500, {"error": "A post tool failed", "code": "tool_failed"})
        except MemoryError:
            self.send_json(503, {"error": "Not enough memory", "code": "unavailable"})
        except Exception as exc:  # noqa: BLE001 - one bad file must not take the service down
            self.log_message("processing failed: %s", str(exc)[:200])
            self.send_json(500, {"error": "Processing failed", "code": "processing_failed"})


def main():
    if HOST not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit(f"Refusing to bind {HOST}: this service is loopback-only.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"LTX post service: http://{HOST}:{PORT} (fake={FAKE}, rife={'yes' if rife_available() else 'no weights'})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
