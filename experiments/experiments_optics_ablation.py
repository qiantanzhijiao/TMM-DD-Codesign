"""
UniDD -- controlled optical ablation: coherent TMM vs Beer-Lambert.

Purpose (from the reviewer-style suggestions in q/2.txt, items 2, 4 and 7)
---------------------------------------------------------------------------
Hold the electrical solver FIXED and replace only the optical generation
model.  Report (i) the Jsc difference, (ii) the shape difference of G(z),
including the positions of the first two interference extrema, (iii) the
difference in the composite thickness gradient dJsc/d(d_abs), and (iv) the
forward cost of each optical model as an order-of-magnitude reference against
Beer-Lambert based differentiable simulators (dPV / DriftJax).

The Beer-Lambert arm deliberately KEEPS the Poynting factor n_r/n_0 and the
same spectral flux and alpha(lambda), so the only thing removed is coherent
interference and back-reflection.  This isolates the optical modelling choice;
it is not a reproduction of dPV or DriftJax, whose electrical discretisations
and contact models differ.

Run:  python experiments_optics_ablation.py
Out:  results_optics_ablation.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import torch

torch.set_default_dtype(torch.float64)
torch.manual_seed(0)

import experiments_final as ef
from soldiff.tmm import field_intensity

CELL = ef.make_cell()
D_TRUE, TAU = 480.0, 3.0e-7
V0 = [0.0]
LAMS = CELL.lam


def nk_of(lams):
    """Same reference spectrum as the E3/E4 inverse problems."""
    return ef.nk_simple(torch.tensor(0.72, dtype=torch.float64), lams=lams)


def beer_lambert_optics(d_abs, nk_abs):
    """Drop-in replacement for CoupledSolarCell.optics: single-pass absorption.

    Returns (G [cm^-3 s^-1], x_rel, None) with the same signature as the
    coherent implementation so jv() needs no change.
    """
    W, N = CELL.lam.shape[0], CELL.dd.N
    d = torch.stack([torch.as_tensor(CELL.d_etl, dtype=torch.float64),
                     d_abs.reshape(()).to(torch.float64),
                     torch.as_tensor(CELL.d_htl, dtype=torch.float64)])
    nk = torch.empty(5, W, dtype=torch.complex128)
    nk[0], nk[1] = 1.0, CELL.nk_etl
    nk[2] = nk_abs.to(torch.complex128)
    nk[3], nk[4] = CELL.nk_htl, 1.5
    nkj = nk[2]
    out = field_intensity(nk, d, CELL.lam)
    a_l = out["a"][2]                                        # forward amplitude
    alpha = 4.0 * torch.pi * nkj.imag / CELL.lam            # (W,) [nm^-1]
    x_rel = torch.linspace(0.0, 1.0, N, dtype=torch.float64)
    zloc = (x_rel * d[1])[:, None]
    # Single-pass Beer-Lambert limit WITHIN this framework: keep the same
    # incident/transmitted amplitude and alpha(lambda), drop the backward wave
    # and the interference cross term only.  Using |E|^2 = exp(-alpha z) with
    # unit amplitude instead would over-count absorption by ~2.6x because it
    # ignores the Fresnel transmission into the absorbing layer.
    I2 = (a_l * a_l.conj()).real[None, :] * torch.exp(-(alpha[None, :] * zloc))
    nr_over_n0 = nkj.real / nk[0].real
    G_spec = (alpha * CELL.phi * nr_over_n0)[None, :] * I2
    G = torch.trapz(G_spec, CELL.lam[None, :].expand_as(G_spec), dim=1) * 1e7
    return G, x_rel, None


def jsc_and_grad(use_bl: bool):
    orig = CELL.optics
    if use_bl:
        CELL.optics = beer_lambert_optics
    try:
        d = torch.tensor(D_TRUE, dtype=torch.float64, requires_grad=True)
        J = CELL.jv(d, nk_of(LAMS), torch.tensor(TAU), V0, ift=True, dV=0.05)[0]
        J.backward()
        grad = float(d.grad)
        # timing: three warm forward evaluations of the same quantity
        ts = []
        for _ in range(3):
            d2 = torch.tensor(D_TRUE, dtype=torch.float64)
            t = time.time()
            with torch.no_grad():
                CELL.jv(d2, nk_of(LAMS), torch.tensor(TAU), V0,
                        ift=False, dV=0.05)
            ts.append(time.time() - t)
        G, x_rel, _ = CELL.optics(d.detach(), nk_of(LAMS))
        return {
            "Jsc_mA_cm2": float(J.detach()),
            "dJsc_d_dabs": grad,
            "t_forward_s": sum(ts) / len(ts),
            "G_profile_cm3_s": [float(v) for v in G.detach()],
            "x_rel": [float(v) for v in x_rel],
        }
    finally:
        CELL.optics = orig


def extrema(profile, x_rel):
    """Interior local extrema of G(z), reported as fractional depth and nm."""
    out = []
    for i in range(1, len(profile) - 1):
        a, b, c = profile[i - 1], profile[i], profile[i + 1]
        if (b > a and b >= c) or (b < a and b <= c):
            out.append({"kind": "max" if b > a else "min",
                        "x_rel": x_rel[i],
                        "z_nm": x_rel[i] * D_TRUE,
                        "G_cm3_s": profile[i]})
    return out


def regime_scan():
    """Where does coherent optics actually matter?  Sweep absorption and thickness.

    The reference stack (k_amp=0.72, 480 nm) is strongly absorbing, so
    interference is damped and the two optical models nearly coincide.  A
    defensible differentiation claim must therefore be made in a weak-
    absorption / thin-layer regime, which this sweep locates.
    """
    rows = []

    def one(k_amp, d, use_bl):
        orig = CELL.optics
        if use_bl:
            CELL.optics = beer_lambert_optics
        try:
            dd = torch.tensor(d, dtype=torch.float64, requires_grad=True)
            nk = ef.nk_simple(torch.tensor(k_amp, dtype=torch.float64), lams=LAMS)
            J = CELL.jv(dd, nk, torch.tensor(TAU), V0, ift=True, dV=0.05)[0]
            J.backward()
            return float(J.detach()), float(dd.grad)
        finally:
            CELL.optics = orig

    for k_amp in (0.72, 0.30, 0.10, 0.05, 0.02):
        for d in (120.0, 240.0, 480.0):
            jc, gc = one(k_amp, d, False)
            jb, gb = one(k_amp, d, True)
            rows.append({
                "k_amp": k_amp, "d_nm": d,
                "Jsc_coherent": jc, "Jsc_single_pass": jb,
                "Jsc_rel_diff_pct": 100.0 * (jc - jb) / jc,
                "grad_coherent": gc, "grad_single_pass": gb,
                "grad_rel_diff_pct": 100.0 * (gc - gb) / abs(gc),
            })
    return rows


def main():
    print("Optical ablation: coherent TMM vs Beer--Lambert (electrical solver fixed)",
          flush=True)
    coh = jsc_and_grad(False)
    print(f"  coherent  Jsc={coh['Jsc_mA_cm2']:.4f}  "
          f"dJ/dd={coh['dJsc_d_dabs']:.4e}  t={coh['t_forward_s']:.2f}s",
          flush=True)
    bl = jsc_and_grad(True)
    print(f"  Beer-Lambert Jsc={bl['Jsc_mA_cm2']:.4f}  "
          f"dJ/dd={bl['dJsc_d_dabs']:.4e}  t={bl['t_forward_s']:.2f}s",
          flush=True)

    e_coh, e_bl = extrema(coh["G_profile_cm3_s"], coh["x_rel"]), \
                  extrema(bl["G_profile_cm3_s"], bl["x_rel"])
    print("  locating the interference-significant regime ...", flush=True)
    scan = regime_scan()
    best = max(scan, key=lambda r: abs(r["grad_rel_diff_pct"]))
    print(f"  largest gradient contrast: k_amp={best['k_amp']}, "
          f"d={best['d_nm']} nm -> {best['grad_rel_diff_pct']:.1f}%", flush=True)
    res = {
        "protocol": {
            "held_fixed": ["electrical solver", "DD mesh N=73", "alpha(lambda)",
                           "AM1.5G flux", "Poynting factor n_r/n_0", "contacts",
                           "d_abs=480 nm", "tau=3e-7 s", "bias continuation dV=0.05"],
            "changed": "optical generation: coherent TMM field vs single-pass exp(-alpha z)",
            "note": "NOT a reproduction of dPV/DriftJax; only an in-framework cost reference",
        },
        "coherent_tmm": {k: v for k, v in coh.items() if k != "G_profile_cm3_s"},
        "beer_lambert": {k: v for k, v in bl.items() if k != "G_profile_cm3_s"},
        "comparison": {
            "Jsc_relative_difference_pct":
                100.0 * (coh["Jsc_mA_cm2"] - bl["Jsc_mA_cm2"]) / coh["Jsc_mA_cm2"],
            "thickness_gradient_relative_difference_pct":
                100.0 * (coh["dJsc_d_dabs"] - bl["dJsc_d_dabs"])
                / abs(coh["dJsc_d_dabs"]),
            "forward_cost_ratio_coherent_over_BL":
                coh["t_forward_s"] / bl["t_forward_s"],
            "first_two_coherent_extrema": e_coh[:2],
            "n_coherent_extrema": len(e_coh),
            "n_BL_extrema": len(e_bl),
            "G_profile_shape": ("coherent profile has %d interior extrema; "
                                "single-pass profile has %d (monotone)"
                                % (len(e_coh), len(e_bl))),
        },
        "G_profiles": {"x_rel": coh["x_rel"],
                       "coherent_cm3_s": coh["G_profile_cm3_s"],
                       "beer_lambert_cm3_s": bl["G_profile_cm3_s"]},
        "regime_scan": scan,
        "interpretation": (
            "At the reference operating point the two optical models give nearly "
            "the same Jsc and thickness gradient, because strong absorption damps "
            "the standing wave. The differentiation claim is therefore supported "
            "only in weak-absorption / thin-layer regimes, identified by "
            "regime_scan; it must NOT be stated as a general necessity of coherent "
            "optics for gradient correctness. The in-framework single-pass arm "
            "keeps the same Fresnel amplitude, alpha(lambda), flux and Poynting "
            "factor, so the comparison isolates interference alone."),
    }
    (ROOT / "results_optics_ablation.json").write_text(
        json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res["comparison"], indent=1), flush=True)


if __name__ == "__main__":
    main()
