"""Private, recoverable media removal. No user-supplied paths reach this module."""
import json
import os
from pathlib import Path
import stat
import tempfile
import time


def regular_file(path):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("Refusing symlinked media paths")
    try:
        info = path.stat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Refusing non-regular media files")
    return True


class MediaArchive:
    def __init__(self, directory, entries):
        self.directory, self.entries = directory, entries

    def remove_sources(self):
        # Archives are linked and journaled BEFORE removing any original name.
        # Refuse to remove a replacement that appeared after archive preparation.
        for source, destination in self.entries:
            if not regular_file(source):
                continue
            if not os.path.samefile(source, destination):
                raise ValueError("Media changed during deletion; archive retained")
            source.unlink()


def prepare_archive(paths, trash_root, record):
    trash_root = Path(trash_root).absolute()
    if any(parent.is_symlink() for parent in (trash_root, *trash_root.parents)):
        raise ValueError("Refusing symlinked trash directory")
    sources = list(dict.fromkeys(Path(p).absolute() for p in paths if regular_file(p)))
    trash_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if trash_root.stat().st_uid != os.getuid():
        raise ValueError("Trash must belong to the service user")
    trash_root.chmod(0o700)
    device = trash_root.stat().st_dev
    if any(p.stat().st_dev != device for p in sources):
        raise ValueError("Recoverable deletion requires media and trash on the same filesystem")
    directory = Path(tempfile.mkdtemp(prefix="media-", dir=trash_root))
    entries = [(p, directory / f"{i:04d}-{p.name}") for i, p in enumerate(sources)]
    manifest = {"created_at": time.time(), "record": record,
                "files": [{"source": str(a), "archive": b.name, "bytes": a.stat().st_size} for a, b in entries]}
    with (directory / "manifest.json").open("x") as handle:
        os.chmod(handle.name, 0o600)
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    for source, destination in entries:
        # Exclusive creation, including on crashes/retries; never overwrite.
        os.link(source, destination, follow_symlinks=False)
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return MediaArchive(directory, entries)
