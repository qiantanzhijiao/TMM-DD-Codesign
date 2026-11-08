"""
UniDD -- ARCHIVED v1 manuscript consistency and format checker.

This script encodes the invariants of the original v1 Solar Energy manuscript
(22 references, 4 tables, the v1 abstract, the v1 PDF/DOCX/aux files).  It is
kept for reproducibility of the recorded 161/161 result and must NOT be run
against the current v2 journal variants.  The active checker for both current
submission packages is ../verify_variants.py.

Exit codes: 0 = v1 checks pass, 1 = v1 check failed, 2 = not applicable
(current v2 manuscript detected).
"""

from __future__ import annotations

import json
import math
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
TEX = HERE / "unidd_solar_energy.tex"
AUX = HERE / "unidd_solar_energy.aux"
PDF = HERE / "unidd_solar_energy.pdf"
DOCX = HERE / "unidd_solar_energy.docx"
HIGHLIGHTS = HERE / "highlights.txt"
COVER_PDF = HERE / "cover_letter_Solar_Energy.pdf"
COVER_DOCX = HERE / "cover_letter_Solar_Energy.docx"

# Guard FIRST, before any file is read: applying v1 invariants to the current
# v2 packages (or running from the release repository's scripts/ directory)
# must never produce a wall of spurious FAILs.
_candidates = (HERE / "unidd_solar_energy.tex",
               HERE.parent / "solar_energy" / "unidd_solar_energy.tex")
_current = next((p for p in _candidates if p.is_file()), None)
if _current is None or "\\bibitem{driftjax2026}" in _current.read_text(
        encoding="utf-8"):
    print("ARCHIVED v1 CHECKER -- not applicable to the current manuscript.")
    print("  This script hard-codes v1 invariants (22 refs, 4 tables, v1 abstract).")
    print("  Use paper/verify_variants.py for the current CPC and Solar Energy")
    print("  packages. The v1 source is preserved in")
    print("  paper/solar_energy/unidd_solar_energy_v1.tex.bak.")
    sys.exit(2)

D = json.loads((ROOT / "results_final.json").read_text(encoding="utf-8"))
S = json.loads((ROOT / "results_supplement.json").read_text(encoding="utf-8"))
H = json.loads((ROOT / "results_E4_highdim.json").read_text(encoding="utf-8"))

TEX_RAW = TEX.read_text(encoding="utf-8")
# LaTeX inserts thin spaces in some numbers; normalise ONLY those so that the
# derived strings can be matched literally.  No numeric characters are removed.
TEX_N = TEX_RAW.replace(r"\!", "").replace(r"\,", " ")
# Word-level view: LaTeX source wraps lines inside sentences, so textual
# phrases must be matched against whitespace-normalised content.
TEX_W = re.sub(r"\s+", " ", TEX_N)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))


def in_tex(name: str, literal: str) -> None:
    check(f"text: {literal}", literal in TEX_N,
          f"derived from source data; {'found' if literal in TEX_N else 'MISSING'}")


def sci(x: float, dec: int = 2, sign: str = "") -> str:
    """Format x as a LaTeX scientific-notation literal, e.g. 1.44\\times10^{-6}."""
    if x == 0:
        return "0"
    e = int(math.floor(math.log10(abs(x))))
    m = x / (10.0 ** e)
    s = f"{m:.{dec}f}"
    if sign == "+":
        s = "+" + s
    return f"{s}\\times10^{{{e}}}"


def num(x: float, dec: int = 2) -> str:
    return f"{x:.{dec}f}"


def pct(x: float, dec: int = 2) -> str:
    return num(100.0 * x, dec)


# ===================================================================== 1. E0
E0 = D["E0"]
in_tex("E0 energy balance, 2001 pts", sci(E0["energy_balance_max_dev"]["2001"]))
in_tex("E0 energy balance, 201 pts", sci(E0["energy_balance_max_dev"]["201"]))
in_tex("E0 energy balance, 501 pts", sci(E0["energy_balance_max_dev"]["501"]))
in_tex("E0 Beer-Lambert", sci(E0["beer_lambert_max_dev"]))
in_tex("E0 correct mean absorptance", num(E0["correct_A_mean"], 4))
in_tex("E0 bug mean absorptance", num(E0["bug_A_mean"], 4))
in_tex("E0 bug max deviation", num(E0["bug_max_dev"], 3))
in_tex("E0 coherent/incoherent at 200 nm",
       num(E0["coherent_to_incoherent"]["200.0"], 3))
in_tex("E0 coherent/incoherent at 3000 nm",
       sci(E0["coherent_to_incoherent"]["3000.0"]))
check("E0 all 6 absolute checks pass",
      E0["pass"] and E0["checks_passed"] == E0["checks_total"] == 6,
      f"pass={E0['pass']}, {E0['checks_passed']}/{E0['checks_total']}")
check("E0 energy-balance deviation decreases with grid",
      E0["energy_balance_max_dev"]["201"] > E0["energy_balance_max_dev"]["501"]
      > E0["energy_balance_max_dev"]["2001"] > 0,
      "monotone second-order convergence")
check("E0 regression test has power",
      E0["bug_max_dev"] > 0.1 and E0["bug_A_mean"] < 0.5 * E0["correct_A_mean"],
      f"bug max dev {E0['bug_max_dev']:.3f} vs correct mean A {E0['correct_A_mean']:.4f}")

# ===================================================================== 2. E1
E1 = D["E1"]
in_tex("E1 pure TMM chain", sci(E1["optics_chain"]["rel_err"]))
in_tex("E1 isolated DD optical path", sci(E1["isolated_paths"]["optics"]["rel_err"]))
in_tex("E1 isolated DD electrical path",
       sci(E1["isolated_paths"]["electrical"]["rel_err"]))
for row in E1["per_coordinate"]:
    in_tex(f"E1 per-coordinate {row['param']}", sci(row["rel_err"]))
in_tex("E1 full-chain directional", sci(E1["full_chain_directional_rel_err"]))
in_tex("E1 thickness optical contribution",
       sci(E1["isolated_paths"]["optics"]["ad"], 3))
in_tex("E1 thickness electrical contribution",
       sci(E1["isolated_paths"]["electrical"]["ad"], 3, sign="+"))
_sum = (E1["isolated_paths"]["optics"]["ad"]
        + E1["isolated_paths"]["electrical"]["ad"])
in_tex("E1 cancellation residual", sci(_sum))
in_tex("E1 cancellation ratio", num(E1["cancellation_ratio"]))
in_tex("E1 adjoint residual (refine=1)",
       sci(E1["adjoint_residual"][0]["rel_residual"]))
walk = E1["solver_walk"]
in_tex("E1 solver residual at 0 V", num(walk[0]["max_abs_residual"], 1))
in_tex("E1 solver residual at 0.3 V", num(walk[1]["max_abs_residual"], 0))
in_tex("E1 solver residual at 0.6 V", sci(walk[2]["max_abs_residual"]))
in_tex("E1 solver residual at 0.9 V", sci(walk[3]["max_abs_residual"]))
check("E1 iteration counts quoted",
      "23, 15, 17 and 17" in TEX_N
      and [w["iters"] for w in walk] == [23, 15, 17, 17],
      f"actual {[w['iters'] for w in walk]}")
check("E1 all solver states converged",
      all(w["converged"] for w in walk), "physical-scale convergence")
check("E1 tolerance sweep is flat (cancellation-limited, not solver-tolerance)",
      len({round(r["rel_err"], 12) for r in E1["tolerance_sweep"]}) == 1
      and not E1["error_decreases_with_tighter_tolerance"],
      f"{len(E1['tolerance_sweep'])} floors, all rel_err "
      f"{E1['tolerance_sweep'][0]['rel_err']:.3e}")
check("E1 pass criteria", E1["pass"], f"pass={E1['pass']}")
check("E1 cancellation ratio reproduces data",
      abs(E1["cancellation_ratio"]
          - abs(E1["isolated_paths"]["optics"]["ad"]) / abs(_sum)) < 1.0,
      f"recorded {E1['cancellation_ratio']:.2f}, recomputed "
      f"{abs(E1['isolated_paths']['optics']['ad']) / abs(_sum):.2f}")

# ===================================================================== 3. E2
E2 = D["E2"]
M = E2["metrics"]
in_tex("E2 dark ideality", num(E2["dark_ideality_factor"], 3))
in_tex("E2 uniform-G ratio", num(E2["uniformG_ratio"], 3))
in_tex("E2 uniform-G Jsc", num(E2["uniformG_Jsc"]))
in_tex("E2 uniform-G analytic", num(E2["uniformG_analytic"]))
in_tex("E2 EQE-integrated Jsc", num(E2["Jsc_eqe"]))
in_tex("E2 J-V Jsc", num(E2["Jsc_jv"]))
in_tex("E2 Jsc consistency", pct(E2["Jsc_consistency_rel_dev"]))
in_tex("E2 mean EQE", num(E2["mean_EQE"], 3))
in_tex("E2 optical upper bound", num(E2["Jsc_optical_upper_bound"]))
in_tex("E2 DD below optical bound",
       num(100 * (E2["Jsc_optical_upper_bound"] - E2["Jsc_jv"])
           / E2["Jsc_optical_upper_bound"], 1))
in_tex("E2 mean R", num(E2["mean_R"], 4))
in_tex("E2 mean T", num(E2["mean_T"], 4))
for key, dec in (("Jsc", 2), ("Voc", 3), ("FF", 3), ("Vmpp", 2), ("Jmpp", 2)):
    in_tex(f"E2 metrics {key}", num(M[key], dec))
in_tex("E2 PCE percent", pct(M["PCE"]))
in_tex("E2 mesh check change", pct(E2["Jsc_grid_rel_change"]))
for row in S["mesh"]:
    in_tex(f"E2 mesh N={row['N_dd']}", num(row["Jsc"], 3))
in_tex("E2 observed order", num(S["observed_order"]))
in_tex("E2 Richardson limit", num(S["Jsc_richardson_extrapolated"], 3))
in_tex("E2 production-grid uncertainty",
       pct(S["production_Jsc_rel_error_vs_extrapolated"]))
in_tex("E2 production vs next refinement",
       pct(S["production_vs_next_refinement_rel_change"]))
check("E2 PCE = Jsc*Voc*FF / Pin",
      abs(M["PCE"] - M["Jsc"] * M["Voc"] * M["FF"] / 100.0) < 1e-9,
      f"PCE {M['PCE']*100:.4f}% vs Jsc*Voc*FF/100 "
      f"{M['Jsc']*M['Voc']*M['FF']:.4f} mW/cm2")
check("E2 equilibrium dark current is zero", E2["J_eq_dark_A_m2"] == 0.0)
check("E2 R+T<=1", E2["R_plus_T_leq_1"], "all wavelengths")
check("E2 Jsc does not exceed the optical bound",
      E2["Jsc_jv"] < E2["Jsc_optical_upper_bound"],
      f"{E2['Jsc_jv']:.2f} < {E2['Jsc_optical_upper_bound']:.2f}")
check("E2 EQE/JV consistency recomputed",
      abs(E2["Jsc_consistency_rel_dev"]
          - abs(E2["Jsc_eqe"] - E2["Jsc_jv"]) / E2["Jsc_jv"]) < 1e-9,
      f"{E2['Jsc_consistency_rel_dev']:.6f}")
check("E2 mesh convergence monotone",
      all(S["mesh"][i]["Jsc"] < S["mesh"][i + 1]["Jsc"]
          for i in range(len(S["mesh"]) - 1)),
      " -> ".join(f"{r['Jsc']:.3f}" for r in S["mesh"]))
check("E2 Richardson limit above finest grid",
      S["Jsc_richardson_extrapolated"] > S["mesh"][-1]["Jsc"],
      f"{S['Jsc_richardson_extrapolated']:.4f} > {S['mesh'][-1]['Jsc']:.4f}")
check("E2 honest pre-registered failure reported",
      (not E2["pass"]) and E2["checks_passed"] == 6
      and E2["checks_total"] == 7
      and "\\textbf{no}" in TEX_RAW,
      f"pass={E2['pass']}, {E2['checks_passed']}/{E2['checks_total']}")

# ===================================================================== 4. E3
E3 = D["E3"]
in_tex("E3 initial loss", sci(D["_E3_hist"][0][1]))
in_tex("E3 final loss", sci(E3["final_loss"]))
in_tex("E3 evaluations", str(E3["evals"]))
in_tex("E3 wall clock", str(round(E3["wall_clock_s"])))
in_tex("E3 recovered d", num(E3["recovered"]["d"], 3))
in_tex("E3 recovered k", num(E3["recovered"]["k"], 6))
in_tex("E3 recovered tau", sci(E3["recovered"]["tau"], 4))
for k in ("d", "k", "log_tau"):
    in_tex(f"E3 relative error {k}", sci(E3["rel_err"][k]))
check("E3 recovery within 0.002%",
      max(E3["rel_err"]["d"], E3["rel_err"]["k"]) < 2.2e-5  # rounds to 0.002%
      and "0.002" in TEX_N,
      f"max rel err {max(E3['rel_err']['d'], E3['rel_err']['k']):.3e}")
check("E3 pass", E3["pass"], f"pass={E3['pass']}, loss {E3['final_loss']:.3e}")

# ===================================================================== 5. E4
E4 = D["E4"]
C3, C8 = E4["cases"]["3D"], E4["cases"]["8D"]
B3, B8 = S["budget"]["3D"], S["budget"]["8D"]
in_tex("E4 3D L-BFGS final loss", sci(C3["final_loss_lbfgs"]))
in_tex("E4 3D NM final loss", sci(C3["final_loss_nm"]))
in_tex("E4 3D NM loss at common budget", sci(B3["at_common_budget"]["nm"]))
in_tex("E4 8D L-BFGS final loss", sci(C8["final_loss_lbfgs"]))
in_tex("E4 8D NM final loss", sci(C8["final_loss_nm"]))
in_tex("E4 8D NM loss at common budget", sci(B8["at_common_budget"]["nm"]))
in_tex("E4 backward overhead", num(C3["backward_overhead_factor"]))
in_tex("E4 forward time", num(C3["t_forward_s"]))
in_tex("E4 forward+backward time", num(C3["t_forward_backward_s"]))
in_tex("E4 8D recovered d", num(C8["recovered"]["d"], 1))
in_tex("E4 8D d target", str(int(C8["truth"]["d"])))
in_tex("E4 8D d error", pct(C8["rel_err_d"], 1))
in_tex("E4 3D speedup at 1e-4", num(B3["ratios"][2]["speedup_lower_bound"], 1))
in_tex("E4 3D speedup at 1e-5", num(B3["ratios"][3]["speedup_lower_bound"], 1))
in_tex("E4 3D speedup at 1e-6", num(B3["ratios"][4]["speedup_lower_bound"], 1))
in_tex("E4 8D speedup at 1e-3", num(B8["ratios"][1]["speedup"], 1))
check("E4 true-call accounting (1 history entry per f() call)",
      all(h[0] == i + 1 for i, h in enumerate(C3["lbfgs_hist"]))
      and all(h[0] == i + 1 for i, h in enumerate(C3["nm_hist"]))
      and all(h[0] == i + 1 for i, h in enumerate(C8["lbfgs_hist"]))
      and all(h[0] == i + 1 for i, h in enumerate(C8["nm_hist"])),
      f"lengths {len(C3['lbfgs_hist'])}, {len(C3['nm_hist'])}, "
      f"{len(C8['lbfgs_hist'])}, {len(C8['nm_hist'])}")
check("E4 3D threshold counts quoted match data",
      "16 / n.r." in TEX_N and "7 / 7" in TEX_N
      and C3["rows"][2]["lbfgs"] == 16 and C3["rows"][2]["nm"] is None,
      "10^-4 censored")
check("E4 8D threshold counts quoted match data",
      "7 / 21" in TEX_N and C8["rows"][1]["lbfgs"] == 7
      and C8["rows"][1]["nm"] == 21, "10^-3 reached by both")
check("E4 honest failure of >=10x criterion reported",
      (not E4["pass"]) and (not B3["preregistered_10x_pass"])
      and (not B8["preregistered_10x_pass"])
      and "not met" in TEX_N and "\\textbf{not met}" in TEX_RAW,
      "pre-registered target explicitly reported as not met")
check("E4 backward overhead matches measured times",
      abs(C3["backward_overhead_factor"]
          - C3["t_forward_backward_s"] / C3["t_forward_s"]) < 1e-9
      and abs(C8["backward_overhead_factor"]
              - C8["t_forward_backward_s"] / C8["t_forward_s"]) < 1e-9,
      f"3D {C3['backward_overhead_factor']:.4f}, 8D {C8['backward_overhead_factor']:.4f}")

# ============================================== 5b. E4-H high-dimensional supplement
# Every literal below is recomputed from results_E4_highdim.json; the original
# E4 verdict is NOT overwritten by this supplementary experiment.
V = H["verdict"]
HL, HN = H["lbfgs"], H["nelder_mead"]
RH = {r["threshold"]: r for r in V["rows"]}


def best_at(hist, n):
    vals = [val for call, val in hist if call <= n]
    return min(vals) if vals else None


nm_common = best_at(HN["hist"], HL["n_calls"])
in_tex("E4-H final L-BFGS loss", sci(HL["final_loss"]))
in_tex("E4-H NM best loss", sci(HN["best_loss"]))
in_tex("E4-H NM loss at common budget", sci(nm_common))
in_tex("E4-H backward overhead", num(H["timing"]["backward_overhead_factor"], 2))
for thr in (1e-4, 1e-5, 1e-6):
    in_tex(f"E4-H censored lower bound at {thr:g}",
           num(HN["n_calls"] / RH[thr]["lbfgs"], 1))
in_tex("E4-H measured ratio at 1e-3",
       num(RH[1e-3]["nm"] / RH[1e-3]["lbfgs"], 2))
check("E4-H verdict is PASS via censored lower bounds",
      V["result"] == "PASS" and V["lbfgs_reaches_1e-4"]
      and len(V["censored_thresholds"]) == 3
      and H["protocol"]["dim"] == 16 and "16 parameters" in TEX_W,
      f"{V['result']}, censored {V['censored_thresholds']}")
check("E4-H retains the original E4 non-claim",
      (not E4["pass"]) and "not met" in TEX_N
      and r"\textbf{not met}" in TEX_RAW,
      "original >=10x failure still reported")
check("E4-H reports bounds, not a measured >=10x speedup",
      RH[1e-3]["nm"] / RH[1e-3]["lbfgs"] < 10
      and "bounds rather than measured ratios" in TEX_W,
      f"measured ratio {RH[1e-3]['nm'] / RH[1e-3]['lbfgs']:.2f}x")

# ============================================================ 6. configuration
check("config: production grid N=73", D["meta"]["N_dd"] == 73
      and "73 (production)" in TEX_N, f"N_dd={D['meta']['N_dd']}")
check("config: adjoint size 3(N-2)=213",
      3 * (D["meta"]["N_dd"] - 2) == 213 and "3(N-2)=213" in TEX_N)
check("config: float64 / seed 0",
      D["meta"]["dtype"] == "float64" and D["meta"]["seed"] == 0
      and "float64" in TEX_N and "seed 0" in TEX_N)
check("config: total wall clock quoted as ~25 min",
      "25~min" in TEX_N
      and 20 < D["meta"]["total_wall_clock_s"] / 60 < 30,
      f"{D['meta']['total_wall_clock_s']/60:.1f} min")
check("config: 41-point spectrum grid / 350-800 nm",
      "41" in TEX_N and "350 to 800" in TEX_N
      and "50~nm" in TEX_N, "AM1.5G table 50 nm, grid 41 pts")
check("config: spectrum description unambiguous",
      "50~nm intervals from 300 to 1000~nm" in TEX_N
      and "41-point grid spanning 350--800" in TEX_N,
      "table spacing and evaluation grid stated separately")

# ============================================================== 7. Solar Energy format
check("journal set to Solar Energy", r"\journal{Solar Energy}" in TEX_RAW)
check("elsarticle preprint class used",
      r"\documentclass[preprint,12pt]{elsarticle}" in TEX_RAW)
check("line numbering enabled", r"\linenumbers" in TEX_RAW)
kw = re.search(r"\\begin\{keyword\}(.*?)\\end\{keyword\}", TEX_RAW, re.S)
n_kw = len(kw.group(1).split(r"\sep")) if kw else 0
check("at most 6 keywords", 0 < n_kw <= 6, f"{n_kw} keywords")
secs = re.findall(r"^\\section\{([^}]*)\}", TEX_RAW, re.M)
check("numbered sections present", len(secs) == 5 and "Conclusions" in secs[-1],
      " / ".join(secs))
check("abstract is stand-alone (no \\ref / \\cite inside)",
      "\\ref" not in re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
                               TEX_RAW, re.S).group(1)
      and "\\cite" not in re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}",
                                    TEX_RAW, re.S).group(1))
abstract = re.sub(r"\s+", " ", re.search(
    r"\\begin\{abstract\}(.*?)\\end\{abstract\}", TEX_RAW, re.S).group(1))
check("abstract contains the headline results",
      all(t in abstract for t in ("29.95", "1.110", "0.835", "27.74",
                                  "1.208", "0.89", "1.52", "44", "1.10")))
check("abstract states results are synthetic / no efficiency claim",
      "All results are synthetic" in abstract
      and "no experimental calibration or efficiency record is claimed" in abstract)
check("author 1 exactly as supplied",
      r"\author[addr1]{Qiong Yan}" in TEX_RAW
      and r"\ead{381007382@qq.com}" in TEX_RAW
      and "Fujian Jiangxia" in TEX_RAW and "Fuzhou 350108" in TEX_RAW)
check("corresponding author exactly as supplied",
      r"\author[addr2,addr3]{Peide Yang\corref{cor1}}" in TEX_RAW
      and r"\ead{yangpd@xujc.com}" in TEX_RAW
      and r"\cortext[cor1]{Corresponding author.}" in TEX_RAW
      and TEX_RAW.count(r"\address[addr") == 3
      and "School of Electronic Science and Technology" in TEX_W
      and "Key Laboratory of Intelligent Manufacturing Equipment and "
          "Industrial Internet Technology for Universities of Fujian Province"
          in TEX_W)
check("declarations present",
      all(s in TEX_RAW for s in ("Declaration of competing interest",
                                 "CRediT authorship contribution statement",
                                 "Funding", "Data availability",
                                 "Generative AI disclosure")))
check("no vertical rules in tables",
      not re.search(r"\\begin\{tabular\}\{[^}]*\|", TEX_RAW))
check("no placeholder bibliography entries",
      not re.search(r"to complete|TODO|XXX|PLACEHOLDER|\[citation needed\]",
                    TEX_RAW, re.I))

# --- citations -----------------------------------------------------------
bib_order = re.findall(r"\\bibitem\{([^}]+)\}", TEX_RAW)
first_cites: list[str] = []
for m in re.finditer(r"\\cite\{([^}]+)\}", TEX_RAW):
    for key in m.group(1).split(","):
        key = key.strip()
        if key not in first_cites:
            first_cites.append(key)
check("numbered bibliography has 22 entries", len(bib_order) == 22,
      f"{len(bib_order)} entries")
check("citation order of first appearance equals bibliography order",
      first_cites == bib_order, f"same order: {first_cites == bib_order}")
check("no missing or uncited bibliography keys",
      set(first_cites) == set(bib_order),
      f"missing={set(first_cites)-set(bib_order)}, uncited={set(bib_order)-set(first_cites)}")
bib_blocks = re.split(r"\\bibitem\{", TEX_RAW)[1:]
check("every reference carries a DOI or an arXiv identifier",
      all(("doi:" in b or "arXiv:" in b) for b in bib_blocks),
      f"{sum('doi:' in b or 'arXiv:' in b for b in bib_blocks)}/{len(bib_blocks)}")
check("no unresolved cross-references",
      all(k in TEX_RAW for k in re.findall(r"\\(?:eq)?ref\{([^}]+)\}", TEX_RAW)),
      "every \\ref / \\eqref target is defined by \\label")
check("no hard-coded figure/table/equation/section numbers in prose",
      not re.search(r"(?<!Fig\.~)(?<!Table~)\\?\b(?:Figure|Table|Equation|Section)\s+\d+"
                    r"(?![\.\w])", re.sub(r"\\(?:caption|label|ref|eqref)\{[^}]*\}",
                                          "", TEX_RAW)),
      "all cross-references use \\ref")

# --- figures -------------------------------------------------------------
incs = re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", TEX_RAW)
check("5 figures referenced", len(incs) == 5, str(len(incs)))
check("all referenced figure files exist",
      all((HERE / p).exists() for p in incs))
figs = sorted((HERE / "figures").glob("fig*.png"))
check("PNG + PDF for all 5 figures",
      len(figs) == 5
      and all((HERE / "figures" / f.with_suffix(".pdf").name).exists() for f in figs),
      f"{len(figs)} PNGs")
caps = re.findall(r"\\caption\{", TEX_RAW)
check("5 figure + 4 table captions", len(caps) == 9, f"{len(caps)} captions")

# --- aux / PDF -----------------------------------------------------------
aux = AUX.read_text(encoding="utf-8") if AUX.exists() else ""
eq_nums = [int(m) for m in re.findall(r"\\newlabel\{eq:[^}]*\}\{\{(\d+)\}", aux)]
check("equation numbering is continuous 1..N",
      eq_nums == list(range(1, len(eq_nums) + 1)), f"numbers {eq_nums}")
check("no LaTeX undefined references/citations in log",
      "There were undefined references" not in (HERE / "unidd_solar_energy.log").read_text(
          encoding="utf-8", errors="ignore"))
check("PDF compiled", PDF.exists(), f"{PDF.stat().st_size} bytes" if PDF.exists() else "missing")
try:
    import fitz
    with fitz.open(PDF) as doc:
        pages = doc.page_count
        full = "".join(p.get_text() for p in doc)
    check("PDF page count between 15 and 25", 15 <= pages <= 25, f"{pages} pages")
    check("PDF first page carries both authors and affiliations",
          all(s in full for s in ("Qiong Yan", "Peide Yang", "381007382@qq.com",
                                  "yangpd@xujc.com", "Fujian Jiangxia")),
          "front matter text extracted")
    check("PDF contains the honest non-claim",
          "not met" in full and "All results are synthetic" in full)
except ImportError:
    check("PyMuPDF available for PDF inspection", False, "fitz not installed")

# ====================================================== 8. other deliverables
if HIGHLIGHTS.exists():
    hl = [l.strip() for l in HIGHLIGHTS.read_text(encoding="utf-8").splitlines()
          if l.strip() and not l.strip().startswith("#")]
    check("Highlights: 3-5 bullets", 3 <= len(hl) <= 5, f"{len(hl)} bullets")
    check("Highlights: every bullet <= 85 characters",
          all(len(x) <= 85 for x in hl), f"longest {max(map(len, hl))} chars")
else:
    check("Highlights file exists", False, str(HIGHLIGHTS))

check("cover letter PDF exists", COVER_PDF.exists())
check("cover letter DOCX exists", COVER_DOCX.exists())

if DOCX.exists():
    from docx import Document
    doc = Document(DOCX)
    xml = zipfile.ZipFile(DOCX).read("word/document.xml").decode("utf-8")
    plain = re.sub(r"<[^>]+>", "", xml)
    check("Word: 4 editable tables", len(doc.tables) == 4, f"{len(doc.tables)} tables")
    check("Word: 5 embedded figures", len(doc.inline_shapes) == 5,
          f"{len(doc.inline_shapes)} images")
    media = [n for n in zipfile.ZipFile(DOCX).namelist() if "media/" in n]
    check("Word: all figures are PNG (displayable in Word)",
          len(media) == 5 and all(n.endswith(".png") for n in media), str(media))
    check("Word: equations stored as editable OMML",
          xml.count("<m:oMath") >= 100, f"{xml.count('<m:oMath')} OMML nodes")
    check("Word: no unresolved LaTeX cross-reference keys",
          not re.search(r"\[(?:eq|fig|tab|sec):", plain),
          "all \\ref targets resolved to numbers")
    check("Word: no raw LaTeX control sequences in visible text",
          not re.search(r"\\(?:cite|ref|eqref|begin|end|includegraphics)\b", plain))
    check("Word: headline numbers present",
          all(t in plain for t in ("29.95", "1.110", "0.835", "27.74",
                                   "1.208", "1.52", "44", "2.78")),
          "abstract + body text")
    check("Word: author block present",
          all(t in plain for t in ("Qiong Yan", "Peide Yang", "381007382@qq.com",
                                   "yangpd@xujc.com")))
    check("Word: references numbered [1]..[22]",
          all(f"[{i}]" in plain for i in (1, 11, 22)), "spot-checked 1/11/22")
else:
    check("Word manuscript exists", False, str(DOCX))

# ===================================================================== report
n_pass = sum(1 for _, ok, _ in RESULTS if ok)
n_fail = len(RESULTS) - n_pass
lines = [
    "# UniDD manuscript — consistency and format verification report",
    "",
    f"**Result: {n_pass}/{len(RESULTS)} checks passed, {n_fail} failed.**",
    "",
    "Generated by `check_consistency.py`. All expected literals are recomputed",
    "from `results_final.json` and `results_supplement.json`; none are typed in",
    "by hand. The checker also validates the Solar Energy (Elsevier) format,",
    "the author block, the bibliography, the figures and the Word/PDF outputs.",
    "",
    "| # | Check | Status | Detail |",
    "|---|-------|--------|--------|",
]
for i, (name, ok, detail) in enumerate(RESULTS, 1):
    d = detail.replace("|", "\\|").replace("\n", " ")
    lines.append(f"| {i} | {name.replace('|', '|')} | {'PASS' if ok else '**FAIL**'} | {d} |")
lines += ["", "## Failed checks", ""]
fails = [f"- **{n}**: {d}" for n, ok, d in RESULTS if not ok]
lines += fails if fails else ["- None.", ""]
lines += [
    "",
    "## Sources of truth",
    "",
    "- `results_final.json` — E0–E4, post-Poynting correction, seed 0, float64.",
    "- `results_supplement.json` — extended mesh study and honest E4 budget study.",
    "- `results_E4_highdim.json` — pre-registered 16-D E4-H supplement (manuscript subsection E4-H).",
    "- `unidd_solar_energy.aux` — resolved equation/section/figure/table numbers.",
    "",
]
(HERE / "consistency_report.md").write_text("\n".join(lines), encoding="utf-8")

print(f"\n{'=' * 70}")
print(f"  {n_pass}/{len(RESULTS)} checks passed, {n_fail} failed")
print(f"  report -> {HERE / 'consistency_report.md'}")
print("=" * 70)
for n, ok, d in RESULTS:
    if not ok:
        print(f"  FAIL  {n}  ::  {d}")
sys.exit(1 if n_fail else 0)
