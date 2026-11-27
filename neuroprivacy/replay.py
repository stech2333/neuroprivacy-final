"""Recompute statistics from already aggregated pair metrics."""
import numpy as np
import yaml
from scipy import stats
from .common import ROOT, WORK, one, read, check, verified, sha, write_json

def load_pairs(stage, ids, reruns):
    if stage in reruns:
        rerun=reruns[stage]
        result=verified(WORK/rerun["rerun"]["path"],rerun["rerun"]["sha256"])
        sealed={WORK/row["path"]:row["sha256"] for row in rerun["paired_result_files"]}
        folder=result.parent
    else:
        folder = one(f"*/{stage}/result.json").parent
        sealed={}
    actual = sorted(folder.glob("pair_*.json"))
    check([p.name for p in actual] == [f"pair_{i:02d}.json" for i in ids], f"{stage} pair coverage")
    if stage in reruns:
        check(set(actual)==set(sealed),f"{stage} verified file coverage")
        for path in actual:
            verified(path,sealed[path])
    return [read(p) for p in actual], read(folder/"result.json")

def holm(raw):
    adjusted = {}
    floor = 0.
    for i, (key,p) in enumerate(sorted(raw.items(),key=lambda kv:kv[1])):
        floor = min(1., max(floor, (len(raw)-i)*p))
        adjusted[key] = floor
    return adjusted

def replay(*, raw=False):
    settings=yaml.safe_load((ROOT/"configs/statistics.yaml").read_text(encoding="utf-8"))
    cfg=yaml.safe_load((ROOT/"configs/protocol.yaml").read_text(encoding="utf-8"))["statistics"]
    level=cfg["historical_ci_level"]
    raw_receipt=ROOT/"results/raw_reproduction_audit.json"
    reruns=read(raw_receipt)["comparisons"] if raw else {}
    def pairs(stage, ids):
        return load_pairs(stage, ids, reruns)

    def component(values, reference, sign=1, boundary=0., direction=1):
        x=np.array(values)
        check(len(x)>=2 and np.isfinite(x).all(),"Pair metric coverage")
        m=float(x.mean())
        se=float(stats.sem(x))
        check(se>0,"Constant contrast requires explicit boundary handling")
        radius=float(stats.t.ppf((1+level)/2,len(x)-1)*se)
        ci=[m-radius,m+radius]
        draws=np.random.default_rng(settings["bootstrap_seed"]).choice(x,(settings["bootstrap_draws"],len(x))).mean(axis=1)
        boot=np.quantile(draws,[(1-level)/2,(1+level)/2])
        if reference is not None:
            historic=np.array(reference["pair_t_ci"])*sign
            check(len(x)==reference["blocks"] and np.allclose(ci,np.sort(historic),atol=1e-12,rtol=0)
                  and abs(m-reference["mean"]*sign)<1e-12,"Source t interval or mean mismatch")
            check(np.allclose(boot,np.sort(np.array(reference["pair_bootstrap_ci"])*sign),atol=1e-12,rtol=0),
                  "Source bootstrap mismatch")
        p=float(stats.t.sf(direction*(m-boundary)/se,len(x)-1))
        return {"mean":m,"pairs":len(x),"t_ci97_5":ci,"bootstrap_ci97_5":boot.tolist(),"null_boundary":boundary,"p_one_sided":p}
    cache,old=pairs("v47",range(1,26))
    lock=one("*/v47/protocol_lock.json")
    runner=one("v47_dreyer_confirmation.py")
    check(all(row["signature"]=={"protocol_sha256":sha(lock),"runner_sha256":sha(runner)} for row in cache),"V47 pair signature mismatch")
    check(all(v["gate"] for v in read(one("*/v44_a1/result.json"))["methods"].values()),"Dreyer method gate")
    check(all(row["controls"][arm]["H_minus_W_concordance"]==0 for row in cache for arm in ("frozen","last_three")), "Dreyer control")
    key="H_minus_W_concordance"
    def gap(rows,arm):
        return np.array([row[arm]["H_concordance"]-row[arm]["W_concordance"] for row in rows])
    rows=[r["results"] for r in cache]
    adapted=gap(rows,"last_three")
    effects={"K1":component(adapted,old["arms"]["last_three"][key]),
             "K2":component(adapted-gap(rows,"frozen"),old["depth_interaction_H_minus_W"])}
    rows,old=pairs("v68",range(1,23))
    rows=[r["8"] for r in rows]
    old=old["analysis"]["8"]
    check(old["background_gate"],"Stieger C8 background gate")
    def col(arm,metric):
        return np.array([r[arm][metric] for r in rows])
    paired=old["paired"]
    own=col("own_rank16","Brier")
    for k,arm in (("K3","background"),("K4","partner_rank16")):
        effects[k]=component(col(arm,"Brier")-own,paired[f"own_rank16_minus_{arm}"]["Brier"],sign=-1)
    exact=paired["own_rank16_minus_exact_shared"]
    margins=cfg["noninferiority"]
    lim=cfg["approximation"]["probability_mae_upper"]
    components={
        "delta_BA":component(col("own_rank16","BA")-col("exact_shared","BA"),exact["BA"],boundary=margins["ba_margin"]),
        "delta_Brier":component(own-col("exact_shared","Brier"),exact["Brier"],boundary=margins["brier_margin"],direction=-1),
        "MAE":component(col("own_rank16","probability_mae"),old["arms"]["own_rank16"]["probability_mae"],boundary=lim,direction=-1)}
    gate=(components["delta_BA"]["t_ci97_5"][0]>margins["ba_margin"] and components["delta_Brier"]["t_ci97_5"][1]<margins["brier_margin"] and components["MAE"]["t_ci97_5"][1]<=lim)
    effects["K5"]={"components":components,"passed_interval_gates":gate,"p_one_sided":max(c["p_one_sided"] for c in components.values())}
    for k,p in holm({k:e["p_one_sided"] for k,e in effects.items()}).items():
        effects[k]["holm_p"]=p
        effects[k]["statistical_threshold_met"]=bool(p<cfg["primary_family_alpha"] and (k!="K5" or gate))
    support={}
    for stage,ids in (("v46_fit",range(1,19)),("v61",range(1,23)),("v65",read(one("*/v65/block_lock.json"))["accepted_original_pair_ordinals"])):
        rows,ref=pairs(stage,ids)
        if stage=="v46_fit":
            arm=[r["arms"]["last_three"] for r in rows]
            saved=ref["arms"]["last_three"]
        else:
            arm=[r["block_separated" if stage=="v65" else "effects"] for r in rows]
            saved=ref["effects"]
        for metric,left,right in ((key,"H","W"),("W_minus_R_concordance","W","R")):
            summary=component([r[left+"_concordance"]-r[right+"_concordance"] for r in arm],saved[metric])
            support[f"{stage}/{metric}"]={k:summary[k] for k in ("mean","pairs","bootstrap_ci97_5","t_ci97_5")}
    openbmi,openbmi_reference=pairs("v46_fit",range(1,19))
    openbmi=[row["arms"] for row in openbmi]
    contrast=component(gap(openbmi,"last_three")-gap(openbmi,"frozen"),
                       openbmi_reference["last_three_minus_frozen"][key])
    support["v46_fit/adaptation_interaction"]={k:contrast[k] for k in ("mean","pairs","bootstrap_ci97_5","t_ci97_5")}

    def utility_boundary(stage, reference, rows, left, right, calibration=None):
        record={}
        for metric,direction,margin in (("BA",1,margins["ba_margin"]),("Brier",-1,margins["brier_margin"])):
            contrasts=[]
            for row in rows:
                a,b=row[left],row[right]
                if calibration:
                    a,b=a[calibration],b[calibration]
                contrasts.append(a[metric]-b[metric])
            item=component(contrasts,reference[metric] if reference else None,boundary=margin,direction=direction)
            record[metric]={k:item[k] for k in ("mean","pairs","bootstrap_ci97_5","t_ci97_5")}
        record["joint_noninferior"]=bool(record["BA"]["t_ci97_5"][0]>margins["ba_margin"]
                                         and record["Brier"]["t_ci97_5"][1]<margins["brier_margin"])
        record["comparison"]=f"{left} minus {right}"
        support[stage]=record

    position_arms,_=pairs("v48",range(1,19))
    old_replay=read(one("*/v54/result.json"))
    utility_boundary("v48/M3_vs_M1",None if raw else old_replay["V48_M3_minus_M1_retrospective"],
                     position_arms,"M3_local","M1_target_encoder")
    calibration,calibration_ref=pairs("v56",range(1,19))
    utility_boundary("v56/M3_vs_M1_Platt",calibration_ref["paired_differences"]["M3_local_minus_M1_target_encoder"]["platt"],
                     [v["row"] for v in calibration],"M3_local","M1_target_encoder","platt")
    for key,record in effects.items():
        record["status"]=("Non-inferior" if key=="K5" else "Supported") if record["statistical_threshold_met"] else "Inconclusive"
    output={"evidence":"statistics replay of verified raw-data reruns" if raw else "statistics replay of archived pair metrics",
            "primary":effects,"supporting":support,
            "K6":"separate offline engineering receipts","config_sha256":sha(ROOT/"configs/statistics.yaml"),
            "source_sha256":sha(ROOT/"neuroprivacy/replay.py")}
    if raw:
        output["raw_reproduction_audit_sha256"]=sha(raw_receipt)
        audit=ROOT/"results/audit.json"
        output["K6"]=read(audit)["cached_runs"]["K6"]
        output["offline_audit_sha256"]=sha(audit)
    write_json(ROOT/"results/primary_statistics.json",output)
    return output
