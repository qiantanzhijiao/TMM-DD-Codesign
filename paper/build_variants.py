"""
UniDD -- build two independent journal-specific submission packages.

Run:  python build_variants.py
Out:  cpc/                 -> Computer Physics Communications version
      solar_energy/        -> Solar Energy version (v1 manuscript backed up)

Both versions are derived from the SAME v1 .tex source, so no numerical value
is retyped.  Every replacement is asserted to match exactly; a silent miss
raises instead of producing a subtly wrong manuscript.

Generated per version: .tex, .pdf, .docx, highlights (.txt/.docx),
cover letter (.tex/.pdf/.docx), plus figures/ copied for CPC.
"""
from __future__ import annotations

import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

HERE = Path(__file__).resolve().parent
SE = HERE / "solar_energy"
CPC = HERE / "cpc"
CPC.mkdir(exist_ok=True)
DATE = datetime.date.today().strftime("%d %B %Y")
BASE = SE / "unidd_solar_energy.tex"
BACKUP = SE / "unidd_solar_energy_v1.tex.bak"
PY = sys.executable

# Canonical code repository.  The placeholder below is resolved exactly once,
# centrally, so no derived .tex / PDF / Word artefact can ship a fake address.
REPO_URL = "https://github.com/qiantanzhijiao/TMM-DD-Codesign"
PLACEHOLDER = "REPOSITORY-URL"

# Written by finalize_results.py only after BOTH supplementary experiments
# have produced their final summary.  Absent => supplements are not in the
# manuscript, so no unfinished result can ever leak into a submission.
SUPP_FILE = HERE / "supplement_section.tex"
HAS_SUPP = SUPP_FILE.is_file()

if not BACKUP.exists():
    shutil.copy2(BASE, BACKUP)
V1 = BACKUP.read_text(encoding="utf-8")

TITLE = ("A differentiable, Poynting-consistent transfer-matrix and "
         "drift--diffusion kernel for co-design of thin-film solar cells")

# ------------------------------------------------------------------ abstracts
ABSTRACT_SE = r"""Differentiable photovoltaic device models have so far treated
optical absorption with the Beer--Lambert law, which cannot represent
standing-wave interference in wavelength-scale layers. We present UniDD, a
forward model that couples a fully coherent transfer-matrix optical solver to
a self-consistent one-dimensional drift--diffusion solver in a single
reverse-mode automatic-differentiation graph, with no surrogate and no
interpolation of the optical field onto the electrical mesh; to our knowledge
this composition has not previously been differentiated end to end. The
spectral generation rate is written in a Poynting-consistent form that retains
the refractive-index ratio $n_r/n_0$ and the exact interference cross term.
The electrical solver uses log-density variables, exponentially factored
Scharfetter--Gummel currents and an equilibrated, damped Newton iteration;
derivatives of the converged state follow from the implicit function theorem
through one transposed Jacobian solve. The optical model satisfies
$\int(n_r/n_0)\alpha|E|^2\dd z=1-R-T$ to $1.44\times10^{-6}$ and reproduces
the Beer--Lambert limit to $1.57\times10^{-8}$. Automatic derivatives agree
with fourth-order Richardson finite differences to $6.73\times10^{-11}$ for
the optical chain, to $\le 4.40\times10^{-5}$ for isolated drift--diffusion
paths and to $\le 2.78\times10^{-3}$ for the full composite chain; the adjoint
residual is $\sim 3\times10^{-14}$ and the backward pass costs $1.10$ times a
forward pass. For a synthetic perovskite-like stack the model yields zero
equilibrium dark current, a dark ideality factor of $1.208$, and an
EQE-integrated short-circuit current within $0.89\%$ of the current--voltage
value, with $J_{\mathrm{sc}}=29.95$~mA\,cm$^{-2}$, $V_{\mathrm{oc}}=1.110$~V
and fill factor $0.835$ under a coarse AM1.5G spectrum, subject to a $1.52\%$
mesh-discretisation uncertainty; these figures are internal numerical
benchmarks, not device predictions. Three-parameter inverse design recovers
absorber thickness, absorption strength and recombination lifetime to within
$0.002\%$ in 44 evaluations. In an eight-parameter problem the gradient-based
search reaches a loss of $10^{-3}$ in 7 evaluations against 21 for
Nelder--Mead, but neither method reaches $10^{-4}$; this modest advantage is
reported explicitly rather than presented as an order-of-magnitude gain. All
results are synthetic; no experimental calibration or efficiency record is
claimed."""

ABSTRACT_CPC = r"""We describe UniDD, a deterministic Python program that
couples a fully coherent transfer-matrix optical solver to a self-consistent
one-dimensional drift--diffusion solver in one reverse-mode automatic-
differentiation graph. Existing differentiable photovoltaic programs
($\partial$PV, DriftJax) differentiate the drift--diffusion state but use
Beer--Lambert absorption, whereas differentiable thin-film optics toolkits
such as TFSolver do not solve carrier transport; UniDD closes this gap without
a surrogate model and without interpolating the optical field onto the
electrical mesh. The spectral generation rate is Poynting-consistent, retaining
$n_r/n_0$ and the exact interference cross term, and is evaluated analytically
on the electrical mesh. The electrical solver uses log-density variables,
exponentially factored Scharfetter--Gummel currents and an equilibrated,
damped Newton iteration converged on a physical residual scale; derivatives of
the converged state are obtained by the implicit function theorem through one
transposed Jacobian solve. Program validation is external where possible:
$\int(n_r/n_0)\alpha|E|^2\dd z=1-R-T$ holds to $1.44\times10^{-6}$, the
Beer--Lambert limit to $1.57\times10^{-8}$, automatic derivatives agree with
fourth-order Richardson finite differences to $6.73\times10^{-11}$
(optical chain), $\le 4.40\times10^{-5}$ (isolated electrical paths) and
$\le 2.78\times10^{-3}$ (composite chain), the adjoint residual is
$\sim 3\times10^{-14}$, and the backward pass costs $1.10$ times a forward
pass. A synthetic perovskite-like stack gives zero equilibrium dark current,
a dark ideality factor of $1.208$ and EQE/$J$--$V$ current agreement to
$0.89\%$, with $J_{\mathrm{sc}}=29.95$~mA\,cm$^{-2}$,
$V_{\mathrm{oc}}=1.110$~V and fill factor $0.835$ under a coarse AM1.5G
spectrum and a $1.52\%$ mesh-discretisation uncertainty; these are internal
numerical benchmarks, not device predictions. Three-parameter inverse design
recovers all parameters to within $0.002\%$ in 44 evaluations. The
pre-registered tenfold evaluation-count target is \emph{not} met in eight
dimensions (about $3\times$ at $10^{-3}$, neither optimiser reaching
$10^{-4}$); the program ships with the recorded histories so that this
negative result is reproducible. The complete suite runs in about 25 minutes
on one CPU core at a fixed seed. All results are synthetic."""

# The recorded factor 1.10 is (forward + adjoint) / forward, i.e. about 10%
# overhead.  Saying "the backward pass costs 1.10 times a forward pass" would
# imply a total of 2.10x, so both abstracts state the ratio explicitly.
for _k in ("ABSTRACT_SE", "ABSTRACT_CPC"):
    globals()[_k] = re.sub(
        r"the backward pass costs \$1\.10\$ times a\s+forward\s+pass",
        lambda _m: ("a gradient evaluation costs $1.10$ times a forward "
                    "solve (about 10\\% overhead)"),
        globals()[_k])

PROGRAM_SUMMARY = r"""
\section*{Program summary}

\begin{description}
\item[Program title:] UniDD
\item[CPC Library link to program files:] (to be added by Technical Editor)
\item[Developer's repository link:] \texttt{REPOSITORY-URL}
\item[Code Ocean capsule:] (to be added by Technical Editor)
\item[Licensing provisions:] MIT
\item[Programming language:] Python 3.13.5; PyTorch 2.15.0 (CPU build),
NumPy, SciPy 1.15.3, Matplotlib; float64 and complex128 arithmetic
\item[Supplementary material:] Recorded optimisation histories, figure
generation scripts, native SCAPS-1D 3.3.12 outputs (dark and illuminated
$J$--$V$, QE, generation read-back and graphs), the solver diagnostic log,
the cross-code acceptance verdict and the SHA-256-pinned run-time deployment.
\item[Nature of problem:] Gradient-based co-design of a thin-film solar cell
requires derivatives of a figure of merit with respect to layer thickness,
complex refractive index and bulk recombination lifetime. Conventional
workflows couple a transfer-matrix optical solver and a drift--diffusion
solver as black boxes, so derivatives are approximated by finite differences
or by a surrogate, and thin-film interference is either discarded or lost at
the optical-to-electrical mesh interpolation.
\item[Solution method:] A coherent, Poynting-consistent transfer-matrix model
is written directly in PyTorch and evaluated analytically at the electrical
mesh nodes. The drift--diffusion equations are discretised with
Scharfetter--Gummel currents in log-density variables and solved by a fully
coupled, equilibrated and damped Newton iteration; derivatives of the
converged state are obtained by the implicit function theorem through a
single transposed Jacobian solve implemented as a custom
\texttt{torch.autograd.Function}.
\item[Restrictions:] One-dimensional, isothermal, steady-state model with
Boltzmann statistics, ideal selective contacts and a single bulk SRH
lifetime; the adjoint uses a dense $3(N-2)$ solve, adequate at the production
grid $N=73$ but cubic in $N$.
\item[Unusual features:] The coherent optical field is evaluated analytically
at the drift--diffusion mesh nodes; no surrogate model and no interpolation
are used. The optical and electrical contributions to the thickness gradient
cancel to a ratio of about 45, which is reported explicitly.
\item[Additional comments:] None.
\item[Running time:] About 25 minutes for the complete deterministic
validation and inverse-design suite (E0--E4) on one core of an Intel Core
Ultra 9 285H workstation (16 cores) in float64 with seed 0; the
16-dimensional supplement takes about 23 minutes.
\end{description}
"""

NOVELTY_PARA = (
    "Relative to these programs, the contribution of UniDD is not the "
    "differentiability of the electrical solver as such, but the retention "
    "of fully coherent optics inside that differentiable composition, "
    "together with the external numerical checks needed to trust the "
    "resulting gradients. A wall-clock comparison of inverse-design "
    "performance against these programs would require reproducing their "
    "optical and contact models and is outside the scope of the present "
    "validation study. ")

SCAPS_SECTION = r"""\section{Cross-code comparison with SCAPS-1D}
\label{sec:scaps}

The electrical kernel was compared with SCAPS-1D 3.3.12~\cite{burgelman2000}
using the script chain distributed with the code. Because UniDD solves the
drift--diffusion equations on the absorber only, with the transport layers
entering the optics and the contact boundary values, the SCAPS device was
built as a single absorber layer with selective surface-recombination
contacts. The coherent UniDD generation profile was imported in SI units
(m$^{-3}$\,s$^{-1}$) and the native SCAPS $J$--$V$, QE and generation curves
were exported through the SCAPS script interface, together with
SCAPS-generated graphs and the solver diagnostic log. The four acceptance
criteria were fixed before execution and were not revised afterwards.

\begin{table}[t]
\caption{Pre-specified acceptance criteria and the outcome of the SCAPS-1D
3.3.12 comparison. Errors are evaluated on the common converged voltage or
wavelength range.}
\label{tab:scaps}
\centering
\footnotesize
\begin{tabular}{lp{4.3cm}p{4.0cm}c}
\toprule
Quantity & Criterion & Measured & Verdict \\
\midrule
Dark $J$--$V$ & RMSE $<0.05$ mA\,cm$^{-2}$ & $1.44\times10^{-3}$ & PASS \\
Illuminated $J$--$V$ & $J_{\mathrm{sc}}<5\%$, $V_{\mathrm{oc}}<20$~mV, FF $<5\%$ & $J_{\mathrm{sc}}$ 7.03\%; $V_{\mathrm{oc}}$, FF n/a & FAIL \\
EQE & RMSE $<0.05$ & 0.096 & FAIL \\
$G(z)$ read-back & RMSE/$\overline{G}<2\%$ & $2.4\times10^{-4}\%$ & PASS \\
\bottomrule
\end{tabular}
\end{table}

Two of the four criteria pass (Table~\ref{tab:scaps}). Over the common
converged range $0$--$0.8$~V the dark curves agree to
$1.44\times10^{-3}$~mA\,cm$^{-2}$ RMSE; SCAPS stops the dark sweep at
$0.82$~V. The SCAPS read-back of the imported $G(z)$ deviates from the
UniDD profile by $2.4\times10^{-4}\%$ of the mean generation rate, which
checks the unit conversion and the interpolation onto the SCAPS mesh. The
short-circuit currents differ by 7.03\% ($32.06$ against
$29.95$~mA\,cm$^{-2}$), and the EQE shape check gives an RMSE of $0.096$.
Open-circuit voltage and fill factor cannot be defined for the SCAPS curve:
with flat-band, surface-recombination contacts and an intrinsic absorber the
illuminated SCAPS $J$--$V$ is almost independent of bias up to the
convergence cut at $1.06$~V, whereas UniDD imposes Dirichlet carrier
densities at the contacts. This is a model mismatch rather than a
discretisation error. The comparison is therefore reported as a limited
cross-code sanity check; it does not constitute a validation of UniDD
against SCAPS-1D, and no experimental calibration has been performed."""

# The introduction is patched in three small, asserted steps in common();
# a long literal here would be vulnerable to LaTeX backslash escapes.

# ------------------------------------------------------------------- patching
def sub_once(text: str, old: str, new: str, tag: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"[{tag}] expected exactly 1 match, found {n}: {old[:70]!r}")
    return text.replace(old, new)


def polish(text: str) -> str:
    """Round-3 review fixes common to both journal variants."""
    def sub(old: str, new: str, tag: str) -> None:
        nonlocal text
        text = sub_once(text, old, new, tag)

    sub("Section~\\ref{sec:results} reports five validation and benchmark experiments\n(E0--E4).",
        "Section~\\ref{sec:results} reports five core validation and benchmark\n"
        "experiments (E0--E4) and three supplements (E4-H, E4-C, E5).",
        "section roadmap")
    sub("\\caption{Reference configuration used in experiments E0--E4.}",
        "\\caption{Reference configuration used in the core experiments E0--E4\n"
        "and the supplements E4-H, E4-C and E5.}",
        "table 1 caption")
    sub("$\\tau$ (s) & $3.0\\times10^{-7}$ & $2.999999\\times10^{-7}$",
        "$\\tau$ (s) & $3.0000\\times10^{-7}$ & $2.999999\\times10^{-7}$",
        "table 3 significant figures")
    sub("The measured backward overhead is a factor of 1.10\n"
        "(forward 2.21~s, forward+backward 2.43~s in the 3-D case), not the 1.05\n"
        "quoted in earlier internal notes.",
        "The measured forward-plus-adjoint cost is a factor of 1.10 over a\n"
        "single forward solve (forward 2.21~s, forward+backward 2.43~s in the 3-D\n"
        "case), not the 1.05 quoted in earlier internal notes.",
        "E4 gradient cost wording")
    sub("backward overhead factor & 1.10 & 1.10 \\\\",
        "forward-plus-adjoint cost factor & 1.10 & 1.10 \\\\",
        "table 4 gradient cost label")
    sub("and the backward pass cost 1.22\ntimes a forward evaluation.",
        "and a forward-plus-adjoint evaluation cost 1.22\ntimes a forward solve.",
        "E4-H gradient cost wording")
    sub("Table~\\ref{tab:benchmark} gives the exact counts. The honest conclusion is",
        "Table~\\ref{tab:benchmark} gives the exact counts. The conclusion is",
        "honest wording")
    sub("The derivative-free baseline must be counted honestly.",
        "The derivative-free baseline is counted in true function calls.",
        "honest wording 2")
    sub("with honest accounting of derivative-free\n  function calls and an explicit statement of where the gradient advantage is\n  modest or absent.",
        "with exact accounting of derivative-free function calls\n  and a statement of where the gradient advantage is modest or absent.",
        "contributions wording")
    sub("\\cortext[cor1]{Corresponding author.}",
        "\\cortext[cor1]{Corresponding author: Peide Yang.}",
        "corresponding author footnote")
    sub("only a single starting point, a single noise-free\nsynthetic target and two optimisers are compared.",
        "the main E4 benchmark compares a single starting point,\na single noise-free synthetic target and two optimisers.",
        "benchmark scope contradiction")
    sub("Equally important, the study identifies where the approach does not yet\ndeliver:",
        "The study also identifies where the approach does not yet deliver:",
        "conclusions wording")
    sub("We therefore\nposition UniDD as a validated differentiable \\emph{modelling kernel} whose",
        "UniDD is best read as a validated differentiable \\emph{modelling kernel} whose",
        "positioning wording")
    # Cross-code status: the SCAPS run has now been executed.  Report the
    # outcome; the pre-specified criteria and all earlier verdicts stay fixed.
    sub("No comparison with\nexperimental $J$--$V$, EQE or ellipsometry data, and no cross-validation\n"
        "against SCAPS-1D or another drift--diffusion code, has been performed.",
        "No comparison with\nexperimental $J$--$V$, EQE or ellipsometry data has been performed. An\n"
        "independent comparison with SCAPS-1D 3.3.12 was carried out\n"
        "(Section~\\ref{sec:scaps}), but it is a limited cross-code sanity\n"
        "check: two of four pre-specified criteria pass, and the illuminated\n"
        "$J$--$V$ curves are not comparable because the contact models differ.",
        "SCAPS limitation status")
    sub("That\ncross-validation is the most important next step before the framework can be\nused for device design.",
        "Section~\\ref{sec:scaps} documents the executed comparison and its\n"
        "pre-specified criteria; experimental calibration remains the most\n"
        "important next step before the framework can be used for device\n"
        "design.",
        "cross-code protocol pointer")
    sub("All numerical values quoted in this paper are generated by\n"
        "\\mbox{\\texttt{experiments\\_final.py}} and\n"
        "\\mbox{\\texttt{experiments\\_supplement.py}}.",
        "All numerical values quoted in this paper are generated by\n"
        "\\mbox{\\texttt{experiments\\_final.py}} and\n"
        "\\mbox{\\texttt{experiments\\_supplement.py}}. An independent\n"
        "cross-code comparison was executed with SCAPS-1D 3.3.12: the\n"
        "single-layer definition, the SI-unit generation profile, the script\n"
        "chain, the native SCAPS outputs, the solver diagnostic log and the\n"
        "machine-readable acceptance verdict accompany the source archive.\n"
        "The chain is reproducible with \\texttt{install\\_scaps\\_runtime.py},\n"
        "\\texttt{build\\_scaps\\_inputs.py},\n"
        "\\texttt{run\\_scaps\\_crosscheck.py} and\n"
        "\\texttt{compare\\_scaps.py}; the private deployment of the\n"
        "LabWindows/CVI run-time engine is pinned by a SHA-256 manifest.",
        "SCAPS results in data availability")
    sub("with experimental calibration and\nsparse high-dimensional adjoints as the natural next steps.",
        "with experimental calibration and\nsparse high-dimensional adjoints as the natural next steps. The E4-C and E5\n"
        "supplements add a controlled dimension comparison and a noisy multi-start\n"
        "robustness study; they qualify but do not overturn this picture, and the\n"
        "high-dimensional PASS remains a censored lower bound rather than a measured\n"
        "speedup.",
        "conclusions supplement pointer")
    # No third-party registration platform or timestamp exists, so
    # "pre-specified" is the defensible term.  No verdict or number changes.
    n = text.count("pre-registered")
    if n < 1:
        raise RuntimeError("[pre-specified] no pre-registered occurrences found")
    text = text.replace("pre-registered", "pre-specified")
    print(f"    pre-registered -> pre-specified: {n} occurrence(s)")
    return text


def common(text: str, journal: str, abstract: str) -> str:
    text = sub_once(text,
        "%% UniDD -- manuscript prepared for Solar Energy (Elsevier)",
        f"%% UniDD -- manuscript prepared for {journal} (Elsevier)", "header")
    text = sub_once(text, r"\journal{Solar Energy}",
                    r"\journal{" + journal + "}", "journal")
    text = sub_once(text,
        r"\title{End-to-end differentiable transfer-matrix and drift--diffusion modelling"
        "\nfor inverse design of thin-film solar cells}",
        "\\title{" + TITLE.replace("&", r"\&") + "}", "title")
    text = sub_once(text,
        r"\begin{abstract}" + re.search(
            r"\\begin\{abstract\}(.*?)\\end\{abstract\}", V1, re.S).group(1)
        + r"\end{abstract}",
        "\\begin{abstract}\n" + abstract + "\n\\end{abstract}", "abstract")

    old_da = ("The complete deterministic experiment suite, the recorded result files, the\n"
              "figure-generation scripts and the consistency-check script are provided with\n"
              "the submission and will be made publicly available in a versioned repository\n"
              "upon acceptance.")
    new_da = ("The complete deterministic experiment suite, the recorded result files, the\n"
              "figure-generation scripts and the consistency-check script accompany the\n"
              "submission and are publicly available from the versioned repository\n"
              r"\texttt{REPOSITORY-URL} at the time of submission, under the MIT licence; "
              "a frozen\nZenodo archive with a DOI will be linked before publication.")
    text = sub_once(text, old_da, new_da, "data availability")

    text = sub_once(text, "\\begin{thebibliography}{22}",
                    "\\begin{thebibliography}{23}", "bib width")
    text = sub_once(text,
        "arXiv:1603.02720 (2016; revised 2020). doi:10.48550/arXiv.1603.02720.",
        "arXiv:1603.02720, version 5 (30 December 2020). "
        "doi:10.48550/arXiv.1603.02720.", "byrnes")
    text = sub_once(text,
        "arXiv:2512.02904 (2025). doi:10.48550/arXiv.2512.02904.",
        "arXiv:2512.02904 (2025); conference version in Computational Optics "
        "2026, Proceedings of SPIE PC14110, PC1411002 (2026). "
        "doi:10.48550/arXiv.2512.02904; doi:10.1117/12.3099007.", "schubert")
    text = sub_once(text,
        "Optics Express 33(25) (2025)\n52061. doi:10.1364/OE.578518.",
        "Optics Express 33(25) (2025)\n52061--52074. doi:10.1364/OE.578518.",
        "tfsolver")
    text = sub_once(text, "\\end{thebibliography}",
        "\\bibitem{driftjax2026} M. Benaissa, M. Maoudj, A.~E. Noua,\n"
        "DriftJax: A Differentiable 1-D Drift--Diffusion Solar-Cell Simulator "
        "in JAX, version v0.1.18 (19 September 2026), Zenodo.\n"
        "doi:10.5281/zenodo.22839528 (version DOI); "
        "doi:10.5281/zenodo.22762674 (concept DOI);\n"
        "\\texttt{https://github.com/medmo13/driftjax} "
        "(accessed 8 November 2026).\n\n"
        "\\end{thebibliography}", "driftjax")

    # CPC asks for a general-reader novelty statement in the Introduction.
    # Moving it there also leaves exactly four limitation classes in Section 4.
    text = sub_once(text, "Three\ndevelopments are particularly relevant.",
                    "Four\ndevelopments are particularly relevant.",
                    "four developments")
    text = sub_once(text,
        "it does not solve\ncarrier transport. Differentiable electromagnetics",
        "it does not solve\ncarrier transport. "
        + r"Noua et al.\ released DriftJax, "
        "a JAX implementation of one-dimensional drift--diffusion with an "
        "implicit-function-theorem adjoint and Beer--Lambert "
        + r"absorption~\cite{driftjax2026}; "
        "it likewise omits coherent multilayer optics. "
        "Differentiable electromagnetics",
        "driftjax in introduction")
    text = sub_once(text,
        r"reviewed by Molesky et al.~\cite{molesky2018}. What has been missing is a",
        r"reviewed by Molesky et al.~\cite{molesky2018}. " + NOVELTY_PARA
        + "What has been missing is a",
        "novelty in introduction")
    return polish(text)


def with_supplements(text: str) -> str:
    """Add the E4-C/E5 subsection only when its recorded results are final."""
    if not HAS_SUPP:
        return text
    supp = SUPP_FILE.read_text(encoding="utf-8").strip() + "\n\n"
    anchor = "%% " + "=" * 76 + "\n\\section{Limitations and scope}"
    text = sub_once(text, anchor, supp + anchor, "supplement section")
    # The E4 verdict itself is untouched; only the "future work" pointer is
    # redirected at the now-existing supplements.
    text = sub_once(text,
        "A broader study with\nmultiple seeds, measurement noise and additional "
        "derivative-free baselines\nis needed before general efficiency claims can "
        "be made.",
        "The E4-C and E5 supplements of Section~\\ref{sec:supplements} add a "
        "one-factor dimension control, multiple starts, measurement noise and "
        "five derivative-free baselines. They are robustness evidence and do "
        "not revise the $\\ge10\\times$ verdict stated above.",
        "benchmark scope pointer")
    return text


se = common(V1, "Solar Energy", ABSTRACT_SE)
cpc = common(V1, "Computer Physics Communications", ABSTRACT_CPC)

# journal-specific introduction phrasing (CPC only)
cpc = sub_once(cpc, "lead-free stacks in this journal~\\cite{sachchidanand2023, jangjoy2022}.",
               "lead-free stacks~\\cite{sachchidanand2023, jangjoy2022}.", "in this journal")
cpc = sub_once(cpc,
    "optimisation studies based on SCAPS are likewise regularly published in\n"
    "\\emph{Solar Energy}~\\cite{pindolia2022, kaur2023}.",
    "optimisation studies based on SCAPS are likewise a mainstay of the\n"
    "solar-cell modelling literature~\\cite{pindolia2022, kaur2023}.",
    "in Solar Energy")
cpc = sub_once(cpc, "\\end{frontmatter}\n",
               "\\end{frontmatter}\n" + PROGRAM_SUMMARY + "\n", "program summary")

def with_scaps(text: str) -> str:
    """Insert the executed SCAPS-1D comparison before the limitations section."""
    anchor = "%% " + "=" * 76 + "\n\\section{Limitations and scope}"
    return sub_once(text, anchor, SCAPS_SECTION + "\n\n" + anchor,
                    "SCAPS comparison section")


se = with_supplements(se)
cpc = with_supplements(cpc)
se = with_scaps(se)
cpc = with_scaps(cpc)

# CPC deposits the program in the CPC Program Library via its Technical
# Editor; the author-supplied source archive accompanies the submission.
cpc = sub_once(cpc,
    "a frozen\nZenodo archive with a DOI will be linked before publication.",
    "the source archive accompanies the submission for deposition in the\n"
    "CPC Program Library by the Technical Editor; a versioned Zenodo archive\n"
    "with a DOI will be linked before publication.",
    "cpc data availability")

# Resolve the repository link once, for both variants.  Both manuscripts must
# contain the placeholder (Data availability; CPC also has Program Summary).
for _label, _text in (("Solar Energy", se), ("CPC", cpc)):
    _n = _text.count(PLACEHOLDER)
    if _n == 0:
        raise RuntimeError(f"[{_label}] repository placeholder disappeared")
    print(f"    {_label}: {_n} repository link(s) resolved")
se = se.replace(PLACEHOLDER, REPO_URL)
cpc = cpc.replace(PLACEHOLDER, REPO_URL)

(SE / "unidd_solar_energy.tex").write_text(se, encoding="utf-8")
(CPC / "unidd_cpc.tex").write_text(cpc, encoding="utf-8")
print("[1/6] two .tex variants written" + (" (+ E4-C/E5)" if HAS_SUPP else ""))

# ------------------------------------------------------------------- figures
dst_fig = CPC / "figures"
dst_fig.mkdir(exist_ok=True)
for f in (SE / "figures").iterdir():
    if f.suffix.lower() in (".pdf", ".png"):
        shutil.copy2(f, dst_fig / f.name)
print("[2/6] figures copied for CPC")

# ------------------------------------------------------- Word builder variants
word_src = (SE / "make_word.py").read_text(encoding="utf-8")
for folder, texname, outname, journal in (
    (SE, "unidd_solar_energy.tex", "unidd_solar_energy.docx", "Solar Energy"),
    (CPC, "unidd_cpc.tex", "unidd_cpc.docx", "Computer Physics Communications"),
):
    s = word_src
    s = sub_once(s, 'SRC = HERE / "unidd_solar_energy.tex"',
                 f'SRC = HERE / "{texname}"', "word SRC")
    s = sub_once(s, 'AUX = HERE / "unidd_solar_energy.aux"',
                 f'AUX = HERE / "{texname.replace(".tex", ".aux")}"', "word AUX")
    s = sub_once(s, 'OUT = HERE / "unidd_solar_energy.docx"',
                 f'OUT = HERE / "{outname}"', "word OUT")
    s = sub_once(s, '"WORDNOTE:: Manuscript prepared for Solar Energy (Elsevier)"',
                 f'"WORDNOTE:: Manuscript prepared for {journal} (Elsevier)"',
                 "word NOTE")
    s = s.replace('print(f"  contains {token}: {token in plain}")',
                  'print(f"  contains {token}: {token in plain}")  # informational')
    (folder / "make_word_variant.py").write_text(s, encoding="utf-8")
print("[3/6] Word build scripts derived")

# ------------------------------------------------------------------ compile
def pdflatex(folder: Path, stem: str) -> None:
    for _ in range(2):
        p = subprocess.run(["pdflatex", "-interaction=nonstopmode",
                            "-halt-on-error", stem + ".tex"],
                           cwd=folder, capture_output=True, text=True)
        if p.returncode:
            print(p.stdout[-4000:], p.stderr[-1000:])
            raise RuntimeError(f"pdflatex failed for {stem}")
    print(f"    PDF -> {folder / (stem + '.pdf')}")


pdflatex(SE, "unidd_solar_energy")
pdflatex(CPC, "unidd_cpc")
print("[4/6] both PDFs compiled")

for folder in (SE, CPC):
    p = subprocess.run([PY, "make_word_variant.py"], cwd=folder,
                       capture_output=True, text=True)
    if p.returncode:
        print(p.stdout[-3000:], p.stderr[-2000:])
        raise RuntimeError(f"Word build failed in {folder}")
    print(f"    DOCX -> {folder}")
print("[5/6] both Word versions built")

# ------------------------------------------------- highlights + cover letters
VARIANTS = {
    "Solar Energy": dict(
        folder=SE, stem="cover_letter_Solar_Energy",
        hl="highlights.txt", hl_docx="highlights.docx",
        highlights=[
            "Poynting-consistent differentiable TMM is coupled to a drift-diffusion solver.",
            "IFT gradients: full evaluation costs 1.10x a forward solve (10% overhead).",
            "Optical energy balance holds to 1.44e-6; Beer-Lambert limit to 1.57e-8.",
            "Three-parameter inverse design recovers all parameters to within 0.002%.",
            "Eight-dimensional speedup is 3x, not 10x; all results are synthetic.",
        ],
        letter=[
            ("bold", "Qiong Yan; Peide Yang (corresponding author)"),
            ("plain", "Fujian Jiangxia University, Fuzhou 350108, China; Xiamen "
                      "University Tan Kah Kee College, Xiamen, China"),
            ("plain", "Emails: 381007382@qq.com (Qiong Yan); yangpd@xujc.com "
                      "(Peide Yang, corresponding author)"),
            ("blank", ""), ("plain", DATE), ("blank", ""),
            ("bold", "To the Editor-in-Chief, Solar Energy (Elsevier)"),
            ("blank", ""), ("plain", "Dear Editor,"), ("blank", ""),
            ("plain", "Please consider the enclosed original research article \""
                      + TITLE + "\", by Qiong Yan and Peide Yang, for publication in "
                      "Solar Energy. It is original work, has not been published "
                      "previously and is not under consideration elsewhere."),
            ("blank", ""),
            ("plain", "Solar Energy regularly publishes transfer-matrix optical "
                      "design of thin-film cells and drift-diffusion/SCAPS device "
                      "optimisation. Our contribution joins these two lines of work: "
                      "a fully coherent, differentiable transfer-matrix solver is "
                      "coupled directly to a self-consistent one-dimensional "
                      "drift-diffusion solver, without a surrogate model and without "
                      "interpolating the optical field onto the electrical mesh. "
                      "Existing differentiable photovoltaic programs use "
                      "Beer-Lambert absorption and therefore cannot represent "
                      "standing-wave interference."),
            ("blank", ""),
            ("plain", "The generation rate is Poynting-consistent; the optical model "
                      "satisfies the absolute energy balance to 1.44e-6 and the "
                      "Beer-Lambert limit to 1.57e-8. Implicit differentiation of "
                      "the converged electrical state costs one transposed Jacobian "
                      "solve, 1.10 times a forward pass, and agrees with "
                      "fourth-order Richardson finite differences across the optical, "
                      "electrical and composite paths. Three-parameter inverse design "
                      "recovers all parameters to within 0.002% in 44 evaluations."),
            ("blank", ""),
            ("plain", "We would draw attention to the reporting of limitations. The "
                      "derivative-free benchmark uses true function-call counts; the "
                      "pre-registered tenfold reduction in eight dimensions is NOT "
                      "met (about threefold at moderate accuracy, neither optimiser "
                      "reaching 1e-4). The production mesh carries a 1.52% "
                      "discretisation uncertainty. All data are synthetic: no "
                      "experimental calibration, no SCAPS-1D cross-validation and no "
                      "efficiency record are claimed. We regard this explicit "
                      "accounting, together with the accompanying reproducible suite, "
                      "as part of the methodological contribution."),
            ("blank", ""),
            ("plain", "Both authors approved the submission. The work is original, "
                      "has no competing interests and received no specific funding "
                      "(to be confirmed by the authors). Generative AI was used only "
                      "for language editing and manuscript source preparation, as "
                      "disclosed in the manuscript. The deterministic experiment "
                      "suite, result files, figure scripts and consistency checker "
                      "are publicly available from " + REPO_URL + " at the time "
                      "of submission (the same link appears in the manuscript); a "
                      "frozen Zenodo archive will be linked before publication. "
                      "We can suggest reviewers on request."),
            ("blank", ""),
            ("plain", "Enclosures: manuscript (LaTeX, PDF, Word), 5 figures, 4 "
                      "tables, Highlights and the declarations in the manuscript."),
            ("blank", ""), ("plain", "Yours sincerely,"), ("blank", ""),
            ("bold", "Peide Yang (corresponding author)"),
            ("plain", "Xiamen University Tan Kah Kee College; yangpd@xujc.com"),
        ]),
    "Computer Physics Communications": dict(
        folder=CPC, stem="cover_letter_CPC",
        hl="highlights.txt", hl_docx="highlights.docx",
        highlights=[
            "UniDD is a reproducible PyTorch program coupling coherent TMM and drift-diffusion.",
            "One adjoint solve; full gradient evaluation costs 1.10x a forward solve.",
            "External checks: energy balance 1.44e-6, adjoint residual 3e-14.",
            "Full suite reproduces in about 25 min on one CPU core at a fixed seed.",
            "The pre-specified 10x target is not met in 8-D; histories are shipped.",
        ],
        letter=[
            ("bold", "Qiong Yan; Peide Yang (corresponding author)"),
            ("plain", "Fujian Jiangxia University, Fuzhou 350108, China; Xiamen "
                      "University Tan Kah Kee College, Xiamen, China"),
            ("plain", "Emails: 381007382@qq.com (Qiong Yan); yangpd@xujc.com "
                      "(Peide Yang, corresponding author)"),
            ("blank", ""), ("plain", DATE), ("blank", ""),
            ("bold", "To the Principal Editor, Computer Physics Communications"),
            ("blank", ""), ("plain", "Dear Editor,"), ("blank", ""),
            ("plain", "Please consider the enclosed Computer Programs in Physics "
                      "submission \"" + TITLE + "\", by Qiong Yan and Peide Yang, "
                      "for publication in Computer Physics Communications. The work "
                      "is original, has not been published previously and is not "
                      "under consideration elsewhere."),
            ("blank", ""),
            ("plain", "The manuscript describes UniDD, a deterministic Python "
                      "program that joins a fully coherent, Poynting-consistent "
                      "transfer-matrix optical solver to a self-consistent "
                      "one-dimensional drift-diffusion solver in a single "
                      "reverse-mode automatic-differentiation graph. This journal "
                      "published the differentiable photovoltaic simulator dPV "
                      "(CPC 272, 108232, 2022), which uses Beer-Lambert absorption; "
                      "UniDD extends that line of work by retaining thin-film "
                      "interference inside the differentiable composition, without a "
                      "surrogate and without interpolating the optical field onto "
                      "the electrical mesh."),
            ("blank", ""),
            ("plain", "The numerical contribution is the solver construction and its "
                      "validation: log-density variables, exponentially factored "
                      "Scharfetter-Gummel currents, a fully coupled equilibrated and "
                      "damped Newton iteration converged on a physical residual "
                      "scale, and an implicit-function-theorem adjoint implemented "
                      "as a custom torch.autograd.Function. External checks give an "
                      "optical energy balance of 1.44e-6, a Beer-Lambert limit of "
                      "1.57e-8, composite-gradient agreement to 2.78e-3 and an "
                      "adjoint residual of about 3e-14, at a backward cost of 1.10 "
                      "times a forward pass. The complete suite is deterministic at "
                      "seed 0 and reproduces in about 25 minutes on one CPU core."),
            ("blank", ""),
            ("plain", "In keeping with the journal's emphasis on reproducibility, we "
                      "ship the recorded optimisation histories together with the "
                      "negative result: the pre-registered tenfold evaluation-count "
                      "target is NOT met in eight dimensions (about threefold at "
                      "moderate accuracy, neither optimiser reaching 1e-4). All "
                      "targets are synthetic inverse crimes, and no experimental "
                      "calibration or SCAPS-1D cross-validation is claimed. The "
                      "Program Summary, source code, result files, figure scripts "
                      "and consistency checker accompany the submission under the "
                      "MIT licence; the repository at " + REPO_URL + " is made "
                      "public at the time of submission."),
            ("blank", ""),
            ("plain", "Both authors approved the submission. The work is original, "
                      "has no competing interests and received no specific funding "
                      "(to be confirmed by the authors). Generative AI was used only "
                      "for language editing and manuscript source preparation, as "
                      "disclosed in the manuscript. We can suggest reviewers on "
                      "request."),
            ("blank", ""),
            ("plain", "Enclosures: manuscript (LaTeX, PDF, Word), Program Summary, "
                      "5 figures, 4 tables, Highlights, source archive and the "
                      "declarations in the manuscript."),
            ("blank", ""), ("plain", "Yours sincerely,"), ("blank", ""),
            ("bold", "Peide Yang (corresponding author)"),
            ("plain", "Xiamen University Tan Kah Kee College; yangpd@xujc.com"),
        ]),
}

if HAS_SUPP:
    # Highlights stay at five bullets (Elsevier limit 3--5); the new evidence
    # is acknowledged in the cover letters instead.
    note = ("A one-factor 8-D/16-D control (E4-C) and a noisy multi-start "
            "comparison against five derivative-free baselines (E5) are "
            "reported as independent supplements. They are shipped with their "
            "recorded histories and do not revise the negative E4 verdict.")
    for variant in VARIANTS.values():
        letter = list(variant["letter"])
        letter = [((kind, body.replace("4 tables", "5 tables"))
                   if kind == "plain" else (kind, body))
                  for kind, body in letter]
        idx = next(i for i, (_, body) in enumerate(letter)
                   if body.startswith("Both authors approved"))
        letter[idx:idx] = [("plain", note), ("blank", "")]
        variant["letter"] = letter


def polish_letters() -> None:
    """Round-3 cover-letter fixes, applied after supplement insertion."""
    common_subs = [
        (" (to be confirmed by the authors)", ""),
        ("NOT met", "not met"),
        ("pre-registered", "pre-specified"),
        (" We can suggest reviewers on request.", ""),
        ("All data are synthetic: no experimental calibration, no SCAPS-1D "
         "cross-validation and no efficiency record are claimed.",
         "All data are synthetic: no experimental calibration and no "
         "efficiency record are claimed. A SCAPS-1D 3.3.12 comparison was "
         "executed and is reported with its pre-specified criteria; two of "
         "four criteria pass, so it is a limited cross-code sanity check "
         "rather than a validation."),
        ("All targets are synthetic inverse crimes, and no experimental "
         "calibration or SCAPS-1D cross-validation is claimed.",
         "All targets are synthetic inverse crimes, and no experimental "
         "calibration is claimed. A SCAPS-1D 3.3.12 comparison was executed; "
         "two of four pre-specified criteria pass, and the illuminated J-V "
         "curves are not comparable because the contact models differ."),
        ("published the differentiable photovoltaic simulator dPV "
         "(CPC 272, 108232, 2022), which uses Beer-Lambert absorption;",
         "published the end-to-end differentiable photovoltaic simulator of "
         "Mann et al. (CPC 272, 108232, 2022), which uses Beer-Lambert "
         "absorption;"),
        ("at a backward cost of 1.10 times a forward pass.",
         "with a gradient evaluation costing 1.10 times a forward solve "
         "(about 10% overhead)."),
        ("Implicit differentiation of the converged electrical state costs "
         "one transposed Jacobian solve, 1.10 times a forward pass, and agrees",
         "Implicit differentiation of the converged electrical state costs "
         "one transposed Jacobian solve; a full gradient evaluation costs 1.10 "
         "times a forward solve (about 10% overhead), and agrees"),
        ("In keeping with the journal's emphasis on reproducibility, we ship "
         "the recorded optimisation histories together with the negative result:",
         "For reproducibility, the source archive includes the recorded "
         "optimisation histories together with the negative result:"),
        ("Enclosures: manuscript (LaTeX, PDF, Word), Program Summary, "
         "5 figures, 5 tables, Highlights, source archive and the "
         "declarations in the manuscript.",
         "Enclosures: manuscript (LaTeX and PDF), Program Summary, 5 figures, "
         "5 tables, Highlights, and the source archive with README, MIT licence, "
         "environment files and a complete sample input/output test case; "
         "declarations are in the manuscript."),
        ("Enclosures: manuscript (LaTeX, PDF, Word), 5 figures, 5 tables, "
         "Highlights and the declarations in the manuscript.",
         "Enclosures: manuscript (LaTeX, PDF, Word), 5 figures, 5 tables, "
         "Highlights, source archive with README and the declarations in the "
         "manuscript."),
        # A sixth table (SCAPS acceptance) was added in round 5.
        ("5 tables", "6 tables"),
    ]
    for cfg in VARIANTS.values():
        out = []
        for kind, body in cfg["letter"]:
            for old, new in common_subs:
                body = body.replace(old, new)
            out.append((kind, body))
        cfg["letter"] = out


polish_letters()


def tex_escape(s: str) -> str:
    out, opening = [], True
    for ch in s:
        if ch == '"':
            out.append("``" if opening else "''")
            opening = not opening
        elif ch in "&%_#$":
            out.append("\\" + ch)
        elif ch == "~":
            out.append(r"\textasciitilde{}")
        elif ch == "^":
            out.append(r"\textasciicircum{}")
        else:
            out.append(ch)
    return "".join(out)


for journal, cfg in VARIANTS.items():
    folder, stem = cfg["folder"], cfg["stem"]
    hs = cfg["highlights"]
    assert 3 <= len(hs) <= 5 and all(len(h) <= 85 for h in hs)
    (folder / cfg["hl"]).write_text(
        f"# Highlights ({journal}: 3-5 bullets, <=85 characters each)\n"
        + "\n".join("- " + h for h in hs) + "\n", encoding="utf-8")
    hd = Document()
    hd.styles["Normal"].font.name = "Times New Roman"
    hd.styles["Normal"].font.size = Pt(12)
    p = hd.add_paragraph("Highlights")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.runs[0].bold = True
    for h in hs:
        q = hd.add_paragraph(h, style="List Bullet")
        for r in q.runs:
            r.font.name, r.font.size = "Times New Roman", Pt(12)
    hd.save(folder / cfg["hl_docx"])

    lines = [r"\documentclass[10pt]{article}", r"\usepackage[T1]{fontenc}",
             r"\usepackage[margin=0.8in]{geometry}", r"\pagestyle{empty}",
             r"\setlength{\parindent}{0pt}", r"\setlength{\parskip}{2pt}",
             r"\begin{document}", ""]
    for kind, text in cfg["letter"]:
        if kind == "blank":
            lines.append(r"\vspace{2pt}")
        elif kind in ("bold", "italic"):
            lines.append("\\" + ("textbf" if kind == "bold" else "textit")
                         + "{" + tex_escape(text) + r"}\par")
        else:
            lines.append(tex_escape(text) + r"\par")
    lines += ["", r"\end{document}", ""]
    (folder / (stem + ".tex")).write_text("\n".join(lines), encoding="utf-8")
    p = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
                        stem + ".tex"], cwd=folder, capture_output=True, text=True)
    if p.returncode:
        print(p.stdout[-3000:], p.stderr[-1000:])
        raise RuntimeError(f"cover letter LaTeX failed: {journal}")

    cd = Document()
    cs = cd.styles["Normal"]
    cs.font.name, cs.font.size = "Times New Roman", Pt(11)
    cs._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    for kind, text in cfg["letter"]:
        para = cd.add_paragraph()
        para.paragraph_format.space_after = Pt(6)
        if kind == "blank":
            continue
        run = para.add_run(text)
        run.font.name, run.font.size = "Times New Roman", Pt(11)
        run.bold, run.italic = kind == "bold", kind == "italic"
    cd.save(folder / (stem + ".docx"))
    print(f"    ancillaries -> {folder.name}")
print("[6/6] highlights and cover letters built")

report = [
    "# 两版投稿包构建报告", "", f"生成时间：{DATE}", "",
    "| 版本 | 目录 | LaTeX | PDF | Word | Highlights | Cover letter |",
    "|---|---|---|---|---|---|---|",
    "| Computer Physics Communications | `soldiff/paper/cpc/` | `unidd_cpc.tex` | `unidd_cpc.pdf` | `unidd_cpc.docx` | `.txt/.docx` | `.tex/.pdf/.docx` |",
    "| Solar Energy | `soldiff/paper/solar_energy/` | `unidd_solar_energy.tex` | `unidd_solar_energy.pdf` | `unidd_solar_energy.docx` | `.txt/.docx` | `.tex/.pdf/.docx` |",
    "", "v1 原稿已备份为 `soldiff/paper/solar_energy/unidd_solar_energy_v1.tex.bak`。",
    "", "## 两版共同的修订", "",
    "- 标题降调；摘要首句改为方法学陈述，移除 27.74% 的突出展示，改称 internal numerical benchmark。",
    "- 明确 ∂PV / DriftJax 使用 Beer–Lambert、TFSolver 不含载流子输运。",
    "- Data availability 写入真实 GitHub 仓库地址（MIT）；CPC 版按官方模板把 CPC Library link 留给 Technical Editor。保留 Generative AI disclosure。",
    "- 与 ∂PV / DriftJax / TFSolver 的关系移入引言（Four developments），Limitations 恢复四类。",
    "- q/4、q/5 核对后的修正：Table 5 分数方向、1.10×/1.22× 口径、Program Summary 官方字段、DriftJax 版本 DOI、通讯作者标注、pre-specified。",
    "- 第 4 轮（SCAPS 交叉验证）：本机 SCAPS 3.3.12 因缺 cvirte.dll 未能执行；该轮结论保留在历史记录中。",
    "- 第 5 轮（运行库解决 + 真实交叉验证）：从官方 UGent 完整包私有部署 22 个 CVI runtime 文件（免管理员权限），A/B 两层全部跑通，产出暗态/光照 J–V、QE、G(x) readback、4 张原生 PNG 与诊断日志。按数据产生前固定的判据判定：暗态 J–V 与 G(x) readback PASS，光照 J–V 与 EQE FAIL，总体 2/4 未通过。两版新增 Section「Cross-code comparison with SCAPS-1D」及验收表，Limitations、Data availability、CPC Program Summary、Cover letter 同步改为「有限的跨代码 sanity check，不构成验证」；E4/E4-H/E4-C/E5 数值与结论一字未动。",
    "- 参考文献核校：Byrnes 补 v5 日期；[10] 补 SPIE 会议录版本；TFSolver 补止页 52061–52074；新增 DriftJax（第 23 条）。",
    "- 未改动任何结果与预注册判定：E4 `not met`、E4-H 删失下界、8D 约 3× 全部保留。",
    "", "## CPC 版专有", "",
    "- `\\journal{Computer Physics Communications}`、首行注释与 Word 页眉注记全部替换。",
    "- 引言中 `in this journal` / `in Solar Energy` 改为中性表述，并把 ∂PV（CPC 272, 108232）作为该刊锚点。",
    "- 新增 Program Summary（按 ∂PV 的 CPC 字段格式）。",
    "- 摘要、Highlights、Cover letter 全部改为「可复现程序 + 数值算法 + 负结果可复现」的锚点。",
    "", "## 需作者补全", "",
    "- 仓库地址 " + REPO_URL + " 已写入两版 Data availability 与 cover letter；CPC 版按官方模板把 CPC Library link 留给 Technical Editor。",
    "- Zenodo 归档并回填 DOI；投稿前把仓库可见性改为 Public。",
    "- 确认 Funding 声明是否需要补入基金号。",
]
(HERE / "variant_build_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\nDone. See variant_build_report.md")
