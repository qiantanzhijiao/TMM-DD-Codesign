"""Pytest entry point for the three script-style regression suites."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


def _run(name: str) -> None:
    p = subprocess.run([sys.executable, str(TESTS / name)], cwd=ROOT,
                       capture_output=True, text=True)
    assert p.returncode == 0, (
        name + " failed\n" + p.stdout[-3000:] + "\n" + p.stderr[-2000:])


def test_optics_energy() -> None:
    _run("check_optics_energy.py")


def test_newton_smoke() -> None:
    _run("check_newton.py")


def test_recorded_results() -> None:
    _run("test_results_integrity.py")
