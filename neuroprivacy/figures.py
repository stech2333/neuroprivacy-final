"""Draw the four protocol figures and their aggregate source data."""
import csv

import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

from .common import ROOT, read, verified

OUT = ROOT / "figures" / "staging"
DATA = ROOT / "results"
NAVY = "#254F75"
TEAL = "#278778"
INK = "#202F3E"
GRAY = "#70808D"
LIGHT = "#EDF3F6"
ORANGE = "#A9623E"
mpl.rcParams.update({
    "font.family":"sans-serif", "font.sans-serif":["Arial","DejaVu Sans"],
    "font.size":7, "axes.titlesize":8, "axes.labelsize":7, "axes.titleweight":"semibold",
    "axes.spines.right":False, "axes.spines.top":False, "axes.linewidth":0.65,
    "text.color":INK, "axes.labelcolor":INK, "xtick.color":INK, "ytick.color":INK,
    "pdf.fonttype":42, "svg.fonttype":"none", "legend.frameon":False,
})

def panel(axes, letter, title):
    axes.set_title(f"{letter}   {title}",loc="left",pad=8)
    axes.set_axisbelow(True)

def diagram(ax, rows, major_color=NAVY):
    ax.set_xlim(0,1)
    ax.set_ylim(0,1)
    ax.axis("off")
    for i,(key,text) in enumerate(rows):
        y=1-(i+.5)/len(rows)
        ax.text(.03,y,key,ha="left",va="center",fontweight="bold",color=major_color,
                bbox={"boxstyle":"round,pad=.36","facecolor":LIGHT,"edgecolor":"none"})
        ax.text(.35,y,text,ha="left",va="center",linespacing=1.28)

class Figure:
    def __init__(self, number, height):
        self.number=number
        self.fig,self.axes=plt.subplots(2,2,figsize=(183/25.4,height/25.4),layout="constrained",
                                      gridspec_kw={"width_ratios":[.86,1.14]})
        self.axes=self.axes.ravel()
        self.source=[]

    def point(self, ax, label, records, unit, margin=0):
        ax.axvline(margin,color="#A8B4BF",lw=.8,ls="--")
        for pos,(name,value,lo,hi,n,color,source) in enumerate(records):
            ax.hlines(pos,lo,hi,color=color,lw=1.1)
            ax.scatter(value,pos,s=19,color=color,zorder=3)
            self.source.append((label,name,value,lo,hi,n,unit,source))
        ax.yaxis.set_ticks(range(len(records)),[record[0] for record in records])
        ax.set_ylim(len(records)-.55,-.45)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y",length=0,pad=5)
        ax.grid(axis="x",lw=.45,color="#E3EAF0")
        ax.set_xlabel(unit)

    def save(self):
        base=OUT/f"fig{self.number}"
        for extension in ("svg","pdf","png"):
            self.fig.savefig(base.with_suffix("."+extension),dpi=300,facecolor="white",bbox_inches="tight",pad_inches=.04)
        with base.with_suffix(".csv").open("w",newline="",encoding="utf-8") as file:
            out=csv.writer(file)
            out.writerow(("panel","comparison","estimate","lower_97_5","upper_97_5","n","unit","source"))
            out.writerows(self.source)
        plt.close(self.fig)

def datum(name, item, interval, n, color, source, sign=1, scale=1):
    lo,hi=sorted(v*sign*scale for v in item[interval])
    return name,item["mean"]*sign*scale,lo,hi,n,color,source

def exposure(primary,support):
    f=Figure(1,105)
    a,b,c,d=f.axes
    panel(a,"a","Controlled record roles")
    diagram(a,[("H  In train","Actual training records"),("W  Same day","Held-out records, same session"),("R  Later day","Held-out records, later session")])
    panel(b,"b","Actual training records show stronger concordance")
    f.point(b,"b",[
        datum("Dreyer · 25 pairs",primary["K1"],"bootstrap_ci97_5",25,NAVY,"V47 adapted",scale=100),
        datum("OpenBMI · 18 pairs",support["v46_fit/H_minus_W_concordance"],"bootstrap_ci97_5",18,TEAL,"V46 adapted",scale=100),
        datum("Stieger · 21 pairs",support["v65/H_minus_W_concordance"],"bootstrap_ci97_5",21,TEAL,"V65 block-disjoint",scale=100),
    ],"H − W (percentage points)")
    panel(c,"c","Interaction with adaptation depth")
    f.point(c,"c",[
        datum("Dreyer",primary["K2"],"bootstrap_ci97_5",25,NAVY,"V47",scale=100),
        datum("OpenBMI",support["v46_fit/adaptation_interaction"],"bootstrap_ci97_5",18,TEAL,"V46",scale=100),
    ],"Adapted − frozen H − W (pp)")
    panel(d,"d","The held-out cross-day contrast remains uncertain")
    f.point(d,"d",[
        datum("OpenBMI",support["v46_fit/W_minus_R_concordance"],"bootstrap_ci97_5",18,TEAL,"V46 adapted",scale=100),
        datum("Stieger",support["v65/W_minus_R_concordance"],"bootstrap_ci97_5",21,TEAL,"V65 block-disjoint",scale=100)
    ],"W − R (percentage points)")
    f.save()

def utility(primary,net,openbmi):
    f=Figure(2,104)
    a,b,c,d=f.axes
    panel(a,"a","Equal-budget history comparison")
    diagram(a,[("U0","Same-day calibration only"),("U1","Own H40 and same-day calibration"),
               ("U2","Partner H40 and same-day calibration")])
    panel(b,"b","Incremental value of own history")
    f.point(b,"b",[
        datum("Stieger C8 · 22 pairs",primary["K3"],"t_ci97_5",22,NAVY,"V68 C8",scale=1000),
        datum("OpenBMI C20 · 18 pairs",openbmi["history_effects"]["own_minus_P0"]["Brier"],"pair_t_ci",18,TEAL,"OpenBMI registered C20",sign=-1,scale=1000),
        datum("NETBCI C8 · 12 people",net["primary_rank4_minus_background_C8"],"ci97_5",12,GRAY,"V67 C8 Days 2–4",sign=-1,scale=1000),
    ],r"Brier reduction vs no history ($\times 10^{-3}$)")
    panel(c,"c","History and evaluation windows")
    diagram(c,[("OpenBMI","Day 1  →  Day 2"),("Stieger","Session 2  →  Session 3"),
               ("NETBCI","Day 1  →  Days 2, 3, 4"),("Reference","Same person, calibration and test set")],TEAL)
    panel(d,"d","Specific value of own history")
    f.point(d,"d",[
        datum("Stieger C8 · 22 pairs",primary["K4"],"t_ci97_5",22,NAVY,"V68 C8",scale=1000),
        datum("OpenBMI C20 · 18 pairs",openbmi["history_effects"]["own_minus_U2"]["Brier"],"pair_t_ci",18,TEAL,"OpenBMI registered C20",sign=-1,scale=1000),
        datum("NETBCI C8 · 6 pairs",net["pooled_subject_first"]["8"]["own_minus_paired_history"]["Brier"],"pair_t_ci",6,GRAY,"V67 C8 Days 2–4",sign=-1,scale=1000)
    ],r"Brier reduction vs partner history ($\times 10^{-3}$)")
    f.save()

def protection(primary,controls):
    f=Figure(3,112)
    a,b,c,d=f.axes
    panel(a,"a","Local personalization")
    diagram(a,[("Background","Fit representation and task head"),("Release","Fixed head and curvature summary"),
               ("Device","Fit with H40, then calibrate locally"),("Evaluation","Score held-out U independently")])
    panel(b,"b","Stieger C8 clears all three required margins")
    names={"delta_BA":"Balanced accuracy","delta_Brier":"Brier score","MAE":"Prediction MAE"}
    denominators={"delta_BA":.03,"delta_Brier":.005,"MAE":.01}
    signs={"delta_BA":1,"delta_Brier":-1,"MAE":-1}
    rows=[]
    for label,item in primary["K5"]["components"].items():
        den,direction=denominators[label],signs[label]
        shift=item["null_boundary"]
        shifted={"mean":item["mean"]-shift,"t_ci97_5":[p-shift for p in item["t_ci97_5"]]}
        rows.append(datum(names[label],shifted,"t_ci97_5",22,NAVY,"V68 C8",sign=direction,scale=1/den))
    f.point(b,"b",rows,"Distance above acceptance boundary / margin")
    panel(c,"c","Structured background approximation")
    diagram(c,[("Anchor","Background optimum"),("Low rank","Retain dominant curvature directions"),
               ("Diagonal","Correct discarded coordinate curvature"),("Exact head","Match frozen representation and budgets")],TEAL)
    panel(d,"d","Approximation error and storage")
    d.set_xscale("log")
    d.set_yscale("log")
    d.axhline(.01,color="#A8B4BF",ls="--",lw=.8)
    for code,label,color,offset in (("P2","isotropic",GRAY,(5,5)),("P3","diagonal",GRAY,(4,5)),
                                   ("P4","full",TEAL,(-8,7)),("P5","rank 16",NAVY,(6,-12))):
        row=controls["metrics"][code]
        size,mae=row["curvature_array_bytes"],row["MAE"]["pair_t_ci"][1]
        d.scatter(size,mae,s=23,color=color,zorder=3)
        d.annotate(label,(size,mae),xytext=offset,textcoords="offset points",
                   ha="right" if code=="P4" else "left",color=color)
        f.source.append(("d",label,mae,None,None,22,f"97.5% upper MAE · {size} array bytes","Stieger fixed C8 P0–P5"))
    d.set_xlabel("Curvature array bytes")
    d.set_ylabel("Upper prediction MAE")
    d.set_ylim(1.7e-4,2.8e-2)
    d.grid(axis="y",lw=.45,color="#E3EAF0")
    f.save()

def isolation(audit,support):
    f=Figure(4,112)
    a,b,c,d=f.axes
    panel(a,"a","Four learning locations")
    diagram(a,[("M0","Frozen pretrained representation"),("M1","Target history in shared encoder"),
               ("M2","Target history in shared task head"),("M3","Target history in local task head")])
    panel(b,"b","Shared output stays fixed when history changes")
    rows=[]
    names={"openbmi":"OpenBMI","stieger":"Stieger"}
    for key,value in audit["cached_runs"]["K6"].items():
        local=value["local_probability_MAE_after_history_swap"]
        shared=value["shared_prediction_max_drift"]
        rows.append((names[key],local,shared))
    y=np.arange(len(rows))
    b.barh(y,[row[1] for row in rows],height=.29,color=NAVY)
    b.scatter([row[2] for row in rows],y,s=23,facecolor="white",edgecolor=TEAL,zorder=4,clip_on=False)
    for i,(name,local,shared) in enumerate(rows):
        b.text(local+.0006,i,f"{local:.4f}",va="center",color=NAVY)
        f.source.extend([("b",name+" local",local,None,None,None,"local mean absolute change","V51"),
                         ("b",name+" shared",shared,None,None,None,"shared maximum drift","V51")])
    b.set_yticks(y,[row[0] for row in rows])
    b.set_ylim(len(rows)-.54,-.48)
    b.set_xlim(0,.038)
    b.set_xlabel("Absolute prediction change · open marker = shared")
    b.tick_params(axis="y",length=0)
    panel(c,"c","Offline reference workflow checks")
    diagram(c,[("Persist","Save, reload and recover"),("Retry","Repeated commit is idempotent"),
               ("Clear","Remove device-specific head"),("Egress","Exercise guard and simulated sync")],TEAL)
    panel(d,"d","The full shared encoder remains a harder reference")
    records=[]
    for panel_name,label in (("v48/M3_vs_M1","V48 · matched head"),("v56/M3_vs_M1_Platt","V56 · Platt calibrated")):
        records.append(datum(label,support[panel_name]["Brier"],"t_ci97_5",18,ORANGE,panel_name,scale=1000))
    f.point(d,"d",records,r"Local M3 − shared M1 Brier ($\times 10^{-3}$)",margin=5)
    f.save()

def main():
    global OUT
    replay=read(DATA/"primary_statistics.json")
    audit=read(DATA/"audit.json")
    if "raw_reproduction_audit_sha256" in replay:
        verified(DATA/"raw_reproduction_audit.json",replay["raw_reproduction_audit_sha256"])
        verified(DATA/"audit.json",replay["offline_audit_sha256"])
        OUT=ROOT/"figures/final"
    else:
        OUT=ROOT/"figures/staging"
    OUT.mkdir(parents=True,exist_ok=True)
    raw=DATA/"raw_reproduction"
    openbmi=read(sorted((raw/"openbmi_controls").glob("*/result.json"))[-1])
    net=read(raw/"netbci/evaluation/v67_aggregate.json")
    stieger=read(sorted((DATA/"stieger_C8_controls").glob("*/result.json"))[-1])
    exposure(replay["primary"],replay["supporting"])
    utility(replay["primary"],net,openbmi)
    protection(replay["primary"],stieger)
    isolation(audit,replay["supporting"])
    print(f"All four figures written to {OUT}")

if __name__=="__main__":
    main()
