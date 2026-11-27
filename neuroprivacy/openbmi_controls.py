"""Evaluate registered OpenBMI C20 controls with the fixed background encoder."""
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter, time

from .raw_panels import OUT, save
import numpy as np

def evaluate(*, rebuilt=False):
    import v49_structured_curvature as method
    import torch
    from scipy.special import expit
    from runtime import pair_blocks, summary
    from v5_data import digest, read

    source = method.v39.history
    v11, trainer, v21 = source.v11, source.v19, source.v21
    provenance={}
    if rebuilt:
        from .gpu_reproduction import rebuilt_openbmi_inputs
        import v46_openbmi_records as v46
        _, _, wave_receipt, _=rebuilt_openbmi_inputs(v46,allow_encode=False)
        provenance={"raw_panels_sha256":digest(wave_receipt)}
    registry_path = v11.RUN/"registration.json"
    registry = read(registry_path)
    freeze = read(source.RUN/"v27_registration.json")
    if digest(registry_path)!=freeze["registry_sha256"] or digest(v11.WEIGHT)!=registry["cbramod_weight_sha256"]:
        raise ValueError("OpenBMI fixed source changed")
    torch.set_num_threads(3)
    encoder, device = v11.load_encoder()
    if device!="cpu":
        raise RuntimeError("Use the original OpenBMI V49 CPU evaluation lane")
    prefixes=v21.load_panels(registry,encoder,device,lambda line: print(line,flush=True),time()+1800)
    if prefixes is None:
        raise TimeoutError("OpenBMI prefix assembly timed out")
    penalty=read(v11.RUN/"utility_CBraMod.json")["lambda"]
    names={"P0":"calibrated_background","P1":"exact_shared","P2":"isotropic","P3":"diagonal","P4":"full",
           "P5":"rank_8","U2":"matched_other_rank_8"}
    all_seeds=[]
    descriptors={}
    for seed in trainer.SEEDS:
        checkpoint=v21.PRIOR/"training"/"v19"/str(seed)/"last_three"/"checkpoint.pt"
        if digest(checkpoint)!=freeze["only_background_tuned_checkpoints"][str(seed)]:
            raise ValueError("OpenBMI background-only checkpoint changed")
        model=trainer.Readout(encoder,3).eval().requires_grad_(False)
        model.load_state_dict(torch.load(checkpoint,map_location="cpu",weights_only=True)["best"]["state"])
        panels=source.representations(prefixes,model,registry,device)
        background=[(panels[p,1][0],panels[p,1][2]) for p in registry["roles"]["background"]]
        fit=source.eeg.fit_equal_people
        base=fit(background,penalty)
        _,_,hessian=method.decompose(background,base)
        specs,operators,_=method.make_operators(hessian,len(background),penalty)
        for code in ("P2","P3","P4","P5"):
            spec=specs[names[code]]
            descriptors[code]=sum(array.nbytes for array in spec.values())
        seed_rows=[]
        for pair in registry["pairs"]:
            heads={}
            elapsed={}
            for person in pair:
                x,_,y,_=panels[person,1]
                heads[person]={"P0":base}
                elapsed[person]={"P0":0.}
                for code in ("P1","P2","P3","P4","P5"):
                    start=perf_counter()
                    heads[person][code]=(fit(background+[(x,y)],penalty) if code=="P1"
                                         else method.update_local(operators[names[code]],base,penalty,x,y))
                    elapsed[person][code]=perf_counter()-start
            for person,other in (pair,pair[::-1]):
                current=panels[person,2]
                x,_,labels,roles=current
                u=roles["U"]
                matched_heads=heads[person] | {"U2":heads[other]["P5"]}
                probabilities={code:source.v12.add_today(expit(x@head),current)[u] for code,head in matched_heads.items()}
                outputs={}
                for code,prob in probabilities.items():
                    metrics=v11.task_metrics(prob,labels[u])
                    if code in ("P2","P3","P4","P5"):
                        metrics["prediction_MAE"]=float(np.abs(prob-probabilities["P1"]).mean())
                        metrics["parameter_L2"]=float(np.linalg.norm(heads[person][code]-heads[person]["P1"]))
                    if code in elapsed[person]:
                        metrics["head_seconds"]=elapsed[person][code]
                    outputs[code]=metrics
                seed_rows.append(outputs)
        all_seeds.append(seed_rows)
        print(f"OpenBMI C20 · background seed {seed} · P0–P5 and matched history completed",flush=True)
    def values(code,metric):
        return np.array([np.mean([row[code][metric] for row in same_person]) for same_person in zip(*all_seeds,strict=True)])
    arms={}
    for code in names:
        v={m:summary(pair_blocks(values(code,m))) for m in all_seeds[0][0][code]}
        if code in descriptors:
            for metric in ("BA","Brier"):
                v[f"delta_{metric}"]=summary(pair_blocks(values(code,metric)-values("P1",metric)))
            v["BA_Brier_MAE_pass"]=bool(v["delta_BA"]["pair_t_ci"][0]>-.03 and v["delta_Brier"]["pair_t_ci"][1]<.005 and v["prediction_MAE"]["pair_t_ci"][1]<=.01)
        arms[code]=v
    trials={}
    for code in ("P0","U2"):
        trials[f"own_minus_{code}"]={m:summary(pair_blocks(values("P5",m)-values(code,m))) for m in ("BA","Brier","MI_AUROC")}
    archive=read(method.RUN/"v49_openbmi"/"result.json")
    for code in descriptors:
        for m,prior_m in (("BA","BA"),("Brier","Brier"),("prediction_MAE","prediction_mae")):
            if not rebuilt and not np.isclose(arms[code][m]["mean"],archive["methods"][names[code]][prior_m]["mean"],atol=1e-12,rtol=0):
                raise ValueError(f"{code}/{m} does not reproduce original V49 arm")
    current=OUT/"openbmi_controls"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    current.mkdir(parents=True)
    save(current/"result.json",{"rank":8,"methods":names,"arms":arms,"history_effects":trials,"curvature_array_bytes":descriptors,
         "pairs":len(registry["pairs"]),"seeds":list(trainer.SEEDS),"budget":"H40/C20/U20",
         "source":"V46 raw-rebuilt prefixes and registered background checkpoints" if rebuilt else
                  "registered OpenBMI cached prefixes and pretrained background checkpoints",
         "source_registration_sha256":digest(registry_path),"code_sha256":digest(Path(__file__))} | provenance)
    print(current,flush=True)

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuilt",action="store_true",help="Use V46 prefixes re-encoded from raw BDF")
    evaluate(rebuilt=parser.parse_args().rebuilt)
