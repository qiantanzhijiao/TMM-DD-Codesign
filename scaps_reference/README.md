# UniDD reference data for SCAPS-1D cross-check

All unidd_*.csv files are UniDD-side reference data, NOT SCAPS output.

Automated workflow (SCAPS 3.3.12 installed, CVI run-time required):

    python build_scaps_inputs.py --deploy \
        --scaps-dir <SCAPS install dir>
    python run_scaps_crosscheck.py \
        --scaps-dir <SCAPS install dir>

The driver checks for cvirte.dll, deploys .def/.gen/.spe/.script, starts
scaps3312.exe with the script on the command line, collects SCAPS .iv/.qe
exports and its native PNG graphs, converts them to CSV, and runs
compare_scaps.py with pre-specified PASS/FAIL criteria. Results land in
../scaps_run/export/; status in ../scaps_run/crosscheck_status.json.

Manual alternative: fill TEMPLATE_*.csv from SCAPS panel exports, then run
    python compare_scaps.py --scaps-dir <dir>

IMPORTANT: SCAPS .def files use SI units (m, m-3, m2/Vs); .gen files use
x in um and G in #/m3.s. UniDD CSVs store G in cm-3 s-1, so multiply by
1e6 when writing the .gen file. UniDD solves drift-diffusion on the
absorber alone: the SCAPS device must be ONE layer, not a three-layer p-i-n.
See ../SCAPS1D交叉验证方案.md (version 3) for the full protocol.
