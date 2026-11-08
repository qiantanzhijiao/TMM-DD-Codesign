"""Fast integrity checks for the recorded result files (also run in CI)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def load(name):
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def check():
    f = load("results_final.json")
    s = load("results_supplement.json")
    h = load("results_E4_highdim.json")
    assert f["E0"]["checks_passed"] == 6 and f["E0"]["pass"] is True
    assert f["E1"]["pass"] is True
    assert f["E2"]["checks_passed"] == 6 and f["E2"]["pass"] is False
    assert f["E3"]["pass"] is True and f["E3"]["evals"] == 44
    assert f["E4"]["pass"] is False
    assert h["verdict"]["result"] == "PASS"
    assert h["verdict"]["min_observed_speedup"] == 1.0
    assert h["verdict"]["note"].startswith("censored comparisons are LOWER BOUNDS")
    assert s["observed_order"] > 2.0
    assert s["production_Jsc_rel_error_vs_extrapolated"] < 0.02
    c = load("results_E4_factorial.json")
    b = load("results_baselines.json")
    assert c["sanity"]["shared_target_max_abs_diff"] == 0.0
    assert set(c["arms"]) == {"8D", "16D"} and "summary" in c
    assert c["summary"]["pilot"] is False
    assert len(b["runs"]) == 10 and "summary" in b
    assert all(0 < r["n_calls"] <= 80 for r in b["runs"])
    print("recorded-result integrity: OK")


if __name__ == "__main__":
    check()
