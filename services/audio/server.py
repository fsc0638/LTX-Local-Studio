#!/usr/bin/env python3
"""Music analysis (MA) and lyric sync (LS) over loopback.

Runs in /opt/studio/venvs/audio, which holds librosa and stable-ts. Nothing here is reachable
from outside the machine: it binds 127.0.0.1 only and accepts a path only after ltx-api has
resolved it from an asset id it owns. The service never sees an asset id, an account, or a URL.

Deliberately built on http.server rather than a web framework. local_backend.py already serves
its API that way, and the audio venv carries several gigabytes of model weights that should not
also carry a dependency tree for two endpoints.

    /opt/studio/venvs/audio/bin/python services/audio/server.py
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading

HOST = os.environ.get("LTX_AUDIO_HOST", "127.0.0.1")
PORT = int(os.environ.get("LTX_AUDIO_PORT", "8790"))
SITE_ROOT = Path(os.environ.get("LTX_SITE_ROOT", Path(__file__).resolve().parents[2]))
# The only directories a caller may name. ltx-api resolves an owned asset to a path inside one of
# them; anything else is a bug or an attempt to read the rest of the disk.
ALLOWED_ROOTS = (SITE_ROOT / "uploads", SITE_ROOT / "data")
MAX_BODY = 256 * 1024
MAX_LYRICS = 16000
WHISPER_MODEL = os.environ.get("LTX_AUDIO_WHISPER_MODEL", "large-v3")

# Loading whisper costs several seconds and about 6 GB, so it happens on the first /align rather
# than at import: a host that only ever asks for beats never pays for it.
_model = None
_model_lock = threading.Lock()


def resolved_path(raw):
    if not isinstance(raw, str) or not raw:
        raise ValueError("path is required")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = SITE_ROOT / candidate
    # resolve() first: a symlink pointing outside must fail the containment check, not pass it.
    candidate = candidate.resolve()
    if not any(candidate.is_relative_to(root.resolve()) for root in ALLOWED_ROOTS):
        raise ValueError("path must be inside uploads/ or data/")
    if not candidate.is_file():
        raise ValueError("path does not name a readable file")
    return candidate


def whisper_model():
    global _model
    with _model_lock:
        if _model is None:
            import stable_whisper

            _model = stable_whisper.load_model(
                WHISPER_MODEL, device="cuda",
                download_root=os.environ.get("STUDIO_MODELS", "/opt/studio/models") + "/whisper")
        return _model


def beats(path):
    """Tempo, the beat grid, section boundaries and an energy curve.

    These are facts about the music. Turning them into shots is the breakdown's job (B3), not
    this service's.
    """
    import librosa
    import numpy as np

    audio, rate = librosa.load(str(path), sr=None, mono=True)
    tempo, frames = librosa.beat.beat_track(y=audio, sr=rate)
    beat_times = librosa.frames_to_time(frames, sr=rate)

    # RMS in dB, sampled about ten times a second: dense enough to see a chorus lift, sparse
    # enough to send over HTTP and draw.
    hop = max(1, int(rate / 10))
    rms = librosa.feature.rms(y=audio, frame_length=hop * 2, hop_length=hop)[0]
    energy = librosa.amplitude_to_db(rms, ref=float(np.max(rms)) or 1.0)

    # Section boundaries from timbre. Agglomerative clustering over MFCCs is coarse, and it is
    # meant to be: it marks where the arrangement changes, not every phrase.
    sections = []
    try:
        mfcc = librosa.feature.mfcc(y=audio, sr=rate, n_mfcc=13)
        wanted = int(min(12, max(2, len(audio) / rate / 15)))
        boundaries = librosa.segment.agglomerative(mfcc, wanted)
        sections = [round(float(t), 3) for t in librosa.frames_to_time(boundaries, sr=rate)]
    except (ValueError, RuntimeError):
        # A very short or near-silent file has no arrangement to segment; beats still stand.
        sections = []

    return {
        "duration_seconds": round(len(audio) / rate, 3),
        "sample_rate": int(rate),
        "tempo_bpm": round(float(np.atleast_1d(tempo)[0]), 2),
        "beats": [round(float(t), 3) for t in beat_times],
        "sections": sections,
        "energy_db": [round(float(v), 2) for v in energy],
        "energy_hop_seconds": round(hop / rate, 4),
    }


def align(path, lyrics, language):
    """Word-level times for lyrics that are already known.

    Alignment, not transcription: the words are given, so this only decides when each was sung.
    """
    if not isinstance(lyrics, str) or not lyrics.strip():
        raise ValueError("lyrics is required")
    if len(lyrics) > MAX_LYRICS:
        raise ValueError(f"lyrics must be at most {MAX_LYRICS} characters")
    result = whisper_model().align(str(path), lyrics, language=language or None)
    lines = []
    for segment in result.segments:
        words = [{"word": w.word, "start": round(float(w.start), 3), "end": round(float(w.end), 3)}
                 for w in (segment.words or [])]
        lines.append({"text": segment.text, "start": round(float(segment.start), 3),
                      "end": round(float(segment.end), 3), "words": words})
    return {"model": WHISPER_MODEL, "language": language or "auto", "segments": lines}


class Handler(BaseHTTPRequestHandler):
    server_version = "LTXAudio/1.0"

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        sys.stderr.write("[ltx-audio] %s\n" % (fmt % args))

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
            # Says nothing about what has been analysed or for whom.
            self.send_json(200, {"ok": True, "service": "ltx-audio", "model": WHISPER_MODEL,
                                 "whisper_loaded": _model is not None})
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):  # noqa: N802
        try:
            raw = self.body()
            path = resolved_path(raw.get("path"))
            if self.path == "/beats":
                self.send_json(200, beats(path))
            elif self.path == "/align":
                self.send_json(200, align(path, raw.get("lyrics"), raw.get("language")))
            else:
                self.send_json(404, {"error": "Not found"})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)[:300], "code": "invalid_request"})
        except MemoryError:
            self.send_json(503, {"error": "Not enough memory for this file", "code": "unavailable"})
        except Exception as exc:  # noqa: BLE001 - one bad file must not take the service down
            self.log_message("analysis failed: %s", str(exc)[:200])
            self.send_json(500, {"error": "Analysis failed", "code": "analysis_failed"})


def main():
    if HOST not in ("127.0.0.1", "::1", "localhost"):
        raise SystemExit(f"Refusing to bind {HOST}: this service is loopback-only.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"LTX audio service: http://{HOST}:{PORT} (roots: "
          f"{', '.join(str(r) for r in ALLOWED_ROOTS)})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
