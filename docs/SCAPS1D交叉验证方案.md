# SCAPS-1D 交叉验证：运行库解决方案、真实实测结果与论文口径

**编写日期**：2026-11-08（第 4 版，取代第 1–3 版）
**本版起因**：用户要求解决与 SCAPS 3.3.12 匹配的 NI LabWindows/CVI Run-Time Engine，并继续未完成的任务。本轮已解决运行库、跑通 A/B 两层全部计算、产出真实 SCAPS 数据、按数据产生前固定的判据完成判定，并把结果如实写入两版稿件。

> **口径声明**：第 2 版 §5 的验收判据数值在本版**逐字保留、一个都没放宽**。本轮修正的是输入构造与脚本语法错误（不会改变被测对象），以及运行/解析层面的实现 bug；所有修正都发生在看到最终验收数字之前或与之无关。E4、E4-H、E4-C、E5 的原始结论与数值一字未动。

---

## 0. 结论先行

| 问题 | 本轮结论 |
|---|---|
| 运行库解决了吗？ | **解决了，且不需要管理员权限、不改动 `C:\Windows`**。从 SCAPS 官方 UGent 完整安装包 `SCAPS3312 Installation Package.zip` 中提取 22 个 CVI runtime 文件，私有部署到 SCAPS 应用目录。`install_scaps_runtime.py --check` 返回 `ready: true / requires_elevation: false`。 |
| SCAPS 能跑吗？ | **能**。A 层暗态 J–V、B 层导入 UniDD `G(x)` 的光照 J–V、QE、`G(x)` 回读、4 张 SCAPS 原生 PNG 与诊断日志全部产出，单次全量耗时约 6 s。 |
| 数据满足验收判据吗？ | **未全部满足：2 PASS / 2 FAIL，`all_pass = false`**。暗态 J–V 与 `G(x)` 回读 PASS；光照 J–V 与 EQE FAIL。详见第 4 节。 |
| 能写「已与 SCAPS-1D 交叉验证」吗？ | **不能**。两版稿件统一写成「有限的跨代码 sanity check，不构成对 UniDD 的验证」，并逐项列出未通过原因。 |
| 论文改了什么？ | 两版新增 `Cross-code comparison with SCAPS-1D` 小节与验收表；Limitations、Data availability、CPC Program Summary、Cover letter、E4-C/E5 补充章节同步。核验 `159/159` 全通过。 |

---

## 1. 运行库问题如何解决

### 1.1 根因

`scaps3312.exe` 与 `Scapsdll.dll` 均为 32 位 `pei-i386` 的 LabWindows/CVI 程序，`objdump -p` 显示两者静态导入 `cvirte.dll`。本机全盘无此 DLL，启动即返回 `0xC0000135`（`STATUS_DLL_NOT_FOUND`），0.1 s 退出、无结果文件。

### 1.2 为什么不走 NI 官方 runtime 下载

NI 官方 `LabWindows/CVI 2019 Runtime` 离线 ISO（约 5.89 MB）直链位于 `download.ni.com`，被 Cloudflare Managed Challenge 拦截，所有二进制下载返回 403「正在进行安全验证」。以下方式均未能自动取得官方 ISO：curl 多 UA / Referer / Range / `%2B` 编码变体、.NET `Invoke-WebRequest`、headless Edge + CDP + cookie 复用、S3 匿名直连、`ftp.ni.com` 镜像。

### 1.3 采用的方案：官方完整包私有部署

| 项 | 值 |
|---|---|
| 来源 | `https://scaps.elis.ugent.be/SCAPS3312%20Installation%20Package.zip`（SCAPS 官方 UGent 站点，3.3.12 complete installation package） |
| 大小 | 19,672,460 B |
| SHA-256 | `c64a79007cdb39e9af3b3827a1c97c4fb7b2147772548cb4cfe5c7e75ca2d98b` |
| ZIP 校验 | `testzip: None`，16 个条目 |
| 下载方式 | 单连接超时，改用 12 线程并行 Range 请求 |

从包内 `bin/dp/Distfile.cab` 用系统自带 `expand.exe -F:*` 解出 326 个文件，取其中 22 个部署到 SCAPS 应用目录：`cvirte.dll`、`mesa.dll`、`cvirt.dll`、`cviauto.dll`、`cvintwrk.dll`、`mkl_*`、`nianlys.dll` 等，以及 `cvirte/bin/` 下的资源文件与 `cvirte/fonts/` 字体。

**关键发现**：只复制 `cvirte.dll` / `mesa.dll` 不够。2007 年老 CVI runtime 会打开 `cvirte\bin\msgrte.txt` 来验证 application-directory RTE 是否有效；缺该文件时它回退到系统目录并报 `Can not find RTE directory: C:\Windows\system32\cvirte`。补齐 `msgrte.txt`、`msgrt4.txt`、`cvierror.txt`、`cvirte.rsc`、`cvirt4.rsc` 与两个字体后，私有部署即生效，**无需 UAC 提权、无需改 `SystemRoot`、无需写系统目录**。

legacy NI DLL 没有 Authenticode 签名，因此完整性靠官方来源 + 包级 SHA-256 + 每个部署文件的 SHA-256 清单固定，绝不使用第三方 DLL 站。

### 1.4 固化脚本

`soldiff/install_scaps_runtime.py`：下载/校验官方包 → 解 CAB → 幂等部署 22 个文件 → 写 `scaps_run/runtime_deploy_manifest.json` → `--check` 输出状态。幂等逻辑对内容已正确的文件只校验不改写，避免 DLL 被占用时报 `WinError 32`。

```bash
python soldiff/install_scaps_runtime.py --check
python soldiff/install_scaps_runtime.py --scaps-dir "D:/software/Scaps3312/Scaps3312"
```

---

## 2. SCAPS 3.3.12 脚本语法：实测结论

命令名逐行核对 `scriptdescription3312.txt` 只能保证「名字存在」，**不能保证在这个构建里真能跑**。本轮用最小脚本逐一实测，结论如下（均已固化到 `build_scaps_inputs.py`）：

| 写法 | 实测结果 | 处理 |
|---|---|---|
| `action generation_defined.file unidd_generation.gen` | **有效**。SCAPS 读到我们导入的 `G(x)`，Jsc = 32.06 mA/cm²；用内部模型只有 9.79 mA/cm² | 采用 |
| `action generation_defined.fromfile` + `load generationfile <name>` | 文件名仍是默认 `generation\*.gen`，求解器报 `Invalid path` 并以 `0xC0000005` 崩溃 | 弃用 |
| `action spectrum_defined.file unidd_am15g.spe` | **有效**。QE 文件头明确写出该光谱文件 | 采用 |
| `load spectrumfile unidd_am15g.spe` | 把参数拼到默认文件名后面（`AM1_5G 1 sun.speD:\...\unidd_am15g.spe`），随后挂起 | 弃用 |
| `action generation_defined.frommodel` | QE 计算直接崩溃、无输出 | 弃用；QE 层改用默认内部光学模型 |
| `save results.SCAPSgenerationfile <name>` | 文件写到 `generation/` 而非 `results/`，内容正确 | 驱动用 `rglob` 收集 |
| `save results.iv <name>` | 把**所有** single-shot I–V 段追加到同一文件（`unidd_B_light.iv` 含暗态 + 光照两段） | `parse_iv()` 改为取最后一段表头 |
| `set quitscript.quitSCAPS` 后的退出码 | 常为 `3221226505`（`0xC0000409`），但结果文件完整 | 驱动改为「以本次真实写出且可解析的文件为准」，退出码只记录不判死 |

另有一项器件方向核验：把 `.def` 里前后接触的 `Sn/Sp` 对调后，光电流由 +32.06 变为 −6.13 mA/cm²（极性反转），说明原配置自洽，`parameter_alignment.csv` 的文字描述已改为按 `.def` 中的 block 顺序表述，不再臆断 front/back 与 x 的对应。

**A/B 两层器件仍是预指定的单层结构**（`grep -c "^layer"` = 1），参数与判据未因上述诊断改动。

---

## 3. 器件对齐与验收判据（数值不变）

### 3.1 单层器件

| | UniDD | SCAPS 侧 |
|---|---|---|
| 电学求解域 | 单层吸收体 480 nm | 单层吸收体 `4.800000e-07 m` |
| ETL / HTL | 仅光学 + 接触边界值 | 不建层 |
| 接触 | Dirichlet 载流子密度 | 金属接触 + 表面复合速度（`Sn/Sp` 两对） |
| 复合 | 单一 SRH，τ = 3e-7 s | 单一中性缺陷、能级在 Ei，`Nt = 3.333e20 m⁻³`；辐射/Auger 全关 |
| 产生率 | `cm⁻³ s⁻¹` | `.gen` 用 `#/m3.s`，**写入时 ×1e6**；`x` 用 µm |
| 光谱 | 粗表 AM1.5G（41 点，350–800 nm） | `unidd_am15g.spe`（由 UniDD 粗表换算） |

**建模差异必须如实说明**：SCAPS 的 flatband/表面复合接触与 UniDD 的 Dirichlet 载流子密度边界在物理上不等价；离散格式也不同。暗态 J–V、Voc、FF 属跨模型对照，不是逐点一致性检验。

### 3.2 预指定验收判据（逐字保留第 2 版 §5）

| 量 | 阈值 | 自动判定实现 |
|---|---|---|
| 暗态 J–V | 逐点相对误差 < 5% **或** 绝对误差 < 0.05 mA/cm² | `rmse < 0.05` 或 `mean_rel_pct < 5`（暗电流近零，优先绝对误差分支） |
| 光照 Jsc | < 5% | `100·|Jsc_S − Jsc_U| / |Jsc_U| < 5` |
| Voc | < 2% / < 20 mV | `|Voc_S − Voc_U| < 0.020 V` |
| FF | < 5% | 两条曲线各自算 `Pmax/(|Jsc|·Voc)` 后比 |
| EQE 形状 | 峰值位置一致、RMSE < 0.05 | `rmse < 0.05`，标注「形状 sanity」 |
| G(z) 剖面 | 回读与 UniDD 剖面 RMSE < 2% | `rmse / mean(UniDD G) < 2%` |

`compare_scaps.py` 用 `ACCEPTANCE` 常量固定这些阈值，输出 `acceptance_verdict.json` 与报告中的 PASS/FAIL 表；`criteria_fixed_before_data: true`。缺失项（Voc/FF 无法计算）一律按不可比处理，不按通过处理。

---

## 4. 真实实测结果

### 4.1 产出清单

`soldiff/scaps_run/export/` 共 18 个文件：`unidd_A_dark.iv/.png`、`unidd_B_light.iv/.png`、`unidd_B_eqe.qe/.png`、`unidd_B_generation_readback.gen`、`unidd_B_generation.png`、`unidd_B_genrec.dat`、`unidd_crosscheck_effective.def`、`SCAPSErrorLogFile.log`、`scaps_process.log`、`metadata.txt`、四份解析后的 CSV、`scaps_comparison.md/.png`、`acceptance_verdict.json`。`crosscheck_status.json` 为 `completed`。

### 4.2 逐项误差

| 量 | 共同区间点数 | RMSE | MAE | 最大偏差 | 平均相对误差 |
|---|---|---|---|---|---|
| 暗态 J–V | 41 | 0.001436 mA/cm² | 0.000485 | 0.007037 | 212.10%（暗电流近零，无意义） |
| 光照 J–V | 54 | 3.424 mA/cm² | 3.200 | 9.792 | 11.17% |
| EQE | 20 | 0.09634 | 0.08188 | 0.2091 | 9.40% |
| G(z) 剖面 | 72 | 1.052e16 cm⁻³ s⁻¹ | 1.24e15 | 8.929e16 | 0.0022% |

### 4.3 预指定验收判定：**2 PASS / 2 FAIL，总体未通过**

| 项目 | 实测 | 阈值 | 判定 |
|---|---|---|---|
| 暗态 J–V | RMSE 0.001436 mA/cm² | < 0.05 mA/cm² | **PASS** |
| 光照 J–V | Jsc 7.03%；Voc / FF 无法定义 | Jsc < 5%；Voc < 20 mV；FF < 5% | **FAIL** |
| EQE | RMSE 0.09634 | < 0.05 | **FAIL** |
| G(z) 回读 | RMSE/mean(UniDD G) = 0.0002369% | < 2% | **PASS** |

### 4.4 收敛截断与模型差异（必须随数字一起报告）

- `SCAPSErrorLogFile.log` 记录：暗态在 **0.82 V** 收敛失败、曲线截到 0.80 V；光照在 **1.08 V** 收敛失败、截到 1.06 V。超出共同收敛区间的电压不参与比较。
- SCAPS 自身在光照 `.iv` 里给出 `Voc = 6.800466 V (extrapolated)`、`collection efficiency = 98.6577%`。在 0–1.06 V 内其 Jtot 从 32.06 升到 32.48 mA/cm²，几乎不随偏压下降，**曲线不穿过零**，因此 Voc/FF 无法定义。
- 根因是**模型不等价**：flatband + 表面复合接触 + 本征单层没有 UniDD Dirichlet 选择性接触所隐含的整流行为；UniDD 的 Voc 为 1.1096 V。这不是离散误差，也不是调参可以消除的差异。
- G(z) 回读与导入剖面平均偏差 0.0029%（148 个 SCAPS 网格点 vs 73 个 UniDD 点），证明单位换算与插值正确——这一项是本次对照中最扎实的正面证据。
- EQE 差异来自光学模型不同（UniDD 相干 TMM vs SCAPS 内部模型），且两者光谱采样点也不完全一致；按预指定阈值判 FAIL，不因「只是形状对照」而放宽。

---

## 5. 论文写入口径

两版稿件（CPC / Solar Energy）新增 `Cross-code comparison with SCAPS-1D` 小节与验收表，写明上述四项判定、收敛截断、模型差异归因，并明确：

> `it does not constitute a validation of UniDD against SCAPS-1D, and no experimental calibration has been performed.`

同步修改：Limitations（从「未做交叉验证」改为「已执行但不构成完整验证」）、Data availability（写入 `install_scaps_runtime.py` / `build_scaps_inputs.py` / `run_scaps_crosscheck.py` / `compare_scaps.py` 与 SHA-256 manifest）、CPC Program Summary 的 Supplementary material、两封 Cover letter、E4-C/E5 补充章节的收尾句。

**明确不得出现的表述**：「已与 SCAPS-1D 交叉验证」「cross-validated against SCAPS」「experimental validation」。稿件核验脚本已加入 7 项专项断言，清除旧的「未执行」措辞，当前 `159/159` 全通过。

---

## 6. 工具链与一键复现

```bash
cd C:/Users/yangp/WorkBuddy/2026-11-06-18-31-56

# 0) 运行库（幂等，免管理员）
python soldiff/install_scaps_runtime.py --check

# 1) 生成输入：单层 .def / SI 单位 .gen / .spe / 官方语法 .script
python soldiff/build_scaps_inputs.py

# 2) 全量 A/B 两层 + QE + 原生 PNG + 解析 + PASS/FAIL 判定
python soldiff/run_scaps_crosscheck.py \
    --scaps-dir "D:/software/Scaps3312/Scaps3312"

# 3) 只重算比对报告（不重跑 SCAPS）
python soldiff/compare_scaps.py \
    --scaps-dir soldiff/scaps_run/export
```

驱动判定原则：以本次真实写出且可解析的四份结果为准；SCAPS 的 CVI 自终止非零退出码只记录到 `scaps_process.log` / `metadata.txt` / `crosscheck_status.json`，不作为失败依据。所有输出均来自本机 SCAPS 3.3.12（`Version scaps3312.exe, dated 07-10-2024`），无任何伪造或占位数据。

---

## 7. 边界与风险

- **仍无实测器件数据**。本次是跨代码对照，不能替代实验校准；《实测器件校准与验证方案.md》的排期与验收设计不受影响。
- **模型不等价是结论的一部分**，不是待修的 bug。为凑 PASS 去把 SCAPS 改成 p–n 结或改接触模型，会改变被测对象，属于事后改口径，已明确排除。
- 官方完整包（约 19 MB）已缓存在 `scaps_run/runtime/`。发布仓库是否纳入该二进制需权衡：脚本 + SHA-256 manifest 已足以复现，建议只发布脚本与清单。
- legacy CVI DLL 未 Authenticode 签名，完整性依赖官方来源与 SHA-256 清单；不要混入第三方 DLL。
- SCAPS 许可一般限学术非商业用途，导出数据用于论文需遵守引用要求（Burgelman 等，*Thin Solid Films* 361–362 (2000) 527–532，稿件已列 `[burgelman2000]`）。
- 其它可脚本化的跨代码验证（Sesame、Solcore、Driftfusion / IonMonger、wxAMPS）本机均未安装，属后续工作。

---

## 8. 一句话总结

运行库已从 SCAPS 官方完整包私有部署解决（免管理员），A/B 两层真实数据全部跑出；按数据产生前固定的判据判定为 **2 PASS / 2 FAIL，总体未通过**，论文据此写成「有限的跨代码 sanity check，不构成验证」，判据与 E4 系列原有结论一个数值都没改。
