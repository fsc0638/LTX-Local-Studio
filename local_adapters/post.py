"""The post tools (VX) as one media adapter: upscale, clean, interpolate an approved take (D3).

A post job's input is a take that already exists on this host, named by its id; ltx-api resolves
the id to the private file and hands the path to the client through the environment. The output
is a new take of the same shot, which the judge scores like any other. No parameter is a path.

Enable with LTX_MODEL_ADAPTERS=local_adapters.imagegen,local_adapters.post.
"""
from model_registry import MediaAdapter


def command(payload, output, context):
    parameters = payload.get("parameters", {})
    argv = [str(context["python"]), str(context["root"] / "services/post/client.py"),
            "--op", parameters["op"], "--output", str(output),
            "--scale", str(parameters.get("scale", 2)),
            "--target-fps", str(parameters.get("target_fps", 0))]
    return argv


ADAPTER = MediaAdapter(
    id="post-vx", label="Post: upscale / clean / interpolate", media_type="video", command=command,
    modes=("post",), accepts_image=False, gpu_tenant="none", max_dimension=5760, max_frames=100000,
    description="Real-ESRGAN upscale, LaMa clean-up with a painted mask, RIFE interpolation. Input is an existing take.",
    parameters={
        "op": {"type": "string", "enum": ["upscale", "clean", "interpolate"], "required": True},
        "take_id": {"type": "string", "maxLength": 36, "required": True,
                    "description": "The take to process. Its file is resolved on the host."},
        "scale": {"type": "integer", "default": 2, "enum": [2, 4], "description": "Upscale factor."},
        "target_fps": {"type": "integer", "default": 48, "minimum": 2, "maximum": 120},
        "mask_image_id": {"type": "string", "maxLength": 32,
                          "description": "A painted mask, uploaded as an asset: white where to clean."},
        # Filled in by ltx-api from the source take; the technical check compares the output to them.
        "width": {"type": "integer", "minimum": 16, "maximum": 5760},
        "height": {"type": "integer", "minimum": 16, "maximum": 5760},
        "frames": {"type": "integer", "minimum": 1, "maximum": 100000},
        "fps": {"type": "integer", "minimum": 1, "maximum": 120},
        "audio": {"type": "boolean", "default": False},
    },
)
