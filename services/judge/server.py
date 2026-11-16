#!/usr/bin/env python3
"""Consistency (CJ), style (SJ) and motion (MQ) scores over loopback.

Runs in /opt/studio/venvs/vision, which holds facenet, DINOv2, CLIP and RAFT. Like the audio
service it binds 127.0.0.1 only and accepts a path only after ltx-api has resolved it from an
asset or output it owns; it never sees an account, an asset id or a URL.

**This service does not decide anything.** It returns numbers. Whether 0.62 is good enough is a
threshold, thresholds are per-model and per-material, and calibrating them is C4's job (see the
calibration section of docs/GB10_SETUP.md). A service that also judged would bake in a number
nobody measured - which is how B2 ended up with a p90 gate that two of three songs failed.

    /opt/studio/venvs/vision/bin/python services/judge/server.py
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading

HOST = os.environ.get("LTX_JUDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("LTX_JUDGE_PORT", "8791"))
SITE_ROOT = Path(os.environ.get("LTX_SITE_ROOT", Path(__file__).resolve().parents[2]))
ALLOWED_ROOTS = tuple(
    Path(item) if Path(item).is_absolute() else SITE_ROOT / item
    for item in os.environ.get("LTX_JUDGE_ROOTS", "uploads,outputs,data").split(",")
    if item.strip()
)
MAX_BODY = 256 * 1024
MAX_REFERENCES = 12
# One frame a second is enough to see a character drift; it is not enough to see motion, which is
# why MQ pairs each sample with the frame that follows it in the video rather than the next sample.
SAMPLE_FPS = float(os.environ.get("LTX_JUDGE_SAMPLE_FPS", "1"))
MAX_FRAMES = int(os.environ.get("LTX_JUDGE_MAX_FRAMES", "300"))
DEVICE = os.environ.get("LTX_JUDGE_DEVICE", "cuda")
# Same thresholds as scripts/check_output.py, on the same 32x18 grey downsample, so the ratios here
# and the ones on the release gate mean the same thing. The vision venv has no av, hence the
# second implementation rather than an import.
BLACK_MEAN, BLACK_STD, FROZEN_DELTA = 8.0, 4.0, 0.5

_models: dict = {}
_lock = threading.Lock()


def resolved_path(raw, label="path"):
    if not isinstance(raw, str) or not raw:
        raise ValueError(f"{label} is required")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = SITE_ROOT / candidate
    # resolve() first: a symlink pointing outside must fail the containment check, not pass it.
    candidate = candidate.resolve()
    if not any(candidate.is_relative_to(root.resolve()) for root in ALLOWED_ROOTS if root.exists()):
        raise ValueError(f"{label} must be inside {', '.join(r.name for r in ALLOWED_ROOTS)}")
    if not candidate.is_file():
        raise ValueError(f"{label} does not name a readable file")
    return candidate


def model(name, build):
    """Load one model once, on first use. Nothing is loaded for a request that does not ask."""
    with _lock:
        if name not in _models:
            _models[name] = build()
        return _models[name]


def face_models():
    from facenet_pytorch import MTCNN, InceptionResnetV1

    return model("face", lambda: (
        MTCNN(device=DEVICE, keep_all=False),
        InceptionResnetV1(pretrained="vggface2").eval().to(DEVICE)))


def dino_models():
    from transformers import AutoImageProcessor, AutoModel

    return model("dino", lambda: (
        AutoImageProcessor.from_pretrained("facebook/dinov2-large"),
        AutoModel.from_pretrained("facebook/dinov2-large").eval().to(DEVICE)))


def clip_models():
    import open_clip

    def build():
        net, _, preprocess = open_clip.create_model_and_transforms(
            "ViT-L-14", pretrained="openai", device=DEVICE)
        return net.eval(), preprocess
    return model("clip", build)


def raft_model():
    import torchvision

    return model("raft", lambda: torchvision.models.optical_flow.raft_large(
        weights="DEFAULT").eval().to(DEVICE))


def frames_of(path):
    """Sampled frames plus, for each, the frame that follows it in the source.

    Returns (samples, followers, meta). A still image yields one sample and no follower, so it
    scores for consistency and style and reports no motion - which is the truth about a still.
    """
    import cv2
    import numpy as np

    image = cv2.imread(str(path))
    if image is not None:
        return [image], [None], {"kind": "image", "frames_scored": 1,
                                 "fps": None, "duration_seconds": None}
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError("path is neither a readable image nor a readable video")
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or 0.0
        stride = max(1, int(round(fps / SAMPLE_FPS))) if fps > 0 else 1
        samples, followers = [], []
        black = frozen = total = 0
        previous_small = None
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            total += 1
            small = cv2.cvtColor(cv2.resize(frame, (32, 18)), cv2.COLOR_BGR2GRAY).astype(np.float32)
            black += int(small.mean() < BLACK_MEAN and small.std() < BLACK_STD)
            frozen += int(previous_small is not None
                          and float(np.abs(small - previous_small).mean()) < FROZEN_DELTA)
            previous_small = small
            if index % stride == 0 and len(samples) < MAX_FRAMES:
                samples.append(frame)
                follow_ok, follow = capture.read()
                followers.append(follow if follow_ok else None)
                if follow_ok:
                    total += 1
                    index += 1
                    small = cv2.cvtColor(cv2.resize(follow, (32, 18)),
                                         cv2.COLOR_BGR2GRAY).astype(np.float32)
                    black += int(small.mean() < BLACK_MEAN and small.std() < BLACK_STD)
                    frozen += int(float(np.abs(small - previous_small).mean()) < FROZEN_DELTA)
                    previous_small = small
            index += 1
        meta = {"kind": "video", "frames_scored": len(samples), "fps": round(fps, 3) or None,
                "frames_decoded": total,
                "duration_seconds": round(total / fps, 3) if fps > 0 else None,
                "black_ratio": round(black / total, 4) if total else None,
                "frozen_ratio": round(frozen / max(1, total - 1), 4) if total else None}
        return samples, followers, meta
    finally:
        capture.release()


def unit(vector):
    import torch

    return torch.nn.functional.normalize(vector.flatten().unsqueeze(0), dim=1)


def face_vector(bgr):
    """A face embedding, or None when no face is found. None is a fact, not a failure."""
    import cv2
    import torch
    from PIL import Image

    detector, encoder = face_models()
    with torch.no_grad():
        cropped = detector(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        if cropped is None:
            return None
        return unit(encoder(cropped.unsqueeze(0).to(DEVICE)))


def dino_vector(bgr):
    import cv2
    import torch
    from PIL import Image

    processor, encoder = dino_models()
    with torch.no_grad():
        inputs = processor(images=Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)),
                           return_tensors="pt").to(DEVICE)
        return unit(encoder(**inputs).last_hidden_state[:, 0])


def clip_vector(bgr):
    import cv2
    import torch
    from PIL import Image

    net, preprocess = clip_models()
    with torch.no_grad():
        tensor = preprocess(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
        return unit(net.encode_image(tensor.unsqueeze(0).to(DEVICE)))


def best_similarity(vector, references):
    """Highest cosine similarity against any reference. Max, not mean: a character seen from
    behind in one reference and face-on in another should score on whichever matches."""
    import torch

    if vector is None or not references:
        return None
    return max(float(torch.mm(vector, reference.t()).item()) for reference in references)


def consistency(samples, reference_paths):
    """CJ. Face where there is one, DINOv2 where there is not, and it says which per frame."""
    import cv2

    if not reference_paths:
        return None
    face_references, dino_references = [], []
    for path in reference_paths:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"reference {path.name} is not a readable image")
        vector = face_vector(image)
        if vector is not None:
            face_references.append(vector)
        dino_references.append(dino_vector(image))

    per_frame, methods = [], []
    for frame in samples:
        vector = face_vector(frame) if face_references else None
        if vector is not None:
            per_frame.append(best_similarity(vector, face_references))
            methods.append("face_facenet")
        else:
            per_frame.append(best_similarity(dino_vector(frame), dino_references))
            methods.append("dinov2_large")
    return {"per_frame": [round(v, 4) for v in per_frame],
            "method_per_frame": methods,
            "median": median(per_frame),
            "faces_found": methods.count("face_facenet"),
            "reference_faces": len(face_references),
            "references": len(dino_references)}


def style(samples, anchor_path):
    """SJ. CLIP similarity to one style anchor."""
    import cv2

    if anchor_path is None:
        return None
    anchor_image = cv2.imread(str(anchor_path))
    if anchor_image is None:
        raise ValueError("style_anchor_path is not a readable image")
    anchor = clip_vector(anchor_image)
    per_frame = [best_similarity(clip_vector(frame), [anchor]) for frame in samples]
    return {"per_frame": [round(v, 4) for v in per_frame], "median": median(per_frame)}


def motion(samples, followers):
    """MQ. RAFT flow magnitude between each sample and the frame right after it.

    Measuring flow between samples a second apart would report displacement over a second and
    call it motion quality. Pairing each sample with its immediate successor measures what the
    video actually does between two frames.
    """
    import cv2
    import numpy as np
    import torch
    import torchvision.transforms.functional as F

    pairs = [(a, b) for a, b in zip(samples, followers) if b is not None]
    if not pairs:
        return None
    net = raft_model()
    magnitudes = []
    with torch.no_grad():
        for first, second in pairs:
            batch = []
            for frame in (first, second):
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                tensor = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
                # RAFT needs both sides divisible by 8, and normalised to [-1, 1].
                height = tensor.shape[1] - tensor.shape[1] % 8
                width = tensor.shape[2] - tensor.shape[2] % 8
                batch.append(F.normalize(tensor[:, :height, :width], mean=[0.5] * 3, std=[0.5] * 3))
            flow = net(batch[0].unsqueeze(0).to(DEVICE), batch[1].unsqueeze(0).to(DEVICE))[-1]
            magnitudes.append(float(torch.linalg.vector_norm(flow, dim=1).mean().item()))
    array = np.array(magnitudes)
    return {"per_pair": [round(v, 4) for v in magnitudes],
            "mean": round(float(array.mean()), 4),
            "median": round(float(np.median(array)), 4),
            "p90": round(float(np.percentile(array, 90, method="nearest")), 4),
            "max": round(float(array.max()), 4),
            "method": "raft_large"}


def median(values):
    import statistics

    usable = [v for v in values if v is not None]
    return round(statistics.median(usable), 4) if usable else None


def score(payload):
    media = resolved_path(payload.get("media_path"), "media_path")
    raw_references = payload.get("references") or []
    if not isinstance(raw_references, list) or len(raw_references) > MAX_REFERENCES:
        raise ValueError(f"references must be a list of at most {MAX_REFERENCES} paths")
    references = [resolved_path(item, "references[]") for item in raw_references]
    anchor = payload.get("style_anchor_path")
    anchor_path = resolved_path(anchor, "style_anchor_path") if anchor else None

    samples, followers, meta = frames_of(media)
    return {"media": meta,
            "consistency": consistency(samples, references),
            "style": style(samples, anchor_path),
            "motion": motion(samples, followers),
            "scored_by": "ltx-judge/1.0"}


class Handler(BaseHTTPRequestHandler):
    server_version = "LTXJudge/1.0"

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        sys.stderr.write("[ltx-judge] %s\n" % (fmt % args))

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
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
            self.send_json(200, {"ok": True, "service": "ltx-judge",
                                 "loaded": sorted(_models), "device": DEVICE})
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):  # noqa: N802
        try:
            if self.path != "/score":
                self.send_json(404, {"error": "Not found"})
                return
            self.send_json(200, score(self.body()))
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)[:300], "code": "invalid_request"})
        except MemoryError:
            self.send_json(503, {"error": "Not enough memory to score this media",
                                 "code": "unavailable"})
        except Exception as exc:  # noqa: BLE001 - one bad file must not take the service down
            self.log_message("scoring failed: %s", str(exc)[:200])
            self.send_json(500, {"error": "Scoring failed", "code": "scoring_failed"})


def main():
    if HOST not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit(f"Refusing to bind {HOST}: this service is loopback-only.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"LTX judge service: http://{HOST}:{PORT} (roots: "
          f"{', '.join(str(r) for r in ALLOWED_ROOTS)})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
