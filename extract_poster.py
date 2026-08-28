#!/usr/bin/env python3
"""Extract the first decoded video frame as a JPEG poster."""

from pathlib import Path
import sys

import av


source = Path(sys.argv[1]).resolve()
destination = Path(sys.argv[2]).resolve()
with av.open(str(source)) as container:
    for frame in container.decode(video=0):
        frame.to_image().save(destination, format="JPEG", quality=90)
        break

if not destination.exists():
    raise SystemExit("No video frame was decoded")
