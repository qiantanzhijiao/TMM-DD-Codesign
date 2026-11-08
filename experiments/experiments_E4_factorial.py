"""
UniDD -- E4-C: ONE-FACTOR controlled dimension experiment (8-D vs 16-D).

Why this exists
---------------
E4-H (16-D) met the >=10x criterion by a CENSORED LOWER BOUND, but it changed
three things at once relative to the original 8-D E4: dimension, spectral
parametrisation (piecewise-linear knots -> smooth Gaussian RBF) and the number
of R/T observables (8 -> 16).  The improvement therefore cannot be attributed
to dimension.  This experiment isolates dimension and dimension alone.

Pre-registered protocol (fixed before execution, mirrored into the JSON)
------------------------------------------------------------------------
* FIXED for both arms: RBF basis (14 centres, sigma 55 nm), true spectrum,
  true thickness 480 nm and lifetime 3e-7 s, observable set (6 J-V biases,
  6 EQE wavelengths, 16 R/T wavelengths), loss and normalisation, threshold
  ladder, optimiser settings, per-f()-call bookkeeping, start point, budgets.
* ONLY CHANGED: the number of free design variables.
    - 16-D arm: u = [d, 14 RBF coefficients, log(tau)].
    -  8-D arm: u = [d,  6 control coefficients, log(tau)], with the 14 RBF
      coefficients obtained by a FIXED 14x6 row-normalised Gaussian map M.
  M maps a constant vector to the same constant, so both arms start from the
  identical physical state and share the identical truth u* and target y*.
  The 8-D arm is an exact linear subspace of the 16-D arm; no other modelling
  choice differs.
* Both arms are deterministic (no measurement noise, seed 0).  Multiple
  starting points and noisy targets belong to experiments_baselines.py, NOT
  here -- mixing them would break the one-factor design.
* Budgets are equal for both arms and both optimisers: L-BFGS 100 f+grad
  calls, Nelder-Mead 300 f() calls (300 >= 10 x 23, so a censored 10x lower
  bound remains evaluable).
* Verdict: report, for each arm, the calls to each threshold, the measured
  speedup where both optimisers succeed, and the censored lower bound where
  NM fails.  A dimension effect is claimed only if the 16-D arm improves over
  the 8-D arm under this fixed protocol.  This experiment does NOT revise the
  original E4 FAIL verdict or the E4-H supplement.

Run:  python experiments_E4_factorial.py [--pilot]
Out:  results_E4_factorial.json  (written incrementally)
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
from soldiff.device import CoupledSolarCell
from soldiff.tmm import field_intensity

# ------------------------------------------------------------- fixed protocol
N_BASIS = 14
SIGMA = 55.0
CENTERS = torch.linspace(350.0, 790.0, N_BASIS)
COARSE = torch.linspace(350.0, 790.0, 6)
W = torch.exp(-((CENTERS[:, None] - COARSE[None, :]) / SIGMA) ** 2)
M = W / W.sum(dim=1, keepdim=True)                       # 14 x 6, rows sum to 1

K_SCALE, D_SCALE, TAU_BASE = 0.72, 480.0, 1e-6
D_TRUE, TAU_TRUE = 480.0, 3.0e-7
LAM_RT = torch.linspace(400.0, 780.0, 16)
THRESHOLDS = [1e-2, 1e-3, 1e-4, 1e-5, 1e-6]
MAX_EVAL_LB, MAX_EVAL_NM = 100, 300
LB_MAX_ITER, NM_STEP = 60, 0.10

PROTOCOL = {
    "status": "pre-registered before execution; not altered afterwards",
    "purpose": "isolate design-space dimension as the cause of the E4-H improvement",
    "relation_to_E4_and_E4H": "independent controlled supplement; neither original verdict is changed",
    "factor_varied": "number of free design variables only (8-D vs 16-D)",
    "held_fixed": ["RBF basis and sigma", "true spectrum and device parameters",
                   "observable set (6 J-V + 6 EQE + 16 R/T)", "loss and normalisation",
                   "threshold ladder", "optimiser settings", "per-f()-call counter",
                   "physical start point", "budgets for both arms and both optimisers"],
    "subspace_map": "8-D control coefficients map to the same 14 RBF coefficients via a fixed row-normalised Gaussian matrix",
    "arms": {"8D": {"dim": 8, "spectral_dof": 6},
             "16D": {"dim": 16, "spectral_dof": 14}},
    "observables": {"JV_biases": list(ef.V_LIST), "dV": ef.DV,
                    "EQE_wavelengths": 6, "R_T_wavelengths": len(LAM_RT),
                    "normalisation": ["J/30", "EQE/0.9", "R", "T"]},
    "loss": "mean((observables(u) - y_star)^2)",
    "thresholds": THRESHOLDS,
    "lbfgs": {"lr": 0.5, "max_iter": LB_MAX_ITER, "max_eval": MAX_EVAL_LB,
              "line_search": "strong_wolfe", "history_size": 25},
    "nelder_mead": {"step": NM_STEP, "max_evals": MAX_EVAL_NM,
                    "counter": "one history entry per f() call; shrink = n+1 calls"},
    "start": "d=300 nm, spectral coefficients 0.45, tau=1.5 us (identical physical state in both arms)",
    "noise": "none (deterministic); multi-start and noisy targets are a separate experiment",
    "dtype": "float64", "seed": 0, "N_dd": ef.N_DD,
}
OUT = ROOT / "results_E4_factorial.json"
R: dict = {"protocol": PROTOCOL, "arms": {}}


def dump(tag: str) -> None:
    OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
    print(f"  [saved {tag} -> {OUT.name}]\n", flush=True)


# ------------------------------------------------------------- spectral model
def k_shape(lams: torch.Tensor) -> torch.Tensor:
    """Same band-edge-like truth used in E4-H."""
    idx = torch.clamp(torch.searchsorted(ef.K_KNOTS, lams), 1, len(ef.K_KNOTS) - 1)
    l0, l1 = ef.K_KNOTS[idx - 1], ef.K_KNOTS[idx]
    w = ((lams - l0) / (l1 - l0)).clamp(0.0, 1.0)
    return ef.K_TRUE[idx - 1] * (1 - w) + ef.K_TRUE[idx] * w


def nk_rbf(coeff: torch.Tensor, lams: torch.Tensor) -> torch.Tensor:
    w = torch.exp(-((lams[:, None] - CENTERS[None, :]) / SIGMA) ** 2)
    kv = (w @ (K_SCALE * coeff)) / w.sum(dim=1)
    return torch.complex(torch.full_like(lams, 2.55), kv.clamp(min=1e-3, max=2.0))


# truth belonging to BOTH parameterisations: c* -> a* = M c*
C_STAR = k_shape(COARSE) / K_SCALE
A_STAR = M @ C_STAR
D0, K0 = 300.0 / D_SCALE, 0.45
LOGTAU0 = math.log(1.5e-6) / math.log(TAU_BASE)
LOGTAU_STAR = math.log(TAU_TRUE) / math.log(TAU_BASE)

U = {
    "8D": torch.cat([torch.tensor([D_TRUE / D_SCALE]), C_STAR,
                     torch.tensor([LOGTAU_STAR])]),
    "16D": torch.cat([torch.tensor([D_TRUE / D_SCALE]), A_STAR,
                      torch.tensor([LOGTAU_STAR])]),
}
U0 = {
    "8D": torch.cat([torch.tensor([D0]), torch.full((6,), K0),
                     torch.tensor([LOGTAU0])]),
    "16D": torch.cat([torch.tensor([D0]), torch.full((N_BASIS,), K0),
                      torch.tensor([LOGTAU0])]),
}
assert len(U["8D"]) == 8 and len(U["16D"]) == 16
assert torch.allclose(M @ torch.full((6,), K0), torch.full((14,), K0), atol=1e-12)

CELL = ef.make_cell()


def coeff_of(arm: str, u: torch.Tensor) -> torch.Tensor:
    c = u[1:-1]
    return c if arm == "16D" else M @ c


def observables(arm: str, u: torch.Tensor, grad: bool) -> torch.Tensor:
    d_abs = D_SCALE * u[0]
    coeff = coeff_of(arm, u)
    tau = torch.exp(math.log(TAU_BASE) * u[-1])
    d_stack = torch.stack([torch.tensor(CELL.d_etl, dtype=torch.float64),
                           d_abs,
                           torch.tensor(CELL.d_htl, dtype=torch.float64)])
    nk_rt = torch.empty(5, LAM_RT.shape[0], dtype=torch.complex128)
    nk_rt[0] = 1.0
    nk_rt[1] = CELL.nk_etl
    nk_rt[2] = nk_rbf(coeff, LAM_RT).to(torch.complex128)
    nk_rt[3] = CELL.nk_htl
    nk_rt[4] = 1.5
    with torch.enable_grad() if grad else torch.no_grad():
        J = CELL.jv(d_abs, nk_rbf(coeff, CELL.lam), tau, ef.V_LIST,
                    ift=grad, dV=ef.DV)
        eqe = CELL.eqe_curve(d_abs, nk_rbf(coeff, ef.LAM_EQE), tau,
                             lam_eqe=ef.LAM_EQE, phi_eqe=ef.PHI_EQE, ift=grad)
        rt = field_intensity(nk_rt, d_stack, LAM_RT)
    return torch.cat([J / 30.0, eqe / 0.9, rt["R"], rt["T"]])


with torch.no_grad():
    Y_16 = observables("16D", U["16D"], grad=False)
    Y_8 = observables("8D", U["8D"], grad=False)
assert torch.allclose(Y_16, Y_8, atol=1e-12), "arms must share one target"


def make_loss(arm: str):
    def loss_of(u: torch.Tensor, grad: bool = False) -> torch.Tensor:
        return ((observables(arm, u, grad) - Y_16) ** 2).mean()
    return loss_of


def scalar(f, u: torch.Tensor) -> float:
    with torch.no_grad():
        return float(f(u, grad=False))


def run_arm(arm: str, pilot: bool) -> dict:
    print(f"\n=== arm {arm} (dim={len(U[arm])}) ===", flush=True)
    f = make_loss(arm)
    l_truth, l_start = scalar(f, U[arm]), scalar(f, U0[arm])
    print(f"  loss(truth)={l_truth:.3e}  loss(start)={l_start:.3e}", flush=True)
    assert l_truth < 1e-20, "truth must be representable in BOTH arms"

    n_lb = 8 if pilot else MAX_EVAL_LB
    n_nm = 12 if pilot else MAX_EVAL_NM

    t0 = time.time()
    _, hist_lb, dt_lb = ef.lbfgs_run(f, U0[arm], max_iter=LB_MAX_ITER,
                                     max_eval=n_lb, tag=f"E4C-{arm}-LB")
    print(f"  L-BFGS {len(hist_lb)} calls, {dt_lb:.0f}s, "
          f"final {hist_lb[-1][1]:.3e}", flush=True)

    t1 = time.time()
    _, hist_nm, n_calls = ef.nelder_mead(lambda p: scalar(f, p), U0[arm],
                                        NM_STEP, n_nm)
    dt_nm = time.time() - t1
    print(f"  NM {n_calls} calls, {dt_nm:.0f}s, best {hist_nm[-1][1]:.3e}",
          flush=True)

    rows = []
    for thr in THRESHOLDS:
        a = ef.first_eval_below(hist_lb, thr)
        b = ef.first_eval_below(hist_nm, thr)
        if a and b:
            rows.append({"threshold": thr, "lbfgs": a, "nm": b,
                         "measured_speedup": b / a, "status": "both_reached"})
        elif a and not b:
            rows.append({"threshold": thr, "lbfgs": a, "nm": None,
                         "censored_lower_bound": n_calls / a,
                         "status": "nm_censored"})
        else:
            rows.append({"threshold": thr, "lbfgs": a, "nm": b,
                         "status": "lbfgs_censored_or_neither"})
    measured = [r["measured_speedup"] for r in rows
                if r["status"] == "both_reached"]
    return {
        "dim": len(U[arm]),
        "loss_at_truth": l_truth, "loss_at_start": l_start,
        "lbfgs": {"hist": hist_lb, "n_calls": len(hist_lb), "wall_clock_s": dt_lb},
        "nelder_mead": {"hist": hist_nm, "n_calls": n_calls, "wall_clock_s": dt_nm},
        "rows": rows,
        "min_measured_speedup": min(measured) if measured else None,
        "max_measured_speedup": max(measured) if measured else None,
        "total_wall_clock_s": time.time() - t0,
    }


def main() -> None:
    pilot = "--pilot" in sys.argv
    print("=" * 76)
    print("E4-C  ONE-FACTOR controlled dimension experiment (8-D vs 16-D)")
    print("=" * 76, flush=True)
    R["sanity"] = {
        "shared_target_max_abs_diff": float((Y_16 - Y_8).abs().max()),
        "constant_coeff_map_error": float(
            (M @ torch.full((6,), K0) - torch.full((14,), K0)).abs().max()),
        "n_observables": int(Y_16.shape[0]),
    }
    dump("sanity")
    for arm in ("8D", "16D"):
        R["arms"][arm] = run_arm(arm, pilot)
        dump(f"arm {arm}")

    a, b = R["arms"]["8D"], R["arms"]["16D"]
    def lb_at(arm, thr):
        for r in arm["rows"]:
            if r["threshold"] == thr:
                return r.get("measured_speedup") or r.get("censored_lower_bound")
        return None
    summary = {
        "speedup_at_1e-3": {"8D": lb_at(a, 1e-3), "16D": lb_at(b, 1e-3)},
        "speedup_at_1e-4": {"8D": lb_at(a, 1e-4), "16D": lb_at(b, 1e-4)},
        "interpretation": (
            "Both arms share the same truth, observables, RBF basis, start and "
            "budgets; only the number of free variables differs. A larger "
            "16-D advantage under this protocol supports a dimension effect. "
            "Censored entries are LOWER BOUNDS, never measured ratios. "
            "This experiment does not revise E4 (not met) or E4-H."),
        "pilot": pilot,
    }
    R["summary"] = summary
    dump("summary")
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()
