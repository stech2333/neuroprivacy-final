"""Materialize the original panel and cohort roles at their native coordinate resolution."""
import csv
import hashlib
from collections import Counter
import numpy as np
from .common import M, OLD, one, read, sha, verified, check, name, table, write_json

def quota(y, pool, each):
    selected = np.sort(np.concatenate([pool[y[pool] == label][:each] for label in (0, 1)]))
    check(len(selected) == 2*each, "Quota mismatch")
    return selected

def build():
    participants, trials, cohorts = [], [], {}
    def roster(dataset, path, roles, pairs, expected):
        ids = [str(p) for group in roles.values() for p in group]
        check(len(ids) == len(set(ids)) == expected, f"{dataset} participant role overlap")
        flat = [str(p) for pair in pairs for p in pair]
        check(set(flat) == set(map(str,roles["evaluation"])) and len(flat) == len(set(flat)), "Invalid pair map")
        order = {p: i for i, pair in enumerate(pairs, 1) for p in pair}
        for role, people in roles.items():
            participants.extend((dataset, str(p), role, order.get(p, ""), name(path)) for p in people)
        cohorts[dataset] = {"source":name(path), "sha256":sha(path), "role_counts":{k:len(v) for k,v in roles.items()},
                            "original_pairs":len(pairs)}
    def panel(dataset, recipe, person, session, groups, kind, source, variant=""):
        seen=set()
        for role, entries in groups.items():
            for index, label in entries:
                check(index not in seen, f"Duplicate trial within {dataset}/{recipe}/{person}/{session}/{variant}")
                seen.add(index)
                trials.append((dataset, recipe, person, session, variant, role, kind, int(index), int(label), name(source)))
    def indexed(y, groups):
        return {k:[(int(i),int(y[i])) for i in v] for k,v in groups.items()}
    registry = one("run_v11*/registration.json")
    o = read(registry)
    roles = dict(o["roles"])
    roles["evaluation"] = roles.pop("confirmation")
    roster("OpenBMI", registry, roles, o["pairs"], 54)
    old = one("*/v46_ledger/trial_roles.json")
    s = read(verified(old, read(old.with_name("result.json"))["trial_roles_sha256"]))
    verified(registry, s["v11"])
    for p in roles["evaluation"]:
        for day in (1,2):
            item = o["windows"][f"{p}_{day}"]
            groups = {k:[(item["positions"][i],item["labels"][i]) for i in v] for k,v in item["groups"].items()}
            panel("OpenBMI","V11 H40",p,day,groups,"sample",registry)
            if day==2:
                panel("OpenBMI","V46 H20",p,day,groups,"sample",registry)
        row=s["panels"][str(p)]
        check(all(Counter(x[1] for x in row[k]) == {0:10,1:10} for k in ("H","W")),"H/W quota")
        panel("OpenBMI","V46 H20",p,1,{k:row[k] for k in ("H","W")},"sample",old)
    dfile = one("*/dreyer_a1/participant_roles.json")
    lock = read(one("*/v47/protocol_lock.json"))
    d = read(verified(dfile,read(one("*/v47/registration.json"))["sources_sha256"]["participant_roles.json"]))
    roster("Dreyer",dfile,{"development":d["original_development"],"background":d["a1"],"evaluation":d["a2"],
                          "reserve":d["technical_reserve"]},lock["sealed_pairs"],87)
    cache=one("*/v47_assets/verified_recordings")
    manifest=verified(one("*/dreyer/manifest.json"),lock["source_manifest_sha256"])
    catalog={row["path"].split("/")[-1]:row for row in read(manifest) if row["path"].startswith("sub-")}
    for ordinal,p in enumerate(d["a2"]):
        for run in (1,2):
            (events,) = cache.glob(f"{p}_*R{run}acquisition*_events.tsv")
            raw=events.read_bytes()
            metadata=catalog[events.name]
            checksum=hashlib.sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest() if metadata["checksum_algorithm"]=="git" else hashlib.sha256(raw).hexdigest()
            check(checksum==metadata["checksum"] and len(raw)==metadata["size"],"Dreyer event source checksum")
            with events.open(encoding="utf-8-sig", newline="") as stream:
                entries=[(int(row["sample"]),int(row["trial_type"]=="right_hand")) for row in csv.DictReader(stream,delimiter="\t") if row["trial_type"] in ("left_hand","right_hand")]
            check(Counter(y for _,y in entries)=={0:20,1:20},"Dreyer panel coverage")
            if run==1:
                y=np.array([label for _, label in entries])
                rng=np.random.default_rng([lock["split_seed"],ordinal])
                perms=[rng.permutation(np.flatnonzero(y==label)) for label in (0,1)]
                groups={role:[entries[i] for i in np.sort(np.concatenate([a[start:start+10] for a in perms]))]
                        for start,role in ((0,"H"),(10,"W"))}
            else:
                groups={"U":entries}
            panel("Dreyer","V47",p,f"R{run}",groups,"sample",events)
    reg=one("run_v6/stieger_registration.json")
    st=read(reg)["roles"]
    target=st["confirmation"]
    pairs=list(zip(target[::2],target[1::2],strict=True))
    roster("Stieger",reg,{"development":st["development"],"background":st["background"],"evaluation":target},pairs,62)
    lock=read(one("*/v65/block_lock.json"))
    verified(reg,lock["background_roles_sha256"])
    v61=read(verified(one("*/v61/allocation.json"),lock["V61_trial_allocation_sha256"]))
    check(lock["seeds"]==v61["seeds"],"Stieger seeds changed")
    cache=one("*/stieger_v18")
    for i,p in enumerate(target):
        pair=i//2+1
        spl=v61["anonymous_pair_positions"][pair-1]
        check(spl["pair_ordinal"]==pair,"Stieger pair order")
        for day in (2,3):
            src=cache/f"S{p}_Session_{day}.npz"
            verified(src,read(src.with_suffix(".json"))["panel_sha256"])
            with np.load(src,allow_pickle=False) as arr:
                y,run=arr["y"],arr["run"]
            all_ix=np.arange(len(y))
            if day==2:
                fixed={"H":quota(y,all_ix,20)}
            else:
                c20=quota(y,all_ix[run<3],10)
                fixed={"C":quota(y,c20,4),"U":quota(y,all_ix[run>=3],20)}
            panel("Stieger","V68 C8",p,day,indexed(y,fixed),"cache_row",src)
            for j,seed in enumerate(v61["seeds"]):
                saved=spl["splits"][j*2+i%2]
                keys=("H","W") if day==2 else ("U","R")
                original={k:saved[k] for k in keys}
                panel("Stieger","V61 interleaved",p,day,indexed(y,original),"cache_row",src,f"{seed}:base")
                if pair not in lock["accepted_original_pair_ordinals"]:
                    continue
                groups=original if day==3 else {"H":quota(y,all_ix[run<3],10),"W":quota(y,all_ix[run>=3],10)}
                panel("Stieger","V65 blocks",p,day,indexed(y,groups),"cache_row",src,f"{seed}:base")
    nr=one("*/v55_prepare/roles_lock.json")
    n=read(verified(nr,read(one("*/v67_prepare/protocol_lock.json"))["role_sha256"]))
    target=n["evaluation"]
    roster("NETBCI",nr,{k:n[k] for k in ("background","evaluation")},list(zip(target[::2],target[1::2],strict=True)),19)
    for folder in ("v63_prepare","v67_prepare"):
        listing=one(f"*/{folder}/panels.json")
        for row in read(verified(listing,read(listing.with_name("result.json"))["panel_list_sha256"])):
            src=listing.with_name(row["file"])
            verified(src,row.get("source_sha256") or row["sha256"])
            p=target[row["ordinal"]]
            with np.load(src,allow_pickle=False) as arr:
                if folder=="v63_prepare":
                    y=arr["H_y"]
                    check(len(y)==40,"NETBCI H40")
                    panel("NETBCI","V67 C8",p,"day1/run1+2",indexed(y,{"H":range(len(y))}),"H_array_row",src)
                else:
                    for role,run in (("C",1),("U",6)):
                        y=arr[f"{role}_y"]
                        take=quota(y,np.arange(len(y)),4) if role=="C" else np.arange(len(y))
                        check(len(take)==(8 if role=="C" else 20),"NETBCI panel size")
                        panel("NETBCI","V67 C8",p,f"day{row['day']}/run{run}",indexed(y,{role:take}),f"{role}_array_row",src)
    table(M/"participant_roles.csv",["dataset","participant","role","pair_ordinal","source"],participants)
    table(M/"trial_roles.csv",["dataset","recipe","participant","session_or_block","seed_and_orientation","role","coordinate_system","index","label","source"],trials)
    write_json(M/"dataset_registry.json",cohorts)
    return len(participants),len(trials)
