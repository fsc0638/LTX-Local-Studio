"""Qwen-Image-Edit-2509 and Z-Image-Turbo as media adapters (D1).

Both run in the imagegen service; the adapter's argv is the loopback client in ltx-api's own
interpreter. Parameters are checked by model_registry before a job is admitted: ids, integers
and enums only. No path or URL is accepted from a request - references are asset ids that
ltx-api resolves to private paths and hands to the client through the environment.

Enable with LTX_MODEL_ADAPTERS=local_adapters.imagegen.
"""
from model_registry import MediaAdapter

ASSET_ID = {"type": "string", "maxLength": 32,
            "description": "A second or third reference image, as an uploaded asset id."}
COMMON = {
    "steps": {"type": "integer", "default": 8, "minimum": 1, "maximum": 50,
              "description": "Denoising steps. 8 with the Lightning LoRA; more buys little."},
    "seed": {"type": "integer", "default": 42, "minimum": 0, "maximum": 2**31 - 1},
    "size": {"type": "string", "default": "1024x1024",
             "enum": ["1024x1024", "1280x720", "720x1280", "1536x864", "864x1536"]},
}


def command(payload, output, context):
    parameters = payload.get("parameters", {})
    argv = [str(context["python"]), str(context["root"] / "services/imagegen/client.py"),
            "--model", payload["model"], "--prompt", payload["prompt"], "--output", str(output),
            "--steps", str(parameters.get("steps", 8)), "--seed", str(payload.get("seed", 42)),
            "--size", parameters.get("size", "1024x1024"),
            "--lightning", "1" if parameters.get("lightning", True) else "0"]
    return argv


QWEN = MediaAdapter(
    id="qwen-image-edit-2509", label="Qwen-Image-Edit 2509", media_type="image", command=command,
    modes=("edit",), accepts_image=True,
    description="Edit or restyle a reference image. Needs one reference (image_id); up to two more via reference_2/3.",
    parameters={**COMMON,
                "lightning": {"type": "boolean", "default": True,
                              "description": "Use the 8-step Lightning LoRA (fast). Off means the full schedule."},
                "reference_2": ASSET_ID, "reference_3": ASSET_ID},
)

ZIMAGE = MediaAdapter(
    id="z-image-turbo", label="Z-Image Turbo", media_type="image", command=command,
    modes=("generate",), accepts_image=False,
    description="Text to image, distilled: fast and needs no reference.",
    parameters=COMMON,
)

# model_registry.load_installed() registers one ADAPTER per module; this module ships two, so it
# exposes the first as ADAPTER and the registry helper below registers both.
ADAPTER = QWEN
EXTRA_ADAPTERS = (ZIMAGE,)
