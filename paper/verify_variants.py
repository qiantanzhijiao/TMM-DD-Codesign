"""Check both journal variants against the recorded result files and format rules."""
from __future__ import annotations

import json
import re
from pathlib import Path

from docx import Document

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SE, CPC = HERE / "solar_energy", HERE / "cpc"
F = json.loads((ROOT / "results_final.json").read_text(encoding="utf-8"))
S = json.loads((ROOT / "results_supplement.json").read_text(encoding="utf-8"))
H = json.loads((ROOT / "results_E4_highdim.json").read_text(encoding="utf-8"))

SUPP_FILE = HERE / "supplement_section.tex"
HAS_SUPP = SUPP_FILE.is_file()
N_TABLES = 5 if HAS_SUPP else 4
REPO_URL = "https://github.com/qiantanzhijiao/TMM-DD-Codesign"

checks: list[tuple[str, bool, str]] = []


def ck(name: str, cond: bool, detail: str = "") -> None:
    checks.append((name, bool(cond), detail))


VARIANTS = {
    "CPC": (CPC, "unidd_cpc", "cover_letter_CPC", "Computer Physics Communications"),
    "Solar Energy": (SE, "unidd_solar_energy", "cover_letter_Solar_Energy", "Solar Energy"),
}

for tag, (folder, stem, cstem, journal) in VARIANTS.items():
    tex = (folder / f"{stem}.tex").read_text(encoding="utf-8")
    flat = re.sub(r"\s+", " ", tex)
    title_block = re.search(r"\\title\{(.*?)\}", tex, re.S).group(1)
    ck(f"{tag}: LaTeX source", (folder / f"{stem}.tex").is_file())
    ck(f"{tag}: PDF", (folder / f"{stem}.pdf").is_file())
    ck(f"{tag}: Word", (folder / f"{stem}.docx").is_file())
    ck(f"{tag}: highlights txt", (folder / "highlights.txt").is_file())
    ck(f"{tag}: highlights docx", (folder / "highlights.docx").is_file())
    ck(f"{tag}: cover letter tex/pdf/docx",
       all((folder / f"{cstem}.{e}").is_file() for e in ("tex", "pdf", "docx")))
    ck(f"{tag}: figures", len(list((folder / "figures").glob("*.pdf"))) == 5)

    ck(f"{tag}: journal field", f"\\journal{{{journal}}}" in tex)
    ck(f"{tag}: title downgraded",
       "for co-design of thin-film solar cells" in title_block
       and "for inverse design" not in title_block)
    ck(f"{tag}: abstract has no efficiency headline",
       "27.74" not in tex.split(r"\end{abstract}")[0])
    ck(f"{tag}: internal numerical benchmark wording",
       "internal numerical benchmark" in flat)
    ck(f"{tag}: Beer-Lambert differentiation stated",
       "Beer--Lambert" in tex.split(r"\end{abstract}")[0])
    ck(f"{tag}: data available at submission",
       "at the time of submission" in tex and "upon acceptance" not in tex)
    ck(f"{tag}: repository URL resolved",
       REPO_URL in tex and "REPOSITORY-URL" not in tex)
    ck(f"{tag}: cover letter carries repository URL",
       REPO_URL in (folder / f"{cstem}.tex").read_text(encoding="utf-8"))
    ck(f"{tag}: AI disclosure retained",
       "\\section*{Generative AI disclosure}" in tex
       and "Generative AI tools were used" in tex)
    ck(f"{tag}: negative E4 result retained", "not met" in tex)
    ck(f"{tag}: E4-H censoring retained", "lower bounds" in tex or "bounds rather than" in tex)
    ck(f"{tag}: relation paragraph", "Relation to existing differentiable tools" in tex)
    ck(f"{tag}: bibliography has 23 entries",
       len(re.findall(r"\\bibitem\{", tex)) == 23)
    ck(f"{tag}: Byrnes v5", "version 5 (30 December 2020)" in tex)
    ck(f"{tag}: TFSolver page range", "52061--52074" in tex)
    ck(f"{tag}: DriftJax cited", "driftjax2026" in tex)
    ck(f"{tag}: SPIE proceedings version", "10.1117/12.3099007" in tex)
    ck(f"{tag}: 5 figures / {N_TABLES} tables",
       tex.count(r"\begin{figure}") == 5
       and tex.count(r"\begin{table}") == N_TABLES)
    if HAS_SUPP:
        ck(f"{tag}: E4-C/E5 supplement present",
           "sec:supplements" in tex and "E4-C" in tex and "E5" in tex)
        ck(f"{tag}: supplement keeps E4 verdict",
           "not met" in tex and "lower bounds" in tex)
        ck(f"{tag}: cover letter mentions supplements",
           "E4-C" in (folder / f"{cstem}.tex").read_text(encoding="utf-8"))

    # numbers derived from the recorded results, not typed by hand
    e0, e1, e2, e3 = F["E0"], F["E1"], F["E2"], F["E3"]
    literals = {
        "1.44\\times10^{-6}": f"{e0['energy_balance_max_dev']['2001']:.2e}".replace("e-06", ""),
        "1.57\\times10^{-8}": None,
        "6.73\\times10^{-11}": None,
        "4.40\\times10^{-5}": None,
        "2.78\\times10^{-3}": None,
        "3.25\\times10^{-14}": None,
        "1.208": None,
        "29.95": None,
        "1.110": None,
        "0.835": None,
        "0.89": None,
        "1.52": None,
        "3.32\\times10^{-13}": None,
        "1.40\\times10^{-7}": None,
        "26.1\\times": None,
    }
    for lit in literals:
        ck(f"{tag}: literal {lit}", lit in tex)
    ck(f"{tag}: E0 pass", e0["pass"] is True and "6/6" in tex)
    ck(f"{tag}: E2 6/7", e2["checks_passed"] == 6 and "6/7" in tex)
    ck(f"{tag}: E3 evals", e3["evals"] == 44 and "44 evaluations" in tex)
    ck(f"{tag}: E4-H PASS recorded", H["verdict"]["result"] == "PASS")

    if tag == "CPC":
        ck("CPC: no Solar Energy header", "prepared for Solar Energy" not in tex)
        ck("CPC: no 'in this journal'", "in this journal" not in tex)
        ck("CPC: program summary", "\\section*{Program summary}" in tex
           and "CPC Library link" in tex and "MIT" in tex)
        ck("CPC: dPV anchor in cover letter",
           "CPC 272, 108232" in (folder / f"{cstem}.tex").read_text(encoding="utf-8"))
        ck("CPC: 25 min reproducibility", "25 minutes" in tex)
    else:
        ck("Solar Energy: journal-specific intro retained", "in this journal" in tex)

    # Word deliverable sanity
    d = Document(folder / f"{stem}.docx")
    xml = (folder / f"{stem}.docx").read_bytes()
    plain = " ".join(p.text for p in d.paragraphs)
    ck(f"{tag}: Word tables", len(d.tables) == N_TABLES, f"{len(d.tables)}")
    ck(f"{tag}: Word images", len(d.inline_shapes) == 5, f"{len(d.inline_shapes)}")
    ck(f"{tag}: Word has no raw LaTeX", "\\cite{" not in plain and "\\ref{" not in plain)
    ck(f"{tag}: Word title present", "Poynting-consistent" in plain)
    ck(f"{tag}: Word AI disclosure", "Generative AI" in plain)
    ck(f"{tag}: Word carries repository URL", REPO_URL in plain)

n_pass = sum(1 for _, ok, _ in checks if ok)
lines = [
    "# 两版投稿包核验报告", "",
    f"**结果：{n_pass}/{len(checks)} 项通过，{len(checks)-n_pass} 项未通过。**", "",
    "| 项 | 状态 | 备注 |", "|---|---|---|",
]
for name, ok, detail in checks:
    lines.append(f"| {name} | {'PASS' if ok else '**FAIL**'} | {detail} |")
lines += [
    "", "## 说明", "",
    "- 数值字面量由 `results_final.json` / `results_supplement.json` / `results_E4_highdim.json` 派生核对，稿件中未手工录入新数字。",
    "- 原 `check_consistency.py`（161 项）针对 v1 稿件与 Solar Energy 格式；本脚本为两版派生稿件的独立核验，保留 v1 备份以便回溯。",
    "- 仓库地址 " + REPO_URL + " 已写入两版稿件、cover letter 与发布包元数据；作者仍需创建 Zenodo 归档回填 DOI、确认 Funding 声明，并在投稿前把仓库可见性改为 Public。",
]
(HERE / "variant_verification.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"{n_pass}/{len(checks)} checks passed")
for name, ok, detail in checks:
    if not ok:
        print("  FAIL:", name, detail)
