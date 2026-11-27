"""Validate the frozen ledger and compare new cached evaluations with archived outputs."""
import csv
from .common import *
from .data import load_cohorts
from .models import registered_assets

def verify_baseline(full=False):
    lock=read(M/"freeze_lock.json")
    for record in lock["files"]:
        verified(WORK/record["path"],record["sha256"])
    inventory=ROOT/"archive/phase0_files.csv"
    with inventory.open(encoding="utf-8",newline="") as stream:
        files={r["path_relative_to_workspace"]:r for r in csv.DictReader(stream)}
    if full:
        selected=set(files)
    else:
        selected=set()
        for source in read(M/"legacy_result_mapping.json").values():
            for item in source["sources"]:
                selected.add(item["file"])
                folder=(WORK/item["file"]).parent
                selected.update(name(p) for p in folder.glob("pair_*.json"))
                selected.update(name(p) for p in folder.glob("registration.json"))
        with (M/"trial_roles.csv").open(encoding="utf-8-sig",newline="") as stream:
            selected.update(r["source"] for r in csv.DictReader(stream))
    for file in sorted(selected):
        verified(WORK/file,files[file]["sha256"])
    assets=registered_assets()
    return {"archive_files":len(files),"archive_bytes":sum(int(r["bytes"]) for r in files.values()),
            "archived_files_rehashed":len(selected),"mode":"full" if full else "core","sealed_inputs_and_outputs":len(lock["files"]),
            "model_assets":len(assets),"cohort_coverage":{name: cohort.coverage() for name,cohort in load_cohorts().items()}}

def verify_runs():
    rows={}
    for stage,count,pattern in (("v68",22,"pair_*.json"),("v67",12,"person_*_summary.json"),("v51",0,None),("v58",0,None),("v74",0,None)):
        folder=ROOT/"results/cached_runs"/stage
        paths=sorted(folder.glob("*/provenance.json"))
        check(bool(paths),f"Missing completed {stage} rerun")
        receipt=paths[-1]
        run=receipt.with_name("result.json")
        reference=one(f"*/{stage}/result.json")
        record=read(receipt)
        verified(run,record["new_result_sha256"])
        verified(reference,record["original_result_sha256"])
        check(read(run)==read(reference),f"Archived and rerun {stage} result values differ")
        if pattern:
            records=list(run.parent.glob(pattern))
            check(len(records)==count and {p.name for p in records}=={p.name for p in reference.parent.glob(pattern)},"Unit file coverage")
            check(all(read(p)==read(reference.with_name(p.name)) for p in records),"Participant/pair output mismatch")
        rows[stage]={"rerun":name(run),"reference":name(reference),"equal_all_result_fields":True,"unit_files_compared":count}
    v51=read(WORK/rows["v51"]["rerun"])
    v58=read(WORK/rows["v58"]["rerun"])
    v74=read(WORK/rows["v74"]["rerun"])
    boundary={}
    for cohort in ("openbmi","stieger"):
        result=v51["cohorts"][cohort]
        recovery=v58["cohorts"][cohort]
        controls=recovery["checks"]
        clear=v74["checks"][cohort]["checks"]
        passed=(result["passed"] and result["shared_package_identical"] and result["shared_prediction_max_drift"]==0 and
                result["local_probability_mean_abs_change_on_history_swap"]>0 and
                recovery["passed"] and controls["shared_prediction_max_change"]==0 and
                all(controls[k] for k in ("background_package_identical","active_head_survived_interruption","restart_recovered_last_commit","duplicate_is_idempotent","logs_and_simulated_sync_have_no_history_canary","positive_control_detected","outbound_socket_control_blocked"))
                and all(clear.values()) and clear["clear_removed_reference_local_head"])
        check(passed,f"{cohort} offline isolation acceptance failed")
        boundary[cohort]={"status":"Isolation passed","shared_prediction_max_drift":result["shared_prediction_max_drift"],
                          "local_probability_MAE_after_history_swap":result["local_probability_mean_abs_change_on_history_swap"]}
    return {"comparisons":rows,"K6":boundary,"scope":"downstream fixed configuration and tested offline reference paths"}

def audit(full=False):
    out={"baseline":verify_baseline(full),"cached_runs":verify_runs()}
    write_json(ROOT/"results/audit.json",out)
    return out
