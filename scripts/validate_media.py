"""Validate untrusted media in a bounded subprocess before publishing it."""
import json
import sys
import warnings
from pathlib import Path

from PIL import Image
import av

Image.MAX_IMAGE_PIXELS = 16_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)
path = Path(sys.argv[1])
kind = sys.argv[2]
if kind == "video":
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        if stream.width * stream.height > 16_000_000:
            raise ValueError("Video dimensions too large")
        frame = next(container.decode(video=0))
        result = {"width": frame.width, "height": frame.height}
else:
    with Image.open(path) as picture:
        if picture.format not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError("Unsupported image format")
        result = {"width": picture.width, "height": picture.height}
        picture.verify()
print(json.dumps(result))
