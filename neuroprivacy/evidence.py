"""Build the Phase A evidence map from historical registrations and sealed results."""
from pathlib import Path
from .common import *

PRIMARY={
"K1":("H1","Dreyer","25 pairs","v47",["v46_fit","v65","v61","v54"]),
"K2":("H1","Dreyer","25 pairs","v47",["v46_fit","v54","v44_a1"]),
"K3":("H2","Stieger","22 pairs, H40/C8/U40","v68",["v67","v64"]),
"K4":("H2","Stieger","22 pairs, H40/C8/U40","v68",["v67"]),
"K5":("H3a","Stieger","22 pairs, H40/C8/U40","v68",["v49_stieger","v49_openbmi","v60","v67","v56"]),
"K6":("H3b","OpenBMI + Stieger","two offline reference paths","v51",["v58","v74","v48"])}
RUNNERS={"v46_fit":"v46_openbmi_records","v47":"v47_dreyer_confirmation","v65":"v65_stieger_blocks",
         "v61":"v61_stieger_records","v68":"v68_stieger_doses","v67":"v67_netbci_repeat",
         "v51":"v51_structured_boundary","v58":"v58_recovery","v49_stieger":"v49_structured_curvature",
         "v49_openbmi":"v49_structured_curvature"}

def models():
    reg=read(one("run_v11*/registration.json"))
    model=read(WORK/"neuroprivacy_v3/run/model.json")
    weights=Path("F:/safe/OpenBMI_WBCIC-SHU_EEGPT/cbramod/pretrained_weights.pth/pretrained_weights.pth")
    verified(weights,reg["cbramod_weight_sha256"])
    verified(weights,model["weight_sha256"])
    for file,digest in model["source_sha256"].items():
        verified(WORK/"neuroprivacy_v3/run/materials/cbramod"/file,digest)
    checkpoints=read(one("*/v27_registration.json"))["only_background_tuned_checkpoints"]
    assets=[{"purpose":"pretrained CBraMod","path":name(weights),"sha256":sha(weights)}]
    for seed,value in checkpoints.items():
        path=one(f"*/training/v19/{seed}/last_three/checkpoint.pt")
        verified(path,value)
        assets.append({"purpose":"background CBraMod","seed":seed,"path":name(path),"sha256":value})
    for cohort,rank in (("openbmi",8),("stieger",16)):
        f=one(f"*/v49_{cohort}/result.json")
        original=read(f)
        candidate=f"rank_{rank}"
        check(original["selected_in_development"]==candidate, "Historical fixed rank mismatch")
        for setup in original["setup"]:
            info=setup["curvature"][candidate]
            path=f.with_name(f"{setup['sample']}_{candidate}_curvature.npz")
            verified(path,info["sha256"])
            check(path.stat().st_size==info["npz_container_bytes"],"Curvature container size")
            assets.append({"purpose":f"{cohort} {candidate}","path":name(path),"sha256":info["sha256"],
                           "array_bytes":info["array_bytes"],"container_bytes":path.stat().st_size})
    net=one("*/v60/rank_4_curvature.npz")
    with __import__("numpy").load(net, allow_pickle=False) as npz:
        array_bytes=sum(npz[k].nbytes for k in npz.files)
    sizes=read(net.with_name("result.json"))["sizes"]["rank_4"]
    check(sizes=={"curvature_bytes":array_bytes,"serialized_bytes":net.stat().st_size},"NETBCI sizes")
    assets.append({"purpose":"NETBCI rank_4","path":name(net),"sha256":sha(net),"array_bytes":array_bytes,
                   "container_bytes":net.stat().st_size,"verification":"current hash; checked historical array/container sizes"})
    return {"assets":assets,"CBraMod_source":model,"author_reported_pretraining_corpus":"TUEG",
        "participant_level_pretraining_overlap":"unverified","citation":"https://proceedings.iclr.cc/paper_files/paper/2025/file/bbbd6d915cb90be21c1254a82d45cedd-Paper-Conference.pdf",
        "OpenBMI_background_penalty":read(one("run_v11*/utility_CBraMod.json"))["lambda"],
        "NETBCI_selection":read(one("*/v59/selection.json"))}

def create():
    mapping={}
    for k,(h,cohort,units,primary,support) in PRIMARY.items():
        files=[]
        for stage in [primary]+support:
            f=one(f"*/{stage}/result.json")
            files.append({"stage":stage,"role":"primary" if stage==primary or (k=="K6" and stage in {"v58","v74"}) else "support_or_boundary","file":name(f),"sha256":sha(f)})
            if stage in RUNNERS:
                verified(OLD/(RUNNERS[stage]+".py"),read(f.with_name("registration.json"))["runner_sha256"])
        mapping[k]={"hypothesis":h,"cohort":cohort,"unit":units,"sources":files}
    write_json(M/"legacy_result_mapping.json",mapping)
    write_json(M/"checkpoint_registry.json",models())
    locked=read(one("*/v67_prepare/protocol_lock.json"))
    verified(one("*/v59/selection.json"),locked["model_sha256"])
    for stage,digest in locked["scoring_recipes_sha256"].items():
        verified(one(f"*/{stage}/"+("prepared.json" if stage=="v55_prepare" else "panels.json")),digest)
    verified(one("*/v65/block_lock.json"),read(one("*/v65/result.json"))["block_lock_sha256"])
    verified(one("*/v47/protocol_lock.json"),read(one("*/v47/result.json"))["protocol_sha256"])
    # The published V54 receipt covers the historical pair files and allocators.
    receipt=read(one("*/v54/replay_receipt.json"))
    for stage,item in receipt["source_files"].items():
        result=one(f"*/{stage}/result.json")
        if "result_sha256" in item:
            verified(result,item["result_sha256"])
        for filename,digest in item["pair_receipts_sha256"].items():
            verified(result.with_name(filename),digest)
    return mapping
