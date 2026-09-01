"""Validate untrusted media in a bounded subprocess before publishing it."""
import json
import sys
import warnings
from pathlib import Path

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 16_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)
path = Path(sys.argv[1])
kind = sys.argv[2]
if kind == "audio":
    import av

    with av.open(str(path)) as container:
        if len(container.streams.audio) != 1 or container.streams.video:
            raise ValueError("Expected audio-only media with one track")
        stream = container.streams.audio[0]
        if not 8000 <= stream.codec_context.sample_rate <= 192000 or stream.codec_context.channels > 2:
            raise ValueError("Audio must be mono/stereo, 8–192kHz")
        samples = 0
        rate = stream.codec_context.sample_rate
        for frame in container.decode(audio=0):
            samples += frame.samples
            if samples / rate > 600:
                raise ValueError("Audio exceeds 10 minutes")
        if samples == 0:
            raise ValueError("Empty audio")
        result = {"duration_seconds": samples / rate, "sample_rate": rate, "channels": stream.codec_context.channels}
elif kind == "video":
    import av

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
        # Verify bytes before loading/orienting a second time.
        picture.verify()
    with Image.open(path) as picture:
        oriented = ImageOps.exif_transpose(picture)
        result = {"width": oriented.width, "height": oriented.height}
print(json.dumps(result))
