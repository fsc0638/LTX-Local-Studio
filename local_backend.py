#!/usr/bin/env python3
"""Local-only API bridge between the LTX Studio UI and the installed LTX-2.3 launcher."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SITE_ROOT = Path(__file__).resolve().parent
LTX_REPO_ROOT = Path(os.environ.get("LTX_REPO_ROOT", SITE_ROOT / "vendor" / "LTX-2")).expanduser().resolve()
LAUNCHER = Path(os.environ.get("LTX_LAUNCHER", SITE_ROOT / "scripts" / "run-ltx-2.3.sh")).expanduser().resolve()
OUTPUT_DIR = Path(os.environ.get("LTX_OUTPUT_DIR", SITE_ROOT / "public" / "generated")).expanduser().resolve()
LTX_PYTHON = Path(os.environ.get("LTX_PYTHON", LTX_REPO_ROOT / ".venv" / "bin" / "python")).expanduser().resolve()
POSTER_SCRIPT = SITE_ROOT / "extract_poster.py"
HOST = os.environ.get("LTX_API_HOST", "127.0.0.1")
PORT = int(os.environ.get("LTX_API_PORT", "8787"))
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "LTX_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
}
JOBS: dict[str, dict[str, Any]] = {}
LOCK = threading.Lock()
PROGRESS_RE = re.compile(r"(?<!\d)(\d{1,3})%")


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in job.items() if key not in {"process", "log_path"}}
    if result["status"] == "running" and result["progress"] < 92:
        elapsed = max(0.0, time.time() - result["started_at"])
        result["progress"] = max(result["progress"], min(92, round(6 + elapsed / 55 * 86)))
    return result


def run_job(job_id: str, payload: dict[str, Any]) -> None:
    with LOCK:
        job = JOBS[job_id]
        job["status"] = "running"
        job["started_at"] = time.time()
        job["progress"] = 3

    env = os.environ.copy()
    env.update({
        "LTX_WIDTH": str(payload["width"]),
        "LTX_HEIGHT": str(payload["height"]),
        "LTX_FRAMES": str(payload["frames"]),
        "LTX_FPS": str(payload["fps"]),
        "LTX_SEED": str(payload["seed"]),
    })
    if payload.get("offload"):
        env["LTX_OFFLOAD"] = "cpu"
    else:
        env.pop("LTX_OFFLOAD", None)

    output_path = OUTPUT_DIR / job["filename"]
    log_path = OUTPUT_DIR / f"{job_id}.log"
    command = ["bash", str(LAUNCHER), payload["prompt"], str(output_path)]
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
            with LOCK:
                job["process"] = process
                job["log_path"] = str(log_path)
            recent: list[str] = []
            assert process.stdout is not None
            for line in process.stdout:
                log_file.write(line)
                log_file.flush()
                cleaned = line.strip()
                if cleaned:
                    recent = (recent + [cleaned])[-18:]
                percentages = [int(value) for value in PROGRESS_RE.findall(line)]
                if percentages:
                    with LOCK:
                        job["progress"] = max(job["progress"], min(94, max(percentages)))
                        job["message"] = cleaned[-220:]
            return_code = process.wait()
        with LOCK:
            job["finished_at"] = time.time()
            job["runtime_seconds"] = round(job["finished_at"] - job["started_at"], 2)
            job.pop("process", None)
            if return_code == 0 and output_path.exists():
                job["status"] = "succeeded"
                job["progress"] = 100
                job["message"] = "影片生成完成，已載入輸出預覽。"
                job["size_bytes"] = output_path.stat().st_size
                poster_path = output_path.with_suffix(".jpg")
                poster_result = subprocess.run(
                    [str(LTX_PYTHON), str(POSTER_SCRIPT), str(output_path), str(poster_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if poster_result.returncode == 0 and poster_path.exists():
                    job["poster_url"] = f"/generated/{poster_path.name}"
                metadata_path = output_path.with_suffix(".json")
                metadata_path.write_text(
                    json.dumps(public_job(job), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            else:
                job["status"] = "failed"
                job["message"] = "\n".join(recent[-5:]) or f"LTX process exited with code {return_code}."
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            job["status"] = "failed"
            job["finished_at"] = time.time()
            job["message"] = str(exc)
            job.pop("process", None)


def parse_payload(raw: dict[str, Any]) -> dict[str, Any]:
    prompt = str(raw.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("請先輸入提示詞。")
    if len(prompt) > 4000:
        raise ValueError("提示詞不可超過 4000 個字元。")
    if raw.get("model", "ltx23-distilled") != "ltx23-distilled":
        raise ValueError("目前本機後端已連接 LTX-2.3 Distilled；其他模型尚未安裝對應執行器。")
    if raw.get("mode", "t2v") != "t2v":
        raise ValueError("目前可直接執行 Text to Video；Image/Video to Video 需要先完成素材傳遞。")
    width = int(raw.get("width", 768))
    height = int(raw.get("height", 512))
    frames = int(raw.get("frames", 49))
    fps = int(raw.get("fps", 24))
    seed = int(raw.get("seed", 42))
    if width < 256 or width > 1536 or width % 32:
        raise ValueError("寬度必須介於 256–1536，且為 32 的倍數。")
    if height < 256 or height > 1536 or height % 32:
        raise ValueError("高度必須介於 256–1536，且為 32 的倍數。")
    if frames < 9 or frames > 257 or (frames - 1) % 8:
        raise ValueError("幀數必須為 8n+1，例如 17、25、33、49。")
    if fps < 8 or fps > 60:
        raise ValueError("FPS 必須介於 8–60。")
    return {
        "prompt": prompt,
        "model": "ltx23-distilled",
        "mode": "t2v",
        "width": width,
        "height": height,
        "frames": frames,
        "fps": fps,
        "seed": seed,
        "offload": bool(raw.get("offload", False)),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "LTXStudioLocal/1.0"

    def cors_origin(self) -> str:
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin in ALLOWED_ORIGINS:
            return origin
        return next(iter(ALLOWED_ORIGINS), "http://localhost:3000")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", self.cors_origin())
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            active = any(job["status"] in {"queued", "running"} for job in JOBS.values())
            self.send_json(200, {"ok": LAUNCHER.exists(), "model": "LTX-2.3 Distilled", "busy": active})
            return
        if path == "/api/outputs":
            outputs: list[dict[str, Any]] = []
            seen: set[str] = set()
            with LOCK:
                completed = [public_job(job) for job in JOBS.values() if job["status"] == "succeeded"]
            for job in completed:
                outputs.append(job)
                seen.add(job["filename"])
            for video_path in sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True):
                if video_path.name in seen:
                    continue
                metadata_path = video_path.with_suffix(".json")
                if metadata_path.exists():
                    try:
                        saved = json.loads(metadata_path.read_text(encoding="utf-8"))
                        outputs.append(saved)
                        continue
                    except (OSError, ValueError, TypeError):
                        pass
                outputs.append({
                    "id": video_path.stem,
                    "status": "succeeded",
                    "progress": 100,
                    "message": "已從本機輸出資料夾恢復。",
                    "filename": video_path.name,
                    "output_url": f"/generated/{video_path.name}",
                    "poster_url": f"/generated/{video_path.with_suffix('.jpg').name}" if video_path.with_suffix(".jpg").exists() else "",
                    "width": 768,
                    "height": 512,
                    "frames": 49,
                    "fps": 24,
                    "runtime_seconds": 0,
                    "size_bytes": video_path.stat().st_size,
                    "finished_at": video_path.stat().st_mtime,
                })
            outputs.sort(key=lambda item: item.get("finished_at", item.get("created_at", 0)), reverse=True)
            self.send_json(200, {"outputs": outputs})
            return
        match = re.fullmatch(r"/api/jobs/([a-f0-9]+)", path)
        if match:
            with LOCK:
                job = JOBS.get(match.group(1))
                payload = public_job(job) if job else None
            if payload is None:
                self.send_json(404, {"error": "找不到這個任務。"})
            else:
                self.send_json(200, payload)
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/jobs":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 32_000:
                raise ValueError("請求內容大小無效。")
            raw = json.loads(self.rfile.read(length))
            payload = parse_payload(raw)
            with LOCK:
                if any(job["status"] in {"queued", "running"} for job in JOBS.values()):
                    self.send_json(409, {"error": "目前已有生成任務執行中，請等待完成。"})
                    return
                job_id = uuid.uuid4().hex[:12]
                filename = f"ltx-ui-{time.strftime('%Y%m%d-%H%M%S')}-{job_id}.mp4"
                job = {
                    "id": job_id,
                    "status": "queued",
                    "progress": 0,
                    "message": "任務已排入本機 GPU。",
                    "created_at": time.time(),
                    "filename": filename,
                    "output_url": f"/generated/{filename}",
                    "prompt": payload["prompt"],
                    "width": payload["width"],
                    "height": payload["height"],
                    "frames": payload["frames"],
                    "fps": payload["fps"],
                    "seed": payload["seed"],
                }
                JOBS[job_id] = job
            threading.Thread(target=run_job, args=(job_id, payload), daemon=True).start()
            self.send_json(202, public_job(job))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[LTX API] {self.address_string()} - {format % args}")


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not LAUNCHER.exists():
        raise SystemExit(f"Missing launcher: {LAUNCHER}")
    if not LTX_REPO_ROOT.exists():
        raise SystemExit(f"Missing LTX repository: {LTX_REPO_ROOT}. Set LTX_REPO_ROOT in .env.local.")
    print(f"LTX Studio local API: http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
