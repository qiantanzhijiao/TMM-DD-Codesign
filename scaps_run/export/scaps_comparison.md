# SCAPS-1D / UniDD 交叉验证比对报告

本报告只量化**已导出数据**的一致性。结论严格按预先固定的判据给出，
不得把跨模型差异或缺失项表述为「验证通过」。下表的 `点数` 是两套曲线
共同可收敛区间内的采样点数：SCAPS 在暗态 0.82 V、光照约 1.08 V 处
收敛失败并自动截断，超出其收敛范围的电压不参与比较。

## SCAPS 运行记录（作者提供）

```
# SCAPS-1D cross-check run log  (fill in and keep with the exported data)
SCAPS executable   : scaps3312.exe
SCAPS version      : 3.3.12  (confirm via Help -> About; record build date)
CVI Run-Time Engine: legacy 2007 NI CVI RTE from the official SCAPS 3.3.12 installation package, privately deployed by install_scaps_runtime.py (no administrator rights)
Operating system   : Windows
Run date / operator: 2026-11-08T23:40:08 / automated run via run_scaps_crosscheck.py
Definition file    : unidd_crosscheck.def
Effective def file : unidd_crosscheck_effective.def  (saved by the script)
Script file        : unidd_crosscheck.script
Spectrum file      : unidd_am15g.spe
Generation file    : unidd_generation.gen  (UniDD coherent TMM, #/m3.s)
Reference data     : scaps_reference/unidd_*.csv  (UniDD side, NOT SCAPS output)
Acceptance criteria: fixed in SCAPS1D交叉验证方案.md section 5; NOT revised after data.

# Mandatory checks before trusting the numbers
- [ ] SCAPS started without DLL errors.  A non-zero exit code (e.g.
      0xC0000409) is expected from the CVI runtime on self-termination;
      judge success by the written files, not by the exit code.
- [ ] unidd_crosscheck_effective.def was written; open it and confirm ONE layer.
- [ ] unidd_B_generation_readback.gen agrees with unidd_generation.gen to <2%.
- [ ] All four result files (.iv x2, .qe, .gen) and PNG graphs are present.
- [ ] SCAPSErrorLogFile.log was collected; convergence cut-offs (dark J-V
      cut at 0.8 V, light J-V cut near 1.06 V) are reported explicitly.
- [ ] No SCAPS data are quoted in the manuscript before this log is complete.

SCAPS exit code: 3221226505 (0xC0000409)
Exit-code note: non-zero CVI runtime termination; all four required result files were written during this run and parsed successfully.
Elapsed: 6.1 s
SCAPS diagnostic log: SCAPSErrorLogFile.log (collected with this run)
Note: SCAPS cuts the dark J-V at 0.8 V and the light J-V near 1.06 V
      on convergence failure; comparisons use the common converged range.
Collected files: unidd_A_dark.iv, unidd_A_dark.png, unidd_B_eqe.png, unidd_B_eqe.qe, unidd_B_generation.png, unidd_B_generation_readback.gen, unidd_B_genrec.dat, unidd_B_light.iv, unidd_B_light.png, unidd_crosscheck_effective.def

```

## 逐项误差

| 量 | 点数 | RMSE | MAE | 最大偏差 | 平均相对误差 | 备注 |
|---|---|---|---|---|---|---|
| dark J-V | 41 | 0.001436 | 0.0004848 | 0.007037 | 212.10% |  |
| light J-V | 54 | 3.424 | 3.2 | 9.792 | 11.17% |  |
| EQE | 20 | 0.09634 | 0.08188 | 0.2091 | 9.40% |  |
| generation profile | 72 | 1.052e+16 | 1.24e+15 | 8.929e+16 | 0.00% |  |

## 器件指标

- **dark J-V**：Jsc UniDD 0.000 / SCAPS 0.0 mA/cm²（暗态电流近零，Voc/FF 无物理意义，不报告）
- **light J-V**：Jsc UniDD 29.950 / SCAPS 32.0563187 mA/cm²；Voc UniDD 1.1095769062592638 / SCAPS None V；FF UniDD 16.26356669922814 / SCAPS None

## 预指定验收判定

判据逐字取自 `SCAPS1D交叉验证方案.md` §5，在任何 SCAPS 数据产生之前固定，
本脚本不会在看到数据后放宽阈值。暗态 J–V 采用绝对误差分支，因为 UniDD
暗电流接近零，相对误差在数值上没有意义。

**总体结论：未全部通过**

逐项统计：PASS 2 / FAIL 2 / N/A 0。

| 项目 | 实测 | 阈值 | 判定 | 说明 |
|---|---|---|---|---|
| dark J-V | RMSE 0.001436 mA/cm2; mean rel. 212.10% | RMSE < 0.05 mA/cm2 OR rel. < 5% | **PASS** | SCAPS metal contacts vs UniDD Dirichlet contacts are not identical |
| light J-V | Jsc 7.03% | Jsc < 5%; Voc < 20 mV; FF < 5% | **FAIL** | Voc unavailable: SCAPS J-V does not cross zero in its converged range; FF unavailable: no Voc crossing on the SCAPS curve |
| EQE | RMSE 0.09634 | RMSE < 0.05 | **FAIL** | different optical models; shape only |
| generation profile | RMSE/mean(ref) 0.0002369% | < 2% | **PASS** | checks unit conversion and G(x) interpolation |

- 暗态 J–V / Voc / FF 若不达标，须在论文中逐项归因（SCAPS 金属接触 + 表面复合速度
  vs UniDD Dirichlet 载流子密度边界、网格离散、复合参数化），不得静默改阈值。
- EQE 仅作形状 sanity check：UniDD 用相干 TMM，SCAPS 用 Beer–Lambert / 用户 G(x)。

## 差异来源（超出阈值时逐条排查）

网格密度与离散格式、接触边界与功函数、复合模型（UniDD 无界面/辐射/Auger）、
光谱采样与归一化、串联电阻、收敛判据、电流符号、单位换算。

本轮实测：SCAPS 的 flatband/表面复合接触与 UniDD 的 Dirichlet 载流子密度
边界在物理上不等价。SCAPS 光照 J–V 在 0–1.06 V 几乎不随偏压下降，
无法定义 Voc/FF；这属于模型差异而非数值误差，不得据此调整阈值。

---

生成脚本：`compare_scaps.py`；参照数据：`scaps_reference/`。
