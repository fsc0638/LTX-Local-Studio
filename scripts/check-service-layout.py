"""Launch/build preflight. No data is changed by this script."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from service_layout import check_private_layout

if os.environ.get("LTX_USER_AUTH_ENABLED", "1") != "0":
    try:
        check_private_layout(root, os.environ.get("LTX_OUTPUT_DIR"), os.environ.get("LTX_UPLOAD_DIR"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
