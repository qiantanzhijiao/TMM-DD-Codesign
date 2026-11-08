# 两版投稿包构建报告

生成时间：08 November 2026

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
- 参考文献核校：Byrnes 补 v5 日期；[10] 补 SPIE 会议录版本；TFSolver 补止页 52061–52074；新增 DriftJax（第 23 条）。
- 未改动任何结果与预注册判定：E4 `not met`、E4-H 删失下界、8D 约 3× 全部保留。

## CPC 版专有

- `\journal{Computer Physics Communications}`、首行注释与 Word 页眉注记全部替换。
- 引言中 `in this journal` / `in Solar Energy` 改为中性表述，并把 ∂PV（CPC 272, 108232）作为该刊锚点。
- 新增 Program Summary（按 ∂PV 的 CPC 字段格式）。
- 摘要、Highlights、Cover letter 全部改为「可复现程序 + 数值算法 + 负结果可复现」的锚点。

## 需作者补全

- 仓库地址 https://github.com/qiantanzhijiao/TMM-DD-Codesign 已写入两版 Data availability 与 cover letter；CPC 版按官方模板把 CPC Library link 留给 Technical Editor。
- Zenodo 归档并回填 DOI；投稿前把仓库可见性改为 Public。
- 确认 Funding 声明是否需要补入基金号。
