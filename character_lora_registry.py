"""Trusted, host-side character LoRA registry.

Clients select stable IDs and strengths.  Weight paths and trigger tokens come only
from administrator-installed metadata under ``LTX_CHARACTER_LORA_DIR``.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re


ID_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,63}")
SHA_RE = re.compile(r"[a-f0-9]{64}")
KINDS = {"identity", "wardrobe"}


def registry_root() -> Path:
    configured = os.environ.get("LTX_CHARACTER_LORA_DIR")
    if configured:
        return Path(configured)
    repo_root = Path(
        os.environ.get(
            "LTX_REPO_ROOT",
            Path(__file__).resolve().parent / "vendor" / "LTX-2",
        )
    )
    return repo_root / "models" / "character-loras"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_file(metadata_path: Path) -> dict:
    root = registry_root().resolve()
    raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    required = {
        "id", "label", "kind", "model_family", "weight_filename",
        "weight_sha256", "trigger_token", "default_strength",
        "validated_strength_range", "compatible_models", "compatible_modes",
        "approval_status", "version",
    }
    if not isinstance(raw, dict) or required - set(raw):
        raise ValueError("metadata is missing required fields")
    if not isinstance(raw["id"], str) or not ID_RE.fullmatch(raw["id"]):
        raise ValueError("invalid registry id")
    if raw["kind"] not in KINDS or raw["model_family"] != "ltx-2.5":
        raise ValueError("unsupported kind or model family")
    if raw["approval_status"] != "approved":
        raise ValueError("LoRA is not approved")
    if not isinstance(raw["label"], str) or not raw["label"].strip() or len(raw["label"]) > 120:
        raise ValueError("label must be a non-empty string up to 120 characters")
    if not isinstance(raw["version"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,31}", raw["version"]):
        raise ValueError("invalid version")
    filename = raw["weight_filename"]
    if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".safetensors"):
        raise ValueError("weight_filename must be a safetensors basename")
    weight = (root / filename).resolve()
    if weight.parent != root or not weight.is_file() or weight.is_symlink():
        raise ValueError("weight file is unavailable")
    expected_sha = raw["weight_sha256"]
    if not isinstance(expected_sha, str) or not SHA_RE.fullmatch(expected_sha):
        raise ValueError("invalid weight_sha256")
    strength_range = raw["validated_strength_range"]
    if not isinstance(strength_range, dict) or set(strength_range) != {"min", "max"}:
        raise ValueError("validated_strength_range must contain min and max")
    low, high = strength_range["min"], strength_range["max"]
    default = raw["default_strength"]
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in (low, high, default)):
        raise ValueError("strength values must be finite numbers")
    if not 0 <= low <= default <= high <= 2:
        raise ValueError("strength range must be within 0..2 and contain the default")
    if not isinstance(raw["trigger_token"], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{2,63}", raw["trigger_token"]):
        raise ValueError("invalid trigger token")
    if (
        not isinstance(raw["compatible_models"], list)
        or not raw["compatible_models"]
        or any(not isinstance(item, str) or not item for item in raw["compatible_models"])
    ):
        raise ValueError("compatible_models must be a non-empty list")
    if (
        not isinstance(raw["compatible_modes"], list)
        or not raw["compatible_modes"]
        or any(not isinstance(item, str) for item in raw["compatible_modes"])
        or not set(raw["compatible_modes"]) <= {"t2v", "i2v"}
    ):
        raise ValueError("compatible_modes must contain only t2v/i2v")
    actual_sha = _sha256(weight)
    if actual_sha != expected_sha:
        raise ValueError("weight SHA-256 does not match metadata")
    return {**raw, "_path": weight, "_metadata_path": metadata_path, "_verified_sha256": actual_sha}


def entries() -> tuple[dict[str, dict], list[dict]]:
    root = registry_root()
    if not root.is_dir() or root.is_symlink():
        return {}, []
    loaded: dict[str, dict] = {}
    errors = []
    for metadata_path in sorted(root.glob("*.json")):
        try:
            entry = _load_file(metadata_path)
            if entry["id"] in loaded:
                raise ValueError("duplicate registry id")
            loaded[entry["id"]] = entry
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append({"metadata": metadata_path.name, "reason": str(exc)[:240]})
    return loaded, errors


def public_catalog() -> dict:
    loaded, errors = entries()
    public = []
    for entry in loaded.values():
        public.append({key: entry[key] for key in (
            "id", "label", "kind", "model_family", "default_strength",
            "validated_strength_range", "compatible_models", "compatible_modes",
            "approval_status", "version", "weight_sha256",
        )})
    return {"registry_version": "character-lora-v1", "loras": public, "invalid_entries": errors}


def resolve(selection, *, model: str, mode: str, kind: str) -> tuple[dict | None, dict | None]:
    if selection is None:
        return None, None
    if not isinstance(selection, dict) or set(selection) - {"id", "strength"}:
        raise ValueError(f"{kind}_lora accepts only id and strength")
    identity = selection.get("id")
    if not isinstance(identity, str) or not ID_RE.fullmatch(identity):
        raise ValueError(f"Invalid {kind} LoRA registry id")
    loaded, _ = entries()
    entry = loaded.get(identity)
    if entry is None or entry["kind"] != kind:
        raise ValueError(f"{kind.capitalize()} LoRA is not installed and approved")
    if model not in entry["compatible_models"] or mode not in entry["compatible_modes"]:
        raise ValueError(f"{kind.capitalize()} LoRA is incompatible with the selected model or mode")
    strength = selection.get("strength", entry["default_strength"])
    low, high = entry["validated_strength_range"]["min"], entry["validated_strength_range"]["max"]
    if type(strength) not in (int, float) or not math.isfinite(strength) or not low <= strength <= high:
        raise ValueError(f"{kind.capitalize()} LoRA strength must be within its validated range {low}..{high}")
    public = {"id": identity, "kind": kind, "strength": float(strength), "version": entry["version"],
              "weight_sha256": entry["weight_sha256"]}
    private = {**public, "path": str(entry["_path"]), "trigger_token": entry["trigger_token"]}
    return public, private


def inject_triggers(prompt: str, selections: list[dict | None]) -> str:
    tokens = [item["trigger_token"] for item in selections if item]
    missing = [token for token in tokens if token not in prompt.split()]
    return " ".join([*missing, prompt]).strip()
