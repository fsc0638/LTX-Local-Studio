# Trusted local model adapters / 本機模型轉接器

Only the host administrator installs adapters. An adapter is privileged Python code,
not a sandbox: review its source, licenses and dependencies before enabling it.
No HTTP caller may submit executable code, model paths, download URLs or commands.

Create a module such as `local_adapters/my_image_model.py` exporting `ADAPTER`:

```python
from model_registry import MediaAdapter

def command(payload, output, context):
    # This example requires an ACTUAL installed runner and weights. It is not a model.
    # Use an argv list (never shell=True); keep the Python venv/model paths host-side.
    return ["/absolute/model-venv/bin/python", "/absolute/model/generate.py",
            "--prompt", payload["prompt"], "--width", str(payload["parameters"]["width"]),
            "--height", str(payload["parameters"]["height"]), "--output", str(output)]

ADAPTER = MediaAdapter(
    id="my-image-model", label="My installed image model", media_type="image",
    command=command, requires_cuda=True,
    parameters={
        "width": {"type": "integer", "default": 512, "minimum": 64, "maximum": 1536},
        "height": {"type": "integer", "default": 512, "minimum": 64, "maximum": 1536},
    },
)
```

This is an integration template, not a runnable generator. Adapt arguments to the real
model's CLI, install its weights and venv on the host, test locally, then set:

```dotenv
LTX_MODEL_ADAPTERS=local_adapters.my_image_model
```

Restart the backend. The frontend catalog discovers the new model on reload without
changes to login, project links or the API route. Only enabled modules are imported;
files merely copied into this directory are not automatically executed.

- `media_type`: `video` → MP4, `image` → single PNG (≤16MP), `text` → nonempty UTF-8 TXT (≤1MiB).
- `command(payload, output, context)` returns argv; write exactly to `output`, no web public files.
- `context` includes `root`, `python` (existing LTX venv), `launcher`; another model may use its own venv.
- Params support integer/number/string/boolean, default, required, enum, min/max, maxLength, title/description. Up to24 fields; no arbitrary object or shell params.
- `modes` defaults to `("generate",)`. `accepts_image=True` enables uploaded image selection and worker ownership checks; `i2v` requires an image ID.
- A validated reference image's private path is supplied in `LTX_IMAGE`; never trust an arbitrary user path.
- Video adapters must resolve `width`, `height`, `frames`, `fps` from parameter defaults/input; must remain within worker resource limits and produce matching metadata. `audio` defaults false.
- Registry `available` indicates CUDA compatibility, not a successful weight load, free-memory guarantee or artistic validation. Smoke-test each real adapter before offering it to users.
- Models share the single worker execution slot and deadline/cancel/technical-QC system. No hot-swapping an active job.
- Generate progress text is logged privately. Non-LTX progress remains phase-based; arbitrary model-specific progress parsers are not installed automatically.
- Keep model weights outside Git. Don't edit issued model IDs/profile defaults in a way that breaks idempotent replays; register a new versioned ID.
- SMTP and worker API credentials are removed from the generator environment. This is defense in depth, **not** an OS sandbox; code running as the host user can access that user's files.

`tests/fixtures/media_generator.py` is explicitly a CPU test fixture and is never registered in production.
