"""Deploy the LabWindows/CVI run-time engine for SCAPS 3.3.12, WITHOUT elevation.

Why this script exists
----------------------
``scaps3312.exe`` is a 32-bit LabWindows/CVI executable.  On a machine without
the CVI Run-Time Engine it exits immediately with ``0xC0000135`` because
``cvirte.dll`` is missing.  The engine is bundled inside the *official* SCAPS
3.3.12 installation package distributed by ELIS / Ghent University:

    https://scaps.elis.ugent.be/SCAPS3312%20Installation%20Package.zip
    SHA-256 c64a79007cdb39e9af3b3827a1c97c4fb7b2147772548cb4cfe5c7e75ca2d98b

Following NI knowledge base article ``kA00Z0000019LJBSA2``, the runtime can be
deployed privately next to the executable: no NI account, no installer, no
administrator rights and no changes to ``C:\\Windows``.

Important detail discovered while setting this up
-------------------------------------------------
It is not enough to copy ``cvirte.dll``, ``mesa.dll`` and ``cvirte\\fonts``.
The 2007-era runtime validates the resource directory by opening
``cvirte\\bin\\msgrte.txt``.  If that file is absent the runtime rejects the
application directory, falls back to the Windows system directory and aborts
with ``Can not find RTE directory: C:\\Windows\\system32\\cvirte``.  Copying the
FULL resource set (``msgrte.txt``, ``msgrt4.txt``, ``cvierror.txt``,
``cvirte.rsc``, ``cvirt4.rsc`` plus the two fonts) makes the private deployment
work.  No elevation or ``SystemRoot`` override is needed.

Usage
-----
    python install_scaps_runtime.py --check
    python install_scaps_runtime.py --scaps-dir "<SCAPS installation dir>"
    python install_scaps_runtime.py --package <official zip> --scaps-dir <dir>

The script downloads the official package if it is not cached locally, extracts
``bin/dp/Distfile.cab`` with the built-in Windows ``expand.exe``, and copies the
22 runtime files into the SCAPS directory.  A SHA-256 manifest is written to
``scaps_run/runtime_deploy_manifest.json`` for reproducibility.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE if (HERE / "scaps_run").is_dir() else HERE.parent
RUN = ROOT / "scaps_run"
CACHE = RUN / "runtime" / "SCAPS3312_Installation_Package.zip"
MANIFEST = RUN / "runtime_deploy_manifest.json"
DEFAULT_SCAPS = Path(r"D:\software\Scaps3312\Scaps3312")

PACKAGE_URL = "https://scaps.elis.ugent.be/SCAPS3312%20Installation%20Package.zip"
PACKAGE_SHA256 = "c64a79007cdb39e9af3b3827a1c97c4fb7b2147772548cb4cfe5c7e75ca2d98b"
PACKAGE_SIZE = 19672460

# CAB entry name -> deployed path relative to the SCAPS directory.
# The GUID-looking suffixes are MSI CAB stream identifiers.
G = "AEE0121B_9196_4E7A_8C0F_7C1B926D077F"
MKL = "B971A7AF_CBFF_4489_9605_3344B7CDDCCD"
MAP: dict[str, str] = {
    f"cvirte.dll1.{G}": "cvirte.dll",
    f"cvirt.dll1.{G}": "cvirt.dll",
    f"cviauto.dll.{G}": "cviauto.dll",
    f"cvintwrk.dll.{G}": "cvintwrk.dll",
    f"cviUSI.dll.{G}": "cviUSI.dll",
    "cvitdms.dll.F9FA0ADE_BB44_45D8_8AD8_7A2D4F2DCD78": "cvitdms.dll",
    f"dataskt.dll.{G}": "dataskt.dll",
    f"libguide40.dll.{MKL}": "libguide40.dll",
    f"mkl_def.dll.{MKL}": "mkl_def.dll",
    f"mkl_lapack64.dll.{MKL}": "mkl_lapack64.dll",
    f"mkl_p3.dll.{MKL}": "mkl_p3.dll",
    f"mkl_p4.dll.{MKL}": "mkl_p4.dll",
    f"mkl_p4p.dll.{MKL}": "mkl_p4p.dll",
    "nianlys.dll.C864C12F_832A_4CC0_A051_156244869B59": "nianlys.dll",
    "mesa.dll.6FE8CEDD_964F_47A2_8F23_5A607953B235": "mesa.dll",
    # the resource tree -- msgrte.txt is the file the runtime checks first
    f"msgrte.txt.{G}": "cvirte/bin/msgrte.txt",
    f"msgrt4.txt.{G}": "cvirte/bin/msgrt4.txt",
    f"cvierror.txt.{G}": "cvirte/bin/cvierror.txt",
    f"cvirte.rsc.{G}": "cvirte/bin/cvirte.rsc",
    f"cvirt4.rsc.{G}": "cvirte/bin/cvirt4.rsc",
    f"ni7seg.ttf1.{G}": "cvirte/fonts/ni7seg.ttf",
    f"nisystem.ttf2.{G}": "cvirte/fonts/nisystem.ttf",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_package(dst: Path) -> None:
    """Parallel range download; the UGent server is slow on a single stream."""
    import requests
    n = 12
    chunk = (PACKAGE_SIZE + n - 1) // n
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "*/*"}

    def fetch(i: int):
        s = i * chunk
        e = min(PACKAGE_SIZE - 1, (i + 1) * chunk - 1)
        if s >= PACKAGE_SIZE:
            return i, s, b""
        for attempt in range(7):
            try:
                r = requests.get(PACKAGE_URL,
                                 headers={**headers, "Range": f"bytes={s}-{e}"},
                                 timeout=70)
                if r.status_code == 206 and len(r.content) == e - s + 1:
                    return i, s, r.content
            except Exception:
                pass
            time.sleep(1.5)
        return i, s, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
        parts = list(pool.map(fetch, range(n)))
    if any(d is None for _, _, d in parts):
        raise RuntimeError("parallel download incomplete; retry later")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("wb") as f:
        for _, s, data in parts:
            if data:
                f.seek(s)
                f.write(data)
    print(f"downloaded official package -> {dst} ({dst.stat().st_size} bytes)")


def check(scaps_dir: Path) -> dict:
    missing = [rel for rel in MAP.values() if not (scaps_dir / rel).is_file()]
    return {
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "scaps_dir": str(scaps_dir),
        "cvirte_dll": (scaps_dir / "cvirte.dll").is_file(),
        "rte_validator_msgrte_txt": (scaps_dir / "cvirte/bin/msgrte.txt").is_file(),
        "files_expected": len(MAP),
        "files_missing": missing,
        "ready": not missing,
        "requires_elevation": False,
    }


def deploy(scaps_dir: Path, package: Path) -> int:
    if not package.is_file():
        download_package(package)
    digest = sha256(package)
    if digest != PACKAGE_SHA256:
        raise RuntimeError(f"official package SHA-256 mismatch: {digest}")
    print(f"official package verified (SHA-256 {digest[:16]}...)")

    work = RUN / "runtime" / "_extract"
    if work.is_dir():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    with zipfile.ZipFile(package) as z:
        cab_member = next((n for n in z.namelist() if n.lower().endswith("distfile.cab")), None)
        if cab_member is None:
            raise RuntimeError("Distfile.cab not found in the official package")
        cab = work / "Distfile.cab"
        cab.write_bytes(z.read(cab_member))

    expand = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "expand.exe"
    out = work / "cab"
    out.mkdir()
    r = subprocess.run([str(expand), "-F:*", str(cab), str(out)],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"expand.exe failed (rc={r.returncode})")

    absent = [name for name in MAP if not (out / name).is_file()]
    if absent:
        raise RuntimeError(f"runtime files missing in CAB: {absent}")

    files = []
    for src_name, rel in MAP.items():
        src = out / src_name
        want = hashlib.sha256(src.read_bytes()).hexdigest()
        dst = scaps_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_file() and hashlib.sha256(dst.read_bytes()).hexdigest() == want:
            b = dst.read_bytes()          # already correct; do not touch a locked DLL
            action = "unchanged"
        else:
            shutil.copy2(src, dst)
            b = dst.read_bytes()
            action = "written"
        files.append({"file": rel, "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
                      "action": action})
    written = sum(1 for f in files if f["action"] == "written")
    print(f"deployed {len(files)} runtime files into {scaps_dir} ({written} newly written)")

    MANIFEST.write_text(json.dumps({
        "deployed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "SCAPS3312 Installation Package.zip (official ELIS/UGent build 4-6-2025)",
        "source_url": PACKAGE_URL,
        "source_sha256": PACKAGE_SHA256,
        "method": "private deployment into the SCAPS application directory; no system changes, no administrator rights",
        "authenticode": "legacy 2007 NI CVI runtime DLLs are not Authenticode-signed; integrity is pinned by SHA-256 above",
        "files": files,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"manifest -> {MANIFEST}")
    shutil.rmtree(work, ignore_errors=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scaps-dir", default=str(DEFAULT_SCAPS))
    ap.add_argument("--package", default=str(CACHE),
                    help="local copy of the official SCAPS installation zip (downloaded if absent)")
    ap.add_argument("--check", action="store_true", help="report deployment state only")
    args = ap.parse_args()
    scaps_dir = Path(args.scaps_dir)

    if args.check:
        state = check(scaps_dir)
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return 0 if state["ready"] else 1
    if not (scaps_dir / "scaps3312.exe").is_file():
        print(f"ERROR: scaps3312.exe not found in {scaps_dir}", file=sys.stderr)
        return 2
    rc = deploy(scaps_dir, Path(args.package))
    print(json.dumps(check(scaps_dir), indent=2, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
