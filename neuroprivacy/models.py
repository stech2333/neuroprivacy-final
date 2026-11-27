"""Resolve registered checkpoints and run existing model-family implementations."""
from dataclasses import dataclass
from pathlib import Path
import os
import subprocess

from .common import M, ROOT, WORK, read, verified

@dataclass(frozen=True)
class Workflow:
    module: str
    arguments: tuple[str, ...]
    gpu: bool = False

    def run(self, runtime):
        env=os.environ.copy()
        env.update(PYTHONUTF8="1",PYTHONDONTWRITEBYTECODE="1",
                   OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",OMP_NUM_THREADS="1")
        if not self.gpu:
            env["CUDA_VISIBLE_DEVICES"]="-1"
        return subprocess.run([str(runtime),"-X","utf8","-s","-u","-m",f"neuroprivacy.{self.module}",*self.arguments],
                              cwd=ROOT,env=env,check=True)

MODEL_WORKFLOWS = {
    "CBraMod": {
        "Dreyer": (Workflow("gpu_reproduction",("dreyer",),gpu=True),),
        "OpenBMI": (Workflow("raw_panels",("openbmi",)),Workflow("gpu_reproduction",("openbmi",),gpu=True),
                    Workflow("openbmi_controls",("--rebuilt",))),
    },
    "TS-LR": {
        "Stieger": (Workflow("raw_panels",("stieger","--all-sessions")),Workflow("raw_eval",("stieger",)),
                    Workflow("fixed_controls",("--rebuilt",))),
        "NETBCI": (Workflow("raw_panels",("netbci",)),Workflow("raw_eval",("netbci",))),
    },
}

def registered_assets():
    return tuple({**asset,"verified_path":verified(WORK/asset["path"],asset["sha256"])}
                 for asset in read(M/"checkpoint_registry.json")["assets"])

def workflow(family, dataset):
    try:
        return MODEL_WORKFLOWS[family][dataset]
    except KeyError as exc:
        raise ValueError(f"Unregistered model workflow: {family} / {dataset}") from exc
