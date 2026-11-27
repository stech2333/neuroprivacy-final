import csv
import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
OLD = WORK / "neuroprivacy_next_20261122"
M = ROOT / "manifests"

def one(pattern):
    paths = list(OLD.glob(pattern))
    if len(paths) != 1:
        raise ValueError(f"Expected exactly one match for {pattern}: {len(paths)}")
    return paths[0]

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def check(condition, message):
    if not condition:
        raise ValueError(message)

def verified(path, expected):
    check(sha(path) == expected, f"Historical SHA-256 mismatch: {path}")
    return path

def name(path):
    return path.relative_to(WORK).as_posix() if path.is_relative_to(WORK) else path.as_posix()

def write_json(path, obj):
    text = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        stream.write(text)
    Path(stream.name).replace(path)

def table(path, fields, rows):
    with NamedTemporaryFile(mode="w", encoding="utf-8-sig", newline="", dir=path.parent, delete=False) as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)
    Path(stream.name).replace(path)
