"""Re-extract frozen EEG panels from registered local waveform files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT.parent / "neuroprivacy_next_20261122"
OUT = ROOT / "results/raw_reproduction"
sys.path.insert(0, str(OLD))
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import numpy as np

def verify_arrays(actual, expected, tag):
    if set(actual) != set(expected):
        raise ValueError(f"Array names differ: {tag}")
    error = {}
    for key in expected:
        a, b = actual[key], expected[key]
        if a.shape != b.shape or a.dtype != b.dtype:
            raise ValueError(f"Array shape or dtype differs: {tag}/{key}")
        np.testing.assert_array_equal(a, b, err_msg=f"{tag}/{key}")
        error[key] = list(a.shape)
    return error

def save(path, value):
    from resume_v21 import write_json
    write_json(path, value)

def seal_arrays(path, arrays, archived, registered_sha256, digest):
    if digest(archived) != registered_sha256:
        raise ValueError(f"Registered feature panel changed: {archived}")
    with np.load(archived, allow_pickle=False) as data:
        matched = verify_arrays(arrays, dict(data), path.stem)
    temp = path.with_suffix(".tmp")
    with temp.open("wb") as stream:
        np.savez(stream, **arrays)
    temp.replace(path)
    return matched

def stieger(all_sessions):
    import sequence_v18_stieger as legacy
    read, digest = legacy.read, legacy.digest
    reg = legacy.ARCHIVE / "stieger_registration.json"
    release = legacy.ARCHIVE / "stieger_release.json"
    original = legacy.RUN / "stieger_v18_registration.json"
    lock = read(original)
    for file, key in ((reg,"source_registration_sha256"), (release,"release_sha256"), (Path(legacy.__file__),"runner_sha256")):
        if digest(file) != lock[key]:
            raise ValueError(f"Stieger historical input or extractor changed: {file.name}")
    data = read(reg)
    roles = data["roles"]
    history = roles["development"] + roles["background"] + roles["confirmation"]
    selected = [(p, 2) for p in history] + [(p, 3) for p in roles["confirmation"]]
    if all_sessions:
        selected += [(p, 3) for p in roles["development"] + roles["background"]]
    else:
        selected = [(p, day) for p in roles["confirmation"][:2] for day in (2, 3)]
    release_files = read(release)["files"]
    folder = OUT / "stieger"
    folder.mkdir(parents=True, exist_ok=True)
    dataset_lock = digest(original)
    receipts = []
    for i, (person, day) in enumerate(selected, 1):
        tag = f"S{person}_Session_{day}"
        archive_item = release_files[str(person)][str(day)]
        waveform = legacy.RAW / tag / f"{tag}.mat"
        archive_panel = legacy.CACHE / f"{tag}.npz"
        archived_sha = read(archive_panel.with_suffix(".json"))["panel_sha256"]
        path = folder / f"{tag}.npz"
        receipt_file = path.with_suffix(".json")
        identity = {"waveform_sha256":archive_item["sha256"], "registered_panel_sha256":archived_sha,
                    "historical_registration_sha256":dataset_lock}
        if receipt_file.is_file():
            receipt = read(receipt_file)
            if any(receipt[key] != v for key, v in identity.items()) or digest(path) != receipt["new_panel_sha256"]:
                raise ValueError(f"Saved re-extraction receipt mismatch: {tag}")
        else:
            if waveform.stat().st_size != archive_item["size"] or digest(waveform) != archive_item["sha256"]:
                raise ValueError(f"Stieger source waveform failed release checksum: {tag}")
            arrays = legacy.extract(waveform, data["channels"])
            matched = seal_arrays(path, arrays, archive_panel, archived_sha, digest)
            receipt = identity | {"waveform": str(waveform), "new_panel_sha256": digest(path), "arrays_exact": matched}
            save(receipt_file, receipt)
        receipts.append({"panel":path.name,"receipt":receipt_file.name,"receipt_sha256":digest(receipt_file)})
        print(f"Stieger MAT → covariance {i}/{len(selected)} · {tag}",flush=True)
    save(folder / ("complete.json" if all_sessions else "spot_check.json"),
         {"extraction":"original raw MAT", "sessions":len(receipts), "input_lock_sha256":dataset_lock,"panels":receipts})

def netbci():
    import v59_existing_data as history
    import v67_netbci_panels as v67
    import v59_netbci_optimize as original
    from v5_data import digest, read
    source_stage = v67.RUN / "v67_prepare"
    locks = read(source_stage / "result.json")
    panel_list = source_stage / "panels.json"
    if digest(panel_list) != locks["panel_list_sha256"] or digest(source_stage/"protocol_lock.json") != locks["protocol_sha256"]:
        raise ValueError("NETBCI frozen holdout ledger changed")
    sys.path.insert(0, str(history.prep.v45.prior.RUNTIME))
    import pyedflib
    grouped, roles = history.prep.manifest(), history.roles()
    old_cache = history.HISTORICAL + (
        original.PREPARED/"verified_recordings", v67_earlier_cache(v67.RUN), source_stage/"verified_recordings",
    )
    def raw(person, day, run):
        assets = grouped[person][day,run]
        names = [Path(r["path"]).name for r in assets]
        present = next((c for c in old_cache if all((c/f).is_file() for f in names)), None)
        if present is None:
            raise FileNotFoundError(f"Registered raw EDF or sidecar unavailable for {person} Day {day} Run {run}")
        for item in assets:
            if not history.prep.verified(present/Path(item["path"]).name,item):
                raise ValueError(f"NETBCI signed source failed original checksum for day {day}, run {run}")
        return history.prep.archived(assets,present,pyedflib.EdfReader)
    def balanced(person, day, runs, count):
        return history.prep.v45.balanced([raw(person,day,run) for run in runs],count)
    def panel(results):
        return {f"{key}_{field}":value for key, values in results.items()
                for field,value in zip(("power","cov","y"),values,strict=True)}
    folder = OUT/"netbci"
    folder.mkdir(parents=True,exist_ok=True)
    manifests = {}
    frozen_background = read(original.PREPARED/"panels.json")
    if digest(original.PREPARED/"panels.json") != read(original.PREPARED/"result.json")["panel_list_sha256"]:
        raise ValueError("NETBCI background manifest changed")
    for row in frozen_background:
        who = roles["background"][row["ordinal"]]
        current = panel({
            "H":balanced(who,1,(1,2),40), "T":balanced(who,1,(1,2),20),
            "D":balanced(who,2,(1,2),20), "C":balanced(who,3,(1,),20),
            "U":balanced(who,3,(2,3),40),
        })
        path = folder / f"background_{row['ordinal']:02d}.npz"
        matched = seal_arrays(path, current, original.PREPARED/row["file"], row["source_sha256"], digest)
        manifests[path.name] = {"new_sha256":digest(path),"original_sha256":row["source_sha256"],"arrays_exact":matched}
    for row in read(panel_list):
        ordinal, day = row["ordinal"], row["day"]
        who = roles["evaluation"][ordinal]
        path = folder / row["file"]
        current = panel({"C":balanced(who,day,(1,),20),"U":balanced(who,day,(6,),20)})
        matched = seal_arrays(path, current, source_stage/row["file"], row["sha256"], digest)
        manifests[path.name] = {"new_sha256":digest(path),"original_sha256":row["sha256"],"arrays_exact":matched}
        print(f"NETBCI EDF → features {len(manifests)-len(frozen_background)}/{locks['covered_panels']}",flush=True)
    history_source = v67.RUN.parent/"run_v63_v66_20261126"/"v63_prepare"
    history_manifest=history_source/"panels.json"
    historical_receipts=read(source_stage/"protocol_lock.json")["scoring_recipes_sha256"]
    if digest(history_manifest)!=historical_receipts["v63_prepare"]:
        raise ValueError("NETBCI history manifest differs from the original V67 freeze")
    for row in read(history_manifest):
        archived = history_source/row["file"]
        if digest(archived) != row["source_sha256"]:
            raise ValueError("NETBCI history seal changed")
        who = roles["evaluation"][row["ordinal"]]
        path=folder/f"history_{row['ordinal']:02d}.npz"
        arrays=panel({"H":balanced(who,1,(1,2),40)})
        with np.load(archived,allow_pickle=False) as data:
            matched=verify_arrays(arrays,{key:data[key] for key in arrays},path.stem)
        temp=path.with_suffix(".tmp")
        with temp.open("wb") as stream:
            np.savez(stream,**arrays)
        temp.replace(path)
        manifests[path.name]={"new_sha256":digest(path),"original_sha256":row["source_sha256"],"arrays_exact":matched}
    save(folder/"complete.json",{"extraction":"registered local raw EDF and sidecars","arrays_exact":manifests,
                                  "run_six_panels":locks["covered_panels"],"background_people":len(frozen_background),
                                  "history_people":len(roles["evaluation"])})

def v67_earlier_cache(root):
    return root.parent/"run_v63_v66_20261126"/"v63_prepare"/"verified_recordings"

def openbmi(limit=None):
    import v46_openbmi_records as legacy
    import v8_local as waveform
    from v7_four_seconds import LocalWindows
    from v5_data import source_entries, stem
    read, digest = legacy.read, legacy.digest
    registered = read(legacy.REGISTRY)
    legacy.acquire.DOWNLOADS = Path(os.environ.get("NEUROPRIVACY_OPENBMI_DOWNLOADS", "F:/safe/OpenBMI_WBCIC-SHU_EEGPT"))
    ledger = legacy.RUN / "v46_ledger" / "trial_roles.json"
    v46 = read(ledger)
    if digest(legacy.REGISTRY) != v46["v11"] or digest(ledger) != read(ledger.with_name("result.json"))["trial_roles_sha256"]:
        raise ValueError("OpenBMI registered ledger changed")
    catalog = source_entries("openbmi")
    folder = OUT / "openbmi"
    folder.mkdir(parents=True,exist_ok=True)
    receipt_list = []
    sessions = list(registered["windows"].items())[:limit]
    for i, (key, meta) in enumerate(sessions,1):
        person,day = map(int,key.split("_"))
        out=folder/(key+".npz")
        stamp=out.with_suffix(".json")
        original = Path(registered["waveform_directory"]) / (key + ".npz")
        catalog_item = catalog[stem("openbmi",person,day)+"_eeg.bdf"]
        if stamp.is_file():
            receipt=read(stamp)
            if receipt["window"] != key or receipt["original"] != meta["wave_sha256"] or receipt["raw_bdf_sha256"] != catalog_item["checksum"] or receipt["new_sha256"] != digest(out):
                raise ValueError(f"Rebuilt OpenBMI waveform receipt changed: {key}")
            receipt_list.append(receipt)
            continue
        source = LocalWindows("openbmi",person,day,catalog_item)
        if source.full is None:
            raise FileNotFoundError(f"Full OpenBMI BDF missing: {key}")
        sha256 = digest(source.full)
        if sha256 != catalog_item["checksum"]:
            raise ValueError(f"OpenBMI BDF fingerprint differs from release: {key}")
        source.old.clear()
        events=np.column_stack((meta["positions"],meta["labels"]))
        wave=waveform.prepare_uv(waveform.raw_uv(source,events,[source.location(pos) for pos in meta["positions"]]))
        arrays={"wave":wave,"y":events[:,1],"selection":events[:,0],
                "cov":waveform.covariance(wave.astype(np.float64)*1000.),
                "status":np.zeros(len(events),dtype=np.int8)}
        if digest(original)!=meta["wave_sha256"]:
            raise ValueError(f"Archived OpenBMI wave panel changed: {key}")
        with np.load(original,allow_pickle=False) as frozen:
            for field in ("y","selection"):
                recorded_dtype=frozen[field].dtype
                native=arrays[field].astype(recorded_dtype)
                np.testing.assert_array_equal(native,arrays[field])
                arrays[field]=native
            matched=verify_arrays(arrays,{name:frozen[name] for name in arrays},key)
        tmp=out.with_suffix(".tmp")
        with tmp.open("wb") as stream:
            np.savez(stream,**arrays)
        tmp.replace(out)
        receipt={"window":key,"original":meta["wave_sha256"],"raw_bdf_sha256":sha256,
                 "new_sha256":digest(out),"arrays_exact":matched}
        save(stamp,receipt)
        receipt_list.append(receipt)
        print(f"OpenBMI BDF → wave and covariance {i}/{len(sessions)} · {key}",flush=True)
    save(folder/("spot_check.json" if limit else "complete.json"),
         {"panel_receipts":receipt_list,"registry_sha256":digest(legacy.REGISTRY)})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", choices=("stieger","netbci","openbmi"))
    parser.add_argument("--all-sessions",action="store_true")
    parser.add_argument("--limit",type=int)
    args=parser.parse_args()
    if args.dataset=="stieger":
        stieger(args.all_sessions)
    elif args.dataset=="netbci":
        netbci()
    else:
        openbmi(args.limit)
