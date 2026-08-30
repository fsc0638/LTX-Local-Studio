"""Trusted host-side adapters. HTTP callers select IDs, never commands or paths.

Register installed adapters via LTX_MODEL_ADAPTERS=local_adapters.module_name.
Each adapter writes exactly one private output: MP4, PNG, or UTF-8 TXT.
"""
from dataclasses import dataclass, field
import importlib
import math
import os
import re
from typing import Callable


FORMATS = {"video": ("mp4", "video/mp4"), "image": ("png", "image/png"), "text": ("txt", "text/plain; charset=utf-8")}


@dataclass(frozen=True)
class MediaAdapter:
    id: str
    label: str
    media_type: str
    command: Callable
    parameters: dict = field(default_factory=dict)
    modes: tuple = ("generate",)
    requires_cuda: bool = True
    description: str = ""
    accepts_image: bool = False

    @property
    def extension(self):
        return FORMATS[self.media_type][0]

    @property
    def content_type(self):
        return FORMATS[self.media_type][1]

    def describe(self, runtime):
        return {"id": self.id, "label": self.label, "media_type": self.media_type,
                "modes": list(self.modes), "parameters": self.parameters, "description": self.description,
                "available": not self.requires_cuda or bool(runtime.get("cuda_available")),
                "accepts_image": self.accepts_image,
                "installed": True, "adapter_version": "media-adapter-v1"}

    def normalize(self, raw):
        # This branch is for non-LTX adapters. LTX keeps its existing v1 fields.
        allowed = {"model", "prompt", "mode", "parameters", "image_id", "timeout_seconds"}
        if set(raw) - allowed:
            raise ValueError("Use the selected adapter's parameters object; unsupported top-level field")
        prompt = raw.get("prompt")
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
            raise ValueError("prompt must contain 1–4000 characters")
        mode = raw.get("mode", self.modes[0])
        if mode not in self.modes:
            raise ValueError("Unsupported mode for selected model")
        parameters = raw.get("parameters", {})
        if not isinstance(parameters, dict) or set(parameters) - set(self.parameters):
            raise ValueError("Unsupported model parameter")
        values = {}
        for name, rule in self.parameters.items():
            value = parameters.get(name, rule.get("default"))
            if value is None and not rule.get("required"):
                continue
            valid_type = {"integer": type(value) is int, "number": type(value) in (int, float),
                          "boolean": type(value) is bool, "string": isinstance(value, str)}.get(rule["type"], False)
            if not valid_type:
                raise ValueError(f"Invalid type for parameter {name}")
            if type(value) in (int, float) and (not math.isfinite(value) or value < rule.get("minimum", -1e12) or value > rule.get("maximum", 1e12)):
                raise ValueError(f"Parameter out of range: {name}")
            if isinstance(value, str) and len(value) > rule.get("maxLength", 2000):
                raise ValueError(f"Parameter too long: {name}")
            if "enum" in rule and value not in rule["enum"]:
                raise ValueError(f"Unsupported value for parameter {name}")
            values[name] = value
        timeout = raw.get("timeout_seconds", 3600)
        if type(timeout) is not int or not 30 <= timeout <= 7200:
            raise ValueError("timeout_seconds must be 30–7200")
        image_id = raw.get("image_id")
        if image_id is not None and not self.accepts_image:
            raise ValueError("Selected adapter does not accept reference images")
        if mode == "i2v" and not image_id:
            raise ValueError("image_id is required for i2v")
        if image_id is not None and (not isinstance(image_id, str) or not re.fullmatch(r"[a-f0-9]{32}", image_id)):
            raise ValueError("image_id must be an uploaded asset ID")
        payload = {"model": self.id, "media_type": self.media_type, "mode": mode, "prompt": prompt.strip(),
                   "parameters": values, "timeout_seconds": timeout, "image_id": image_id, "audio": False,
                   "width": values.get("width"), "height": values.get("height"),
                   "frames": values.get("frames"), "fps": values.get("fps"), "seed": values.get("seed", 42), "offload": False}
        if self.media_type == "video":
            if any(type(payload.get(key)) is not int or payload[key] <= 0 for key in ("width", "height", "frames", "fps")):
                raise ValueError("Video adapters must resolve width, height, frames and fps")
            if payload["frames"] > 257 or payload["width"] > 1536 or payload["height"] > 1536 or payload["fps"] > 60:
                raise ValueError("Video adapter exceeds worker resource limits")
            payload["audio"] = values.get("audio", False)
        return payload


def ltx_command(payload, output, context):
    return ["bash", str(context["launcher"]), payload["prompt"], str(output)]


ADAPTERS = {"ltx23-distilled": MediaAdapter("ltx23-distilled", "LTX-2.3 Distilled", "video", ltx_command,
                                           modes=("t2v", "i2v"), accepts_image=True, description="Existing LTX video contract and versioned profiles")}


def register(adapter):
    if not isinstance(adapter, MediaAdapter) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", adapter.id):
        raise ValueError("Invalid model adapter")
    if adapter.id in ADAPTERS or adapter.media_type not in FORMATS or not callable(adapter.command) or len(adapter.parameters) > 24:
        raise ValueError("Duplicate or invalid model adapter")
    if not adapter.modes or any(not isinstance(mode, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,31}", mode) for mode in adapter.modes):
        raise ValueError("Invalid adapter modes")
    for name, rule in adapter.parameters.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name) or rule.get("type") not in {"integer", "number", "string", "boolean"}:
            raise ValueError("Invalid model parameter schema")
    ADAPTERS[adapter.id] = adapter


def load_installed():
    for name in filter(None, (value.strip() for value in os.environ.get("LTX_MODEL_ADAPTERS", "").split(","))):
        if not re.fullmatch(r"local_adapters\.[a-z][a-z0-9_]*", name):
            raise ValueError("Adapters must be trusted local_adapters modules, not paths or URLs")
        register(importlib.import_module(name).ADAPTER)


def get(model_id):
    if not isinstance(model_id, str) or model_id not in ADAPTERS:
        raise ValueError("Model is not installed/registered on this host")
    return ADAPTERS[model_id]


def catalog(runtime):
    return {"adapter_version": "media-adapter-v1", "models": [item.describe(runtime) for item in ADAPTERS.values()],
            "supported_output_types": list(FORMATS), "installation_requires_host_admin": True}
