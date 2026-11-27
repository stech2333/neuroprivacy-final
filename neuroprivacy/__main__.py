import argparse
import os
from pathlib import Path
from .audit import audit
from .replay import replay
from .report import generate
from .data import load_cohorts
from .models import MODEL_WORKFLOWS, workflow

def reproduce(options):
    cohorts=load_cohorts()
    runtime=Path(options.runtime)
    if not runtime.is_file():
        raise FileNotFoundError(f"Original deep-gpu runtime not found: {runtime}")
    registered={name:family for family, entries in MODEL_WORKFLOWS.items() for name in entries}
    selected=("NETBCI","Stieger","Dreyer","OpenBMI") if options.dataset=="all" else (options.dataset,)
    for dataset in selected:
        print(f"{dataset} {registered[dataset]} · {cohorts[dataset].coverage()}",flush=True)
        for step in workflow(registered[dataset],dataset):
            step.run(runtime)

def main():
    cli=argparse.ArgumentParser(description="Frozen neuroprivacy protocol and completed Phase A checks")
    args=cli.add_subparsers(dest="mode",required=True)
    a=args.add_parser("audit",help="Verify the frozen ledgers and offline rerun receipts")
    a.add_argument("--full",action="store_true",help="Rehash every Phase 0 workspace file in the inventory")
    r=args.add_parser("replay",help="Recalculate K1–K5 and validate the separate K6 receipt")
    r.add_argument("--experiment",choices=["all"],default="all")
    r.add_argument("--source", choices=("auto","archive","raw"),default="auto",
                   help="Use verified raw-data reruns when available, or select the evidence source")
    raw=args.add_parser("reproduce",help="Repeat the registered raw-data evaluation workflows")
    raw.add_argument("--experiment",choices=["all"],default="all")
    raw.add_argument("--dataset",choices=("all","NETBCI","Stieger","Dreyer","OpenBMI"),default="all")
    raw.add_argument("--runtime",default=os.environ.get("NEUROPRIVACY_LEGACY_PYTHON","E:/Python/envs/deep-gpu/python.exe"))
    report=args.add_parser("report",help="Produce an aggregate report from the current receipts")
    report.add_argument("--figures",action="store_true",help="Also render the four figures from the current aggregate data")
    options=cli.parse_args()
    if options.mode=="audit":
        print(audit(options.full)["baseline"])
    elif options.mode=="replay":
        audit()
        from .acceptance import verify_raw_results
        from .common import ROOT
        raw=options.source=="raw" or (options.source=="auto" and (ROOT/"results/raw_reproduction_audit.json").is_file())
        if raw:
            verify_raw_results()
        primary=replay(raw=raw)["primary"]
        for key,item in primary.items():
            print(f"{key}  Holm p = {item['holm_p']:.8g}")
    elif options.mode=="reproduce":
        reproduce(options)
    else:
        print(generate())
        if options.figures:
            from .figures import main as figures
            figures()

if __name__=="__main__":
    main()
