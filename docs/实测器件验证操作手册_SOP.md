# 实测器件验证操作手册（SOP）

**版本**：v1.0，2026-11-09
**配套文档**：`实测器件校准与验证方案.md`（讲为什么这么设计）、`实验数据复核与论文支撑度再评估.md`（讲当前证据强度）、`soldiff/SCAPS1D交叉验证方案.md`（代码↔代码对照，已完成）
**适用对象**：准备用真实器件数据校准 / 验证 UniDD 的实验人员
**纪律**：验收判据在看到 hold-out 数据**之前**锁定，写进 `acceptance_criteria.json` 并进版本控制；任何一条不达标都如实报告，**不调阈值、不换器件、不挑最好像素**。

---

## 0. 这份文档与已有方案的分工

| 文档 | 回答 | 粒度 |
|---|---|---|
| 《实测器件校准与验证方案》 | 为什么需要实测、样品矩阵怎么设计、判据怎么定 | 设计层 |
| **本 SOP** | **每天做什么、仪器设什么参数、文件叫什么名字、跑哪条命令、什么情况下停** | 执行层 |
| 《SCAPS1D交叉验证方案》 | 代码↔代码对照（已执行，2/4 通过） | 已完成 |

**一句话流程**：先过 Go/No-Go 门 → 制备留档 → 标定 → 光学表征 → 电学表征 → 数据入库对齐观测网格 → calibration 反演 → hold-out 前向预测 → TMM vs Beer–Lambert 消融 → 不确定度 → 判据判定 → 按可写口径写稿。

---

## 1. Go / No-Go 前置门：四个 gate，全绿才进实验室

> 这一步最容易被跳过，但 SCAPS 对照已经给出预警：**UniDD 的 Dirichlet 接触与真实金属接触不等价**，光照 J–V 因此 FAIL。带着这个已知差异直接做实测，结果对不上时无法区分「数值 bug」和「缺物理机制」。

| Gate | 检查项 | 通过标准 | 不通过怎么办 |
|---|---|---|---|
| **G0 模型扩展决策** | 是否给 DD 内核加上：接触表面复合速度 `S_n/S_p`、串联电阻 `R_s`、并联电阻 `R_sh`（至少 `S` 与 `R_s`） | 明确写出「加 / 不加 + 理由」，并记入 `model_scope.md` | 若决定不加，必须在验收前**书面接受**「光照 J–V 残差可能系统性偏大且不可归因」，并把判据重心放到 EQE 形状与 R/T |
| **G1 标定链** | 标准电池（可溯源证书）、标准 Si/Ge 探测器、椭偏标准片、台阶仪标准台阶，证书编号齐 | 4 类证书编号写进 `metadata/calibration_certificates.csv` | 缺任何一项 → **不能做定量反演**，只能做定性对照，论文不得写 calibration |
| **G2 厚度档位** | 至少 3 档且**必须含 120–200 nm 薄层** | 例如 `120 / 200 / 350 / 480 / 620 nm` | 只有 480 nm 一档 → **不要开工**：真源 `results_optics_ablation.json` 显示 480 nm 下相干与单通 Jsc 仅差 0.0071%、厚度梯度差 1.91%，而 120 nm 下梯度差达 **39.85%**。只做厚层等于无法区分两个光学模型 |
| **G3 代码 dry-run** | 新增的实测适配层能否用**合成伪数据**完整跑通 P4→P8 | 反演能收敛、hold-out 能预测、消融脚本能出图、判据脚本能输出 `acceptance_verdict.json`；伪数据结果不写入论文 | 先在合成数据上调通，不要用真实数据调试代码（避免无意识泄露 hold-out） |

**G0 建议**：加 `S` 与 `R_s` 两个参数并固定为独立测量值（不要与 `τ` 同时反演——稳态 J–V 中它们强耦合、不可辨识）。这一步是纯软件工作，1–2 周，收益远大于多测几个器件。

---

## 2. 目录结构与命名规范（先建好，别事后整理）

```
experiment/
├── raw/                          # 仪器原始输出，只读，永不编辑
│   ├── ellipsometry/
│   ├── rt_spectra/
│   ├── jv/
│   ├── eqe/
│   ├── mpp/
│   └── profilometry/
├── metadata/
│   ├── samples.csv               # 器件台账
│   ├── fabrication_log.csv       # 制备参数
│   ├── calibration_certificates.csv
│   ├── measurement_log.csv       # 每次测量的环境/顺序/方向
│   └── acceptance_criteria.json  # ★ 看 hold-out 之前锁定并 git commit
├── processed/                    # 插值到 UniDD 观测网格后的数据
│   ├── observations.csv          # 每个器件一行的观测向量
│   └── nk_tables/                # 每批次 n(λ)+ik(λ)
├── inversion/
│   ├── adapt_observations.py     # ★ 新增适配层（见 §4.4）
│   ├── fit_calibration.py        # ★ 新增
│   ├── predict_holdout.py        # ★ 新增
│   ├── ablation_tmm_vs_bl.py     # ★ 新增
│   ├── uncertainty_mc.py         # ★ 新增
│   └── evaluate_acceptance.py    # ★ 新增
└── report/
    ├── acceptance_verdict.json
    ├── figures/
    └── experimental_validation.md
```

**文件命名**：`{batch}_{thickness}_{pixel}_{measurement}_{seq}.csv`
例：`B01_T120_P2_JV_fwd_01.csv`、`B02_T480_P1_EQE_01.csv`。
`batch` 用 `B01/B02`（≥2 独立批次），`thickness` 用实测标称值 `T120/T200/T350/T480/T620`，`pixel` 用 `P1..P3`（≥3 独立像素/档），`fwd/rev` 记录扫描方向。**禁止**用 `best.csv`、`final.csv`、`final_v2.csv`。

**`metadata/samples.csv` 表头**：
```
device_id,batch,thickness_nominal_nm,thickness_profilometer_nm,thickness_sem_nm,
area_cm2,mask_area_cm2,fabrication_date,precursor_lot,spin_rpm,spin_s,
anneal_C,anneal_s,glovebox_H2O_ppm,glovebox_O2_ppm,encapsulation,
ellipsometry_sample_id,calibration_set,notes
```
`calibration_set` 只填 `calibration` 或 `hold_out`，**在拆封测量之前由另一个人/另一次掷硬币决定并锁定**。

**`metadata/measurement_log.csv` 表头**：
```
device_id,timestamp,measurement,instrument_id,operator,scan_direction,
scan_rate_mV_s,settling_s,light_intensity_mW_cm2,standard_cell_id,
T_C,RH_pct,stabilized_mpp_s,file_raw,flags
```

---

## 3. 逐阶段操作

### P0 制备与留档

1. 按 G2 的 ≥3 厚度档（建议 5 档）、每档 ≥3 独立像素、**≥2 个独立制备批次**制备器件；参考叠层 `glass / TCO / TiO₂ 50 nm / absorber / spiro-OMeTAD 150 nm / metal`。
   - 若改用 CdTe / CIGS / 有机体系可以，但**必须重新测 `n(λ)+ik(λ)`**，且 `Eg/μ/τ` 作为待校准参数，不得沿用稿件的合成值。
2. 每片留档 `samples.csv` + `fabrication_log.csv`；每档另做**同批次同工艺的单层薄膜**用于椭偏（不要在有金属电极的完整器件上测椭偏）。
3. **输出**：`raw/profilometry/`、`metadata/samples.csv`。
4. **停止条件**：任一厚度档没有独立厚度测量 → 补齐再进 P1。

### P1 标定（每项都要留证书编号 + 当天复核记录）

| 仪器 | 操作 | 记录 |
|---|---|---|
| 太阳模拟器 | AAA 级，AM1.5G，用可溯源标准电池调到 `100.0 mW/cm²`；测光谱失配因子 `M` | `standard_cell_id`、证书号、`M`、标定时间 |
| 单色仪 / EQE | 标准 Si/Ge 探测器标定 300–850 nm；波长用 Hg/Ne 谱线校验 | 探测器证书号、波长偏移 |
| 椭偏 | 标准片（如 Si/SiO₂）校验，350–800 nm，≤5 nm 步长 | 标准片证书号、拟合 MSE |
| 台阶仪 / 轮廓仪 | 标准台阶校验；每档 ≥3 点取均值 ± 标准差 | 台阶证书号 |
| 源表 | 开路 / 短路零位检查，四线接法 | 零点记录 |

**没有标定链的 J–V / EQE 不得进入反演**（方案 §3 同一条纪律）。

### P2 光学表征

1. **椭偏**：350–800 nm、≥5 nm 步长，测同批次单层膜；拟合得 `n(λ), k(λ)`，目标 `n ±0.02`、`k ±5%`。
2. **R/T 光谱**：紫外–可见–近红外 + 积分球，350–800 nm；每档至少 1 片，记录绝对反射率 `±1% abs`。
3. **厚度交叉核对**：台阶仪 + 截面 SEM，两者差 >5 nm 要在 `flags` 标注，不要私自取平均。
4. **输出**：`raw/ellipsometry/`、`raw/rt_spectra/`、`processed/nk_tables/B01_nk.csv`（列：`lam_nm,n,k`）。

### P3 电学表征

| 项目 | 设置 | 输出 |
|---|---|---|
| 暗态 J–V | −0.2 → 1.2 V，`≤10 mV/s`，正/反扫各一次 | `raw/jv/*_dark_*.csv` |
| 光照 J–V | `100 mW/cm²`，−0.2 → 1.2 V，正反扫；每片测前在 MPP 稳定 ≥300 s | `raw/jv/*_light_*.csv` |
| 稳态 / MPP | ≥300 s 最大功率点跟踪，记录迟滞 | `raw/mpp/` |
| EQE | 300–850 nm，≤10 nm 步长，锁相 + 斩波，无白光偏置与有偏置各一次 | `raw/eqe/` |
| 光强依赖 | 中性密度片 0.1 / 0.3 / 0.5 / 1.0 sun，测 `Voc`、`Jsc` 对数斜率 | 判复合机制是否偏离单一 SRH |
| TRPL（强烈建议） | 同批次薄膜，独立估 `τ` | 用于核对反演 `τ` |

**必须记录的坑**：电流符号约定。UniDD 的 `CoupledSolarCell.jv()` 是 **photocurrent-positive**；SCAPS 那次交叉验证就因为符号约定吃过亏。入库前画一张 J–V 图人工确认 `J(0 V) < 0` 还是 `> 0` 与代码一致，写进 `measurement_log.flags`。

### P4 数据入库与观测网格对齐

**UniDD 的观测网格（与 `experiments_final.py` 逐字一致，不要自行改）**：

```python
V_LIST  = [0.0, 0.4, 0.7, 0.9, 1.0, 1.06]        # J–V 6 点
LAM_EQE = torch.linspace(420.0, 760.0, 6)         # EQE 6 点
LAM_RT  = torch.linspace(400.0, 780.0, 8)         # R/T 8 点
# 归一化：J/30, EQE/0.9, R, T  →  观测向量共 6+6+8+8 = 28 维
```

**损失口径以代码为准**：`experiments_final.py::stage_E3` 用的是 `((obs(u) − y_star)**2).mean()`，观测已按上面归一化；《方案》§4.3 写的 `||y−y*||²/||y*||²` 是设计层表述，**实现时以代码为准并保持一致**，不要混用两种 loss 再比较收敛曲线。

**仓库里目前没有实测适配层**，需要新增 `inversion/adapt_observations.py`。以下骨架的接口已在本机 PyTorch 2.15.0 + 项目代码上逐项验证（`cell.lam` 为 41 点、`field_intensity` 返回 `R/T/a/b/I2` 等键）：

```python
import sys, numpy as np, torch
sys.path.insert(0, "soldiff")              # 仓库根目录下的包路径；发布包内改为实际布局
from soldiff.device import CoupledSolarCell, am15_flux
from soldiff.tmm import field_intensity

torch.set_default_dtype(torch.float64)
cell = CoupledSolarCell(N_dd=73)          # 与生产网格一致

V_LIST  = [0.0, 0.4, 0.7, 0.9, 1.0, 1.06]
LAM_EQE = torch.linspace(420.0, 760.0, 6)
LAM_RT  = torch.linspace(400.0, 780.0, 8)
PHI_EQE = am15_flux(LAM_EQE)

def interp_complex(lam_src, n_src, k_src, lam_dst):
    """实测椭偏表 -> cell.lam (41 点) / LAM_EQE / LAM_RT 的复折射率。
    n/k 是实测固定量，不参与反演梯度，用 numpy 线性插值即可。
    注意：torch.interp 在 PyTorch 2.15 中不存在；若日后需要可导插值，
    改用 soldiff/device.py 内的 _interp（torch.searchsorted 实现）。"""
    dst = np.asarray(lam_dst.tolist(), dtype=np.float64)
    ni = np.interp(dst, np.asarray(lam_src, dtype=float),
                   np.asarray(n_src, dtype=float))
    ki = np.interp(dst, np.asarray(lam_src, dtype=float),
                   np.asarray(k_src, dtype=float))
    return torch.complex(torch.as_tensor(ni, dtype=torch.float64),
                         torch.as_tensor(ki, dtype=torch.float64))   # complex128

def measured_observation(jv_meas, eqe_meas, R_meas, T_meas):
    """已插值到 V_LIST / LAM_EQE / LAM_RT 的实测值 -> 与 obs() 同尺度的 y_star。"""
    return torch.cat([torch.as_tensor(jv_meas)/30.0,
                      torch.as_tensor(eqe_meas)/0.9,
                      torch.as_tensor(R_meas),
                      torch.as_tensor(T_meas)])

def forward_observables(u, nk_table, d_abs_fixed_nm=None):
    """与 build_observables 相同的结构，仅把合成 nk 换成实测表。"""
    d_abs = u[0] if d_abs_fixed_nm is None else torch.as_tensor(d_abs_fixed_nm)
    # k_amp / tau 等由 decode(u) 给出；nk_abs 由实测表 × 可反演幅值构造
    ...
    J   = cell.jv(d_abs, nk_abs_41, tau, V_LIST, ift=True, dV=0.05)
    eqe = cell.eqe_curve(d_abs, nk_abs_eqe, tau,
                         lam_eqe=LAM_EQE, phi_eqe=PHI_EQE, ift=True)
    d_stack = torch.stack([...])
    rt = field_intensity(nk_rt_5x8, d_stack, LAM_RT)   # 5 层 × 8 波长
    return torch.cat([J/30.0, eqe/0.9, rt["R"], rt["T"]])
```

**三处必须对齐的张量形状**（照 `build_observables` 的写法，已核实）：

| 传入量 | 形状 | 对应网格 |
|---|---|---|
| `nk_abs_41` | `(41,)` complex128 | `cell.lam` = linspace(350, 800, 41) |
| `nk_abs_eqe` | `(6,)` complex128 | `LAM_EQE` = linspace(420, 760, 6) |
| `nk_rt_5x8` | `(5, 8)` complex128 | `LAM_RT` = linspace(400, 780, 8)，5 层顺序为 `[air=1.0, ETL, absorber, HTL, substrate=1.5]` |
| `d_stack` | `(3,)` | `[d_etl=50, d_abs, d_htl=150]` nm |

静态层 `cell.nk_etl = 2.0`、`cell.nk_htl = 1.5+0.005i` 可直接复用；实测若与之不同，替换并在 `model_scope.md` 记录出处。

**输出**：`processed/observations.csv`，每个 `device_id` 一行，列为 `JV_0.0 ... JV_1.06, EQE_420 ... EQE_760, R_400 ... R_780, T_400 ... T_780`，另附 `n(λ),k(λ)` 表路径与 `calibration_set`。

**验收**：任意取一行回代 `forward_observables`，确认维度 28、无 NaN、`R+T ≤ 1`；与原始曲线画叠图人工签字。

### P5 Calibration 反演

1. **划分（锁定后不再改）**：
   ```
   calibration : B01 的 T200、T350、T480 全部像素
   hold_out    : B02 的 T120、T200、T350、T480、T620 全部像素
   ```
   批次 + 厚度双重分离；绝不用同一条曲线既拟合又验证。
2. 待反演：`d_abs`（仅用于与台阶仪交叉核对）、`k_amp` 或 6 节点 `k(λ)` 幅值、`τ`。
   **固定**：`μ_n=μ_p`（来自文献或 Hall/SCLC）、实测 `n(λ)`、`Eg`、接触参数、`R_s/S`。理由见方案 §4.2：`μ` 与 `τ` 在稳态 J–V 强耦合，同时反演不可辨识。
3. 复用 `experiments_final.py::lbfgs_run` 的调用方式（`torch.optim.LBFGS` + `loss_of(u, grad=True)` + `loss.backward()`），把 `y_star` 换成 `measured_observation(...)`：
   ```python
   loss = ((forward_observables(u, nk_table) - y_cal) ** 2).mean()
   ```
   `ift=True` 保证 IFT 伴随梯度挂上；不要包 `torch.no_grad()` 切断链路。
4. 记录：每 20 次打印一次 loss，保存完整 history、`f()` 真实调用数、wall clock、参数置信初值。
5. **输出**：`inversion/calibration_fit.json`（参数、loss、history、seed、软件版本）。

### P6 Hold-out 前向预测 + TMM vs Beer–Lambert 消融

**关键修正（比方案 §4.3 更细）**：迁移的只是**材料参数**（`k(λ), τ, μ, 接触参数`）；**几何参数 `d_abs` 必须用每个 hold-out 器件自己的台阶仪/SEM 实测值**，不能把 calibration 反演出的那个 `d_abs` 套到别的厚度档。否则「预测误差」里混进了厚度赋值错误，无法归因。

1. 用 calibration 的材料参数 + 各档实测厚度，对 hold-out **逐器件**前向预测 J–V / EQE / R / T，**不做任何再调参**。
2. 计算逐器件残差：J–V 逐点相对误差、`Jsc/Voc/FF`、EQE 形状 RMSE、`R/T` RMSE；报告**逐器件值 + 最差器件**，不只报平均。
3. 消融：把光学换成单通 / Beer–Lambert，**保留相同的 Fresnel 透射振幅、`α(λ)`、光子通量与 Poynting 因子**，只关掉干涉项。
   > 历史 bug 警示：早期消融漏掉 Fresnel 振幅，得到非物理的 `Jsc=79.5 mA/cm²`。正确写法见 `experiments_optics_ablation.py`：
   > `I2 = |a_l|² · exp(−α z)`，其中 `a_l = field_intensity(...)["a"][2]`。
4. 用配对检验（如 Wilcoxon signed-rank，逐器件配对）判断 TMM 是否在**薄层档**显著优于单通；报效应量不要只报 p 值。
5. **输出**：`report/figures/holdout_residuals.png`、`ablation_thin_vs_thick.png`、`inversion/ablation_results.json`。

### P7 不确定度传播

Monte Carlo ≥200 次，每次从以下分布抽样后重跑 P5→P6：
`d_abs ±5 nm`、`n ±0.02`、`k ±5%`、光谱标定 `±1–2%`、温度 `±1 K`、`R_s` 先验区间。
输出参数 95% 区间、hold-out 预测带、以及「判据是否在全扰动范围内稳定」的结论。**若结论在扰动下翻转，必须如实写「结论对标定不确定度敏感」**。

### P8 验收判定

把 §4 的判据写进 `metadata/acceptance_criteria.json`，用 `inversion/evaluate_acceptance.py` 自动判定，输出与 `scaps_run/export/acceptance_verdict.json` 同构的 `report/acceptance_verdict.json`：

```json
{
  "criteria_fixed_before_data": true,
  "all_pass": false,
  "verdicts": [
    {"item": "hold-out J-V", "criterion": "...", "measured": "...", "verdict": "PASS|FAIL",
     "note": "..."}
  ]
}
```

**判定必须在看到 hold-out 残差之前把脚本与阈值提交 git**（`git commit -m "lock acceptance criteria before hold-out"`），之后只运行、不编辑。这与本项目「E4 未达标结论一字不改」是同一条纪律。

---

## 4. 预指定验收判据（逐字沿用《方案》§4.4，不得事后调整）

| 判据 | 阈值 | 若不达标（按 §5 处置） |
|---|---|---|
| hold-out J–V 逐点相对误差 | `< 8%`（或 `< 0.5 mA/cm²`） | 查接触边界与界面复合，**不要调优化器** |
| hold-out `Jsc / Voc / FF` | `< 5% / < 2% / < 5%` | 同上 |
| EQE 形状 RMSE | `< 0.08` | 查光谱归一与 `k(λ)` |
| 反演 `d_abs` vs 台阶仪 | `< 8%` | `(d,k)` 简并未解除，或椭偏 n/k 有偏 |
| 反演 `τ` vs TRPL | 同一数量级且差异可解释 | 复合模型过于简单 |
| **薄层上 TMM 显著优于 Beer–Lambert** | 厚度梯度或 J–V 残差有统计显著改善 | **中心主张在实测上不成立，如实报告** |
| 残差结构 | 无系统性厚度 / 波长趋势 | 有趋势 = 缺物理机制，写进 Limitations |

---

## 5. 失败分支决策树

```
hold-out 残差偏大
├─ 所有厚度档整体同向偏移、形状相似
│    → 接触 / Rs / 准费米边界问题（SCAPS 2/4 已预警）→ 回 G0 加表面复合与 Rs
├─ 只在薄层档偏大，且残差随厚度单调
│    → 光学模型或 k(λ) 短波端；先查椭偏拟合与光谱标定
├─ 残差随波长有系统趋势
│    → k(λ) 幅值 / 带隙截断 / EQE 波长标定
├─ 反演 d_abs 与台阶仪差 >8%
│    → (d,k) 简并：补 R/T 光谱观测（稿件 E3 已证实可解除），或固定 d_abs
├─ 反演 τ 与 TRPL 差一个量级以上
│    → 单一 SRH 不足；考虑辐射 / Auger / 界面复合，或承认模型不适用
├─ TMM 在所有档位都不优于 Beer–Lambert
│    → ★ 中心主张在实测上不成立。如实写进论文，不得改判据、不得只报薄层子集
└─ 结论在 Monte Carlo 扰动下翻转
     → 写「对标定不确定度敏感」，降低主张强度，不删不确定性分析
```

**任何分支都不允许**：删器件、换 hold-out 集合、放宽阈值、只报通过的子集、把失败重述为「定性一致」。

---

## 6. 论文可写 / 不可写表述清单

| 情形 | 可以写 | 绝不能写 |
|---|---|---|
| 未完成任何实测 | 「no experimental calibration has been performed」「synthetic inverse crimes」 | `experimental validation`、`validated against measurements` |
| 完成标定 + hold-out 全部判据通过 | 「calibrated on batch B01 and validated on an independent batch B02」「TMM outperforms a single-pass optical model on thin absorbers (effect size …)」 | 「proves the model is correct」；仍不得改写 E4 未达标 |
| SCAPS 对照（已执行） | 「a limited cross-code sanity check, two of four criteria pass」 | 「cross-validated against SCAPS-1D」「validated against SCAPS」 |
| 部分判据失败 | 逐条列出失败项与归因，说明对结论的影响 | 只报通过项、隐藏失败项 |
| 器件指标 | 「measured Jsc/Voc/FF」并给误差棒与器件数 | 把实测效率与稿件合成 `η=27.74%` 直接对比，或用合成数值当预测精度证据 |

**Generative AI disclosure 保留**，不因补了实验而删。

---

## 7. 排期与 go/no-go gate（估时，非承诺）

| 周 | 工作 | Gate |
|---|---|---|
| W0 | G0 模型扩展（`S`, `Rs`）+ G3 合成数据 dry-run；锁定判据并 git commit | **G0–G3 全绿**才订机时 |
| W1–W2 | 制备 ≥2 批次、≥3 厚度档（含薄层）、单层椭偏片；P1 标定 | 厚度实测齐全、证书齐全 |
| W3 | P2 椭偏 / R/T / 厚度交叉核对 | `n ±0.02`、`k ±5%` |
| W4–W5 | P3 明暗 J–V / EQE / MPP / 光强依赖 / TRPL | 迟滞可控、标定复核通过 |
| W6 | P4 入库 + P5 calibration 反演 | 收敛、`d_abs` 与台阶仪一致 |
| W7 | **P6 hold-out 前向预测（此前不得查看 hold-out 残差）** + 消融 | 逐器件残差出齐 |
| W8 | P7 Monte Carlo + P8 判定 + 图表 + 写稿 | 判据脚本未改动、结果如实 |

MVP 约 6–10 周，取决于制备与机时。**W0 的 G0 不能省**：SCAPS 光照 J–V 的 FAIL 已经指明接触模型是首要嫌疑。

---

## 8. 合规与安全

- 铅基钙钛矿：含铅废液 / 废片分类收集，手套箱与通风柜操作，遵守本单位危化品与废弃物规程；不在文档中写「规避」做法。
- 太阳模拟器 / 源表：按仪器 SOP 操作，标定证书在有效期内。
- 原始数据 `raw/` 只读；任何处理都写到 `processed/`，保留从 raw 到 processed 的脚本与参数，保证可复算。
- 数据留存：原始文件、metadata、脚本、判据、`acceptance_verdict.json` 一并归档；投稿时给出仓库 / Zenodo 链接。
- **不编造、不补点、不平滑**：缺测标记为缺失，不用插值伪造实测点。

---

## 9. 交付清单

| 交付项 | 产出方 | 状态 |
|---|---|---|
| 样品矩阵、标定链、判据设计 | 《实测器件校准与验证方案.md》 | 已备 |
| SCAPS-1D 代码↔代码对照 | `scaps_run/export/`（20 个真实文件） | **已完成，2/4 通过** |
| 实测适配层 6 个脚本 | 需按 §4.4 / §4.5 骨架新增 | 待做（W0 dry-run） |
| 实测数据、反演、消融、判定 | 实验阶段产出 | 待做 |
| 两版论文 Results / Limitations 改写 | 判定完成后由撰稿侧承接 | 待做 |

> **本 SOP 不含任何实测数据，也不声称验证已完成。** 当前 UniDD 的全部数值证据仍是合成的；SCAPS 对照是有限跨代码 sanity check，不是实验验证。实测到位之前，论文口径维持「no experimental calibration has been performed」。
