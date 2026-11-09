"""
UniDD -- E6-FD: finite-difference gradients + L-BFGS as the missing baseline.

Motivation (q/1109 review, q4 "the baseline is in the wrong place")
-------------------------------------------------------------------
All recorded E4/E5 comparisons use derivative-free optimisers (Nelder--Mead,
Powell, differential evolution, dual annealing).  The baseline that actually
isolates the value of the IFT adjoint is the SAME optimiser (L-BFGS) driven by
finite-difference gradients.  This script adds that arm on the recorded 3-D
E4 case and converts every method to a common unit: forward-solve equivalents.

Protocol (pre-specified in this file before execution)
-----------------------------------------------------
* Same cell, same observables, same target y*, same u_init and the same
  L-BFGS settings as the recorded E4 3-D case.
* Central differences with h = 1e-4 in the normalised parameter u.
  One gradient therefore costs 2p + 1 = 7 forward solves (one base loss plus
  six perturbed losses); every individual f() call is counted, including
  line-search evaluations.
* IFT cost per gradient evaluation is taken from the RECORDED
  results_final.json E4 3-D timing (1.099167 forward solves), not re-measured.
* Histories are compared as cumulative-best loss vs cumulative forward-solve
  equivalents, so no method is credited with a cheaper currency.
* The check is a cost/accuracy comparison.  It does not alter the E4 verdict:
  the >=10x evaluation-count target remains unmet in eight dimensions.

Run:  python experiments_fd_baseline.py
Out:  results_fd_baseline.json
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import torch

torch.set_default_dtype(torch.float64)
torch.manual_seed(0)

import experiments_final as ef

H_FD = 1e-4
MAX_ITER, MAX_EVAL = 20, 30
THRESHOLDS = [1e-2, 1e-3, 1e-4, 1e-5, 1e-6]


def first_below(hist, thr, cost_per_eval=1.0):
    """hist: [[cumulative f() calls, best loss], ...] -> forward equivalents."""
    for n, v in hist:
        if v < thr:
            return n * cost_per_eval
    return None


def best_so_far(raw):
    out, best = [], float("inf")
    for n, v in raw:
        best = min(best, v)
        out.append([n, best])
    return out


def main():
    print("E6-FD finite-difference gradient baseline on the E4 3-D case", flush=True)
    F = json.loads((ROOT / "results_final.json").read_text(encoding="utf-8"))
    e4 = F["E4"]["cases"]["3D"]
    factor = e4["backward_overhead_factor"]
    print(f"  recorded IFT cost factor = {factor:.6f} forward solves", flush=True)

    cell = ef.make_cell()
    obs, u_star, u_init, decode = ef.build_observables(cell, 3)
    with torch.no_grad():
        y_star = obs(u_star, grad=False)
    p = u_init.numel()

    def f(u, grad=False):
        return ((obs(u, grad) - y_star) ** 2).mean()

    def eval_no_grad(u):
        return float(f(u, grad=False))

    def fd_grad(u):
        g = torch.zeros_like(u)
        for i in range(p):
            up, um = u.clone(), u.clone()
            up[i] += H_FD
            um[i] -= H_FD
            g[i] = (eval_no_grad(up) - eval_no_grad(um)) / (2 * H_FD)
        return g

    # Exact IFT gradient at the common starting point (accuracy reference).
    u_ref = u_init.clone().requires_grad_(True)
    loss_ref = f(u_ref, grad=True)
    loss_ref.backward()
    g_ift = u_ref.grad.detach().clone()
    g_fd = fd_grad(u_init)
    cosine = float(torch.nn.functional.cosine_similarity(g_ift, g_fd, dim=0))
    rel_l2 = float((g_ift - g_fd).norm() / g_ift.norm())
    print(f"  initial gradient: cosine {cosine:.6f}, relative L2 error {rel_l2:.3e}",
          flush=True)

    u = u_init.clone().requires_grad_(True)
    opt = torch.optim.LBFGS([u], lr=0.5, max_iter=MAX_ITER, max_eval=MAX_EVAL,
                            tolerance_grad=1e-12, tolerance_change=1e-14,
                            history_size=25, line_search_fn="strong_wolfe")
    n_forwards, raw, t0 = {"n": 0}, [], time.time()

    def closure():
        opt.zero_grad()
        val = eval_no_grad(u)                 # 1 forward solve
        n_forwards["n"] += 1
        g = fd_grad(u)                        # 2p forward solves
        n_forwards["n"] += 2 * p
        u.grad = g
        raw.append([n_forwards["n"], val])
        return torch.tensor(val, dtype=torch.float64)

    opt.step(closure)
    dt = time.time() - t0
    hist = best_so_far(raw)
    print(f"  FD-LBFGS: {len(raw)} gradient evaluations, "
          f"{n_forwards['n']} forward solves, {dt:.0f}s, "
          f"best loss {hist[-1][1]:.3e}", flush=True)

    comparison = {}
    rows = []
    for thr in THRESHOLDS:
        fd_n = first_below(hist, thr)
        ift_n = first_below(F["E4"]["cases"]["3D"]["lbfgs_hist"], thr, factor)
        nm_n = first_below(F["E4"]["cases"]["3D"]["nm_hist"], thr)
        rows.append({"threshold": thr,
                     "FD_LBFGS_forward_equivalents": fd_n,
                     "IFT_LBFGS_forward_equivalents": ift_n,
                     "Nelder_Mead_forward_equivalents": nm_n})
    at_1e3 = next(r for r in rows if r["threshold"] == 1e-3)
    speedup = (at_1e3["FD_LBFGS_forward_equivalents"]
               / at_1e3["IFT_LBFGS_forward_equivalents"]
               if at_1e3["FD_LBFGS_forward_equivalents"] is not None
               and at_1e3["IFT_LBFGS_forward_equivalents"] is not None else None)
    comparison = {
        "thresholds": rows,
        "FD_vs_IFT_forward_equivalent_speedup_at_1e-3": speedup,
        "per_gradient_cost": {
            "FD_central_differences": 2 * p + 1,
            "IFT_forward_plus_adjoint": factor,
            "theoretical_ratio": (2 * p + 1) / factor,
        },
    }
    print(f"  at 1e-3: FD {at_1e3['FD_LBFGS_forward_equivalents']} vs "
          f"IFT {at_1e3['IFT_LBFGS_forward_equivalents']:.2f} forward equivalents "
          f"-> {speedup:.2f}x" if speedup else "  no comparable threshold crossing",
          flush=True)

    res = {
        "protocol": {
            "purpose": "isolate the value of the IFT adjoint against the same "
                       "optimiser driven by finite differences",
            "case": "recorded E4 3-D inverse problem (480 nm, k=0.72, tau=3e-7 s)",
            "fd_step": H_FD,
            "difference_scheme": "central, 2p+1 forward solves per gradient",
            "p": p,
            "max_iter": MAX_ITER, "max_eval": MAX_EVAL,
            "IFT_cost_factor_from": "results_final.json E4.cases.3D.backward_overhead_factor",
            "currency": "forward-solve equivalents; every f() call counted",
            "note": "baseline only; does not revise the E4 eight-dimensional verdict",
        },
        "initial_gradient": {
            "IFT": [float(v) for v in g_ift],
            "FD": [float(v) for v in g_fd],
            "cosine": cosine, "relative_L2_error": rel_l2,
        },
        "fd_lbfgs": {
            "gradient_evaluations": len(raw),
            "forward_solves": n_forwards["n"],
            "wall_clock_s": dt,
            "best_loss": hist[-1][1],
            "history_forward_solves_vs_best_loss": hist,
        },
        "comparison": comparison,
        "interpretation": (
            "An adjoint gradient costs about 1.10 forward solves whereas a "
            "central finite-difference gradient costs seven; once both methods "
            "are charged in the same currency the IFT arm reaches the same "
            "loss with fewer forward solves. This quantifies the net benefit "
            "of the 10% adjoint overhead. It is a synthetic 3-D cost comparison "
            "and is not a claim about eight-dimensional convergence or about "
            "experimental data."),
    }
    (ROOT / "results_fd_baseline.json").write_text(
        json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(comparison, indent=1), flush=True)


if __name__ == "__main__":
    main()
