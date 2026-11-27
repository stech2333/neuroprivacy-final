"""Read-only Windows monitor for the official checklist and active reproduction runs."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic

import psutil


ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "manifests" / "acceptance_progress.md"
RUNS = ROOT / "results" / "raw_reproduction"
REFRESH_MS = 2000
SHANGHAI = timezone(timedelta(hours=8))
ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")


@dataclass(frozen=True)
class Acceptance:
    number: int
    label: str
    status: str


@dataclass(frozen=True)
class Work:
    label: str
    current: int
    total: int
    unit: str
    status: str
    detail: str


def read_acceptance(path):
    items = [
        Acceptance(int(match[1]), match[2], match[3])
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if (match := ROW.match(line))
    ]
    if [item.number for item in items] != list(range(1, 17)):
        raise ValueError("验收清单应包含完整的 16 项")
    return items


def read_receipt(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def count_files(folder, pattern):
    return sum(1 for path in folder.glob("*.json") if pattern.fullmatch(path.stem))


def log_tail(path):
    try:
        with path.open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - 4096))
            data = stream.read()
    except OSError:
        return ""
    return next((line.strip() for line in reversed(data.decode("utf-8", errors="replace").splitlines())
                 if line.strip()), "")


def scan_workers(root):
    active = {}
    root_key = str(root).casefold()
    for process in psutil.process_iter(["name"]):
        try:
            if (process.info["name"] or "").casefold() not in {
                "python.exe", "pythonw.exe", "pwsh.exe", "powershell.exe"
            }:
                continue
            args = process.cmdline()
            if "-m" in args:
                index = args.index("-m")
                role = tuple(args[index + 1:index + 3])
                if len(role) == 2 and role[0].startswith("neuroprivacy.") and process.cwd().casefold() == root_key:
                    active[process] = role
            elif any(arg.casefold().endswith("\\continue_reproduction.ps1") for arg in args):
                if "-Dataset" in args:
                    index = args.index("-Dataset")
                    active[process] = ("queue", args[index + 1].casefold())
        except (psutil.Error, IndexError, OSError):
            continue
    return active


def workers(root):
    return set(scan_workers(root).values())


class WorkerProbe:
    """Keep job liveness current without enumerating Windows processes on every UI tick."""

    def __init__(self, root):
        self.root = root
        self.active = {}
        self.next_scan = 0.

    def roles(self):
        now = monotonic()
        if now >= self.next_scan:
            self.active = scan_workers(self.root)
            self.next_scan = now + 30.
        else:
            live = {p: role for p, role in self.active.items() if p.is_running()}
            if len(live) != len(self.active):
                self.next_scan = min(self.next_scan, now + 3.)
            self.active = live
        return set(self.active.values())


def work_snapshot(runs, active):
    def observe(label, progress, total, unit, receipt, running, log=None,
                waiting="", completed_detail="", differing=False, running_detail=""):
        error = log_tail(runs / (log + ".stderr.log")) if log else ""
        latest = log_tail(runs / (log + ".stdout.log")) if log else ""
        if receipt:
            status = "待核对" if differing else "已完成"
            detail = completed_detail or "完成回执已写入"
        elif running:
            status = "运行中"
            detail = error or latest or running_detail or "正在处理"
        elif error:
            status, detail = "日志有异常", error
        elif waiting:
            status, detail = "排队中", waiting
        elif progress == total:
            status, detail = "待核对", "计数已满，等待完成回执"
        else:
            status = "等待核对" if progress else "待启动"
            detail = latest or "等待工作进程或新回执"
        return Work(label, progress, total, unit, status, detail)

    dreyer = runs / "dreyer" / "v47"
    dreyer_comparison = read_receipt(dreyer / "comparison.json")
    pair_pattern = re.compile(r"pair_\d{2}")
    bmi = runs / "openbmi"
    stieger = runs / "stieger"
    bmi_wave = read_receipt(bmi / "complete.json")
    stieger_wave = read_receipt(stieger / "complete.json")
    bmi_eval = bmi / "evaluation"
    stieger_eval = stieger / "evaluation"
    bmi_fits = (("v46_fit", "comparison.json"), ("v48", "result.json"), ("v56", "result.json"))
    stieger_fits = ("v61", "v65", "v68")
    bmi_complete = [stage.upper().replace("_FIT", "") for stage, receipt in bmi_fits
                    if read_receipt(bmi_eval / stage / receipt)]
    stieger_complete = [stage.upper() for stage in stieger_fits
                        if read_receipt(stieger_eval / stage / "provenance.json")]
    net = runs / "netbci"
    net_wave = read_receipt(net / "complete.json").get("run_six_panels", 0)
    net_scored = read_receipt(net / "evaluation" / "provenance.json").get("exact_participant_results", 0)
    net_ready = net_wave == 36 and net_scored == 12 and bool(read_receipt(net / "evaluation" / "controls_C8.json"))
    openbmi_active = ("neuroprivacy.gpu_reproduction", "openbmi") in active
    dreyer_active = ("neuroprivacy.gpu_reproduction", "dreyer") in active
    stieger_active = ("neuroprivacy.raw_eval", "stieger") in active
    stieger_count = count_files(stieger, re.compile(r"S\d+_Session_[23]"))
    bmi_count = count_files(bmi, re.compile(r"\d+_[12]"))
    bmi_comparison = read_receipt(bmi_eval / "v46_fit" / "comparison.json")
    bmi_waiting = ""
    if ("queue", "openbmi") in active:
        if len(bmi_wave.get("panel_receipts", [])) < 96:
            bmi_waiting = "等待波形完成"
        else:
            bmi_waiting = "等待 Dreyer 释放 GPU" if dreyer_active else "等待模型进程接手"
    return [
        observe("Dreyer  ·  V47 重训", count_files(dreyer, pair_pattern), 25, "人对",
                dreyer_comparison.get("coverage") == 25,
                dreyer_active, "dreyer",
                completed_detail="原始波形至模型重训回执已写入",
                differing=dreyer_comparison.get("equal_primary_effects") is False),
        observe("OpenBMI  ·  波形重提取", bmi_count, 96, "会话",
                len(bmi_wave.get("panel_receipts", [])) == 96,
                ("neuroprivacy.raw_panels", "openbmi") in active, "openbmi"),
        observe("OpenBMI  ·  模型复现", len(bmi_complete), 3, "阶段", len(bmi_complete) == 3,
                openbmi_active, "openbmi.evaluation",
                bmi_waiting,
                completed_detail="V46、V48、V56 回执已写入",
                differing=bmi_comparison.get("rerun") != bmi_comparison.get("reference")),
        observe("Stieger  ·  波形重提取", stieger_count, 124, "会话", stieger_wave.get("sessions") == 124,
                ("neuroprivacy.raw_panels", "stieger") in active,
                running_detail="已核对的会话按回执逐个计数"),
        observe("Stieger  ·  模型复现", len(stieger_complete), 3, "阶段", len(stieger_complete) == 3,
                stieger_active, "stieger.evaluation",
                "等待波形完成" if ("queue", "stieger") in active else "",
                completed_detail="V61、V65、V68 复现与比对均完成"),
        observe("NETBCI  ·  波形及评分", net_wave, 36, "评分块", net_ready,
                ("neuroprivacy.raw_panels", "netbci") in active or ("neuroprivacy.raw_eval", "netbci") in active,
                completed_detail=f"{net_scored}/12 人评分与原结果逐项一致，P0–P5 已完成"),
    ]


def launch():
    import tkinter as tk
    from tkinter import font, ttk

    root = tk.Tk()
    root.title("神经数据隐私研究 · 实时进度")
    root.geometry("1080x830")
    root.minsize(850, 690)
    root.configure(bg="#F2F5F9")
    root.option_add("*Font", ("Microsoft YaHei UI", 10))
    row_font = font.Font(root=root, family="Microsoft YaHei UI", size=9)

    ink, muted, accent, paper = "#182D42", "#50667D", "#176B70", "#FFFFFF"
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Horizontal.TProgressbar", background=accent, troughcolor="#DDE7EF",
                    bordercolor="#DDE7EF", lightcolor=accent, darkcolor=accent)
    style.configure("Treeview", rowheight=24, background=paper, fieldbackground=paper, foreground=ink)
    style.configure("Treeview.Heading", background="#E7EEF4", foreground=ink, padding=(7, 5))
    style.map("Treeview", background=[("selected", "#D8E8F0")], foreground=[("selected", ink)])
    style.configure("TButton", padding=(9, 5))

    shell = tk.Frame(root, bg="#F2F5F9", padx=20, pady=14)
    shell.pack(fill="both", expand=True)
    header = tk.Frame(shell, bg="#F2F5F9")
    header.pack(fill="x")
    tk.Label(header, text="神经数据隐私研究", anchor="w", bg="#F2F5F9", fg=ink,
             font=("Microsoft YaHei UI", 19, "bold")).pack(side="left")
    update_text = tk.StringVar()
    tk.Label(header, textvariable=update_text, bg="#F2F5F9", fg=muted).pack(side="right")

    total_card = tk.Frame(shell, bg=paper, padx=13, pady=8)
    total_card.pack(fill="x", pady=(9, 11))
    total_card.columnconfigure(1, weight=1)
    total_text = tk.StringVar()
    tk.Label(total_card, textvariable=total_text, fg=ink, bg=paper, anchor="w",
             font=("Microsoft YaHei UI", 12, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 14))
    total_bar = ttk.Progressbar(total_card, maximum=16, mode="determinate")
    total_bar.grid(row=0, column=1, sticky="ew", pady=5)
    notification = tk.StringVar(value="运行进度来自实验回执，验收数量来自正式清单。")
    tk.Label(total_card, textvariable=notification, fg=accent, bg=paper, anchor="w").grid(
        row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))

    rows = tk.Frame(shell, bg=paper, padx=13, pady=7)
    rows.pack(fill="x")
    rows.columnconfigure(4, weight=1)
    for index, name in enumerate(("复现任务", "状态", "已处理", "进度", "最新回执或日志")):
        tk.Label(rows, text=name, bg=paper, fg=muted, anchor="w",
                 font=("Microsoft YaHei UI", 9, "bold")).grid(row=0, column=index, sticky="ew", padx=(0, 9))
    work_widgets = []
    for index in range(1, 7):
        cells = [tk.Label(rows, bg=paper, fg=ink, anchor="w", font=row_font)
                 for _ in range(4)]
        bar = ttk.Progressbar(rows, length=112, mode="determinate")
        for column, widget in zip((0, 1, 2, 3, 4), (*cells[:3], bar, cells[3]), strict=True):
            widget.grid(row=index, column=column, sticky="ew" if column == 3 else "w", padx=(0, 9), pady=3)
        work_widgets.append((cells, bar))

    checklist_header = tk.Frame(shell, bg="#F2F5F9")
    checklist_header.pack(fill="x", pady=(9, 4))
    tk.Label(checklist_header, text="16 项正式验收", bg="#F2F5F9", fg=ink,
             font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
    ttk.Button(checklist_header, text="查看日志目录", command=lambda: os.startfile(RUNS)).pack(side="right")
    ttk.Button(checklist_header, text="打开验收清单",
               command=lambda: subprocess.Popen(["notepad.exe", str(CHECKLIST)])).pack(side="right", padx=(0, 7))

    table_area = tk.Frame(shell, bg=paper)
    table_area.pack(fill="both", expand=True)
    table = ttk.Treeview(table_area, columns=("id", "phase", "item", "status"), show="headings", height=16)
    scroll = ttk.Scrollbar(table_area, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    table.pack(fill="both", expand=True)
    for field, title, width, stretch in (
        ("id", "编号", 58, False), ("phase", "阶段", 108, False),
        ("item", "验收项", 490, True), ("status", "状态", 135, False),
    ):
        table.heading(field, text=title, anchor="w")
        table.column(field, width=width, minwidth=width if not stretch else 390, stretch=stretch)
    table.tag_configure("passed", foreground=accent)
    table.tag_configure("alternate", background="#F6F8FA")
    phase_names = ("A 协议冻结", "B 工程建设", "C 正式实验", "D 结果定型")
    previous = None
    latest_milestone = notification.get()
    probe = WorkerProbe(ROOT)

    def refresh():
        nonlocal previous, latest_milestone
        now = datetime.now(SHANGHAI).strftime("%H:%M:%S")
        update_text.set(f"北京时间 {now}  ·  每 2 秒刷新")
        try:
            accepted = read_acceptance(CHECKLIST)
        except (OSError, ValueError) as error:
            notification.set(f"验收清单暂不可读 · {error}")
        else:
            completed = {item.number for item in accepted if item.status == "完成"}
            total_text.set(f"正式验收  {len(completed)} / 16")
            total_bar.configure(value=len(completed))
            if previous is not None:
                newly_passed = [item for item in accepted if item.number in completed - previous]
                if newly_passed:
                    latest_milestone = " · ".join(f"第 {item.number} 项通过 · {item.label}" for item in newly_passed)
                    root.bell()
            notification.set(latest_milestone)
            previous = completed
            for item in accepted:
                key = str(item.number)
                tags = tuple(tag for tag, enabled in (("passed", item.status == "完成"),
                                                      ("alternate", item.number % 2 == 0)) if enabled)
                values = (f"{item.number:02d}", phase_names[(item.number - 1)//4], item.label, item.status)
                if table.exists(key):
                    table.item(key, values=values, tags=tags)
                else:
                    table.insert("", "end", iid=key, values=values, tags=tags)

        try:
            progress = work_snapshot(RUNS, probe.roles())
        except (OSError, ValueError) as error:
            notification.set(f"运行回执暂不可读 · {error}")
        else:
            for item, (labels, bar) in zip(progress, work_widgets, strict=True):
                detail = item.detail
                width = max(170, root.winfo_width() - 555) if root.winfo_width() > 1 else 480
                if row_font.measure(detail) > width:
                    while detail and row_font.measure(detail + "…") > width:
                        detail = detail[:-1]
                    detail += "…"
                shown = (item.label, item.status, f"{item.current}/{item.total} {item.unit}", detail)
                for label, value in zip(labels, shown, strict=True):
                    label.configure(text=value)
                labels[1].configure(fg=accent if item.status in {"已完成", "运行中"} else muted)
                bar.configure(maximum=item.total, value=item.current)
        root.after(REFRESH_MS, refresh)

    refresh()
    root.mainloop()


if __name__ == "__main__":
    if sys.argv[1:] == ["--snapshot"]:
        acceptance = read_acceptance(CHECKLIST)
        print(json.dumps({"accepted": sum(row.status == "完成" for row in acceptance),
                          "checklist": [asdict(row) for row in acceptance],
                          "work": [asdict(row) for row in work_snapshot(RUNS, workers(ROOT))]},
                         ensure_ascii=False, indent=2))
    else:
        launch()
