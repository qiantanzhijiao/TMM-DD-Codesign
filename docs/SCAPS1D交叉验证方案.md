# SCAPS-1D 官方算例交叉校验：可行性、人工操作与数据对齐

**编写日期**：2026-11-08
**结论先行**：本机**没有安装 SCAPS-1D**（已检查 `C:\Program Files\SCAPS`、`C:\Program Files (x86)\SCAPS`、用户目录、`C:\SCAPS`），且 SCAPS-1D 是 Windows GUI 程序、没有可用的批量脚本 API，因此**我无法自动跑完这条验证**。但它可以做成「半自动」：我这边生成 UniDD 的标准参照数据与比对脚本，你在 SCAPS 里按下面的步骤人工跑一次、导出 CSV，然后一条命令出叠图和误差表。全流程不需要改 UniDD 代码。

---

## 1. 为什么不能简单地说「同结构同参数叠个图」

SCAPS-1D 的光学是 Beer–Lambert 吸收或用户导入的 generation profile，**不含相干薄膜干涉**；UniDD 的光学是全相干 TMM。直接把两边 J–V 曲线放一起，差异里混着光学模型、接触边界、复合机制、光谱采样和网格离散，无法归因。

本轮已实测（`results_optics_ablation.json`）：在本文参考器件（k=0.72、480 nm）下，相干 TMM 与框架内单次通过产生的 Jsc 只差 **0.007%**、厚度梯度差 **1.9%**（强吸收把驻波阻尼掉了）；但在 120 nm 薄层下梯度差可达 **24–40%**。因此建议分两层做：

| 层 | 比什么 | 光学处理 | 目的 |
|---|---|---|---|
| **A（必做，最干净）** | 暗态 J–V、稳态 n(x)/p(x)、均匀 G 下的 Jsc | 两边都关掉光照 / 给同一均匀产生率 | 只比漂移–扩散求解器与接触边界，排除光学差异 |
| **B（选做）** | 光照 J–V、EQE、G(z) 剖面 | 把 UniDD 的 G(z) 导出后导入 SCAPS，或把 UniDD 退化为单次通过 | 检查光学→电学耦合与单位换算 |

A 层通过后再做 B 层；若 A 层就对不上，先查边界条件与单位，不要急着比 EQE。

---

## 2. 参数对齐表（UniDD → SCAPS）

| UniDD | 值 | SCAPS 字段 | 单位换算 | 注意事项 |
|---|---|---|---|---|
| 层结构 | air / TiO₂ 50 nm / 吸收层 480 nm / HTL 150 nm / 玻璃 | 3 层 + 前后接触 | nm → µm 除以 1000 | SCAPS 没有「空气/玻璃」层，只设 3 个半导体层；光学反射需另设 |
| 吸收层厚度 | 480 nm | thickness | 0.48 µm | 反演实验里是变量，交叉验证固定为真值 |
| 带隙 | 1.55 eV | Eg | 同 | 温度 300 K |
| 相对介电常数 | 6.5 | eps / epsilon_r | 同 | |
| 有效态密度 | Nc=2.2×10²⁴ m⁻³；Nv=1.8×10²⁵ m⁻³ | Nc, Nv | **除以 10⁶** → 2.2×10¹⁸ / 1.8×10¹⁹ cm⁻³ | 单位错是最常见的数量级偏差来源 |
| 迁移率 | μn=μp=2×10⁻⁴ m²/Vs | mu_e, mu_h | **乘 10⁴** → 2 cm²/Vs | |
| SRH 寿命 | τn=τp=3×10⁻⁷ s | tau_n / tau_p 或缺陷俘获截面 | 同 | SCAPS 默认包含缺陷分布与界面复合，须**全部关掉或设为等效单一 SRH** |
| 掺杂 | 吸收层本征（p-i-n） | doping / NA, ND | 同 | 两侧传输层按选择性接触近似 |
| 温度 | 300 K | T | 同 | |
| 复合 | 仅体 SRH | radiative / Auger / interface | 关 | UniDD 无辐射、Auger、表面/晶界复合 |
| 接触 | 理想选择性欧姆接触 | front/back contact work function, S_n, S_p | — | 设为 flat-band、表面复合速度取 0（或极小值近似）；SCAPS 默认金属功函数会引入额外势垒 |
| 串联/并联电阻 | 无 | Rs, Rsh | — | Rs=0、Rsh→∞ |
| 光谱 | ASTM G173 粗表 300–1000 nm（50 nm 间隔）插值到 41 点 350–800 nm，归一 100 mW/cm² | illumination spectrum | nm 同 | SCAPS 内建 AM1.5G 采样不同，B 层建议导入同一张表；A 层不用光谱 |
| 网格 | 均匀 N=73（float64），dx 随 d_abs 变化 | mesh / grading | nm → µm | 两边离散阶不同（UniDD 用指数拟合 SG），5% 以内差异可接受并需说明 |
| 电流 | 光生电流为正，A/m² → mA/cm² | J | **1 A/m² = 0.1 mA/cm²** | SCAPS 常把光生电流记为负，出图前统一符号 |
| 产生率 | cm⁻³ s⁻¹ → m⁻³ s⁻¹ | generation profile | **乘 10⁶** | 导入 SCAPS 的 G(z) 用 cm⁻³ s⁻¹ |
| 吸收系数 | nm⁻¹ → cm⁻¹ | alpha | **乘 10⁷** | |

---

## 3. 人工操作步骤（SCAPS 3.3.x，界面名称随小版本略有差异）

1. **获取与安装**：到 Ghent University / ELIS 的 SCAPS 官网注册并下载 SCAPS-1D（学术用途免费）。记录**准确版本号**，写进 `metadata.txt`。
2. **打开官方算例**：启动后用 `File → Open` 载入自带的 demo / 示例 `.scaps` 文件，先确认软件能正常出 J–V 曲线，再另存为 `unidd_crosscheck.scaps`。**不要直接在官方算例上改后覆盖**。
3. **定义器件**：在 solar-cell definition 面板把层数设为 3，按上表逐层填 thickness、Eg、chi、eps、Nc/Nv、mu、doping；把缺陷（defect）与界面复合全部禁用或设为等效单一 SRH 寿命。
4. **接触**：把前后接触设为 flat-band / 理想欧姆，表面复合速度置 0；关闭 Rs、Rsh。
5. **A 层 — 暗态**：在 illumination 面板关闭光照；在 calculation/action 面板选 J–V，电压范围 0→1.20 V、步长 0.02 V（与 UniDD 的 61 点一致）。运行后把结果导出为 ASCII/CSV，命名为 `dark_JV.csv`。若界面可导出载流子浓度，另存 `carrier_profile.csv`（可选）。
6. **A 层 — 均匀产生率**：如需校核 `Jsc/qGL`，把 generation 设为空间均匀值（UniDD 里是 `uniformG_Jsc=35.42 mA/cm²` 的那一组），再跑一次 J–V，导出 `uniformG_JV.csv`。
7. **B 层 — 导入产生率**：把我方生成的 `scaps_reference/unidd_generation_profile.csv`（列 `z_um, G_cm3_s`）按 SCAPS 的 generation-profile 导入格式转成其要求的 ASCII 文件（必要时改列名/分隔符），在光学/generation 面板导入；导入前确认 z 单位为 µm、G 单位为 cm⁻³ s⁻¹。
8. **B 层 — 光照 J–V 与 QE**：打开光照（导入同一张 AM1.5G 表），跑 0→1.20 V J–V，导出 `light_JV.csv`；再跑 QE / spectral response，波长 380–790 nm、步长约 20 nm，导出 `EQE.csv`。
9. **导出规范**：所有文件放在同一个目录，列名用 `V_V, J_mA_cm2`（J–V）与 `lambda_nm, EQE`（QE）。写一个 `metadata.txt` 记录 SCAPS 版本、算例文件名、全部参数、收敛设置与日期。
10. **比对**：运行
    ```
    python compare_scaps.py --scaps-dir <你导出的目录>
    ```
    输出 `scaps_comparison.png`（叠图）与 `scaps_comparison.md`（相对误差、RMSE、最大偏差表）。

---

## 4. 验收判据（建议，不是承诺）

| 量 | 建议阈值 | 说明 |
|---|---|---|
| 暗态 J–V | 逐点相对误差 < 5%（或绝对误差 < 0.05 mA/cm²） | 只比 DD 内核，最该对得上 |
| 光照 Jsc | < 5% | 含光谱与 G(z) 差异 |
| Voc | < 2% / < 20 mV | 对接触边界与复合极敏感 |
| FF | < 5% | |
| EQE 形状 | 峰值位置一致、RMSE < 0.05 | 允许整体幅度差，形状不一致要查光谱归一 |
| G(z) 剖面 | 导入后回读与 UniDD 剖面 RMSE < 2% | 验证单位换算与插值没有走样 |

**差异来源清单**（写进论文时逐条说明，不要只报一个百分数）：网格密度与离散格式（指数拟合 SG vs SCAPS 内部格式）、接触边界与功函数、复合模型（UniDD 无界面/辐射/Auger）、光谱采样与归一化、离子迁移（UniDD 无）、串联电阻、收敛判据、电流符号约定、单位换算。

---

## 5. 边界与风险

- **不能声称「已与 SCAPS 交叉验证」**，除非上述人工步骤真的跑完并留下数据；论文现有 Limitations 中「未做 SCAPS 交叉验证」的表述在跑完之前必须保留。
- SCAPS 无脚本 API，这条验证**无法进 CI**；它是一次性的人工基准，不是可自动复现的回归测试。
- SCAPS 的许可一般限学术非商业用途，导出数据用于论文需遵守其引用与许可要求（常见引用为 Burgelman 等，Thin Solid Films 361–362 (2000) 527–532，本文已列 `[burgelman2000]`）。
- 若需要**可自动化的**跨代码验证，可脚本化的替代有 Sesame（Python）、Solcore（Python）、Driftfusion / IonMonger（MATLAB/Octave）、wxAMPS。本机均未安装，需联网安装并单独验证；这是后续工作，本轮未做。
- 还有一种零成本的替代：把 `results_supplement.json` 的 Richardson 外推与 `results_optics_ablation.json` 的单通对照作为**内部**一致性证据写进回复信，但这不能替代跨代码验证。

---

## 6. 本轮已交付的工具

| 文件 | 作用 |
|---|---|
| `export_scaps_reference.py` | 生成 UniDD 参照数据到 `scaps_reference/`：暗态/光照 J–V（相干与单通两套）、EQE、G(z) 剖面、参数表、空白模板 |
| `compare_scaps.py` | 读你从 SCAPS 导出的 CSV，插值对齐、算相对误差/RMSE、出叠图与误差报告 |
| `scaps_reference/*.csv` | 参照数据（运行上一个脚本后生成） |

**一句话**：能实现，但不是我点一下就完成——SCAPS 那一步需要你在 GUI 里人工跑并导出；除此之外的数据准备、单位换算、误差分析和出图都已经自动化。
