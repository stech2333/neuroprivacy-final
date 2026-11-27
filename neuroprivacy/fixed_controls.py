"""Apply the registered P0–P5 methods to the original Stieger V68 C8 panel."""
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent/"neuroprivacy_next_20261122"
sys.path.insert(0,str(OLD))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

def main(*, rebuilt=False):
    import v68_stieger_doses as source
    from .raw_eval import rebuilt_stieger_loader
    import numpy as np
    from runtime import summary
    roles=source.read(source.archive.REG)["roles"]
    dev,bg,evaluation=(roles[k] for k in ("development","background","confirmation"))
    load=rebuilt_stieger_loader() if rebuilt else source.archive.load
    data=load(dev+bg+evaluation,(2,))
    data.update(load(evaluation,(3,)))
    histories,panels=source.scope(data,roles)
    background=[histories[p] for p in bg]
    penalty=source.archive.stieger.PENALTY
    fit=source.archive.stieger.eeg.fit_equal_people
    base=fit(background,penalty)
    _,_,matrix=source.curvature.decompose(background,base)
    specs,operators,_=source.curvature.make_operators(matrix,len(bg),penalty)
    methods={"P0":"background","P1":"exact_shared","P2":"isotropic","P3":"diagonal","P4":"full","P5":"rank_16"}
    rows=[]
    for p in evaluation:
        outputs={}
        for code,method in methods.items():
            start=perf_counter()
            if code=="P0":
                head=base
            elif code=="P1":
                head=fit(background+[histories[p]],penalty)
            else:
                head=source.curvature.update_local(operators[method],base,penalty,*histories[p])
            seconds=perf_counter()-start
            prob,metrics=source.score(head,panels[p],8)
            if code=="P1":
                exact=prob
                exact_head=head
            outputs[code]={"BA":metrics["BA"],"Brier":metrics["Brier"],"head_fit_seconds":seconds}
            if code not in ("P0","P1"):
                outputs[code]["MAE"]=float(np.abs(exact-prob).mean())
                outputs[code]["parameter_L2"]=float(np.linalg.norm(head-exact_head))
        rows.append(outputs)
    def within_pairs(values):
        return np.asarray(values).reshape(-1,2).mean(axis=1)
    def vector(code,metric):
        return within_pairs([r[code][metric] for r in rows])
    historical=source.read(source.RUN/"v68"/"result.json")["analysis"]["8"]
    mapping={"P0":"background","P1":"exact_shared","P4":"own_full","P5":"own_rank16"}
    for code,arm in mapping.items():
        for metric in ("BA","Brier"):
            if not np.isclose(vector(code,metric).mean(),historical["arms"][arm][metric]["mean"],atol=1e-12,rtol=0):
                raise ValueError("Mismatch with the existing V68 panel")
    report={}
    for code,method in methods.items():
        row={key:summary(vector(code,key)) for key in rows[0][code]}
        if code not in ("P0","P1"):
            row["delta_BA"]=summary(vector(code,"BA")-vector("P1","BA"))
            row["delta_Brier"]=summary(vector(code,"Brier")-vector("P1","Brier"))
            row["curvature_array_bytes"]=sum(a.nbytes for a in specs[method].values())
            row["BA_Brier_MAE_pass"]=bool(row["delta_BA"]["pair_t_ci"][0]>-.03 and
                                      row["delta_Brier"]["pair_t_ci"][1]<.005 and row["MAE"]["pair_t_ci"][1]<=.01)
        report[code]=row
    out=ROOT/"results"/"stieger_C8_controls"/datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out.mkdir(parents=True)
    provenance={"raw_panels_sha256":source.digest(ROOT/"results/raw_reproduction/stieger/complete.json")} if rebuilt else {}
    for filename,record in (("participant_metrics.json",{"evaluation_order":evaluation,"metrics":rows}),
                             ("result.json",{"methods":methods,"metrics":report,"budget":"H40/C8/U40","pairs":22,
                              "selection":"frozen rank 16; no reselection","panel":source.digest(source.archive.REG),
                              "base_head_sha256":source.curvature.sha256(base.tobytes()).hexdigest(),
                              "v68_source_sha256":source.digest(Path(source.__file__)),"v49_source_sha256":source.digest(Path(source.curvature.__file__)),
                              "code_sha256":source.digest(Path(__file__))} | provenance)):
        (out/filename).write_text(json.dumps(record,indent=2,allow_nan=False),encoding="utf-8")
    print(out)

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuilt",action="store_true",help="Read re-extracted raw MAT panels")
    main(rebuilt=parser.parse_args().rebuilt)
