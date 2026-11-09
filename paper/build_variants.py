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

# ---------------------------------------------------------------------------
# Round-7 evidence.  All numbers in the new sections come from the recorded
# result files; the build fails loudly rather than shipping a placeholder.
# Accept the working-tree layout (results next to paper/) and the release
# layout (results under ../results/).
import json as _json

_RES_DIR = HERE.parent if (HERE.parent / "results_final.json").is_file() \
    else HERE.parent / "results"


def _load_result(name: str) -> dict:
    p = _RES_DIR / name
    if not p.is_file():
        raise RuntimeError(f"missing recorded result file: {p}")
    return _json.loads(p.read_text(encoding="utf-8"))


OI = _load_result("results_optical_inverse.json")
SC = _load_result("results_adjoint_scaling.json")
FD = _load_result("results_fd_baseline.json")

_arm_c = OI["arms"]["coherent"]
_arm_b = OI["arms"]["single_pass"]
_cmp = OI["comparison"]
_xm = OI["cross_model_consequence"]
_fd_rows = FD["comparison"]["thresholds"]
_at1e3 = next(r for r in _fd_rows if r["threshold"] == 1e-3)
_sc_rows = SC["rows"]

TOKENS = {
    "@@DBIAS@@": f"{_cmp['thickness_bias_pct']:.2f}",
    "@@COHD@@": f"{_arm_c['best_fit_d_nm']:.2f}",
    "@@BLD@@": f"{_arm_b['best_fit_d_nm']:.2f}",
    "@@COHLOSS@@": f"{_arm_c['best_loss']:.2e}",
    "@@BLLOSS@@": f"{_arm_b['best_loss']:.2e}",
    "@@COHGRAD@@": f"{_arm_c['gradient_at_d0']:.3e}",
    "@@BLGRAD@@": f"{_arm_b['gradient_at_d0']:.3e}",
    "@@GRADRATIO@@":
        f"{_cmp['gradient_ratio_BL_over_coherent_at_d0']:.2f}",
    "@@CROSSRMSE@@":
        f"{_xm['single_pass']['observable_rmse_vs_target']:.3e}",
    "@@COHEVALS@@": str(_arm_c["n_forward_observations"]),
    "@@BLEVALS@@": str(_arm_b["n_forward_observations"]),
    # Signed change, NOT a "deficit": the measured value is positive, i.e.
    # the misspecified design gives a slightly higher Jsc under the coherent
    # truth model.  Reporting it as a deficit would invert the sign.
    "@@DESIGNCHG@@":
        f"{_xm['BL_design_Jsc_signed_change_vs_coherent_design_pct']:.2f}",
    "@@DESIGNDIR@@": _xm["BL_design_Jsc_direction"],
    "@@FDSPEEDUP@@":
        f"{FD['comparison']['FD_vs_IFT_forward_equivalent_speedup_at_1e-3']:.2f}",
    "@@FDFORWARD@@": f"{int(_at1e3['FD_LBFGS_forward_equivalents'])}",
    "@@IFTFORWARD@@":
        f"{_at1e3['IFT_LBFGS_forward_equivalents']:.2f}",
    "@@FDCOSINE@@": f"{FD['initial_gradient']['cosine']:.5f}",
    "@@FDPERGRAD@@":
        str(FD["comparison"]["per_gradient_cost"]["FD_central_differences"]),
    "@@FDTHEOR@@":
        f"{FD['comparison']['per_gradient_cost']['theoretical_ratio']:.2f}",
    "@@SCALEROWS@@": "\n".join(
        f"{r['N']} & {r['dense_jacobian_size']} & {r['t_forward_s']:.3f} "
        f"& {r['t_forward_adjoint_s']:.3f} "
        f"& {r['cost_factor_forward_plus_adjoint_over_forward']:.2f} "
        f"& {1000*r['t_isolated_dense_solve_s']:.2f} \\\\"
        for r in _sc_rows),
    "@@SCALEEXP@@": f"{SC['fitted_exponent_isolated_dense_solve']:.2f}",
}


def resolve_tokens(text: str) -> str:
    for key, value in TOKENS.items():
        if key not in text:
            raise RuntimeError(f"token {key} absent from manuscript source")
        text = text.replace(key, value)
    left = [k for k in TOKENS if k in text]
    if left or "@@" in text:
        raise RuntimeError(f"unresolved tokens: {left}")
    return text


TITLE = ("A differentiable, Poynting-consistent transfer-matrix and "
         "drift--diffusion kernel for co-design of thin-film solar cells")

# ------------------------------------------------------------------ abstracts
# Round 7 (q/1109 review): Elsevier's Guide for Authors for CPC caps the
# abstract at 250 words. Both abstracts were measured at 228 / 217 words
# (LaTeX commands and inline maths stripped) and 235 / 223 raw tokens.
# They now state the scope of the program, the one failing physical check,
# the synthetic inverse crime, the comparability boundary of the cross-code
# check, and the direct inverse-design consequence of dropping interference.
ABSTRACT_SE = r"""Thin-film solar-cell co-design needs coherent optics, self-consistent carrier
transport and derivatives with respect to layer geometry and material
parameters. Differentiable photovoltaic solvers with explicit optics use
Beer--Lambert absorption; surrogate-based digital twins learn the optical
stage. UniDD couples a Poynting-consistent coherent transfer-matrix solver to
a one-dimensional drift--diffusion solver in one differentiable graph, with
no surrogate and no optical-to-electrical interpolation; to our knowledge
this composition has not previously been differentiated end to end without
replacing either stage by a learned surrogate. Log-density variables and an
implicit-function-theorem adjoint give derivatives of the converged state.
External checks: optical energy balance $1.44\times10^{-6}$, Beer--Lambert
limit $1.57\times10^{-8}$, composite gradients $2.78\times10^{-3}$; a
forward-plus-adjoint evaluation costs $1.10$ times a forward solve. One of
seven physical checks fails at the coarsest grid. All device results are
synthetic internal numerical benchmarks, not predictions. A synthetic
three-parameter inverse crime recovers parameters to $0.0022\%$ in 44
evaluations; the tenfold evaluation-count target is not met in eight
dimensions (about $3\times$). The advantage is in low-dimensional,
tight-tolerance gradients and identifiability analysis, not general
high-dimensional inverse design. Replacing coherent optics with single-pass
absorption biases the recovered thickness by @@DBIAS@@\%, although reference
$J_{\mathrm{sc}}$ changes by only $0.0071\%$. A limited SCAPS-1D 3.3.12
sanity check reproduces the dark $J$--$V$ and imported generation profile;
two of four pre-specified criteria pass, and illumination results are not
comparable by construction. No experimental calibration is claimed."""

ABSTRACT_CPC = r"""We describe UniDD, a deterministic Python program and numerical kernel that
couples a coherent transfer-matrix optical solver to a self-consistent
one-dimensional drift--diffusion solver in one differentiable composition.
Existing differentiable photovoltaic solvers use Beer--Lambert absorption;
thin-film optics toolkits omit carrier transport. UniDD retains the exact
interference cross term with no surrogate and no optical-to-electrical
interpolation. Log-density variables, an equilibrated damped Newton iteration
and implicit-function-theorem gradients through one dense transposed solve
give derivatives of the converged state. External checks give an optical
energy balance of $1.44\times10^{-6}$, the Beer--Lambert limit to
$1.57\times10^{-8}$, composite gradient agreement to $2.78\times10^{-3}$ and
a forward-plus-adjoint evaluation costs $1.10$ times a forward solve. One of
seven physical checks fails at the coarsest grid. All device results are
synthetic internal numerical benchmarks, not predictions. A three-parameter
synthetic inverse crime recovers parameters to $0.0022\%$ in 44 evaluations.
The pre-specified tenfold evaluation-count target is not met in eight
dimensions (about $3\times$ at $10^{-3}$): the advantage lies in
low-dimensional, tight-tolerance gradients, gradient verification and
identifiability analysis, not general high-dimensional inverse design.
Replacing coherent optics with single-pass absorption in inverse design
biases the recovered thickness by @@DBIAS@@\%, although the reference
$J_{\mathrm{sc}}$ changes by only $0.0071\%$. A limited SCAPS-1D 3.3.12
sanity check reproduces the dark $J$--$V$ and imported generation profile;
two of four pre-specified criteria pass, and illumination results are not
comparable by construction. No experimental calibration is claimed. The
suite reproduces in about 25 minutes on one CPU core."""

# The recorded factor 1.10 is (forward + adjoint) / forward, i.e. about 10%
# overhead.  Saying "the backward pass costs 1.10 times a forward pass" would
# imply a total of 2.10x, so both abstracts state the ratio explicitly.
for _k in ("ABSTRACT_SE", "ABSTRACT_CPC"):
    globals()[_k] = re.sub(
        r"the backward pass costs \$1\.10\$ times a\s+forward\s+pass",
        lambda _m: ("a forward-plus-adjoint evaluation costs $1.10$ times a "
                    "forward\nsolve (about 10\\% overhead)"),
        globals()[_k])

PROGRAM_SUMMARY = r"""
\section*{Program summary}

\begin{description}
\item[Program title:] UniDD
\item[CPC Library link to program files:] (to be added by Technical Editor)
\item[Developer's repository link:] \url{REPOSITORY-URL}
\item[Code Ocean capsule:] (to be added by Technical Editor)
\item[Licensing provisions:] MIT
\item[Programming language:] Python 3.13.5; PyTorch 2.15.0 (CPU build),
NumPy, SciPy 1.15.3, Matplotlib; float64 and complex128 arithmetic
\item[Supplementary material:] Recorded optimisation histories, figure
generation scripts, the optical-coherence ablation and its recorded output,
the optical-model-misspecification inverse design, the dense-adjoint scaling
measurement and the finite-difference gradient baseline, native SCAPS-1D
3.3.12 outputs (dark and illuminated $J$--$V$, QE, generation read-back and
graphs), the solver diagnostic log, the cross-code acceptance verdict, the
pinned SCAPS version record and the SHA-256-pinned run-time deployment.
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
Boltzmann statistics, ideal Dirichlet selective contacts and a single bulk
SRH lifetime. No radiative, Auger or surface recombination, no series or
shunt resistance, no band-gap grading and no band-tail truncation are
included; the solar input is a coarse 41-point AM1.5G table spanning
350--800~nm. The electrical solve covers the absorber only, so the transport
layers enter through optics and contact boundary values. The adjoint uses a
dense $3(N-2)$ transposed solve whose isolated linear-algebra cost grows
approximately as $N^{@@SCALEEXP@@}$ over the measured $N=49$--$145$ range;
this is adequate at the production grid $N=73$ but cubic in the dense limit,
and a sparse or matrix-free adjoint is future work. The program is a
numerical kernel, not an experimentally calibrated device predictor.
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
    "of fully coherent optics, an explicit self-consistent DD solve and "
    "exact implicit gradients inside one differentiable composition, with "
    "no learned surrogate at either stage. $\\partial$PV itself identified "
    "the coupling of drift--diffusion to a Maxwell solver as a direction "
    "opened by differentiable programming; UniDD realises the coherent-"
    "multilayer instance of that direction. A wall-clock comparison of "
    "inverse-design performance against these programs would require "
    "reproducing their optical and contact models and is outside the scope "
    "of the present validation study. ")

SCAPS_SECTION = r"""\section{Limited cross-code sanity check with SCAPS-1D 3.3.12}
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
\caption{Pre-specified acceptance criteria, reproduced verbatim from the
distributed protocol, and the outcome of the SCAPS-1D 3.3.12 comparison.
Errors are evaluated on the common converged voltage or wavelength range;
dark-current RMSE is in mA\,cm$^{-2}$.}
\label{tab:scaps}
\centering
\footnotesize
\begin{tabular}{lp{4.3cm}p{4.0cm}c}
\toprule
Quantity & Criterion & Measured & Verdict \\
\midrule
Dark $J$--$V$ & RMSE $<0.05$ \emph{or} mean rel.\ $<5\%$ & RMSE $1.44\times10^{-3}$; mean rel.\ 212.10\% & PASS \\
Illuminated $J$--$V$ & $J_{\mathrm{sc}}<5\%$, $V_{\mathrm{oc}}<20$~mV, FF $<5\%$ & $J_{\mathrm{sc}}$ 7.03\%; $V_{\mathrm{oc}}$, FF n/a & FAIL \\
EQE & RMSE $<0.05$ & 0.096 & FAIL \\
$G(z)$ read-back & RMSE/$\overline{G}<2\%$ & $2.4\times10^{-4}\%$ & PASS \\
\bottomrule
\end{tabular}
\end{table}

\textbf{Comparability, fixed before the run.} The dark $J$--$V$ and the
generation read-back are comparable by construction: the former has no
generation term, and the latter is a direct unit-conversion and mesh
interpolation check of the imported profile. The illuminated $J$--$V$ and the
EQE are \emph{not comparable by construction}: UniDD imposes Dirichlet
carrier densities at the contacts, whereas SCAPS uses flat-band,
surface-recombination contacts, and SCAPS recomputes its QE from its own
internal wavelength-resolved absorption while UniDD imports a
wavelength-integrated $G(z)$. Their FAIL verdicts are retained verbatim as
pre-specified outcomes and are reported as model-mismatch diagnostics, not
as a failure rate of the drift--diffusion kernel. No criterion, threshold
or verdict was added, removed or relaxed after the data were produced.

Two of the four pre-specified criteria pass (Table~\ref{tab:scaps}); the
remaining two are the non-comparable ones. The dark-current criterion has two
branches because the UniDD dark current is essentially zero: a mean relative
error of 212.10\% is not informative there, so the absolute-RMSE branch
decides that verdict. Over the common converged range
$0$--$0.8$~V the dark curves agree to
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
against SCAPS-1D, and no experimental calibration has been performed. The
SCAPS binary is closed source and is not redistributed for licensing
reasons; the single-layer definition, the imported generation profile, the
script chain, the native SCAPS outputs and the solver diagnostic log are
shipped together with \texttt{scaps\_version.txt}, which pins the executable
version and build date and the SHA-256 of the LabWindows/CVI run-time
deployment. This pinned archive allows the comparison to be audited without
re-running SCAPS-1D."""

# The ablation result existed in the release archive but was not cited in
# either manuscript.  Reporting it pins down where coherent optics actually
# matters, instead of leaving an implicit "coherence is necessary" claim.
ABLATION_SECTION = r"""\subsection{Scope of the coherent optical model}
\label{sec:ablation}

Retaining the interference term is a modelling choice rather than a universal
accuracy requirement. To locate its practical scope, the reference device and
a grid of five absorption strengths ($k$ amplitude $0.02$--$0.72$) and three
absorber thicknesses ($120$, $240$, $480$~nm) were recomputed with the
coherent field replaced by a single-pass Beer--Lambert profile that keeps the
same Fresnel transmission amplitude. At the reference $480$~nm device the
short-circuit current changes by only $0.0071\%$ ($29.9499$ against
$29.9477$~mA\,cm$^{-2}$) and the thickness gradient by $1.91\%$; the coherent
generation profile has one interior extremum where the single-pass profile is
monotone. Over the $15$ grid points the largest $J_{\mathrm{sc}}$ difference
is $4.87\%$, whereas the largest thickness-gradient difference is $39.85\%$
at $120$~nm and $k=0.72$. Coherent optics therefore matters chiefly for
derivatives and inverse design in thin, strongly absorbing stacks, and much
less for predicting $J_{\mathrm{sc}}$ in the reference device. We do not
claim that a coherent optical model is necessary in general. The ablation and
its recorded output are distributed with the code
(\texttt{experiments\_optics\_ablation.py},
\texttt{results\_optics\_ablation.json})."""

# Round 7: direct evidence for "why coherent optics" and for the net value of
# the adjoint.  All numbers are resolved from the recorded result files by
# resolve_tokens(); nothing is typed into the manuscript by hand.
EVIDENCE_SECTION = r"""\section{Model choice and gradient cost}
\label{sec:evidence}

The ablation of Section~\ref{sec:ablation} identifies where coherent optics
changes derivatives but not whether it changes a design decision. This
section supplies that missing evidence and quantifies the cost of the
adjoint against the finite-difference baseline that was previously absent.
All three experiments are synthetic; none is an experimental validation.

\subsection{Optical-model misspecification in inverse design}
\label{sec:evidence-inverse}

A thin, strongly absorbing stack ($d=120$~nm, $k=0.72$, $\tau=3\times10^{-7}$~s)
was chosen at the grid point where the recorded regime scan reports the
largest thickness-gradient contrast. Twelve normalised observations (six
$J$--$V$ points and six EQE points) were generated with the coherent model.
The inverse variable is the absorber thickness alone, with $k$ and $\tau$
fixed at their true values: a preliminary three-parameter version stalled in
local minima on both arms, reflecting the weak identifiability already
reported in E4, and would have confounded the model-choice question. The
loss was therefore scanned on a deterministic grid (80--300~nm in 5~nm steps
plus a 1~nm local refinement) rather than trusted to a local optimiser. Two
arms used the same grid and budget, changing only the optical generation
model inside the inverse loop: a correctly specified coherent arm and a
misspecified single-pass arm that keeps the same Fresnel amplitude,
$\alpha(\lambda)$, AM1.5G flux and $n_r/n_0$ factor. Reflection/transmission
observations were excluded so that each arm is a self-consistent forward
model. The target is generated by the same forward model as the control arm,
so this is a synthetic inverse crime; what it measures is
\emph{model-misspecification bias}, not identifiability from measured data.

\begin{table}[t]
\caption{One-parameter thickness inversion under a correctly specified and a
misspecified optical model. Truth: $d=120$~nm, $k=0.72$,
$\tau=3\times10^{-7}$~s.}
\label{tab:optical_inverse}
\centering
\footnotesize
\begin{tabular}{lcc}
\toprule
Quantity & Coherent TMM & Single-pass \\
\midrule
Best-fit $d$ (nm) & @@COHD@@ & @@BLD@@ \\
Loss at best fit & @@COHLOSS@@ & @@BLLOSS@@ \\
$\dd L/\dd d$ at 200~nm & @@COHGRAD@@ & @@BLGRAD@@ \\
Forward evaluations & @@COHEVALS@@ & @@BLEVALS@@ \\
\bottomrule
\end{tabular}
\end{table}

The control recovers the generating thickness, whereas the single-pass arm
prefers a thickness biased by @@DBIAS@@\% (Table~\ref{tab:optical_inverse}):
the two optical models rank designs differently. At a common starting
thickness their loss gradients differ by a factor of @@GRADRATIO@@. Evaluated
with the coherent truth model, the misspecified solution leaves a normalised
observable RMSE of @@CROSSRMSE@@, while its $J_{\mathrm{sc}}$ is
@@DESIGNCHG@@\% @@DESIGNDIR@@: at this operating point the parameter bias
does not translate into a current penalty. Together with the $0.0071\%$
reference-current change reported in Section~\ref{sec:ablation}, this bounds
the claim. Coherent optics is material to parameter recovery and gradient
fidelity in thin, strongly absorbing stacks; it is not shown to be necessary
for $J_{\mathrm{sc}}$ prediction. This is a model-choice result from a
synthetic inverse crime, not a claim that coherent optics is generally
necessary and not an experimental validation. The experiment and its recorded
loss curves are distributed as \texttt{experiments\_optical\_inverse.py} and
\texttt{results\_optical\_inverse.json}.

\subsection{Measured cost of the dense adjoint}
\label{sec:evidence-scaling}

Table~\ref{tab:adjoint_scaling} times a single-bias forward solve and a
forward-plus-adjoint evaluation on the five DD meshes used in the recorded
convergence study, together with the isolated dense
\texttt{torch.linalg.solve} of size $3(N-2)$ that the IFT node performs.
The isolated linear-algebra cost grows approximately as
$N^{@@SCALEEXP@@}$ over the measured range, while the end-to-end gradient
cost is dominated by the Newton iteration at these mesh sizes. The dense
adjoint is therefore adequate at the production grid $N=73$ but is the
limiting factor for much larger meshes; a sparse or matrix-free adjoint is
left as future work.

\begin{table}[t]
\caption{Measured adjoint cost versus DD mesh size. Best of repeated runs on
one CPU core; the last column times the isolated dense solve of size
$3(N-2)$.}
\label{tab:adjoint_scaling}
\centering
\footnotesize
\begin{tabular}{lccccc}
\toprule
$N$ & $3(N-2)$ & Forward (s) & Fwd\,+\,adj.\ (s) & Ratio & Dense solve (ms) \\
\midrule
@@SCALEROWS@@
\bottomrule
\end{tabular}
\end{table}

\subsection{Finite-difference gradients with the same optimiser}
\label{sec:evidence-cost}

The derivative-free baselines of E4 and E5 do not isolate the value of the
adjoint, because they also change the optimiser. An additional arm therefore
reruns the recorded three-dimensional E4 case with central finite differences
($h=10^{-4}$) driving the same L-BFGS settings. At the common start point
the finite-difference and IFT gradients agree to cosine @@FDCOSINE@@. A
central-difference gradient costs @@FDPERGRAD@@ forward solves against
$1.10$ for a forward-plus-adjoint evaluation, a per-gradient ratio of
@@FDTHEOR@@. Counting every forward solve, including line-search
evaluations, the finite-difference arm needs @@FDFORWARD@@ forward solves to
reach a loss of $10^{-3}$ against @@IFTFORWARD@@ forward-solve equivalents for
the IFT arm, a @@FDSPEEDUP@@-fold advantage. This quantifies the net benefit
of the 10\% adjoint overhead. It is a three-dimensional cost comparison; it
does not revise the pre-specified eight-dimensional E4 verdict, and it is
not an experimental result. The arm and its recorded output are distributed
as \texttt{experiments\_fd\_baseline.py} and
\texttt{results\_fd\_baseline.json}; the scaling measurement is
\texttt{experiments\_adjoint\_scaling.py} with
\texttt{results\_adjoint\_scaling.json}.
"""

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
        "experiments (E0--E4), three supplements (E4-H, E4-C, E5) and an\n"
        "optical-coherence ablation.",
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
        "UniDD is best read as a numerically validated differentiable\n"
        "\\emph{modelling kernel} whose",
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
        "LabWindows/CVI run-time engine is pinned by a SHA-256 manifest. "
        "The optical-coherence ablation of Section~\\ref{sec:ablation} is\n"
        "reproduced by \\texttt{experiments\\_optics\\_ablation.py} with its\n"
        "recorded \\texttt{results\\_optics\\_ablation.json}.",
        "SCAPS results in data availability")
    sub("Section~\\ref{sec:e2} are illustrative; they should not be compared with\n"
        "measured efficiencies or with detailed-balance limits.",
        "Section~\\ref{sec:e2} are illustrative; they should not be compared with\n"
        "measured efficiencies or with detailed-balance limits. The ablation of\n"
        "Section~\\ref{sec:ablation} further delimits the interference term: for\n"
        "the reference device it changes $J_{\\mathrm{sc}}$ by $0.0071\\%$ only,\n"
        "so coherent optics is not a generally necessary correction to the\n"
        "current.",
        "ablation in limitations")
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


def polish_round7(text: str) -> str:
    """Round-7 (q/1109) fixes applied AFTER polish(), so all strings below are
    the post-polish ones.  Every replacement is asserted to match exactly."""
    def sub(old: str, new: str, tag: str) -> None:
        nonlocal text
        text = sub_once(text, old, new, tag)

    def rep(old: str, new: str, tag: str, expect: int) -> None:
        nonlocal text
        n = text.count(old)
        if n != expect:
            raise RuntimeError(f"[{tag}] expected {expect} matches, found {n}: {old[:70]!r}")
        text = text.replace(old, new)

    # --- portability and URL line breaking ---------------------------------
    sub("\\usepackage{booktabs}\n\\usepackage{lineno}\n\\linenumbers",
        "\\usepackage{booktabs}\n\\usepackage{url}\n"
        "\\IfFileExists{lineno.sty}{\\usepackage{lineno}\\linenumbers}{}",
        "portable line numbering / url package")
    rep(r"\texttt{REPOSITORY-URL}", r"\url{REPOSITORY-URL}",
        "repository URL uses url.sty", 1)
    rep(r"\texttt{https://github.com/medmo13/driftjax}",
        r"\url{https://github.com/medmo13/driftjax}",
        "DriftJax URL uses url.sty", 1)

    # --- Eq. (5) notation: one symbol for the intrinsic density ------------
    sub("\\begin{equation}\n"
        "  x=(\\psi_i,\\; w^{n}_i,\\; w^{p}_i),\\qquad\n"
        "  n_i = n_i^{0}\\,\\ee^{-w^{n}_i/\\Vt},\\qquad\n"
        "  p_i = n_i^{0}\\,\\ee^{+w^{p}_i/\\Vt},\n"
        "  \\label{eq:vars}\n"
        "\\end{equation}\n"
        "with $\\Vt=\\kb T/q$ and $w^{n}=\\varphi_n-\\psi$, "
        "$w^{p}=\\varphi_p-\\psi$. Each",
        "\\begin{equation}\n"
        "  x=(\\psi_j,\\; w^{n}_j,\\; w^{p}_j),\\qquad\n"
        "  n_j = n_{\\mathrm{i}}^{0}\\,\\ee^{-w^{n}_j/\\Vt},\\qquad\n"
        "  p_j = n_{\\mathrm{i}}^{0}\\,\\ee^{+w^{p}_j/\\Vt},\n"
        "  \\label{eq:vars}\n"
        "\\end{equation}\n"
        "with $\\Vt=\\kb T/q$ and $w^{n}=\\varphi_n-\\psi$, "
        "$w^{p}=\\varphi_p-\\psi$; here $j$ indexes the mesh node and "
        "$n_{\\mathrm{i}}^{0}$ denotes the intrinsic carrier density, so that "
        "$np=(n_{\\mathrm{i}}^{0})^2$ at thermal equilibrium. As written in "
        "Eq.~\\eqref{eq:vars}, each",
        "unify intrinsic-density notation and node index")
    rep("\\, n^{0}\\,\\ee", "\\, n_{\\mathrm{i}}^{0}\\,\\ee",
        "SG intrinsic density notation", 2)
    sub("with Shockley--Read--Hall (SRH) recombination\n"
        "$R=(np-n_i^2)/[\\tau_p(n+n_i)+\\tau_n(p+n_i)]$. Contacts are ideal and ohmic;",
        "with Shockley--Read--Hall (SRH) recombination\n"
        "$R=(np-(n_{\\mathrm{i}}^{0})^2)/[\\tau_p(n+n_{\\mathrm{i}}^{0})"
        "+\\tau_n(p+n_{\\mathrm{i}}^{0})]$. "
        "Contacts are ideal and ohmic;",
        "SRH intrinsic density notation")

    # --- physical meaning of the equilibrated residual floor ---------------
    sub("$F_{\\mathrm{floor}}=3\\times10^{2}$~A\\,m$^{-3}$, all solves in this work\n"
        "converge in 15--23 iterations.",
        "$F_{\\mathrm{floor}}=3\\times10^{2}$~A\\,m$^{-3}$, all solves in this work\n"
        "converge in 15--23 iterations. The floor acts on the equilibrated\n"
        "residual vector: row--column equilibration places the Poisson and the\n"
        "two continuity blocks on a common dimensionless scale, so a single\n"
        "tolerance quoted in the continuity unit A\\,m$^{-3}$ applies to all\n"
        "three blocks rather than to the continuity equations alone.",
        "explain equilibrated residual floor")

    # --- engineering value of the interference cross term ------------------
    sub("cancel exactly in the product. Multiplying it by $\\ee^{-\\alpha z}$ is a\n"
        "convenient-looking but incorrect simplification that breaks energy balance\n"
        "for strongly absorbing layers.",
        "cancel exactly in the product. Multiplying it by $\\ee^{-\\alpha z}$ is a\n"
        "convenient-looking but incorrect simplification that breaks energy balance\n"
        "for strongly absorbing layers; it is the term most often mis-implemented\n"
        "when a coherent field is converted into a generation profile, and the\n"
        "absolute check of Eq.~\\eqref{eq:energy} is what exposes it.",
        "interference cross-term pitfall")

    # --- cite the seven previously unreferenced numbered equations ----------
    sub("where the substrate condition $b_{L-1}=0$ fixes $r$ by a single ratio. This\n"
        "parameterisation is branch-free, vectorised over wavelengths and exactly\n"
        "differentiable.",
        "where the substrate condition $b_{L-1}=0$ fixes $r$ by a single ratio\n"
        "(Eq.~\\eqref{eq:recursion}). This parameterisation is branch-free,\n"
        "vectorised over wavelengths and exactly differentiable.",
        "cite eq:recursion")
    sub("with $\\Phi$ the AM1.5G photon flux~\\cite{astm2020}. All TMM operations are\n"
        "performed in complex128/float64 arithmetic and are differentiable with\n"
        "respect to layer thicknesses and complex indices.",
        "with $\\Phi$ the AM1.5G photon flux~\\cite{astm2020}. "
        "Equation~\\eqref{eq:generation} is evaluated analytically at the\n"
        "electrical mesh nodes. All TMM operations are performed in\n"
        "complex128/float64 arithmetic and are differentiable with respect to\n"
        "layer thicknesses and complex indices.",
        "cite eq:generation")
    sub("with $B(u)=u/(\\ee^{u}-1)$ the Bernoulli function. The brackets are $O(1)$\n"
        "and cancel exactly at equilibrium, whereas the textbook form",
        "with $B(u)=u/(\\ee^{u}-1)$ the Bernoulli function. The brackets in\n"
        "Eq.~\\eqref{eq:sg} are $O(1)$ and cancel exactly at equilibrium, whereas\n"
        "the textbook form",
        "cite eq:sg")
    sub("The residual equations are the two continuity equations and Poisson's\n"
        "equation,",
        "The residual equations (Eq.~\\eqref{eq:ddsystem}) are the two continuity\n"
        "equations and Poisson's equation,",
        "cite eq:ddsystem")
    sub("This is the same implicit differentiation used in deep equilibrium\n"
        "models~\\cite{bai2019}, applied here to a physical fixed-point solver.",
        "Equations~\\eqref{eq:ift} and~\\eqref{eq:adjoint} implement the same implicit\n"
        "differentiation used in deep equilibrium models~\\cite{bai2019}, applied\n"
        "here to a physical fixed-point solver.",
        "cite eq:ift and eq:adjoint")

    # --- contribution list: explicit composition-level differentiability ---
    sub("and a statement of where the gradient advantage is modest or absent.\n"
        "\\end{enumerate}",
        "and a statement of where the gradient advantage is modest or absent.\n"
        "\\item Composition-level differentiability. The contribution is not a\n"
        "  new discretisation of the drift--diffusion equations or a new optical\n"
        "  algorithm: it is that a fully coherent multilayer solve, a\n"
        "  self-consistent carrier-transport solve and exact implicit gradients\n"
        "  are retained together in one differentiable composition, with no\n"
        "  learned surrogate at either stage.\n"
        "\\end{enumerate}",
        "explicit composition-level novelty")

    # --- honest E2 reporting, precision of the inverse-crime error ----------
    sub("Six of seven pre-specified physical checks pass\n"
        "(Table~\\ref{tab:validation}, lower block).",
        "Six of seven pre-specified physical checks pass; the failing one is the\n"
        "coarsest-grid mesh test, reported together with its Richardson\n"
        "extrapolation (Table~\\ref{tab:validation}, lower block).",
        "state the failing E2 check")
    text = text.replace("0.002\\%", "0.0022\\%")
    text = text.replace("recovers all parameters to within $0.0022\\%$",
                        "recovers all parameters to within $0.0022\\%$ in a "
                        "synthetic inverse crime")

    # --- non-differentiable predecessors ------------------------------------
    sub("Four\ndevelopments are particularly relevant. Mann et al.\\ introduced",
        "Four\ndevelopments are particularly relevant. Established non-differentiable\n"
        "multiscale packages such as Solcore~\\cite{solcore2018}, GPVDM/OghmaNano\n"
        "and SCAPS-1D already combine transfer-matrix optics with carrier\n"
        "transport; the gap is differentiability of the entire coupled\n"
        "composition, not of the individual stages. Mann et al.\\ introduced",
        "acknowledge non-differentiable predecessors")

    # --- declaration wording and position (Elsevier: before reference list) -
    sub("\\section*{Generative AI disclosure}\n"
        "Generative AI tools were used to assist with language editing and with the\n"
        "preparation of manuscript source files. All physical models, numerical\n"
        "experiments, results and scientific conclusions were conceived, implemented\n"
        "and verified by the authors, who take full responsibility for the content.",
        "\\section*{Declaration of generative AI and AI-assisted technologies in the\n"
        "manuscript preparation process}\n"
        "During the preparation of this work the authors used Generative AI tools\n"
        "for language editing and for the preparation of manuscript source files.\n"
        "After using these tools the authors reviewed and edited the content as\n"
        "needed and take full responsibility for the content of the published\n"
        "article. All physical models, numerical experiments, results and\n"
        "scientific conclusions were conceived, implemented and verified by the\n"
        "authors.",
        "Elsevier-aligned GenAI declaration")

    # --- limitations: concrete experimental roadmap -------------------------
    sub("Section~\\ref{sec:scaps} documents the executed comparison and its\n"
        "pre-specified criteria; experimental calibration remains the most\n"
        "important next step before the framework can be used for device\n"
        "design.",
        "Section~\\ref{sec:scaps} documents the executed comparison and its\n"
        "pre-specified criteria; experimental calibration remains the most\n"
        "important next step before the framework can be used for device design.\n"
        "A minimal programme is (i) spectroscopic ellipsometry for layer\n"
        "thicknesses and $n(\\lambda)+ik(\\lambda)$, (ii) absolute EQE and dark\n"
        "and illuminated $J$--$V$ on the same devices, and (iii) a\n"
        "calibration/hold-out split over thicknesses and fabrication batches.",
        "concrete experimental roadmap")

    # --- Figure 4: disclose the truncated vertical axis ---------------------
    sub("\\caption{(a) Ratio of automatic derivatives to fourth-order Richardson\n"
        "  finite differences for each design parameter; labels give the relative\n"
        "  deviation. (b) Relative deviation of the full-chain directional derivative",
        "\\caption{(a) Ratio of automatic derivatives to fourth-order Richardson\n"
        "  finite differences for each design parameter; labels give the relative\n"
        "  deviation and the vertical axis is explicitly truncated and labelled\n"
        "  in the panel. (b) Relative deviation of the full-chain directional derivative",
        "disclose truncated axis in Figure 4")

    # --- conclusions: scope statement matching the abstract -----------------
    sub("UniDD is best read as a numerically validated differentiable\n"
        "\\emph{modelling kernel} whose",
        "Its advantage is confined to low-dimensional, tight-tolerance gradients,\n"
        "gradient verification and identifiability analysis; high-dimensional\n"
        "spectral inversion still needs richer observations or regularisation.\n"
        "UniDD is best read as a numerically validated differentiable\n"
        "\\emph{modelling kernel} whose",
        "scope statement in conclusions")
    return text


def reorder_bibliography(text: str) -> str:
    """Elsevier numbered style: list references in order of first citation.

    The v1 source hand-orders its thebibliography blocks, which puts DriftJax
    at [23] although it is first cited in the Introduction.  Reordering by
    first appearance also absorbs the newly added Solcore and DriftJax entries
    without any hand-maintained numbering.
    """
    m = re.search(r"(\\begin\{thebibliography\}\{\d+\})(.*?)"
                  r"(\\end\{thebibliography\})", text, re.S)
    if not m:
        raise RuntimeError("[bibliography] thebibliography environment not found")
    head, body, tail = m.group(1), m.group(2), m.group(3)
    blocks = re.findall(r"\\bibitem\{([^}]+)\}.*?(?=\\bibitem\{|\Z)", body, re.S)
    if len(blocks) != len(re.findall(r"\\bibitem\{", body)):
        raise RuntimeError("[bibliography] block split failed")
    by_key = {}
    for chunk in re.findall(
            r"(\\bibitem\{[^}]+\}.*?)(?=\\bibitem\{|\Z)", body, re.S):
        k = re.match(r"\\bibitem\{([^}]+)\}", chunk).group(1)
        by_key[k] = chunk.rstrip() + "\n\n"
    before = text[:m.start()]
    order, seen = [], set()
    for cite in re.findall(r"\\cite\{([^}]+)\}", before):
        for k in (x.strip() for x in cite.split(",")):
            if k and k not in seen and k in by_key:
                seen.add(k)
                order.append(k)
    for k in by_key:
        if k not in seen:
            order.append(k)
    new_body = "\n" + "".join(by_key[k] for k in order)
    head = re.sub(r"\{\d+\}$", "{" + str(len(by_key)) + "}", head)
    return text[:m.start()] + head + new_body + tail + text[m.end():]


def common(text: str, journal: str, abstract: str) -> str:
    text = sub_once(text,
        "%% UniDD -- manuscript prepared for Solar Energy (Elsevier)",
        f"%% UniDD -- manuscript prepared for {journal} (Elsevier)", "header")
    if journal == "Computer Physics Communications":
        text = sub_once(text,
            "%% Compile: pdflatex unidd_solar_energy.tex  (twice)",
            "%% Compile: pdflatex unidd_cpc.tex  (twice)", "cpc compile header")
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
                    "\\begin{thebibliography}{24}", "bib width")
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
        "\\bibitem{solcore2018} D. Alonso-\\'{A}lvarez, T. Wilson, P. Pearce, "
        "M. F\\\"{u}hrer, D. Farrell, N.~J. Ekins-Daukes, Solcore: a "
        "multi-scale, Python-based library for modelling solar cells and "
        "semiconductor materials, Journal of Computational Electronics 17 "
        "(2018) 1099--1123. doi:10.1007/s10825-018-1171-3.\n\n"
        "\\end{thebibliography}", "driftjax + solcore")

    # CPC asks for a general-reader novelty statement in the Introduction.
    # Moving it there also leaves exactly four limitation classes in Section 4.
    text = sub_once(text, "Three\ndevelopments are particularly relevant.",
                    "Four\ndevelopments are particularly relevant.",
                    "four developments")
    text = sub_once(text,
        "it does not solve\ncarrier transport. Differentiable electromagnetics",
        "it does not solve\ncarrier transport. "
        + r"Benaissa et al.\ released DriftJax, "
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
    result = polish_round7(polish(text))
    if journal == "Computer Physics Communications":
        result = sub_once(result,
            "Mann et al.\\ introduced\n"
            "$\\partial$PV, an end-to-end differentiable solar-cell simulator in JAX",
            "Mann et al.\\ introduced\n"
            "$\\partial$PV (published in this journal), an end-to-end "
            "differentiable solar-cell simulator in JAX",
            "dPV published in this journal")
    return reorder_bibliography(result)


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

def with_ablation(text: str) -> str:
    """Insert the optical-coherence ablation before the limitations section."""
    anchor = "%% " + "=" * 76 + "\n\\section{Limitations and scope}"
    return sub_once(text, anchor, ABLATION_SECTION + "\n\n" + anchor,
                    "optical-coherence ablation")


def with_scaps(text: str) -> str:
    """Insert the executed SCAPS-1D comparison before the limitations section."""
    anchor = "%% " + "=" * 76 + "\n\\section{Limitations and scope}"
    return sub_once(text, anchor, SCAPS_SECTION + "\n\n" + anchor,
                    "SCAPS comparison section")


def with_evidence(text: str) -> str:
    """Insert the round-7 model-choice and cost evidence before Limitations."""
    anchor = "%% " + "=" * 76 + "\n\\section{Limitations and scope}"
    return sub_once(text, anchor, EVIDENCE_SECTION + "\n\n" + anchor,
                    "model-choice and cost evidence")


se = with_supplements(se)
cpc = with_supplements(cpc)
se = with_ablation(se)
cpc = with_ablation(cpc)
se = with_scaps(se)
cpc = with_scaps(cpc)
se = with_evidence(se)
cpc = with_evidence(cpc)

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
se = resolve_tokens(se)
cpc = resolve_tokens(cpc)

(SE / "unidd_solar_energy.tex").write_text(se, encoding="utf-8")
(CPC / "unidd_cpc.tex").write_text(cpc, encoding="utf-8")
print("[1/6] two .tex variants written" + (" (+ E4-C/E5)" if HAS_SUPP else ""))

# ------------------------------------------------------------------- figures
dst_fig = CPC / "figures"
dst_fig.mkdir(exist_ok=True)
for f in (SE / "figures").iterdir():
    if f.suffix.lower() in (".pdf", ".png"):
        shutil.copy2(f, dst_fig / f.name)
# Elsevier's Editorial Manager expects a flat source archive.  The LaTeX
# still uses figures/ (portable for local builds) but the same five vector
# PDFs are also placed flat in the CPC directory for a one-folder upload.
for f in dst_fig.glob("*.pdf"):
    shutil.copy2(f, CPC / f.name)
print("[2/6] figures copied for CPC (plus flat vector copies for upload)")

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
    # q/1109: the italic "Manuscript prepared for <journal>" line is a build
    # annotation, not part of a submission. Drop it from both Word variants.
    s, n_note = re.subn(r'^[ \t]*"WORDNOTE::[^"]*",[ \t]*\n', '', s,
                        count=1, flags=re.M)
    if n_note != 1 or "WORDNOTE::" in s:
        raise RuntimeError("[word NOTE] front-matter annotation was not removed")
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
            "IFT gradients: full evaluation costs 1.10× a forward solve (10% overhead).",
            "Optical energy balance holds to 1.44e-6; Beer-Lambert limit to 1.57e-8.",
            "Synthetic inverse crime recovers three parameters to within 0.0022%.",
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
            "UniDD couples coherent TMM to drift-diffusion in one differentiable graph.",
            "One adjoint solve; gradient evaluation costs 1.10× a forward solve.",
            "External checks: energy balance 1.44e-6; synthetic inverse crime 0.0022%.",
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
            "recorded histories and do not revise the negative E4 verdict. "
            "An optical-coherence ablation delimits the role of the "
            "interference term: coherent and single-pass optics differ by "
            "only 0.0071% in Jsc for the reference device, while the "
            "thickness-gradient difference reaches 39.85% in thin, strongly "
            "absorbing stacks. A controlled inverse-design experiment now "
            "shows that a single-pass optical model biases the recovered "
            "absorber thickness, and a finite-difference-gradient baseline "
            "isolates the net benefit of the adjoint; the dense-adjoint cost "
            "is measured across five mesh sizes.")
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
        ("Existing differentiable photovoltaic programs use "
         "Beer-Lambert absorption and therefore cannot represent "
         "standing-wave interference.",
         "Existing differentiable photovoltaic solvers with an explicit "
         "optical model (dPV, DriftJax) use Beer-Lambert absorption and "
         "therefore cannot represent standing-wave interference; "
         "surrogate-based digital twins replace the optical stage by a "
         "learned model."),
        ("All data are synthetic: no experimental calibration, no SCAPS-1D "
         "cross-validation and no efficiency record are claimed.",
         "All data are synthetic: no experimental calibration and no "
         "efficiency record are claimed. A SCAPS-1D 3.3.12 comparison was "
         "executed and is reported with its pre-specified criteria; two of "
         "four criteria pass, and we report it as a limited sanity check, "
         "not as validation."),
        ("All targets are synthetic inverse crimes, and no experimental "
         "calibration or SCAPS-1D cross-validation is claimed.",
         "All targets are synthetic inverse crimes, and no experimental "
         "calibration is claimed. A SCAPS-1D 3.3.12 comparison was executed; "
         "two of four pre-specified criteria pass, and the illuminated J-V "
         "curves are not comparable because the contact models differ. We "
         "report it as a limited sanity check, not as validation."),
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
        # Round 5 added the SCAPS acceptance table; round 7 added the
        # optical-model-misspecification and adjoint-scaling tables.
        ("5 tables", "8 tables"),
        ("0.002%", "0.0022%"),
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
    # q/1109: the leading "# Highlights (...)" line is an author annotation
    # and must not be shipped inside a submission file.
    (folder / cfg["hl"]).write_text(
        "\n".join("- " + h for h in hs) + "\n", encoding="utf-8")
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
        # q/1109: the manuscript title carries the LaTeX en-dash "--" but
        # Word is plain text, where it must become a real en dash.
        text = text.replace("---", "\u2014").replace("--", "\u2013")
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
    "- 第 6 轮（文献/主张一致性 + 光学消融）：联网核验 23 条文献、24 个 DOI（CrossRef 20 条 + DataCite 4 条），全部真实；补正 DriftJax 第一作者归属（Benaissa et al.），收紧摘要与引言的 novelty 口径以区分 Sol(Di)$^2$T 等代理类数字孪生，结论段改 `numerically validated`，SCAPS 暗态判据按仓库真源补全 OR 分支与 212.10% 相对误差，并把此前已入库但未引用的光学消融写入两版新增 subsection「Scope of the coherent optical model」（参考器件 Jsc 差 0.0071%、梯度差 1.91%；15 组扫描最大梯度差 39.85%）。核验脚本扩到 179/179；E4/E4-H/E4-C/E5 数值与结论一字未动。",
    "- 参考文献核校：Byrnes 补 v5 日期；[10] 补 SPIE 会议录版本；TFSolver 补止页 52061–52074；新增 DriftJax（第 23 条）。",
    "- 未改动任何结果与预指定判定：E4 `not met`、E4-H 删失下界、8D 约 3× 全部保留。",
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
