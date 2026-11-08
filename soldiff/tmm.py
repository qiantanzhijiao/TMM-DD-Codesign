"""
Differentiable Transfer Matrix Method (TMM) in PyTorch.

Computes position- and wavelength-resolved |E(z,λ)|² (normalized to the incident
amplitude) in a planar multilayer stack, and the carrier generation rate
G(z) = ∫ Φ(λ) α(λ) |E(z,λ)|²/|E₀|² dλ.

All ops are torch float64: thicknesses and complex refractive indices are
differentiable design parameters.

Physics: coherent, normal-incidence plane waves; optional incoherent treatment
per layer (interference term dropped). α_j = 4π·k_j/λ.

Layer convention (stack of L entries):
    layer 0        : ambient / incident medium (semi-infinite)
    layers 1..L-2  : physical layers, thicknesses d (nm)
    layer L-1      : substrate / exit medium (semi-infinite)
Amplitudes (a_j, b_j): E_j(z) = a_j·e^{+ik_j(z-z_j^left)} + b_j·e^{-ik_j(z-z_j^left)}
Computed as *linear functions of the ambient reflection r* via forward recursion;
the substrate condition b_{L-1}=0 fixes r. This keeps the whole recursion exact,
vectorized over wavelengths, and autograd-friendly.
"""
from __future__ import annotations
import torch
from torch import Tensor

TwoPi = 2.0 * torch.pi


def field_intensity(nk_stack: Tensor, d_stack: Tensor, lam: Tensor,
                    incoherent_mask: Tensor | None = None,
                    z_grid: Tensor | None = None) -> dict:
    """
    nk_stack : (L, W) complex128 — full stack incl. ambient (0) and substrate (L-1).
    d_stack  : (L-2,) float64 — thicknesses [nm] of physical layers.
    lam      : (W,) float64 — wavelengths [nm].
    incoherent_mask : optional bool (L-2,) — drop interference inside marked layers.
    z_grid   : optional (Z,) float64 — sample positions [nm] from stack top (0 = surface).

    Returns dict:
      I2 (W,Z) |E|²/|E₀|², z (Z,) [nm], layer_id (Z,) internal-layer index,
      R (W,), T (W,), bounds (L-1,), a, b (L,W) complex amplitudes.
    """
    L, W = nk_stack.shape
    device = nk_stack.device
    dtype = nk_stack.real.dtype
    d_tot = d_stack.sum()
    if z_grid is None:
        z_grid = torch.arange(0.0, d_tot.item() + 1.0, 1.0, device=device, dtype=dtype)
    d_full = torch.cat([torch.zeros(1, device=device, dtype=dtype),
                        d_stack.to(dtype),
                        torch.zeros(1, device=device, dtype=dtype)])
    deltas = TwoPi * nk_stack * (d_full[:, None] / lam[None, :])   # (L, W)

    # --- forward recursion: amplitudes linear in r ---------------------------
    one = torch.ones(1, W, dtype=nk_stack.dtype, device=device)
    zero = torch.zeros(1, W, dtype=nk_stack.dtype, device=device)
    aA, aB, bA, bB = [one], [zero], [zero], [one]
    for j in range(L - 1):
        uA = aA[j] * torch.exp(1j * deltas[j]); uB = aB[j] * torch.exp(1j * deltas[j])
        vA = bA[j] * torch.exp(-1j * deltas[j]); vB = bB[j] * torch.exp(-1j * deltas[j])
        c = 0.5 * nk_stack[j][None, :] / nk_stack[j + 1][None, :]
        sA, sB = 0.5 * (uA + vA), 0.5 * (uB + vB)
        dA, dB = c * (uA - vA), c * (uB - vB)
        aA.append(sA + dA); aB.append(sB + dB)
        bA.append(sA - dA); bB.append(sB - dB)
    aA = torch.stack(aA); aB = torch.stack(aB); bA = torch.stack(bA); bB = torch.stack(bB)
    r = -bA[L - 1].reshape(W) / bB[L - 1].reshape(W)               # (W,)
    a = (aA + aB * r[None, :]).reshape(L, W)
    b = (bA + bB * r[None, :]).reshape(L, W)
    R = (r * r.conj()).real
    t = a[L - 1]
    # Power transmittance.  Do NOT clamp: an unphysical T > 1 must remain
    # visible to the energy-balance check instead of being silently hidden.
    T = (nk_stack[L - 1] / nk_stack[0]).real * (t * t.conj()).real

    # --- sample |E|² on the grid inside physical layers ----------------------
    bounds = torch.cat([torch.zeros(1, device=device, dtype=dtype),
                        torch.cumsum(d_stack.to(dtype), 0)])       # (L-2+1,)
    lid = (torch.searchsorted(bounds, z_grid, right=True) - 1).clamp(0, L - 3)
    zloc = z_grid - bounds[lid]
    nkj = nk_stack[1 + lid]                                        # (Z,W)
    aj, bj = a[1 + lid], b[1 + lid]
    lamw = lam[None, :]
    alpha_z = (4.0 * torch.pi * nkj.imag / lamw) * zloc[:, None]   # α·z
    # |E|² = |a|²e^{−αz} + |b|²e^{+αz} + 2 Re[a b* e^{2 i k_r z}],
    # k_r = 2π n_r/λ.  The cross term carries NO extra exp(−αz): the two
    # αz/2 factors from the counter-propagating waves cancel exactly.
    cross = (aj * bj.conj() *
             torch.exp(4j * torch.pi * nkj.real / lamw * zloc[:, None])).real
    if incoherent_mask is not None:
        cross = torch.where(incoherent_mask[lid][:, None],
                            torch.zeros_like(cross), cross)
    I2 = ((aj * aj.conj()).real * torch.exp(-alpha_z)
          + (bj * bj.conj()).real * torch.exp(alpha_z)
          + 2.0 * cross).clamp(min=0.0)                            # (Z,W)
    return {"I2": I2.t(), "z": z_grid, "layer_id": lid, "R": R, "T": T,
            "bounds": bounds, "a": a, "b": b}


def generation_rate(nk_stack: Tensor, d_stack: Tensor, lam: Tensor,
                    phi_sun: Tensor, target_layer: int = 0,
                    alpha_ext: Tensor | None = None, **kw) -> dict:
    """
    G(z) in the target internal layer [photons cm⁻³ s⁻¹].

    G(z) = ∫ Φ(λ) α(λ) |E(z,λ)|²/|E₀|² dλ,   α = 4π k/λ  [nm⁻¹]
    (α_ext may override, e.g. tabulated absorption [nm⁻¹])
    """
    out = field_intensity(nk_stack, d_stack, lam, **kw)
    I2 = out["I2"]                                                 # (Z,W)
    sel = (out["layer_id"] == target_layer)
    alpha = (4.0 * torch.pi * nk_stack[1 + target_layer].imag / lam
             if alpha_ext is None else alpha_ext)                  # (W,)
    # Poynting factor: dissipated power density is ω ε0 n_r k |E|², while the
    # incident flux is (1/2) c ε0 n_0 |E0|².  Hence dA/dz =
    # (n_r/n_0) α |E|²/|E0|², NOT α |E|²/|E0|².  Dropping n_r/n_0
    # underestimates generation (and Jsc, EQE, PCE) by ~2.5× for n_r≈2.55.
    n0 = nk_stack[0].real                                          # (W,)
    nr = nk_stack[1 + target_layer].real                           # (W,)
    G_spec = (alpha * phi_sun * (nr / n0))[:, None] * I2            # (W,Z)
    G_spec = G_spec * sel.to(G_spec.dtype)[None, :]                # target layer only
    G = torch.trapz(G_spec, lam[:, None].expand_as(G_spec), dim=0).squeeze(-1) * 1e7  # nm⁻¹→cm⁻¹
    out.update(G=G, target_layer=target_layer)
    return out


def absorbed_fraction(nk_stack: Tensor, d_stack: Tensor, lam: Tensor,
                      n_grid: int = 2001) -> dict:
    """Spectral absorptance from the local dissipated power, plus the
    independent Poynting-balance reference A = 1 - R - T.

    A(λ) = ∫ (n_r(z,λ)/n_0(λ)) α(z,λ) |E(z,λ)|²/|E₀|² dz

    This is the absolute (external) validation missing from the original
    test suite: internal checks such as R+T≤1 or EQE-integrated Jsc vs J-V
    Jsc cannot detect a common multiplicative error in G(z).
    """
    L, W = nk_stack.shape
    # Only the layer amplitudes r, t are needed from the global recursion.
    out = field_intensity(nk_stack, d_stack, lam,
                          z_grid=torch.zeros(1, device=nk_stack.device,
                                             dtype=nk_stack.real.dtype))
    A = torch.zeros(W, device=nk_stack.device, dtype=nk_stack.real.dtype)
    # Integrate layer by layer: n_r and alpha jump at every interface, so a
    # single trapezoid over the whole stack converges erratically (the error
    # depends on whether a grid point happens to land on an interface).
    for j in range(L - 2):
        dj = float(d_stack[j].detach())
        zl = torch.linspace(0.0, dj, n_grid, device=nk_stack.device,
                            dtype=nk_stack.real.dtype)          # (Z,)
        nkj = nk_stack[j + 1]                                  # (W,)
        aj, bj = out["a"][j + 1], out["b"][j + 1]               # (W,)
        alpha = 4.0 * torch.pi * nkj.imag / lam                 # (W,)
        kr = 2.0 * torch.pi * nkj.real / lam                    # (W,)
        c = (aj * bj.conj())[:, None]                       # (W,1)
        phase = 2.0 * kr[:, None] * zl[None, :]              # (W,Z)
        I2 = ((aj * aj.conj()).real[:, None] * torch.exp(-alpha[:, None] * zl[None, :])
              + (bj * bj.conj()).real[:, None] * torch.exp(alpha[:, None] * zl[None, :])
              + 2.0 * (c.real * torch.cos(phase) - c.imag * torch.sin(phase)))
        integrand = ((nkj.real / nk_stack[0].real) * alpha)[:, None] * I2
        A = A + torch.trapz(integrand, zl.expand_as(integrand), dim=1)
    out.update(A_field=A, A_poynting=1.0 - out["R"] - out["T"])
    return out
