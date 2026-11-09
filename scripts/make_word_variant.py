"""
UniDD -- build the editable Word version of the Solar Energy manuscript.

Run:  python make_word.py
Out:  unidd_solar_energy.docx

The LaTeX file (`unidd_solar_energy.tex`) is the single source of truth.  This
script derives a Word-specific intermediate from it:

  * resolves every \\ref / \\eqref / \\cite using the compiled .aux file, so no
    raw label keys survive in the Word document;
  * expands the custom macros (\\dd, \\ee, \\Vt, \\kb, \\pder) into plain amsmath;
  * splits `aligned` equations into plain display maths that Pandoc's math
    parser can convert to editable Word OMML;
  * swaps the PDF figures for PNG so Word can actually display them;
  * numbers figures/tables/equations explicitly, because Word has no automatic
    LaTeX-style counters;
  * converts the embedded bibliography into editable numbered paragraphs;
  * converts the table \\multicolumns into ordinary rows.

Pandoc produces the DOCX, then python-docx applies the journal-style layout
(Times New Roman 12 pt, double spacing, line and page numbering, sized figures).
No scientific content is retyped: every sentence comes from the .tex source.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SRC = HERE / "unidd_solar_energy.tex"
AUX = HERE / "unidd_solar_energy.aux"
BUILD = HERE / "_build"
BUILD.mkdir(exist_ok=True)
WORD_TEX = BUILD / "unidd_word.tex"
OUT = HERE / "unidd_solar_energy.docx"

raw = SRC.read_text(encoding="utf-8")
aux = AUX.read_text(encoding="utf-8")

# --------------------------------------------------------------- aux labels
labels: dict[str, str] = {}
for m in re.finditer(r"\\newlabel\{([^}]+)\}\{\{([^}]+)\}", aux):
    labels[m.group(1)] = m.group(2)

bib_keys = re.findall(r"\\bibitem\{([^}]+)\}", raw)
bib_num = {k: i + 1 for i, k in enumerate(bib_keys)}


def braced(s: str, i: int) -> tuple[str, int]:
    """Return the content of the brace group starting at s[i] == '{'."""
    assert s[i] == "{"
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    raise ValueError("unbalanced braces")


def expand_macros(s: str) -> str:
    """Replace the manuscript's private macros with portable LaTeX."""
    # \pder{...}{...} may contain nested braces; parse both arguments.
    out, i = [], 0
    while True:
        j = s.find(r"\pder", i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        k = j + len(r"\pder")
        a, k = braced(s, k)
        b, k = braced(s, k)
        out.append(r"\frac{\partial " + a + r"}{\partial " + b + "}")
        i = k
    s = "".join(out)
    s = re.sub(r"\\dd\b", lambda m: r"\mathrm{d}", s)
    s = re.sub(r"\\ee\b", lambda m: r"\mathrm{e}", s)
    s = re.sub(r"\\Vt\b", lambda m: r"V_{\mathrm{T}}", s)
    s = re.sub(r"\\kb\b", lambda m: r"k_{\mathrm{B}}", s)
    s = re.sub(r"\\R\b", lambda m: r"\mathcal{R}", s)
    # Pandoc's TeX-math parser does not know \Bigl / \Bigr; plain brackets
    # are visually identical here and always convert to editable OMML.
    s = s.replace(r"\Bigl[", "[").replace(r"\Bigr]", "]")
    s = s.replace(r"\Bigl(", "(").replace(r"\Bigr)", ")")
    s = s.replace(r"\mbox{\texttt{", r"\texttt{")
    # \mbox{...} wrapping became \texttt{...}} -- drop the now-extra brace
    s = re.sub(r"(\\texttt\{experiments\\_final\.py\})\}", r"\1", s)
    s = re.sub(r"(\\texttt\{experiments\\_supplement\.py\})\}", r"\1", s)
    return s


def resolve_refs(s: str) -> str:
    """Replace LaTeX cross-references and citations with literal numbers."""
    # Longest, most specific prefixes first.
    s = re.sub(r"Figure~\\ref\{([^}]+)\}",
               lambda m: "Figure " + labels[m.group(1)], s)
    s = re.sub(r"Table~\\ref\{([^}]+)\}",
               lambda m: "Table " + labels[m.group(1)], s)
    s = re.sub(r"Section~\\ref\{([^}]+)\}",
               lambda m: "Section " + labels[m.group(1)], s)
    s = re.sub(r"Equation~\\eqref\{([^}]+)\}",
               lambda m: "Equation (" + labels[m.group(1)] + ")", s)
    s = re.sub(r"Fig\.~\\ref\{([^}]+)\}",
               lambda m: "Fig. " + labels[m.group(1)], s)
    s = re.sub(r"Eq\.~\\eqref\{([^}]+)\}",
               lambda m: "Eq. (" + labels[m.group(1)] + ")", s)
    s = re.sub(r"\\eqref\{([^}]+)\}", lambda m: "(" + labels[m.group(1)] + ")", s)
    s = re.sub(r"\\ref\{([^}]+)\}", lambda m: labels[m.group(1)], s)
    s = re.sub(r"~?\\cite\{([^}]+)\}",
               lambda m: "[" + ",".join(
                   str(bib_num[k.strip()]) for k in m.group(1).split(",")) + "]", s)
    return s


def transform_equation(block: str) -> str:
    """One `equation` environment -> pandoc-safe display maths with a number."""
    lm = re.search(r"\\label\{([^}]+)\}", block)
    n = labels[lm.group(1)] if lm else None
    block = re.sub(r"\s*\\label\{[^}]+\}", "", block)
    body = block.replace(r"\begin{equation}", "").replace(r"\end{equation}", "")
    am = re.search(r"\\begin\{aligned\}(.*?)\\end\{aligned\}", body, re.S)
    if am:
        lines = [x.strip() for x in re.split(r"\\\\", am.group(1)) if x.strip()]
        lines = [x.replace("&", " ").replace(r"\nonumber", "").strip()
                 for x in lines]
        if n:
            lines[-1] += r"\quad (" + n + ")"
        return "\n".join("\\[\n" + x + "\n\\]" for x in lines)
    body = body.strip()
    if n:
        body += r"\quad (" + n + ")"
    return "\\[\n" + body + "\n\\]"


def transform_floats(s: str) -> str:
    """Number captions, use PNG figures and flatten \\multicolumn rows."""
    pat = re.compile(r"\\begin\{(figure|table)\}(\[[^]]*\])?(.*?)\\end\{\1\}", re.S)

    def repl(m: re.Match) -> str:
        kind, opt, body = m.group(1), m.group(2) or "", m.group(3)
        lm = re.search(r"\\label\{([^}]+)\}", body)
        n = labels[lm.group(1)] if lm else "?"
        body = re.sub(r"\s*\\label\{[^}]+\}", "", body)
        body = body.replace(r"\centering", "").replace(r"\small", "")

        # caption -> explicit "Figure N. " / "Table N. "
        ci = body.find(r"\caption")
        if ci >= 0:
            bi = body.find("{", ci)
            content, end = braced(body, bi)
            prefix = "Figure " if kind == "figure" else "Table "
            body = body[:ci] + r"\caption{" + prefix + n + ". " + content + "}" + body[end:]

        body = re.sub(r"\\includegraphics\[[^]]*\]\{figures/([^}.]+)\.pdf\}",
                      r"\\includegraphics{figures/\1.png}", body)

        # flatten \multicolumn{N}{align}{text} in tables
        tab = re.search(r"\\begin\{tabular\}\{([^}]+)\}", body)
        ncols = len(re.sub(r"[^lcr]", "", tab.group(1))) if tab else 1
        while True:
            mi = re.search(r"\\multicolumn\{\d+\}\{[^}]*\}\{", body)
            if not mi:
                break
            bi = body.find("{", mi.start() + len(r"\multicolumn"))
            # first two arguments
            _, p = braced(body, bi)
            _, p = braced(body, p)
            text, p = braced(body, p)
            body = body[:mi.start()] + text + " &" * (ncols - 1) + " " + body[p:]
        return r"\begin{" + kind + "}" + opt + body + r"\end{" + kind + "}"

    return pat.sub(repl, s)


def transform_bibliography(bib_src: str) -> str:
    """Editable numbered reference list instead of `thebibliography`."""
    parts = re.split(r"\\bibitem\{[^}]+\}", bib_src)
    entries = [re.sub(r"\s+", " ", p).strip() for p in parts[1:]]
    out = [r"\section*{References}", ""]
    for i, e in enumerate(entries, 1):
        out.append(f"[{i}] {e}")
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------- front matter
title = re.search(r"\\title\{(.*?)\}\n\n", raw, re.S).group(1)
title = re.sub(r"\s+", " ", title).strip()
abstract = re.sub(r"\s+", " ", re.search(
    r"\\begin\{abstract\}(.*?)\\end\{abstract\}", raw, re.S).group(1)).strip()
keywords = re.sub(r"\s+", " ", re.search(
    r"\\begin\{keyword\}(.*?)\\end\{keyword\}", raw, re.S).group(1)).strip()
keywords = "; ".join(k.strip() for k in keywords.split(r"\sep"))
addresses = dict(re.findall(r"\\address\[([^]]+)\]\{(.*?)\}\n", raw, re.S))
addresses = {k: re.sub(r"\s+", " ", v).strip() for k, v in addresses.items()}

front = "\n\n".join([
    "WORDTITLE:: " + title,
    r"WORDAUTHORS:: Qiong Yan\textsuperscript{1}, "
    r"Peide Yang\textsuperscript{2,3,*}",
    "WORDAFFIL1:: " + addresses["addr1"],
    "WORDAFFIL2:: " + addresses["addr2"],
    "WORDAFFIL3:: " + addresses["addr3"],
    "WORDCORR:: * Corresponding author: Peide Yang (yangpd@xujc.com); "
    "Qiong Yan (381007382@qq.com).",
    "WORDABSHEAD:: ABSTRACT",
    "WORDABSTRACT:: " + abstract,
    "WORDKEYWORDS:: Keywords: " + keywords,
]) + "\n\n\\newpage\n\n"

# ------------------------------------------------------------------ body
start = raw.index(r"\end{frontmatter}") + len(r"\end{frontmatter}")
bib_start = raw.index(r"\begin{thebibliography}")
body = raw[start:bib_start]
bib_src = raw[bib_start:raw.index(r"\end{thebibliography}")]

body = resolve_refs(body)
body = transform_floats(body)
body = expand_macros(body)
# equations (both plain and `aligned`) -> pandoc-safe display maths
eq_pat = re.compile(r"\\begin\{equation\}.*?\\end\{equation\}", re.S)
body = eq_pat.sub(lambda m: transform_equation(m.group()), body)
# stray labels outside floats/equations (sections)
body = re.sub(r"\s*\\label\{[^}]+\}", "", body)
body = re.sub(r"\\begin\{table\}\[[^]]*\]", lambda m: r"\begin{table}", body)
body = re.sub(r"\\begin\{figure\}\[[^]]*\]", lambda m: r"\begin{figure}", body)
body = body.replace(r"\end{document}", "").strip()

references = transform_bibliography(bib_src)

word_src = "\n".join([
    r"\documentclass{article}",
    r"\usepackage{amsmath,amssymb}",
    r"\usepackage{graphicx}",
    r"\usepackage{booktabs}",
    r"\begin{document}",
    front,
    body,
    "",
    references,
    "",
    r"\end{document}",
    "",
])
WORD_TEX.write_text(word_src, encoding="utf-8")

# ------------------------------------------------------------------ pandoc
cmd = ["pandoc", str(WORD_TEX), "-f", "latex", "-t", "docx",
       "--number-sections", "--resource-path=" + str(HERE),
       "-o", str(OUT)]
p = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
if p.returncode:
    print(p.stdout, p.stderr)
    sys.exit("pandoc failed")
if p.stderr.strip():
    print("[pandoc warnings]", p.stderr.strip()[:2000])

# ------------------------------------------------------------- Word styling
doc = Document(OUT)
sec = doc.sections[0]
sec.top_margin = sec.bottom_margin = Inches(1.0)
sec.left_margin = sec.right_margin = Inches(1.0)

normal = doc.styles["Normal"]
normal.font.name = "Times New Roman"
normal.font.size = Pt(12)
normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
normal.paragraph_format.line_spacing = 2.0
normal.paragraph_format.space_after = Pt(0)

def style_named(document, name):
    """Pandoc capitalises built-in style names; python-docx expects lower case."""
    for st in document.styles:
        if st.name.lower() == name.lower():
            return st
    raise KeyError(name)


for hs in ("Heading 1", "Heading 2"):
    st = style_named(doc, hs)
    st.font.name = "Times New Roman"
    st.font.size = Pt(12)
    st.font.bold = True
    st.paragraph_format.line_spacing = 2.0
    st.paragraph_format.space_before = Pt(12)
    st.paragraph_format.space_after = Pt(6)

MARKERS = {
    "WORDNOTE": dict(size=9, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
                     italic=True, spacing=1.0),
    "WORDTITLE": dict(size=16, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER,
                      spacing=1.0, after=14),
    "WORDAUTHORS": dict(size=12, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
                        spacing=1.0, after=10),
    "WORDAFFIL1": dict(size=10, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
                       spacing=1.0),
    "WORDAFFIL2": dict(size=10, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
                       spacing=1.0),
    "WORDAFFIL3": dict(size=10, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
                       spacing=1.0),
    "WORDCORR": dict(size=10, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER,
                     spacing=1.0, after=14),
    "WORDABSHEAD": dict(size=12, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER,
                        spacing=1.0, after=6),
    "WORDABSTRACT": dict(size=11, bold=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                         spacing=1.0, after=10, indent=0.4),
    "WORDKEYWORDS": dict(size=11, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT,
                         spacing=1.0),
}

for para in doc.paragraphs:
    m = re.match(r"^(WORD[A-Z0-9]+)::\s*(.*)$", para.text, re.S)
    if not m or m.group(1) not in MARKERS:
        continue
    key, text = m.group(1), m.group(2)
    # strip the marker from the first run, preserving all math runs
    if para.runs:
        first = para.runs[0]
        first.text = re.sub(r"^WORD[A-Z0-9]+::\s*", "", first.text)
    cfg = MARKERS[key]
    para.alignment = cfg["align"]
    para.paragraph_format.line_spacing = cfg["spacing"]
    para.paragraph_format.space_after = Pt(cfg.get("after", 0))
    if cfg.get("indent"):
        para.paragraph_format.left_indent = Inches(cfg["indent"])
        para.paragraph_format.right_indent = Inches(cfg["indent"])
    for r in para.runs:
        r.font.name = "Times New Roman"
        r.font.size = Pt(cfg["size"])
        r.bold = cfg["bold"]
        r.italic = cfg.get("italic", False)

# Pandoc drops LaTeX \newpage; put the manuscript body on its own page,
# matching the PDF preprint (title/abstract on page 1).
for para in doc.paragraphs:
    if para.style.name.startswith("Heading") and re.match(r"^1\t", para.text):
        para.paragraph_format.page_break_before = True
        break

# single spacing for captions, tables and equation paragraphs
for para in doc.paragraphs:
    if para.style.name in ("Image Caption", "Table Caption", "Captioned Figure"):
        para.paragraph_format.line_spacing = 1.0
        for r in para.runs:
            r.font.size = Pt(10)
    if not para.text.strip():  # OMML-only equations
        para.paragraph_format.line_spacing = 1.0
        para.paragraph_format.space_after = Pt(6)
for t in doc.tables:
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for row in t.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                para.paragraph_format.line_spacing = 1.0
                para.paragraph_format.space_after = Pt(0)
                for r in para.runs:
                    r.font.name = "Times New Roman"
                    r.font.size = Pt(9)

# size the embedded figures to the printable width, preserving aspect ratio
for shape in doc.inline_shapes:
    cx, cy = shape.width, shape.height
    new_w = Inches(6.3)
    shape.width = new_w
    if cx:
        shape.height = int(cy * new_w / cx)

# continuous line numbering (Elsevier preprint style)
sectPr = sec._sectPr
ln = OxmlElement("w:lnNumType")
ln.set(qn("w:countBy"), "1")
ln.set(qn("w:start"), "1")
ln.set(qn("w:distance"), "360")
sectPr.append(ln)

# centred page number in the footer
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = fp.add_run()
run.font.name = "Times New Roman"
run.font.size = Pt(10)
for el, attrs, txt in (
    ("w:fldChar", {"w:fldCharType": "begin"}, None),
    ("w:instrText", {"xml:space": "preserve"}, "PAGE"),
    ("w:fldChar", {"w:fldCharType": "end"}, None),
):
    node = OxmlElement(el)
    for k, v in attrs.items():
        node.set(qn(k), v)
    if txt is not None:
        node.text = txt
    run._r.append(node)

doc.save(OUT)

# --------------------------------------------------------------- diagnostics
import zipfile
d2 = Document(OUT)
xml = zipfile.ZipFile(OUT).read("word/document.xml").decode("utf-8")
plain = re.sub(r"<[^>]+>", "", xml)
media = [n for n in zipfile.ZipFile(OUT).namelist() if "media/" in n]
print(f"\nWord -> {OUT}")
print(f"  paragraphs {len(d2.paragraphs)}, tables {len(d2.tables)}, "
      f"images {len(d2.inline_shapes)}, OMML nodes {xml.count('<m:oMath')}")
print(f"  media: {media}")
unresolved = re.findall(r"\[(?:eq|fig|tab|sec):[^\]]*\]", plain)
print(f"  unresolved LaTeX labels: {unresolved}")
raw_cmds = re.findall(r"\\(?:cite|ref|eqref|begin|end|includegraphics)\b", plain)
print(f"  raw LaTeX commands in text: {raw_cmds[:10]}")
for token in ("[1]", "[11]", "[22]", "29.95", "27.74", "1.208"):
    print(f"  contains {token}: {token in plain}")  # informational
if unresolved or raw_cmds:
    sys.exit("Word document still contains unresolved LaTeX")
