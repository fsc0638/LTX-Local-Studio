"""Create a worker credential once. Never print it or overwrite an existing key."""
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1] / "data/worker"
root.mkdir(parents=True, exist_ok=True, mode=0o700)
path = root / "api-key"
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit("Worker credential already exists; unchanged.")
with os.fdopen(fd, "w", encoding="utf-8") as destination:
    destination.write(secrets.token_urlsafe(48) + "\n")
print("Worker credential created in data/worker/api-key (owner-only); value not displayed.")
