# 生产网格 N=73 → N≥97 的影响评估与重跑清单

**状态：仅评估，未重跑、未覆盖任何结果文件。**

## 数值影响（来自 `results_supplement.json`）

| 量 | N=73 | N=97 | 变化 |
|---|---|---|---|
| Jsc (mA/cm²) | 29.9499 | 30.1639 | +0.71% |
| Voc (V) | 1.1096 | 1.1083 | -0.0013 |
| FF | 0.8347 | 0.8326 | — |
| PCE (%) | 27.7371 | 27.8321 | +0.34% |

- Richardson 外推 Jsc = 30.4125 mA/cm²，观测阶 2.72。
- 生产网格 N=73 相对外推误差 1.52%；73→97 仅变化 0.71%。

## 为什么不能只改一个数字

The production mesh enters the DD Jacobian size, the optical field evaluation nodes, every reported metric, the IFT adjoint and all inverse-design histories.

## 若决定重跑，必须依次完成

1. 把 experiments_final.py 的 N_DD 由 73 改为 97，并把输出重定向到新的结果文件（绝不可覆盖 results_final.json）
2. 重跑 E0--E4 全套；E1 的伴随规模由 3(N-2)=213 变为 285，梯度与容差扫描需重新核验
3. 重跑 experiments_supplement.py 的网格收敛，确认 N=97 相对 Richardson 外推的误差
4. 重跑 experiments_E4_highdim.py 与新增的单因子/基线实验（网格变化会改变每次 f() 的代价与历史）
5. 重新生成 5 张图与 4 张表（make_figures.py 从结果文件派生，不能沿用手写数字）
6. 重新生成 CPC 与 Solar Energy 两版 LaTeX/PDF/Word、Highlights、Cover letter，并替换正文全部数值
7. 重跑 verify_variants.py（两版）与 check_consistency.py（v1 归档），全部通过后再更新摘要
8. 同步更新 实验设计方案.md、稿件中的 1.52% 离散不确定度表述与 Limitations
9. 保留 N=73 版本的归档，便于审稿人复现投稿时的数字

## 更低成本的替代

- 不重跑全链，改用 Richardson 外推值 30.412 mA/cm2 作为网格无关性声明，并明确生产网格误差 1.52%（成本最低，推荐先做）
- 只把 E2 的网格收敛研究扩展到 N=145（已完成），把结论写成误差界而非改生产网格
- 若确要加密，优先改 E2 的指标输出而非整个反演链，避免与 E3/E4 的预注册历史冲突

## 建议

Adopt the Richardson-based grid-independence statement for the current submission. Run the full N=97 chain only if a reviewer explicitly requires a finer production grid; budget roughly 4x the 24.8 min baseline plus figure, manuscript and consistency regeneration.

