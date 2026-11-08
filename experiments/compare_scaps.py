"""
Compare user-exported SCAPS-1D curves against the UniDD reference data.

Run:  python compare_scaps.py --scaps-dir <export_dir>
Out:  <export_dir>/scaps_comparison.png and scaps_comparison.md

Expected files in --scaps-dir (column names are matched fuzzily):
  dark_JV.csv    V_V, J_mA_cm2
  light_JV.csv   V_V, J_mA_cm2
  EQE.csv        lambda_nm, EQE
  generation_profile.csv  z_um, G_cm3_s   (optional)
  metadata.txt   (recommended; copied into the report)

Missing files are reported, not silently skipped.  This script does NOT claim
that a cross-validation has been performed: it only quantifies agreement once
the user has actually run SCAPS and exported its curves.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
# Source tree: this file sits next to scaps_reference/.  Release tree: it sits
# in experiments/ while scaps_reference/ is one level up.
ROOT = HERE if (HERE / "scaps_reference").is_dir() else HERE.parent
REF = ROOT / "scaps_reference"

ALIASES = {
    "V_V": ["V_V", "V", "v", "bias", "bias_v", "voltage", "voltage_v"],
    "J_mA_cm2": ["J_mA_cm2", "J", "j", "current", "current_density", "j_ma_cm2"],
    "lambda_nm": ["lambda_nm", "lambda", "wavelength", "wavelength_nm", "lam_nm"],
    "EQE": ["EQE", "eqe", "QE", "qe", "ipce"],
    "z_um": ["z_um", "z", "x", "x_um", "position_um"],
    "G_cm3_s": ["G_cm3_s", "g_coherent_cm3_s", "g_singlepass_cm3_s",
                "G", "g", "generation", "generation_cm3_s"],
}


def read_xy(path: Path, xkey: str, ykey: str):
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"{path.name}: no data rows")
    cols = {k.strip().lower(): k for k in rows[0].keys() if k}

    def pick(key):
        for a in ALIASES[key]:
            if a.lower() in cols:
                return cols[a.lower()]
        raise KeyError(f"{path.name}: no column for {key}; got {list(cols)}")

    cx, cy = pick(xkey), pick(ykey)
    x, y = [], []
    for r in rows:
        try:
            x.append(float(r[cx]))
            y.append(float(r[cy]))
        except (ValueError, TypeError):
            continue
    if len(x) < 2:
        raise ValueError(f"{path.name}: fewer than 2 numeric rows")
    order = np.argsort(x)
    return np.asarray(x)[order], np.asarray(y)[order]


def metrics(x, ref, got):
    m = np.isfinite(ref) & np.isfinite(got)
    x, ref, got = x[m], ref[m], got[m]
    if len(x) < 2:
        return {}
    d = got - ref
    denom = np.maximum(np.abs(ref), 1e-9)
    return {
        "n_points": int(len(x)),
        "rmse": float(np.sqrt(np.mean(d ** 2))),
        "mae": float(np.mean(np.abs(d))),
        "max_abs": float(np.max(np.abs(d))),
        "mean_rel_pct": float(100.0 * np.mean(np.abs(d) / denom)),
        "ref_range": [float(ref.min()), float(ref.max())],
        "scaps_range": [float(got.min()), float(got.max())],
    }


def crossing(v, j):
    for i in range(len(v) - 1):
        if j[i] * j[i + 1] <= 0 and j[i] != j[i + 1]:
            return float(v[i] - j[i] * (v[i + 1] - v[i]) / (j[i + 1] - j[i]))
    return None


def ff_from_jv(v, j):
    """Fill factor from a J-V curve, independent of the current sign convention."""
    voc = crossing(v, j)
    m = np.isfinite(v) & np.isfinite(j)
    v, j = np.asarray(v)[m], np.asarray(j)[m]
    if voc is None or len(v) < 3 or abs(j[0]) < 1e-12:
        return None
    pmax = float(np.max(np.abs(v * j)))
    denom = abs(j[0]) * abs(voc)
    return pmax / denom if denom > 0 else None


# Acceptance criteria are copied verbatim from SCAPS1D交叉验证方案.md §5.
# They were fixed BEFORE any SCAPS data existed and are NOT relaxed here.
# Dark J-V uses the absolute-error branch because the UniDD dark current is
# nearly zero and a relative error would be numerically meaningless.
ACCEPTANCE = {
    "dark J-V": "RMSE < 0.05 mA/cm2 OR mean rel. error < 5%",
    "light J-V": "Jsc < 5%, Voc < 20 mV, FF < 5%",
    "EQE": "RMSE < 0.05 (shape sanity check)",
    "generation profile": "RMSE / mean(UniDD G) < 2%",
}


def evaluate(results: dict) -> list[dict]:
    """Return one verdict row per pre-specified acceptance item."""
    rows = []

    def add(item, measured, threshold, ok, note=""):
        verdict = "N/A" if ok is None else ("PASS" if bool(ok) else "FAIL")
        rows.append({"item": item, "criterion": ACCEPTANCE.get(item, ""),
                     "measured": measured, "threshold": threshold,
                     "verdict": verdict, "note": note})

    r = results.get("dark J-V", {})
    if "rmse" in r:
        ok = (r["rmse"] < 0.05) or (r["mean_rel_pct"] < 5.0)
        add("dark J-V", f"RMSE {r['rmse']:.4g} mA/cm2; mean rel. {r['mean_rel_pct']:.2f}%",
            "RMSE < 0.05 mA/cm2 OR rel. < 5%", ok,
            "SCAPS metal contacts vs UniDD Dirichlet contacts are not identical")
    else:
        add("dark J-V", "no data", "-", None)

    r = results.get("light J-V", {})
    if "rmse" in r:
        jr, js = r.get("Jsc_ref_mA_cm2"), r.get("Jsc_scaps_mA_cm2")
        vr, vs = r.get("Voc_ref_V"), r.get("Voc_scaps_V")
        fr, fs = r.get("FF_ref"), r.get("FF_scaps")
        checks = []
        if jr and js is not None and abs(jr) > 1e-12:
            err = 100.0 * abs(js - jr) / abs(jr)
            checks.append((f"Jsc {err:.2f}%", err < 5.0))
        if vr and vs is not None:
            err = 1000.0 * abs(vs - vr)
            checks.append((f"Voc {err:.1f} mV", err < 20.0))
        if fr and fs is not None:
            err = 100.0 * abs(fs - fr) / abs(fr)
            checks.append((f"FF {err:.2f}%", err < 5.0))
        ok = bool(checks) and all(c[1] for c in checks)
        add("light J-V", "; ".join(c[0] for c in checks) or "no metrics",
            "Jsc < 5%; Voc < 20 mV; FF < 5%", ok if checks else None)
    else:
        add("light J-V", "no data", "-", None)

    r = results.get("EQE", {})
    if "rmse" in r:
        add("EQE", f"RMSE {r['rmse']:.4g}", "RMSE < 0.05", r["rmse"] < 0.05,
            "different optical models; shape only")
    else:
        add("EQE", "no data", "-", None)

    r = results.get("generation profile", {})
    if "rmse" in r:
        scale = np.mean(np.abs(r["ref_range"])) or 1.0
        rel = 100.0 * r["rmse"] / scale
        add("generation profile", f"RMSE/mean(ref) {rel:.2f}%", "< 2%", rel < 2.0,
            "checks unit conversion and G(x) interpolation")
    else:
        add("generation profile", "no data", "-", None)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scaps-dir", required=True)
    args = ap.parse_args()
    d = Path(args.scaps_dir)
    if not d.is_dir():
        raise SystemExit(f"not a directory: {d}")

    jobs = [
        ("dark J-V", "dark_JV.csv", "unidd_dark_JV.csv", "V_V", "J_mA_cm2",
         "V [V]", "J [mA/cm2]"),
        ("light J-V", "light_JV.csv", "unidd_light_JV_coherent.csv",
         "V_V", "J_mA_cm2", "V [V]", "J [mA/cm2]"),
        ("EQE", "EQE.csv", "unidd_EQE.csv", "lambda_nm", "EQE",
         "wavelength [nm]", "EQE"),
        ("generation profile", "generation_profile.csv",
         "unidd_generation_profile.csv", "z_um", "G_cm3_s",
         "z in absorber [um]", "G [cm-3 s-1]"),
    ]
    results, curves, missing = {}, [], []
    for label, scaps_name, ref_name, xk, yk, xl, yl in jobs:
        sp, rp = d / scaps_name, REF / ref_name
        if not sp.is_file():
            missing.append(scaps_name)
            continue
        if not rp.is_file():
            missing.append(f"[reference missing] {ref_name}")
            continue
        try:
            xr, yr = read_xy(rp, xk, yk)
            xs, ys = read_xy(sp, xk, yk)
        except Exception as e:
            results[label] = {"error": str(e)}
            continue
        # sign convention: flip if anti-correlated
        yi = np.interp(xr, xs, ys, left=np.nan, right=np.nan)
        valid = np.isfinite(yi)
        flipped = False
        if valid.sum() > 2 and np.corrcoef(yr[valid], yi[valid])[0, 1] < 0:
            yi, ys, flipped = -yi, -ys, True
        res = metrics(xr, yr, yi)
        res["sign_flipped"] = flipped
        if label in ("dark J-V", "light J-V"):
            res["Jsc_ref_mA_cm2"] = float(yr[0])
            res["Jsc_scaps_mA_cm2"] = float(yi[0]) if np.isfinite(yi[0]) else None
            res["Voc_ref_V"] = crossing(xr, yr)
            res["Voc_scaps_V"] = crossing(xr, yi)
            res["FF_ref"] = ff_from_jv(xr, yr)
            res["FF_scaps"] = ff_from_jv(xr, yi)
        results[label] = res
        curves.append((label, xr, yr, yi, xl, yl))

    verdicts = evaluate(results)
    all_pass = all(v["verdict"] == "PASS" for v in verdicts)

    # figure
    if curves:
        fig, axes = plt.subplots(len(curves), 1, figsize=(7.0, 2.5 * len(curves)))
        if len(curves) == 1:
            axes = [axes]
        for ax, (label, x, yr, yi, xl, yl) in zip(axes, curves):
            ax.plot(x, yr, "-", lw=2, label="UniDD", color="#1f4e79")
            ax.plot(x, yi, "--", lw=1.8, label="SCAPS-1D", color="#c0504d")
            ax.set_xlabel(xl)
            ax.set_ylabel(yl)
            ax.set_title(label)
            ax.grid(alpha=0.3)
            ax.legend(fontsize=9)
        fig.tight_layout()
        fig.savefig(d / "scaps_comparison.png", dpi=160)
        plt.close(fig)

    lines = ["# SCAPS-1D / UniDD 交叉验证比对报告", "",
             "本报告只量化**已导出数据**的一致性；在作者实际完成 SCAPS 运行之前，",
             "论文中「未做 SCAPS 交叉验证」的表述必须保留。", ""]
    meta = d / "metadata.txt"
    if meta.is_file():
        lines += ["## SCAPS 运行记录（作者提供）", "", "```",
                  meta.read_text(encoding="utf-8", errors="replace")[:2000], "```", ""]
    else:
        lines += ["## SCAPS 运行记录", "",
                  "`metadata.txt` 缺失：请补记 SCAPS 版本、算例文件、参数与收敛设置。", ""]
    lines += ["## 逐项误差", "", "| 量 | 点数 | RMSE | MAE | 最大偏差 | 平均相对误差 | 备注 |",
              "|---|---|---|---|---|---|---|"]
    for label in ("dark J-V", "light J-V", "EQE", "generation profile"):
        r = results.get(label)
        if r is None:
            lines.append(f"| {label} | — | — | — | — | — | 未提供 |")
        elif "error" in r:
            lines.append(f"| {label} | — | — | — | — | — | 读取失败: {r['error']} |")
        else:
            note = "符号已统一" if r.get("sign_flipped") else ""
            lines.append(
                f"| {label} | {r['n_points']} | {r['rmse']:.4g} | {r['mae']:.4g} | "
                f"{r['max_abs']:.4g} | {r['mean_rel_pct']:.2f}% | {note} |")
    lines += ["", "## 器件指标", ""]
    for label in ("dark J-V", "light J-V"):
        r = results.get(label, {})
        if "Jsc_ref_mA_cm2" in r:
            lines.append(f"- **{label}**：Jsc UniDD {r['Jsc_ref_mA_cm2']:.3f} / "
                         f"SCAPS {r['Jsc_scaps_mA_cm2']} mA/cm²；"
                         f"Voc UniDD {r['Voc_ref_V']} / SCAPS {r['Voc_scaps_V']} V")
    lines += ["", "## 预指定验收判定", "",
              "判据逐字取自 `SCAPS1D交叉验证方案.md` §5，在任何 SCAPS 数据产生之前固定，",
              "本脚本不会在看到数据后放宽阈值。暗态 J–V 采用绝对误差分支，因为 UniDD",
              "暗电流接近零，相对误差在数值上没有意义。", "",
              f"**总体结论：{'PASS（全部通过）' if all_pass else '未全部通过 / 数据不完整'}**", "",
              "| 项目 | 实测 | 阈值 | 判定 | 说明 |", "|---|---|---|---|---|"]
    for v in verdicts:
        lines.append(f"| {v['item']} | {v['measured']} | {v['threshold']} | "
                     f"**{v['verdict']}** | {v['note']} |")
    lines += ["", "- 暗态 J–V / Voc / FF 若不达标，须在论文中逐项归因（SCAPS 金属接触 + 表面复合速度",
              "  vs UniDD Dirichlet 载流子密度边界、网格离散、复合参数化），不得静默改阈值。",
              "- EQE 仅作形状 sanity check：UniDD 用相干 TMM，SCAPS 用 Beer–Lambert / 用户 G(x)。",
              "", "## 差异来源（超出阈值时逐条排查）", "",
              "网格密度与离散格式、接触边界与功函数、复合模型（UniDD 无界面/辐射/Auger）、",
              "光谱采样与归一化、串联电阻、收敛判据、电流符号、单位换算。", ""]
    if missing:
        lines += ["## 缺失文件", ""] + [f"- `{m}`" for m in missing] + [""]
    lines += ["---", "", "生成脚本：`compare_scaps.py`；参照数据：`scaps_reference/`。", ""]
    (d / "scaps_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    (d / "acceptance_verdict.json").write_text(
        json.dumps({"all_pass": all_pass, "criteria_fixed_before_data": True,
                    "verdicts": verdicts,
                    "generated": dt.datetime.now().isoformat(timespec="seconds")},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"report -> {d / 'scaps_comparison.md'}")
    print(f"verdict -> {d / 'acceptance_verdict.json'}  all_pass={all_pass}")
    if curves:
        print(f"figure -> {d / 'scaps_comparison.png'}")
    for label, r in results.items():
        print(f"  {label}: {r if 'error' in r else {k: r[k] for k in ('rmse','mean_rel_pct') if k in r}}")
    if missing:
        print("  missing:", ", ".join(missing))


if __name__ == "__main__":
    main()
