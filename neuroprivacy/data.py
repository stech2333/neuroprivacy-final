"""Read the four locked evaluation ledgers through the same data interface."""
import csv
from dataclasses import dataclass
from collections import Counter

from .common import M, read, check

@dataclass(frozen=True)
class Cohort:
    name: str
    participant_roles: tuple[dict, ...]
    trials: tuple[dict, ...]
    source: dict

    def panels(self, recipe):
        rows=tuple(row for row in self.trials if row["recipe"]==recipe)
        if not rows:
            raise ValueError(f"Unknown registered recipe for {self.name}: {recipe}")
        return rows

    def coverage(self):
        return {"people":dict(Counter(row["role"] for row in self.participant_roles)),
                "recipe_allocations":dict(Counter(row["recipe"] for row in self.trials))}

def load_cohorts():
    registry=read(M/"dataset_registry.json")
    names=("OpenBMI","Dreyer","Stieger","NETBCI")
    check(set(registry)==set(names),"The data registry differs from the four frozen cohorts")
    with (M/"participant_roles.csv").open(encoding="utf-8-sig",newline="") as stream:
        participants=list(csv.DictReader(stream))
    with (M/"trial_roles.csv").open(encoding="utf-8-sig",newline="") as stream:
        trials=list(csv.DictReader(stream))
    cohorts={}
    for dataset in names:
        roles=tuple(r for r in participants if r["dataset"]==dataset)
        records=tuple(r for r in trials if r["dataset"]==dataset)
        by_person={r["participant"]:r["role"] for r in roles}
        check(len(by_person)==len(roles) and all(by_person.get(r["participant"])=="evaluation" for r in records),
              f"Participant role ledger mismatch for {dataset}")
        cohort=Cohort(dataset,roles,records,registry[dataset])
        check(cohort.coverage()["people"]==registry[dataset]["role_counts"],f"Frozen coverage mismatch for {dataset}")
        cohorts[dataset]=cohort
    return cohorts
