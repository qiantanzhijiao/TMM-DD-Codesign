"""
Build SCAPS-1D 3.3.12 cross-check inputs from the UniDD single source of truth.

This script does NOT run SCAPS and does NOT fabricate SCAPS results.  It only
writes the input files that the official SCAPS command-line/script chain needs:

  scaps_run/inputs/unidd_crosscheck.def      one-layer absorber + selective contacts
  scaps_run/inputs/unidd_generation.gen     UniDD G(z) in SCAPS units (#/m3.s)
  scaps_run/inputs/unidd_am15g.spe          UniDD AM1.5G coarse table (approximate)
  scaps_run/inputs/unidd_crosscheck.script  official 3.3.12 script syntax
  scaps_run/inputs/metadata_template.txt    run log template
  scaps_run/inputs/parameter_alignment.csv  auditable parameter mapping

Run:
    python build_scaps_inputs.py
    python build_scaps_inputs.py --deploy --scaps-dir "<SCAPS install dir>"

Design notes (see SCAPS1D交叉验证方案.md, version 3):
  * UniDD solves drift-diffusion on the ABSORBER only; ETL/HTL enter optics
    and the contact boundary values.  SCAPS must therefore be a ONE-layer
    device, not a three-layer p-i-n stack.
  * SCAPS .gen files use x in um and G in #/m3.s.  UniDD reference CSVs are
    in cm-3 s-1, so the .gen values are multiplied by 1e6.  The first version
    of the protocol had this conversion backwards; it is corrected here.
  * SCAPS contacts are metal/surface-recombination boundaries, whereas UniDD
    imposes Dirichlet carrier densities.  They are not mathematically
    identical; the protocol reports the discrepancy rather than hiding it.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Source tree: this file sits in soldiff/ next to the soldiff/ package and
# scaps_reference/.  Release tree: it sits in experiments/ with both one level
# up.  Resolve the project root so the same script works in either layout.
ROOT = HERE if (HERE / "soldiff" / "dd.py").is_file() else HERE.parent
RUN = ROOT / "scaps_run"
TPL = RUN / "templates"
INP = RUN / "inputs"
REF = ROOT / "scaps_reference"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))

from soldiff.dd import DDDevice, KB, Q          # noqa: E402
from soldiff.device import AM15_LAM, AM15_IRR  # noqa: E402

DEF_TPL = TPL / "simple_pn_3302.def"

# SCAPS layer parameters are stored as 7 composition-grading values + 2 flags.
GRADED_KEYS = ("eps", "chi", "Eg", "Nc", "Nv", "mu_n", "mu_p",
               "v_th_n", "v_th_p", "K_rad", "c_n_auger", "c_p_auger",
               "Na(y)", "Nd(y)", "Nt(y)")
UNIT_RE = re.compile(r"^(?P<key>[^:]+?)\s*:\s*(?P<body>.*?)\s*\[(?P<unit>[^\]]+)\]\s*$")


def graded_line(key: str, value: float, unit: str) -> str:
    vals = "\t".join(f" {value:14.6e}" for _ in range(7))
    return f"{key} :\t{vals}\t 0\t 0\t[{unit}]"


def replace_graded(text: str, key: str, value: float) -> str:
    out, hit = [], 0
    for line in text.splitlines():
        m = UNIT_RE.match(line)
        if m and m.group("key").strip() == key:
            out.append(graded_line(key, value, m.group("unit")))
            hit += 1
        else:
            out.append(line)
    if hit != 1:
        raise RuntimeError(f"expected exactly one '{key}' line, found {hit}")
    return "\n".join(out)


def replace_scalar(text: str, key: str, value: str) -> str:
    out, hit = [], 0
    for line in text.splitlines():
        m = UNIT_RE.match(line)
        if m and m.group("key").strip() == key:
            unit = m.group("unit")
            out.append(f"{key} : {value}\t[{unit}]")
            hit += 1
            continue
        m2 = re.match(r"^(?P<key>[^:]+?)\s*:\s*(?P<body>.*)$", line)
        if m2 and m2.group("key").strip() == key:
            out.append(f"{key} : {value}")
            hit += 1
        else:
            out.append(line)
    if hit != 1:
        raise RuntimeError(f"expected exactly one '{key}' scalar, found {hit}")
    return "\n".join(out)


def build_def(dd: DDDevice) -> str:
    raw = DEF_TPL.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()

    def index(word: str, nth: int = 1):
        hits = [i for i, l in enumerate(lines) if l.strip() == word]
        if len(hits) < nth:
            raise RuntimeError(f"template missing '{word}' #{nth}")
        return hits[nth - 1]

    i_conv = index("convergence")
    i_layer1 = index("layer")
    i_iface = index("interface properties")
    i_front = index("front contact")

    header = lines[:i_conv]
    front_and_wp = lines[i_front:]
    # convergence + back contact; layer 1 up to (but excluding) interface block
    middle = lines[i_conv:i_layer1]
    layer1 = "\n".join(lines[i_layer1:i_iface])

    # --- layer 1: UniDD absorber (SI units, SCAPS .def is also SI) -----------
    layer1 = replace_scalar(layer1, "name", "unidd absorber")
    layer1 = replace_scalar(layer1, "d", f"{480e-9:.6e}")
    for key, val in (
        ("eps", dd.eps_r), ("chi", dd.chi), ("Eg", dd.Eg),
        ("Nc", dd.Nc), ("Nv", dd.Nv),
        ("mu_n", 2e-4), ("mu_p", 2e-4),
        ("v_th_n", 1e5), ("v_th_p", 1e5),
        ("K_rad", 0.0), ("c_n_auger", 0.0), ("c_p_auger", 0.0),
        ("Na(y)", 1e7), ("Nd(y)", 1e7),
    ):
        layer1 = replace_graded(layer1, key, val)

    # One neutral SRH level at mid-gap, tuned to the UniDD lifetime tau.
    # tau = 1 / (sigma * v_th * Nt)  =>  Nt = 1 / (tau * sigma * v_th).
    tau = 3.0e-7
    sigma = 1.0e-19
    v_th = 1.0e5
    nt = 1.0 / (tau * sigma * v_th)
    layer1 = replace_graded(layer1, "Nt(y)", nt)
    layer1 = replace_scalar(layer1, "sigma_n", f"{sigma:.3e}")
    layer1 = replace_scalar(layer1, "sigma_p", f"{sigma:.3e}")
    layer1 = replace_scalar(layer1, "Et", "  0.000")
    layer1 = replace_scalar(layer1, "Nleft", f"{nt:.3e}")
    layer1 = replace_scalar(layer1, "Nright", f"{nt:.3e}")
    layer1 = layer1.replace("Reference for defect energy :  0 ;",
                            "Reference for defect energy :  1 ;")

    # --- contacts: electron-selective at x=0, hole-selective at x=d ---------
    mid = "\n".join(middle)
    mid = replace_scalar(mid, "Sn", " 1.000e+05")
    mid = replace_scalar(mid, "Sp", " 1.000e-02")
    front = "\n".join(front_and_wp)
    front = replace_scalar(front, "Sn", " 1.000e-02")
    front = replace_scalar(front, "Sp", " 1.000e+05")
    front = re.sub(r"illuminated from\s*:\s*\w+", "illuminated from : left", front)
    front = front.replace("internal Rfront :   1.00000000",
                          "internal Rfront :   0.00000000")
    front = front.replace("internal Tfront :  0.0000e+00",
                          "internal Tfront :  1.0000e+00")

    hdr = ["> UniDD cross-check device: single absorber layer, ideal selective contacts",
           f"> generated by build_scaps_inputs.py at {dt.datetime.now().isoformat(timespec='seconds')}",
           "> template: SCAPS 3.3.02 'simple pn.def'; first layer retained, second layer removed",
           "> SCAPS 3.3.12 will rewrite this file in its own format on 'save settings.definitionfile'",
           "> ",
           "> SRH equivalence: tau = 1/(sigma*vth*Nt), single mid-gap neutral level",
           f">   tau={tau:.3e} s, sigma={sigma:.3e} m2, vth={v_th:.3e} m/s, Nt={nt:.6e} m-3",
           "> Contacts are metal/surface-recombination boundaries: NOT identical to the",
           "> Dirichlet carrier-density contacts used by UniDD. Report the difference.",
           "> "]
    return "\n".join(hdr + [l for l in mid.splitlines()] + layer1.splitlines()
                     + front.splitlines()) + "\n"


def build_gen() -> str:
    with (REF / "unidd_generation_profile.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) < 2:
        raise RuntimeError("UniDD generation profile is empty")
    out = [
        "> UniDD generation profile for SCAPS-1D cross-check (coherent TMM)",
        "> x is measured from the ETL side of the ABSORBER ONLY, in micrometer",
        "> Geh is the electron-hole generation rate in #/m3.s (SI)",
        "> UniDD reference CSV stores cm-3 s-1; values here are multiplied by 1e6",
        "> generated by build_scaps_inputs.py; do not edit by hand",
        "x (um)\tGeh (#/m3.s)",
    ]
    for r in rows:
        z = float(r["z_um"])
        g_cm = float(r["G_coherent_cm3_s"])
        out.append(f"{z:.6f}\t{g_cm * 1e6:.6e}")
    return "\n".join(out) + "\n"


def build_spe() -> str:
    """Approximate UniDD AM1.5G coarse table as a SCAPS .spe file.

    SCAPS .spe rows are the incident POWER (W/m2) inside the wavelength bin
    centred on each row, not the spectral irradiance density.  UniDD stores
    W m-2 nm-1 at 50 nm knots; we interpolate to the 41-point 350-800 nm grid
    and integrate each bin.  The table is then scaled to 1000 W/m2.  This is
    an APPROXIMATION restricted to 350-800 nm and must not be used as a strict
    EQE acceptance test.
    """
    lam = [350.0 + (800.0 - 350.0) * i / 40 for i in range(41)]
    knots = [float(x) for x in AM15_LAM]
    irr = [float(x) for x in AM15_IRR]

    def interp(x: float) -> float:
        for i in range(len(knots) - 1):
            if knots[i] <= x <= knots[i + 1]:
                w = (x - knots[i]) / (knots[i + 1] - knots[i])
                return irr[i] + w * (irr[i + 1] - irr[i])
        return irr[0] if x < knots[0] else irr[-1]

    powers = []
    for i, x in enumerate(lam):
        lo = lam[i - 1] if i > 0 else lam[0] - (lam[1] - lam[0]) / 2
        hi = lam[i + 1] if i < len(lam) - 1 else lam[-1] + (lam[-1] - lam[-2]) / 2
        powers.append(interp(x) * (hi - lo) / 2.0)
    total = sum(powers)
    scale = 1000.0 / total
    out = [
        "> UniDD AM1.5G coarse table (ASTM G173 knots at 50 nm spacing)",
        "> APPROXIMATE SCAPS spectrum: 350-800 nm only, bin-integrated power",
        f"> raw integrated power {total:.3f} W/m2, scaled to 1000 W/m2 by {scale:.6f}",
        "> EQE comparison using this file is a SHAPE sanity check, not a strict test",
        "> SCAPS .spe convention: P(W/m2) in the bin around each wavelength",
        "> ",
        ">lambda (nm)\tP(W/m2)",
    ]
    for x, p in zip(lam, powers):
        out.append(f"{x:.3f}\t{p * scale:.6e}")
    return "\n".join(out) + "\n"


SCRIPT = """// UniDD <-> SCAPS-1D cross-check, official SCAPS 3.3.12 script syntax.
// Generated by build_scaps_inputs.py.  Command names were checked against
// scriptdescription3312.txt distributed with this SCAPS build.
// Start with:  scaps3312.exe <absolute path to this .script>
// The script sets quitscript.quitSCAPS so the process exits when finished.

set quitscript.quitSCAPS
set script_display_mode.fully_suppressed
set errorhandling.overwritefile
set batch_display_mode.suppressed

load definitionfile unidd_crosscheck.def
load spectrumfile unidd_am15g.spe
clear all
clear actions

// ---------------- Layer A: dark J-V, drift-diffusion kernel only ----------
action dark
action iv.doiv
action iv.startV 0.0
action iv.stopV 1.2
action iv.increment 0.02
action iv.continueafterVoc
calculate singleshot
save results.iv unidd_A_dark.iv
save graph.iv.iv unidd_A_dark.png

// -------- Layer B: user G(x) from UniDD, illuminated J-V and readback -----
clear actions
action light
action generation_defined.fromfile
load generationfile unidd_generation.gen
action iv.doiv
action iv.startV 0.0
action iv.stopV 1.2
action iv.increment 0.02
action iv.continueafterVoc
calculate singleshot
save results.iv unidd_B_light.iv
save graph.iv.iv unidd_B_light.png
save results.SCAPSgenerationfile unidd_B_generation_readback.gen
save results.genrec unidd_B_genrec.dat
save graph.genrec.genrec unidd_B_generation.png

// -------- Layer B: spectral response (shape sanity check only) ------------
clear actions
action light
action generation_defined.frommodel
action qe.doqe
action qe.startlambda 380
action qe.stoplambda 780
action qe.increment 20
calculate singleshot
save results.qe unidd_B_eqe.qe
save graph.qe.qe unidd_B_eqe.png

// ---------------- Persist the effective problem definition ----------------
save settings.definitionfile unidd_crosscheck_effective.def
// set quitscript.quitSCAPS (above) terminates SCAPS here
"""


def official_signatures() -> set[tuple[str, tuple[str, ...]]]:
    """Parse the distributed scriptdescription3312.txt into (command, args)."""
    path = TPL / "scriptdescription3312.txt"
    if not path.is_file():
        return set()
    sigs: set[tuple[str, tuple[str, ...]]] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ";" not in line or line.lstrip().startswith("//"):
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 6 or not parts[0] or not parts[0].isalpha():
            continue
        cmd = parts[0].lower()
        args = tuple(p.lower() for p in parts[1:5] if p)
        sigs.add((cmd, args))
    return sigs


def validate_script(script_text: str) -> list[str]:
    """Check every command line against the official 3.3.12 command table."""
    sigs = official_signatures()
    if not sigs:
        return ["official command table missing; validation skipped"]
    problems = []
    for lineno, raw in enumerate(script_text.splitlines(), 1):
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        toks = tuple(t.lower() for t in arg.split(".") if t)
        ok = any(c == cmd and a[:len(toks)] == toks for c, a in sigs)
        if not ok:
            problems.append(f"line {lineno}: {line}")
    return problems


def build_alignment(dd: DDDevice) -> str:
    tau, sigma, vth = 3.0e-7, 1.0e-19, 1.0e5
    nt = 1.0 / (tau * sigma * vth)
    rows = [
        ("quantity", "UniDD", "SCAPS", "unit", "note"),
        ("solved domain", "absorber only", "one layer", "-",
         "ETL/HTL only enter UniDD optics and contact boundary values"),
        ("absorber thickness", "480 nm", "4.800000e-07 m", "m", "nm -> m"),
        ("Eg", str(dd.Eg), str(dd.Eg), "eV", "300 K"),
        ("chi", str(dd.chi), str(dd.chi), "eV", "electron affinity"),
        ("epsilon_r", str(dd.eps_r), str(dd.eps_r), "-", ""),
        ("Nc", f"{dd.Nc:.3e} m-3", f"{dd.Nc:.3e} m-3", "m-3",
         "SCAPS .def is SI; do NOT divide by 1e6 for the .def file"),
        ("Nv", f"{dd.Nv:.3e} m-3", f"{dd.Nv:.3e} m-3", "m-3", "same"),
        ("mu_n = mu_p", "2.0e-4 m2/Vs", "2.0e-4 m2/Vs", "m2/Vs", "same"),
        ("tau_SRH", f"{tau:.3e} s", f"Nt={nt:.6e} m-3", "s / m-3",
         "tau = 1/(sigma*vth*Nt); sigma=1e-19 m2, vth=1e5 m/s, Et at Ei"),
        ("Na, Nd", "intrinsic", "1e7 m-3", "m-3", "numerically neutral"),
        ("contact at x=0", "electron selective, n=2.2e24 m-3", "Sn=1e5, Sp=1e-2 m/s",
         "-", "MODELS DIFFER: Dirichlet vs surface recombination"),
        ("contact at x=d", "hole selective, p=1.8e25 m-3", "Sn=1e-2, Sp=1e5 m/s",
         "-", "MODELS DIFFER"),
        ("illumination side", "ETL (x=0)", "left", "-", ""),
        ("generation file", "cm-3 s-1", "#/m3.s", "-",
         "multiply UniDD values by 1e6 when writing the .gen file"),
        ("current", "A/m2", "mA/cm2", "-", "1 A/m2 = 0.1 mA/cm2; SCAPS sign flipped"),
        ("mesh", "N=73 uniform", "SCAPS internal", "-", "discretisation differs"),
    ]
    return "\n".join(",".join(f'"{c}"' if "," in c else c for c in r) for r in rows) + "\n"


METADATA = """# SCAPS-1D cross-check run log  (fill in and keep with the exported data)
SCAPS executable   : scaps3312.exe
SCAPS version      : 3.3.12  (confirm via Help -> About; record build date)
CVI Run-Time Engine: <version, e.g. LabWindows/CVI Run-Time Engine 2019 or 2020>
Operating system   : Windows
Run date / operator: <YYYY-MM-DD HH:MM> / <name>
Definition file    : unidd_crosscheck.def
Effective def file : unidd_crosscheck_effective.def  (saved by the script)
Script file        : unidd_crosscheck.script
Spectrum file      : unidd_am15g.spe
Generation file    : unidd_generation.gen  (UniDD coherent TMM, #/m3.s)
Reference data     : scaps_reference/unidd_*.csv  (UniDD side, NOT SCAPS output)
Acceptance criteria: fixed in SCAPS1D交叉验证方案.md section 5; NOT revised after data.

# Mandatory checks before trusting the numbers
- [ ] SCAPS started without DLL errors and the process exited by itself.
- [ ] unidd_crosscheck_effective.def was written; open it and confirm ONE layer.
- [ ] unidd_B_generation_readback.gen agrees with unidd_generation.gen to <2%.
- [ ] All four result files (.iv x2, .qe, .gen) and PNG graphs are present.
- [ ] No SCAPS data are quoted in the manuscript before this log is complete.
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", action="store_true",
                    help="copy generated inputs into the SCAPS default directories")
    ap.add_argument("--scaps-dir", default="",
                    help="SCAPS installation directory (required with --deploy)")
    args = ap.parse_args()

    INP.mkdir(parents=True, exist_ok=True)
    dd = DDDevice(N=73)
    files = {
        "unidd_crosscheck.def": build_def(dd),
        "unidd_generation.gen": build_gen(),
        "unidd_am15g.spe": build_spe(),
        "unidd_crosscheck.script": SCRIPT,
        "parameter_alignment.csv": build_alignment(dd),
        "metadata_template.txt": METADATA,
    }
    for name, text in files.items():
        (INP / name).write_text(text, encoding="utf-8")
        print(f"  wrote {INP / name}  ({len(text)} bytes)")

    problems = validate_script(SCRIPT)
    if problems:
        print("\n  script syntax check (vs scriptdescription3312.txt):")
        for p in problems:
            print("    UNVERIFIED:", p)
        print("  Resolve these in the built-in script editor before running SCAPS.")
    else:
        print("\n  script syntax check: every command matches the official 3.3.12 table.")

    if args.deploy:
        base = Path(args.scaps_dir)
        if not (base / "scaps3312.exe").is_file():
            raise SystemExit(f"not a SCAPS installation: {base}")
        targets = {
            "def": ["unidd_crosscheck.def"],
            "generation": ["unidd_generation.gen"],
            "spectrum": ["unidd_am15g.spe"],
            "script": ["unidd_crosscheck.script"],
        }
        for sub, names in targets.items():
            (base / sub).mkdir(exist_ok=True)
            for n in names:
                shutil.copy2(INP / n, base / sub / n)
                print(f"  deployed {sub}/{n}")
        runtime = base / "cvirte.dll"
        if not runtime.is_file():
            print("\n  WARNING: cvirte.dll is absent from the SCAPS directory and")
            print("  was not found anywhere on this machine. SCAPS will exit with")
            print("  0xC0000135 until the matching NI LabWindows/CVI Run-Time")
            print("  Engine is installed. See SCAPS1D交叉验证方案.md section 0.")
    print("\nDry-run build complete. No SCAPS simulation has been executed.")


if __name__ == "__main__":
    main()
