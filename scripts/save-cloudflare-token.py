#!/usr/bin/env python3
"""Interactive secret setup: no CLI secret argument, echo, or overwrite."""
import getpass
import os
from pathlib import Path
import re


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    parent = root / 'data/worker'
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = parent / 'cloudflare-api-token'
    if path.exists() or path.is_symlink():
        raise SystemExit('A token file already exists; no secret was overwritten.')
    token = getpass.getpass('Paste dedicated Cloudflare API Token (hidden): ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}', token):
        raise SystemExit('Invalid token shape; nothing saved.')
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as handle:
        handle.write(token + '\n')
    del token
    print('Dedicated token saved privately. No Cloudflare settings were changed.')
