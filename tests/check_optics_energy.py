"""Absolute (external) validation of the optical model.

Run:  python test_optics_energy.py

These checks detect errors that the original internal-consistency suite
(R+T<=1, EQE-integrated Jsc vs J-V Jsc, qGL) cannot detect, because those
checks share the same generation profile G(z) and therefore cancel out any
common multiplicative error in G.
"""
from __future__ import annotations
import sys
from pathlib import Path
import torch

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))
torch.set_default_dtype(torch.float64)

from soldiff.tmm import field_intensity, generation_rate, absorbed_fraction
from soldiff.device import am15_flux

TwoPi = 2.0 * torch.pi
PASS, FAIL = "PASS", "FAIL"


def check(name: str, ok: bool, detail: str) -> bool:
    print(f"  [{PASS if ok else FAIL}] {name}: {detail}")
    return ok


def stack(nr_layers, k_layers, d, lam):
    """air / (physical layers) / semi-infinite exit medium."""
    L = len(nr_layers) + 2
    W = lam.shape[0]
    nk = torch.empty(L, W, dtype=torch.complex128)
    nk[0] = 1.0
    for j, (nr, k) in enumerate(zip(nr_layers, k_layers)):
        nk[j + 1] = torch.complex(torch.full_like(lam, nr),
                                  k * torch.ones_like(lam))
    nk[L - 1] = 1.0
    return nk, torch.tensor(d, dtype=torch.float64)


def main() -> int:
    results = []
    lam = torch.linspace(400.0, 800.0, 81)
    print("=" * 72)
    print("Optical model: absolute validation and regression tests")
    print("=" * 72)

    # --- (1) Poynting balance on the full perovskite-like stack -------------
    print("\n[1] A_field = integral (n_r/n_0) alpha |E|^2 dz  vs  1 - R - T")
    k = 0.65 * torch.ones_like(lam)
    k_htl = 0.005 * torch.ones_like(lam)
    nk = torch.empty(5, lam.shape[0], dtype=torch.complex128)
    nk[0] = 1.0
    nk[1] = 2.0 + 0.0j
    nk[2] = torch.complex(torch.full_like(lam, 2.55), k)
    nk[3] = 1.5 + 0.005j
    nk[4] = 1.5
    d = torch.tensor([50.0, 420.0, 150.0], dtype=torch.float64)
    devs = []
    for ng in (201, 501, 2001):
        o = absorbed_fraction(nk, d, lam, n_grid=ng)
        devs.append(float((o["A_field"] - o["A_poynting"]).abs().max()))
        print(f"      per-layer grid {ng:5d} pts : max |A_field-(1-R-T)| = {devs[-1]:.3e}")
    out = o
    ok = check("energy balance (finest grid)", devs[-1] < 1e-4,
               f"max |A_field-(1-R-T)| = {devs[-1]:.3e}, "
               f"mean A = {float(out['A_field'].mean()):.4f}")
    results.append(ok)
    ok = check("z-grid convergence", devs[0] > devs[1] > devs[2],
               f"deviation {devs[0]:.2e} -> {devs[1]:.2e} -> {devs[2]:.2e}")
    results.append(ok)

    # The old (buggy) integrand must FAIL this test, proving the test has power
    z = torch.linspace(0.0, float(d.sum()), 4001, dtype=torch.float64)
    raw = field_intensity(nk, d, lam, z_grid=z)
    nk_j = nk[1 + raw["layer_id"]].t()
    alpha_z = 4.0 * torch.pi * nk_j.imag / lam[:, None]
    A_bug = torch.trapz(alpha_z * raw["I2"], z.expand_as(alpha_z), dim=1)
    bug_dev = float((A_bug - out["A_poynting"]).abs().max())
    ok = check("regression test has power", bug_dev > 0.1,
               f"omitting n_r/n_0 gives max deviation {bug_dev:.3f} "
               f"(mean A {float(A_bug.mean()):.4f} vs {float(out['A_poynting'].mean()):.4f})")
    results.append(ok)

    # --- (2) analytic Beer-Lambert limit (impedance matched) ---------------
    print("\n[2] Index-matched absorbing slab -> A = 1 - exp(-alpha d)")
    # A genuinely reflection-free absorbing slab requires the ambient and
    # substrate to share the SAME complex index (an absorbing ambient is a
    # legitimate limiting case, see Byrnes arXiv:1603.02720).  Then r = 0,
    # I2 = exp(-alpha z), T = exp(-alpha d) and A = 1 - exp(-alpha d).
    lam1 = torch.tensor([500.0, 600.0, 700.0])
    kv = torch.tensor([0.10, 0.20, 0.35])
    nk1 = torch.empty(3, 3, dtype=torch.complex128)
    for j in range(3):
        nk1[j] = torch.complex(torch.ones_like(lam1), kv)
    d1 = torch.tensor([300.0], dtype=torch.float64)
    out1 = absorbed_fraction(nk1, d1, lam1, n_grid=4001)
    alpha1 = 4.0 * torch.pi * kv / lam1
    A_ana = 1.0 - torch.exp(-alpha1 * d1[0])
    ok = check("Beer-Lambert limit",
               bool((out1["A_field"] - A_ana).abs().max() < 1e-5),
               f"max deviation = {float((out1['A_field'] - A_ana).abs().max()):.3e}, "
               f"A = {[round(float(x), 4) for x in out1['A_field']]}")
    results.append(ok)
    ok = check("index-matched R ~ 0", bool(out1["R"].abs().max() < 1e-12),
               f"max R = {float(out1['R'].abs().max()):.3e}")
    results.append(ok)

    # --- (3) generation_rate integrates to A * Phi ---------------------------
    print("\n[3] generation_rate is consistent with absorbed_fraction")
    phi = am15_flux(lam)
    g = generation_rate(nk, d, lam, phi, target_layer=1, z_grid=z)
    z_cm = z * 1e-7                       # nm -> cm
    absorber = (g["layer_id"] == 1)
    integral_G = torch.trapz(g["G"][absorber], z_cm[absorber])  # cm^-2 s^-1
    # A from the field integrand restricted to the absorber
    A_abs = torch.trapz((alpha_z * (nk_j.real / nk[0].real[:, None]) * raw["I2"])
                        [:, absorber], z[absorber].expand(lam.shape[0], int(absorber.sum())), dim=1)
    target_integral = torch.trapz(phi * A_abs, lam)
    rel = float((integral_G - target_integral).abs() / target_integral.abs())
    ok = check("G integral = Phi * A_absorber", rel < 2e-3,
               f"relative deviation = {rel:.3e}")
    results.append(ok)

    # --- (4) thick-layer coherent -> incoherent degeneration ----------------
    print("\n[4] coherent interference dies out for optically thick layers")
    lam2 = torch.tensor([600.0])
    ratios = []
    for thick in (200.0, 600.0, 1500.0, 3000.0):
        nk2 = torch.empty(3, 1, dtype=torch.complex128)
        nk2[0] = 1.0
        nk2[1] = torch.complex(torch.tensor([[2.55]]), torch.tensor([[0.30]]))
        nk2[2] = 1.5
        d2 = torch.tensor([thick], dtype=torch.float64)
        zz = torch.linspace(0.0, thick, 20001, dtype=torch.float64)
        coh = field_intensity(nk2, d2, lam2, z_grid=zz)
        inc = field_intensity(nk2, d2, lam2, z_grid=zz,
                              incoherent_mask=torch.tensor([True]))
        I2c, I2i = coh["I2"], inc["I2"]
        rel_i = float((I2c - I2i).abs().mean() / I2i.abs().mean())
        ratios.append(rel_i)
        print(f"      d = {thick:6.0f} nm : mean |I_coh - I_incoh|/I_incoh = {rel_i:.3e}")
    ok = check("interference decays with thickness",
               ratios[-1] < ratios[0] and ratios[-1] < 1e-2,
               f"{ratios[0]:.2e} -> {ratios[-1]:.2e}")
    results.append(ok)

    print("\n" + "=" * 72)
    print(f"RESULT: {sum(results)}/{len(results)} checks passed")
    print("=" * 72)
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
