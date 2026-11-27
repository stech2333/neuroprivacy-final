
# NeuroPrivacy Final

EEG 个人历史共享隔离研究。此私有仓库归档 Final Protocol 1.0 的工程代码、Windows 进度监控、聚合结果与四张正式主图。正式验收于 2026 年 11 月 27 日完成，共 16 项。K1–K4 获支持，K5 通过联合非劣性与预测近似判定，K6 在受测的 OpenBMI、Stieger 离线路径通过。

- [验收清单](manifests/acceptance_progress.md)
- [冻结协议](<archive/Final Protocol 1.0.txt>) · [协议配置](configs/protocol.yaml) · [统计细则](configs/statistics.yaml)
- [统一结果](results/report.md) · [队列表](results/table1_cohorts.csv) · [方法与资源表](results/table2_methods.csv)
- [四张主图与图例](figures/final/legends.md) · [图表指纹](figures/final/provenance.json)
- [复现核对](results/raw_reproduction_audit.json) · [阴性结果与偏离](results/deviations_and_negative_results.md)

## 从聚合数据重建报告

在工程根目录使用 Python 3.11 运行。

```powershell
python -m pip install -r requirements-report.txt
python -m neuroprivacy report --figures
```

Windows 上可运行 `python -m neuroprivacy.monitor` 打开监控。验收表从已归档的清单读取，运行状态则需要本机实验进程和回执。

## 完整复现环境

`audit`、`replay` 和 `reproduce` 需要原受控工作区。将工程放在原历史目录的同级，使用该工作区的登记、原始波形缓存、权重和运行回执。GPU 重训使用原 deep-gpu 环境，可用 `--runtime` 设置解释器。完整实验与归档容量均以本地登记为准。

```powershell
python -m neuroprivacy audit
python -m neuroprivacy reproduce --experiment all
python -m neuroprivacy replay --experiment all --source raw
python -m neuroprivacy report --figures
```

本仓库中的 JSON 和表格仅保存聚合统计。原始脑电数据、个体级预测与试次账本、模型权重、历史清单及日志存放在原受控工作区。聚合核对回执保留各队列的计数和比较结果。OpenBMI 重训的主要排序读数与历史一致，部分辅助指标存在微小数值差异。K6 的结论适用于既定共享产物和受测离线路径。
