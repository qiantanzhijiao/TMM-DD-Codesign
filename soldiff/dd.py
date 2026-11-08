"""
Differentiable 1D drift-diffusion solver for photovoltaic devices.

Formulation
-----------
Fully-coupled Newton iteration on Poisson + electron/hole continuity in the
**log-density** (ψ, wⁿ, wᵖ) formulation.  Unknowns at interior nodes
(i = 1..N-2):

    ψ   electrostatic potential            [V]
    wⁿ  electron quasi-Fermi offset       [V]
    wᵖ  hole quasi-Fermi offset           [V]

with wⁿ = φn − ψ, wᵖ = φp − ψ and Boltzmann statistics
    n = ni·exp(−wⁿ/VT),   p = ni·exp(+wᵖ/VT).

Each carrier density depends on a single unknown, which removes the diagonal
gauge redundancy of the (ψ, φn, φp) formulation.

Scharfetter–Gummel midpoint currents in exponentially factored form
(δ_i = (ψ_{i+1}−ψ_i)/VT, B(x)=x/(e^x−1), Δw_i = w_{i+1} − w_i):
    J_{n,i+½} = −(qDn/dx)·ni·e^(−wⁿ_i/VT)·[B(−δ_i) − B(δ_i)·e^(−Δwⁿ_i/VT)]
    J_{p,i+½} = +(qDp/dx)·ni·e^(+wᵖ_i/VT)·[B(δ_i) − B(−δ_i)·e^(+Δwᵖ_i/VT)]

The factored brackets are O(1) and cancel exactly at equilibrium, avoiding the
float64 cancellation of the textbook B(−δ)n_i − B(δ)n_{i+1} form.

continuity  dJn/dx = q(R−G),  −dJp/dx = q(R−G),
SRH recombination  R = (np−ni²)/(τp(n+ni) + τn(p+ni)),
and Poisson  εψ'' = −q(p−n)  (no fixed charge).

Boundary conditions (ideal ohmic, bias V applied between contacts):
    ψ = ψ0 (left), ψ = ψL (right)          — Dirichlet from work functions
    φn = φp = 0 at the left contact,  φn = φp = +V at the right contact
    (forward bias raises the majority hole density at the anode, so the dark
    diode current opposes the photocurrent).

Differentiation
---------------
The converged solution x*(θ) is a root of F(x, θ) = 0. Gradients w.r.t. the
design parameters θ (generation profile, lifetimes, mobilities, contacts, ...)
are obtained with the implicit function theorem via a custom autograd
Function: backward solves Jᵀλ = g and returns  ∂F/∂θᵀ·(−λ)  exactly.
"""
from __future__ import annotations
import torch
from torch import Tensor

Q = 1.602176634e-19          # C
KB = 1.380649e-23            # J/K
EPS0 = 8.8541878128e-12      # F/m

# Potential damping cap.  Both the IFT-wrapped and the plain Newton loop MUST
# use the same value: finite-difference validation differentiates the plain
# forward map, and a different damping factor would make the two solvers
# converge to (slightly) different iterates, producing a spurious gradient
# mismatch that has nothing to do with the implicit-function theorem.
PSI_CAP = 0.4


def _B(x: Tensor) -> Tensor:
    """Bernoulli function x/(e^x − 1), stable near 0."""
    return torch.where(x.abs() < 1e-8, 1.0 - 0.5 * x, x / torch.expm1(x))


def make_residual(ni: Tensor, VT: float, eps: Tensor, dx: Tensor,
                  psi0: Tensor, psiL: Tensor, V: float,
                  tau_n: Tensor, tau_p: Tensor,
                  Dn: Tensor, Dp: Tensor, G: Tensor):
    """
    Build the residual F(x, θ) for the coupled Newton system in the
    **log-density formulation**:

        x = [ψ_int, wn_int, wp_int],   n = ni·e^(−wn/VT),  p = ni·e^(+wp/VT)

    where wn = φn − ψ and wp = φp − ψ are quasi-Fermi-level offsets. Unlike
    the raw (ψ, φn, φp) variables, each carrier density depends on a single
    unknown, so the diagonal-shift gauge redundancy (ψ→ψ+g, φn→φn+g,
    φp→φp+g leaving n, p invariant) is removed structurally and the
    Newton step is a genuine descent direction.

    SG currents in exponentially-factored form (O(1) brackets, no 10²⁴-scale
    cancellation):
        Jn = −(qDn/dx)·ni·e^(−wn_i/VT)·[B(−δ) − B(δ)e^(−Δwn_i/VT)]
        Jp = +(qDp/dx)·ni·e^(+wp_i/VT)·[B(δ) − B(−δ)e^(+Δwp_i/VT)]
    """
    N = G.shape[0]

    def residual(x: Tensor, theta: Tensor) -> Tensor:
        # theta = [G(N), tau_n, tau_p, Dn, Dp, psi0, psiL, dx]
        Gn, tn, tp, Dne, Dpe, p0, pL, dxv = theta
        cE = Q * Dne / dxv
        cH = Q * Dpe / dxv
        psi = torch.cat([p0[None], x[:N - 2], pL[None]])
        m = x.dtype
        # Applied bias V > 0 forward-biases the hole (right) contact: the
        # quasi-Fermi POTENTIAL there is φ = +V (n = ni·e^((ψ−φ)/VT)), so the
        # majority hole density rises p ∝ e^(+V/VT) — the true diode direction
        # whose dark current opposes the photocurrent.
        wnL = torch.tensor(-float(p0.detach()), dtype=m, device=x.device)
        wnR = torch.tensor(V - float(pL.detach()), dtype=m, device=x.device)
        wn = torch.cat([wnL[None], x[N - 2:2 * (N - 2)], wnR[None]])
        wp = torch.cat([wnL[None], x[2 * (N - 2):], wnR[None]])
        n = ni * torch.exp(-wn / VT)
        p = ni * torch.exp(wp / VT)
        delta = (psi[1:] - psi[:-1]) / VT                      # (N-1,)
        Bm, Bp = _B(-delta), _B(delta)
        dwn = (wn[1:] - wn[:-1]) / VT
        dwp = (wp[1:] - wp[:-1]) / VT
        Jn = -cE * ni * torch.exp(-wn[:-1] / VT) * (Bm - Bp * torch.exp(-dwn))
        Jp = cH * ni * torch.exp(wp[:-1] / VT) * (Bp - Bm * torch.exp(dwp))
        R = (n * p - ni ** 2) / (tp * (n + ni) + tn * (p + ni))
        divJn = (Jn[1:] - Jn[:-1]) / dxv
        divJp = (Jp[1:] - Jp[:-1]) / dxv
        R_i = R[1:-1]                                          # interior nodes only
        f1 = divJn - Q * (R_i - Gn[1:-1])                      # electron continuity
        f2 = -divJp - Q * (R_i - Gn[1:-1])                     # hole continuity
        lap = (psi[:-2] - 2 * psi[1:-1] + psi[2:]) * eps / dxv ** 2
        f3 = lap + Q * (p[1:-1] - n[1:-1])                     # Poisson
        return torch.cat([f1, f2, f3])

    return residual


def _scaled_solve(J: Tensor, F: Tensor, refine: int = 1) -> Tensor:
    """Solve Jd = −F with row/column max-abs equilibration + iterative
    refinement in the original residual (the row scales span ~24 decades,
    so one refinement pass is needed for a usable Newton direction)."""
    rs = J.abs().amax(dim=1).clamp(min=1e-300)
    Jr = J / rs[:, None]
    cs = Jr.abs().amax(dim=0).clamp(min=1e-300)
    Jc = Jr / cs[None, :]
    try:
        d = torch.linalg.solve(Jc, (-F / rs).unsqueeze(1)).squeeze(1) / cs
    except Exception:
        d = torch.linalg.lstsq(Jc, (-F / rs).unsqueeze(1)).solution.squeeze(1) / cs
    for _ in range(refine):
        r = F + J @ d
        d = d + torch.linalg.solve(Jc, (-r / rs).unsqueeze(1)).squeeze(1) / cs
    return d


def _potential_damp(d: Tensor, cap: float = 0.5) -> Tensor:
    """Selberherr/Heiser potential damping d ← d/(1+|d|/cap).
    Leaves small (linear-regime) components untouched — quadratic
    convergence near the root — while mapping the exponentially-inflated
    steps of the drift-diffusion stiffness to O(cap) moves."""
    return d / (1.0 + d.abs() / cap)


def _jac(residual, x: Tensor, th: list) -> Tensor:
    """Full Jacobian ∂F/∂x at x (θ detached); x is given requires_grad locally."""
    xg = x.detach().requires_grad_(True)
    return torch.autograd.functional.jacobian(
        lambda xx: residual(xx, th), xg, vectorize=True)


def newton_ift(residual, x0: Tensor, theta: Tensor, max_iter: int = 40,
               tol: float = 1e-9, psi_cap: float = PSI_CAP,
               n_int: int = 0, verbose: bool = False, info: dict | None = None,
               abs_floor: float = 3e2, adjoint_refine: int = 3,
               res_scale: float | None = None,
               step_tol: float = 1e-9, noise_rel: float = 1e-3):
    """
    Full-Newton solve of residual(x, theta) = 0 with IFT gradients.

    The Newton loop runs on detached tensors (fast, no graph); the final
    iterate is returned through a custom autograd Function so that the
    converged x*(θ) carries exact implicit-function gradients:
        backward: solve Jᵀλ = grad_x,  grad_θ = −(∂F/∂θ)ᵀλ.

    x0            : (3·n_int,) warm start
    theta         : list of differentiable tensors forwarded to residual
    n_int         : number of interior nodes (unknowns per species)
    Returns (x*, converged, iters).
    """
    n_int = n_int or (x0.shape[0] // 3)
    info = {} if info is None else info

    class _Solve(torch.autograd.Function):
        @staticmethod
        def forward(ctx, x0_in, *theta_in):
            th = [t.detach() for t in theta_in]
            with torch.no_grad():
                x = x0_in.detach().clone()
                F = residual(x, th)
                fnorm = F.abs().max()
                fnorm0 = fnorm
                # Convergence MUST be measured on a PHYSICAL residual scale,
                # not on the warm-start residual fnorm0.  When the applied bias
                # is stepped, the boundary condition jumps and fnorm0 can be
                # 1e17 A/m^3; a criterion tol*fnorm0 then declares convergence
                # at |F| ~ 1e8, i.e. at a point that is nowhere near a root.
                # IFT gradients evaluated there are systematically wrong.
                # res_scale = q*G_max is the natural continuity scale; the
                # absolute floor covers the float64 cancellation noise.
                scale = fnorm0 if res_scale is None else torch.as_tensor(
                    res_scale, dtype=fnorm0.dtype)
                target = torch.clamp(tol * scale, min=abs_floor)
                # At large forward bias the continuity residual is the small
                # difference of ~1e10 A/m^3 recombination/current terms, so
                # float64 cancellation leaves an irreducible |F| ~ 1e3-1e4.
                # There the Newton *step* is the meaningful convergence
                # measure: |J^-1 F| < step_tol means x* is a true root to
                # machine precision, which is what the IFT requires.
                noise_cap = noise_rel * scale
                converged = bool(fnorm < target)
                it = 0
                while not converged and it < max_iter:
                    it += 1
                    J = _jac(residual, x, th)
                    d_raw = _scaled_solve(J, F)
                    if (float(d_raw.abs().max()) < step_tol
                            and fnorm < noise_cap):
                        converged = True
                        break
                    d = _potential_damp(d_raw, psi_cap)
                    # Armijo backtracking line search on the residual 2-norm
                    fn2 = (F * F).sum()
                    alpha = 1.0
                    ok = False
                    for _ls in range(50):
                        x_try = x + alpha * d
                        F_try = residual(x_try, th)
                        if torch.isnan(F_try).any():
                            alpha *= 0.5
                            continue
                        if (F_try * F_try).sum() <= (1.0 - 1e-4 * alpha) * fn2:
                            ok = True
                            break
                        alpha *= 0.5
                    if not ok:
                        converged = bool(fnorm < target)
                        break
                    x, F, fnorm = x_try, F_try, F_try.abs().max()
                    converged = bool(fnorm < target)
            if info is not None:
                info.update(converged=converged, iters=it, fnorm=fnorm.item(),
                            target=float(target), fnorm0=float(fnorm0),
                            res_scale=float(scale))
            ctx.save_for_backward(x, *theta_in)
            ctx.residual = residual
            ctx.n_int = n_int
            return x

        @staticmethod
        def backward(ctx, grad_x):
            x, *theta_in = ctx.saved_tensors
            with torch.enable_grad():
                xd = x.detach().requires_grad_(True)
                thd = [t.detach().requires_grad_(True) for t in theta_in]
                F = ctx.residual(xd, thd)
                J = _jac(ctx.residual, xd, thd)
                # ∂L/∂θ = −(∂F/∂θ)ᵀ λ  with  λ = J⁻ᵀ grad_x.
                # NOTE _scaled_solve returns the solution of J·d = −F, i.e.
                # _scaled_solve(Jᵀ, g) = −J⁻ᵀ g = −λ, which is exactly the
                # grad_outputs vector we need.
                # Extra refinement passes matter: the equilibrated Jacobian
                # spans ~24 decades, and a single pass leaves an adjoint
                # residual large enough to bias gradients at the 1e-3 level.
                lam = _scaled_solve(J.transpose(0, 1), grad_x.detach(),
                                    refine=adjoint_refine)
                if info is not None:
                    with torch.no_grad():
                        res = J.transpose(0, 1) @ lam.detach() + grad_x.detach()
                        info["adjoint_residual_rel"] = float(
                            res.norm() / (grad_x.detach().norm() + 1e-300))
                grad_th = torch.autograd.grad(F, thd, grad_outputs=lam,
                                              allow_unused=True)
            out = tuple(g if g is not None else torch.zeros_like(t)
                        for g, t in zip(grad_th, thd))
            return (None,) + out

    return _Solve.apply(x0, *theta)


class DDDevice:
    """1D p-i-n-like photovoltaic device (single absorber, ideal selective contacts)."""

    def __init__(self, N: int = 129, T: float = 300.0):
        self.N = N
        self.T = T
        self.VT = KB * T / Q                       # thermal voltage [V]
        # MAPbI3-like absorber (SI units, densities in m^-3)
        self.Eg = 1.55                             # eV
        self.chi = 3.90                            # electron affinity [eV]
        self.eps_r = 6.5
        self.Nc = 2.2e24                           # m^-3
        self.Nv = 1.8e25                           # m^-3
        self.ni = float(torch.sqrt(torch.tensor(self.Nc * self.Nv, dtype=torch.float64))
                        * torch.exp(torch.tensor(-self.Eg * Q / (2.0 * KB * T),
                                                 dtype=torch.float64)))   # m^-3
        self.n_contactL = 2.2e24                   # electron contact (ETL side)
        self.p_contactR = 1.8e25                   # hole contact (HTL side)
        # Solver tolerances (exposed so that gradient-verification experiments
        # can sweep them).  abs_floor is in residual units (A/m^3); the
        # original hard-coded value 3e2 is retained as the default.
        self.rel_tol = 1e-9
        self.abs_floor = 3e2

    # ------------------------------------------------------------------ setup
    def mesh(self, L_nm: float) -> dict:
        """Grid for absorber thickness L_nm; returns dx [m], ψ boundary values."""
        dx = torch.tensor(L_nm * 1e-9 / (self.N - 1), dtype=torch.float64)
        psi0 = self.VT * torch.log(torch.tensor(self.n_contactL / self.ni,
                                                dtype=torch.float64))
        psiL = -self.VT * torch.log(torch.tensor(self.p_contactR / self.ni,
                                                 dtype=torch.float64))
        return {"dx": dx, "psi0": psi0, "psiL": psiL, "L": L_nm * 1e-9}

    # ------------------------------------------------------------- equilibrium
    def equilibrium(self, dx: Tensor, psi0: Tensor, psiL: Tensor,
                    newton_iter: int = 60, tol: float = 1e-12) -> Tensor:
        """
        Self-consistent equilibrium potential via Newton on the
        Poisson–Boltzmann equation (n = ni·e^{ψ/VT}, p = ni·e^{−ψ/VT}).
        Provides the physically consistent initial guess for the biased solves.
        """
        N, ni, VT = self.N, self.ni, self.VT
        eps = self.eps_r * EPS0
        x = torch.linspace(0.0, 1.0, N, dtype=torch.float64)
        psi = psi0 + (psiL - psi0) * x
        L = (torch.diag(torch.full((N - 2,), -2.0, dtype=torch.float64))
             + torch.diag(torch.ones(N - 3), 1) + torch.diag(torch.ones(N - 3), -1)) / dx ** 2

        def pb_res(psi_full):
            n = ni * torch.exp(psi_full / VT)
            p = ni * torch.exp(-psi_full / VT)
            F = L @ psi_full[1:-1] - (Q / eps) * (n - p)[1:-1]
            F = F.clone()
            F[0] = F[0] + psi0 / dx ** 2
            F[-1] = F[-1] + psiL / dx ** 2
            return F

        for _ in range(newton_iter):
            F = pb_res(psi)
            fn = F.abs().max()
            n = ni * torch.exp(psi / VT)
            p = ni * torch.exp(-psi / VT)
            Jac = L - torch.diag((Q / eps) * (n + p)[1:-1] / VT)
            d = torch.linalg.solve(Jac, -F)
            alpha = 1.0
            for _ls in range(24):
                psi_try = torch.cat([psi0[None], psi[1:-1] + alpha * d, psiL[None]])
                if pb_res(psi_try).abs().max() < fn or alpha < 2 ** -22:
                    break
                alpha = alpha * 0.5
            step = (alpha * d).abs().max().item()
            psi = psi_try
            if step < tol and fn < 1e-6 * (Q / eps) * ni:
                break
        return psi

    # ------------------------------------------------------------- full Newton
    def solve_state(self, G: Tensor, V: float, dx: Tensor, psi0: Tensor, psiL: Tensor,
                    tau_n: Tensor, tau_p: Tensor, mu_n: float = 2e-4, mu_p: float = 2e-4,
                    x0: Tensor | None = None, max_iter: int = 50,
                    tol: float | None = None, ift: bool = False) -> dict:
        """
        Fully-coupled Newton solve of Poisson ⊕ continuity in the (ψ, φn, φp)
        formulation.

        G    : (N,) generation rate [m^-3 s^-1] (differentiable source term)
        ift  : if True, the returned unknown vector x* is wrapped in an
               implicit-function autograd node → exact dJ/dθ through the
               converged solve (recommended for inverse design).

        Returns dict(ψ, n, p, J [A/m²], converged, iters, x).
        """
        N, ni, VT = self.N, self.ni, self.VT
        eps = self.eps_r * EPS0
        Dn = torch.as_tensor(mu_n * VT, dtype=torch.float64)
        Dp = torch.as_tensor(mu_p * VT, dtype=torch.float64)
        Gn = torch.as_tensor(G, dtype=torch.float64)
        tn = torch.as_tensor(tau_n, dtype=torch.float64)
        tp = torch.as_tensor(tau_p, dtype=torch.float64)

        dxt = torch.as_tensor(dx, dtype=torch.float64)
        theta = [Gn, tn, tp, Dn, Dp,
                 torch.as_tensor(psi0, dtype=torch.float64),
                 torch.as_tensor(psiL, dtype=torch.float64), dxt]
        residual = make_residual(torch.tensor(ni, dtype=torch.float64), VT, eps,
                                 dxt, theta[5], theta[6], V, tn, tp, Dn, Dp, Gn)

        if x0 is None:
            x_eq = self.equilibrium(dx, theta[5], theta[6])
            # log-density variables: wn = wp = φ − ψ = −ψ at equilibrium (φ=0)
            x = torch.cat([x_eq[1:-1], -x_eq[1:-1], -x_eq[1:-1]])
        else:
            x = torch.as_tensor(x0, dtype=torch.float64)

        tol = self.rel_tol if tol is None else tol
        # Physical scale of the continuity equations [A/m^3].  Using this
        # instead of the warm-start residual makes convergence bias-independent.
        res_scale = float(Q * Gn.detach().abs().max())
        if ift:
            info = {}
            x_star = newton_ift(residual, x, theta, max_iter=max_iter,
                                tol=tol, abs_floor=self.abs_floor,
                                n_int=N - 2, info=info, res_scale=res_scale)
            conv, it = info["converged"], info["iters"]
        else:
            x_star, conv, it = self._newton_plain(residual, x, theta,
                                                  max_iter, tol, N - 2,
                                                  abs_floor=self.abs_floor,
                                                  res_scale=res_scale)

        with torch.enable_grad() if ift else torch.no_grad():
            psi0t, psiLt = theta[5], theta[6]
            psi = torch.cat([psi0t[None], x_star[:N - 2], psiLt[None]])
            m_dt = x_star.dtype
            wnR = V * torch.ones(1, dtype=m_dt) - psiLt
            wnL = (-psi0t)[None]
            wn = torch.cat([wnL, x_star[N - 2:2 * (N - 2)], wnR])
            wp = torch.cat([wnL, x_star[2 * (N - 2):], wnR])
            n = ni * torch.exp(-wn / VT)
            p = ni * torch.exp(wp / VT)
            delta = (psi[1:] - psi[:-1]) / VT
            Bm, Bp = _B(-delta), _B(delta)
            dwn = (wn[1:] - wn[:-1]) / VT
            dwp = (wp[1:] - wp[:-1]) / VT
            cDe, cDh = Q * Dn / dxt, Q * Dp / dxt
            Jn = -cDe * ni * torch.exp(-wn[:-1] / VT) * (Bm - Bp * torch.exp(-dwn))
            Jp = cDh * ni * torch.exp(wp[:-1] / VT) * (Bp - Bm * torch.exp(dwp))
            J = 0.5 * ((Jn[0] + Jp[0]) + (Jn[-1] + Jp[-1]))
        return {"psi": psi, "n": n, "p": p, "J": J, "converged": conv,
                "iters": it, "x": x_star}

    @staticmethod
    def _newton_plain(residual, x, theta, max_iter, tol, n_int,
                      abs_floor: float = 3e2,
                      res_scale: float | None = None,
                      step_tol: float = 1e-9, noise_rel: float = 1e-3):
        """Same Newton loop without the IFT wrapper (for cheap forward runs)."""
        F = residual(x, theta)
        fnorm = F.abs().max()
        fnorm0 = fnorm
        scale = fnorm0 if res_scale is None else torch.as_tensor(
            res_scale, dtype=fnorm0.dtype)
        target = torch.clamp(tol * scale, min=abs_floor)
        noise_cap = noise_rel * scale
        conv = bool(fnorm < target)
        it = 0
        while not conv and it < max_iter:
            it += 1
            J = _jac(residual, x, theta)
            d_raw = _scaled_solve(J, F)
            if float(d_raw.abs().max()) < step_tol and fnorm < noise_cap:
                conv = True
                break
            d = _potential_damp(d_raw, PSI_CAP)
            fn2 = (F * F).sum()
            alpha, ok = 1.0, False
            for _ls in range(50):
                x_try = x + alpha * d
                F_try = residual(x_try, theta)
                if torch.isnan(F_try).any():
                    alpha *= 0.5
                    continue
                if (F_try * F_try).sum() <= (1.0 - 1e-4 * alpha) * fn2:
                    ok = True
                    break
                alpha *= 0.5
            if not ok:
                conv = bool(fnorm < target)
                break
            x, F, fnorm = x_try, F_try, F_try.abs().max()
            conv = bool(fnorm < target)
        return x, conv, it

    # ------------------------------------------------------------------ J-V
    def jv_curve(self, G: Tensor, V_list, dx: Tensor, psi0: Tensor, psiL: Tensor,
                 tau_n: Tensor, tau_p: Tensor, mu_n: float = 2e-4, mu_p: float = 2e-4,
                 ift: bool = False) -> Tensor:
        """
        J-V [mA/cm²] (photocurrent-positive) over V_list with bias-continuation
        (warm start from the previous bias point). G differentiable (N,).
        """
        N = self.N
        x = None
        Js = []
        for V in V_list:
            out = self.solve_state(G, V, dx, psi0, psiL, tau_n, tau_p,
                                   mu_n, mu_p, x0=x, ift=ift)
            x = out["x"].detach()
            Js.append(out["J"])
        J = torch.stack(Js) / 10.0            # A/m² → mA/cm²
        return -J                             # photocurrent-positive convention
