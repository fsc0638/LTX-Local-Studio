"""Fail closed before an account-enabled API or UI can serve legacy public files."""
from pathlib import Path


def check_private_layout(root, output=None, upload=None):
    root = Path(root).resolve()
    public_roots = (root / "public", root / "dist/client")
    for location in (output, upload):
        if location and any(Path(location).resolve().is_relative_to(public) for public in public_roots):
            raise ValueError("Account mode requires private upload/output directories outside public/ and dist/client/.")
    for public in public_roots:
        for name in ("generated", "media"):
            directory = public / name
            if directory.is_symlink() or (directory.exists() and any(path.name != ".gitkeep" for path in directory.iterdir())):
                raise ValueError("Legacy public media must be secured first. Stop API/UI, then run scripts/secure-media.py --apply and rebuild.")
