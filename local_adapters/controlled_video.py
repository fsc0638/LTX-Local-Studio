"""Official LTX controlled-video lanes.

These adapters expose three distinct production jobs instead of pretending a text prompt is a
pose, camera path, or phoneme track. Uploaded asset ids are resolved by ltx-api and reach the
launchers only through private environment variables. Missing optional checkpoints keep the
model visible but unavailable; nothing is downloaded automatically.
"""
from __future__ import annotations

import os
from pathlib import Path

from model_registry import MediaAdapter, ltx25_paths


ASSET_ID = {"type": "string", "maxLength": 32, "required": True}
VIDEO_ASSET = {**ASSET_ID, "asset_kind": "video"}
AUDIO_ASSET = {**ASSET_ID, "asset_kind": "audio"}
COMMON_VIDEO = {
    "width": {"type": "integer", "default": 768, "minimum": 256, "maximum": 1536},
    "height": {"type": "integer", "default": 512, "minimum": 256, "maximum": 1536},
    "frames": {"type": "integer", "default": 121, "minimum": 9, "maximum": 10800, "step": 8, "step_base": 1},
    "fps": {"type": "integer", "default": 24, "minimum": 8, "maximum": 60},
    "seed": {"type": "integer", "default": 42, "minimum": 0, "maximum": 2**32 - 1},
    # These official pipelines always emit synchronized audio. Reject a false value instead of
    # accepting a request whose artifact would contradict the declared contract.
    "audio": {"type": "boolean", "default": True, "enum": [True]},
}


def _path(name: str, fallback: Path) -> Path:
    return Path(os.environ.get(name, fallback)).expanduser()


def _missing(paths: dict[str, Path]) -> tuple[bool, str]:
    absent = [name for name, path in paths.items() if not path.is_file()]
    return (not absent, "" if not absent else "Missing controlled-video components: " + ", ".join(absent))


def _ltx23_paths() -> dict[str, Path]:
    root = Path(os.environ.get("LTX_REPO_ROOT", ""))
    return {
        "checkpoint": _path("LTX_CHECKPOINT_PATH", root / "models/LTX-2.3/ltx-2.3-22b-distilled-1.1.safetensors"),
        "upsampler": _path("LTX_UPSAMPLER_PATH", root / "models/LTX-2.3/ltx-2.3-spatial-upscaler-x2-1.1.safetensors"),
        "gemma": _path("LTX_GEMMA_ROOT", root / "models/gemma-3-12b") / "config.json",
    }


def control_readiness() -> tuple[bool, str]:
    root = Path(os.environ.get("LTX_REPO_ROOT", ""))
    loras = {
        "performance": _path("LTX_CONTROL_PERFORMANCE_LORA_PATH", root / "models/control/ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors"),
        "pose": _path("LTX_CONTROL_POSE_LORA_PATH", root / "models/control/ltx-2-19b-ic-lora-pose-control.safetensors"),
    }
    ready, reason = _missing({**_ltx23_paths(), **{f"{kind}_control_lora": path for kind, path in loras.items()}})
    return ready, reason


CAMERA_MOVES = ("dolly-in", "dolly-left", "dolly-out", "dolly-right", "jib-down", "jib-up", "static")


def camera_readiness() -> tuple[bool, str]:
    root = Path(os.environ.get("LTX_REPO_ROOT", ""))
    loras = {
        move: _path(f"LTX_CAMERA_{move.replace('-', '_').upper()}_LORA_PATH", root / "models/control" / f"ltx-2-19b-lora-camera-control-{move}.safetensors")
        for move in CAMERA_MOVES
    }
    return _missing({**_ltx23_paths(), **{f"camera_{move}_lora": path for move, path in loras.items()}})


def a2v_readiness() -> tuple[bool, str]:
    paths = ltx25_paths()
    root = Path(os.environ.get("LTX_REPO_ROOT", "")) / "models/LTX-2.5"
    paths["full_transformer"] = _path("LTX25_A2V_TRANSFORMER_PATH", root / "diffusion_models/ltx-2.5-22b-dev-transformer-bf16.safetensors")
    paths["distilled_lora"] = _path("LTX25_DISTILLED_LORA_PATH", root / "loras/ltx-2.5-22b-distilled-lora-450-bf16.safetensors")
    paths.pop("transformer", None)
    return _missing(paths)


def dubit_readiness() -> tuple[bool, str]:
    root = Path(os.environ.get("LTX_REPO_ROOT", ""))
    return _missing({**_ltx23_paths(),
        "dubit_lora": _path("LTX_DUBIT_LORA_PATH", root / "models/control/ltx-2.3-22b-ic-lora-dubit-0.9.safetensors")})


def command(script: str):
    def build(payload, output, context):
        return ["bash", str(context["root"] / "scripts" / script), payload["prompt"], str(output)]
    return build


CONTROL = MediaAdapter(
    id="ltx23-control", label="LTX 2.3 · Performance / Pose Control",
    media_type="video", command=command("run-ltx-control.sh"), modes=("v2v",), accepts_image=True,
    readiness=control_readiness,
    description="Drive motion or camera structure from an uploaded reference video through an installed IC-LoRA.",
    parameters={**COMMON_VIDEO,
                "control_video_id": {**VIDEO_ASSET, "title": "Control video"},
                "control_kind": {"type": "string", "default": "performance", "enum": ["performance", "pose"]},
                "control_strength": {"type": "number", "default": 1.0, "minimum": 0.0, "maximum": 1.0}},
)

CAMERA = MediaAdapter(
    id="ltx23-camera", label="LTX 2.3 · Camera Control",
    media_type="video", command=command("run-ltx-camera.sh"), modes=("t2v", "i2v"), accepts_image=True,
    readiness=camera_readiness,
    description="Apply one official camera-motion LoRA; an optional opening image locks character identity.",
    parameters={**COMMON_VIDEO,
                "camera_move": {"type": "string", "default": "static", "enum": list(CAMERA_MOVES)},
                "camera_strength": {"type": "number", "default": 1.0, "minimum": 0.0, "maximum": 2.0}},
)

A2V = MediaAdapter(
    id="ltx25-a2v", label="LTX 2.5 · Audio-to-Video",
    media_type="video", command=command("run-ltx-a2v.sh"), modes=("a2v",), accepts_image=True,
    readiness=a2v_readiness,
    description="Generate video from a frozen uploaded speech or singing track; optional image fixes the opening identity.",
    parameters={**COMMON_VIDEO, "audio_id": {**AUDIO_ASSET, "title": "Driving audio"},
                "a2v_guidance": {"type": "number", "default": 3.0, "minimum": 1.0, "maximum": 8.0}},
)

DUBIT = MediaAdapter(
    id="ltx23-dubit", label="LTX 2.3 · Dub-It",
    media_type="video", command=command("run-ltx-dubit.sh"), modes=("dubit",), accepts_image=False,
    readiness=dubit_readiness,
    description="Rephrase a reference performance while preserving speaker identity and matching new lip movements.",
    parameters={**COMMON_VIDEO, "reference_video_id": {**VIDEO_ASSET, "title": "Reference performance"},
                "reference_strength": {"type": "number", "default": 1.0, "minimum": 0.0, "maximum": 1.0}},
)

ADAPTER = CONTROL
EXTRA_ADAPTERS = (CAMERA, A2V, DUBIT)
