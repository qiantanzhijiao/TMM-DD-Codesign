"""Smoke tests for the new full-coupled Newton DD solver + IFT gradients."""
import sys, time
from pathlib import Path

# Works both in the development tree (this file sits next to the package)
# and in the released repository (this file sits in tests/).
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))
import torch
torch.set_default_dtype(torch.float64)
from soldiff.dd import DDDevice, Q

dev = DDDevice(N=73)
m = dev.mesh(400.0)

# ---- 1. dark J-V -----------------------------------------------------------
print("== dark J-V ==")
t0 = time.time()
G0 = torch.zeros(dev.N)
for V in [0.0, 0.5, 0.9, 1.0, 1.1, 1.2]:
    out = dev.solve_state(G0, V, m["dx"], m["psi0"], m["psiL"],
                          torch.tensor(1e-6), torch.tensor(1e-6), 2e-4, 2e-4)
    print(f"  V={V:4.2f}  J={out['J']: .6e} A/m2  conv={out['converged']} it={out['iters']}")
print(f"  ({time.time()-t0:.1f}s)")

# ---- 2. uniform generation Jsc vs analytic --------------------------------
print("== uniform G, V=0 ==")
G_u = torch.full((dev.N,), 4.7e27)   # m^-3 s^-1
t0 = time.time()
out = dev.solve_state(G_u, 0.0, m["dx"], m["psi0"], m["psiL"],
                      torch.tensor(1e-6), torch.tensor(1e-6), 2e-4, 2e-4)
print(f"  J = {out['J']:.4f} A/m2 = {out['J']/10:.2f} mA/cm2  conv={out['converged']} it={out['iters']} ({time.time()-t0:.1f}s)")
# analytic pure-diffusion estimate: J = q G L  (uniform gen, perfect collection)
print(f"  analytic qGL = {Q*4.7e27*400e-9:.2f} A/m2")

# ---- 3. IFT gradient vs finite difference (E1) -----------------------------
print("== IFT gradient check (dJ/dtau_n at V=1.0, uniform G) ==")
tau_n0 = 2e-7
# warm start via illuminated bias continuation (physical branch)
G_u = torch.full((dev.N,), 4.7e27)
xw = None
for Vi in range(0, 51):
    o = dev.solve_state(G_u, Vi * 0.02, m["dx"], m["psi0"], m["psiL"],
                        torch.tensor(tau_n0), torch.tensor(2e-7), 2e-4, 2e-4, x0=xw)
    xw = o["x"].detach()
Vt = 1.0

def J_of(tau_n_val):
    tn = torch.tensor(tau_n_val, requires_grad=True)
    tp = torch.tensor(2e-7)
    res = dev.solve_state(G_u, Vt, m["dx"], m["psi0"], m["psiL"], tn, tp,
                          2e-4, 2e-4, x0=xw, ift=True)
    return res["J"], tn

J0, tn_t = J_of(tau_n0)
grad_ift = torch.autograd.grad(J0, tn_t)[0]
print(f"  J(tau0) = {J0.item():.6e}  IFT grad = {grad_ift.item():.6e}")

h = 1e-9   # central FD, ~1e-9 on 2e-7 = 0.5% step
Jp_, _ = J_of(tau_n0 + h); Jp = float(Jp_.detach())
Jm_, _ = J_of(tau_n0 - h); Jm = float(Jm_.detach())
grad_fd = (Jp - Jm) / (2 * h)
rel = abs(grad_ift.item() - grad_fd) / (abs(grad_fd) + 1e-300)
print(f"  FD grad  = {grad_fd:.6e}   rel err = {rel:.3e}")

# gradient wrt a generation amplitude too (route to optics params)
print("== IFT gradient check (dJ/dG_scale at V=0.9) ==")
Gs = torch.tensor(1.0, requires_grad=True)
res = dev.solve_state(G_u * Gs, 0.9, m["dx"], m["psi0"], m["psiL"],
                      torch.tensor(2e-7), torch.tensor(2e-7), 2e-4, 2e-4, ift=True)
g = torch.autograd.grad(res["J"], Gs)[0]
g_fd = None
Jp_ = dev.solve_state(G_u * (1 + 1e-6), 0.9, m["dx"], m["psi0"], m["psiL"],
                      torch.tensor(2e-7), torch.tensor(2e-7), 2e-4, 2e-4)["J"]
Jm_ = dev.solve_state(G_u * (1 - 1e-6), 0.9, m["dx"], m["psi0"], m["psiL"],
                      torch.tensor(2e-7), torch.tensor(2e-7), 2e-4, 2e-4)["J"]
g_fd = (Jp_.item() - Jm_.item()) / (2e-6)
rel2 = abs(g.item() - g_fd) / (abs(g_fd) + 1e-300)
print(f"  IFT dJ/dGs = {g.item():.4e}   FD = {g_fd:.4e}   rel err = {rel2:.3e}")
