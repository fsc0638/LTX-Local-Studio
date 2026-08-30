"""Move legacy media outside public/ without deleting or overwriting any file.

Default is a dry run. Stop the API/UI before --apply; paths remain recoverable
using the generated journal. Never expose the old directories after restoring.
"""
import argparse
import json
from pathlib import Path
import time


def plan(root):
    root = Path(root).resolve()
    moves = []
    for source, destination in ((root / "public/generated", root / "data/worker/legacy-outputs"),
                                (root / "public/media", root / "data/worker/legacy-media"),
                                (root / "dist/client/generated", root / "data/worker/legacy-build-generated"),
                                (root / "dist/client/media", root / "data/worker/legacy-build-media")):
        if not source.exists():
            continue
        if source.is_symlink() or destination.is_symlink():
            raise ValueError("Refusing symlinked media directories")
        for path in sorted(source.iterdir()):
            if path.name == ".gitkeep":
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"Review unexpected non-regular file first: {path}")
            target = destination / path.name
            if target.exists() or target.is_symlink():
                raise ValueError(f"Destination exists; nothing will be overwritten: {target}")
            moves.append((path, target))
    return moves


def migrate(root, apply=False):
    moves = plan(root)
    if not apply or not moves:
        return [{"from": str(a), "to": str(b)} for a, b in moves]
    journal_dir = Path(root) / "data/worker/migrations"
    journal_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    journal = journal_dir / f"media-{time.time_ns()}.json"
    report = {"planned": [{"from": str(a), "to": str(b)} for a, b in moves], "completed": []}
    journal.write_text(json.dumps(report, indent=2))
    journal.chmod(0o600)
    for source, destination in moves:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Exclusive hard-link + unlink never overwrites an existing destination,
        # including one created after the dry-run. Both names remain recoverable
        # if interrupted between these two operations.
        destination.hardlink_to(source)
        source.unlink()
        report["completed"].append(str(destination))
        journal.write_text(json.dumps(report, indent=2))
    return {"moved": len(moves), "journal": str(journal), "deleted": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply after stopping API and UI; default is dry-run")
    arguments = parser.parse_args()
    print(json.dumps(migrate(Path(__file__).resolve().parents[1], arguments.apply), indent=2))
