"""
Assess the cost of moving the production DD mesh from N=73 to N>=97.

This script does NOT re-run the validation suite.  Changing the production
mesh changes EVERY reported number (Jsc, Voc, FF, PCE, EQE, gradients, inverse
design, all five figures, four tables, both journal variants and the cover
letters), so it is a decision for the authors, not a silent background edit.
What this script does is lay out the evidence and the exact re-run checklist,
using only the recorded result files.

Run:  python experiments_mesh_N97.py
Out:  mesh_N97_plan.md, mesh_N97_plan.json
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
F = json.loads((ROOT / "results_final.json").read_text(encoding="utf-8"))
S = json.loads((ROOT / "results_supplement.json").read_text(encoding="utf-8"))

rows = S["mesh"]
by_n = {r["N_dd"]: r for r in rows}
n73, n97, n121, n145 = (by_n[n] for n in (73, 97, 121, 145))

impact = {
    "production_N": 73,
    "candidate_N": 97,
    "Jsc": {"N73": n73["Jsc"], "N97": n97["Jsc"],
            "abs_change_mA_cm2": n97["Jsc"] - n73["Jsc"],
            "rel_change_pct": 100 * (n97["Jsc"] - n73["Jsc"]) / n73["Jsc"]},
    "Voc": {"N73": n73["Voc"], "N97": n97["Voc"],
            "abs_change_V": n97["Voc"] - n73["Voc"]},
    "FF": {"N73": n73["FF"], "N97": n97["FF"]},
    "PCE": {"N73": n73["PCE"], "N97": n97["PCE"],
            "rel_change_pct": 100 * (n97["PCE"] - n73["PCE"]) / n73["PCE"]},
    "richardson_extrapolated_Jsc": S["Jsc_richardson_extrapolated"],
    "observed_order": S["observed_order"],
    "production_rel_error_vs_extrapolated_pct":
        100 * S["production_Jsc_rel_error_vs_extrapolated"],
    "N73_to_N97_rel_change_pct": 100 * S["production_vs_next_refinement_rel_change"],
}

checklist = [
    "把 experiments_final.py 的 N_DD 由 73 改为 97，并把输出重定向到新的结果文件（绝不可覆盖 results_final.json）",
    "重跑 E0--E4 全套；E1 的伴随规模由 3(N-2)=213 变为 285，梯度与容差扫描需重新核验",
    "重跑 experiments_supplement.py 的网格收敛，确认 N=97 相对 Richardson 外推的误差",
    "重跑 experiments_E4_highdim.py 与新增的单因子/基线实验（网格变化会改变每次 f() 的代价与历史）",
    "重新生成 5 张图与 4 张表（make_figures.py 从结果文件派生，不能沿用手写数字）",
    "重新生成 CPC 与 Solar Energy 两版 LaTeX/PDF/Word、Highlights、Cover letter，并替换正文全部数值",
    "重跑 verify_variants.py（两版）与 check_consistency.py（v1 归档），全部通过后再更新摘要",
    "同步更新 实验设计方案.md、稿件中的 1.52% 离散不确定度表述与 Limitations",
    "保留 N=73 版本的归档，便于审稿人复现投稿时的数字",
]

alternatives = [
    "不重跑全链，改用 Richardson 外推值 30.412 mA/cm2 作为网格无关性声明，并明确生产网格误差 1.52%（成本最低，推荐先做）",
    "只把 E2 的网格收敛研究扩展到 N=145（已完成），把结论写成误差界而非改生产网格",
    "若确要加密，优先改 E2 的指标输出而非整个反演链，避免与 E3/E4 的预注册历史冲突",
]

plan = {
    "status": "ASSESSMENT ONLY -- no experiment re-run, no result file overwritten",
    "impact": impact,
    "why_not_silent": ("The production mesh enters the DD Jacobian size, the "
                       "optical field evaluation nodes, every reported metric, "
                       "the IFT adjoint and all inverse-design histories."),
    "rerun_checklist": checklist,
    "lower_cost_alternatives": alternatives,
    "recommendation": ("Adopt the Richardson-based grid-independence statement "
                       "for the current submission. Run the full N=97 chain only "
                       "if a reviewer explicitly requires a finer production grid; "
                       "budget roughly 4x the 24.8 min baseline plus figure, "
                       "manuscript and consistency regeneration."),
}

(ROOT / "mesh_N97_plan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
lines = [
    "# 生产网格 N=73 → N≥97 的影响评估与重跑清单", "",
    "**状态：仅评估，未重跑、未覆盖任何结果文件。**", "",
    "## 数值影响（来自 `results_supplement.json`）", "",
    "| 量 | N=73 | N=97 | 变化 |", "|---|---|---|---|",
    f"| Jsc (mA/cm²) | {n73['Jsc']:.4f} | {n97['Jsc']:.4f} | {impact['Jsc']['rel_change_pct']:+.2f}% |",
    f"| Voc (V) | {n73['Voc']:.4f} | {n97['Voc']:.4f} | {impact['Voc']['abs_change_V']:+.4f} |",
    f"| FF | {n73['FF']:.4f} | {n97['FF']:.4f} | — |",
    f"| PCE (%) | {100*n73['PCE']:.4f} | {100*n97['PCE']:.4f} | {impact['PCE']['rel_change_pct']:+.2f}% |",
    "",
    f"- Richardson 外推 Jsc = {S['Jsc_richardson_extrapolated']:.4f} mA/cm²，观测阶 {S['observed_order']:.2f}。",
    f"- 生产网格 N=73 相对外推误差 {impact['production_rel_error_vs_extrapolated_pct']:.2f}%；73→97 仅变化 {impact['N73_to_N97_rel_change_pct']:.2f}%。",
    "", "## 为什么不能只改一个数字", "", plan["why_not_silent"], "",
    "## 若决定重跑，必须依次完成", "",
] + [f"{i}. {c}" for i, c in enumerate(checklist, 1)] + [
    "", "## 更低成本的替代", "",
] + [f"- {a}" for a in alternatives] + [
    "", "## 建议", "", plan["recommendation"], "",
]
(ROOT / "mesh_N97_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Jsc 73->97: {impact['Jsc']['rel_change_pct']:+.2f}% ; "
      f"Richardson {S['Jsc_richardson_extrapolated']:.3f} ; "
      f"production error {impact['production_rel_error_vs_extrapolated_pct']:.2f}%")
print("-> mesh_N97_plan.md / .json")
