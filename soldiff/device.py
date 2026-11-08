"""
Coupled differentiable optical-electrical solar-cell model.

Stack: air / TiO2 (ETL) / MAPbI3 (absorber) / spiro-OMeTAD (HTL) / glass-equivalent.
Optics: differentiable TMM  ->  G(z,λ) in the absorber.
Electrics: differentiable drift-diffusion (Gummel/SG) driven by G(z).

Design parameters (all torch-differentiable):
    d_abs   absorber thickness [nm]
    nk_abs  (W,) complex refractive index of the absorber (k scales absorption)
    tau     SRH lifetime (single level, τn = τp) [s]  (defect-density proxy: τ ∝ 1/N_t)
Outputs: J-V curve, EQE(λ), and the figure-of-merit tuple (Jsc, Voc, FF, PCE).
"""
from __future__ import annotations
import torch
from torch import Tensor

from .tmm import field_intensity, generation_rate
from .dd import DDDevice, Q


def _interp(xq: Tensor, x: Tensor, y: Tensor) -> Tensor:
    """1-D linear interpolation (differentiable in y)."""
    idx = torch.clamp(torch.searchsorted(x, xq), 1, len(x) - 1)
    x0, x1 = x[idx - 1], x[idx]
    y0, y1 = y[idx - 1], y[idx]
    w = ((xq - x0) / (x1 - x0 + 1e-300)).clamp(0.0, 1.0)
    return y0 + w * (y1 - y0)

# --- coarse AM1.5G table (ASTM G-173, ~50 nm sampling, W m^-2 nm^-1) ----------
AM15_LAM = torch.tensor([300., 350., 400., 450., 500., 550., 600., 650., 700.,
                         750., 800., 850., 900., 950., 1000.])
AM15_IRR = torch.tensor([0.22, 0.52, 1.12, 1.62, 1.82, 1.86, 1.86, 1.80, 1.70,
                         1.54, 1.42, 1.26, 1.06, 0.86, 0.66])
HC_Q = 0.00198644586    # h*c/q [J·m]  ->  Φ = E·λ/(hc) ; with E in W/m²/nm and λ in nm:
# Φ [photons cm⁻² s⁻¹ nm⁻¹] = E * λ_nm * 1e-9 / (h c) * 1e-4  (m²→cm²)
_PLANCK = 6.62607015e-34
_C_LIGHT = 2.99792458e8


def am15_flux(lam_nm: Tensor) -> Tensor:
    """Photon flux [photons cm⁻² s⁻¹ nm⁻¹] at wavelengths lam_nm [nm]."""
    idx = torch.searchsorted(AM15_LAM, lam_nm).clamp(1, len(AM15_LAM) - 1)
    l0, l1 = AM15_LAM[idx - 1], AM15_LAM[idx]
    E0, E1 = AM15_IRR[idx - 1], AM15_IRR[idx]
    w = ((lam_nm - l0) / (l1 - l0)).clamp(0.0, 1.0)
    E = E0 + w * (E1 - E0)                                  # W m⁻² nm⁻¹
    photon_J = _PLANCK * _C_LIGHT / (lam_nm * 1e-9)          # J per photon
    return E / photon_J * 1e-4                               # photons cm⁻² s⁻¹ nm⁻¹


class CoupledSolarCell:
    """End-to-end differentiable TMM + drift-diffusion model of a p-i-n cell."""

    def __init__(self, W_opt: int = 41, lam_min: float = 350.0, lam_max: float = 800.0,
                 N_dd: int = 97, d_etl: float = 50.0, d_htl: float = 150.0,
                 lam_eqe: int = 13):
        self.lam = torch.linspace(lam_min, lam_max, W_opt, dtype=torch.float64)
        self.phi = am15_flux(self.lam)
        # static layers (complex n, flat)
        self.nk_etl = 2.0 + 0.0j
        self.nk_htl = 1.5 + 0.005j
        self.d_etl, self.d_htl = d_etl, d_htl
        self.dd = DDDevice(N=N_dd)
        self.lam_eqe = torch.linspace(380.0, 780.0, lam_eqe, dtype=torch.float64)
        self.phi_eqe = am15_flux(self.lam_eqe)

    # ------------------------------------------------------------------ optics
    def optics(self, d_abs: Tensor, nk_abs: Tensor):
        """
        TMM generation directly on the DD nodes (analytic |E(z,λ)|² evaluation —
        no optical-grid resampling, hence kink-free gradients).
        Returns G (N,) [cm⁻³ s⁻¹] on the uniform DD mesh.
        """
        W = self.lam.shape[0]
        N = self.dd.N
        d = torch.stack([torch.as_tensor(self.d_etl, dtype=torch.float64),
                         d_abs.reshape(()).to(torch.float64),
                         torch.as_tensor(self.d_htl, dtype=torch.float64)])
        nk = torch.empty(5, W, dtype=torch.complex128)
        nk[0] = 1.0
        nk[1] = self.nk_etl
        nk[2] = nk_abs.to(torch.complex128)
        nk[3] = self.nk_htl
        nk[4] = 1.5
        out = field_intensity(nk, d, self.lam)
        a_l, b_l = out["a"][2], out["b"][2]              # absorber amplitudes (W,)
        nkj = nk[2]
        lamw = self.lam[None, :]
        # local coordinate inside the absorber at each DD node (relative grid)
        x_rel = torch.linspace(0.0, 1.0, N, dtype=torch.float64)
        zloc = (x_rel * d[1])[:, None]                    # (N,1) [nm]
        alpha_z = (4.0 * torch.pi * nkj.imag / lamw) * zloc
        # cross term: no extra exp(-alpha z); see tmm.field_intensity
        cross = (a_l * b_l.conj() *
                 torch.exp(4j * torch.pi * nkj.real / lamw * zloc)).real
        I2 = ((a_l * a_l.conj()).real * torch.exp(-alpha_z)
              + (b_l * b_l.conj()).real * torch.exp(alpha_z)
              + 2.0 * cross).clamp(min=0.0)               # (N,W)
        alpha = 4.0 * torch.pi * nkj.imag / self.lam       # (W,) [nm⁻¹]
        # Poynting factor n_r/n_0 (see tmm.absorbed_fraction).  Without it
        # generation, Jsc, EQE and PCE are all low by a factor ~n_r/n_0.
        n0 = nk[0].real                                    # (W,)
        G_spec = (alpha * self.phi * (nkj.real / n0))[None, :] * I2   # (N,W)
        G = torch.trapz(G_spec, self.lam[None, :].expand_as(G_spec), dim=1) * 1e7
        return G, x_rel, out

    def _interp_to_mesh(self, G_opt: Tensor, z_rel: Tensor) -> tuple[Tensor, Tensor]:
        """G already on the DD mesh; unit conversion only (cm⁻³ → m⁻³ s⁻¹)."""
        return G_opt * 1e6, None

    def mesh_diff(self, d_abs: Tensor) -> dict:
        """Differentiable mesh for a tensor absorber thickness [nm]:
        dx carries the grad so the IFT backward covers the electrical-size
        dependence of J (in addition to the optical path)."""
        dd = self.dd
        L = d_abs.reshape(()).to(torch.float64) * 1e-9
        dx = L / (dd.N - 1)
        psi0 = dd.VT * torch.log(torch.tensor(dd.n_contactL / dd.ni, dtype=torch.float64))
        psiL = -dd.VT * torch.log(torch.tensor(dd.p_contactR / dd.ni, dtype=torch.float64))
        return {"dx": dx, "psi0": psi0, "psiL": psiL}

    # ---------------------------------------------------------------- EQE
    def eqe_curve(self, d_abs: Tensor, nk_abs_eqe: Tensor, tau: Tensor,
                  lam_eqe: Tensor | None = None, phi_eqe: Tensor | None = None,
                  mu: float = 2e-4, ift: bool = False):
        """EQE(λ) by running the DD solve once per wavelength (V = 0)."""
        lam_eqe = self.lam_eqe if lam_eqe is None else lam_eqe
        phi_eqe = self.phi_eqe if phi_eqe is None else phi_eqe
        Weq = lam_eqe.shape[0]
        N = self.dd.N
        d = torch.stack([torch.as_tensor(self.d_etl, dtype=torch.float64),
                         d_abs.reshape(()).to(torch.float64),
                         torch.as_tensor(self.d_htl, dtype=torch.float64)])
        nk = torch.empty(5, Weq, dtype=torch.complex128)
        nk[0] = 1.0
        nk[1] = self.nk_etl
        nk[2] = nk_abs_eqe.to(torch.complex128)
        nk[3] = self.nk_htl
        nk[4] = 1.5
        out = field_intensity(nk, d, lam_eqe)
        a_l, b_l = out["a"][2], out["b"][2]
        nkj = nk[2]
        lamw = lam_eqe[None, :]
        x_rel = torch.linspace(0.0, 1.0, N, dtype=torch.float64)
        zloc = (x_rel * d[1])[:, None]
        alpha_z = (4.0 * torch.pi * nkj.imag / lamw) * zloc
        # cross term: no extra exp(-alpha z); see tmm.field_intensity
        cross = (a_l * b_l.conj() *
                 torch.exp(4j * torch.pi * nkj.real / lamw * zloc)).real
        I2 = ((a_l * a_l.conj()).real * torch.exp(-alpha_z)
              + (b_l * b_l.conj()).real * torch.exp(alpha_z)
              + 2.0 * cross).clamp(min=0.0)               # (N,Weq)
        alpha = 4.0 * torch.pi * nkj.imag / lam_eqe        # (Weq,)
        m = self.mesh_diff(d_abs)
        dlam = (lam_eqe[1] - lam_eqe[0])                     # wavelength bin [nm]
        xw = None
        dark_out = self.dd.solve_state(torch.zeros(self.dd.N), 0.0,
                                       m["dx"], m["psi0"], m["psiL"], tau, tau, mu, mu,
                                       x0=xw, ift=ift)
        dark, xw = dark_out["J"], dark_out["x"].detach()
        eqes = []
        for w_i in range(Weq):
            # photon flux in the wavelength bin; generation ramps up via
            # continuation to keep the diffusive device on the physical branch
            phi_bin = phi_eqe[w_i] * dlam
            nr_over_n0 = nkj.real[w_i] / nk[0].real[w_i]
            G_mesh = (phi_bin * alpha[w_i] * I2[:, w_i] * nr_over_n0) * 1e7 * 1e6  # nm⁻¹→cm⁻¹, cm⁻³→m⁻³
            J = dark
            for s in (1e-2, 0.3, 1.0):
                out2 = self.dd.solve_state(G_mesh * s, 0.0, m["dx"], m["psi0"],
                                           m["psiL"], tau, tau, mu, mu, x0=xw, ift=ift)
                J, xw = out2["J"], out2["x"].detach()
            eqes.append((J - dark) / (Q * phi_bin * 1e4))
        return torch.stack(eqes).clamp(0.0, 1.0)

    # ---------------------------------------------------------------- J-V
    def jv(self, d_abs: Tensor, nk_abs: Tensor, tau: Tensor,
           V_list, mu: float = 2e-4, ift: bool = False, dV: float = 0.02) -> Tensor:
        """
        J-V [mA/cm²] (photocurrent-positive) for a bias list.

        The solve walks a dense bias grid with step dV (bias continuation —
        coarse jumps can drop the Newton iteration onto the parasitic
        hole-depleted branch) but only records the requested points, where
        IFT gradients are attached. Warm-start detachment between points is
        legitimate: the IFT backward is evaluated at each converged root.
        """
        G_opt, z_rel, _ = self.optics(d_abs, nk_abs)
        G_mesh, _ = self._interp_to_mesh(G_opt, z_rel)
        mm = self.mesh_diff(d_abs)
        req = [float(v) for v in V_list]
        req_set = set(req)
        nmax = int(round(max(req) / dV))
        walk = sorted(req_set | {round(i * dV, 10) for i in range(nmax + 1)})
        Js = {}
        x = None
        for V in walk:
            out = self.dd.solve_state(G_mesh, V, mm["dx"], mm["psi0"],
                                      mm["psiL"], tau, tau, mu, mu, x0=x,
                                      ift=ift and V in req_set)
            x = out["x"].detach()
            if V in req_set:
                Js[V] = out["J"]
        return torch.stack([Js[v] for v in req]) / 10.0   # A/m² → mA/cm²

    # ---------------------------------------------------------------- metrics
    @staticmethod
    def metrics(V: Tensor, J: Tensor) -> dict:
        """J in mA/cm² (photocurrent-positive), V in volts; V ascending."""
        # Jsc: linear interp at V=0 (J crosses from +Jsc); if V[0] > 0 use plateau
        zero = torch.zeros((), dtype=J.dtype)
        if V[0] <= 0.0:
            Jsc = _interp(zero, V, J)
        else:
            Jsc = J[0]
        Jsc = Jsc.clamp(min=1e-9)
        # Voc: zero crossing (J > 0 below Voc, J < 0 above)
        neg = (J <= 0).nonzero()
        if neg.numel() > 0 and neg[0] > 0:
            i = neg[0]
            V0, V1 = V[i - 1], V[i]
            J0, J1 = J[i - 1], J[i]
            Voc = V0 - J0 * (V1 - V0) / (J1 - J0 + 1e-300)
        else:
            Voc = V[-1]
        P = V * J
        Pmax_idx = int(P.argmax())
        Pmax = P[Pmax_idx]
        FF = (Pmax / (Jsc * Voc)).clamp(0.0, 1.0)
        return {"Jsc": Jsc, "Voc": Voc, "FF": FF, "PCE": Pmax / 100.0,
                "Vmpp": V[Pmax_idx], "Jmpp": J[Pmax_idx]}
