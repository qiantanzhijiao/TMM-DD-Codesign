"""
Generate all manuscript figures directly from results_final.json and
results_supplement.json.  No number is typed in by hand.

Run:  python make_figures.py
Out:  figures/fig1_framework.pdf|png ... fig5_optimization.pdf|png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)
D = json.load(open(ROOT / "results_final.json"))
S = json.load(open(ROOT / "results_supplement.json"))

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.labelsize": 9.5,
    "axes.titlesize": 10,
    "legend.fontsize": 8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "mathtext.fontset": "dejavusans",
    "axes.linewidth": 0.8,
    "figure.dpi": 200,
})
BLUE = "#1f5c99"
RED = "#b5372f"
GREY = "#6b6b6b"
GREEN = "#2a7a4b"


def save(fig, name: str) -> None:
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"{name}.{ext}", bbox_inches="tight",
                    dpi=300 if ext == "png" else None)
    plt.close(fig)
    print("  wrote", name)


# ---------------------------------------------------------------- Fig. 1
def framework() -> None:
    fig, ax = plt.subplots(figsize=(7.4, 3.3))
    ax.set_xlim(-0.15, 12.45)
    ax.set_ylim(0.3, 5.5)
    ax.axis("off")

    Y, H = 3.55, 1.05
    boxes = [
        (0.15, Y, 2.05, H, "Design parameters\n$\\theta=(d,\\,n+ik,\\,\\tau)$", "#eaf1f8"),
        (2.60, Y, 2.20, H, "Differentiable TMM\n$|E(z,\\lambda)|^2,\\;R,\\;T$", "#e8f2ec"),
        (5.20, Y, 2.25, H,
         "Generation $G(z)$\n$\\int\\frac{n_r}{n_0}\\alpha\\Phi|E|^2 d\\lambda$\non DD nodes (analytic)", "#eaf1f8"),
        (7.85, Y, 2.00, H, "Differentiable DD\nNewton + IFT adjoint", "#e8f2ec"),
        (10.25, Y, 1.55, H, "Observables\n$J$--$V$, EQE, $R$, $T$", "#f4f0e6"),
        (3.50, 1.95, 2.20, 0.85, "AM1.5G $\\Phi(\\lambda)$", "#f4f0e6"),
        (9.05, 1.95, 2.75, 0.85,
         "Loss $\\mathcal{L}=\\|y(\\theta)-y^{*}\\|^2$", "#f4f0e6"),
    ]
    for i, (x, y, w, h, txt, fc) in enumerate(boxes):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.08",
            linewidth=1.0, edgecolor="#394a5a", facecolor=fc))
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center",
                fontsize=6.3 if i == 2 else 7.0)

    def arrow(x1, y1, x2, y2, colour="#394a5a"):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                     mutation_scale=11, linewidth=1.1,
                                     color=colour, shrinkA=0, shrinkB=0))

    cy = Y + H / 2
    for x1, x2 in ((2.20, 2.60), (4.80, 5.20), (7.45, 7.85), (9.85, 10.25)):
        arrow(x1, cy, x2, cy)
    arrow(4.60, 2.80, 5.75, Y)          # photon flux -> generation
    arrow(11.00, Y, 10.40, 2.80)        # observables -> loss
    # outer reverse-mode loop, kept clear of every box
    loop_x = [11.80, 12.25, 12.25, 0.60]
    loop_y = [cy, cy, 0.95, 0.95]
    ax.plot(loop_x, loop_y, color=RED, lw=1.15)
    arrow(0.60, 0.95, 0.60, Y, colour=RED)
    ax.text(6.2, 1.18,
            "$\\nabla_\\theta\\mathcal{L}$  (reverse mode; one $J^{-T}$ solve per converged state)",
            ha="center", va="center", color=RED, fontsize=8.2)
    ax.text(6.0, 5.10, "Forward model", ha="center", fontsize=9.5,
            fontweight="bold", color="#394a5a")
    save(fig, "fig1_framework")


# ---------------------------------------------------------------- Fig. 2
def optical_validation() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    ax = axes[0]
    e0 = D["E0"]
    ns = np.array(sorted(int(k) for k in e0["energy_balance_max_dev"]))
    dev = np.array([e0["energy_balance_max_dev"][str(n)] for n in ns])
    ax.loglog(ns, dev, "o-", color=BLUE, lw=1.4, ms=5, label="measured")
    ref = dev[0] * (ns[0] / ns) ** 2
    ax.loglog(ns, ref, "--", color=GREY, lw=1.1, label="$O(n_z^{-2})$ guide")
    ax.set_xlabel("grid points per layer, $n_z$")
    ax.set_ylabel(r"$\max_\lambda|A_{\rm field}-(1-R-T)|$")
    ax.set_title("(a) Poynting-consistent energy balance")
    ax.grid(alpha=0.25, which="both")
    ax.legend(frameon=False)

    ax = axes[1]
    ci = e0["coherent_to_incoherent"]
    th = np.array(sorted(float(k) for k in ci))
    delta = np.array([ci[f"{t:.1f}"] for t in th])
    ax.semilogy(th, np.maximum(delta, 1e-12), "s-", color=GREEN, lw=1.4, ms=5)
    ax.set_xlabel("absorber thickness (nm)")
    ax.set_ylabel(r"$|A_{\rm coh}-A_{\rm incoh}|$")
    ax.set_title("(b) coherent $\\rightarrow$ incoherent limit")
    ax.grid(alpha=0.25, which="both")
    ax.annotate("thick-layer degeneration", xy=(1500, max(delta[2], 1e-11)),
                xytext=(300, 3e-3), fontsize=7.6, color=GREY,
                arrowprops=dict(arrowstyle="->", color=GREY, lw=0.8))
    fig.tight_layout()
    save(fig, "fig2_optical_validation")


# ---------------------------------------------------------------- Fig. 3
def device_and_mesh() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    ax = axes[0]
    jv = D["E2"]["jv_curve"]
    V = np.array(jv["V"])
    J = np.array(jv["J"])
    m = D["E2"]["metrics"]
    ax.plot(V, J, "-", color=BLUE, lw=1.7)
    ax.axhline(0, color=GREY, lw=0.7)
    ax.axvline(0, color=GREY, lw=0.7)
    ax.plot([m["Vmpp"]], [m["Jmpp"]], "o", color=RED, ms=5, zorder=3)
    ax.annotate(f"MPP ({m['Vmpp']:.2f} V, {m['Jmpp']:.2f} mA/cm$^2$)",
                xy=(m["Vmpp"], m["Jmpp"]), xytext=(0.34, 16.0),
                fontsize=7.8, color=RED,
                arrowprops=dict(arrowstyle="->", color=RED, lw=0.9))
    ax.set_xlim(0, 1.2)
    ax.set_ylim(-2, 32)
    ax.set_xlabel("applied bias $V$ (V)")
    ax.set_ylabel("photocurrent $J$ (mA cm$^{-2}$)")
    ax.set_title("(a) illuminated $J$--$V$, $N=73$")
    ax.grid(alpha=0.25)

    ax = axes[1]
    rows = S["mesh"]
    N = np.array([r["N_dd"] for r in rows])
    Jsc = np.array([r["Jsc"] for r in rows])
    ax.plot(1 / N, Jsc, "o-", color=BLUE, lw=1.4, ms=5, label="computed")
    lim = S["Jsc_richardson_extrapolated"]
    ax.axhline(lim, ls="--", color=RED, lw=1.2,
               label=f"extrapolated {lim:.3f} mA/cm$^2$")
    ax.axvline(1 / 73, ls=":", color=GREY, lw=1.0)
    ax.text(1 / 73 + 0.0002, 29.45, "production grid", color=GREY, fontsize=7.4)
    ax.set_xlabel("inverse node count, $1/N$")
    ax.set_ylabel("$J_{\\rm sc}$ (mA cm$^{-2}$)")
    ax.set_title("(b) mesh convergence")
    ax.grid(alpha=0.25)
    ax.legend(frameon=True, facecolor="white", framealpha=0.92,
              edgecolor="#cccccc", loc="lower right")
    fig.tight_layout()
    save(fig, "fig3_device_and_mesh")


# ---------------------------------------------------------------- Fig. 4
def gradients() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    ax = axes[0]
    pc = D["E1"]["per_coordinate"]
    labels = [p["param"] for p in pc]
    ratios = [p["ad"] / p["fd_richardson4"] for p in pc]
    errs = [abs(p["ad"] - p["fd_richardson4"]) / abs(p["fd_richardson4"]) for p in pc]
    ax.bar(labels, ratios, color=BLUE, width=0.52)
    ax.axhline(1.0, ls="--", color=RED, lw=1.1)
    ax.set_ylim(0.994, 1.006)
    ax.set_ylabel("AD / FD (Richardson $R_4$)")
    ax.set_title("(a) per-parameter gradient ratio")
    for i, e in enumerate(errs):
        ax.text(i, 1.0052, f"{e*100:.3f}%", ha="center", fontsize=7.6)
    ax.grid(alpha=0.25, axis="y")

    ax = axes[1]
    sw = D["E1"]["tolerance_sweep"]
    floors = np.array([x["abs_floor"] for x in sw])
    err = np.array([x["rel_err"] for x in sw])
    ax.semilogx(floors, err * 100, "o-", color=BLUE, lw=1.4, ms=5,
                label="full-chain directional derivative")
    iso = D["E1"]["best_isolated_path_rel_err"] * 100
    ax.axhline(iso, ls="--", color=GREEN, lw=1.1,
               label="isolated DD path (best)")
    ax.set_xlabel("Newton absolute residual floor (A m$^{-3}$)")
    ax.set_ylabel("relative deviation (%)")
    ax.set_title("(b) tolerance independence")
    ax.grid(alpha=0.25, which="both")
    ax.legend(frameon=False)
    fig.tight_layout()
    save(fig, "fig4_gradients")


# ---------------------------------------------------------------- Fig. 5
def optimization() -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    for ax, tag in zip(axes, ("3D", "8D")):
        c = D["E4"]["cases"][tag]
        lb = np.array(c["lbfgs_hist"], dtype=float)
        nm = np.array(c["nm_hist"], dtype=float)
        ax.semilogy(lb[:, 0], np.maximum(lb[:, 1], 1e-16), "-", color=BLUE,
                    lw=1.5, label=f"L-BFGS + IFT ({len(lb)} calls)")
        ax.semilogy(nm[:, 0], np.maximum(nm[:, 1], 1e-16), "-", color=RED,
                    lw=1.2, alpha=0.85, label=f"Nelder--Mead ({len(nm)} calls)")
        ax.axhline(1e-3, ls=":", color=GREY, lw=0.9)
        ax.axhline(1e-4, ls=":", color=GREY, lw=0.9)
        ax.text(ax.get_xlim()[1], 1.3e-3, "$10^{-3}$", fontsize=7, color=GREY,
                ha="right")
        ax.text(ax.get_xlim()[1], 1.3e-4, "$10^{-4}$", fontsize=7, color=GREY,
                ha="right")
        ax.set_xlabel("true objective evaluations")
        ax.set_ylabel("mean squared loss")
        ax.set_title(f"({'a' if tag == '3D' else 'b'}) {tag} inverse design")
        ax.grid(alpha=0.25, which="both")
        ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    save(fig, "fig5_optimization")


if __name__ == "__main__":
    print("Generating figures from recorded results ...")
    framework()
    optical_validation()
    device_and_mesh()
    gradients()
    optimization()
    print("Done ->", FIG)
