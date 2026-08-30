"""Strict server-to-server contract; no URL fetching, training or shell inputs."""
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import model_registry


MAX_FRAMES = 257
CONTRACT_VERSION = "1.2.0"
# Immutable named defaults. Explicit request fields override a profile; return
# all resolved values so clients never have to reconstruct them from defaults.
PROFILES = {
    "compat-v1": {"width": 768, "height": 512, "frames": 49, "fps": 24, "audio": True},
    "preview-v1": {"width": 512, "height": 320, "frames": 49, "fps": 24, "audio": False},
    "landscape-v1": {"width": 1024, "height": 576, "frames": 97, "fps": 24, "audio": False},
    "portrait-v1": {"width": 576, "height": 1024, "frames": 97, "fps": 24, "audio": False},
}
MAX_TIMEOUT = 7200
PARAMETERS = ("model", "profile", "mode", "prompt", "image_id", "image_strength", "width", "height",
              "frames", "fps", "seed", "audio", "offload", "timeout_seconds", "parameters", "media_type")


def default_timeout():
    return min(MAX_TIMEOUT, max(30, int(os.environ.get("LTX_JOB_TIMEOUT_SECONDS", "3600"))))


def api_key(root):
    key = os.environ.get("LTX_WORKER_API_KEY", "")
    if not key:
        path = Path(os.environ.get("LTX_WORKER_API_KEY_FILE", Path(root) / "data/worker/api-key"))
        try:
            if path.is_symlink():
                return ""
            key = path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return key if len(key) >= 32 else ""


def authorized(header, key):
    return bool(key) and hmac.compare_digest(header.encode("utf-8"), f"Bearer {key}".encode("utf-8"))


def validate_request(raw, idempotency_key):
    if not isinstance(raw, dict):
        raise ValueError("Expected a JSON object")
    allowed = {"prompt", "model", "mode", "image_id", "width", "height", "frames", "fps",
               "duration_seconds", "seed", "audio", "offload", "external", "profile",
               "image_strength", "timeout_seconds", "parameters"}
    if set(raw) - allowed:
        raise ValueError("Unsupported field. Character/music/marketing assets belong to the calling project.")
    if not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", idempotency_key):
        raise ValueError("Idempotency-Key must be 8–128 letters, digits, dots, underscores, colons or hyphens")
    if not isinstance(raw.get("prompt"), str):
        raise ValueError("prompt must be a string")
    for name in ("width", "height", "frames", "fps", "seed", "timeout_seconds"):
        if name in raw and type(raw[name]) is not int:
            raise ValueError(f"{name} must be an integer")
    external = raw.get("external", {})
    if not isinstance(external, dict) or set(external) - {"project_id", "asset_id", "shot_id", "request_id"}:
        raise ValueError("external is optional and accepts project_id, asset_id, shot_id, request_id")
    if any(not isinstance(value, str) or not re.fullmatch(r"[\w.:-]{1,120}", value) for value in external.values()):
        raise ValueError("External IDs must be short identifiers, not URLs or paths")
    # Hash the original request so a lost response can be replayed even if the
    # uploaded reference is later missing. Defaults must not drift on retries.
    request_hash = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()
    scoped_key = hashlib.sha256(json.dumps([external.get("project_id"), idempotency_key]).encode()).hexdigest()
    return scoped_key, request_hash


def parse_request(raw, parse_payload):
    if raw.get("model", "ltx23-distilled") != "ltx23-distilled":
        payload = dict(raw)
        external = payload.pop("external", {})
        return model_registry.get(raw["model"]).normalize(payload), external, None
    if "parameters" in raw:
        raise ValueError("LTX uses its existing top-level parameters, not a parameters object")
    profile = raw.get("profile", "compat-v1")
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError("Unknown profile; query capabilities for versioned profiles")
    payload = {**PROFILES[profile], **raw, "profile": profile}
    requested = payload.pop("duration_seconds", None)
    external = payload.pop("external", {})
    if payload.get("mode", "t2v") == "t2v" and ("image_id" in raw or "image_strength" in raw):
        raise ValueError("image_id and image_strength require mode=i2v")
    if "duration_seconds" in raw:
        if type(requested) not in (int, float) or not math.isfinite(requested) or requested <= 0:
            raise ValueError("duration_seconds must be positive and finite")
        if "frames" in raw:
            raise ValueError("Use duration_seconds OR frames, not both")
        fps = payload.get("fps", 24)
        if type(fps) is not int or not 8 <= fps <= 60:
            raise ValueError("fps must be an integer from 8 to 60")
        if requested > MAX_FRAMES / fps:
            raise ValueError(f"Duration exceeds worker limit: {MAX_FRAMES / fps:.3f}s at {fps} FPS; no silent trimming")
        payload["frames"] = max(9, math.ceil((requested * fps - 1) / 8) * 8 + 1)
    return parse_payload(payload), external, requested


def resolved_parameters(payload):
    return {name: payload.get(name) for name in PARAMETERS}


def validation_result(payload, external, requested):
    return {"valid": True, "contract_version": CONTRACT_VERSION,
            "resolved_parameters": resolved_parameters(payload), "external": external,
            "requested_duration_seconds": requested,
            "configured_duration_seconds": payload["frames"] / payload["fps"] if payload.get("frames") and payload.get("fps") else None,
            "warnings": ["Parameter validation is not a GPU memory or visual quality guarantee."]}


def describe_job(job):
    job_id = job["id"]
    result = {"id": job_id, "status": job["status"], "progress": job.get("progress", 0),
              "phase": job.get("phase"), "message": job.get("message"),
              "external": job.get("external"), "status_url": f"/api/v1/jobs/{job_id}",
              "runtime_seconds": job.get("runtime_seconds"), "elapsed_seconds": job.get("elapsed_seconds"),
              "requested_duration_seconds": job.get("requested_duration_seconds"),
              "configured_duration_seconds": job["frames"] / job["fps"] if job.get("frames") and job.get("fps") else None,
              "media_type": job.get("media_type", "video"),
              "frames": job.get("frames"), "fps": job.get("fps"),
              "width": job.get("width"), "height": job.get("height"),
              "measured_media": job.get("measured_media"), "artifacts": [],
              "contract_version": job.get("contract_version", "1.0.0"),
              "resolved_parameters": resolved_parameters(job),
              "cancel_requested": job.get("cancel_requested", False),
              "error": job.get("error"), "quality_control": job.get("quality_control"),
              "provenance": job.get("provenance"),
              "created_at": job.get("created_at"), "started_at": job.get("started_at"),
              "finished_at": job.get("finished_at")}
    if job["status"] == "succeeded":
        kind = job.get("media_type", "video")
        result["artifacts"] = [{"kind": kind, "content_type": job.get("content_type", "video/mp4"),
                                "url": f"/api/v1/jobs/{job_id}/{'video' if kind == 'video' else 'artifact'}?download=1",
                                "size_bytes": job.get("size_bytes"),
                                "sha256": job.get("artifact_sha256")}]
    return result


def capabilities(runtime):
    return {"api_version": "1", "contract_version": CONTRACT_VERSION,
            "openapi_url": "/api/v1/openapi.json", "role": "video_generation_worker", "ready": bool(runtime.get("cuda_available")),
            "models": list(model_registry.ADAPTERS), "model_catalog_url": "/api/v1/models", "modes": ["t2v", "i2v"],
            "browser_account_auth": True, "user_asset_isolation": True, "service_key_is_privileged": True,
            "limits": {"max_frames": MAX_FRAMES, "frame_multiple_plus_one": 8, "fps_min": 8, "fps_max": 60,
                       "dimension_min": 256, "dimension_max": 1536, "dimension_multiple": 64,
                       "max_upload_bytes": 50 * 1024**2, "max_library_bytes": 2 * 1024**3,
                       "timeout_seconds_min": 30, "timeout_seconds_max": MAX_TIMEOUT},
            "profiles": PROFILES, "default_profile": "compat-v1", "default_timeout_seconds": default_timeout(),
            "image_strength": {"min": 0, "max": 1, "default": 0.8},
            "sampling": {"schedule": "distilled_fixed", "stage_1_steps": 8, "stage_2_steps": 3,
                         "custom_steps": False, "custom_guidance": False},
            "quality_control": "full_decode_v1_technical_gate_visual_warnings_only",
            "cancel": True, "validation_without_generation": True,
            "external_required": False,
            "duration_rounding": "ceil_to_8n_plus_1_no_silent_clamp", "gpu_concurrency": 1,
            "queue": "caller_managed_busy_returns_409", "idempotency": True,
            "download": "authenticated_binary_with_range", "reference_input": "uploaded_image_id_at_frame_0",
            "music_conditioning": False, "character_database": False, "automatic_training": False,
            "automatic_updates": False, "webhooks": False, "tenant_isolation": False,
            "service_key_scope": "privileged_host_access"}
