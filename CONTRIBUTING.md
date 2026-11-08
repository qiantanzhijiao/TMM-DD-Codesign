# Contributing

Issues and pull requests are welcome. Before opening a change to the physics
or the solver, run `pytest -q tests/` and regenerate the affected result
files. Do not hand-edit numbers in the manuscripts: every value is derived
from the JSON files and checked by the consistency scripts.

If a change affects the production DD mesh, the optimisation histories or the
optical generation rate, all downstream figures, tables and both journal
variants must be regenerated. See `docs/mesh_N97_plan.md` for the checklist.

Please keep negative results visible. The pre-registered E4 verdict is `not
met`; the 16-D supplement passes only by a censored lower bound. Neither is
to be re-labelled after the fact.
