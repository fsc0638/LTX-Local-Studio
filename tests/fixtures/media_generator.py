"""TEST FIXTURE ONLY: deterministic files, not an installed AI model."""
import sys
from pathlib import Path
from PIL import Image

kind, output = sys.argv[1:3]
if kind == "image":
    Image.new("RGB", (64, 48), (225, 85, 120)).save(output, "PNG")
elif kind == "text":
    Path(output).write_text("測試文字 <script>not executable</script> 日本語", encoding="utf-8")
else:
    Path(output).write_bytes(b"invalid fixture")
