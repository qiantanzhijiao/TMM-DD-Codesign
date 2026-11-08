# SCAPS-1D 交叉验证：本机实测状态、自动链路与验收口径

**编写日期**：2026-11-08（第 3 版，取代第 1、2 版）
**本版起因**：用户已把 SCAPS-1D 安装到 `D:\software\Scaps3312\Scaps3312`，要求完善交叉验证、查看数据是否满足、并写入论文。本轮实际检查了安装、核对了官方脚本手册、重写了自动化链，但**没能产出真实 SCAPS 数据**，原因见第 0 节。

---

## 0. 结论先行

| 问题 | 本轮结论 |
|---|---|
| SCAPS 装好了吗？ | **装了，但没装全**。`scaps3312.exe`、`Scapsdll.dll`、`gui3312.uir`、`def/`、`script/`、`spectrum/`、`generation/`、官方手册与 `scriptdescription3312.txt` 都在；压缩包 `Scaps3312.rar` 里只有这 3 个二进制文件。 |
| 能跑吗？ | **不能**。命令行启动 `scaps3312.exe unidd_smoke.script` 返回 `0xC0000135`（`STATUS_DLL_NOT_FOUND`），0.1 秒退出，无任何结果文件。`objdump -p` 显示静态导入 `cvirte.dll`；全盘搜索 `C:\` 与 `D:\` 均无此 DLL。 |
| 根因 | SCAPS 是 NI LabWindows/CVI 编译的程序，目标机必须装**版本匹配的 LabWindows/CVI Run-Time Engine**。NI 官方知识库 `kA00Z000000P6AXSA0` 明确给出这个原因和解法。这不是脚本问题，也不是权限问题；双击图标同样会失败。 |
| 需要用户做什么 | 安装与该 SCAPS 构建匹配的 CVI Run-Time Engine（3.3.12 常见于 2019/2020），或换用附带运行库的完整 SCAPS 发行包；把 `cvirte.dll` 放到 `scaps3312.exe` 同目录或系统路径即可（**不要**从第三方 DLL 站下载）。装好后跑第 4 节的一条命令。 |
| 本轮把交叉验证完善到什么程度 | 已按 3.3.12 官方语法写好**全自动链路**：器件 `.def`、用户 `G(x)` `.gen`、光谱 `.spe`、A/B/QE 脚本（含 SCAPS 原生出图）、一键驱动、结果解析、预指定判据的 PASS/FAIL 自动判定。所有命令逐行核对过官方命令表；解析器用官方 `.iv`/`.gen` 样例测过；判定链用 UniDD 参照数据自测 4/4 PASS，自测产物已删除，`export/` 目前为空。 |
| 数据满足验收判据吗？ | **无法判定**：`scaps_run/crosscheck_status.json` 记录 `not_performed / cvirte.dll missing`。`export/` 里没有任何 SCAPS 结果，也没有任何伪造或占位数据。UniDD 侧参照数据完整（7 份 CSV + 模板）。 |
| 能写进论文吗？ | **不能写「已与 SCAPS-1D 交叉验证」**。两版稿件的 Limitations 必须继续保留「未做 SCAPS-1D 交叉验证」。本轮只把**内部数值验证证据**（真实存在、可发表）补写进稿件，见《q4_q5_意见核对与修正说明.md》之后的本轮修订记录。 |

> **口径声明**：第 2 版 §5 的验收判据数值在本版**逐字保留、一个都没放宽**；本版只新增了自动判定实现、模型不对等归因说明，以及两处**输入构造错误**的更正（G(x) 单位、器件层数）。这两处更正是把输入改对，不是把判据改松；且更正发生在任何 SCAPS 数据产生之前，不属于事后改口径。

---

## 1. 本机环境与官方能力核实

### 1.1 实际安装清单

```
D:\software\Scaps3312\Scaps3312\
  scaps3312.exe          4,969,984 B
  Scapsdll.dll             213,504 B
  gui3312.uir            1,173,717 B
  SCAPS manual most recent.pdf   157 页
  scriptdescription3312.txt      官方脚本命令表（文件头写 version SCAPS 3.3.11）
  def/  script/  spectrum/  generation/  absorption/  results/ ...
```

- 安装目录名为 `Scaps3312`；手册正文出现「SCAPS3.3.12, October 2024」字样；`scriptdescription` 文件头仍写 3.3.11。**投稿或留档时以 `Help → About` 读到的实际版本号与 build 日期为准**，写进 `metadata.txt`。
- 第 2 版里「官网概览写 3.8、版本历史写 3.3.11」的版本号矛盾，在本机安装上不存在：这里就是 3.3.x 系列。

### 1.2 命令行驱动能力（手册 §10.1，已核实）

> "you can add extra arguments to this command line: a list of filenames to be loaded/executed before SCAPS starts … The order of execution is: first .def, then .act, .scaps, .spe, .gen, .sbf, .srf, and finally .script."

> "When no script file was found in the command line, SCAPS remains the same interactive program as it has always been."

即：命令行带 `.script` 时 SCAPS 会在启动阶段自动执行脚本。配合官方命令

```
set quitscript.quitSCAPS
set script_display_mode.fully_suppressed
set errorhandling.overwritefile
```

可以在无人工点击的情况下跑完并自行退出。第 2 版「只能 GUI 里手动点脚本」的描述已废弃。

### 1.3 脚本命令自动核对

`build_scaps_inputs.py` 会把 `scriptdescription3312.txt`（已固化到 `scaps_run/templates/`）解析成 `(command, arguments)` 集合，逐行比对生成的 `unidd_crosscheck.script`。本轮输出：

```
script syntax check: every command matches the official 3.3.12 table.
```

若将来换了 SCAPS 构建，先替换模板里的命令表，重新跑一次核对再整段执行。

---

## 2. 两处实质性更正

### 2.1 G(x) 单位换算写反了（重要）

第 2 版参数表写「产生率 m⁻³ s⁻¹ → cm⁻³ s⁻¹，除以 10⁶；导入 SCAPS 的 G(z) 用 cm⁻³ s⁻¹」，这是**错的**，而且 `unidd_parameters.csv` 里同一行自相矛盾。

SCAPS 官方 `generation/*.gen` 文件头写的是：

```
x (µm)    Geh (#/m3.s)
```

即 **SCAPS 用户产生率文件用 SI 单位 m⁻³ s⁻¹**，`x` 用 µm。UniDD 的 `scaps_reference/unidd_generation_profile.csv` 存的是 cm⁻³ s⁻¹。因此：

```
写入 .gen 的值 = UniDD CSV 值 × 1e6
从 SCAPS 回读的 .gen 转成比对 CSV 时 = ÷ 1e6
```

`build_scaps_inputs.py::build_gen()` 与 `run_scaps_crosscheck.py::parse_gen()` 已按此实现；`parameter_alignment.csv` 与 `.gen` 文件头都写明了换算。若沿用第 2 版的错误换算，G 会差 10⁶ 倍，Jsc 会完全对不上——这属于会毁掉整条验证的量级错误。

### 2.2 器件必须是单层，不是三层 p-i-n（重要）

读 `soldiff/soldiff/dd.py` 与 `device.py` 可以确认：UniDD 的漂移–扩散**只在吸收层上求解**（`dx = d_abs / (N-1)`，N=73），TiO₂/HTL 只进入 TMM 光学与接触边界值 `psi0 = VT·ln(n_contactL/ni)`、`psiL = -VT·ln(p_contactR/ni)`。

第 2 版让 SCAPS 建「3 层 + 前后接触」，会把两套不同的电学求解域拿来比，暗态 J–V 根本没有可比性。第 3 版改为：

| | UniDD | SCAPS 侧 |
|---|---|---|
| 电学求解域 | 单层吸收体 480 nm | **单层**吸收体 4.8e-7 m |
| ETL / HTL | 仅光学 + 边界 | 不建层 |
| 接触 | Dirichlet 载流子密度（左电子、右空穴） | 金属接触 + 表面复合速度（左 `Sn=1e5, Sp=1e-2`；右 `Sn=1e-2, Sp=1e5`） |
| 复合 | 单一 SRH，τn=τp=3e-7 s | 单一中性缺陷、能级在 Ei，`τ=1/(σ·vth·Nt)` 反推 `Nt=3.333e20 m⁻³`（σ=1e-19 m², vth=1e5 m/s），辐射/Auger 全关 |
| 光照方向 | ETL 侧 x=0 | `illuminated from : left` |

**必须如实说明的建模差异**：SCAPS 的金属接触/表面复合速度边界与 UniDD 的 Dirichlet 载流子密度边界在数学上**不等价**，离散格式（SCAPS 内部自适应网格 vs UniDD 均匀 73 点 SG）也不同。因此暗态 J–V、Voc、FF 属于「跨模型半定量对照」，不是逐点一致性检验。判据不放宽，但结果若不达标，论文里要逐项归因，不能静默改阈值，也不能只报一个百分数。

`unidd_crosscheck.def` 由官方 `simple pn.def` 模板生成：保留第一层、删掉第二层与界面块、逐项覆盖参数；`grep -c "^layer"` 结果为 **1**，无 `interface properties` 块。

---

## 3. 三层验证设计与判据（数值不变）

| 层 | 比什么 | 光学处理 | 目的 |
|---|---|---|---|
| **A（必做）** | 暗态 J–V | 关光照，不用 G(x) | 只比漂移–扩散内核与接触边界（承认边界模型不等价） |
| **B（必做）** | 光照 J–V、G(z) 回读 | 导入 UniDD 的 `G(x)` | 检查光学→电学耦合、单位换算与插值 |
| **B′（sanity）** | EQE 形状 | SCAPS 内部光学模型 | 只作形状/量级参考，**不纳入严格验收归因** |

### 预指定验收判据（逐字保留第 2 版 §5）

| 量 | 阈值 | 自动判定实现 |
|---|---|---|
| 暗态 J–V | 逐点相对误差 < 5% **或** 绝对误差 < 0.05 mA/cm² | `rmse < 0.05` 或 `mean_rel_pct < 5`（暗电流近零，优先用绝对误差分支） |
| 光照 Jsc | < 5% | `100·|Jsc_S - Jsc_U| / |Jsc_U| < 5` |
| Voc | < 2% / < 20 mV | `|Voc_S - Voc_U| < 0.020 V` |
| FF | < 5% | 两条曲线各自算 `Pmax/(|Jsc|·Voc)` 后比 |
| EQE 形状 | 峰值位置一致、RMSE < 0.05 | `rmse < 0.05`，标注「形状 sanity」 |
| G(z) 剖面 | 回读与 UniDD 剖面 RMSE < 2% | `rmse / mean(|ref|) < 2%` |

`compare_scaps.py` 现在输出 `acceptance_verdict.json` 与报告中的 PASS/FAIL 表，并在报告里写明「判据在任何 SCAPS 数据产生之前固定，不会在看到数据后放宽」。

---

## 4. 交付的工具链与运行方式

### 4.1 文件清单

| 文件 | 作用 | 状态 |
|---|---|---|
| `soldiff/build_scaps_inputs.py` | 从 UniDD 真源生成 `.def` / `.gen` / `.spe` / `.script` / 参数对齐表 / metadata 模板，并自动核对脚本命令 | 已生成、已核对 |
| `soldiff/run_scaps_crosscheck.py` | 一键：检查运行库 → 部署 → 启动 SCAPS → 收集 `.iv/.qe/.gen/PNG` → 解析成 CSV → 调比对 → 写状态 | 已干跑（当前返回 2，阻塞） |
| `soldiff/compare_scaps.py` | 误差量化 + 预指定判据 PASS/FAIL 自动判定 + 叠图 | 已增强、已自测 4/4 PASS |
| `soldiff/scaps_run/inputs/` | 6 个输入文件 | 已生成 |
| `soldiff/scaps_run/templates/` | 官方 `.def` / `.gen` / `.spe` / 命令表模板（固化，避免工具依赖本机绝对路径） | 已固化 |
| `soldiff/scaps_run/export/` | 真实 SCAPS 输出与比对报告的落地目录 | **当前为空** |
| `soldiff/scaps_run/crosscheck_status.json` | 机器可读状态：`not_performed / cvirte.dll missing` | 已写入 |
| `scaps_reference/` | UniDD 侧参照数据（**不是 SCAPS 结果**） | 完整，7 份 CSV + 模板 |

### 4.2 装好运行库后的一键命令

```bash
cd C:/Users/yangp/WorkBuddy/2026-11-06-18-31-56/soldiff

# 1) 重新生成输入（可选，参数有改动时才需要）
python build_scaps_inputs.py --deploy \
    --scaps-dir "D:/software/Scaps3312/Scaps3312"

# 2) 全自动跑 A 层暗态、B 层导入 G(x) 光照、QE sanity，出 SCAPS 原生 PNG，
#    解析结果并按预指定判据判定
python run_scaps_crosscheck.py \
    --scaps-dir "D:/software/Scaps3312/Scaps3312"
```

驱动脚本会：

1. 在 exe 同目录、System32/SysWOW64、PATH 里找 `cvirte.dll`；找不到就直接退出码 2 并写 `not_performed`，**不会伪造数据**；
2. 把输入部署到 `def/`, `generation/`, `spectrum/`, `script/`；
3. 以 `scaps3312.exe <abs path to .script>` 启动，等待退出（默认 900 s，超时 kill 并记状态）；
4. 扫描所有新增/更新的 `unidd_*` 文件，复制进 `export/`（含 SCAPS 自己生成的 PNG）；
5. 把 `.iv` / `.qe` / 回读 `.gen` 转成 `dark_JV.csv` / `light_JV.csv` / `EQE.csv` / `generation_profile.csv`；
6. 写 `metadata.txt`，调用 `compare_scaps.py` 输出 `scaps_comparison.md`、`.png`、`acceptance_verdict.json`；
7. 把结果写进 `crosscheck_status.json`（`completed` + `all_pass`）。

### 4.3 派生稿件的判定门槛

只有同时满足以下条件，才允许把「已与 SCAPS-1D 交叉验证」写进论文：

- `crosscheck_status.json` 的 `state == "completed"`；
- `acceptance_verdict.json` 的 `all_pass == true`，或明确列出未通过项并在论文里逐项归因；
- `export/` 里 `.iv ×2`、`.qe`、回读 `.gen`、SCAPS 原生 PNG 齐全；
- `metadata.txt` 填了实际版本号、build 日期、运行库版本与操作人；
- 误差表与叠图已留档。

**任何一条不满足，稿件 Limitations 保持原表述。**

---

## 5. 边界与风险

- 本轮**没有产出任何真实 SCAPS 数据**。`export/` 为空，自测用的假数据已删除；`scaps_reference/` 里的 CSV 全是 UniDD 侧数据，命名不要混淆。
- 缺的是 NI 运行库，不是 SCAPS 缺文件、不是脚本语法错、不是权限问题。NI 官方解法见 `kA00Z000000P6AXSA0`；**不建议**从第三方 DLL 下载站补 `cvirte.dll`。
- 运行库版本必须与编译该 SCAPS 的 CVI 版本匹配；装错版本可能出现 `the executable is linked to a missing export` 或 `0x7E`。若出现，先查 VC++ Redistributable 与架构（32/64 位）。
- 即使运行库装好，A 层也**不保证**逐点对得上：接触边界模型不等价、网格离散不同。这正是交叉验证要暴露的信息，不是失败到需要改判据的理由。
- SCAPS 许可一般限学术非商业用途，导出数据用于论文需遵守其引用要求（Burgelman 等，*Thin Solid Films* 361–362 (2000) 527–532，稿件已列 `[burgelman2000]`）。
- 零成本的内部替代证据（Richardson 外推、单通光学对照、E0/E1/E2）可作为**内部一致性**写进论文，但**不能替代**跨代码验证。
- 可脚本化的其它跨代码验证：Sesame、Solcore、Driftfusion / IonMonger、wxAMPS；本机均未安装，属后续工作。

---

## 6. 一句话总结

SCAPS 3.3.12 装在本机但缺 `cvirte.dll`，所以**本轮跑不出真实交叉验证数据，也不能写进论文**；本轮把整条链路按官方 3.3.12 语法做成了「装好运行库即一键跑完并自动判定」，并更正了 G(x) 单位与器件层数两处会毁掉验证的错误。验收判据一个数值都没改。
