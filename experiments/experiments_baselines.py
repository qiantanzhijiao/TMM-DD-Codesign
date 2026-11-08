"""
UniDD -- multi-start, noisy-target, extended derivative-free baselines.

Companion to experiments_E4_factorial.py.  That experiment is deliberately
one-factor and noise-free; this one deliberately adds the factors that a
general efficiency claim would need:

  * multiple starting points (deterministic perturbations, seeds 0..n-1),
  * 1% relative Gaussian measurement noise on the synthetic observables,
  * baselines beyond Nelder-Mead: Powell, differential evolution, dual
    annealing and a lightweight GP-UCB-style Bayesian optimiser,
  * honest per-f()-call counting, wall-clock, and cross-seed mean / 95% CI.

No external optimisation package beyond SciPy is required (scikit-optimize,
cma and botorch are NOT installed in this environment).  The Bayesian
baseline is an RBF-interpolant UCB acquisition: mean from a Gaussian-kernel
interpolant of evaluated losses, uncertainty from the distance to the nearest
evaluated point.  It is a genuine surrogate-based baseline, not a tuned BO
library; this is stated in the output so the comparison is not oversold.

Run:  python experiments_baselines.py [--pilot]
Out:  results_baselines.json (written incrementally)
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import numpy as np
import torch
from scipy.optimize import differential_evolution, dual_annealing, minimize

torch.set_default_dtype(torch.float64)

import experiments_final as ef
import experiments_E4_factorial as fac

ARM = "16D"
U_STAR, U_INIT = fac.U[ARM], fac.U0[ARM]
DIM = len(U_STAR)
PROBLEM = {
    "arm": ARM, "dim": DIM, "observable_set": fac.PROTOCOL["observables"],
    "noise": "1% relative Gaussian on synthetic observables",
    "starts": "deterministic perturbation of the E4-H start, amplitude 0.02",
    "budget_f_calls_per_run": None,
    "baselines": ["NelderMead", "Powell", "DifferentialEvolution",
                  "DualAnnealing", "RBF-UCB Bayesian"],
    "caveat": "RBF-UCB is a lightweight in-house surrogate baseline, not a tuned BO library",
}


class Objective:
    """One f() = one history entry.  Shared by every baseline."""

    def __init__(self, seed: int):
        g = torch.Generator().manual_seed(seed)
        y = fac.Y_16.clone()
        noise = torch.randn(y.shape, generator=g, dtype=torch.float64) * 0.01
        self.y = y * (1.0 + noise)
        self.hist: list[list] = []
        self.calls = 0
        self.t0 = time.time()

    def __call__(self, u) -> float:
        uu = torch.as_tensor(np.asarray(u, dtype=np.float64), dtype=torch.float64)
        with torch.no_grad():
            val = float(((fac.observables(ARM, uu, grad=False) - self.y) ** 2).mean())
        self.calls += 1
        best = min(self.hist[-1][1], val) if self.hist else val
        self.hist.append([self.calls, best])
        return val

    def result(self):
        return {"hist": self.hist, "n_calls": self.calls,
                "wall_clock_s": time.time() - self.t0,
                "best_loss": self.hist[-1][1] if self.hist else None}


def first_below(hist, thr):
    for n, v in hist:
        if v < thr:
            return n
    return None


def start_for(seed: int):
    g = torch.Generator().manual_seed(1000 + seed)
    return U_INIT + 0.02 * torch.randn(DIM, generator=g, dtype=torch.float64)


# ------------------------------------------------------------------- baselines
def run_nm(obj, x0, budget):
    ef.nelder_mead(lambda p: obj(p.detach().numpy() if torch.is_tensor(p) else p),
                   x0.numpy(), 0.10, budget)


def run_powell(obj, x0, budget):
    n = {"i": 0}

    def f(x):
        if n["i"] >= budget:
            return 1e6
        n["i"] += 1
        return obj(x)

    minimize(f, x0.numpy(), method="Powell",
             options={"maxfev": budget, "xtol": 1e-8, "ftol": 1e-10})


def run_de(obj, x0, budget):
    lo = np.maximum(x0.numpy() - 0.35, 0.05)
    hi = np.minimum(x0.numpy() + 0.35, 2.0)
    n = {"i": 0}

    def f(x):
        if n["i"] >= budget:
            return 1e6
        n["i"] += 1
        return obj(x)

    differential_evolution(f, list(zip(lo, hi)), maxiter=max(1, budget // (10 * DIM)),
                           popsize=8, seed=0, polish=False, tol=1e-10,
                           updating="immediate")


def run_da(obj, x0, budget):
    lo = np.maximum(x0.numpy() - 0.35, 0.05)
    hi = np.minimum(x0.numpy() + 0.35, 2.0)
    n = {"i": 0}

    def f(x):
        if n["i"] >= budget:
            return 1e6
        n["i"] += 1
        return obj(x)

    dual_annealing(f, list(zip(lo, hi)), maxfun=budget, seed=0, no_local_search=True)


def run_bo(obj, x0, budget):
    """Lightweight RBF-interpolant UCB surrogate baseline (no external BO lib)."""
    rnd = np.random.default_rng(0)
    lo = np.maximum(x0.numpy() - 0.35, 0.05)
    hi = np.minimum(x0.numpy() + 0.35, 2.0)
    X, Y = [], []
    for _ in range(min(12, budget)):
        x = rnd.uniform(lo, hi)
        X.append(x)
        Y.append(obj(x))
    while obj.calls < budget:
        Xa, Ya = np.asarray(X), np.asarray(Y)
        # GP-like UCB: kernel mean + distance-based exploration bonus
        cand = rnd.uniform(lo, hi, size=(64, DIM))
        d2 = ((cand[:, None, :] - Xa[None, :, :]) ** 2).sum(-1)
        w = np.exp(-d2 / (2 * 0.15 ** 2))
        mu = (w @ Ya) / np.maximum(w.sum(1), 1e-12)
        sigma = np.sqrt(np.min(d2, axis=1)) / np.sqrt(DIM)
        score = mu - 1.5 * sigma
        x = cand[int(np.argmin(score))]
        X.append(x)
        Y.append(obj(x))


RUNNERS = {"NelderMead": run_nm, "Powell": run_powell,
           "DifferentialEvolution": run_de, "DualAnnealing": run_da,
           "RBF-UCB Bayesian": run_bo}
OUT = ROOT / "results_baselines.json"
R: dict = {"protocol": PROBLEM, "runs": []}


def dump(tag):
    OUT.write_text(json.dumps(R, indent=1), encoding="utf-8")
    print(f"  [saved {tag}]\n", flush=True)


def main():
    pilot = "--pilot" in sys.argv
    seeds, budget = (1, 12) if pilot else (2, 80)
    PROBLEM["budget_f_calls_per_run"] = budget
    PROBLEM["seeds"] = seeds
    print(f"Extended baselines: {seeds} starts x {len(RUNNERS)} methods x "
          f"{budget} f() calls each", flush=True)
    for seed in range(seeds):
        x0 = start_for(seed)
        for name, runner in RUNNERS.items():
            obj = Objective(seed)
            t = time.time()
            runner(obj, x0, budget)
            res = obj.result()
            res.update({"seed": seed, "baseline": name,
                        "calls_to_1e-3": first_below(res["hist"], 1e-3),
                        "calls_to_1e-4": first_below(res["hist"], 1e-4),
                        "loss_at_common_budget": res["hist"][min(budget, len(res["hist"])) - 1][1]})
            R["runs"].append(res)
            print(f"  seed {seed} {name:22s} calls={res['n_calls']:3d} "
                  f"best={res['best_loss']:.3e} ({time.time()-t:.0f}s)", flush=True)
            dump(f"seed{seed}-{name}")

    # cross-seed summary at the common budget
    summary = {}
    for name in RUNNERS:
        vals = [r["loss_at_common_budget"] for r in R["runs"] if r["baseline"] == name]
        arr = np.asarray(vals, dtype=float)
        times = [r["wall_clock_s"] for r in R["runs"] if r["baseline"] == name]
        summary[name] = {
            "mean_best_loss": float(arr.mean()),
            "std_best_loss": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
            "ci95_half_width": float(1.96 * arr.std(ddof=1) / math.sqrt(len(arr)))
                               if len(arr) > 1 else 0.0,
            "mean_wall_clock_s": float(np.mean(times)),
            "n_seeds": len(arr),
        }
    R["summary"] = summary
    R["interpretation"] = (
        "These runs add multiple starts, measurement noise and several "
        "derivative-free baselines. They are robustness evidence, NOT a "
        "revision of the pre-registered E4 verdict or of the one-factor E4-C "
        "experiment (which is intentionally noise-free).")
    dump("summary")
    print(json.dumps(summary, indent=1), flush=True)


if __name__ == "__main__":
    main()
