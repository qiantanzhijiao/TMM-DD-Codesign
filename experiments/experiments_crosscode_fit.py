"""
Cross-code surrogate J-V/EQE fit (NOT experimental data).

PURPOSE
-------
Answer, as far as this machine honestly can, the request for "at least one
J-V/EQE fit".  There is NO measured device data here; SCAPS-1D is a simulator
and the .iv/.qe files shipped in its measurements/ folder are SCAPS
simulation outputs (their own headers say so).  What CAN be done on this
machine is a fit whose TARGET was produced by an independent code rather than
by UniDD itself.  That removes the pure "inverse crime" of E3/E4, where the
target and the forward model were the same, while remaining a synthetic,
cross-code exercise.

TARGET (external, produced by SCAPS 3.3.12, no UniDD involvement)
    * EQE(lambda) on six wavelengths, interpolated from
      scaps_run/export/EQE.csv (native SCAPS .qe export)
    * Jsc = J(0 V) from scaps_run/export/light_JV.csv (native SCAPS .iv export)
The full SCAPS J-V curve is deliberately NOT used: on this device SCAPS
returns an almost bias-independent current (32.06 -> 32.48 mA/cm2 over
0-1.06 V) with no Voc crossing, while UniDD returns a rectifying curve with
Voc ~ 1.11 V.  Fitting those two shapes against each other would be fitting
model incomparability, not physics.  The dark J-V is likewise saturated near
8e-9 mA/cm2.  Only Jsc, a well-defined single observable, enters the fit.

MODEL / OPTIMISER
    Same UniDD differentiable stack and same three-parameter inverse problem
    (absorber thickness d, extinction scale k, SRH lifetime tau) and the same
    L-BFGS with exact IFT gradients as E3/E4.  Nothing about the solver is
    changed.  Only the target vector is different.

PRE-SPECIFIED READ-OUT (no post-hoc success criteria)
    * the fit must reduce the weighted residual (loss_final < loss_start)
    * EQE RMSE and Jsc error before/after are reported
    * recovered (d, k, tau) are reported together with their bias against the
      UniDD truth used to generate the SCAPS inputs
    NO "parameter recovery succeeded" criterion is defined: the target comes
    from a different physical model, so recovering the UniDD truth is NOT
    expected.  A parameter bias is the anticipated signature of cross-code
    model misspecification, not a failure of the optimiser.

WHAT THIS DOES NOT ESTABLISH
    * not experimental validation, not calibration against a real device
    * not equivalence of UniDD and SCAPS
    * does not change the E4 "not met" verdict, the 16-D censored lower bound,
      or scaps_run/export/acceptance_verdict.json (2 PASS / 2 FAIL)

Run:  python experiments_crosscode_fit.py
Out:  results_crosscode_fit.json
      scaps_run/crosscode_fit/crosscode_fit.png
      scaps_run/crosscode_fit/README.md
"""
from __future__ import annotations

import datetime as dt
import json
import math
import time
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
# Source tree: experiments sit next to the soldiff package.  Release tree:
# experiments/ is one level below the repository root that contains soldiff/.
ROOT = HERE if (HERE / "soldiff").is_dir() else HERE.parent
import sys                                                   # noqa: E402
sys.path.insert(0, str(ROOT))
torch.set_default_dtype(torch.float64)
torch.manual_seed(0)

from soldiff.device import CoupledSolarCell, am15_flux        # noqa: E402

# Recorded results live beside the experiments in the source tree, but under
# results/ in the clean release repository (same convention as build_variants).
RES_DIR = HERE if (HERE / "results_final.json").is_file() else ROOT / "results"
EXP = ROOT / "scaps_run" / "export"
OUT = ROOT / "scaps_run" / "crosscode_fit"
RES = RES_DIR / "results_crosscode_fit.json"

# Same observation grid as the recorded E3/E4 inverse problem.
LAM_EQE = torch.linspace(420.0, 760.0, 6)
PHI_EQE = am15_flux(LAM_EQE)
DV = 0.05
D_TRUE, K_TRUE, TAU_TRUE = 480.0, 0.72, 3.0e-7


def read_xy(path: Path):
    a = np.genfromtxt(path, delimiter=",", skip_header=1)
    return a[:, 0], a[:, 1]


def nk_simple(k_amp, lams):
    k = k_amp * torch.exp(-torch.relu(lams - 800.0) / 60.0) + 1e-3
    return torch.complex(torch.full_like(lams, 2.55), k)


def decode(u):
    return (480.0 * u[0],
            torch.clamp(0.72 * u[1], 1e-3, 2.0),
            torch.exp(math.log(3e-7) * u[2]))


def main() -> int:
    for p in (EXP / "EQE.csv", EXP / "light_JV.csv"):
        if not p.is_file():
            raise SystemExit(f"missing native SCAPS export: {p}")
    lam_s, eqe_s = read_xy(EXP / "EQE.csv")
    v_s, j_s = read_xy(EXP / "light_JV.csv")

    # Interpolate the external target onto UniDD's recorded observation grid.
    eqe_target = torch.tensor(
        np.interp(LAM_EQE.numpy(), lam_s, eqe_s), dtype=torch.float64)
    jsc_target = float(np.interp(0.0, v_s, j_s))
    y_target = torch.cat([eqe_target / 0.9,
                          torch.tensor([jsc_target / 30.0], dtype=torch.float64)])

    cell = CoupledSolarCell(N_dd=73)

    def observables(u, grad: bool = False):
        d, k, tau = decode(u)
        with torch.enable_grad() if grad else torch.no_grad():
            eqe = cell.eqe_curve(d, nk_simple(k, LAM_EQE), tau,
                                 lam_eqe=LAM_EQE, phi_eqe=PHI_EQE, ift=grad)
            jsc = cell.jv(d, nk_simple(k, cell.lam), tau, [0.0],
                          ift=grad, dV=DV)[0]
        return torch.cat([eqe / 0.9, (jsc / 30.0).reshape(1)])

    def loss_of(u, grad=False):
        return ((observables(u, grad) - y_target) ** 2).mean()

    u_star = torch.tensor([1.0, 1.0, 1.0])
    u_init = torch.tensor([300.0 / 480.0, 0.35 / 0.72,
                           math.log(1.5e-6) / math.log(3e-7)])

    print("target: SCAPS 3.3.12 native exports (NOT measured data)")
    print(f"  Jsc target       = {jsc_target:.6f} mA/cm2")
    print(f"  EQE target (6)   = {np.round(eqe_target.numpy(), 5).tolist()}")
    t0 = time.time()
    with torch.no_grad():
        y0 = observables(u_star)
        y_init = observables(u_init)
    loss_star = float(((y0 - y_target) ** 2).mean())
    loss_start = float(((y_init - y_target) ** 2).mean())
    print(f"  loss at UniDD truth = {loss_star:.6e}")
    print(f"  loss at E3 start    = {loss_start:.6e}")

    u = u_init.clone().requires_grad_(True)
    opt = torch.optim.LBFGS([u], lr=0.5, max_iter=40, max_eval=100,
                            tolerance_grad=1e-12, tolerance_change=1e-14,
                            history_size=25, line_search_fn="strong_wolfe")
    hist = []
    counter = {"n": 0}

    def closure():
        opt.zero_grad()
        loss = loss_of(u, grad=True)
        loss.backward()
        counter["n"] += 1
        hist.append([counter["n"], float(loss.detach())])
        if counter["n"] % 10 == 0:
            print(f"    eval {counter['n']:3d}  loss {float(loss.detach()):.6e} "
                  f"({time.time() - t0:.0f}s)", flush=True)
        return loss

    opt.step(closure)
    u_opt = u.detach()
    loss_final = float(loss_of(u_opt))
    wall = time.time() - t0

    with torch.no_grad():
        y_final = observables(u_opt)
    d, k, tau = decode(u_opt)

    def split(y):
        return y[:6] * 0.9, float(y[6] * 30.0)

    eqe_star, jsc_star = split(y0)
    eqe_final, jsc_final = split(y_final)
    eqe_rmse = lambda a: float(torch.sqrt(((a - eqe_target) ** 2).mean()))
    rmse_before, rmse_after = eqe_rmse(eqe_star), eqe_rmse(eqe_final)

    err_d = abs(float(d) - D_TRUE) / D_TRUE
    err_k = abs(float(k) - K_TRUE) / K_TRUE
    err_t = abs(math.log(float(tau) / TAU_TRUE))

    result = {
        "experiment": "cross-code surrogate J-V/EQE fit",
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "NOT_experimental_data": True,
        "NOT_experimental_validation": True,
        "NOT_parameter_recovery_test": True,
        "target": {
            "source": "SCAPS 3.3.12 native .iv/.qe exports, scaps_run/export/",
            "files": ["EQE.csv", "light_JV.csv"],
            "jsc_mA_cm2": jsc_target,
            "eqe_wavelengths_nm": LAM_EQE.tolist(),
            "eqe_values": eqe_target.tolist(),
            "eqe_interpolated_from_scaps_grid": True,
            "full_JV_excluded_reason": (
                "SCAPS illuminated J-V is bias-independent on this device "
                "(32.06 -> 32.48 mA/cm2 over 0-1.06 V, no Voc crossing) and "
                "the SCAPS dark J-V saturates near 8e-9 mA/cm2; neither is "
                "commensurate with the UniDD rectifying J-V. Only Jsc is used."),
            "target_produced_by_UniDD": False,
        },
        "model": {
            "solver": "UniDD CoupledSolarCell, N_dd=73, float64",
            "inverse_variables": ["absorber thickness d (nm)",
                                  "extinction scale k", "SRH lifetime tau (s)"],
            "optimiser": "L-BFGS, exact IFT gradients, max_iter=40, max_eval=100",
            "observation_grid": {"eqe_nm": LAM_EQE.tolist(), "V_for_Jsc": 0.0},
            "weights": "EQE/0.9 and Jsc/30, equal weight, mean squared residual",
        },
        "pre_specified_readout": {
            "criteria": ["loss_final < loss_start", "EQE RMSE after < before"],
            "criteria_fixed_before_run": True,
            "no_parameter_recovery_criterion": True,
        },
        "baseline": {
            "loss_at_UniDD_truth": loss_star,
            "loss_at_E3_start": loss_start,
            "eqe_rmse_at_UniDD_truth": rmse_before,
            "jsc_at_UniDD_truth_mA_cm2": jsc_star,
            "jsc_rel_error_at_truth_pct": 100.0 * abs(jsc_star - jsc_target)
                                          / abs(jsc_target),
        },
        "fit": {
            "loss_final": loss_final,
            "evaluations": len(hist),
            "wall_clock_s": wall,
            "eqe_rmse_after": rmse_after,
            "jsc_after_mA_cm2": jsc_final,
            "jsc_rel_error_after_pct": 100.0 * abs(jsc_final - jsc_target)
                                       / abs(jsc_target),
            "history": hist,
        },
        "recovered": {
            "d_nm": float(d), "k": float(k), "tau_s": float(tau),
            "rel_err_d": err_d, "rel_err_k": err_k, "abs_dlog_tau": err_t,
            "truth": {"d_nm": D_TRUE, "k": K_TRUE, "tau_s": TAU_TRUE},
        },
        "curves": {
            "scaps_eqe_lambda_nm": lam_s.tolist(),
            "scaps_eqe": eqe_s.tolist(),
            "eqe_grid_nm": LAM_EQE.tolist(),
            "unidd_truth_eqe": eqe_star.tolist(),
            "unidd_fit_eqe": eqe_final.tolist(),
            "scaps_full_light_JV": {"V_V": v_s.tolist(), "J_mA_cm2": j_s.tolist()},
        },
        "verdict": {
            "fit_reduces_residual": bool(loss_final < loss_start),
            "eqe_rmse_improves": bool(rmse_after < rmse_before),
            "unchanged": ["E4 not met", "16-D censored lower bound",
                          "SCAPS 2 PASS / 2 FAIL, all_pass=false"],
        },
    }
    RES.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        make_figure(result)
    except Exception as e:                                    # noqa: BLE001
        print(f"figure skipped: {e}")
    write_readme(result)

    print(f"\nfit: {len(hist)} evals, {wall:.1f}s, "
          f"loss {loss_start:.3e} -> {loss_final:.3e}")
    print(f"  EQE RMSE {rmse_before:.5f} -> {rmse_after:.5f}")
    print(f"  Jsc {jsc_star:.3f} -> {jsc_final:.3f} (target {jsc_target:.3f})")
    print(f"  recovered d={float(d):.2f} nm ({100*err_d:.2f}% bias), "
          f"k={float(k):.4f} ({100*err_k:.2f}%), |dlog tau|={err_t:.4f}")
    print(f"outputs -> {RES}, {OUT}")
    return 0


def make_figure(r: dict) -> None:
    """Render in a CHILD process; see render_crosscode_fit.py.

    Importing matplotlib in this process (which already holds torch + Anaconda
    MKL) aborts on Windows with ``OMP: Error #15: ... libiomp5md.dll already
    initialized`` -- AFTER the numerical fit has finished.  The child imports
    no torch, so only one OpenMP runtime is ever initialised.
    """
    import subprocess
    import sys
    renderer = HERE / "render_crosscode_fit.py"
    p = subprocess.run([sys.executable, str(renderer), str(RES), str(OUT)],
                       capture_output=True, text=True)
    if p.returncode != 0:
        print("renderer failed:", p.stdout.strip(), p.stderr.strip())
    elif p.stdout.strip():
        print(p.stdout.strip())


def write_readme(r: dict) -> None:
    v = r["verdict"]
    L = [
        "# 跨代码 surrogate J–V/EQE 拟合（非实测）", "",
        f"生成时间：{r['generated']}", "",
        "> **本目录所有曲线都是仿真数据。** Target 由 SCAPS 3.3.12 生成，"
        "拟合器是 UniDD；没有使用、也没有生成任何实测器件数据。",
        "> 不得在论文中写成 experimental validation / measured fit / device calibration。", "",
        "## 做了什么", "",
        "用 UniDD 的可微求解器（N=73、IFT 梯度、L-BFGS，与 E3/E4 完全相同的设置），"
        "对一组**由外部代码 SCAPS 3.3.12 生成**的观测量做三参数反演：", "",
        f"- EQE(λ) 六点，插值自 `scaps_run/export/EQE.csv`；",
        f"- Jsc = J(0 V) = {r['target']['jsc_mA_cm2']:.4f} mA/cm²，"
        "取自 `scaps_run/export/light_JV.csv`。", "",
        "相对 E3/E4 的改进：target 不再由 UniDD 自己生成，因此不是纯粹的 "
        "inverse crime。但这仍是**仿真对仿真**的跨代码练习。", "",
        "## 为什么没有用整条 J–V 曲线", "",
        r["target"]["full_JV_excluded_reason"], "",
        "UniDD 在同一器件上给出 Voc ≈ 1.11 V 的整流曲线，SCAPS 的光照 J–V "
        "在收敛区间内几乎不随偏压变化且没有 Voc 交叉；暗态 J–V 饱和在 "
        "8×10⁻⁹ mA/cm²。把两条不同构的曲线做最小二乘拟合，拟合的是模型"
        "不可比性而不是物理，因此只保留物理定义明确、两边都存在的 Jsc 标量。", "",
        "## 结果", "",
        "| 量 | 拟合前（UniDD 真值参数） | 拟合后 |", "|--|--|--|",
        f"| 加权残差 loss | {r['baseline']['loss_at_UniDD_truth']:.4e} | "
        f"{r['fit']['loss_final']:.4e} |",
        f"| EQE RMSE | {r['baseline']['eqe_rmse_at_UniDD_truth']:.5f} | "
        f"{r['fit']['eqe_rmse_after']:.5f} |",
        f"| Jsc (mA/cm²) | {r['baseline']['jsc_at_UniDD_truth_mA_cm2']:.3f} | "
        f"{r['fit']['jsc_after_mA_cm2']:.3f} |",
        f"| Jsc 相对误差 | {r['baseline']['jsc_rel_error_at_truth_pct']:.2f}% | "
        f"{r['fit']['jsc_rel_error_after_pct']:.2f}% |", "",
        f"L-BFGS  evaluations {r['fit']['evaluations']}，"
        f"耗时 {r['fit']['wall_clock_s']:.1f} s。", "",
        "恢复参数（对照 UniDD 生成 SCAPS 输入时用的真值）：", "",
        f"- d = {r['recovered']['d_nm']:.2f} nm "
        f"（真值 {r['recovered']['truth']['d_nm']}，偏倚 "
        f"{100*r['recovered']['rel_err_d']:.2f}%）",
        f"- k = {r['recovered']['k']:.4f} "
        f"（真值 {r['recovered']['truth']['k']}，偏倚 "
        f"{100*r['recovered']['rel_err_k']:.2f}%）",
        f"- τ = {r['recovered']['tau_s']:.3e} s，"
        f"|Δlog τ| = {r['recovered']['abs_dlog_tau']:.4f}", "",
        f"预指定读出：残差下降 `{v['fit_reduces_residual']}`；"
        f"EQE RMSE 改善 `{v['eqe_rmse_improves']}`。"
        "**未设「参数恢复成功」判据**：target 来自不同物理模型，"
        "恢复出真值不是预期结果；参数偏倚正是跨代码模型失配的signature。", "",
        "### 关键解读：残差下降不等于校准成功", "",
        f"总残差下降几乎全部来自 EQE 形状（RMSE "
        f"{r['baseline']['eqe_rmse_at_UniDD_truth']:.4f} → "
        f"{r['fit']['eqe_rmse_after']:.4f}），而 Jsc 的相对误差反而由 "
        f"{r['baseline']['jsc_rel_error_at_truth_pct']:.2f}% 升到 "
        f"{r['fit']['jsc_rel_error_after_pct']:.2f}%。优化器在两类观测量之间"
        "做了折中：调 (d, k, τ) 可以让 EQE 更贴近 SCAPS，却无法同时把 Jsc "
        f"拉到 {r['target']['jsc_mA_cm2']:.2f} mA/cm²。这是跨代码模型失配"
        "**无法通过调参消除**的直接证据。若把这类拟合写成\"器件校准\"，"
        "会得到一组物理上明显错误（τ 偏离约三个数量级）却\"看起来拟合更好\""
        "的参数，属于典型的把仿真对仿真包装成实验验证。", "",
        "## 不改变的既有结论", "",
        "- E4 加速比目标 `not met`；16-D 删失下界不变；",
        "- `scaps_run/export/acceptance_verdict.json` 的 "
        "`2 PASS / 2 FAIL, all_pass=false` 不变；",
        "- 论文中 `no experimental calibration` / `limited cross-code sanity "
        "check` 的措辞不变。", "",
        "## 若要在论文中引用（措辞建议，需你确认后再改稿）", "",
        "> \"As an additional synthetic check, we replaced the self-generated "
        "target of the inverse problem with observables produced by an "
        "independent drift–diffusion code (SCAPS-1D 3.3.12). The fit reduces "
        "the observable residual but returns biased parameters, quantifying "
        "the model mismatch between the two codes. This is a cross-code "
        "consistency exercise, not calibration against measured data.\"", "",
        "注意：这只是措辞建议，**本轮未改动两版稿件**，是否纳入由你决定。", "",
    ]
    (OUT / "README.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
