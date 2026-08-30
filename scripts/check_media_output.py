"""Technical validation for registered image/text adapters, independent of model."""
import json
from pathlib import Path
import sys


def check(path, kind, expected):
    path = Path(path)
    report = {"version": "media-technical-v1", "passed": False, "errors": [], "warnings": [],
              "human_review_required": True, "visual_review_required": kind != "text", "metrics": {}}
    measured = {"verified": False, "measurement": "full_decode"}
    try:
        if kind == "image":
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = 16_000_000
            with Image.open(path) as picture:
                if picture.format != "PNG" or picture.width * picture.height > 16_000_000 or getattr(picture, "n_frames", 1) != 1:
                    raise ValueError("Image output must be a single PNG, maximum 16 megapixels")
                picture.load()
                for dimension in ("width", "height"):
                    if expected.get(dimension) is not None and getattr(picture, dimension) != expected[dimension]:
                        raise ValueError("Image dimensions do not match requested values")
                measured.update(width=picture.width, height=picture.height, format="png")
        elif kind == "text":
            if path.stat().st_size > 1024**2:
                raise ValueError("Text output exceeds 1 MiB")
            value = path.read_text(encoding="utf-8")
            if not value.strip() or "\x00" in value:
                raise ValueError("Output must be non-empty UTF-8 text")
            measured.update(characters=len(value), encoding="utf-8")
        else:
            raise ValueError("Unsupported output type")
        report["passed"] = measured["verified"] = True
    except Exception as exc:
        report["errors"].append("invalid_media_output")
        report["detail"] = str(exc)[:300]
    return {"quality_control": report, "measured_media": measured}


if __name__ == "__main__":
    print(json.dumps(check(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))))
