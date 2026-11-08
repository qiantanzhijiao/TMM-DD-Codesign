"""
UniDD -- final, post-correction validation and benchmark suite.

This is the SINGLE source of truth for every numerical value quoted in the
Solar Energy manuscript.  It supersedes experiments_E1_E2.py,
experiments_E3v2.py and experiments_E4v3.py, which were produced with the
uncorrected generation rate (missing the Poynting factor n_r/n_0) and with an
incorrect Nelder-Mead evaluation counter (one history entry per *iteration*,
not per function call).

Run:  python experiments_final.py
Out:  results_final.json   (written incrementally after every stage)

Stages
------
E0  external/absolute optical validation (energy balance, Beer-Lambert,
    regression power, coherent -> incoherent degeneration)
E1  gradient verification: pure optics chain, isolated DD path, full chain
    per coordinate, Richardson FD, solver-tolerance sweep, adjoint residual
E2  physical validation: dark current, ideality, qGL limit, EQE/J-V
    consistency, optical Jsc bound, figures of merit, DD mesh convergence
E3  three-parameter inverse design (L-BFGS + exact IFT gradients)
E4  evaluation-count and wall-clock benchmark L-BFGS vs Nelder-Mead in 3-D
    and 8-D, with TRUE f() call accounting for the derivative-free baseline
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

from soldiff.device import CoupledSolarCell, am15_flux          # noqa: E402
from soldiff.dd import DDDevice, Q, KB, newton_ift, make_residual  # noqa: E402
from soldiff.tmm import (field_intensity, generation_rate,       # noqa: E402
                         absorbed_fraction)

OUT = ROOT / "results_final.json"
R: dict = {"meta": {"N_dd": 73, "dtype": "float64", "seed": 0,
                    "note": "post-Poynting-correction; single source of truth"}}


def dump(tag: str) -> None:
    with open(OUT, "w") as f:
        json.dump(R, f, indent=1)
    print(f"  [saved stage {tag} -> {OUT.name}]\n", flush=True)


def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(s)
    print("=" * 76, flush=True)


# ----------------------------------------------------------------- shared setup
N_DD = 73
V_LIST = [0.0, 0.4, 0.7, 0.9, 1.0, 1.06]
DV = 0.05
LAM_EQE = torch.linspace(420.0, 760.0, 6)
PHI_EQE = am15_flux(LAM_EQE)
LAM_RT = torch.linspace(400.0, 780.0, 8)
V_METRICS = [round(0.02 * i, 10) for i in range(0, 61)]   # 0 -> 1.20 V, 61 pts

K_KNOTS = torch.tensor([350.0, 450.0, 550.0, 650.0, 720.0, 790.0])
K_TRUE = torch.tensor([0.85, 0.80, 0.72, 0.60, 0.42, 0.18])
D_TRUE_8, TAU_TRUE_8 = 460.0, 3.5e-7
D_TRUE_3, K_TRUE_3, TAU_TRUE_3 = 480.0, 0.72, 3.0e-7


def make_cell() -> CoupledSolarCell:
    return CoupledSolarCell(N_dd=N_DD)


def nk_simple(k_amp, lams=None, cell=None):
    l = cell.lam if (lams is None and cell is not None) else (
        make_cell().lam if lams is None else lams)
    k = k_amp * torch.exp(-torch.relu(l - 800.0) / 60.0) + 1e-3
    return torch.complex(torch.full_like(l, 2.55), k)


def nk_knots(kamp: torch.Tensor, lams: torch.Tensor) -> torch.Tensor:
    idx = torch.clamp(torch.searchsorted(K_KNOTS, lams), 1, len(K_KNOTS) - 1)
    l0, l1 = K_KNOTS[idx - 1], K_KNOTS[idx]
    w = ((lams - l0) / (l1 - l0)).clamp(0.0, 1.0)
    kv = kamp[idx - 1] * (1 - w) + kamp[idx] * w + 1e-3
    return torch.complex(torch.full_like(lams, 2.55), kv)


# ===================================================================== E0
def stage_E0() -> None:
    banner("E0  external/absolute validation of the optical model")
    cell = make_cell()
    lam = torch.linspace(400.0, 800.0, 81)
    k = 0.65 * torch.ones_like(lam)
    nk = torch.empty(5, lam.shape[0], dtype=torch.complex128)
    nk[0] = 1.0
    nk[1] = 2.0 + 0.0j
    nk[2] = torch.complex(torch.full_like(lam, 2.55), k)
    nk[3] = 1.5 + 0.005j
    nk[4] = 1.5
    d = torch.tensor([50.0, 420.0, 150.0], dtype=torch.float64)

    devs = {}
    for ng in (201, 501, 2001):
        o = absorbed_fraction(nk, d, lam, n_grid=ng)
        devs[ng] = float((o["A_field"] - o["A_poynting"]).abs().max())
        print(f"  energy balance, {ng:5d} pts/layer: "
              f"max |A_field-(1-R-T)| = {devs[ng]:.3e}")
    e0 = {"energy_balance_max_dev": devs,
          "energy_balance_converges": bool(devs[201] > devs[501] > devs[2001]),
          "mean_absorptance": float(o["A_field"].mean()),
          "mean_R": float(o["R"].mean()), "mean_T": float(o["T"].mean())}

    # regression: dropping n_r/n_0 must break the balance
    z = torch.linspace(0.0, float(d.sum()), 4001, dtype=torch.float64)
    raw = field_intensity(nk, d, lam, z_grid=z)
    nk_j = nk[1 + raw["layer_id"]].t()
    alpha_z = 4.0 * torch.pi * nk_j.imag / lam[:, None]
    A_bug = torch.trapz(alpha_z * raw["I2"], z.expand_as(alpha_z), dim=1)
    e0["bug_A_mean"] = float(A_bug.mean())
    e0["correct_A_mean"] = float(o["A_poynting"].mean())
    e0["bug_max_dev"] = float((A_bug - o["A_poynting"]).abs().max())
    print(f"  regression: omitting n_r/n_0 gives mean A = {e0['bug_A_mean']:.4f} "
          f"vs Poynting {e0['correct_A_mean']:.4f}")

    # analytic Beer-Lambert limit with a genuinely index-matched slab
    lam1 = torch.tensor([500.0, 600.0, 700.0])
    kv = torch.tensor([0.10, 0.20, 0.35])
    nk1 = torch.empty(3, 3, dtype=torch.complex128)
    for j in range(3):
        nk1[j] = torch.complex(torch.ones_like(lam1), kv)
    d1 = torch.tensor([300.0], dtype=torch.float64)
    out1 = absorbed_fraction(nk1, d1, lam1, n_grid=4001)
    A_ana = 1.0 - torch.exp(-(4.0 * torch.pi * kv / lam1) * d1[0])
    e0["beer_lambert_max_dev"] = float((out1["A_field"] - A_ana).abs().max())
    e0["index_matched_max_R"] = float(out1["R"].abs().max())
    print(f"  Beer-Lambert limit max deviation = {e0['beer_lambert_max_dev']:.3e}, "
          f"max R = {e0['index_matched_max_R']:.3e}")

    # coherent -> incoherent degeneration
    lam2 = torch.tensor([600.0])
    ratios = {}
    for thick in (200.0, 600.0, 1500.0, 3000.0):
        nk2 = torch.empty(3, 1, dtype=torch.complex128)
        nk2[0] = 1.0
        nk2[1] = 2.55 + 0.30j
        nk2[2] = 1.5
        d2 = torch.tensor([thick], dtype=torch.float64)
        zz = torch.linspace(0.0, thick, 20001, dtype=torch.float64)
        coh = field_intensity(nk2, d2, lam2, z_grid=zz)
        inc = field_intensity(nk2, d2, lam2, z_grid=zz,
                              incoherent_mask=torch.tensor([True]))
        ratios[thick] = float((coh["I2"] - inc["I2"]).abs().mean()
                              / inc["I2"].abs().mean())
    e0["coherent_to_incoherent"] = ratios
    print(f"  interference decay: {ratios[200.0]:.2e} -> {ratios[3000.0]:.2e}")

    checks = [devs[2001] < 1e-4, e0["energy_balance_converges"],
              e0["bug_max_dev"] > 0.1,
              e0["beer_lambert_max_dev"] < 1e-5,
              e0["index_matched_max_R"] < 1e-12,
              ratios[3000.0] < ratios[200.0] and ratios[3000.0] < 1e-2]
    e0["checks_passed"] = int(sum(checks))
    e0["checks_total"] = len(checks)
    e0["pass"] = bool(all(checks))
    print(f"  E0: {sum(checks)}/{len(checks)} checks passed")
    R["E0"] = e0
    dump("E0")


# ===================================================================== E1
def stage_E1() -> None:
    banner("E1  gradient verification (IFT / autodiff vs finite differences)")
    cell = make_cell()
    lam = cell.lam
    TH0 = torch.tensor([420.0, 0.65, math.log(2.5e-7)])
    SCALE = torch.tensor([480.0, 0.72, math.log(1e-6)])
    STEP = [abs(float(x)) for x in SCALE]      # plain floats: keep JSON clean
    v = torch.nn.functional.normalize(torch.tensor([0.4, -0.7, 0.6]), dim=0)
    VL = [0.0, 0.3, 0.6, 0.9]

    def objective(th, grad=False, c=None):
        c = c or cell
        J = c.jv(th[0], nk_simple(th[1], cell=c), torch.exp(th[2]),
                 VL, ift=grad, dV=DV)
        return ((J / 30.0) ** 2).mean()

    e1: dict = {"V_list": VL, "dV": DV}

    # (a) pure optical chain
    kt = torch.tensor(0.65, requires_grad=True)
    Go = cell.optics(TH0[0].detach(), nk_simple(kt, cell=cell))[0].sum()
    g_ad = float(torch.autograd.grad(Go, kt)[0])
    h = 1e-6
    gp = cell.optics(TH0[0].detach(), nk_simple(torch.tensor(0.65 + h), cell=cell))[0].sum()
    gm = cell.optics(TH0[0].detach(), nk_simple(torch.tensor(0.65 - h), cell=cell))[0].sum()
    g_fd = float(gp - gm) / (2 * h)
    e1["optics_chain"] = {"ad": g_ad, "fd": g_fd,
                          "rel_err": abs(g_ad - g_fd) / max(abs(g_fd), 1e-30)}
    print(f"  [a] pure optics chain   AD {g_ad:.6e}  FD {g_fd:.6e}  "
          f"rel {e1['optics_chain']['rel_err']:.2e}")

    # (b) per-coordinate full-chain AD vs Richardson FD
    th = TH0.clone().requires_grad_(True)
    g = torch.autograd.grad(objective(th, grad=True), th)[0]
    g_ad_vec = [float(x) for x in g]
    per_coord = []
    for i, name in enumerate(("d_abs", "k_amp", "log_tau")):
        def f_scalar(delta, ii=i):
            t = TH0.clone()
            t[ii] = t[ii] + delta
            with torch.no_grad():
                return float(objective(t))

        hs = [0.01 * STEP[i], 0.005 * STEP[i], 0.0025 * STEP[i]]
        D = []
        for hh in hs:
            D.append((f_scalar(hh) - f_scalar(-hh)) / (2 * hh))
        r2a = (4.0 * D[1] - D[0]) / 3.0
        r2b = (4.0 * D[2] - D[1]) / 3.0
        r4 = (16.0 * r2b - r2a) / 15.0
        rel = abs(g_ad_vec[i] - r4) / max(abs(g_ad_vec[i]), abs(r4), 1e-30)
        per_coord.append({"param": name, "ad": g_ad_vec[i],
                          "fd_central": float(D[0]),
                          "fd_central_by_h": [float(x) for x in D],
                          "fd_richardson2": float(r2a),
                          "fd_richardson4": float(r4),
                          "h_values": [float(x) for x in hs],
                          "rel_err": float(rel)})
        print(f"  [b] {name:8s} AD {g_ad_vec[i]:+.6e}  FD_R4 {r4:+.6e}  "
              f"rel {rel:.2e}")
    e1["per_coordinate"] = per_coord

    gd = float((g * v * SCALE).sum())
    e1["directional"] = {"ad": gd, "per_coordinate_contributions":
                         [float(g[i] * v[i] * SCALE[i]) for i in range(3)]}
    print(f"  [b] directional AD = {gd:.6e}, contributions "
          f"{[round(x, 6) for x in e1['directional']['per_coordinate_contributions']]}")

    # (c) path isolation: hold dx fixed -> optics only; hold G fixed -> electrical only
    om, oo = cell.mesh_diff, cell.optics
    fixed_mesh = {k: (vv.detach().clone() if isinstance(vv, torch.Tensor) else vv)
                  for k, vv in om(TH0[0].detach()).items()}
    fixed_G = oo(TH0[0].detach(),
                 nk_simple(TH0[1].detach(), cell=cell))[0].detach().clone()

    def iso_ad(mode):
        c2 = make_cell()
        if mode == "optics":
            c2.mesh_diff = lambda dd: fixed_mesh
        else:
            c2.optics = lambda dd, nn: (fixed_G, None, None)
        t = TH0.clone().requires_grad_(True)
        L = objective(t, grad=True, c=c2)
        return float(torch.autograd.grad(L, t)[0][0])

    def iso_fd(mode, base=0.01 * STEP[0]):
        c2 = make_cell()
        if mode == "optics":
            c2.mesh_diff = lambda dd: fixed_mesh
        else:
            c2.optics = lambda dd, nn: (fixed_G, None, None)
        Ds = []
        for hh in (base, base / 2, base / 4):
            with torch.no_grad():
                tp, tm = TH0.clone(), TH0.clone()
                tp[0] += hh
                tm[0] -= hh
                Ds.append((float(objective(tp, c=c2))
                           - float(objective(tm, c=c2))) / (2 * hh))
        r2a = (4.0 * Ds[1] - Ds[0]) / 3.0
        r2b = (4.0 * Ds[2] - Ds[1]) / 3.0
        return (16.0 * r2b - r2a) / 15.0

    iso = {}
    for mode in ("optics", "electrical"):
        a, f_ = iso_ad(mode), iso_fd(mode)
        iso[mode] = {"ad": a, "fd": f_,
                     "rel_err": abs(a - f_) / max(abs(a), abs(f_), 1e-30)}
        print(f"  [c] {mode:10s} path  AD {a:+.6e}  FD {f_:+.6e}  "
              f"rel {iso[mode]['rel_err']:.2e}")
    e1["isolated_paths"] = iso
    e1["cancellation_ratio"] = abs(
        max(abs(iso["optics"]["ad"]), abs(iso["electrical"]["ad"]))
        / max(abs(iso["optics"]["ad"] + iso["electrical"]["ad"]), 1e-30))

    # (d) solver-tolerance sweep (does tightening fix the composite gap?)
    direction = v * SCALE
    sweep = []

    def dir_fd(hh, floor):
        cell.dd.abs_floor = floor
        with torch.no_grad():
            lp = objective(TH0 + hh * direction)
            lm = objective(TH0 - hh * direction)
        return float((lp - lm) / (2 * hh))

    for floor in (3e2, 3e1, 3e0, 3e-1, 3e-2):
        cell.dd.abs_floor = floor
        t = TH0.clone().requires_grad_(True)
        gg = torch.autograd.grad(objective(t, grad=True), t)[0]
        gdir = float((gg * direction).sum())
        d1 = dir_fd(1e-2, floor)
        d2 = dir_fd(5e-3, floor)
        dr = (4.0 * d2 - d1) / 3.0
        rel = abs(gdir - dr) / max(abs(gdir), abs(dr), 1e-30)
        sweep.append({"abs_floor": floor, "ad": gdir, "fd_richardson": dr,
                      "rel_err": rel})
        print(f"  [d] abs_floor {floor:8.0e}  AD {gdir:+.6e}  "
              f"FD_R {dr:+.6e}  rel {rel:.2e}")
    cell.dd.abs_floor = 3e2
    e1["tolerance_sweep"] = sweep
    e1["error_decreases_with_tighter_tolerance"] = bool(
        sweep[-1]["rel_err"] < sweep[0]["rel_err"])
    e1["interpretation"] = (
        "The original solver declared convergence relative to the WARM-START "
        "residual; after a bias step that residual can be 1e17 A/m^3, so the "
        "returned iterate had |F| ~ 1e8 and was not a root. IFT gradients "
        "evaluated there were biased. Convergence is now measured on the "
        "physical scale q*G_max with a Newton-step test, so x* is a true "
        "root. The composite d_abs gradient is still the difference of two "
        "O(5e-3) optical and electrical contributions (cancellation ratio "
        "~45), which amplifies the residual round-off; this is reported "
        "honestly rather than hidden by a single directional number.")

    # (e) adjoint linear-solve residual (verifies the IFT backward itself)
    c3 = make_cell()
    G, _, _ = c3.optics(TH0[0].detach(), nk_simple(TH0[1].detach(), cell=c3))
    Gm, _ = c3._interp_to_mesh(G, None)
    m = c3.mesh_diff(TH0[0].detach())
    tau0 = torch.exp(TH0[2]).detach()
    eps = c3.dd.eps_r * 8.8541878128e-12
    # one input must require grad so the custom Function output has a graph
    Gleaf = Gm.detach().clone().requires_grad_(True)
    th_list = [Gleaf, tau0, tau0,
               torch.as_tensor(2e-4 * c3.dd.VT, dtype=torch.float64),
               torch.as_tensor(2e-4 * c3.dd.VT, dtype=torch.float64),
               m["psi0"].detach(), m["psiL"].detach(), m["dx"].detach()]
    res = make_residual(torch.tensor(c3.dd.ni, dtype=torch.float64), c3.dd.VT,
                        eps, m["dx"], m["psi0"], m["psiL"], 0.0,
                        tau0, tau0, th_list[3], th_list[4], Gm)
    x_eq = c3.dd.equilibrium(m["dx"], m["psi0"], m["psiL"])
    x0 = torch.cat([x_eq[1:-1], -x_eq[1:-1], -x_eq[1:-1]])
    for refine in (1, 3, 6):
        info = {}
        xr = newton_ift(res, x0, th_list, max_iter=40, tol=1e-9,
                        n_int=c3.dd.N - 2, info=info,
                        adjoint_refine=refine)
        xr.sum().backward()
        e1.setdefault("adjoint_residual", []).append(
            {"refine": refine, "rel_residual": info.get("adjoint_residual_rel"),
             "newton_iters": info.get("iters"),
             "newton_converged": info.get("converged")})
        print(f"  [e] adjoint refine={refine}: "
              f"relative residual {info.get('adjoint_residual_rel'):.3e}")

    # (f) demonstrate the solver now returns genuine roots along the J-V walk
    Dg = torch.as_tensor(2e-4 * c3.dd.VT, dtype=torch.float64)
    epsr = c3.dd.eps_r * 8.8541878128e-12
    walk_diag = []
    xw = None
    for Vwalk in [0.0, 0.3, 0.6, 0.9]:
        oo = c3.dd.solve_state(Gm, Vwalk, m["dx"].detach(), m["psi0"],
                               m["psiL"], tau0, tau0, x0=xw, ift=False)
        xw = oo["x"].detach()
        rv = make_residual(torch.tensor(c3.dd.ni, dtype=torch.float64),
                           c3.dd.VT, epsr, m["dx"], m["psi0"], m["psiL"],
                           Vwalk, tau0, tau0, Dg, Dg, Gm)
        Fv = rv(xw, [Gm, tau0, tau0, Dg, Dg, m["psi0"], m["psiL"], m["dx"]])
        walk_diag.append({"V": Vwalk, "iters": int(oo["iters"]),
                          "converged": bool(oo["converged"]),
                          "max_abs_residual": float(Fv.abs().max())})
    e1["solver_walk"] = walk_diag
    print("  [f] solver walk: " + ", ".join(
        f"V={q['V']:.1f} it={q['iters']} conv={q['converged']} "
        f"|F|={q['max_abs_residual']:.1e}" for q in walk_diag))

    e1["optics_chain_rel_err"] = e1["optics_chain"]["rel_err"]
    e1["best_isolated_path_rel_err"] = max(
        iso["optics"]["rel_err"], iso["electrical"]["rel_err"])
    e1["full_chain_directional_rel_err"] = sweep[0]["rel_err"]
    e1["worst_per_coordinate_rel_err"] = max(p["rel_err"] for p in per_coord)
    e1["pass"] = bool(e1["optics_chain"]["rel_err"] < 1e-6
                      and e1["best_isolated_path_rel_err"] < 1e-3
                      and e1["worst_per_coordinate_rel_err"] < 1e-2
                      and e1["full_chain_directional_rel_err"] < 1e-2)
    print(f"  E1 pass = {e1['pass']} (optics chain {e1['optics_chain']['rel_err']:.2e}, "
          f"isolated paths <= {e1['best_isolated_path_rel_err']:.2e}, "
          f"per-coordinate <= {e1['worst_per_coordinate_rel_err']:.2e}, "
          f"directional {sweep[0]['rel_err']:.2e})")
    R["E1"] = e1
    dump("E1")


# ===================================================================== E2
def stage_E2() -> None:
    banner("E2  physical validation and device figures of merit")
    cell = make_cell()
    lam = cell.lam
    d0 = torch.tensor(480.0)
    k0 = torch.tensor(0.72)
    tau0 = torch.tensor(3.0e-7)
    nk0 = nk_simple(k0, cell=cell)
    mm = cell.mesh_diff(d0)
    e2: dict = {}

    # (a) energy balance at the operating stack
    nk = torch.empty(5, lam.shape[0], dtype=torch.complex128)
    nk[0] = 1.0
    nk[1] = cell.nk_etl
    nk[2] = nk0
    nk[3] = cell.nk_htl
    nk[4] = 1.5
    d_stack = torch.stack([torch.tensor(cell.d_etl, dtype=torch.float64),
                           d0, torch.tensor(cell.d_htl, dtype=torch.float64)])
    out = field_intensity(nk, d_stack, lam)
    e2["mean_R"] = float(out["R"].mean())
    e2["mean_T"] = float(out["T"].mean())
    e2["R_plus_T_leq_1"] = bool((out["R"] + out["T"] <= 1 + 1e-9).all())
    print(f"  [a] mean R {e2['mean_R']:.4f}, mean T {e2['mean_T']:.4f}, "
          f"R+T<=1: {e2['R_plus_T_leq_1']}")

    # (b) thermal-equilibrium dark current
    o = cell.dd.solve_state(torch.zeros(cell.dd.N), 0.0, mm["dx"].detach(),
                            mm["psi0"], mm["psiL"], tau0, tau0)
    e2["J_eq_dark_A_m2"] = float(o["J"])
    print(f"  [b] equilibrium dark J = {e2['J_eq_dark_A_m2']:.3e} A/m2")

    # (c) dark ideality factor
    x, Vs, Jd = None, [], []
    for Vi in range(58):
        V = Vi * 0.02
        oo = cell.dd.solve_state(torch.zeros(cell.dd.N), V, mm["dx"].detach(),
                                 mm["psi0"], mm["psiL"], tau0, tau0, x0=x)
        x = oo["x"].detach()
        Vs.append(V)
        Jd.append(float(oo["J"]))
    n_id = None
    for i in range(1, len(Vs)):
        if abs(Jd[i]) > 1.0 and abs(Jd[i - 1]) > 1.0:
            slope = ((Vs[i] - Vs[i - 1])
                     / (math.log(abs(Jd[i])) - math.log(abs(Jd[i - 1]))))
            n_id = slope / (KB * 300 / Q)
    e2["dark_ideality_factor"] = n_id
    print(f"  [c] dark ideality factor n = {n_id:.3f}")

    # (d) uniform generation -> analytic q G L
    G_u = 4.7e27
    o = cell.dd.solve_state(torch.full((cell.dd.N,), G_u), 0.0,
                            mm["dx"].detach(), mm["psi0"], mm["psiL"],
                            tau0, tau0)
    J_num = float(o["J"]) / 10.0
    J_ana = Q * G_u * 480e-9 / 10.0
    e2["uniformG_ratio"] = J_num / J_ana
    e2["uniformG_Jsc"] = J_num
    e2["uniformG_analytic"] = J_ana
    print(f"  [d] uniform-G Jsc {J_num:.2f} vs qGL {J_ana:.2f} mA/cm2 "
          f"(ratio {e2['uniformG_ratio']:.4f})")

    # (e) optical upper bound on Jsc (external validation of corrected G)
    o_abs = absorbed_fraction(nk, d_stack, lam, n_grid=2001)
    phi = am15_flux(lam)
    Jsc_opt = float(torch.trapz(phi * o_abs["A_field"], lam) * Q * 1e4 / 10.0)
    e2["Jsc_optical_upper_bound"] = Jsc_opt
    print(f"  [e] optical upper bound Jsc = {Jsc_opt:.2f} mA/cm2")

    # (f) EQE-integrated Jsc vs J-V Jsc
    t0 = time.time()
    lam_eqe = torch.linspace(380.0, 790.0, 21)
    phi_eqe = am15_flux(lam_eqe)
    eqe = cell.eqe_curve(d0, nk_simple(k0, lams=lam_eqe), tau0,
                         lam_eqe=lam_eqe, phi_eqe=phi_eqe)
    Jsc_eqe = float((eqe * phi_eqe * (lam_eqe[1] - lam_eqe[0])).sum()
                    * Q * 1e4 / 10.0)
    with torch.no_grad():
        Jv0 = cell.jv(d0, nk0, tau0, [0.0], dV=DV)
    Jsc_jv = float(Jv0[0])
    e2["Jsc_eqe"] = Jsc_eqe
    e2["Jsc_jv"] = Jsc_jv
    e2["Jsc_consistency_rel_dev"] = abs(Jsc_eqe - Jsc_jv) / Jsc_jv
    e2["mean_EQE"] = float(eqe.mean())
    print(f"  [f] EQE-integrated Jsc {Jsc_eqe:.2f} vs J-V {Jsc_jv:.2f} mA/cm2 "
          f"(dev {100 * e2['Jsc_consistency_rel_dev']:.2f}%, mean EQE "
          f"{e2['mean_EQE']:.3f}, {time.time()-t0:.0f}s)")

    # (g) full J-V metrics
    t0 = time.time()
    with torch.no_grad():
        J = cell.jv(d0, nk0, tau0, V_METRICS, dV=DV)
    Vt = torch.tensor(V_METRICS)
    met = CoupledSolarCell.metrics(Vt, J)
    e2["metrics"] = {k: float(vv) for k, vv in met.items()}
    print(f"  [g] Jsc {float(met['Jsc']):.2f} mA/cm2, Voc {float(met['Voc']):.3f} V, "
          f"FF {float(met['FF']):.3f}, PCE {100*float(met['PCE']):.2f}%  "
          f"({time.time()-t0:.0f}s)")
    e2["jv_curve"] = {"V": V_METRICS, "J": [float(x) for x in J]}

    # (h) DD mesh convergence
    conv = []
    for Nd in (49, 73, 97):
        cm = CoupledSolarCell(N_dd=Nd)
        with torch.no_grad():
            Jm = cm.jv(d0, nk_simple(k0, cell=cm), tau0, V_METRICS, dV=DV)
        mm2 = CoupledSolarCell.metrics(Vt, Jm)
        conv.append({"N_dd": Nd, "Jsc": float(mm2["Jsc"]),
                     "Voc": float(mm2["Voc"]), "PCE": float(mm2["PCE"])})
        print(f"  [h] N_dd {Nd:3d}: Jsc {float(mm2['Jsc']):.3f}, "
              f"Voc {float(mm2['Voc']):.4f}, PCE {100*float(mm2['PCE']):.3f}%")
    e2["mesh_convergence"] = conv
    e2["Jsc_grid_rel_change"] = abs(conv[-1]["Jsc"] - conv[0]["Jsc"]) / conv[-1]["Jsc"]

    checks = [e2["R_plus_T_leq_1"],
              abs(e2["J_eq_dark_A_m2"]) < 1e-6,
              1.0 <= (n_id or 0) <= 2.0,
              abs(e2["uniformG_ratio"] - 1) < 0.05,
              e2["Jsc_consistency_rel_dev"] < 0.05,
              Jsc_jv <= Jsc_opt * 1.02,
              e2["Jsc_grid_rel_change"] < 0.02]
    e2["checks_passed"] = int(sum(checks))
    e2["checks_total"] = len(checks)
    e2["pass"] = bool(all(checks))
    print(f"  E2: {sum(checks)}/{len(checks)} checks passed")
    R["E2"] = e2
    dump("E2")


# ============================================================ E3/E4 machinery
def build_observables(cell, ndim: int):
    """Return (observables_fn, u_star, u_init, decode_fn)."""
    if ndim == 3:
        def decode(u):
            return (480.0 * u[0],
                    torch.clamp(0.72 * u[1], 1e-3, 2.0),
                    torch.exp(math.log(3e-7) * u[2]))

        def nk_build(k, lams):
            return nk_simple(k, lams=lams)

        u_star = torch.tensor([1.0, 1.0, 1.0])
        u_init = torch.tensor([300.0 / 480.0, 0.35 / 0.72,
                               math.log(1.5e-6) / math.log(3e-7)])
    else:
        def decode(u):
            return (480.0 * u[0],
                    torch.clamp(0.72 * u[1:7], min=1e-3),
                    torch.exp(math.log(1e-6) * u[7]))

        def nk_build(k, lams):
            return nk_knots(k, lams)

        u_star = torch.cat([torch.tensor([D_TRUE_8 / 480.0]), K_TRUE / 0.72,
                            torch.tensor([math.log(TAU_TRUE_8) / math.log(1e-6)])])
        u_init = torch.cat([torch.tensor([300.0 / 480.0]), torch.full((6,), 0.45),
                            torch.tensor([math.log(1.5e-6) / math.log(1e-6)])])

    def observables(u, grad: bool):
        d_abs, kpar, tau = decode(u)
        d_stack = torch.stack([torch.tensor(cell.d_etl, dtype=torch.float64),
                               d_abs,
                               torch.tensor(cell.d_htl, dtype=torch.float64)])
        nk_rt = torch.empty(5, LAM_RT.shape[0], dtype=torch.complex128)
        nk_rt[0] = 1.0
        nk_rt[1] = cell.nk_etl
        nk_rt[2] = nk_build(kpar, LAM_RT).to(torch.complex128)
        nk_rt[3] = cell.nk_htl
        nk_rt[4] = 1.5
        with torch.enable_grad() if grad else torch.no_grad():
            J = cell.jv(d_abs, nk_build(kpar, cell.lam), tau,
                        V_LIST, ift=grad, dV=DV)
            eqe = cell.eqe_curve(d_abs, nk_build(kpar, LAM_EQE), tau,
                                 lam_eqe=LAM_EQE, phi_eqe=PHI_EQE, ift=grad)
            rt = field_intensity(nk_rt, d_stack, LAM_RT)
        # J/30, EQE/0.9, R, T -- all O(1) with the corrected optical model
        return torch.cat([J / 30.0, eqe / 0.9, rt["R"], rt["T"]])

    return observables, u_star, u_init, decode


def nelder_mead(f, x0, step, max_evals):
    """Nelder-Mead with an HONEST evaluation counter: history is
    (cumulative f() calls, best-so-far) recorded after EVERY f() call.

    The previous implementation appended one entry per *iteration* and then
    used the history index as an evaluation count.  A shrink step costs n+1
    function calls, so that under-counted derivative-free work badly.
    """
    n = len(x0)
    calls = {"n": 0}
    hist = []

    def ev(p):
        val = float(f(p))
        calls["n"] += 1
        hist.append([calls["n"], min(hist[-1][1], val) if hist else val])
        return val

    pts = [torch.tensor(x0, dtype=torch.float64)]
    for i in range(n):
        p = torch.tensor(x0, dtype=torch.float64)
        p[i] += step
        pts.append(p)
    vals = [ev(p) for p in pts]
    while calls["n"] < max_evals:
        order = sorted(range(len(pts)), key=lambda i: vals[i])
        pts = [pts[i] for i in order]
        vals = [vals[i] for i in order]
        c = torch.stack(pts[:-1]).mean(0)
        xr = c + (c - pts[-1])
        fr = ev(xr)
        if fr < vals[0]:
            xe = c + 2 * (xr - c)
            fe = ev(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (pts[-1] - c)
            fc = ev(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                for i in range(1, len(pts)):
                    pts[i] = pts[0] + 0.5 * (pts[i] - pts[0])
                    vals[i] = ev(pts[i])
    return min(vals), hist, calls["n"]


def lbfgs_run(loss_of, u_init, max_iter, max_eval, tag):
    u = u_init.clone().requires_grad_(True)
    opt = torch.optim.LBFGS([u], lr=0.5, max_iter=max_iter, max_eval=max_eval,
                            tolerance_grad=1e-12, tolerance_change=1e-14,
                            history_size=25, line_search_fn="strong_wolfe")
    counter = {"n": 0}
    hist = []
    t0 = time.time()

    def closure():
        opt.zero_grad()
        loss = loss_of(u, grad=True)
        loss.backward()
        counter["n"] += 1
        hist.append([counter["n"], float(loss)])
        if counter["n"] % 20 == 0:
            print(f"    [{tag}] eval {counter['n']:3d} loss {float(loss):.3e} "
                  f"({time.time()-t0:.0f}s)", flush=True)
        return loss

    opt.step(closure)
    return u.detach(), hist, time.time() - t0


def first_eval_below(hist, thr):
    for n, v in hist:
        if v < thr:
            return n
    return None


# ===================================================================== E3
def stage_E3() -> None:
    banner("E3  three-parameter inverse design (L-BFGS + exact IFT gradients)")
    cell = make_cell()
    obs, u_star, u_init, decode = build_observables(cell, 3)
    with torch.no_grad():
        y_star = obs(u_star, grad=False)

    def loss_of(u, grad=False):
        return ((obs(u, grad) - y_star) ** 2).mean()

    t0 = time.time()
    u, hist, dt = lbfgs_run(loss_of, u_init, max_iter=40, max_eval=100,
                            tag="E3-3D")
    d, k, tau = decode(u)
    err_d = abs(float(d) - D_TRUE_3) / D_TRUE_3
    err_k = abs(float(k) - K_TRUE_3) / K_TRUE_3
    err_t = abs(math.log(float(tau) / TAU_TRUE_3))
    final_loss = hist[-1][1]
    e3 = {"final_loss": final_loss, "evals": len(hist),
          "wall_clock_s": dt,
          "recovered": {"d": float(d), "k": float(k), "tau": float(tau)},
          "truth": {"d": D_TRUE_3, "k": K_TRUE_3, "tau": TAU_TRUE_3},
          "rel_err": {"d": err_d, "k": err_k, "log_tau": err_t},
          "history": hist,
          "pass": bool(err_d < 0.02 and err_k < 0.02
                       and err_t < 0.05 and final_loss < 1e-6)}
    print(f"  E3: {len(hist)} evals, loss {final_loss:.3e}, "
          f"d {float(d):.2f} nm ({100*err_d:.3f}%), k {float(k):.5f} "
          f"({100*err_k:.3f}%), |dlog tau| {err_t:.4f}, PASS {e3['pass']}")
    R["E3"] = e3
    dump("E3")
    R["_E3_hist"] = hist


# ===================================================================== E4
def stage_E4() -> None:
    banner("E4  efficiency benchmark: true f() counts and wall-clock time")
    thresholds = [1e-2, 1e-3, 1e-4, 1e-5, 1e-6]
    e4: dict = {"thresholds": thresholds, "cases": {}}

    for ndim, max_ev_lb, max_ev_nm in ((3, 100, 150), (8, 150, 300)):
        tag = f"{ndim}D"
        print(f"\n  --- {tag} inverse design ---", flush=True)
        cell = make_cell()
        obs, u_star, u_init, decode = build_observables(cell, ndim)
        with torch.no_grad():
            y_star = obs(u_star, grad=False)

        def loss_of(u, grad=False):
            return ((obs(u, grad) - y_star) ** 2).mean()

        def loss_scalar(u):
            with torch.no_grad():
                return float(loss_of(u, grad=False))

        # forward-only and forward+backward wall clock (same machine, same model)
        with torch.no_grad():
            t0 = time.time()
            for _ in range(3):
                _ = loss_of(u_init, grad=False)
            t_fwd = (time.time() - t0) / 3
        t0 = time.time()
        for _ in range(3):
            uu = u_init.clone().requires_grad_(True)
            ll = loss_of(uu, grad=True)
            ll.backward()
        t_fwd_bwd = (time.time() - t0) / 3

        u, hist_lb, dt_lb = lbfgs_run(loss_of, u_init, max_iter=60,
                                      max_eval=max_ev_lb, tag=f"E4-{tag}-LB")
        t0 = time.time()
        f_nm, hist_nm, ne_nm = nelder_mead(loss_scalar, u_init,
                                            step=0.12 if ndim == 3 else 0.10,
                                            max_evals=max_ev_nm)
        dt_nm = time.time() - t0
        print(f"    L-BFGS {len(hist_lb)} f+grad calls in {dt_lb:.0f}s; "
              f"NM {ne_nm} f() calls in {dt_nm:.0f}s "
              f"(best {f_nm:.3e})", flush=True)

        rows = []
        for t in thresholds:
            a, b = first_eval_below(hist_lb, t), first_eval_below(hist_nm, t)
            rows.append({"threshold": t, "lbfgs": a, "nm": b})
            print(f"    loss<{t:g}: L-BFGS {a}, NM {b}", flush=True)

        d, k, tau = decode(u)
        truth_d = D_TRUE_3 if ndim == 3 else D_TRUE_8
        truth_t = TAU_TRUE_3 if ndim == 3 else TAU_TRUE_8
        reach = [r for r in rows if r["lbfgs"] and r["nm"]]
        speedup_ev = min((r["nm"] / r["lbfgs"] for r in reach), default=None)
        # NM never reaching a threshold within its budget => censored lower bound
        censored = [r for r in rows if r["lbfgs"] and not r["nm"]]
        c2 = {"final_loss_lbfgs": hist_lb[-1][1],
              "final_loss_nm": f_nm,
              "n_calls_lbfgs": len(hist_lb), "n_calls_nm": ne_nm,
              "wall_clock_lbfgs_s": dt_lb, "wall_clock_nm_s": dt_nm,
              "t_forward_s": t_fwd, "t_forward_backward_s": t_fwd_bwd,
              "backward_overhead_factor": t_fwd_bwd / t_fwd,
              "rows": rows, "min_observed_speedup": speedup_ev,
              "censored_thresholds": [r["threshold"] for r in censored],
              "recovered": {"d": float(d),
                            "k": [float(x) for x in torch.atleast_1d(k)],
                            "tau": float(tau)},
              "truth": {"d": truth_d,
                        "k": (K_TRUE_3 if ndim == 3 else K_TRUE).tolist()
                        if ndim == 8 else K_TRUE_3,
                        "tau": truth_t},
              "rel_err_d": abs(float(d) - truth_d) / truth_d,
              "pass": bool((speedup_ev is not None and speedup_ev >= 10)
                           or any(r["lbfgs"] and not r["nm"]
                                  and max_ev_nm >= 10 * r["lbfgs"]
                                  for r in rows)),
              "lbfgs_hist": hist_lb, "nm_hist": hist_nm}
        e4["cases"][tag] = c2
        print(f"    {tag} PASS = {c2['pass']}, backward overhead "
              f"{c2['backward_overhead_factor']:.2f}x", flush=True)
        R["E4"] = e4
        dump("E4")

    e4["pass"] = bool(e4["cases"]["8D"]["pass"])
    R["E4"] = e4
    dump("E4-final")


def main() -> None:
    t0 = time.time()
    print("UniDD final validation suite -- corrected optical model", flush=True)
    for fn in (stage_E0, stage_E1, stage_E2, stage_E3, stage_E4):
        fn()
    R["meta"]["total_wall_clock_s"] = time.time() - t0
    dump("COMPLETE")
    print(f"\nAll stages done in {time.time()-t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()
