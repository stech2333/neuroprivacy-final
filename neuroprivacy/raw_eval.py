"""Refit frozen models using the panels rebuilt from local raw waveforms."""
import argparse
from pathlib import Path
from time import perf_counter

from .raw_panels import OUT
import numpy as np

def write_result(folder, name, body, expected=None):
    from resume_v21 import write_json
    if expected is not None and body != expected:
        raise ValueError(f"{name}: model rerun differs from the original aggregate")
    write_json(folder / f"{name}.json", body)

def netbci():
    import v67_netbci_repeat as legacy
    from v59_existing_data import roles as original_roles
    from v5_data import digest, read
    original = legacy.original
    local = OUT / "netbci"
    receipt = read(local/"complete.json")
    manifest = receipt["arrays_exact"]
    roles = original_roles()

    def load(name):
        path = local/name
        if digest(path) != manifest[name]["new_sha256"]:
            raise ValueError(f"Re-extracted NETBCI panel changed: {name}")
        with np.load(path,allow_pickle=False) as data:
            return dict(data)

    background = [load(f"background_{i:02d}.npz") for i in range(len(roles["background"]))]
    histories = [load(f"history_{i:02d}.npz") for i in range(len(roles["evaluation"]))]
    matrix = {(i,day):load(f"person_{i:02d}_day{day}.npz") for i in range(len(histories)) for day in legacy.DAYS}
    archived_loader = original.panels
    def rebuilt_background(folder):
        if folder != original.PREPARED:
            return archived_loader(folder)
        return read(folder/"result.json"), background

    legacy.evaluation_data = lambda: (read(legacy.PREP/"result.json"), matrix)
    legacy.reuse_histories = lambda: histories
    original.panels = rebuilt_background
    folder = local/"evaluation"
    folder.mkdir(exist_ok=True)
    result, _ = legacy.run(folder, lambda msg: print(msg,flush=True))
    archived = legacy.RUN/"v67"/"result.json"
    write_result(folder,"v67_aggregate",result,read(archived))
    for f in folder.glob("person_*_summary.json"):
        if read(f) != read(archived.with_name(f.name)):
            raise ValueError(f"Rebuilt NETBCI result differs for {f.name}")
    if {f.name for f in folder.glob("person_*_summary.json")}!={f.name for f in archived.parent.glob("person_*_summary.json")}:
        raise ValueError("The original and rebuilt NETBCI participant outputs have different coverage")
    write_result(folder,"provenance",{"raw_panels_sha256":digest(local/"complete.json"),
                 "archived_result_sha256":digest(archived),"rebuilt_result_sha256":digest(folder/"v67_aggregate.json"),
                 "exact_participant_results":len(histories),"code_sha256":digest(Path(__file__))})

    config = read(legacy.day3.V59)["background_model"]
    basis, groups, base = original.train(background,config)
    penalty = config[2]
    solvers = original.solver_library(groups,base,penalty)
    _, _, hessian = original.curvature.decompose(groups,base)
    diagonal = np.diag(hessian)
    spec = {"isotropic":{"scalar":np.asarray(np.trace(hessian)/len(diagonal))},"diagonal":{"diagonal":diagonal}}
    for method, descriptor in spec.items():
        diag = descriptor.get("diagonal",np.full(len(diagonal),descriptor.get("scalar",0.)))
        curved = original.curvature.DiagonalLowRank(diag,np.empty((len(diagonal),0)),np.empty(0),len(groups),penalty)
        solvers[method] = (curved.solve,descriptor)
    methods = {"P0":"optimized_background","P1":"exact_shared","P2":"isotropic","P3":"diagonal","P4":"full","P5":"rank_4"}
    rows = []
    resource_rows = []
    for i, panel in enumerate(histories):
        h,y=original.fields(panel,"H","cov")
        h=basis(h)
        heads={}
        runtimes={}
        for code,method in methods.items():
            started=perf_counter()
            if code=="P0":
                heads[code]=base
            elif code=="P1":
                heads[code]=original.fit_equal_people(groups+[(h,y)],penalty)
            else:
                heads[code]=original.curvature.update_local(solvers[method][0],base,penalty,h,y)
            runtimes[code]=perf_counter()-started
        daily=[]
        for day in legacy.DAYS:
            day_panel=matrix[i,day]
            c,cy=original.fields(day_panel,"C","cov")
            u,truth=original.fields(day_panel,"U","cov")
            cal=legacy.nested(basis(c),cy,8)
            ux=basis(u)
            probabilities={code:original.score(head,cal,ux,config) for code,head in heads.items()}
            daily.append({code:original.task_metrics(p,truth) | ({"probability_mae":float(np.abs(p-probabilities["P1"]).mean())}
                         if code not in ("P0","P1") else {}) for code,p in probabilities.items()})
        rows.append({method:{metric:float(np.mean([day[code][metric] for day in daily])) for metric in daily[0][code]}
                     for code,method in methods.items()})
        resource_rows.append({method:{"head_seconds":runtimes[code]} | (
            {"parameter_L2":float(np.linalg.norm(heads[code]-heads["P1"]))} if code not in ("P0","P1") else {})
            for code,method in methods.items()})
        write_result(folder,f"controls_person_{i:02d}",{"head_seconds":runtimes,"participant_first_metrics":rows[-1]})
    report=original.statistics(rows)
    for arm in (methods["P0"],methods["P1"],methods["P4"],methods["P5"]):
        if report["arms"][arm]!=result["pooled_subject_first"]["8"]["arms"][arm]:
            raise ValueError(f"{arm} differed from the rebuilt original arm")
    write_result(folder,"controls_C8",{"method_labels":methods,"people":len(rows),"days":list(legacy.DAYS),
                 "summary":report,"curvature_array_bytes":{method:sum(a.nbytes for a in solvers[method][1].values())
                 for method in methods.values() if method in solvers},
                 "resources":{method:{metric:float(np.mean([row[method][metric] for row in resource_rows]))
                              for metric in resource_rows[0][method]} for method in methods.values()},
                 "rank_selection":"fixed rank 4",
                 "source_manifest_sha256":digest(local/"complete.json"),"code_sha256":digest(Path(__file__))})
    print("NETBCI V67 raw-to-result reproduction and P0–P5 finished.",flush=True)

def rebuilt_stieger_loader():
    from v5_data import digest, read
    local = OUT / "stieger"
    lock = read(local / "complete.json")
    receipts = {row["panel"]:row for row in lock["panels"]}
    def load(people, dates):
        panels={}
        for p in people:
            for day in dates:
                path=local/f"S{p}_Session_{day}.npz"
                info=receipts[path.name]
                receipt=local/info["receipt"]
                if digest(receipt)!=info["receipt_sha256"] or digest(path)!=read(receipt)["new_panel_sha256"]:
                    raise ValueError(f"Rebuilt Stieger panel changed: {path.name}")
                with np.load(path,allow_pickle=False) as dataset:
                    panels[p,day]=dict(dataset)
        return panels
    return load

def stieger():
    import v61_stieger_records as source
    import v65_stieger_blocks as v65
    import v68_stieger_doses as v68
    from v5_data import digest, read
    local=OUT/"stieger"
    source.load=rebuilt_stieger_loader()
    for stage,module in (("v61",source),("v65",v65),("v68",v68)):
        target=local/"evaluation"/stage
        target.mkdir(parents=True,exist_ok=True)
        result,_=module.run(target,lambda line:print(line,flush=True))
        archived=module.RUN/stage/"result.json"
        write_result(target,"result",result,read(archived))
        if {f.name for f in target.glob("pair_*.json")}!={f.name for f in archived.parent.glob("pair_*.json")}:
            raise ValueError(f"{stage} used different original person pairs")
        for f in target.glob("pair_*.json"):
            if read(f)!=read(archived.with_name(f.name)):
                raise ValueError(f"{stage} disagreed with original paired record {f.name}")
        write_result(target,"provenance",{"raw_panels_sha256":digest(local/"complete.json"),
                      "archived_result_sha256":digest(archived),"code_sha256":digest(Path(__file__))})

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset",choices=("netbci","stieger"))
    options=parser.parse_args()
    if options.dataset=="stieger":
        stieger()
    else:
        netbci()
