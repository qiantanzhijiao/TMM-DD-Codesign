"""
UniDD -- E4-H: PRE-REGISTERED high-dimensional supplement to E4.

Purpose
-------
The original, pre-registered E4 (results_final.json) did NOT reach the
>=10x evaluation-count criterion: 3-D gave censored ratios of 7.5--9.4x and
8-D gave only ~3x.  That verdict stands and is reported honestly in the
manuscript.  This experiment is an INDEPENDENT, separately pre-registered
test of the specific hypothesis "the advantage of exact gradients grows with
design-space dimension".  It does not overwrite, re-threshold, or
re-optimise the original E4 result.

Protocol (fixed before execution; mirrored verbatim into results_E4_highdim.json)
--------------------------------------------------------------------------------
* Identical to original E4: loss = mean((observables(u) - y*)^2),
  observable normalisation [J/30, EQE/0.9, R, T], threshold sequence
  [1e-2, 1e-3, 1e-4, 1e-5, 1e-6], L-BFGS settings
  (lr=0.5, max_iter=60, strong_wolfe, history_size=25),
  Nelder-Mead step 0.10, and the HONEST f()-call counter (one history entry
  per objective call; a shrink step costs n+1 calls).
* Dimension raised 8 -> 16: absorber thickness, 14 spectral coefficients,
  SRH lifetime.  The spectrum uses smooth Gaussian RBF (Nadaraya-Watson)
  interpolation instead of the original piecewise-linear/searchsorted
  parametrisation, which is non-differentiable at knot crossings and is a
  genuine numerical cause of stalled high-dimensional inversions.
* R/T wavelengths raised 8 -> 16 so the larger design space stays
  identifiable; R/T are pure TMM (negligible cost) and are applied
  identically to both optimisers.  J-V (6 biases) and EQE (6 wavelengths)
  are unchanged.
* Budgets raised for BOTH optimisers (L-BFGS 150 -> 200, NM 300 -> 600).
  Giving the derivative-free baseline more budget is the conservative choice.
* Start point: same deterministic perturbation rule as original 8-D
  (d 300 nm, all spectral coefficients 0.45, tau 1.5 us); truth is generated
  from u* so loss(u*) = 0 to round-off.  Identical start for both optimisers.
* Verdict rule unchanged: either min observed speedup >= 10, or NM is
  censored at a threshold where L-BFGS succeeded and max_evals_NM >= 10 *
  n_LBFGS (reported explicitly as a LOWER BOUND, never as a measured ratio).
  ADDITIONAL VALIDITY GATE: L-BFGS must itself reach 1e-4; otherwise the
  comparison is declared invalid rather than "passed".

Run:  python experiments_E4_highdim.py [--pilot]
Out:  results_E4_highdim.json   (written incrementally)
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

import experiments_final as ef                                    # noqa: E402
from soldiff.device import CoupledSolarCell                       # noqa: E402
from soldiff.tmm import field_intensity                          # noqa: E402

# ------------------------------------------------------------- fixed protocol
DIM = 16
N_BASIS = DIM - 2                       # 14 spectral coefficients
SIGMA = 55.0                            # [nm] Gaussian RBF width
CENTERS = torch.linspace(350.0, 790.0, N_BASIS)
K_SCALE = 0.72
D_SCALE = 480.0
TAU_BASE = 1e-6
D_TRUE = 480.0
TAU_TRUE = 3.0e-7
LAM_RT_H = torch.linspace(400.0, 780.0, 16)
THRESHOLDS = [1e-2, 1e-3, 1e-4, 1e-5, 1e-6]
MAX_EVAL_LB = 200
MAX_EVAL_NM = 600
LB_MAX_ITER = 60
NM_STEP = 0.10
VALIDITY_THRESHOLD = 1e-4

PROTOCOL = {
    "status": "pre-registered before execution; not altered afterwards",
    "hypothesis": "gradient advantage grows with design-space dimension",
    "relation_to_original_E4": "independent supplement; original FAIL verdict retained",
    "dim": DIM, "n_spectral_basis": N_BASIS, "rbf_sigma_nm": SIGMA,
    "spectrum_parametrisation": "smooth Gaussian RBF / Nadaraya-Watson",
    "reason_for_smooth_basis": "piecewise-linear knots are non-differentiable at crossings",
    "observables": {"JV_biases": list(ef.V_LIST), "dV": ef.DV,
                    "EQE_wavelengths": 6, "R_T_wavelengths": len(LAM_RT_H),
                    "normalisation": ["J/30", "EQE/0.9", "R", "T"]},
    "loss": "mean((observables(u) - y_star)^2)",
    "thresholds": THRESHOLDS,
    "lbfgs": {"lr": 0.5, "max_iter": LB_MAX_ITER, "max_eval": MAX_EVAL_LB,
              "line_search": "strong_wolfe", "history_size": 25},
    "nelder_mead": {"step": NM_STEP, "max_evals": MAX_EVAL_NM,
                    "counter": "one history entry per f() call; shrink = n+1 calls"},
    "budgets": "both optimisers given more budget than original 8-D",
    "start": "d=300 nm, all k coefficients 0.45, tau=1.5 us (same rule as original 8-D)",
    "verdict": "min observed speedup >= 10, or censored lower bound with "
               "max_evals_NM >= 10*n_LBFGS; L-BFGS must reach 1e-4 for validity",
    "dtype": "float64", "seed": 0, "N_dd": ef.N_DD,
}

OUT = ROOT / "results_E4_highdim.json"
R: dict = {"protocol": PROTOCOL}


def dump(tag: str) -> None:
    with open(OUT, "w") as f:
        json.dump(R, f, indent=1)
    print(f"  [saved {tag} -> {OUT.name}]\n", flush=True)


# ------------------------------------------------------------- spectral model
def k_shape(lams: torch.Tensor) -> torch.Tensor:
    """Ground-truth band-edge-like absorption shape (linear on K_KNOTS)."""
    idx = torch.clamp(torch.searchsorted(ef.K_KNOTS, lams), 1,
                      len(ef.K_KNOTS) - 1)
    l0, l1 = ef.K_KNOTS[idx - 1], ef.K_KNOTS[idx]
    w = ((lams - l0) / (l1 - l0)).clamp(0.0, 1.0)
    return ef.K_TRUE[idx - 1] * (1 - w) + ef.K_TRUE[idx] * w


def nk_rbf(coeff: torch.Tensor, lams: torch.Tensor) -> torch.Tensor:
    """Smooth, everywhere-differentiable k(lambda) = weighted RBF sum."""
    w = torch.exp(-((lams[:, None] - CENTERS[None, :]) / SIGMA) ** 2)
    kv = (w @ (K_SCALE * coeff)) / w.sum(dim=1)
    kv = kv.clamp(min=1e-3, max=2.0)
    return torch.complex(torch.full_like(lams, 2.55), kv)


U_STAR = torch.cat([
    torch.tensor([D_TRUE / D_SCALE]),
    k_shape(CENTERS) / K_SCALE,
    torch.tensor([math.log(TAU_TRUE) / math.log(TAU_BASE)]),
])
U_INIT = torch.cat([
    torch.tensor([300.0 / D_SCALE]),
    torch.full((N_BASIS,), 0.45),
    torch.tensor([math.log(1.5e-6) / math.log(TAU_BASE)]),
])
assert U_STAR.shape[0] == DIM and U_INIT.shape[0] == DIM

CELL = ef.make_cell()


def observables(u: torch.Tensor, grad: bool) -> torch.Tensor:
    d_abs = D_SCALE * u[0]
    coeff = u[1:1 + N_BASIS]
    tau = torch.exp(math.log(TAU_BASE) * u[-1])
    d_stack = torch.stack([
        torch.tensor(CELL.d_etl, dtype=torch.float64),
        d_abs,
        torch.tensor(CELL.d_htl, dtype=torch.float64),
    ])
    nk_rt = torch.empty(5, LAM_RT_H.shape[0], dtype=torch.complex128)
    nk_rt[0] = 1.0
    nk_rt[1] = CELL.nk_etl
    nk_rt[2] = nk_rbf(coeff, LAM_RT_H).to(torch.complex128)
    nk_rt[3] = CELL.nk_htl
    nk_rt[4] = 1.5
    with torch.enable_grad() if grad else torch.no_grad():
        J = CELL.jv(d_abs, nk_rbf(coeff, CELL.lam), tau, ef.V_LIST,
                    ift=grad, dV=ef.DV)
        eqe = CELL.eqe_curve(d_abs, nk_rbf(coeff, ef.LAM_EQE), tau,
                             lam_eqe=ef.LAM_EQE, phi_eqe=ef.PHI_EQE, ift=grad)
        rt = field_intensity(nk_rt, d_stack, LAM_RT_H)
    return torch.cat([J / 30.0, eqe / 0.9, rt["R"], rt["T"]])


with torch.no_grad():
    Y_STAR = observables(U_STAR, grad=False)


def loss_of(u: torch.Tensor, grad: bool = False) -> torch.Tensor:
    return ((observables(u, grad) - Y_STAR) ** 2).mean()


def loss_scalar(u: torch.Tensor) -> float:
    with torch.no_grad():
        return float(loss_of(u, grad=False))


def main() -> None:
    t_start = time.time()
    print("=" * 76)
    print("E4-H  pre-registered 16-D supplement (exact IFT gradients vs NM)")
    print("=" * 76, flush=True)

    l0 = float(loss_of(U_STAR, grad=False))
    l_init = loss_scalar(U_INIT)
    print(f"  loss(u*) = {l0:.3e}  (must be ~0);  loss(u_init) = {l_init:.3e}")
    assert l0 < 1e-20, "target observables not generated from u* -- implementation bug"
    R["sanity"] = {"loss_at_truth": l0, "loss_at_start": l_init,
                   "n_observables": int(Y_STAR.shape[0]),
                   "u_star": U_STAR.tolist(), "u_init": U_INIT.tolist()}
    dump("sanity")

    # ---- wall-clock per forward / forward+backward (same convention as E4) --
    with torch.no_grad():
        t0 = time.time()
        for _ in range(3):
            _ = loss_of(U_INIT, grad=False)
        t_fwd = (time.time() - t0) / 3
    t0 = time.time()
    for _ in range(3):
        uu = U_INIT.clone().requires_grad_(True)
        ll = loss_of(uu, grad=True)
        ll.backward()
    t_fwd_bwd = (time.time() - t0) / 3
    R["timing"] = {"t_forward_s": t_fwd, "t_forward_backward_s": t_fwd_bwd,
                   "backward_overhead_factor": t_fwd_bwd / t_fwd}
    print(f"  forward {t_fwd:.2f}s, fwd+bwd {t_fwd_bwd:.2f}s "
          f"({t_fwd_bwd / t_fwd:.2f}x)\n", flush=True)
    dump("timing")

    pilot = "--pilot" in sys.argv
    max_ev_lb = 20 if pilot else MAX_EVAL_LB
    max_ev_nm = 0 if pilot else MAX_EVAL_NM

    # ------------------------------------------------------------- L-BFGS
    print("  --- L-BFGS with exact IFT gradients ---", flush=True)
    u_lb, hist_lb, dt_lb = ef.lbfgs_run(
        loss_of, U_INIT, max_iter=LB_MAX_ITER, max_eval=max_ev_lb,
        tag="E4H-16D-LB")
    print(f"  L-BFGS: {len(hist_lb)} f+grad calls, {dt_lb:.0f}s, "
          f"final loss {hist_lb[-1][1]:.3e}", flush=True)
    R["lbfgs"] = {"hist": hist_lb, "wall_clock_s": dt_lb,
                  "n_calls": len(hist_lb), "final_loss": hist_lb[-1][1],
                  "u_final": u_lb.tolist()}
    dump("lbfgs")

    if pilot:
        print("\n  PILOT ONLY -- no NM run, no verdict.", flush=True)
        return

    # ------------------------------------------------------------- Nelder-Mead
    print("  --- Nelder-Mead (derivative-free, honest f() counting) ---",
          flush=True)
    t0 = time.time()
    f_nm, hist_nm, ne_nm = ef.nelder_mead(
        loss_scalar, U_INIT, step=NM_STEP, max_evals=max_ev_nm)
    dt_nm = time.time() - t0
    print(f"  NM: {ne_nm} f() calls, {dt_nm:.0f}s, best loss {f_nm:.3e}",
          flush=True)
    R["nelder_mead"] = {"hist": hist_nm, "wall_clock_s": dt_nm,
                        "n_calls": ne_nm, "best_loss": f_nm}
    dump("nelder_mead")

    # ------------------------------------------------------------- verdict
    rows = []
    for t in THRESHOLDS:
        a = ef.first_eval_below(hist_lb, t)
        b = ef.first_eval_below(hist_nm, t)
        rows.append({"threshold": t, "lbfgs": a, "nm": b,
                     "status": ("both_reached" if a and b else
                                "nm_censored" if a else
                                "lbfgs_not_reached")})
        print(f"    loss<{t:g}: L-BFGS {a}, NM {b}", flush=True)

    reached = [r for r in rows if r["lbfgs"] and r["nm"]]
    speedup = min((r["nm"] / r["lbfgs"] for r in reached), default=None)
    censored = [r for r in rows if r["lbfgs"] and not r["nm"]
                and MAX_EVAL_NM >= 10 * r["lbfgs"]]
    lb_reaches_1e4 = ef.first_eval_below(hist_lb, VALIDITY_THRESHOLD) is not None
    raw_pass = bool((speedup is not None and speedup >= 10) or censored)
    verdict = ("PASS" if raw_pass and lb_reaches_1e4 else
               "INVALID_NO_COMPARISON" if not lb_reaches_1e4 else "FAIL")
    R["verdict"] = {
        "rows": rows, "min_observed_speedup": speedup,
        "censored_thresholds": [r["threshold"] for r in censored],
        "lbfgs_reaches_1e-4": lb_reaches_1e4,
        "raw_pass": raw_pass, "result": verdict,
        "note": "censored comparisons are LOWER BOUNDS, not measured ratios",
        "total_wall_clock_s": time.time() - t_start,
    }
    dump("verdict")
    print(f"\n  E4-H verdict: {verdict} "
          f"(min observed speedup {speedup}, censored "
          f"{[r['threshold'] for r in censored]})", flush=True)
    print(f"  total {time.time() - t_start:.0f}s -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
