# SCAPS-1D 交叉验证：软件出数、出图能力与可执行方案

**编写日期**：2026-11-08（第 2 版，取代 11-08 第 1 版）
**取代说明**：第 1 版写「SCAPS 是 Windows GUI 程序、没有可用的批量脚本 API，因此无法自动跑完」「SCAPS 无脚本 API，这条验证无法进 CI」。经核查 SCAPS 官网、官方 scripting manual 与 script add-on manual，**该结论不成立**，本版更正。

---

## 0. 结论先行（直接回答两个问题）

**问：SCAPS-1D 是不是可以用软件生成仿真数据、生成结果图？**

**答：可以，而且是它的原生功能，不需要外部逆向或抓屏。**

- 官网对当前版本的特性清单里明确写有：`batch calculations possible`、`the results of batch calculations can be internally recorded, so that afterwards graphs can be made of nearly everything against everything`、以及 `a script language facility to run SCAPS from a "script file"; all internal variables can be accessed and plotted via the script`。
- 官方 script add-on manual 给出了成体系的命令：`load` / `save` / `action` / `calculate` / `get` / `set` / `loop` / `run` / `system`。其中 `save results.iv`、`save results.qe`、`save results.recorder` 导出数值结果，`save graph.iv.iv`、`save graph.qe.qe` 等直接把图形存成 **PNG**；`get iv` / `get qe` / `get gx` / `get characteristics.*` / `get recombination.*` / `get energybands.*` 把曲线取进脚本向量。
- 官方手册还明确支持 `generation: either from internal calculation or from user supplied G(x) file`、`illumination: AM0, AM1.5D, AM1.5G, ...`、最多 7 层半导体、参数 grading、内建 curve fitting、以及 `All calculations can be saved in ASCII format`（教学讲义原文；官网特性页只写 `show/save` 与 `.iv/.cv/.cf/.qe` 文件类型，未逐字写 ASCII，引用时按后者更稳妥）。

**所以正确的边界不是「SCAPS 不能自动出数据」，而是：**

> 本机当前**没有安装 SCAPS-1D**，且 SCAPS 是需注册获取、依赖 Windows 图形环境的商业/学术许可软件；因此**本轮环境里无法由我直接跑完并产出真实 SCAPS 数据**。但在用户安装好 SCAPS 的机器上，这条验证可以脚本化、批量化、自动出图，只是不能无条件塞进当前这个纯 Python 的 CI（CI 容器里没有 SCAPS 授权与 GUI 依赖）。

**稿件表述约束不变**：在真实的 SCAPS 数据产出并留档之前，两版稿件的 Limitations 必须继续保留「未做 SCAPS-1D 交叉验证」。方案写得再细，也不等于验证已做。

### 版本号的诚实说明

官网特性页写 `The most recent version, SCAPS 3.8, may 2020, includes: ...`，但同一页的 version history 最新条目是 `SCAPS 3.3.11`（2024-06-16）。这两处不一致，**不要凭网页概览段断言版本号**。请在安装后从 `Help → About` 读取实际版本号，连同 build 日期写进 `metadata.txt`；本文所有命令名以该版本的 script manual 为准逐条核对。

---

## 1. 为什么不能「同结构同参数叠个图」就完事

SCAPS 的光学是 Beer–Lambert 吸收或用户导入的 generation profile，**不含相干薄膜干涉**；UniDD 的光学是全相干 TMM。直接把两条 J–V 放一起，差异里混着光学模型、接触边界、复合机制、光谱采样与网格离散，无法归因。

本轮实测（`results_optics_ablation.json`）：在参考器件（k=0.72、480 nm）下，相干 TMM 与框架内单次通过产生的 Jsc 只差 **0.007%**、厚度梯度差 **1.9%**（强吸收把驻波阻尼掉了）；但在 120 nm 薄层下梯度差可达 **24–40%**。因此必须分两层：

| 层 | 比什么 | 光学处理 | 目的 |
|---|---|---|---|
| **A（必做，最干净）** | 暗态 J–V、稳态 n(x)/p(x)、均匀 G 下的 Jsc | 两边关掉光照 / 给同一均匀产生率 | 只比漂移–扩散求解器与接触边界，排除光学差异 |
| **B（选做）** | 光照 J–V、EQE、G(z) 剖面 | 导入 UniDD 的 G(z)，或把 UniDD 退化为单次通过 | 检查光学→电学耦合与单位换算 |

A 层通过后再做 B 层；A 层对不上先查边界条件与单位，不要急着比 EQE。

---

## 2. 参数对齐表（UniDD → SCAPS）

| UniDD | 值 | SCAPS 字段 | 单位换算 | 注意事项 |
|---|---|---|---|---|
| 层结构 | air / TiO₂ 50 nm / 吸收层 480 nm / HTL 150 nm / 玻璃 | 3 层 + 前后接触 | nm → µm 除以 1000 | SCAPS 没有「空气/玻璃」层，只设 3 个半导体层；反射需另设 filter |
| 吸收层厚度 | 480 nm | thickness | 0.48 µm | 反演实验里是变量，交叉验证固定为真值 |
| 带隙 | 1.55 eV | Eg | 同 | 300 K |
| 相对介电常数 | 6.5 | eps / epsilon_r | 同 | |
| 有效态密度 | Nc=2.2×10²⁴ m⁻³；Nv=1.8×10²⁵ m⁻³ | Nc, Nv | **除以 10⁶** → 2.2×10¹⁸ / 1.8×10¹⁹ cm⁻³ | 最常见的数量级错误来源 |
| 迁移率 | μn=μp=2×10⁻⁴ m²/Vs | mu_e, mu_h | **乘 10⁴** → 2 cm²/Vs | |
| SRH 寿命 | τn=τp=3×10⁻⁷ s | tau_n / tau_p 或缺陷俘获截面 | 同 | SCAPS 默认含缺陷分布与界面复合，须全部禁用或设为等效单一 SRH |
| 掺杂 | 吸收层本征（p-i-n） | NA, ND | 同 | 两侧传输层按选择性接触近似 |
| 温度 | 300 K | T | 同 | |
| 复合 | 仅体 SRH | radiative / Auger / interface | 关 | UniDD 无辐射、Auger、表面/晶界复合 |
| 接触 | 理想选择性欧姆接触 | work function / flat-band, S_n, S_p | — | 设为 flat-band、表面复合速度取 0（或极小近似） |
| 串联/并联电阻 | 无 | Rs, Rsh | — | Rs=0、Rsh→∞ |
| 光谱 | ASTM G173 粗表插值到 41 点 350–800 nm，归一 100 mW/cm² | illumination spectrum | nm 同 | SCAPS 内建 AM1.5G 采样不同，B 层导入同一张表；A 层不用光谱 |
| 网格 | 均匀 N=73（float64） | mesh / grading | nm → µm | 离散阶不同（UniDD 为指数拟合 SG），5% 内差异需说明 |
| 电流 | A/m² → mA/cm² | J | **1 A/m² = 0.1 mA/cm²** | SCAPS 常把光生电流记为负，出图前统一符号 |
| 产生率 | m⁻³ s⁻¹ → cm⁻³ s⁻¹ | generation profile | **除以 10⁶** | 导入 SCAPS 的 G(z) 用 cm⁻³ s⁻¹ |
| 吸收系数 | nm⁻¹ → cm⁻¹ | alpha | **乘 10⁷** | |

参数表已由 `export_scaps_reference.py` 写成 `scaps_reference/unidd_parameters.csv`，含逐项换算备注。

---

## 3. 三种执行模式（按自动化程度排序）

### 模式 1：GUI 人工（最低门槛，第 1 版文档写的就是这条）

1. 到 Ghent University / ELIS 的 SCAPS 官网注册并下载（学术用途免费），记录 `Help → About` 里的**准确版本号**。
2. 用 `File → Open` 载入自带 demo 确认能出 J–V，再另存为 `unidd_crosscheck.def`。**不要覆盖官方算例**。
3. 在 Solar Cell Definition Panel 设 3 层，按第 2 节逐层填参数；禁用缺陷与界面复合，接触设 flat-band，Rs=0 / Rsh→∞。
4. Action Panel 里勾选 I–V，设电压范围 0 → 1.20 V、步长 0.02 V（与 UniDD 的 61 点一致）。
5. **A 层**：illumination 面板关光照 → `calculate: single shot` → IV panel 点 `show` / `save` 导出 `dark_JV.csv`；若可导出载流子浓度，另存 `carrier_profile.csv`。
6. **B 层**：把 `scaps_reference/unidd_generation_profile.csv` 转成 SCAPS 的 generation file 格式（列 `z_um, G_cm3_s`，注意 z 单位 µm、G 单位 cm⁻³ s⁻¹），在 generation 面板导入；打开同一张 AM1.5G 表 → 跑光照 J–V 导出 `light_JV.csv`；再跑 QE，380–790 nm、步长约 20 nm，导出 `EQE.csv`。
7. 需要论文用图时，直接在对应 panel 用 `save graph`（输出 PNG），或用官方命令 `save graph.iv.iv` / `save graph.qe.qe` 批量存图。
8. 写 `metadata.txt`：SCAPS 版本、`.def` 文件名、全部参数、收敛设置、光谱文件、日期、操作人。

### 模式 2：脚本半自动（推荐，可复现、可出图）

官方 script language 支持把整套设置与动作写进 `.script` 文件，在 SCAPS 里用 script editor 载入执行。我已在 `scaps_reference/unidd_crosscheck.script` 放了一份模板，核心命令族如下（**命令名随 3.3.x / 3.8 构建略有差异，请在内置 script editor 里逐条核对后再整段运行**）：

| 命令族 | 例子 | 作用 |
|---|---|---|
| `load` | `load definition unidd_crosscheck.def`、`load spectrum am15g_unidd.spe`、`load generation unidd_generation.gen` | 载入器件 / 光谱 / 用户 G(x) |
| `action` | `action dark`、`action light`、`action iv.doiv 1`、`action workingpoint.voltage 0` | 设置计算动作与工作点 |
| `calculate` | `calculate singleshot`、`calculate batch`、`calculate recorder` | 单次 / 批量 / 记录器计算 |
| `get` | `get characteristics.jsc/voc/ff/eta`、`get iv xy`、`get qe xy`、`get gx xy`、`get recombination.SRH`、`get energybands.n` | 把曲线与标量取进脚本向量 |
| `save` | `save results.iv unidd_A_dark.iv`、`save results.qe unidd_B.qe`、`save results.recorder unidd_recorder.txt`、`save graph.iv.iv unidd_A_dark.png` | 导出数值结果 / 图形 PNG |
| `set` | `set generation.from_scriptvectors xy` | 把脚本向量设为 generation profile |
| 批量 | `load batchsettings ...`、`load recordersettings ...`、`calculate batch`、`calculate recorder` | 参数扫描 + 任意量对任意量作图 |

关键点：`save graph.*` 是官方命令，**结果图由 SCAPS 自己生成**，不需要外部绘图库；`get iv` / `get qe` 把数值取进脚本向量后也可导出 ASCII/自定义格式，供 `compare_scaps.py` 读取。

**脚本模式的正确工作流**：先在 GUI 里把器件调通并保存 `.def` + action list + spectrum 文件，再用脚本重复执行 A/B 两层、批量导出与出图。这样「人工」只发生在第一次建器件，之后的重复运行与出图都是软件自动完成。

### 模式 3：命令行 / 高通量（可选，非本轮交付）

社区存在用 Wine + xvfb 在 Linux 无头环境里驱动 SCAPS 做批量扫描的非官方封装。这条路能把 SCAPS 接进自动化管线，但依赖 Wine、Windows 运行时与 SCAPS 许可，**本轮未安装、未验证、不作交付承诺**；若后续要做，应先在单机上验证 `load settings from command line` + script file 的链路，再谈容器化。

---

## 4. 与 UniDD 工具链的接口

| 文件 | 作用 | 状态 |
|---|---|---|
| `export_scaps_reference.py` | 生成 UniDD 参照数据到 `scaps_reference/`：暗态/光照 J–V（相干 + 单通两套）、EQE、G(z) 剖面、参数换算表、空白模板、SCAPS 脚本模板 | 已交付并自测 |
| `compare_scaps.py` | 读 SCAPS 导出的 CSV（列名模糊匹配、符号自动翻转），插值对齐，算 RMSE / MAE / 最大偏差 / 平均相对误差、Jsc / Voc 交叉，出 `scaps_comparison.png` 与 `scaps_comparison.md` | 已交付并自测 |
| `scaps_reference/unidd_crosscheck.script` | 官方 script 语法模板（需按本机版本核对命令名） | 本版新增 |
| `scaps_reference/TEMPLATE_*.csv` | 从 SCAPS 导出后填写的空白表头 | 已生成 |

运行链：

```bash
# 1) 生成/刷新 UniDD 参照数据与脚本模板
cd soldiff
python export_scaps_reference.py

# 2) 在装好 SCAPS 的机器上按第 3 节跑 A/B 两层，导出 CSV 到单独目录
#    （GUI 的 show/save，或脚本的 save results.* / save graph.*）
#    同目录写 metadata.txt 记录版本与全部设置

# 3) 自动比对 + 出叠图与误差表
python compare_scaps.py --scaps-dir <导出目录>
```

`compare_scaps.py` 期望的文件名：`dark_JV.csv`、`light_JV.csv`、`EQE.csv`、`generation_profile.csv`，列名 `V_V, J_mA_cm2` 与 `lambda_nm, EQE`（支持模糊别名与符号翻转）。

---

## 5. 验收判据（建议值，不是承诺）

| 量 | 建议阈值 | 说明 |
|---|---|---|
| 暗态 J–V | 逐点相对误差 < 5%（或绝对误差 < 0.05 mA/cm²） | 只比 DD 内核，最该对得上 |
| 光照 Jsc | < 5% | 含光谱与 G(z) 差异 |
| Voc | < 2% / < 20 mV | 对接触边界与复合极敏感 |
| FF | < 5% | |
| EQE 形状 | 峰值位置一致、RMSE < 0.05 | 允许整体幅度差；形状不一致要查光谱归一 |
| G(z) 剖面 | 导入后回读与 UniDD 剖面 RMSE < 2% | 验证单位换算与插值没有走样 |

**差异来源清单**（写进论文时逐条说明，不要只报一个百分数）：网格密度与离散格式（指数拟合 SG vs SCAPS 内部格式）、接触边界与功函数、复合模型（UniDD 无界面/辐射/Auger）、光谱采样与归一化、离子迁移（UniDD 无）、串联电阻、收敛判据、电流符号约定、单位换算。

---

## 6. 边界与风险

- **不得声称「已与 SCAPS 交叉验证」**，除非上述步骤真的跑完、数据留档、误差表生成。两版稿件现有的「未做 SCAPS 交叉验证」在跑完之前必须保留。
- 本轮环境**没有安装 SCAPS-1D**（已检查常见安装路径），因此本轮没有产出任何真实 SCAPS 数据；`scaps_reference/` 里的 CSV 全部是 **UniDD 侧参照数据**，不是 SCAPS 结果，命名上不要混淆。
- 第 1 版「SCAPS 无脚本 API、无法进 CI」的说法已废弃：SCAPS 有脚本与批量能力，**不能进 CI 的原因是本机/容器缺少软件本体与许可**，不是软件本身不支持自动化。若将来在持有机器的环境里部署，脚本模式可以作为回归基准。
- SCAPS 许可一般限学术非商业用途，导出数据用于论文需遵守其引用与许可要求（常见引用 Burgelman 等，Thin Solid Films 361–362 (2000) 527–532，本文已列 `[burgelman2000]`）。
- 可脚本化的替代跨代码验证：Sesame（Python）、Solcore（Python）、Driftfusion / IonMonger（MATLAB/Octave）、wxAMPS。本机均未安装，属后续工作。
- 零成本的内部替代：`results_supplement.json` 的 Richardson 外推与 `results_optics_ablation.json` 的单通对照可作为**内部**一致性证据写进回复信，但**不能替代**跨代码验证。

---

## 7. 一句话总结

SCAPS-1D **能**用软件生成仿真数据、生成结果图，而且原生支持脚本与批量；我这边已经把 UniDD 参照数据、参数换算、脚本模板和自动比对/出图工具备齐。缺的只是**在装有 SCAPS 的机器上执行一次**——这一步需要你安装软件并核对脚本命令名，本轮环境无法代跑，也不代为声称验证完成。
