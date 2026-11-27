# 统一结果表

K1–K5 以原登记的独立人对为单位，按冻结统计细则做单侧 t 检验和 Holm 校正。表中保留 97.5% 双侧区间。K6 按离线工程回执判定。

| 检验 | 均值 | 97.5% 区间 | Holm p | 判定 |
|---|---:|---|---:|---|
| K1 | 0.46 | [0.4, 0.506667] | 6.86865e-15 | Supported |
| K2 | 0.386667 | [0.293333, 0.473333] | 2.41738e-09 | Supported |
| K3 | 0.00375194 | [0.000526883, 0.00697701] | 0.0105342 | Supported |
| K4 | 0.00349758 | [7.63969e-05, 0.00691876] | 0.0111371 | Supported |
| K5 delta_BA | 0.00397727 | [-0.00355262, 0.0115072] | 1.0759e-07（联合） | Non-inferior |
| K5 delta_Brier | -0.000316752 | [-0.000846227, 0.000212722] | 1.0759e-07（联合） | Non-inferior |
| K5 MAE | 0.00747367 | [0.00671793, 0.00822942] | 1.0759e-07（联合） | Non-inferior |
| K6 openbmi | 共享预测最大漂移 0 | — | — | 受测离线路径通过 |
| K6 stieger | 共享预测最大漂移 0 | — | — | 受测离线路径通过 |

## 数据至结果复现


固定 OpenBMI 模型的附属历史结果来自 V29b 和 V36 CPU 复算。在重用的 H40 窗口上，ROC-AUC 为 0.8796，95% 区间 [0.7777, 0.9606]。该对照的两组样本数为 12 和 36。[复现核对与来源指纹](raw_reproduction_audit.json)

| 队列 | 已有回执 |
|---|---|
| Stieger | 等待本轮原始数据复现回执 |
| Dreyer | [v47 / comparison.json](raw_reproduction/dreyer/v47/comparison.json) |
| OpenBMI | [v46_fit / comparison.json](raw_reproduction/openbmi/evaluation/v46_fit/comparison.json) · [v48 / result.json](raw_reproduction/openbmi/evaluation/v48/result.json) · [v56 / result.json](raw_reproduction/openbmi/evaluation/v56/result.json) |
| NETBCI | [evaluation / v67_aggregate.json](raw_reproduction/netbci/evaluation/v67_aggregate.json) · [evaluation / controls_C8.json](raw_reproduction/netbci/evaluation/controls_C8.json) |

## 完整共享深层适配边界

OpenBMI V56 原 18 个人对的 Platt 校准复算中，本地 M3 相对完整共享深层适配 M1 的 BA 差为 -1.713 个百分点，Brier 差为 +0.004698。
BA 的 97.5% 区间下界为 -3.913 个百分点，Brier 区间上界为 +0.010532。联合非劣未通过。

## NETBCI C8 等预算曲率对照

| 方法 | 联合非劣 | 预测 MAE 区间上界 | 曲率数组字节数 |
|---|---|---:|---:|
| isotropic | 通过 | 0.00803562 | 8 |
| diagonal | 通过 | 0.00810848 | 368 |
| full | 通过 | 0.000139423 | 16,928 |
| rank_4 | 通过 | 0.00345613 | 1,872 |

同一批 12 名参与者先在人内汇总三个日期。V67 C8 历史效用区间仍跨零。

## OpenBMI C20 等预算对照

18 个人对。三个种子先在人内汇总，再按原人对计算区间。所有对照使用各目标当天的 C20 和 U20。

| 对照 | 本人秩 8 减对照的 Brier | 历史 97.5% 人对 t 区间 |
|---|---:|---|
| 仅当天校准 | -0.00792564 | [-0.0104362, -0.00541508] |
| 等量匹配者历史 | -0.00348484 | [-0.00579961, -0.00117008] |

补充对照使用从原始波形重建的固定前缀与原背景检查点。[完整指标](raw_reproduction/openbmi_controls/20261126T161815835053Z/result.json)

[队列汇总表](table1_cohorts.csv) · [方法比较与资源表](table2_methods.csv) · [验收进度](../manifests/acceptance_progress.md)
