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
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
REF = ROOT / "scaps_reference"

ALIASES = {
    "V_V": ["V_V", "V", "v", "bias", "bias_v", "voltage", "voltage_v"],
    "J_mA_cm2": ["J_mA_cm2", "J", "j", "current", "current_density", "j_ma_cm2"],
    "lambda_nm": ["lambda_nm", "lambda", "wavelength", "wavelength_nm", "lam_nm"],
    "EQE": ["EQE", "eqe", "QE", "qe", "ipce"],
    "z_um": ["z_um", "z", "x", "x_um", "position_um"],
    "G_cm3_s": ["G_cm3_s", "G", "g", "generation", "generation_cm3_s"],
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
        results[label] = res
        curves.append((label, xr, yr, yi, xl, yl))

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
    lines += ["", "## 建议判据（供作者判断）", "",
              "- 暗态 J–V：逐点相对误差 <5%（或绝对误差 <0.05 mA/cm²）",
              "- 光照 Jsc <5%；Voc 差异 <20 mV；FF <5%",
              "- EQE 形状一致、RMSE <0.05；G(z) 剖面 RMSE <2%",
              "", "## 差异来源（超出阈值时逐条排查）", "",
              "网格密度与离散格式、接触边界与功函数、复合模型（UniDD 无界面/辐射/Auger）、",
              "光谱采样与归一化、串联电阻、收敛判据、电流符号、单位换算。", ""]
    if missing:
        lines += ["## 缺失文件", ""] + [f"- `{m}`" for m in missing] + [""]
    lines += ["---", "", "生成脚本：`compare_scaps.py`；参照数据：`scaps_reference/`。", ""]
    (d / "scaps_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"report -> {d / 'scaps_comparison.md'}")
    if curves:
        print(f"figure -> {d / 'scaps_comparison.png'}")
    for label, r in results.items():
        print(f"  {label}: {r if 'error' in r else {k: r[k] for k in ('rmse','mean_rel_pct') if k in r}}")
    if missing:
        print("  missing:", ", ".join(missing))


if __name__ == "__main__":
    main()
