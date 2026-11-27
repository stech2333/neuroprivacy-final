"""Write an aggregate research status report from the latest verified evidence."""
from .common import ROOT, read, table

def generate():
    out=ROOT/"results"
    primary=read(out/"primary_statistics.json")
    audit=read(out/"audit.json")
    body=["# 统一结果表","",
          "K1–K5 以原登记的独立人对为单位，按冻结统计细则做单侧 t 检验和 Holm 校正。表中保留 97.5% 双侧区间。K6 按离线工程回执判定。",
          "","| 检验 | 均值 | 97.5% 区间 | Holm p | 判定 |","|---|---:|---|---:|---|"]
    for key,item in primary["primary"].items():
        if key=="K5":
            for label,component in item["components"].items():
                lo,hi=component["t_ci97_5"]
                body.append(f"| {key} {label} | {component['mean']:.6g} | [{lo:.6g}, {hi:.6g}] | {item['holm_p']:.6g}（联合） | {item['status']} |")
        else:
            lo,hi=item["bootstrap_ci97_5" if key in ("K1","K2") else "t_ci97_5"]
            body.append(f"| {key} | {item['mean']:.6g} | [{lo:.6g}, {hi:.6g}] | {item['holm_p']:.6g} | {item['status']} |")
    for cohort,info in audit["cached_runs"]["K6"].items():
        body.append(f"| K6 {cohort} | 共享预测最大漂移 {info['shared_prediction_max_drift']:.0f} | — | — | 受测离线路径通过 |")
    body.extend(["","## 数据至结果复现",""])
    raw=out/"raw_reproduction"
    if "raw_reproduction_audit_sha256" in primary:
        raw_info=read(out/"raw_reproduction_audit.json")
        auc=raw_info["fixed_model_ancillary"]
        lo, hi=auc["bootstrap_ci95"]
        body.extend(["","固定 OpenBMI 模型的附属历史结果来自 V29b 和 V36 CPU 复算。"
                     f"在重用的 H40 窗口上，ROC-AUC 为 {auc['roc_auc']:.4f}，95% 区间 [{lo:.4f}, {hi:.4f}]。"
                     "该对照的两组样本数为 12 和 36。"
                     "[复现核对与来源指纹](raw_reproduction_audit.json)",""])
    body.extend(["| 队列 | 已有回执 |","|---|---|"])
    milestones={"Stieger":("stieger/complete.json","stieger/evaluation/v68/provenance.json"),
                "Dreyer":("dreyer/v47/comparison.json",),
                "OpenBMI":("openbmi/complete.json","openbmi/evaluation/v46_fit/comparison.json","openbmi/evaluation/v48/result.json","openbmi/evaluation/v56/result.json"),
                "NETBCI":("netbci/complete.json","netbci/evaluation/v67_aggregate.json","netbci/evaluation/controls_C8.json")}
    for cohort,files in milestones.items():
        current=[f"[{path.split('/')[-2]} / {path.split('/')[-1]}](raw_reproduction/{path})"
                 for path in files if (raw/path).is_file()]
        body.append(f"| {cohort} | {' · '.join(current) if current else '等待本轮原始数据复现回执'} |")
    location=primary["supporting"].get("v56/M3_vs_M1_Platt")
    if location:
        ba, brier=location["BA"],location["Brier"]
        body.extend(["","## 完整共享深层适配边界",
                     "",f"OpenBMI V56 原 18 个人对的 Platt 校准复算中，本地 M3 相对完整共享深层适配 M1 的 BA 差为 {100*ba['mean']:+.3f} 个百分点，Brier 差为 {brier['mean']:+.6f}。",
                     f"BA 的 97.5% 区间下界为 {100*ba['t_ci97_5'][0]:+.3f} 个百分点，Brier 区间上界为 {brier['t_ci97_5'][1]:+.6f}。联合非劣{'通过' if location['joint_noninferior'] else '未通过'}。"])
    net=raw/"netbci/evaluation/controls_C8.json"
    if net.is_file():
        methods=read(net)
        verdicts=methods["summary"]["verdicts"]
        body.extend(["","## NETBCI C8 等预算曲率对照","",
                     "| 方法 | 联合非劣 | 预测 MAE 区间上界 | 曲率数组字节数 |",
                     "|---|---|---:|---:|"])
        for arm,record in verdicts.items():
            value=methods["summary"]["arms"][arm]["probability_mae"]["ci97_5"][1]
            body.append(f"| {arm} | {'通过' if record['joint_noninferiority'] else '未通过'} | {value:.6g} | {methods['curvature_array_bytes'][arm]:,} |")
        body.extend(["","同一批 12 名参与者先在人内汇总三个日期。V67 C8 历史效用区间仍跨零。"])
    cached=sorted((raw/"openbmi_controls").glob("*/result.json"))
    if cached:
        v=read(cached[-1])
        body.extend(["","## OpenBMI C20 等预算对照","",
                     "18 个人对。三个种子先在人内汇总，再按原人对计算区间。所有对照使用各目标当天的 C20 和 U20。",
                     "","| 对照 | 本人秩 8 减对照的 Brier | 历史 97.5% 人对 t 区间 |",
                     "|---|---:|---|"])
        for contrast,label in (("own_minus_P0","仅当天校准"),("own_minus_U2","等量匹配者历史")):
            item=v["history_effects"][contrast]["Brier"]
            lo,hi=item["pair_t_ci"]
            body.append(f"| {label} | {item['mean']:.6g} | [{lo:.6g}, {hi:.6g}] |")
        source_description=("从原始波形重建的固定前缀" if "raw_panels_sha256" in v else "V49 冻结前缀")
        body.extend(["",f"补充对照使用{source_description}与原背景检查点。[完整指标]({cached[-1].relative_to(out).as_posix()})"])
        export_tables(out,primary,audit,read(net),v)
    body.extend(["","[队列汇总表](table1_cohorts.csv) · [方法比较与资源表](table2_methods.csv) · [验收进度](../manifests/acceptance_progress.md)",""])
    target=out/"report.md"
    target.write_text("\n".join(body),encoding="utf-8")
    return target

def export_tables(out, replay, audit, net, openbmi):
    """Export the protocol's two aggregate tables without trial-level information."""
    p=replay["primary"]
    s=replay["supporting"]
    net_utility=read(out/"raw_reproduction/netbci/evaluation/v67_aggregate.json")["primary_rank4_minus_background_C8"]
    openbmi_utility=openbmi["history_effects"]["own_minus_P0"]["Brier"]
    table(out/"table1_cohorts.csv",
          ["cohort","registered_people","risk_model","risk_n_pairs","H_minus_W_mean",
           "adaptation_interaction_mean","utility_model","utility_n","own_minus_day_only_Brier_mean","offline_K6"],
          [("Dreyer",87,"CBraMod, last three blocks",25,p["K1"]["mean"],p["K2"]["mean"],"","","",""),
           ("OpenBMI",54,"CBraMod, last three blocks",18,s["v46_fit/H_minus_W_concordance"]["mean"],
            s["v46_fit/adaptation_interaction"]["mean"],"CBraMod, rank-8 local head","18 pairs",openbmi_utility["mean"],
            audit["cached_runs"]["K6"]["openbmi"]["status"]),
           ("Stieger",62,"TS-LR, separated acquisition blocks",21,s["v65/H_minus_W_concordance"]["mean"],"",
            "TS-LR, rank-16 local head","22 pairs",-p["K3"]["mean"],audit["cached_runs"]["K6"]["stieger"]["status"]),
           ("NETBCI",19,"","","","","TS-LR, rank-4 local head","12 people across three days",net_utility["mean"],"")])
    stieger=read(sorted((out/"stieger_C8_controls").glob("*/result.json"))[-1])
    rows=[]
    for code,name in stieger["methods"].items():
        row=stieger["metrics"][code]
        rows.append(("Stieger","C8",code,name,row["BA"]["mean"],row["Brier"]["mean"],
                     row.get("MAE",{}).get("pair_t_ci",[None,None])[1],row.get("curvature_array_bytes"),
                     row["head_fit_seconds"]["mean"],row.get("parameter_L2",{}).get("mean"),row.get("BA_Brier_MAE_pass")))
    for code,name in openbmi["methods"].items():
        if code=="U2":
            continue
        row=openbmi["arms"][code]
        rows.append(("OpenBMI","C20",code,name,row["BA"]["mean"],row["Brier"]["mean"],
                     row.get("prediction_MAE",{}).get("pair_t_ci",[None,None])[1],openbmi["curvature_array_bytes"].get(code),
                     row["head_seconds"]["mean"],row.get("parameter_L2",{}).get("mean"),row.get("BA_Brier_MAE_pass")))
    for code,name in net["method_labels"].items():
        row=net["summary"]["arms"][name]
        gates=net["summary"]["verdicts"].get(name)
        resources=net.get("resources",{}).get(name,{})
        passed=gates["joint_noninferiority"] and gates["probability_near_exact"] if gates else None
        rows.append(("NETBCI","C8",code,name,row["BA"]["mean"],row["Brier"]["mean"],
                     row.get("probability_mae",{}).get("ci97_5",[None,None])[1],net["curvature_array_bytes"].get(name),
                     resources.get("head_seconds"),resources.get("parameter_L2"),passed))
    table(out/"table2_methods.csv",
          ["cohort","calibration","arm","method","mean_BA","mean_Brier","prediction_MAE_upper_97_5",
           "curvature_array_bytes","mean_head_fit_seconds","mean_parameter_L2_vs_P1","BA_Brier_and_MAE_gates"],rows)
