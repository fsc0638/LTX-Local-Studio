#!/usr/bin/env python3
"""Local-only API bridge between the LTX Studio UI and the installed LTX-2.3 launcher."""

from __future__ import annotations

import json
import fcntl
import math
import os
import re
import signal
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from media_store import MediaHandlerMixin, asset_by_id, asset_path, list_assets, MAX_UPLOAD
import psycopg

import database
from production_store import ProductionStore, file_fingerprint
import worker_contract as worker
from auth_http import AuthHandlerMixin
from user_auth import AuthSettings, AuthStore
from cloudflare_access import AccessSettings, AccessClient, AccessVerifier, sync_enrollment
import model_registry
import media_store
from media_deletion import prepare_archive
from video_settings import image_geometry
import mv_timeline
import character_consistency


SITE_ROOT = Path(__file__).resolve().parent
LTX_REPO_ROOT = Path(os.environ.get("LTX_REPO_ROOT", SITE_ROOT / "vendor" / "LTX-2")).expanduser().resolve()
LAUNCHER = Path(os.environ.get("LTX_LAUNCHER", SITE_ROOT / "scripts" / "run-ltx-2.3.sh")).expanduser().resolve()
OUTPUT_DIR = Path(os.environ.get("LTX_OUTPUT_DIR", SITE_ROOT / "data/worker/outputs")).expanduser().resolve()
LEGACY_OUTPUT_DIR = SITE_ROOT / "data/worker/legacy-outputs"
# Preserve the venv entrypoint: resolving its symlink selects system Python and
# loses the environment's PyAV/Pillow packages (uploads and posters then fail).
LTX_PYTHON = Path(os.environ.get("LTX_PYTHON", LTX_REPO_ROOT / ".venv" / "bin" / "python")).expanduser().absolute()
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
RUNTIME: dict[str, Any] = {}
STORE: ProductionStore | None = None
STORE_ERROR = ""
WORK_DIR = Path(os.environ.get("LTX_WORK_DIR", SITE_ROOT / "data/worker/work")).expanduser().absolute()
TRASH_DIR = SITE_ROOT / "data/worker/trash"
STOPPING = False
RESUME_REQUEST = SITE_ROOT / "data/worker/resume-request.json"
USER_AUTH_ENABLED = os.environ.get("LTX_USER_AUTH_ENABLED", "1") != "0"
AUTH = None
AUTH_SETTINGS = AuthSettings.from_env()
ACCESS_SETTINGS = AccessSettings.from_env()
ACCESS_CLIENT = AccessClient(ACCESS_SETTINGS)
ACCESS_VERIFIER = AccessVerifier(ACCESS_SETTINGS)


def output_location(filename):
    current = OUTPUT_DIR / filename
    return current if current.exists() else LEGACY_OUTPUT_DIR / filename


class JobFailure(Exception):
    def __init__(self, code, message, status="failed", retryable=False):
        super().__init__(message)
        self.code, self.status, self.retryable = code, status, retryable


def stop_process(process):
    """Only signal a process group we created with start_new_session=True."""
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    except ProcessLookupError:
        pass


def check_abort(job, deadline):
    if STOPPING:
        raise JobFailure("worker_shutdown", "Worker is shutting down.", "interrupted", True)
    if job.get("cancel_requested"):
        raise JobFailure("cancelled", "Generation cancelled by caller.", "cancelled")
    if time.monotonic() >= deadline:
        raise JobFailure("generation_timeout", "Generation exceeded timeout_seconds.", "failed", True)


def record_job(job):
    global STORE_ERROR
    if STORE is None:
        return
    try:
        STORE.record(job)
        STORE_ERROR = ""
    except (OSError, ValueError, sqlite3.Error):
        # A memory-store failure must not discard a successfully generated video.
        STORE_ERROR = "任務紀錄儲存失敗，請檢查磁碟與權限。"


def generation_provenance(payload):
    if payload["model"] != "ltx23-distilled":
        import inspect
        adapter = model_registry.get(payload["model"])
        source = inspect.getsourcefile(adapter.command)
        return {"source": "live_generation", "adapter_id": adapter.id, "adapter_version": "media-adapter-v1",
                "contract_version": worker.CONTRACT_VERSION, "runtime": dict(RUNTIME),
                "adapter_code": file_fingerprint(source, digest=True) if source else None,
                "weights_content_verified": False, "precision": "adapter_defined"}
    checkpoint = Path(os.environ.get("LTX_CHECKPOINT_PATH", LTX_REPO_ROOT / "models/LTX-2.3/ltx-2.3-22b-distilled-1.1.safetensors"))
    upsampler = Path(os.environ.get("LTX_UPSAMPLER_PATH", LTX_REPO_ROOT / "models/LTX-2.3/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"))
    try:
        revision = subprocess.run(["git", "-C", str(LTX_REPO_ROOT), "rev-parse", "HEAD"],
                                  capture_output=True, text=True, timeout=3, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        revision = "unknown"
    provenance = {"source": "live_generation", "pipeline_commit": revision,
                  "runtime": {key: RUNTIME.get(key) for key in ("device", "torch", "cuda_available")},
                  "checkpoint": file_fingerprint(checkpoint), "upsampler": file_fingerprint(upsampler),
                  "code": [file_fingerprint(path, digest=True) for path in
                           (LAUNCHER, SITE_ROOT / "scripts/run_local.py", SITE_ROOT / "local_backend.py",
                            SITE_ROOT / "worker_contract.py", SITE_ROOT / "scripts/check_output.py")],
                  "contract_version": worker.CONTRACT_VERSION,
                  "profile": payload.get("profile", "compat-v1"),
                  "precision": "bf16", "attention": "sdpa", "image_strength": payload.get("image_strength") if payload.get("image_id") else None,
                  "reference_background": payload.get("reference_background") if payload.get("image_id") else None,
                  "quantization": os.environ.get("LTX_QUANTIZATION") or None,
                  "weights_content_verified": False}
    reference_ids = character_consistency.reference_ids(payload.get("character"), payload.get("image_id"))
    if reference_ids:
        references = [file_fingerprint(asset_path(asset_by_id(identity)), digest=True) for identity in reference_ids]
        provenance["reference"] = references[0]
        provenance["references"] = references
    if payload.get("timeline", {}).get("audio_id"):
        provenance["source_audio"] = file_fingerprint(asset_path(asset_by_id(payload["timeline"]["audio_id"])), digest=True)
        provenance["audio_conditioning"] = "experimental_distilled_frozen_audio_v1" if payload["timeline"].get("audio_mode") == "condition" else "soundtrack_only"
    provenance["render_mode"] = payload.get("render_mode", "single")
    provenance["composition_code"] = [file_fingerprint(SITE_ROOT / name, digest=True) for name in
                                      ("mv_timeline.py", "scripts/sequence_media.py", "scripts/audio_conditioning.py", "video_settings.py")]
    return provenance


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in job.items() if key not in {"process", "log_path"}}
    if result["status"] == "running":
        result["elapsed_seconds"] = round(time.time() - result["started_at"], 1)
    return result


def update_progress(job, line):
    """Stage-weighted progress, not a time-based ETA or raw tqdm percentage."""
    phases = [
        ("Building text encoder", "prompt", 5, "提示詞編碼 / Prompt encoding / プロンプト処理"),
        ("Prompt encoding complete", "loading", 12, "載入模型 / Loading model / モデル読込"),
        ("Building video encoder + spatial upsampler", "upscale", 50, "空間放大 / Upscaling / アップスケール"),
        ("Building video decoder", "decode", 92, "影音解碼 / Decoding / デコード"),
        ("Building audio decoder", "audio", 94, "音訊解碼 / Audio decoding / 音声デコード"),
    ]
    if "Running denoising loop" in line:
        second = job.get("phase") == "upscale"
        job.update(phase="refine" if second else "denoise", progress=55 if second else 15,
                   message="第二階段推論 / Stage 2 / 第2段階" if second else "第一階段推論 / Stage 1 / 第1段階")
    for marker, phase, progress, message in phases:
        if marker in line:
            job.update(phase=phase, progress=progress, message=message)
    percentages = [int(value) for value in PROGRESS_RE.findall(line)]
    phase = job.get("phase")
    if percentages and phase in {"denoise", "refine", "decode", "audio"}:
        low, high = {"denoise": (15, 49), "refine": (55, 91), "decode": (92, 98), "audio": (94, 98)}[phase]
        job["progress"] = max(job["progress"], low + round((high - low) * min(100, max(percentages)) / 100))


def job_environment(payload):
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("LTX_SMTP_"):
            env.pop(name)
    env.pop("LTX_WORKER_API_KEY", None)
    env.pop("LTX_WORKER_API_KEY_FILE", None)
    env.update({
        "LTX_WIDTH": str(payload["width"]),
        "LTX_HEIGHT": str(payload["height"]),
        "LTX_FRAMES": str(payload["frames"]),
        "LTX_FPS": str(payload["fps"]),
        "LTX_SEED": str(payload["seed"]),
        "LTX_AUDIO": "1" if payload["audio"] else "0",
        "LTX_WORKER_PARENT_PID": str(os.getpid()),
        "PYTHONUNBUFFERED": "1",
    })
    for key in ("LTX_IMAGE", "LTX_IMAGE_FRAME", "LTX_IMAGE_STRENGTH", "LTX_AUDIO_REFERENCE"):
        env.pop(key, None)
    if payload.get("image_id"):
        env["LTX_IMAGE"] = str(asset_path(asset_by_id(payload["image_id"])))
        env["LTX_IMAGE_FRAME"] = "0"
        env["LTX_IMAGE_STRENGTH"] = str(payload.get("image_strength", 0.8))
    if payload.get("offload"):
        env["LTX_OFFLOAD"] = "cpu"
    else:
        env.pop("LTX_OFFLOAD", None)
    return env


def run_job(job_id: str, payload: dict[str, Any], *, resume: bool = False) -> None:
    with LOCK:
        job = JOBS[job_id]
        if resume:
            for stale in ("finished_at", "runtime_seconds", "error", "quality_control", "measured_media",
                          "artifact_sha256", "size_bytes", "poster_url", "cancel_requested"):
                job.pop(stale, None)
        job["status"] = "running"
        job["started_at"] = time.time()
        job["progress"] = 3
        if resume:
            job["message"] = "正在驗證既有鏡頭並從中斷處續跑。"
        record_job(job)

    # Work products and logs are never written under the web public directory.
    work_path = WORK_DIR / job_id
    output_path = work_path / job["filename"]
    deadline = time.monotonic() + payload.get("timeout_seconds", worker.default_timeout())
    process = None
    watchdog_done = threading.Event()
    watchdog = None
    failure = None
    completed = None

    def watch():
        while not watchdog_done.wait(0.25):
            try:
                check_abort(job, deadline)
            except JobFailure:
                with LOCK:
                    active = job.get("process")
                stop_process(active)

    def auxiliary(command, timeout):
        """Keep cancellation effective during CPU decode and thumbnail creation."""
        nonlocal process
        check_abort(job, deadline)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        with LOCK:
            job["process"] = process
        try:
            stdout, stderr = process.communicate(timeout=min(timeout, max(0.1, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            stop_process(process)
            check_abort(job, deadline)
            raise JobFailure("validation_timeout", "Output verification timed out.", retryable=True)
        check_abort(job, deadline)
        if process.returncode:
            raise JobFailure("validation_failed", "Output verification process failed: " + stderr[-500:])
        return stdout

    def generate_part(part, target, log_file, index=0, count=1, reference_paths=None, music_path=None):
        nonlocal process
        env = job_environment(part)
        selected_reference = character_consistency.select_reference(
            part.get("character"), part.get("directing", {}), part.get("image_id"))
        if reference_paths and selected_reference in reference_paths:
            env["LTX_IMAGE"] = str(reference_paths[selected_reference])
        if music_path:
            env["LTX_AUDIO_REFERENCE"] = str(music_path)
        check_abort(job, deadline)
        process = subprocess.Popen(
            adapter.command(part, target, {"launcher": LAUNCHER, "python": LTX_PYTHON, "root": SITE_ROOT}),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env, start_new_session=True)
        with LOCK:
            job["process"] = process
        recent = []
        persisted_at = time.monotonic()
        stage = {"progress": 3}
        for line in process.stdout:
            log_file.write(line)
            log_file.flush()
            if line.strip():
                recent = (recent + [line.strip()])[-18:]
            update_progress(stage, line)
            with LOCK:
                old_phase = job.get("phase")
                if payload.get("render_mode") == "sequence":
                    job.update(progress=max(job.get("progress", 3), round(94 * (index + stage["progress"] / 100) / count)),
                               phase="shot_" + str(index + 1), segment_index=index + 1, segment_count=count,
                               message=f"鏡頭 / Shot {index + 1}/{count} · " + stage.get("message", "Generating"))
                else:
                    job.update(stage)
                if old_phase != job.get("phase") or time.monotonic() - persisted_at >= 2:
                    record_job(job)
                    persisted_at = time.monotonic()
        return_code = process.wait()
        process.stdout.close()
        check_abort(job, deadline)
        if return_code or not target.is_file():
            raise JobFailure("generation_failed", "\n".join(recent[-5:]) or f"Generator exited with code {return_code}", retryable=True)

    try:
        check_abort(job, deadline)
        adapter = model_registry.get(payload["model"])
        if resume:
            if payload.get("render_mode") != "sequence" or not work_path.is_dir() or work_path.is_symlink():
                raise JobFailure("resume_unavailable", "Only an existing sequence workspace can be resumed.")
        else:
            work_path.mkdir(parents=True, exist_ok=False, mode=0o700)
        log_path = work_path / "generation.log"
        watchdog = threading.Thread(target=watch, daemon=True)
        watchdog.start()
        media_command = [str(LTX_PYTHON), str(SITE_ROOT / "scripts/sequence_media.py")]
        reference_paths = {}
        if payload.get("image_id") and payload["model"] == "ltx23-distilled":
            for reference_id in character_consistency.reference_ids(payload.get("character"), payload["image_id"]):
                reference_path = work_path / f"reference-{len(reference_paths) + 1:02d}.png"
                if not (resume and reference_path.is_file() and not reference_path.is_symlink()):
                    auxiliary([*media_command, "image", str(asset_path(asset_by_id(reference_id))), str(reference_path),
                               str(payload["width"]), str(payload["height"]), payload.get("reference_background", "source")], 30)
                reference_paths[reference_id] = reference_path
        job["log_path"] = str(log_path)
        with log_path.open("a" if resume else "w", encoding="utf-8") as log_file:
            if resume:
                log_file.write("\n--- sequence recovery started ---\n")
            if payload.get("render_mode") == "sequence":
                timeline = payload["timeline"]
                audio_source = asset_path(asset_by_id(timeline["audio_id"])) if timeline.get("audio_id") else None
                parts = []
                for index, segment in enumerate(payload["segments"]):
                    check_abort(job, deadline)
                    if shutil.disk_usage(work_path).free < 2 * 1024**3:
                        raise JobFailure("insufficient_disk", "Insufficient space for remaining shots")
                    target = work_path / f"shot-{index + 1:03d}.mp4"
                    part = {**payload, "frames": segment["frames"], "prompt": segment["prompt"],
                            "directing": segment["directing"],
                            "seed": character_consistency.segment_seed(payload["seed"], index, payload.get("character")),
                            "audio": False if audio_source else payload["audio"]}
                    expected_part = json.dumps({key: part[key] for key in ("width", "height", "frames", "fps", "audio")})
                    if resume and target.is_file() and not target.is_symlink():
                        checked = json.loads(auxiliary([str(LTX_PYTHON), str(SITE_ROOT / "scripts/check_output.py"), str(target), expected_part], 120))
                        if not checked["quality_control"]["passed"]:
                            raise JobFailure("shot_quality_failed", f"Existing shot {index + 1} failed technical validation")
                        parts.append({"path": str(target), "keep_frames": segment["keep_frames"]})
                        with LOCK:
                            job.update(progress=max(job.get("progress", 3), round(94 * (index + 1) / len(payload["segments"]))),
                                       phase="resume_check", segment_index=index + 1, segment_count=len(payload["segments"]),
                                       message=f"已驗證既有鏡頭 / Reused shot {index + 1}/{len(payload['segments'])}")
                            record_job(job)
                        continue
                    music = None
                    if audio_source and timeline.get("audio_mode") == "condition":
                        music = work_path / f"shot-{index + 1:03d}.wav"
                        auxiliary([*media_command, "audio", str(audio_source), str(music),
                                   str(timeline["audio_start_seconds"] + segment["start_seconds"]), str(part["frames"] / part["fps"])], 45)
                    generate_part(part, target, log_file, index, len(payload["segments"]), reference_paths, music)
                    checked = json.loads(auxiliary([str(LTX_PYTHON), str(SITE_ROOT / "scripts/check_output.py"), str(target), expected_part], 120))
                    if not checked["quality_control"]["passed"]:
                        raise JobFailure("shot_quality_failed", f"Shot {index + 1} failed technical validation")
                    parts.append({"path": str(target), "keep_frames": segment["keep_frames"]})
                with LOCK:
                    job.update(progress=95, phase="assembly", message="組合鏡頭與連續音樂母帶 / Assembling timeline")
                    record_job(job)
                manifest = work_path / "sequence.json"
                manifest.write_text(json.dumps({"segments": parts, "fps": payload["fps"], "width": payload["width"],
                                               "height": payload["height"], "audio": payload["audio"],
                                               "audio_path": str(audio_source) if audio_source else None,
                                               "audio_start_seconds": timeline["audio_start_seconds"]}), encoding="utf-8")
                auxiliary([*media_command, "assemble", str(manifest), str(output_path)], 1800)
            else:
                part = {**payload, "prompt": mv_timeline.compose_prompt(payload["prompt"], payload.get("directing", {}))}
                generate_part(part, output_path, log_file, reference_paths=reference_paths)
        with LOCK:
            job.update(progress=98, phase="validation", message="完整解碼與成品驗證 / Validating output")
            record_job(job)
        expected = json.dumps({name: payload.get(name) for name in ("width", "height", "frames", "fps", "audio")})
        check_command = [str(LTX_PYTHON), str(SITE_ROOT / "scripts/check_output.py"), str(output_path), expected] if adapter.media_type == "video" else [str(LTX_PYTHON), str(SITE_ROOT / "scripts/check_media_output.py"), str(output_path), adapter.media_type, expected]
        result = json.loads(auxiliary(check_command, 600 if payload.get("render_mode") == "sequence" else 120))
        if payload.get("render_mode") == "sequence":
            result["quality_control"]["warnings"].append("independent_shots_continuity_requires_review")
            if payload["timeline"].get("audio_mode") == "condition":
                result["quality_control"]["warnings"].append("experimental_audio_conditioning_not_verified_lip_sync")
        with LOCK:
            job.update(result)
        if not result.get("quality_control", {}).get("passed"):
            raise JobFailure("quality_check_failed", "Output failed technical validation: " +
                             ", ".join(result.get("quality_control", {}).get("errors", [])))
        job["artifact_sha256"] = file_fingerprint(output_path, digest=True)["sha256"]
        poster_path = output_path.with_suffix(".jpg") if adapter.media_type == "video" else None
        with LOCK:
            job.update(progress=99, phase="poster", message="建立預覽 / Preparing preview")
        if poster_path is not None:
            try:
                auxiliary([str(LTX_PYTHON), str(POSTER_SCRIPT), str(output_path), str(poster_path)], 30)
            except JobFailure:
                check_abort(job, deadline)
                job["quality_control"]["warnings"].append("poster_unavailable")
        check_abort(job, deadline)
        with LOCK:
            # Serialize cancellation with publication: either cancel wins or a
            # complete artifact wins. Never return cancelled then publish later.
            check_abort(job, deadline)
            completed = {**public_job(job), "status": "succeeded", "phase": "complete", "progress": 100,
                         "finished_at": time.time(), "size_bytes": output_path.stat().st_size,
                         "message": "影片通過技術驗證，已載入輸出預覽。"}
            completed["runtime_seconds"] = round(completed["finished_at"] - job["started_at"], 2)
            if poster_path is not None and poster_path.is_file():
                completed["poster_url"] = f"/generated/{poster_path.name}"
            elif adapter.media_type == "image":
                completed["poster_url"] = f"/generated/{output_path.name}"
            metadata = work_path / "result.json"
            metadata.write_text(json.dumps(completed, ensure_ascii=False, indent=2), encoding="utf-8")
            output_path.replace(OUTPUT_DIR / output_path.name)
            if poster_path is not None and poster_path.is_file():
                poster_path.replace(OUTPUT_DIR / poster_path.name)
            metadata.replace((OUTPUT_DIR / output_path.name).with_suffix(".json"))
            job.update(completed)
    except Exception as exc:  # noqa: BLE001
        failure = exc if isinstance(exc, JobFailure) else JobFailure("worker_error", str(exc))
    finally:
        watchdog_done.set()
        if watchdog is not None:
            watchdog.join(timeout=11)
        stop_process(process)
        if process is not None and process.stdout is not None:
            process.stdout.close()
        if process is not None and process.stderr is not None:
            process.stderr.close()
        with LOCK:
            if failure is not None:
                job.update(status=failure.status, finished_at=time.time(), message=str(failure),
                           error={"code": failure.code, "retryable": failure.retryable})
            job.pop("process", None)
            if job.get("finished_at") and job.get("started_at"):
                job["runtime_seconds"] = round(job["finished_at"] - job["started_at"], 2)
            record_job(job)


def claim_resume_request() -> tuple[str, dict[str, Any]] | None:
    """Claim one operator-approved sequence recovery request at service startup."""
    if STORE is None or not RESUME_REQUEST.is_file() or RESUME_REQUEST.is_symlink():
        return None
    try:
        raw = json.loads(RESUME_REQUEST.read_text(encoding="utf-8"))
        job_id = str(raw.get("job_id", ""))
        timeout = raw.get("timeout_seconds", worker.MAX_TIMEOUT)
        if not re.fullmatch(r"[a-f0-9]{12,32}", job_id) or type(timeout) is not int or not 30 <= timeout <= worker.MAX_TIMEOUT:
            raise ValueError("Invalid resume request")
        job = STORE.get(job_id)
        if not job or job.get("render_mode") != "sequence" or job.get("status") not in {"failed", "interrupted"}:
            raise ValueError("Job is not resumable")
        if job.get("status") == "failed" and not job.get("error", {}).get("retryable"):
            raise ValueError("Job failure is not retryable")
        work_path = WORK_DIR / job_id
        if not work_path.is_dir() or work_path.is_symlink():
            raise ValueError("Recovery workspace is unavailable")
        payload = dict(job)
        payload["timeout_seconds"] = timeout
        job["timeout_seconds"] = timeout
        JOBS[job_id] = job
        RESUME_REQUEST.unlink()
        return job_id, payload
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Resume request rejected: {exc}", flush=True)
        return None


def parse_payload(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("請求需為 JSON 物件。")
    prompt = str(raw.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("請先輸入提示詞。")
    if len(prompt) > 4000:
        raise ValueError("提示詞不可超過 4000 個字元。")
    if raw.get("model", "ltx23-distilled") != "ltx23-distilled":
        raise ValueError("目前本機後端已連接 LTX-2.3 Distilled；其他模型尚未安裝對應執行器。")
    if "negative_prompt" in raw and (not isinstance(raw["negative_prompt"], str) or raw["negative_prompt"].strip()):
        raise ValueError("LTX-2.3 Distilled 不支援負面提示詞（CFG=1）。需安裝 Dev 模型及 guided 執行器；不會默默忽略此欄位。")
    mode = raw.get("mode", "t2v")
    if mode not in {"t2v", "i2v"}:
        raise ValueError("支援文字或圖片生成；影片轉影片尚未接通。")
    render_mode = raw.get("render_mode", "single")
    if render_mode not in {"single", "sequence"}:
        raise ValueError("render_mode must be single or sequence")
    if render_mode != "sequence" and ("timeline" in raw or "segment_seconds" in raw):
        raise ValueError("Timeline and segment_seconds require render_mode=sequence")
    if render_mode == "sequence" and "frames" in raw:
        raise ValueError("Sequence uses duration_seconds, not frames")
    directing = mv_timeline.normalize_directing(raw.get("directing", {}))
    mv_timeline.compose_prompt(prompt, directing)
    image_id = None
    if mode == "i2v":
        image_id = str(raw.get("image_id", ""))
        if asset_by_id(image_id)["kind"] != "image":
            raise ValueError("圖片生成必須選擇圖片素材。")
    character = character_consistency.normalize_character(raw.get("character"), image_id, asset_by_id)
    prompt = character_consistency.apply_identity_prompt(prompt, character)
    ratio = raw.get("aspect_ratio")
    dimensions = {}
    source_geometry = image_geometry(asset_by_id(image_id)["width"], asset_by_id(image_id)["height"]) if image_id else None
    if "aspect_ratio" in raw:
        if not isinstance(ratio, str) or ratio not in {*worker.ASPECT_RATIOS, "source"}:
            raise ValueError("不支援此長寬比例，請查詢 capabilities.aspect_ratios。")
        if "width" in raw or "height" in raw:
            raise ValueError("請選用 aspect_ratio 或 width/height，不可同時設定。")
        if ratio == "source":
            if not source_geometry:
                raise ValueError("Source ratio requires an image reference")
            dimensions = source_geometry["suggested_dimensions"]
        else:
            dimensions = worker.ASPECT_RATIOS[ratio]
    elif image_id and "width" not in raw and "height" not in raw:
        ratio = "source"
        dimensions = source_geometry["suggested_dimensions"]
    width = int(dimensions.get("width", raw.get("width", 768)))
    height = int(dimensions.get("height", raw.get("height", 512)))
    frames = int(raw.get("frames", 49))
    fps = int(raw.get("fps", 24))
    seed = int(raw.get("seed", 42))
    if width < 256 or width > 1536 or width % 64:
        raise ValueError("二階段生成寬度必須介於 256–1536，且為 64 的倍數。")
    if height < 256 or height > 1536 or height % 64:
        raise ValueError("二階段生成高度必須介於 256–1536，且為 64 的倍數。")
    if frames < 9 or frames > worker.MAX_FRAMES or (frames - 1) % 8:
        raise ValueError(f"幀數必須為 8n+1，範圍 9–{worker.MAX_FRAMES}；最長秒數 = {worker.MAX_FRAMES} ÷ FPS。")
    if fps < 8 or fps > 60:
        raise ValueError("FPS 必須介於 8–60。")
    if seed < 0 or seed > 2**32 - 1:
        raise ValueError("種子必須介於 0–4294967295。")
    for key in ("audio", "offload"):
        if key in raw and not isinstance(raw[key], bool):
            raise ValueError(f"{key} 必須為布林值。")
    strength = raw.get("image_strength", 0.8)
    if type(strength) not in (int, float) or not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("image_strength 必須是 0–1 的有限數值。")
    reference_background = raw.get("reference_background", "source")
    if reference_background not in {"source", "alpha_neutral"}:
        raise ValueError("reference_background must be source or alpha_neutral")
    timeout = raw.get("timeout_seconds", worker.default_timeout())
    if type(timeout) is not int or not 30 <= timeout <= worker.MAX_TIMEOUT:
        raise ValueError(f"timeout_seconds 必須是 30–{worker.MAX_TIMEOUT} 的整數。")
    payload = {
        "prompt": prompt,
        "model": "ltx23-distilled",
        "mode": mode,
        "image_id": image_id,
        "audio": raw.get("audio", True),
        "width": width,
        "height": height,
        "aspect_ratio": ratio,
        "frames": frames,
        "fps": fps,
        "seed": seed,
        "offload": bool(raw.get("offload", False)),
        "profile": raw.get("profile", "compat-v1"),
        "image_strength": strength if mode == "i2v" else None,
        "reference_background": reference_background if mode == "i2v" else None,
        "character": character,
        "timeout_seconds": timeout,
        "media_type": "video",
        "render_mode": render_mode,
        "directing": directing,
        "source_geometry": source_geometry,
    }
    if render_mode == "sequence":
        payload.update(mv_timeline.normalize_sequence(raw, payload, worker.MAX_FRAMES, asset_by_id))
    return payload


def replay_job(key, request_hash):
    if STORE is None:
        return None
    previous = STORE.by_key(key)
    if previous is None:
        return None
    saved, fingerprint = previous
    if fingerprint != request_hash:
        return 409, {"error": "Idempotency key was already used with a different payload", "code": "idempotency_conflict"}
    if saved.get("deleted_at"):
        return 410, {"error": "This job was deleted; use a new idempotency key for a new generation", "code": "job_deleted"}
    current = JOBS.get(saved["id"], saved)
    return 200, {**public_job(current), "idempotent_replay": True}


def submit_job(payload, *, key=None, request_hash=None, external=None, requested=None, owner_id=None):
    with LOCK:
        if key:
            replay = replay_job(key, request_hash)
            if replay:
                return replay
        if STOPPING:
            return 503, {"error": "Worker is shutting down", "code": "worker_unavailable"}
        if any(job["status"] in {"queued", "running"} for job in JOBS.values()):
            return 409, {"error": "GPU busy; retry this request later with the same idempotency key", "code": "worker_busy", "retry_after_seconds": 5}
        reference_ids = [*character_consistency.reference_ids(payload.get("character"), payload.get("image_id")),
                         payload.get("timeline", {}).get("audio_id")]
        for reference_id in dict.fromkeys(reference_ids):
            # Serialize final reference validation with deletion and admission.
            if not reference_id:
                continue
            asset = asset_by_id(reference_id)
            if owner_id and asset.get("owner_id") != owner_id:
                raise ValueError("Reference asset is not available to this account")
        adapter = model_registry.get(payload["model"])
        if adapter.requires_cuda and not RUNTIME.get("cuda_available"):
            return 503, {"error": "CUDA GPU unavailable", "code": "worker_unavailable"}
        if key and STORE is None:
            return 503, {"error": "Durable job store unavailable", "code": "store_unavailable"}
        if owner_id and (STORE is None or STORE.recent_count(owner_id, time.time() - 86400) >= int(os.environ.get("LTX_USER_DAILY_JOB_LIMIT", "20"))):
            return 429, {"error": "Daily generation limit reached", "code": "daily_job_limit"}
        if shutil.disk_usage(OUTPUT_DIR).free < 5 * 1024**3:
            return 503, {"error": "Less than 5 GiB free; no generation accepted", "code": "insufficient_disk"}
        job_id = uuid.uuid4().hex[:12]
        filename = f"ltx-ui-{time.strftime('%Y%m%d-%H%M%S')}-{job_id}.{adapter.extension}"
        job = {**payload, "id": job_id, "status": "queued", "progress": 0,
               "message": "任務已排入本機 GPU。", "created_at": time.time(), "filename": filename,
               "output_url": f"/generated/{filename}", "device": RUNTIME.get("device"),
               "provenance": generation_provenance(payload), "external": external,
               "requested_duration_seconds": requested, "contract_version": worker.CONTRACT_VERSION, "owner_id": owner_id,
               "media_type": adapter.media_type, "content_type": adapter.content_type}
        if STORE is not None:
            # Admission fails before GPU work if durable recording fails.
            STORE.record(job, key=key, request_hash=request_hash)
        JOBS[job_id] = job
    try:
        threading.Thread(target=run_job, args=(job_id, payload), name=f"ltx-job-{job_id}", daemon=True).start()
    except RuntimeError:
        with LOCK:
            job.update(status="failed", finished_at=time.time(), message="Could not start GPU worker thread.")
            record_job(job)
        # The task already has a durable ID. Return it so retries cannot hide
        # an accepted job behind an ambiguous network/server error.
    return 202, public_job(job)


class Handler(AuthHandlerMixin, MediaHandlerMixin, BaseHTTPRequestHandler):
    server_version = "LTXStudioLocal/1.0"

    @property
    def access_settings(self):
        return ACCESS_SETTINGS

    @property
    def access_client(self):
        return ACCESS_CLIENT

    @property
    def access_verifier(self):
        return ACCESS_VERIFIER

    @property
    def user_auth_enabled(self):
        return USER_AUTH_ENABLED

    @property
    def auth_store(self):
        return AUTH

    @property
    def auth_settings(self):
        return AUTH_SETTINGS

    @property
    def auth_origins(self):
        return ALLOWED_ORIGINS | ({AUTH_SETTINGS.origin} if AUTH_SETTINGS.origin else set()) | ({ACCESS_SETTINGS.origin} if ACCESS_SETTINGS.enabled else set())

    def worker_key(self):
        return worker.api_key(SITE_ROOT)

    def check_reference_owner(self, raw):
        if isinstance(raw, dict):
            image_ids = [raw.get("image_id")]
            character = raw.get("character")
            if isinstance(character, dict) and isinstance(character.get("references"), list):
                image_ids.extend(item.get("image_id") for item in character["references"] if isinstance(item, dict))
            for image_id in dict.fromkeys(image_ids):
                if not image_id:
                    continue
                asset = asset_by_id(str(image_id))
                if not self.can_access(asset) or asset.get("kind") != "image":
                    raise ValueError("Reference asset is not available to this account")
        timeline = raw.get("timeline") if isinstance(raw, dict) else None
        if isinstance(timeline, dict) and timeline.get("audio_id"):
            asset = asset_by_id(str(timeline["audio_id"]))
            if not self.can_access(asset) or asset.get("kind") != "audio":
                raise ValueError("Audio asset is not available to this account")

    def cors_origin(self) -> str:
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin in ALLOWED_ORIGINS:
            return origin
        return next(iter(ALLOWED_ORIGINS), "http://localhost:3000")

    def send_json(self, status: int, payload: dict[str, Any], *, extra_headers=None) -> None:
        body = b"" if status == 204 else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", self.cors_origin())
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, DELETE, OPTIONS")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("Vary", "Origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        if payload.get("code") == "worker_busy":
            self.send_header("Retry-After", "5")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_json(204, {})

    def do_HEAD(self):
        self.do_GET()

    def do_DELETE(self):
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin not in self.auth_origins:
            self.send_json(403, {"error": "Origin not allowed", "code": "origin_not_allowed"})
            return
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0":
            self.close_connection = True
            self.send_json(400, {"error": "DELETE must not have a body", "code": "invalid_request"})
            return
        # Destructive routes always need a real account or privileged service key,
        # even on installations that have disabled browser account authentication.
        if not self.require_principal(worker_only=True):
            return
        path = urlparse(self.path).path
        match = re.fullmatch(r"/api/(?:v1/)?(jobs|assets)/([a-f0-9]{12,32})", path)
        if not match:
            self.send_json(404, {"error": "Not found", "code": "not_found"})
            return
        kind, identity = match.groups()
        try:
            with LOCK:
                if kind == "assets":
                    try:
                        asset = asset_by_id(identity)
                    except ValueError:
                        self.send_json(404, {"error": "Asset not found", "code": "asset_not_found"})
                        return
                    if not self.can_access(asset):
                        self.send_json(404, {"error": "Asset not found", "code": "asset_not_found"})
                        return
                    if any(identity in (*character_consistency.reference_ids(j.get("character"), j.get("image_id")),
                                        j.get("timeline", {}).get("audio_id")) and j["status"] in {"queued", "running"} for j in JOBS.values()):
                        self.send_json(409, {"error": "Reference is being used by a generation job", "code": "asset_in_use"})
                        return
                    with media_store.UPLOAD_LOCK:
                        archive = prepare_archive([media_store.UPLOAD_DIR / f"{identity}.json", asset_path(asset)],
                                                  TRASH_DIR, {"kind": "asset", "asset": asset})
                        archive.remove_sources()
                else:
                    if STORE is None:
                        raise sqlite3.OperationalError()
                    job = JOBS.get(identity) or STORE.get(identity)
                    if not job or (self.principal["kind"] != "service" and job.get("owner_id") != self.principal["id"]):
                        self.send_json(404, {"error": "Job not found", "code": "job_not_found"})
                        return
                    if job.get("deleted_at"):
                        self.send_json(200, {"deleted": True, "recoverable": True})
                        return
                    if job["status"] in {"queued", "running"}:
                        self.send_json(409, {"error": "Cancel the active job and wait for it to stop first", "code": "job_active"})
                        return
                    filename = job.get("filename", "")
                    if not re.fullmatch(r"[A-Za-z0-9_-]+\.(mp4|png|txt)", filename):
                        raise ValueError("Invalid stored media filename")
                    names = {filename, str(Path(filename).with_suffix(".json")), str(Path(filename).with_suffix(".jpg"))}
                    paths = [folder / name for folder in (OUTPUT_DIR, LEGACY_OUTPUT_DIR, WORK_DIR / identity) for name in sorted(names)]
                    private_work = WORK_DIR / identity
                    if private_work.is_dir() and not private_work.is_symlink():
                        paths.extend(path for path in private_work.iterdir() if path.suffix in {".mp4", ".wav", ".png", ".jpg", ".json"})
                    paths = list(dict.fromkeys(paths))
                    archive = prepare_archive(paths, TRASH_DIR, {"kind": "job", "job": public_job(job)})
                    tombstone = {**public_job(job), "deleted_at": time.time()}
                    STORE.record(tombstone)
                    job.update(deleted_at=tombstone["deleted_at"])
                    JOBS[identity] = job
                    try:
                        archive.remove_sources()
                    except (OSError, ValueError):
                        # The durable tombstone denies every download even if a
                        # filesystem error leaves an original name behind.
                        self.send_json(200, {"deleted": True, "recoverable": True, "cleanup_pending": True})
                        return
            self.send_json(200, {"deleted": True, "recoverable": True})
        except (OSError, sqlite3.Error, ValueError):
            self.send_json(503, {"error": "Media deletion failed; retained files are recoverable", "code": "delete_failed"})

    def worker_authorized(self):
        return self.require_principal(worker_only=True)

    def worker_get(self, path):
        if not self.worker_authorized():
            return
        if path == "/api/v1/models":
            self.send_json(200, model_registry.catalog(RUNTIME))
            return
        if path == "/api/v1/capabilities":
            self.send_json(200, {**worker.capabilities(RUNTIME), "job_store_ready": STORE is not None,
                                 "job_store_warning": STORE_ERROR})
            return
        if path == "/api/v1/openapi.json":
            from worker_schema import openapi_document
            self.send_json(200, openapi_document())
            return
        if path == "/api/v1/assets":
            self.send_json(200, {"assets": [{**a, "url": f"/api/v1/assets/{a['id']}/file"} for a in list_assets() if self.can_access(a)],
                                 "shared": self.principal["kind"] == "service", "max_upload_bytes": MAX_UPLOAD})
            return
        asset_match = re.fullmatch(r"/api/v1/assets/([a-f0-9]{32})/file", path)
        if asset_match:
            try:
                asset = asset_by_id(asset_match.group(1))
                if not self.can_access(asset):
                    raise ValueError("Asset not found")
                self.serve_media(asset_path(asset), asset["content_type"], asset["name"])
            except ValueError:
                self.send_json(404, {"error": "Asset not found", "code": "asset_not_found"})
            return
        if path == "/api/v1/jobs":
            try:
                if STORE is None:
                    raise sqlite3.OperationalError()
                query = parse_qs(urlparse(self.path).query)
                result = STORE.list_jobs(int(query.get("limit", [30])[0]), int(query.get("offset", [0])[0]), self.principal["id"])
                with LOCK:
                    result["jobs"] = [worker.describe_job(public_job(JOBS.get(job["id"], job))) for job in result["jobs"]]
                self.send_json(200, result)
            except ValueError:
                self.send_json(400, {"error": "limit must be 1–100, offset >= 0", "code": "invalid_request"})
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Job store unavailable", "code": "store_unavailable"})
            return
        match = re.fullmatch(r"/api/v1/jobs/([a-f0-9]{12,32})(/video|/artifact)?", path)
        if not match:
            self.send_json(404, {"error": "Not found"})
            return
        try:
            with LOCK:
                job = JOBS.get(match.group(1)) or (STORE.get(match.group(1)) if STORE else None)
                snapshot = public_job(job) if job else None
                if snapshot and not self.can_access(snapshot):
                    snapshot = None
            if snapshot is None:
                self.send_json(404, {"error": "Job not found", "code": "job_not_found"})
            elif match.group(2):
                if snapshot["status"] != "succeeded":
                    self.send_json(409, {"error": "Artifact is not ready", "code": "artifact_not_ready"})
                    return
                if match.group(2) == "/video" and snapshot.get("media_type", "video") != "video":
                    self.send_json(404, {"error": "Not a video artifact"})
                    return
                filename = snapshot.get("filename", "")
                if not re.fullmatch(r"[A-Za-z0-9_-]+\.(mp4|png|txt)", filename):
                    self.send_json(404, {"error": "Artifact not found"})
                    return
                self.serve_media(output_location(filename), snapshot.get("content_type", "video/mp4"), filename)
            else:
                self.send_json(200, worker.describe_job(snapshot))
        except (OSError, sqlite3.Error):
            self.send_json(503, {"error": "Job store unavailable", "code": "store_unavailable"})

    def worker_post(self, path):
        if not self.worker_authorized():
            return
        if path == "/api/v1/assets":
            self.receive_asset(LTX_PYTHON)
            return
        cancel = re.fullmatch(r"/api/v1/jobs/([a-f0-9]{12,32})/cancel", path)
        if cancel:
            try:
                with LOCK:
                    job = JOBS.get(cancel.group(1)) or (STORE.get(cancel.group(1)) if STORE else None)
                    if job and not self.can_access(job):
                        job = None
                    if job is None:
                        status, response = 404, {"error": "Job not found", "code": "job_not_found"}
                    elif job["status"] in {"queued", "running"}:
                        if STORE is None:
                            raise sqlite3.OperationalError()
                        STORE.record({**job, "cancel_requested": True})
                        job["cancel_requested"] = True
                        status, response = 202, worker.describe_job(public_job(job))
                    else:
                        status, response = 200, worker.describe_job(public_job(job))
                self.send_json(status, response)
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Could not persist cancellation", "code": "store_unavailable"})
            return
        if path not in {"/api/v1/jobs", "/api/v1/validate"}:
            self.send_json(404, {"error": "Not found"})
            return
        if path == "/api/v1/jobs" and STORE is None:
            self.send_json(503, {"error": "Durable job store unavailable", "code": "store_unavailable"})
            return
        try:
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.send_json(415, {"error": "Content-Type must be application/json"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 128_000:
                raise ValueError("Body must be 1–128000 bytes")
            self.connection.settimeout(15)
            raw = json.loads(self.rfile.read(length))
            key, fingerprint = worker.validate_request(raw, self.headers.get("Idempotency-Key", "") if path == "/api/v1/jobs" else "validate-only")
            if self.principal["id"]:
                from user_auth import digest
                key = digest(f"user:{self.principal['id']}:{key}")
            if path == "/api/v1/validate":
                self.check_reference_owner(raw)
                payload, external, requested = worker.parse_request(raw, parse_payload)
                self.send_json(200, worker.validation_result(payload, external, requested))
                return
            with LOCK:
                replay = replay_job(key, fingerprint)
            if replay:
                status, result = replay
            else:
                self.check_reference_owner(raw)
                payload, external, requested = worker.parse_request(raw, parse_payload)
                status, result = submit_job(payload, key=key, request_hash=fingerprint, external=external, requested=requested, owner_id=self.principal["id"])
            if "id" in result:
                result = {**worker.describe_job(result), "idempotent_replay": status == 200}
            self.send_json(status, result)
        except (ValueError, TypeError, OverflowError) as exc:
            self.send_json(400, {"error": str(exc)[:300], "code": "invalid_request"})
        except (OSError, sqlite3.Error):
            self.send_json(503, {"error": "Could not persist job; no new generation was accepted", "code": "store_unavailable"})

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/auth/"):
            self.auth_get(path)
            return
        if path.startswith("/api/v1/"):
            self.worker_get(path)
            return
        if not self.require_principal():
            return
        if path == "/api/models":
            self.send_json(200, model_registry.catalog(RUNTIME))
            return
        if path == "/api/assets":
            self.send_json(200, {"assets": [a for a in list_assets() if self.can_access(a)], "max_upload_bytes": MAX_UPLOAD, "shared": self.principal["kind"] == "service"})
            return
        asset_match = re.fullmatch(r"/api/assets/([a-f0-9]{32})/file", path)
        if asset_match:
            try:
                asset = asset_by_id(asset_match.group(1))
                if not self.can_access(asset):
                    raise ValueError("Asset not found")
                self.serve_media(asset_path(asset), asset["content_type"], asset["name"])
            except ValueError:
                self.send_json(404, {"error": "找不到素材。"})
            return
        media_match = re.fullmatch(r"/generated/([a-zA-Z0-9_-]+\.(mp4|jpg|png|txt))", path)
        if media_match:
            try:
                filename = str(Path(media_match.group(1)).with_suffix(".mp4")) if media_match.group(2) == "jpg" else media_match.group(1)
                stored = STORE.by_filename(filename) if STORE else None
                if stored and stored.get("deleted_at"):
                    self.send_json(404, {"error": "Artifact not found"})
                    return
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Job store unavailable"})
                return
            if self.principal["kind"] != "service":
                try:
                    filename = str(Path(media_match.group(1)).with_suffix(".mp4")) if media_match.group(2) == "jpg" else media_match.group(1)
                    job = STORE.by_filename(filename) if STORE else None
                    if not job or not self.can_access(job) or job["status"] != "succeeded":
                        self.send_json(404, {"error": "Artifact not found"})
                        return
                except (OSError, sqlite3.Error):
                    self.send_json(503, {"error": "Job store unavailable"})
                    return
            mime = {"mp4": "video/mp4", "jpg": "image/jpeg", "png": "image/png", "txt": "text/plain; charset=utf-8"}[media_match.group(2)]
            self.serve_media(output_location(media_match.group(1)), mime)
            return
        legacy_media = re.fullmatch(r"/media/([a-zA-Z0-9_.-]+\.(mp4|png|jpg|webp))", path)
        if legacy_media:
            if self.principal["kind"] != "service":
                self.send_json(404, {"error": "Artifact not found"})
                return
            self.serve_media(SITE_ROOT / "data/worker/legacy-media" / legacy_media.group(1), "video/mp4" if legacy_media.group(2) == "mp4" else "image/" + legacy_media.group(2))
            return
        if path == "/api/health":
            with LOCK:
                active_job = next((public_job(job) for job in JOBS.values() if job["status"] in {"queued", "running"}), None)
            self.send_json(200, {"ok": LAUNCHER.exists() and RUNTIME.get("cuda_available", False), "model": "LTX-2.3 Distilled", "busy": bool(active_job), "active_job": active_job if active_job and self.can_access(active_job) else None, "runtime": RUNTIME, "worker_api": bool(worker.api_key(SITE_ROOT)) and STORE is not None, "job_store_warning": STORE_ERROR})
            return
        if path == "/api/outputs":
            if self.principal["kind"] != "service":
                try:
                    if STORE is None:
                        raise sqlite3.OperationalError()
                    jobs = STORE.list_jobs(100, 0, self.principal["id"])["jobs"]
                    self.send_json(200, {"outputs": [public_job(j) for j in jobs if j["status"] == "succeeded"]})
                except (OSError, sqlite3.Error):
                    self.send_json(503, {"error": "Job store unavailable"})
                return
            outputs: list[dict[str, Any]] = []
            seen: set[str] = set()
            with LOCK:
                completed = [public_job(job) for job in JOBS.values() if job["status"] == "succeeded" and not job.get("deleted_at")]
            for job in completed:
                outputs.append(job)
                seen.add(job["filename"])
            for video_path in sorted(OUTPUT_DIR.glob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True):
                if video_path.name in seen:
                    continue
                metadata_path = video_path.with_suffix(".json")
                # Never show an in-progress or interrupted MP4 as a completed result.
                if not metadata_path.exists():
                    continue
                if metadata_path.exists():
                    try:
                        saved = json.loads(metadata_path.read_text(encoding="utf-8"))
                        stored = STORE.get(saved.get("id", "")) if STORE else None
                        if saved.get("status") == "succeeded" and not saved.get("deleted_at") and not (stored and stored.get("deleted_at")):
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
                if job is None and STORE is not None:
                    job = STORE.get(match.group(1))
                payload = public_job(job) if job else None
                if payload and not self.can_access(payload):
                    payload = None
                if payload and payload["status"] in {"interrupted", "cancelled"}:
                    payload["status"] = "failed"  # Older UI only knows succeeded/failed.
            if payload is None:
                self.send_json(404, {"error": "找不到這個任務。"})
            else:
                self.send_json(200, payload)
            return
        self.send_json(404, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        origin = self.headers.get("Origin", "").rstrip("/")
        if origin and origin not in self.auth_origins:
            self.send_json(403, {"error": "Origin not allowed"})
            return
        if self.headers.get("Transfer-Encoding"):
            self.send_json(400, {"error": "Content-Length required"})
            return
        if urlparse(self.path).path.startswith("/api/auth/"):
            self.auth_post(urlparse(self.path).path)
            return
        if urlparse(self.path).path.startswith("/api/v1/"):
            self.worker_post(urlparse(self.path).path)
            return
        if not self.require_principal():
            return
        if urlparse(self.path).path == "/api/assets":
            self.receive_asset(LTX_PYTHON)
            return
        if urlparse(self.path).path != "/api/jobs":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.send_json(415, {"error": "Content-Type must be application/json"})
                return
            if not RUNTIME.get("cuda_available"):
                self.send_json(503, {"error": RUNTIME.get("error", "CUDA GPU 未就緒。")})
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 32_000:
                raise ValueError("請求內容大小無效。")
            raw = json.loads(self.rfile.read(length))
            self.check_reference_owner(raw)
            payload = parse_payload(raw)
            status, response = submit_job(payload, owner_id=self.principal["id"])
            self.send_json(status, response)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})
        except (OSError, sqlite3.Error):
            self.send_json(503, {"error": "任務紀錄暫時無法儲存，請稍後重試。"})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[LTX API] {self.address_string()} - {format % args}")


def sync_pending_access():
    """Retry only pre-write failures; never resubmit a completed/uncertain append."""
    while not STOPPING:
        try:
            with AUTH.connect() as db:
                rows = db.execute("SELECT e.user_id FROM cloudflare_enrollments e JOIN users u ON u.id=e.user_id WHERE e.state='pending' AND e.target=? AND u.disabled=0 ORDER BY e.created_at LIMIT 5",
                                  (ACCESS_SETTINGS.target,)).fetchall()
            for row in rows:
                if STOPPING:
                    return
                sync_enrollment(AUTH, ACCESS_CLIENT, row["user_id"])
        except (OSError, ValueError, sqlite3.Error):
            print("Cloudflare enrollment storage unavailable; no access was granted by fallback.")
        for _ in range(30):
            if STOPPING:
                return
            time.sleep(1)


if __name__ == "__main__":
    if ACCESS_SETTINGS.enabled and not USER_AUTH_ENABLED:
        raise SystemExit("Cloudflare enrollment requires local account authentication.")
    model_registry.load_installed()
    if USER_AUTH_ENABLED:
        from media_store import UPLOAD_DIR
        from service_layout import check_private_layout
        try:
            check_private_layout(SITE_ROOT, OUTPUT_DIR, UPLOAD_DIR)
            if not AUTH_SETTINGS.origin:
                raise ValueError("Configure LTX_PUBLIC_ORIGIN before enabling service accounts.")
        except ValueError as exc:
            raise SystemExit(str(exc)) from None
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if WORK_DIR.resolve().is_relative_to(SITE_ROOT / "public") or WORK_DIR.resolve().is_relative_to(OUTPUT_DIR):
        raise SystemExit("LTX_WORK_DIR must be private and outside public/output directories.")
    WORK_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    if WORK_DIR.stat().st_dev != OUTPUT_DIR.stat().st_dev:
        raise SystemExit("LTX_WORK_DIR and LTX_OUTPUT_DIR must share a filesystem for atomic publication.")
    # One backend instance per machine/project, even if started on another port.
    # Keep this descriptor alive for the full server lifetime.
    worker_state = SITE_ROOT / "data/worker"
    worker_state.mkdir(parents=True, exist_ok=True, mode=0o700)
    instance_lock = (worker_state / "instance.lock").open("a")
    try:
        fcntl.flock(instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another LTX API instance is active; refusing a second GPU worker.")
    try:
        applied = database.apply_migrations()
        if applied:
            print(f"Applied migrations: {', '.join(applied)}", flush=True)
    except Exception as exc:  # noqa: BLE001 - any failure here must stop the server
        raise SystemExit(f"Database migration failed: {exc}") from None
    try:
        AUTH = AuthStore(SITE_ROOT / "data/worker/accounts.sqlite3")
        STORE = ProductionStore()
        STORE.recover(OUTPUT_DIR)
        if LEGACY_OUTPUT_DIR != OUTPUT_DIR:
            STORE.recover(LEGACY_OUTPUT_DIR)
    except (OSError, ValueError, psycopg.Error):
        STORE = None
        STORE_ERROR = "任務紀錄初始化失敗，請檢查資料庫連線與權限。"
    if ACCESS_SETTINGS.enabled and AUTH is not None:
        threading.Thread(target=sync_pending_access, name="cloudflare-enrollment", daemon=True).start()
    if not LAUNCHER.exists():
        raise SystemExit(f"Missing launcher: {LAUNCHER}")
    if not LTX_REPO_ROOT.exists():
        raise SystemExit(f"Missing LTX repository: {LTX_REPO_ROOT}. Set LTX_REPO_ROOT in .env.local.")
    try:
        probe = subprocess.run([str(LTX_PYTHON), str(SITE_ROOT / "scripts/run_local.py"), "--check"], capture_output=True, text=True, timeout=30, check=True)
        RUNTIME.update(json.loads(probe.stdout))
    except (OSError, ValueError, subprocess.SubprocessError):
        RUNTIME.update(cuda_available=False, error="無法檢查模型 Python / CUDA；請查看主機環境設定。")
    print(f"Runtime: {json.dumps(RUNTIME, ensure_ascii=False)}", flush=True)
    print(f"LTX Studio local API: http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    resume_request = claim_resume_request()
    if resume_request is not None:
        resume_job_id, resume_payload = resume_request
        print(f"Resuming sequence job {resume_job_id} from verified work products.", flush=True)
        threading.Thread(target=run_job, args=(resume_job_id, resume_payload), kwargs={"resume": True},
                         name=f"ltx-job-{resume_job_id}", daemon=True).start()

    def shutdown(_signum, _frame):
        global STOPPING
        STOPPING = True
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        server.serve_forever()
    finally:
        STOPPING = True
        server.server_close()
        for thread in threading.enumerate():
            if thread.name.startswith("ltx-job-"):
                thread.join(timeout=15)
