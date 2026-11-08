"""
One-command SCAPS-1D 3.3.12 cross-check driver.

    python run_scaps_crosscheck.py --scaps-dir "<SCAPS install dir>"

What it does:
  1. verifies the NI LabWindows/CVI run-time engine is present (cvirte.dll);
  2. deploys the generated .def/.gen/.spe/.script into SCAPS default folders;
  3. starts scaps3312.exe with the script on the command line and waits;
  4. collects every newly written unidd_* result file, including SCAPS's own
     PNG graphs;
  5. converts native .iv/.qe/.gen exports into the CSVs that compare_scaps.py
     expects;
  6. runs compare_scaps.py and writes crosscheck_status.json.

It NEVER fabricates SCAPS numbers.  If SCAPS cannot start, or any required
result is missing, the status file records "not_performed" and the manuscript
must keep its "no SCAPS cross-validation" limitation.

Exit codes: 0 = completed, 2 = blocked/missing runtime, 3 = SCAPS failed,
            4 = results incomplete.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Source tree: scaps_run/ is next to this file.  Release tree: one level up.
ROOT = HERE if (HERE / "scaps_run").is_dir() else HERE.parent
RUN = ROOT / "scaps_run"
INP = RUN / "inputs"
EXP = RUN / "export"
STATUS = RUN / "crosscheck_status.json"

NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
ROW2 = re.compile(rf"^\s*({NUM})\s+({NUM})(?:\s|$)")

DEPLOY = {
    "def": ["unidd_crosscheck.def"],
    "generation": ["unidd_generation.gen"],
    "spectrum": ["unidd_am15g.spe"],
    "script": ["unidd_crosscheck.script"],
}
RESULT_NAMES = {
    "unidd_A_dark.iv": "dark J-V",
    "unidd_B_light.iv": "light J-V",
    "unidd_B_eqe.qe": "EQE",
    "unidd_B_generation_readback.gen": "G(z) readback",
}


def write_status(state: str, **kw) -> None:
    data = {"state": state, "checked_at": dt.datetime.now().isoformat(timespec="seconds"), **kw}
    STATUS.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"status -> {STATUS}  [{state}]")


def find_runtime(base: Path) -> Path | None:
    candidates = [
        base / "cvirte.dll",
        Path("C:/Windows/System32/cvirte.dll"),
        Path("C:/Windows/SysWOW64/cvirte.dll"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    for p in (Path(x) for x in os.environ.get("PATH", "").split(";") if x):
        if (p / "cvirte.dll").is_file():
            return p / "cvirte.dll"
    return None


def numeric_rows(text: str, start: int = 0) -> list[tuple[float, float]]:
    out = []
    for line in text.splitlines()[start:]:
        m = ROW2.match(line)
        if m:
            out.append((float(m.group(1)), float(m.group(2))))
        elif out and line.strip() and not line.lstrip().startswith(">"):
            break
    return out


def parse_iv(path: Path) -> list[tuple[float, float]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    hdr = next((i for i, l in enumerate(lines)
                if "v(V)" in l and "jtot" in l), None)
    if hdr is None:
        raise ValueError(f"{path.name}: no 'v(V) jtot' table header")
    rows = numeric_rows("\n".join(lines), hdr + 1)
    if len(rows) < 5:
        raise ValueError(f"{path.name}: only {len(rows)} J-V rows")
    return rows


def parse_qe(path: Path) -> list[tuple[float, float]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = [(a, b) for a, b in numeric_rows(text)
            if 250.0 <= a <= 1400.0 and -1.5 <= b <= 120.0]
    if len(rows) < 3:
        raise ValueError(f"{path.name}: no plausible wavelength/QE rows")
    # SCAPS may export QE in percent; normalise only if clearly > 1.
    if sum(1 for _, b in rows if b > 1.5) > len(rows) / 2:
        rows = [(a, b / 100.0) for a, b in rows]
    return rows


def parse_gen(path: Path) -> list[tuple[float, float]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = numeric_rows(text)
    # SCAPS .gen stores #/m3.s; the reference CSV is cm-3 s-1.
    rows = [(x, g / 1e6) for x, g in rows if g > 0]
    if len(rows) < 3:
        raise ValueError(f"{path.name}: no generation rows")
    return rows


def write_csv(path: Path, header: tuple[str, str], rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  parsed -> {path.name} ({len(rows)} rows)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scaps-dir", required=True)
    ap.add_argument("--timeout", type=int, default=900,
                    help="seconds to wait for SCAPS to finish")
    args = ap.parse_args()
    base = Path(args.scaps_dir)
    exe = base / "scaps3312.exe"
    EXP.mkdir(parents=True, exist_ok=True)

    if not exe.is_file():
        print(f"SCAPS executable not found: {exe}")
        write_status("not_performed", reason="scaps3312.exe not found")
        return 2

    rt = find_runtime(base)
    if rt is None:
        print("\nBLOCKED: cvirte.dll (NI LabWindows/CVI Run-Time Engine) is missing.")
        print("SCAPS 3.3.12 is a LabWindows/CVI executable; it exits with 0xC0000135")
        print("until the matching Run-Time Engine is installed. NI's official fix:")
        print("  https://knowledge.ni.com/KnowledgeArticleDetails?id=kA00Z000000P6AXSA0")
        print("Install the version that matches the CVI build used for SCAPS 3.3.12")
        print("(2019 or 2020), or obtain the full SCAPS distribution that bundles it.")
        write_status("not_performed", reason="cvirte.dll missing",
                     scaps_dir=str(base), ni_kb="kA00Z000000P6AXSA0")
        return 2
    print(f"CVI run-time engine: {rt}")

    # --- deploy ------------------------------------------------------------
    for sub, names in DEPLOY.items():
        (base / sub).mkdir(exist_ok=True)
        for n in names:
            src = INP / n
            if not src.is_file():
                print(f"missing generated input: {src}; run build_scaps_inputs.py first")
                write_status("not_performed", reason="inputs not generated")
                return 2
            shutil.copy2(src, base / sub / n)

    # --- snapshot existing outputs ----------------------------------------
    before = {p: p.stat().st_mtime_ns for p in base.rglob("unidd_*")
              if p.is_file() and "scaps_run" not in str(p)}

    script = base / "script" / "unidd_crosscheck.script"
    print(f"launching: {exe} {script}")
    t0 = time.time()
    proc = subprocess.Popen([str(exe), str(script)], cwd=str(base),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=args.timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        rc = None
    elapsed = round(time.time() - t0, 1)
    print(f"SCAPS exit code: {rc}  elapsed: {elapsed} s")
    if out.strip():
        print("stdout:", out[:400].decode("utf-8", "replace"))
    if err.strip():
        print("stderr:", err[:400].decode("utf-8", "replace"))
    if rc is None:
        write_status("not_performed", reason="SCAPS did not exit before timeout",
                     elapsed_s=elapsed)
        return 3
    if rc != 0:
        write_status("not_performed", reason=f"SCAPS exited with code {rc}",
                     elapsed_s=elapsed)
        return 3

    # --- collect new/updated unidd_* outputs -------------------------------
    collected: dict[str, Path] = {}
    for p in base.rglob("unidd_*"):
        if not p.is_file() or "scaps_run" in str(p):
            continue
        mtime = p.stat().st_mtime_ns
        if before.get(p) == mtime:
            continue
        dst = EXP / p.name
        shutil.copy2(p, dst)
        collected[p.name] = dst
        print(f"  collected {p.relative_to(base)} -> {dst.name} ({p.stat().st_size} B)")

    missing = [n for n in RESULT_NAMES if n not in collected]
    if missing:
        print("missing SCAPS result files:", ", ".join(missing))
        write_status("not_performed", reason="incomplete results",
                     missing=missing, elapsed_s=elapsed,
                     collected=sorted(collected))
        return 4

    # --- convert to compare_scaps.py CSVs ----------------------------------
    try:
        write_csv(EXP / "dark_JV.csv", ("V_V", "J_mA_cm2"),
                  parse_iv(collected["unidd_A_dark.iv"]))
        write_csv(EXP / "light_JV.csv", ("V_V", "J_mA_cm2"),
                  parse_iv(collected["unidd_B_light.iv"]))
        write_csv(EXP / "EQE.csv", ("lambda_nm", "EQE"),
                  parse_qe(collected["unidd_B_eqe.qe"]))
        write_csv(EXP / "generation_profile.csv", ("z_um", "G_cm3_s"),
                  parse_gen(collected["unidd_B_generation_readback.gen"]))
    except Exception as e:
        write_status("not_performed", reason=f"result parse failed: {e}",
                     collected=sorted(collected))
        return 4

    # --- metadata ----------------------------------------------------------
    tpl = (INP / "metadata_template.txt").read_text(encoding="utf-8")
    (EXP / "metadata.txt").write_text(
        tpl.replace("<YYYY-MM-DD HH:MM>", dt.datetime.now().isoformat(timespec="seconds"))
           .replace("<name>", "automated run via run_scaps_crosscheck.py")
        + f"\nSCAPS exit code: {rc}\nElapsed: {elapsed} s\n"
        + f"Collected files: {', '.join(sorted(collected))}\n",
        encoding="utf-8")

    # --- compare -----------------------------------------------------------
    cp = subprocess.run([sys.executable, str(HERE / "compare_scaps.py"),
                         "--scaps-dir", str(EXP)], cwd=str(ROOT),
                        capture_output=True, text=True)
    print(cp.stdout.strip())
    if cp.returncode != 0:
        print(cp.stderr.strip())
        write_status("not_performed", reason="compare_scaps.py failed")
        return 4

    verdict = EXP / "acceptance_verdict.json"
    passed = None
    if verdict.is_file():
        passed = json.loads(verdict.read_text(encoding="utf-8")).get("all_pass")
    write_status("completed", elapsed_s=elapsed, collected=sorted(collected),
                 all_pass=passed, report=str(EXP / "scaps_comparison.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
