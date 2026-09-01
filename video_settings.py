"""Host resource policy, distinct from the model's quality/training envelope."""
import os
import math


def frame_limit(value):
    try:
        frames = int(value)
    except (TypeError, ValueError):
        raise ValueError("LTX_MAX_FRAMES must be an integer") from None
    if not 257 <= frames <= 1201 or (frames - 1) % 8:
        raise ValueError("LTX_MAX_FRAMES must be 8n+1, between 257 and 1201")
    return frames


# 20-second-class clips at 24 FPS. Larger limits are an explicit host-admin
# resource choice, never advertised as a tested memory/quality guarantee.
MAX_FRAMES = frame_limit(os.environ.get("LTX_MAX_FRAMES", "481"))
ASPECT_RATIOS = {
    "9:16": {"width": 576, "height": 1024},
    "16:9": {"width": 1024, "height": 576},
    "1:1": {"width": 512, "height": 512},
    "4:3": {"width": 512, "height": 384},
    "3:4": {"width": 384, "height": 512},
    "3:2": {"width": 768, "height": 512},
}


def image_geometry(width, height):
    """Match orientation-corrected source geometry to the two-stage 64px grid."""
    if type(width) is not int or type(height) is not int or min(width, height) <= 0:
        raise ValueError("Invalid source dimensions")
    common = math.gcd(width, height)
    source_ratio = f"{width // common}:{height // common}"
    preset = ASPECT_RATIOS.get(source_ratio)
    if preset:
        output = preset
    else:
        candidates = [(w, h) for w in range(256, 1537, 64) for h in range(256, 1537, 64)
                      if w * h <= 1024 * 1024]
        w, h = min(candidates, key=lambda pair: (round(abs(math.log(pair[0] * height / (pair[1] * width))), 9),
                                                abs(pair[0] * pair[1] - 512 * 768)))
        output = {"width": w, "height": h}
    return {"source_ratio": source_ratio, "suggested_aspect_ratio": source_ratio if preset else "source",
            "suggested_dimensions": dict(output),
            "ratio_error_percent": round(abs(output["width"] * height / (output["height"] * width) - 1) * 100, 3)}
