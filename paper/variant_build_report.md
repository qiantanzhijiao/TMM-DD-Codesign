# 两版投稿包构建报告

生成时间：09 November 2026

| 版本 | 目录 | LaTeX | PDF | Word | Highlights | Cover letter |
|---|---|---|---|---|---|---|
| Computer Physics Communications | `soldiff/paper/cpc/` | `unidd_cpc.tex` | `unidd_cpc.pdf` | `unidd_cpc.docx` | `.txt/.docx` | `.tex/.pdf/.docx` |
| Solar Energy | `soldiff/paper/solar_energy/` | `unidd_solar_energy.tex` | `unidd_solar_energy.pdf` | `unidd_solar_energy.docx` | `.txt/.docx` | `.tex/.pdf/.docx` |

v1 原稿已备份为 `soldiff/paper/solar_energy/unidd_solar_energy_v1.tex.bak`。

## 两版共同的修订

- 标题降调；摘要首句改为方法学陈述，移除 27.74% 的突出展示，改称 internal numerical benchmark。
- 明确 ∂PV / DriftJax 使用 Beer–Lambert、TFSolver 不含载流子输运。
- Data availability 写入真实 GitHub 仓库地址（MIT）；CPC 版按官方模板把 CPC Library link 留给 Technical Editor。保留 Generative AI disclosure。
- 与 ∂PV / DriftJax / TFSolver 的关系移入引言（Four developments），Limitations 恢复四类。
- q/4、q/5 核对后的修正：Table 5 分数方向、1.10×/1.22× 口径、Program Summary 官方字段、DriftJax 版本 DOI、通讯作者标注、pre-specified。
- 第 4 轮（SCAPS 交叉验证）：本机 SCAPS 3.3.12 因缺 cvirte.dll 未能执行；该轮结论保留在历史记录中。
- 第 5 轮（运行库解决 + 真实交叉验证）：从官方 UGent 完整包私有部署 22 个 CVI runtime 文件（免管理员权限），A/B 两层全部跑通，产出暗态/光照 J–V、QE、G(x) readback、4 张原生 PNG 与诊断日志。按数据产生前固定的判据判定：暗态 J–V 与 G(x) readback PASS，光照 J–V 与 EQE FAIL，总体 2/4 未通过。两版新增 Section「Cross-code comparison with SCAPS-1D」及验收表，Limitations、Data availability、CPC Program Summary、Cover letter 同步改为「有限的跨代码 sanity check，不构成验证」；E4/E4-H/E4-C/E5 数值与结论一字未动。
- 第 6 轮（文献/主张一致性 + 光学消融）：联网核验 23 条文献、24 个 DOI（CrossRef 20 条 + DataCite 4 条），全部真实；补正 DriftJax 第一作者归属（Benaissa et al.），收紧摘要与引言的 novelty 口径以区分 Sol(Di)$^2$T 等代理类数字孪生，结论段改 `numerically validated`，SCAPS 暗态判据按仓库真源补全 OR 分支与 212.10% 相对误差，并把此前已入库但未引用的光学消融写入两版新增 subsection「Scope of the coherent optical model」（参考器件 Jsc 差 0.0071%、梯度差 1.91%；15 组扫描最大梯度差 39.85%）。核验脚本扩到 179/179；E4/E4-H/E4-C/E5 数值与结论一字未动。
- 参考文献核校：Byrnes 补 v5 日期；[10] 补 SPIE 会议录版本；TFSolver 补止页 52061–52074；新增 DriftJax（第 23 条）。
- 未改动任何结果与预指定判定：E4 `not met`、E4-H 删失下界、8D 约 3× 全部保留。

## CPC 版专有

- `\journal{Computer Physics Communications}`、首行注释与 Word 页眉注记全部替换。
- 引言中 `in this journal` / `in Solar Energy` 改为中性表述，并把 ∂PV（CPC 272, 108232）作为该刊锚点。
- 新增 Program Summary（按 ∂PV 的 CPC 字段格式）。
- 摘要、Highlights、Cover letter 全部改为「可复现程序 + 数值算法 + 负结果可复现」的锚点。

## 需作者补全

- 仓库地址 https://github.com/qiantanzhijiao/TMM-DD-Codesign 已写入两版 Data availability 与 cover letter；CPC 版按官方模板把 CPC Library link 留给 Technical Editor。
- Zenodo 归档并回填 DOI；投稿前把仓库可见性改为 Public。
- 确认 Funding 声明是否需要补入基金号。
