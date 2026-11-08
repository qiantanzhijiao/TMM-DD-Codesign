"""
UniDD -- supplementary studies for the manuscript.

Two pre-registered checks in experiments_final.py did not pass:

  * E2: the mesh-convergence check compared N=49 with N=97 and demanded
    <2% change in Jsc; the measured change was 2.48%.  This is not a physics
    error but an under-resolved *coarsest* grid.  Here we extend the study to
    N=121,145, estimate the observed convergence order, and quantify the
    discretisation uncertainty of the PRODUCTION grid (N=73) by Richardson
    extrapolation.  The paper reports this uncertainty explicitly.

  * E4: the pre-registered ">=10x fewer evaluations" criterion is not met in
    8-D.  This file does NOT change that verdict.  It only re-expresses the
    already-recorded, honest call histories as censored ratios and as
    loss-at-equal-budget comparisons, which is what the paper reports.

Run:  python experiments_supplement.py
Out:  results_supplement.json
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
torch.set_default_dtype(torch.float64)
torch.manual_seed(0)

from soldiff.device import CoupledSolarCell  # noqa: E402
from experiments_final import V_METRICS, DV, make_cell, nk_simple  # noqa: E402

OUT = ROOT / "results_supplement.json"
FINAL = ROOT / "results_final.json"
S: dict = {}


def banner(s: str) -> None:
    print("\n" + "=" * 76 + "\n" + s + "\n" + "=" * 76, flush=True)


def mesh_study() -> None:
    banner("S1  extended DD mesh convergence (N = 49 ... 145)")
    d0 = torch.tensor(480.0)
    k0 = torch.tensor(0.72)
    tau0 = torch.tensor(3.0e-7)
    Vt = torch.tensor(V_METRICS)
    rows = []
    for Nd in (49, 73, 97, 121, 145):
        t0 = time.time()
        cm = CoupledSolarCell(N_dd=Nd)
        with torch.no_grad():
            J = cm.jv(d0, nk_simple(k0, cell=cm), tau0, V_METRICS, dV=DV)
        m = CoupledSolarCell.metrics(Vt, J)
        row = {"N_dd": Nd, "h_nm": 480.0 / (Nd - 1),
               "Jsc": float(m["Jsc"]), "Voc": float(m["Voc"]),
               "FF": float(m["FF"]), "PCE": float(m["PCE"])}
        rows.append(row)
        print(f"  N_dd {Nd:3d} (h={row['h_nm']:.3f} nm): Jsc {row['Jsc']:.4f}, "
              f"Voc {row['Voc']:.5f}, FF {row['FF']:.5f}, "
              f"PCE {100*row['PCE']:.4f}%   ({time.time()-t0:.0f}s)", flush=True)
        S["mesh"] = rows
        with open(OUT, "w") as f:
            json.dump(S, f, indent=1)

    # consecutive-refinement changes and observed order from the three finest grids
    changes = []
    for a, b in zip(rows[:-1], rows[1:]):
        changes.append({"from_N": a["N_dd"], "to_N": b["N_dd"],
                        "Jsc_rel_change": abs(b["Jsc"] - a["Jsc"]) / b["Jsc"],
                        "PCE_rel_change": abs(b["PCE"] - a["PCE"]) / b["PCE"]})
    S["mesh_changes"] = changes
    a, b, c = rows[-3], rows[-2], rows[-1]        # 97, 121, 145
    r = (b["Jsc"] - a["Jsc"]) / (c["Jsc"] - b["Jsc"]) if abs(c["Jsc"] - b["Jsc"]) > 1e-12 else float("nan")
    hr = a["h_nm"] / b["h_nm"]
    p = math.log(abs(r)) / math.log(hr) if r and math.isfinite(r) and r > 0 else None
    S["observed_order"] = p
    S["ratio_successive_differences"] = r
    # Richardson extrapolation from the two finest grids, using observed order
    if p and p > 0:
        J_exact = c["Jsc"] + (c["Jsc"] - b["Jsc"]) / ((b["h_nm"] / c["h_nm"]) ** p - 1)
    else:
        J_exact = None
    S["Jsc_richardson_extrapolated"] = J_exact
    prod = next(x for x in rows if x["N_dd"] == 73)
    S["production_N"] = 73
    S["production_Jsc"] = prod["Jsc"]
    S["production_Jsc_rel_error_vs_extrapolated"] = (
        abs(prod["Jsc"] - J_exact) / J_exact if J_exact else None)
    S["production_vs_next_refinement_rel_change"] = changes[1]["Jsc_rel_change"]
    print(f"\n  observed order p = {p}, Jsc(N->inf) = {J_exact}")
    print(f"  production grid N=73: Jsc {prod['Jsc']:.4f} mA/cm2, "
          f"relative error vs extrapolated "
          f"{100*S['production_Jsc_rel_error_vs_extrapolated']:.2f}%" if J_exact else "")
    print(f"  N=73 -> N=97 change: "
          f"{100*S['production_vs_next_refinement_rel_change']:.2f}%", flush=True)


def budget_study() -> None:
    banner("S2  honest re-expression of the recorded E4 call histories")
    d = json.load(open(FINAL))
    e4 = d["E4"]
    summary = {}
    for tag, c in e4["cases"].items():
        lb, nm = c["lbfgs_hist"], c["nm_hist"]
        assert all(lb[i][0] == i + 1 for i in range(len(lb))), "L-BFGS history not 1 call/entry"
        assert all(nm[i][0] == i + 1 for i in range(len(nm))), "NM history not 1 call/entry"
        n_lb, n_nm = len(lb), len(nm)
        # best-so-far loss at a COMMON budget (fair comparison)
        common = min(n_lb, n_nm)
        at_common = {"budget": common,
                     "lbfgs": min(x[1] for x in lb[:common]),
                     "nm": min(x[1] for x in nm[:common])}
        # censored lower bound on the call-count ratio at every threshold
        ratios = []
        for row in c["rows"]:
            t, a, b = row["threshold"], row["lbfgs"], row["nm"]
            if a is None:
                ratios.append({"threshold": t, "status": "neither_reached"})
            elif b is None:
                ratios.append({"threshold": t, "lbfgs": a,
                               "nm_lower_bound": n_nm,
                               "speedup_lower_bound": n_nm / a,
                               "status": "nm_censored"})
            else:
                ratios.append({"threshold": t, "lbfgs": a, "nm": b,
                               "speedup": b / a, "status": "both_reached"})
        # wall-clock per function call
        summary[tag] = {
            "n_calls_lbfgs": n_lb, "n_calls_nm": n_nm,
            "final_loss_lbfgs": c["final_loss_lbfgs"],
            "final_loss_nm": c["final_loss_nm"],
            "time_per_fg_call_s": c["wall_clock_lbfgs_s"] / n_lb,
            "time_per_nm_call_s": c["wall_clock_nm_s"] / n_nm,
            "backward_overhead_factor": c["backward_overhead_factor"],
            "at_common_budget": at_common,
            "ratios": ratios,
            "preregistered_10x_pass": c["pass"],
        }
        print(f"  {tag}: L-BFGS {n_lb} f+grad calls ({c['wall_clock_lbfgs_s']/n_lb:.1f}s each), "
              f"NM {n_nm} f() calls ({c['wall_clock_nm_s']/n_nm:.1f}s each)")
        print(f"       at common budget {common}: L-BFGS {at_common['lbfgs']:.3e} "
              f"vs NM {at_common['nm']:.3e}")
        for rr in ratios:
            print("       ", rr)
    S["budget"] = summary
    print("\n  NOTE: the pre-registered >=10x criterion is NOT met.  The paper "
          "reports the exact counts and the censored lower bounds instead of "
          "claiming an order-of-magnitude advantage.", flush=True)


def main() -> None:
    mesh_study()
    budget_study()
    with open(OUT, "w") as f:
        json.dump(S, f, indent=1)
    print(f"\nWritten -> {OUT}")


if __name__ == "__main__":
    main()
