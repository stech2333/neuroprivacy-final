"""Re-run the existing utility and offline boundary routines into a fresh directory."""
import argparse
import hashlib
import importlib
import json
import os
import shutil
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT.parent / "neuroprivacy_next_20261122"
STAGES = {
    "v68": ("v68_stieger_doses", "run_v67_v69_20261126"),
    "v67": ("v67_netbci_repeat", "run_v67_v69_20261126"),
    "v61": ("v61_stieger_records", "run_v59_v62_20261126"),
    "v65": ("v65_stieger_blocks", "run_v63_v66_20261126"),
    "v58": ("v58_recovery", "run_v54_v58_20261126"),
    "v74": ("v74_v76_admission", "run_v71_v76_launch_20261126"),
    "v51": ("v51_structured_boundary", "run_v44_v53_20261126"),
}

def main(stage):
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(LEGACY))
    module_name, archived = STAGES[stage]
    source = LEGACY / (module_name + ".py")
    runner_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    prior = LEGACY / archived / stage
    if (prior / "registration.json").exists():
        reg = json.loads((prior / "registration.json").read_bytes())
        if runner_hash != reg["runner_sha256"]:
            raise ValueError("Runner differs from registered source")
    dest = ROOT / "results" / "cached_runs" / stage / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest.mkdir(parents=True)
    module = importlib.import_module(module_name)
    if stage == "v74":
        result = module.release_checks(dest)
    elif stage == "v51":
        # The historical verifier expects its V49 descriptors in sibling folders.
        replay_dir = dest / "v51"
        replay_dir.mkdir()
        for cohort in ("stieger", "openbmi"):
            source_dir = prior.parent / f"v49_{cohort}"
            selected = json.loads((source_dir / "result.json").read_bytes())
            candidate = selected["selected_in_development"]
            sample = selected["setup"][0]
            filename = f"{sample['sample']}_{candidate}_curvature.npz"
            target_dir = dest / source_dir.name
            target_dir.mkdir()
            shutil.copyfile(source_dir / filename, target_dir / filename)
        result, _ = module.run(replay_dir, lambda detail: print(detail, flush=True))
    else:
        result, _ = module.run(dest, lambda detail: print(detail, flush=True))
    saved = dest / "result.json"
    saved.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    record = {"stage": stage, "runner_sha256": runner_hash, "python": sys.executable,
              "original_result_sha256": hashlib.sha256((prior/"result.json").read_bytes()).hexdigest(),
              "new_result_sha256": hashlib.sha256(saved.read_bytes()).hexdigest(),
              "scope": "frozen derived panels or offline reference harness"}
    (dest / "provenance.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(dest)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=STAGES)
    main(parser.parse_args().stage)
