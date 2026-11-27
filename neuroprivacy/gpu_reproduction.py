"""Reproduce the original GPU arms with locked inputs and a separate output tree."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

from .raw_panels import ROOT, OUT

def locked_design(sha, digest):
    archives = ROOT.parent / "_feasibility/designs"
    destination = OUT / "historical_designs" / (sha + ".md")
    destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        from hashlib import sha256
        for path in archives.glob("*.zip"):
            with zipfile.ZipFile(path) as source:
                for member in source.infolist():
                    if member.is_dir():
                        continue
                    content=source.read(member)
                    if sha256(content).hexdigest()==sha:
                        destination.write_bytes(content)
                        break
            if destination.exists():
                break
    if not destination.is_file() or digest(destination)!=sha:
        raise ValueError("Exact protocol bytes for legacy stage are unavailable")
    return destination

def dreyer():
    import v47_dreyer_confirmation as source
    source_files=source.RUN/"v47"
    lock=source.read(source_files/"protocol_lock.json")
    destination=OUT/"dreyer"/"v47"
    destination.mkdir(parents=True,exist_ok=True)
    runner=source.Path(source.__file__)
    if source.digest(runner)!=source.read(source_files/"registration.json")["runner_sha256"]:
        raise ValueError("Dreyer original GPU runner does not match historical registration")
    source.DESIGN=locked_design(lock["plan_sha256"],source.digest)
    originals=source.PREFETCH/"verified_recordings"
    _, files=source.sources()
    catalog={Path(row["path"]).name:row for rows in files.values() for row in rows}

    def use_local(row, _):
        name=Path(row["path"]).name
        path=originals/name
        if catalog[name]!=row or not source.v44.dreyer.verified(path,row):
            raise ValueError(f"Missing or changed locally registered Dreyer asset: {name}")
        return path

    source.transfer=use_local
    result,_=source.sealed(destination,lambda line:print(line,flush=True))
    reference=source.read(source_files/"result.json")
    if result["valid_pairs"]!=25 or result["protocol_sha256"]!=reference["protocol_sha256"]:
        raise ValueError("Dreyer original test coverage or lock differs")
    source.write_json(destination/"result.json",result)
    key="H_minus_W_concordance"
    expected={"K1":reference["arms"]["last_three"][key]["mean"],
              "K2":reference["depth_interaction_H_minus_W"]["mean"]}
    actual={"K1":result["arms"]["last_three"][key]["mean"],"K2":result["depth_interaction_H_minus_W"]["mean"]}
    source.write_json(destination/"comparison.json",{"reference":expected,"rerun":actual,"equal_primary_effects":expected==actual,
                      "coverage":result["valid_pairs"],"historical_lock":result["protocol_sha256"],"source_runner":source.digest(runner),
                      "result_sha256":source.digest(destination/"result.json")})
    print("Dreyer V47 original waveform and training reproduction finished.",flush=True)

def rebuilt_openbmi_inputs(source, *, allow_encode):
    import numpy as np
    import torch
    from runtime import record_npz
    local=OUT/"openbmi"
    wave_receipt=local/"complete.json"
    registered=source.read(wave_receipt)
    if registered["registry_sha256"]!=source.digest(source.REGISTRY):
        raise ValueError("Rebuilt OpenBMI panels use another V11 registry")
    manifests={r["window"]:r for r in registered["panel_receipts"]}
    historical=source.RUN/"v46_fit"
    fit_dir=local/"evaluation"/"v46_fit"
    prefix_dir=fit_dir/"rebuilt_prefix"
    prefix_dir.mkdir(parents=True,exist_ok=True)
    original_registration=source.read(historical/"registration.json")
    if source.digest(Path(source.__file__))!=original_registration["runner_sha256"]:
        raise ValueError("V46 implementation changed since registration")

    def load_panels(reg,encoder,device,update,deadline):
        panels={}
        for i,(key,meta) in enumerate(reg["windows"].items(),1):
            if time.time()>=deadline:
                return None
            new=local/f"{key}.npz"
            old=manifests[key]
            if source.digest(new)!=old["new_sha256"] or meta["wave_sha256"]!=old["original"]:
                raise ValueError("Rebuilt panel or original wave receipt changed")
            output=prefix_dir/f"{key}.npz"
            receipt=output.with_suffix(".json")
            if receipt.is_file():
                if source.read(receipt)!={"wave":old["new_sha256"],"prefix":source.digest(output)}:
                    raise ValueError("Rebuilt prefix receipt mismatch")
                payload=source.v21.v11.read_window(output,("features","y"))
            else:
                if not allow_encode:
                    raise FileNotFoundError(f"V46 rebuilt prefix is missing: {key}")
                raw=source.v21.v11.read_window(new,("wave","y"))
                payload={"features":source.v21.v19.prefix(encoder,raw["wave"],device),"y":raw["y"]}
                record_npz(output,**payload)
                source.write_json(receipt,{"wave":old["new_sha256"],"prefix":source.digest(output)})
            if not np.array_equal(payload["y"],meta["labels"]):
                raise ValueError("Rebuilt prefix lost the original labels")
            p,day=map(int,key.split("_"))
            panels[p,day]={role:tuple(torch.from_numpy(payload[k][ids]) for k in ("features","y"))
                           for role,ids in meta["groups"].items()}
            if i%8==0 or i==len(reg["windows"]):
                update(f"OpenBMI frozen prefix rebuilt {i}/{len(reg['windows'])}")
        return panels

    source.v21.load_panels=load_panels
    return fit_dir, historical, wave_receipt, original_registration

def openbmi():
    import torch
    import v46_openbmi_records as source

    if not torch.cuda.is_available():
        raise RuntimeError("OpenBMI V46 needs a visible CUDA GPU in the original deep-gpu runtime")
    fit_dir, historical, wave_receipt, original_registration = rebuilt_openbmi_inputs(source, allow_encode=True)
    print(f"OpenBMI V46 · CUDA device: {torch.cuda.get_device_name(0)}", flush=True)
    source.write_json(fit_dir/"registration.json",
                      {"runner_sha256":original_registration["runner_sha256"],
                       "sources_sha256":original_registration["sources_sha256"],
                       "raw_reproduction_sha256":source.digest(wave_receipt)})
    log=lambda line: print(line,flush=True)
    result,_=source.fit_records(fit_dir,log)
    source.write_json(fit_dir/"result.json",result)
    archived=source.read(historical/"result.json")
    key="H_minus_W_concordance"
    source.write_json(fit_dir/"comparison.json",{
        "reference":archived["arms"]["last_three"][key]["mean"],
        "rerun":result["arms"]["last_three"][key]["mean"],"pairs":result["pairs"],
        "result_sha256":source.digest(fit_dir/"result.json")})
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = "-1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    subprocess.run([sys.executable, "-X", "utf8", "-s", "-u", "-m",
                    "neuroprivacy.gpu_reproduction", "openbmi", "--postfit"],
                   cwd=ROOT, env=env, check=True)

def openbmi_postfit():
    import v46_openbmi_records as source
    import v48_learning_location as positions
    import v56_calibration as deep

    fit_dir, _, _, _ = rebuilt_openbmi_inputs(source, allow_encode=False)
    comparison = source.read(fit_dir/"comparison.json")
    if comparison["pairs"] != 18 or source.digest(fit_dir/"result.json") != comparison["result_sha256"]:
        raise ValueError("Complete V46 results are required before V48 and V56")
    positions.V46=fit_dir
    print("OpenBMI V48 and V56 · CPU (registered device)", flush=True)
    log=lambda line: print(line,flush=True)
    for stage, runner, registration in (
        ("v48", positions, positions.RUN/"v48"/"registration.json"),
        ("v56", deep, deep.RUN/"v56"/"registration.json"),
    ):
        original = source.read(registration)
        if original["device"] != "CPU" or source.digest(Path(runner.__file__)) != original["runner_sha256"]:
            raise ValueError(f"{stage} CPU runner differs from the historical registration")
        out=fit_dir.parent/stage
        out.mkdir(exist_ok=True)
        result,_=runner.run(out,log)
        source.write_json(out/"result.json",result)

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset",choices=("dreyer","openbmi"))
    parser.add_argument("--postfit",action="store_true",help=argparse.SUPPRESS)
    options=parser.parse_args()
    if options.postfit:
        if options.dataset!="openbmi":
            parser.error("--postfit is only for OpenBMI")
        openbmi_postfit()
    elif options.dataset=="dreyer":
        dreyer()
    else:
        openbmi()
