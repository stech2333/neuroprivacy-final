"""Verify the raw-data reruns and index evidence used by formal acceptance."""

from .common import ROOT, check, name, one, read, sha, verified, write_json

RAW = ROOT / "results/raw_reproduction"
RUN_FOLDERS = {
    "v47": RAW / "dreyer/v47",
    "v46_fit": RAW / "openbmi/evaluation/v46_fit",
    "v48": RAW / "openbmi/evaluation/v48",
    "v56": RAW / "openbmi/evaluation/v56",
    "v61": RAW / "stieger/evaluation/v61",
    "v65": RAW / "stieger/evaluation/v65",
    "v68": RAW / "stieger/evaluation/v68",
}


def numeric_differences(reference, rerun, field=""):
    check(type(reference) is type(rerun), f"Different rerun field type: {field}")
    if isinstance(reference, dict):
        check(reference.keys() == rerun.keys(), f"Different rerun fields: {field}")
        for key, value in reference.items():
            yield from numeric_differences(value, rerun[key], f"{field}/{key}")
    elif isinstance(reference, list):
        check(len(reference) == len(rerun), f"Different rerun field length: {field}")
        for i, value in enumerate(reference):
            yield from numeric_differences(value, rerun[i], f"{field}/{i}")
    elif reference != rerun:
        check(type(reference) in (int, float), f"Different nonnumeric rerun value: {field}")
        yield {"field": field, "historical": reference, "rerun": rerun, "delta": rerun-reference}


def file_receipt(path):
    return {"path": name(path), "sha256": sha(path)}


def verify_raw_results():
    waves = {cohort: RAW / cohort / "complete.json" for cohort in ("openbmi","stieger","netbci")}
    openbmi = read(waves["openbmi"])
    register = one("run_v11*/registration.json")
    verified(register, openbmi["registry_sha256"])
    expected = read(register)["windows"]
    rows = {row["window"]: row for row in openbmi["panel_receipts"]}
    check(len(rows) == len(openbmi["panel_receipts"]) == len(expected) == 96, "OpenBMI panel coverage")
    for key, row in rows.items():
        check(row["original"] == expected[key]["wave_sha256"], "OpenBMI raw source mapping")
        verified(waves["openbmi"].with_name(key+".npz"),row["new_sha256"])
    stieger = read(waves["stieger"])
    check(stieger["sessions"] == len({r["panel"] for r in stieger["panels"]}) == 124, "Stieger panel coverage")
    for row in stieger["panels"]:
        receipt = verified(waves["stieger"].with_name(row["receipt"]),row["receipt_sha256"])
        verified(waves["stieger"].with_name(row["panel"]),read(receipt)["new_panel_sha256"])
    net = read(waves["netbci"])
    check(net["run_six_panels"] == 36 and net["history_people"] == 12 and net["background_people"] == 7
          and len(net["arrays_exact"]) == 55,"NETBCI panel coverage")
    for key, item in net["arrays_exact"].items():
        verified(waves["netbci"].with_name(key),item["new_sha256"])
    matches = {}
    for stage, folder in RUN_FOLDERS.items():
        reference = one(f"*/{stage}/result.json")
        regenerated = folder/"result.json"
        original_pairs = sorted(reference.parent.glob("pair_*.json"))
        actual_pairs = sorted(folder.glob("pair_*.json"))
        check([p.name for p in original_pairs] == [p.name for p in actual_pairs], f"{stage} paired coverage")
        paired = [(read(a),read(b)) for a,b in zip(original_pairs,actual_pairs,strict=True)]
        differences = list(numeric_differences(read(reference),read(regenerated)))
        is_exact = sum(a==b for a,b in paired)
        if stage in ("v47","v61","v65","v68"):
            check(not differences and is_exact == len(paired),f"{stage} exact raw reproduction")
        else:
            for a,b in paired:
                check(a.get("signature")==b.get("signature"), f"{stage} changed historical runner signature")
        if stage.startswith("v6"):
            provenance = read(folder/"provenance.json")
            verified(waves["stieger"],provenance["raw_panels_sha256"])
            verified(reference,provenance["archived_result_sha256"])
        if stage in ("v47","v46_fit"):
            if stage=="v46_fit":
                check(read(regenerated)["utility_gate"]==read(reference)["utility_gate"],f"{stage} task gate changed")
            comparison=read(folder/"comparison.json")
            verified(regenerated,comparison["result_sha256"])
            check(comparison["reference"]==comparison["rerun"], f"{stage} primary concordance changed")
        matches[stage]={"historical":file_receipt(reference),"rerun":file_receipt(regenerated),
                        "pairs":len(actual_pairs),"exact_pair_receipts":is_exact,
                        "paired_result_files":[file_receipt(p) for p in actual_pairs],
                        "changed_numeric_fields":len(differences),
                        "largest_absolute_display_change":max((abs(x["delta"]) for x in differences),default=0),
                        "largest_change":max(differences,key=lambda row:abs(row["delta"]),default=None)}
    v46=read(RUN_FOLDERS["v46_fit"]/"registration.json")
    verified(waves["openbmi"],v46["raw_reproduction_sha256"])
    net_result=RAW/"netbci/evaluation/v67_aggregate.json"
    net_receipt=read(net_result.with_name("provenance.json"))
    verified(waves["netbci"],net_receipt["raw_panels_sha256"])
    verified(net_result,net_receipt["rebuilt_result_sha256"])
    net_old=verified(one("*/v67/result.json"),net_receipt["archived_result_sha256"])
    units=list(net_result.parent.glob("person_*_summary.json"))
    check(len(units)==12 and read(net_result)==read(net_old)
          and all(read(p)==read(net_old.with_name(p.name)) for p in units),"V67 exact raw reproduction")
    matches["v67"]={"historical":file_receipt(net_old),"rerun":file_receipt(net_result),
                    "exact_participant_receipts":len(units),"participant_result_files":[file_receipt(p) for p in sorted(units)]}
    fixed = one("*/v29b_mia/v29b_mia.json")
    repeat = one("*/openbmi/v36_risk_audit.json")
    original = read(fixed)["results"]["negative_log_likelihood"]
    repeated = read(repeat)["V36_A1_original_fixed_groups"]
    check(original["auc_member_versus_nonmember"] == repeated["old_groups_auc"]
          and original["auc_ci_95"] == repeated["auc_ci_95"], "V29b/V36 archived fixed-model ROC-AUC")
    fixed_evidence = {"fixed_evaluation":file_receipt(fixed),"existing_cpu_replay":file_receipt(repeat),
                      "roc_auc":repeated["old_groups_auc"],"bootstrap_ci95":repeated["auc_ci_95"],
                      "group_sizes":repeated["old_groups"],
                      "scope":"historical fixed-model negative log likelihood on the reused H40 windows"}
    result={"mode":"raw data reruns and archived comparisons",
            "panels":{cohort:file_receipt(path) for cohort,path in waves.items()},"comparisons":matches,
            "fixed_model_ancillary":fixed_evidence}
    write_json(ROOT/"results/raw_reproduction_audit.json",result)
    return result


if __name__=="__main__":
    for stage, item in verify_raw_results()["comparisons"].items():
        print(stage,item.get("exact_pair_receipts",item.get("exact_participant_receipts")),
              item.get("pairs"),item.get("changed_numeric_fields",0))
