"""Seal the initial evidence delivery, without replacing an existing seal."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    expected=(ROOT/"manifests/data_sources.json",ROOT/"archive/phase0_files.csv",ROOT/"archive/late_runs.json",
              ROOT/"archive/Final Protocol 1.0.txt",ROOT/"archive/protocol_classification.csv")
    if not all(p.is_file() for p in expected):
        raise FileNotFoundError("Missing freeze deliverable")
    files=set(expected)
    files.update((ROOT/"configs").glob("*"))
    files.update((ROOT/"manifests").glob("*.csv"))
    files.update(p for p in (ROOT/"manifests").glob("*.json") if p.name!="freeze_lock.json")
    for stage in ("v51","v58","v68","v67","v74"):
        receipts=sorted((ROOT/"results/cached_runs"/stage).glob("*/provenance.json"))
        receipt=receipts[-1]
        files.update([receipt,receipt.with_name("result.json")])
    controls=sorted((ROOT/"results/stieger_C8_controls").glob("*/result.json"))[-1]
    files.update([controls,controls.with_name("participant_metrics.json")])
    rows=[]
    for path in sorted(files):
        with path.open("rb") as stream:
            rows.append({"path":path.relative_to(ROOT.parent).as_posix(),"sha256":hashlib.file_digest(stream,"sha256").hexdigest()})
    output=ROOT/"manifests/freeze_lock.json"
    with output.open("x",encoding="utf-8") as stream:
        json.dump({"protocol":"1.0","evidence_cutoff":"2026-11-26","scope":"initial local execution, previously explored cohorts","files":rows},stream,indent=2,ensure_ascii=False)
    print("Sealed",len(rows),"files")

if __name__=="__main__":
    main()
