"""
Generate UniDD reference data for a manual SCAPS-1D cross-check.

The SCAPS step itself cannot be automated here (GUI-only, not installed).
This script produces everything that CAN be prepared in advance:

  scaps_reference/unidd_dark_JV.csv             dark J-V, 61 bias points
  scaps_reference/unidd_light_JV_coherent.csv   illuminated J-V, coherent TMM
  scaps_reference/unidd_light_JV_singlepass.csv illuminated J-V, single-pass optics
  scaps_reference/unidd_EQE.csv                 EQE, 380-790 nm
  scaps_reference/unidd_generation_profile.csv  G(z) for both optical models
  scaps_reference/unidd_parameters.csv          parameter table with unit conversions
  scaps_reference/TEMPLATE_*.csv                empty templates for SCAPS export

Run:  python export_scaps_reference.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "scaps_reference"
OUT.mkdir(exist_ok=True)

import torch

torch.set_default_dtype(torch.float64)
torch.manual_seed(0)

import experiments_final as ef
from soldiff.device import am15_flux
from soldiff.tmm import field_intensity

CELL = ef.make_cell()
D, TAU = torch.tensor(480.0, dtype=torch.float64), torch.tensor(3.0e-7)
K_AMP = torch.tensor(0.72, dtype=torch.float64)
V_GRID = [round(0.02 * i, 2) for i in range(61)]          # 0 .. 1.20 V
LAM_EQE = torch.linspace(380.0, 790.0, 21)


def nk_of(lams):
    return ef.nk_simple(K_AMP, lams=lams)


def optics_zero(d_abs, nk_abs):
    N = CELL.dd.N
    return (torch.zeros(N, dtype=torch.float64),
            torch.linspace(0.0, 1.0, N, dtype=torch.float64), None)


def optics_single_pass(d_abs, nk_abs):
    """Coherent amplitudes retained, backward wave and cross term removed."""
    W, N = CELL.lam.shape[0], CELL.dd.N
    d = torch.stack([torch.as_tensor(CELL.d_etl, dtype=torch.float64),
                     d_abs.reshape(()).to(torch.float64),
                     torch.as_tensor(CELL.d_htl, dtype=torch.float64)])
    nk = torch.empty(5, W, dtype=torch.complex128)
    nk[0], nk[1] = 1.0, CELL.nk_etl
    nk[2] = nk_of(CELL.lam).to(torch.complex128)
    nk[3], nk[4] = CELL.nk_htl, 1.5
    out = field_intensity(nk, d, CELL.lam)
    a_l = out["a"][2]
    nkj = nk[2]
    alpha = 4.0 * torch.pi * nkj.imag / CELL.lam
    x_rel = torch.linspace(0.0, 1.0, N, dtype=torch.float64)
    zloc = (x_rel * d[1])[:, None]
    I2 = (a_l * a_l.conj()).real[None, :] * torch.exp(-(alpha[None, :] * zloc))
    nr = nkj.real / nk[0].real
    G_spec = (alpha * CELL.phi * nr)[None, :] * I2
    G = torch.trapz(G_spec, CELL.lam[None, :].expand_as(G_spec), dim=1) * 1e7
    return G, x_rel, None


def jv_with(optics_fn, tag: str):
    """optics_fn=None keeps the class's coherent TMM optics."""
    if optics_fn is None:
        with torch.no_grad():
            J = CELL.jv(D, nk_of(CELL.lam), TAU, V_GRID, ift=False, dV=0.02)
        rows = [{"V_V": f"{v:.4f}", "J_mA_cm2": f"{float(j):.8f}"}
                for v, j in zip(V_GRID, J)]
        write_csv(OUT / f"unidd_{tag}.csv", ["V_V", "J_mA_cm2"], rows)
        print(f"  {tag}: Jsc={float(J[0]):.4f} mA/cm2, {len(rows)} points")
        return
    CELL.optics = optics_fn
    try:
        with torch.no_grad():
            J = CELL.jv(D, nk_of(CELL.lam), TAU, V_GRID, ift=False, dV=0.02)
        rows = [{"V_V": f"{v:.4f}", "J_mA_cm2": f"{float(j):.8f}"}
                for v, j in zip(V_GRID, J)]
        write_csv(OUT / f"unidd_{tag}.csv", ["V_V", "J_mA_cm2"], rows)
        print(f"  {tag}: Jsc={float(J[0]):.4f} mA/cm2, {len(rows)} points")
    finally:
        # delete the instance attribute so the class method is visible again
        if "optics" in CELL.__dict__:
            del CELL.optics


def write_csv(path: Path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def main():
    print("Exporting UniDD reference data for SCAPS-1D cross-check", flush=True)
    jv_with(None, "light_JV_coherent")
    jv_with(optics_zero, "dark_JV")
    jv_with(optics_single_pass, "light_JV_singlepass")

    # EQE (coherent only; SCAPS has no coherent optics, see the plan document)
    with torch.no_grad():
        lam_eqe = LAM_EQE
        eqe = CELL.eqe_curve(D, nk_of(lam_eqe), TAU,
                             lam_eqe=lam_eqe, phi_eqe=am15_flux(lam_eqe),
                             ift=False)
    write_csv(OUT / "unidd_EQE.csv", ["lambda_nm", "EQE"],
              [{"lambda_nm": f"{float(l):.2f}", "EQE": f"{float(e):.8f}"}
               for l, e in zip(lam_eqe, eqe)])
    print(f"  EQE: {len(eqe)} wavelengths, mean {float(eqe.mean()):.4f}")

    # generation profile on the absorber, both optical models
    G_coh, x_rel, _ = CELL.optics(D, nk_of(CELL.lam))
    G_bl, _, _ = optics_single_pass(D, nk_of(CELL.lam))
    write_csv(OUT / "unidd_generation_profile.csv",
              ["z_um", "G_coherent_cm3_s", "G_singlepass_cm3_s"],
              [{"z_um": f"{float(x)*0.48:.6f}",
                "G_coherent_cm3_s": f"{float(gc):.6e}",
                "G_singlepass_cm3_s": f"{float(gb):.6e}"}
               for x, gc, gb in zip(x_rel, G_coh, G_bl)])
    print("  generation profile: 73 nodes, z in um, G in cm^-3 s^-1")

    params = [
        ("layer_ETL_thickness_nm", "50", "0.05 um", "TiO2, n=2.0"),
        ("layer_absorber_thickness_nm", "480", "0.48 um", "2.55 + i k(lambda)"),
        ("layer_HTL_thickness_nm", "150", "0.15 um", "1.5 + 0.005i"),
        ("Eg_eV", "1.55", "1.55 eV", "T=300 K"),
        ("epsilon_r", "6.5", "6.5", "absorber"),
        ("Nc_m-3", "2.2e24", "2.2e18 cm-3", "divide by 1e6"),
        ("Nv_m-3", "1.8e25", "1.8e19 cm-3", "divide by 1e6"),
        ("mu_m2_Vs", "2e-4", "2 cm2/Vs", "multiply by 1e4"),
        ("tau_n_p_s", "3e-7", "3e-7 s", "single bulk SRH, no interface recombination"),
        ("T_K", "300", "300 K", ""),
        ("contact", "ideal selective ohmic", "flat-band, S_n=S_p=0", "no Rs/Rsh"),
        ("recombination", "bulk SRH only", "disable radiative/Auger/interface", ""),
        ("spectrum", "ASTM G173 coarse, 350-800 nm, 41 pts",
         "100 mW/cm2", "import the same table for layer-B comparison"),
        ("DD_mesh", "N=73 uniform, float64", "dx=0.48um/72", ""),
        ("J_conversion", "1 A/m2 = 0.1 mA/cm2", "divide by 10",
         "UniDD photocurrent positive; check SCAPS sign"),
        ("G_conversion", "cm-3 s-1 -> m-3 s-1", "multiply by 1e6",
         "SCAPS generation profile uses cm-3 s-1"),
        ("alpha_conversion", "nm-1 -> cm-1", "multiply by 1e7", ""),
    ]
    write_csv(OUT / "unidd_parameters.csv", ["parameter", "UniDD_value",
                                             "SCAPS_value", "note"],
              [dict(zip(["parameter", "UniDD_value", "SCAPS_value", "note"], p))
               for p in params])

    for name, header in (
        ("dark_JV", ["V_V", "J_mA_cm2"]),
        ("light_JV", ["V_V", "J_mA_cm2"]),
        ("EQE", ["lambda_nm", "EQE"]),
        ("generation_profile", ["z_um", "G_cm3_s"]),
    ):
        write_csv(OUT / f"TEMPLATE_{name}.csv", header, [])
    (OUT / "README.md").write_text(
        "# UniDD reference data for SCAPS-1D cross-check\n\n"
        "Fill TEMPLATE_*.csv from SCAPS exports (rename to dark_JV.csv, "
        "light_JV.csv, EQE.csv, generation_profile.csv) and put them in one "
        "directory, then run:\n\n"
        "    python compare_scaps.py --scaps-dir <dir>\n\n"
        "See ../SCAPS1D交叉验证方案.md for the GUI procedure, parameter "
        "alignment table and acceptance criteria. Record the SCAPS version "
        "and every setting in metadata.txt.\n", encoding="utf-8")
    print(f"  -> {OUT}")


if __name__ == "__main__":
    main()
