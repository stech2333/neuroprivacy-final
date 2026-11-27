"""Index the local Phase 0 tree in place. Original files are opened read-only."""
import csv
import hashlib
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent.parent
ROOTS = ("_feasibility", "models", "neuroprivacy_v3", "neuroprivacy_followup_20261121", "neuroprivacy_next_20261122")

def fingerprint(path):
    before = path.stat()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"File changed while archiving: {path}")
    return before.st_size, digest

def main():
    destination = HERE / "phase0_files.csv"
    if destination.exists():
        raise SystemExit("A frozen inventory already exists.")
    with destination.with_suffix(".partial").open("x", newline="", encoding="utf-8") as stream:
        out = csv.writer(stream)
        out.writerow(["path_relative_to_workspace", "bytes", "sha256"])
        for path in sorted(WORK.glob("*.md")):
            out.writerow([path.name, *fingerprint(path)])
        for root in ROOTS:
            for directory, dirs, files in os.walk(WORK / root):
                dirs[:] = sorted(d for d in dirs if d not in {"__pycache__", ".git"})
                for name in sorted(files):
                    path = Path(directory) / name
                    if path.suffix != ".pyc":
                        out.writerow([path.relative_to(WORK).as_posix(), *fingerprint(path)])
    destination.with_suffix(".partial").rename(destination)

if __name__ == "__main__":
    main()
