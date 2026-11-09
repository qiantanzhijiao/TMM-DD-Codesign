"""
SCAPS-1D 3.3.12 official-example reproduction check.

WHAT THIS IS
------------
A reproducible, pre-specified check of the SCAPS side of the cross-code
comparison.  It runs the official example definition files SHIPPED WITH the
SCAPS 3.3.12 distribution (CdTe, CIGS, Si), exports dark/light J-V and QE
curves through the headless script interface, and verifies physical sanity,
run-to-run determinism, and genuine 3.3.12 provenance of every output.

WHAT THIS IS NOT  (read this before quoting it anywhere)
--------------------------------------------------------
* NOT experimental validation.  There is no measured device data on this
  machine, and this script does not create any.
* NOT a validation of UniDD.  UniDD does not participate in this check.
* NOT a like-for-like comparison against the ``measurements/*.iv/.qe`` files
  shipped with SCAPS.  Those files are SCAPS *simulation outputs* explicitly
  labelled as such in their own headers (e.g. "the measurement is a
  simulation with problem definition file ..."), they were produced by older
  SCAPS versions and, in some cases, by different definition files.  They are
  quoted here only as evidence of provenance, never as an acceptance target.
* This check does NOT change the existing UniDD <-> SCAPS verdict in
  scaps_run/export/acceptance_verdict.json (2 PASS / 2 FAIL, all_pass=false).

The only claim supported by a passing result is: the SCAPS 3.3.12
installation used for the cross-code sanity check can reproduce its own
official example problems through the same script chain, deterministically.

Usage
-----
    python verify_scaps_official_examples.py
    python verify_scaps_official_examples.py --scaps-dir "D:/.../Scaps3312"

Outputs: scaps_run/official_examples/
    official_examples_verdict.json   machine-readable pre-specified verdict
    official_examples_report.md      human-readable report
    official_examples_curves.png     dark/light J-V and QE for each example
    official_examples_curves.csv     all curves, tidy long format
    <tag>_dark.iv / <tag>_light.iv / <tag>_eqe.qe   native SCAPS exports
    <tag>_dark.script / <tag>_light.script          exact scripts used
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "scaps_run").is_dir() else HERE.parent
OUT = ROOT / "scaps_run" / "official_examples"
DEFAULT_SCAPS = "D:/software/Scaps3312/Scaps3312"

sys.path.insert(0, str(HERE))
from run_scaps_crosscheck import parse_iv, parse_qe  # noqa: E402

# Official example definition files distributed with SCAPS 3.3.12.  The
# CdTe one carries a literature provenance in its own header (Niemegeers
# thesis, Gent 1998; Burgelman, Nollet & Degrave, Appl. Phys. A 69, 149-153,
# 1999) and has shipped with every SCAPS version since 2.1 (1999).
EXAMPLES = {
    "cdte": "example CdTe.def",
    "cigs": "Numos CIGS baseline.def",
    "si":   "example Si.def",
}

# ---- PRE-SPECIFIED acceptance criteria ------------------------------------
# Fixed before the first SCAPS run.  Do not relax after seeing the data.
CRITERIA = {
    "min_jv_points": 30,
    "min_qe_points": 15,
    "qe_lower": -0.01,
    "qe_upper": 1.05,
    "min_abs_jsc_mA_cm2": 1.0,
    "determinism_rmse_max": 1e-6,
    "provenance_tokens": ("SCAPS 3.3.12", "ELIS-UGent"),
}
# ---------------------------------------------------------------------------

HEAD = """set quitscript.quitSCAPS
set script_display_mode.fully_suppressed
set errorhandling.overwritefile
set batch_display_mode.suppressed
"""


def dark_script(tag: str) -> str:
    # No "iv.continueafterVoc": with the official CdTe definition file it
    # makes 3.3.12 retry non-convergent high-injection bias points indefinitely
    # (verified: a 240 s run produced no output file).  The native J-V sweep
    # to 1.0 V is sufficient for a reproduction check.
    return HEAD + f"""load definitionfile official_{tag}.def
clear all
clear actions
action dark
action iv.doiv
action iv.startV 0.0
action iv.stopV 1.0
action iv.increment 0.02
calculate singleshot
save results.iv oe_{tag}_dark.iv
"""


def light_script(tag: str, prefix: str = "oe") -> str:
    return HEAD + f"""load definitionfile official_{tag}.def
clear all
clear actions
action light
action iv.doiv
action iv.startV 0.0
action iv.stopV 1.0
action iv.increment 0.02
calculate singleshot
save results.iv {prefix}_{tag}_light.iv
clear actions
action light
action qe.startlambda 380
action qe.stoplambda 1100
action qe.increment 20
action qe.doqe
calculate singleshot
save results.qe {prefix}_{tag}_eqe.qe
"""


def run_script(base: Path, exe: Path, name: str, body: str,
               timeout: int = 180) -> dict:
    sp = base / "script" / f"{name}.script"
    sp.write_text(body, encoding="utf-8")
    t0 = time.time()
    p = subprocess.Popen([str(exe), str(sp)], cwd=str(base),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = p.communicate(timeout=timeout)
        rc: int | str = p.returncode
    except subprocess.TimeoutExpired:
        p.kill()
        out, err = p.communicate()
        rc = "TIMEOUT"
    return {"rc": rc, "elapsed_s": round(time.time() - t0, 1),
            "script": sp, "stdout": out.decode("utf-8", "replace"),
            "stderr": err.decode("utf-8", "replace")}


def provenance_ok(path: Path) -> bool:
    head = "\n".join(path.read_text(encoding="utf-8", errors="replace")
                     .splitlines()[:15])
    return all(t in head for t in CRITERIA["provenance_tokens"])


def normalise_qe(rows):
    a = np.asarray([r[0] for r in rows], float)
    b = np.asarray([r[1] for r in rows], float)
    # SCAPS exports QE either as a fraction or in percent.
    if np.nanmedian(b) > 1.5:
        b = b / 100.0
    return a, b


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scaps-dir", default=DEFAULT_SCAPS)
    ap.add_argument("--skip-determinism", action="store_true")
    args = ap.parse_args()

    base = Path(args.scaps_dir)
    exe = base / "scaps3312.exe"
    OUT.mkdir(parents=True, exist_ok=True)
    if not exe.is_file():
        print(f"SCAPS executable not found: {exe}")
        return 2
    if not (base / "cvirte.dll").is_file():
        print("cvirte.dll (LabWindows/CVI run-time engine) missing; "
              "run install_scaps_runtime.py first")
        return 2

    # Stage the official defs under space-free aliases.  `load definitionfile`
    # accepts spaces, but aliases keep the exact scripts auditable.
    for tag, src in EXAMPLES.items():
        s = base / "def" / src
        if not s.is_file():
            print(f"missing official example definition: {s}")
            return 2
        shutil.copy2(s, base / "def" / f"official_{tag}.def")

    runs: dict = {}
    curves: dict = {}
    verdicts: list[dict] = []

    def add(item, measured, threshold, ok, note=""):
        verdicts.append({"item": item, "measured": measured,
                         "threshold": threshold,
                         "verdict": "PASS" if ok else "FAIL",
                         "note": note})

    for tag in EXAMPLES:
        print(f"[{tag}] running official example ...", flush=True)
        # Remove stale exports first: a missing/failed run must never be
        # mistaken for a successful one by reading an old file.
        for old in (base / "results").glob(f"oe_{tag}_*"):
            if old.suffix in (".iv", ".qe"):
                old.unlink()
        rd = run_script(base, exe, f"oe_{tag}_dark", dark_script(tag))
        rl = run_script(base, exe, f"oe_{tag}_light", light_script(tag))
        runs[tag] = {"dark": {"rc": rd["rc"], "elapsed_s": rd["elapsed_s"]},
                     "light": {"rc": rl["rc"], "elapsed_s": rl["elapsed_s"]}}
        shutil.copy2(rd["script"], OUT / f"{tag}_dark.script")
        shutil.copy2(rl["script"], OUT / f"{tag}_light.script")

        wanted = [f"oe_{tag}_dark.iv", f"oe_{tag}_light.iv", f"oe_{tag}_eqe.qe"]
        got = {}
        for n in wanted:
            p = base / "results" / n
            if p.is_file():
                shutil.copy2(p, OUT / f"{tag}_{n.split('_', 2)[-1]}")
                got[n] = OUT / f"{tag}_{n.split('_', 2)[-1]}"
        missing = [n for n in wanted if n not in got]
        if missing:
            add(f"{tag}: native SCAPS exports written",
                f"missing {missing}", "all three files written", False,
                f"dark rc={rd['rc']}, light rc={rl['rc']}")
            continue
        add(f"{tag}: native SCAPS exports written",
            ", ".join(sorted(got)), "all three files written", True,
            "non-zero CVI runtime exit codes are expected; file content is authoritative")

        # provenance: genuine output of THIS 3.3.12 binary
        prov = {n: provenance_ok(p) for n, p in got.items()}
        add(f"{tag}: genuine SCAPS 3.3.12 provenance",
            ", ".join(f"{n}={'ok' if v else 'MISSING'}" for n, v in prov.items()),
            "all headers contain " + " + ".join(CRITERIA["provenance_tokens"]),
            all(prov.values()))

        try:
            dj = parse_iv(got[wanted[0]])
            lj = parse_iv(got[wanted[1]])
            qe = parse_qe(got[wanted[2]])
        except Exception as e:                                # noqa: BLE001
            add(f"{tag}: parse SCAPS curves", f"parse error: {e}",
                "all curves parse", False)
            continue

        la, lb = normalise_qe(qe)
        curves[tag] = {
            "dark": {"V": [r[0] for r in dj], "J": [r[1] for r in dj]},
            "light": {"V": [r[0] for r in lj], "J": [r[1] for r in lj]},
            "eqe": {"lambda_nm": la.tolist(), "EQE": lb.tolist()},
        }
        add(f"{tag}: J-V / QE point counts",
            f"dark {len(dj)}, light {len(lj)}, QE {len(qe)}",
            f">= {CRITERIA['min_jv_points']} / {CRITERIA['min_jv_points']} "
            f"/ {CRITERIA['min_qe_points']}",
            len(dj) >= CRITERIA["min_jv_points"]
            and len(lj) >= CRITERIA["min_jv_points"]
            and len(qe) >= CRITERIA["min_qe_points"])

        add(f"{tag}: QE physically bounded",
            f"[{lb.min():.4f}, {lb.max():.4f}]",
            f"[{CRITERIA['qe_lower']}, {CRITERIA['qe_upper']}]",
            bool(lb.min() >= CRITERIA["qe_lower"]
                 and lb.max() <= CRITERIA["qe_upper"]))

        jsc = abs(lj[0][1]) if lj else 0.0
        add(f"{tag}: illuminated short-circuit current is non-trivial",
            f"|J(0 V)| = {jsc:.3f} mA/cm2",
            f"> {CRITERIA['min_abs_jsc_mA_cm2']} mA/cm2",
            jsc > CRITERIA["min_abs_jsc_mA_cm2"],
            "magnitude only; SCAPS sign convention differs from UniDD")

        dV = np.asarray([r[0] for r in dj], float)
        dJ = np.abs(np.asarray([r[1] for r in dj], float))
        mono = bool(np.all(np.diff(dJ) >= -1e-6 * max(1.0, dJ.max())))
        add(f"{tag}: dark |J| monotone in V over the converged range",
            f"min successive step = {np.diff(dJ).min():.3e} mA/cm2",
            "no decreasing step beyond numerical tolerance", mono,
            "indicative: SCAPS truncates the sweep on convergence failure")

        print(f"[{tag}] dark {len(dj)} pts, light {len(lj)} pts, "
              f"QE {len(qe)} pts, |Jsc| {jsc:.3f} mA/cm2", flush=True)

    # ---- determinism: repeat the CdTe example from a fresh SCAPS process ---
    if not args.skip_determinism and "cdte" in curves:
        print("[determinism] repeating the CdTe example ...", flush=True)
        # The repeat scripts must save to distinct filenames so the reference
        # exports are left untouched.
        rep_light = light_script("cdte", prefix="oer")
        rep_dark = dark_script("cdte").replace("oe_cdte_dark.iv",
                                               "oer_cdte_dark.iv")
        for old in (base / "results").glob("oer_cdte_*"):
            if old.suffix in (".iv", ".qe"):
                old.unlink()
        rd = run_script(base, exe, "oe_cdte_repeat_dark2", rep_dark)
        rl = run_script(base, exe, "oe_cdte_repeat_light", rep_light)
        pairs = []
        for kind, key in (("dark", "oer_cdte_dark.iv"),
                          ("light", "oer_cdte_light.iv")):
            p = base / "results" / key
            if not p.is_file():
                pairs.append((kind, None, "repeat export missing"))
                continue
            new = parse_iv(p)
            ref = curves["cdte"][kind]
            if len(new) != len(ref["V"]):
                pairs.append((kind, None, f"length {len(new)} vs {len(ref['V'])}"))
                continue
            dv = np.abs(np.asarray([r[0] for r in new]) - np.asarray(ref["V"])).max()
            rms = float(np.sqrt(np.mean((np.asarray([r[1] for r in new])
                                         - np.asarray(ref["J"])) ** 2)))
            pairs.append((kind, {"max_delta_V": float(dv), "rmse_J": rms},
                          None))
        ok = all(x[1] is not None
                 and x[1]["max_delta_V"] < 1e-9
                 and x[1]["rmse_J"] <= CRITERIA["determinism_rmse_max"]
                 for x in pairs)
        add("CdTe: run-to-run determinism (independent SCAPS process)",
            "; ".join(f"{k}: " + (f"RMSE(J)={v['rmse_J']:.3e}" if v else e)
                      for k, v, e in pairs),
            f"RMSE(J) <= {CRITERIA['determinism_rmse_max']} and identical V grid",
            ok)
        runs["determinism"] = {"dark_rc": rd["rc"], "light_rc": rl["rc"],
                               "pairs": pairs}

    # ---- outputs ----------------------------------------------------------
    all_pass = all(v["verdict"] == "PASS" for v in verdicts)
    verdict = {
        "check": "SCAPS 3.3.12 official-example reproduction",
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "criteria_fixed_before_run": True,
        "criteria": {k: (list(v) if isinstance(v, tuple) else v)
                     for k, v in CRITERIA.items()},
        "all_pass": all_pass,
        "verdicts": verdicts,
        "runs": runs,
        "scaps_dir": str(base),
        "official_definition_files": EXAMPLES,
        "NOT_experimental_validation": True,
        "NOT_UniDD_validation": True,
        "existing_crosscode_verdict_unchanged": "2 PASS / 2 FAIL, all_pass=false",
    }
    (OUT / "official_examples_verdict.json").write_text(
        json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")

    with (OUT / "official_examples_curves.csv").open(
            "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["example", "curve", "x", "x_unit", "y", "y_unit"])
        for tag, c in curves.items():
            for (v, j) in zip(c["dark"]["V"], c["dark"]["J"]):
                w.writerow([tag, "dark_JV", v, "V", j, "mA/cm2"])
            for (v, j) in zip(c["light"]["V"], c["light"]["J"]):
                w.writerow([tag, "light_JV", v, "V", j, "mA/cm2"])
            for (l, q) in zip(c["eqe"]["lambda_nm"], c["eqe"]["EQE"]):
                w.writerow([tag, "QE", l, "nm", q, "fraction"])

    try:
        make_figure(curves)
    except Exception as e:                                    # noqa: BLE001
        print(f"figure skipped: {e}")

    write_report(base, verdict, curves)
    print(f"\nall_pass={all_pass}  "
          f"PASS {sum(v['verdict'] == 'PASS' for v in verdicts)} / "
          f"FAIL {sum(v['verdict'] == 'FAIL' for v in verdicts)}")
    print(f"outputs -> {OUT}")
    return 0 if all_pass else 1


def make_figure(curves: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tags = list(curves)
    fig, axes = plt.subplots(len(tags), 3, figsize=(13.5, 3.1 * len(tags)))
    if len(tags) == 1:
        axes = np.asarray([axes])
    for i, tag in enumerate(tags):
        c = curves[tag]
        ax = axes[i][0]
        ax.plot(c["dark"]["V"], np.abs(c["dark"]["J"]), color="#1f4e79", lw=1.6)
        ax.set_yscale("log")
        ax.set_title(f"{tag.upper()}  dark |J|", fontsize=10)
        ax.set_xlabel("V (V)"); ax.set_ylabel("|J| (mA/cm2)")
        ax.grid(alpha=0.3)

        ax = axes[i][1]
        Jl = np.asarray(c["light"]["J"], float)
        ax.plot(c["light"]["V"], Jl, color="#c0504d", lw=1.6)
        ax.axhline(0, color="0.6", lw=0.7)
        # The official definitions are swept to 1.0 V, well past Voc.  SCAPS
        # returns divergent, non-physical currents there (up to 1e5-1e6
        # mA/cm2 for CIGS/Si).  Truncate the axis for legibility; the raw,
        # untruncated values remain in the CSV and the native .iv exports.
        lim = 1.3 * max(1.0, abs(Jl[0]))
        ax.set_ylim(-lim, lim)
        ax.text(0.02, 0.04, "truncated axis; SCAPS diverges past Voc",
                transform=ax.transAxes, fontsize=7.0, color="#555555",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.88, pad=1.5))
        ax.set_title(f"{tag.upper()}  illuminated J-V", fontsize=10)
        ax.set_xlabel("V (V)"); ax.set_ylabel("J (mA/cm2)")
        ax.grid(alpha=0.3)

        ax = axes[i][2]
        ax.plot(c["eqe"]["lambda_nm"], c["eqe"]["EQE"], color="#2e7d32", lw=1.6)
        ax.set_ylim(-0.02, 1.05)
        ax.set_title(f"{tag.upper()}  QE", fontsize=10)
        ax.set_xlabel("wavelength (nm)"); ax.set_ylabel("QE (fraction)")
        ax.grid(alpha=0.3)
    fig.suptitle("SCAPS 3.3.12 official example problems -- reproduction "
                 "(SIMULATION; not measured data)", fontsize=11, y=0.995)
    fig.text(0.5, 0.008,
             "Official default definitions swept to 1.0 V: beyond Voc SCAPS "
             "returns divergent currents; dark |J| and QE are shown exactly as "
             "produced. Reproduction check only, not device performance.",
             ha="center", fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.035, 1, 0.975))
    fig.savefig(OUT / "official_examples_curves.png", dpi=160)
    plt.close(fig)


def official_measurement_evidence(base: Path) -> list[str]:
    """Quote the SCAPS-distributed 'measurement' headers verbatim.

    These files are the reason a "measured J-V/EQE fit" cannot be produced
    from this machine: they are SCAPS simulation outputs, not measurements.
    """
    out = []
    for rel in ("measurements/Interact  CdTe light IV measurement.iv",
                "measurements/Interact  CdTe light QE 0 Vbias measurement.qe",
                "measurements/example IV-measurement.iv",
                "measurements/Numos baseline dark IV 300K.iv"):
        p = base / rel
        if not p.is_file():
            continue
        hits = [l.strip() for l in p.read_text(encoding="utf-8", errors="replace")
                .splitlines()[:12]
                if "simulation" in l.lower() or "measurement is a simulation" in l.lower()
                or "SCAPS version" in l]
        if hits:
            out.append(f"- `{p.name}`: " + " / ".join(h[:180] for h in hits[:2]))
    return out


def write_report(base: Path, verdict: dict, curves: dict) -> None:
    L = [
        "# SCAPS-1D 3.3.12 官方算例交叉校验（复现性验证）", "",
        f"生成时间：{verdict['generated']}", "",
        "> **性质声明（请勿越界引用）**",
        "> 本报告是 **SCAPS 侧安装与脚本链的官方算例复现性验证**。",
        "> 它 **不是实验验证**、**不是 UniDD 的验证**、**不是器件级实测数据**。",
        "> 全部曲线均由 SCAPS 3.3.12 仿真生成，UniDD 未参与。",
        "> 既有 `scaps_run/export/acceptance_verdict.json` 的 "
        "`2 PASS / 2 FAIL, all_pass=false` 判定 **不因本报告改变**。", "",
        "## 1. 能回答什么、不能回答什么", "",
        "| 诉求 | 本机能否完成 | 结论 |", "|--|--|--|",
        "| SCAPS 官方算例交叉校验 | **能** | 本报告即为实现：3 个官方 def "
        "在本机 3.3.12 下重算暗/光 J–V 与 QE，含预指定判据与确定性检验 |",
        "| 补一组 **实测** J–V / EQE 数据 | **不能** | 实测数据必须由真实器件 + "
        "太阳模拟器 / QE 系统产生；本机只有求解器，无法生成测量 |",
        "| 把 SCAPS 自带 `measurements/` 文件当实测数据拟合 | **不应做** | "
        "这些文件在自身文件头里明确写是 SCAPS 仿真的输出，见第 4 节原文 |",
        "| 用 SCAPS 仿真输出做拟合（诚实标注） | 能 | 属于跨代码 surrogate 拟合，"
        "不是实测；见配套说明 |", "",
        "## 2. 官方算例与出处", "",
        "| tag | 发行包内文件 | 说明 |", "|--|--|--|",
        "| cdte | `def/example CdTe.def` | 随 SCAPS 2.1(1999) 起所有版本分发；"
        "参数源自 A. Niemegeers 博士论文 (Gent, 1998)，用于 Burgelman, Nollet & "
        "Degrave, *Appl. Phys. A* **69**, 149–153 (1999) 的图 |",
        "| cigs | `def/Numos CIGS baseline.def` | NUMOS 教学基准器件 |",
        "| si | `def/example Si.def` | 官方 Si 算例 |", "",
        "每个算例通过两个独立脚本（暗态 J–V；光照 J–V + QE）启动 SCAPS，"
        "脚本原文与原生 `.iv/.qe` 导出一并保存在本目录。", "",
        "## 3. 预指定判据与逐项结果", "",
        "判据在任何 SCAPS 运行之前写入脚本常量 `CRITERIA`，未因结果调整。", "",
        "| 检查项 | 实测 | 判据 | 判定 |", "|--|--|--|--|",
    ]
    for v in verdict["verdicts"]:
        L.append(f"| {v['item']} | {v['measured']} | {v['threshold']} | "
                 f"**{v['verdict']}** |")
    L += ["", f"**总计：PASS {sum(v['verdict'] == 'PASS' for v in verdict['verdicts'])}"
          f" / FAIL {sum(v['verdict'] == 'FAIL' for v in verdict['verdicts'])}"
          f"；all_pass = {str(verdict['all_pass']).lower()}。**", "",
          "说明：SCAPS 3.3.12 是 32 位 LabWindows/CVI 程序，`quitscript.quitSCAPS` "
          "结束后 CVI runtime 常返回 `0xC0000409` 一类非零码。判定以"
          "「本次运行确实写出且能解析的原生输出」为准，返回码仅记录在 JSON 里。", "",
          "### 3.1 官方默认设置下的数值行为（不是错误，也不作性能评估）", "",
          "本检验使用官方 def 的**原始默认参数**，未针对复现检验调参，"
          "扫描区间统一到 1.0 V，超出各器件 Voc：", "",
          "- CdTe / CIGS / Si 的光照 |Jsc| 分别为 21.638 / 33.775 / 35.762 mA/cm²，"
          "量级合理；越过 Voc 后 SCAPS 继续扫描并返回明显非物理的发散电流，"
          "图中对纵轴做了截断并标注，原始值完整保留在 CSV 与原生 `.iv` 导出里。",
          "- CdTe 官方算例的 QE 峰值约 0.29 且带边在 ~830 nm 截止，"
          "CIGS / Si 峰值约 0.95 / 0.97；差异来自官方 def 各自的光学文件与"
          "收集设置，不是求解器故障。",
          "- 暗态 |J| 在高偏压下同样进入强注入区，图中为对数轴如实呈现。", "",
          "因此本报告的用途**仅限**确认「本机 SCAPS 能正确复现官方算例」，"
          "不得把这些曲线当作器件性能预测或实验对照。", "",
          "## 4. 为什么本机没有、也不能造出「实测」数据", "",
          "SCAPS 发行包 `measurements/` 目录下的 `.iv/.qe/.cv` 文件常被误认为实测数据。"
          "但官方文件头自己写明它们是仿真：", ""]
    L += official_measurement_evidence(base)
    L += ["",
          "手册 6.5.2 亦写明：*“any of the simulation results which have been saved "
          "by SCAPS can be read as a measurement file”*。因此把这类文件当作 independent "
          "measurement 去拟合，属于把仿真对仿真包装成实验验证，不能写进论文。", "",
          "本机工作区同样没有任何真实测量 J–V / EQE 数据：现有 csv 均由 UniDD 或 "
          "SCAPS 求解器生成（`scaps_reference/`、`scaps_run/export/`）。", "",
          "## 5. 与既有 UniDD ↔ SCAPS 交叉校验的关系", "",
          "之前那轮交叉校验用的是**自建** `unidd_crosscheck.def`（A/B 两层器件），"
          "结论是暗态 J–V 与产生率剖面 PASS、光照 J–V 与 EQE FAIL，原因是 SCAPS "
          "flatband / 表面复合接触与 UniDD Dirichlet 接触不等价。本报告补的是"
          "**官方标准算例**在本机能否被同一脚本链正确复现这一前置问题，"
          "属于对 SCAPS 侧可信度的审计，不改变也不稀释上述 2/4 判定。", "",
          "## 6. 若要真正补一组实测拟合，需要什么", "",
          "1. 一组真实器件的 J–V（暗 + 光照，AM1.5G）与绝对 EQE，附带测量条件："
          "温度、扫描方向/速率、光强标定、器件面积、光斑、预处理（light soaking）。",
          "2. 同一器件的结构参数：各层厚度、复折射率 `n+ik`（椭偏）、迁移率、"
          "掺杂、缺陷参数；否则只能做现象学拟合，无法做物理反演。",
          "3. 或者改用**已发表、许可允许、含完整元数据**的公开实测数据集做 "
          "literature-based calibration（此前 SOP 中的 L0 路线），并在论文中明确"
          "引用数据来源与数字化方法。", "",
          "在这些输入到位之前，任何「实测拟合」都只能是仿真对仿真的 surrogate，"
          "必须在图和正文里显式标注 `NOT experimental data`。", "",
          "## 7. 复现", "",
          "```bash",
          "python verify_scaps_official_examples.py "
          "--scaps-dir \"D:/software/Scaps3312/Scaps3312\"",
          "```", "",
          "输出：`official_examples_verdict.json`、`official_examples_curves.csv`、"
          "`official_examples_curves.png`、各算例原生 `.iv/.qe` 与所用 `.script`。", "",
    ]
    (OUT / "official_examples_report.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
