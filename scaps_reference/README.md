# UniDD reference data for SCAPS-1D cross-check

All unidd_*.csv files are UniDD-side reference data, NOT SCAPS output.

Workflow:
1. Install SCAPS-1D and record the exact version in metadata.txt.
2. Build the device once in the GUI and save the .def / action / spectrum
   files; then run unidd_crosscheck.script in the built-in script editor
   (or do the equivalent show/save operations in the panels). SCAPS
   natively exports both ASCII results and PNG graphs.
3. Fill TEMPLATE_*.csv from the SCAPS exports (rename to dark_JV.csv,
   light_JV.csv, EQE.csv, generation_profile.csv) in one directory.
4. Run:

    python compare_scaps.py --scaps-dir <dir>

See ../SCAPS1D交叉验证方案.md for the three execution modes, the
parameter alignment table, unit conversions and acceptance criteria.
Script command names vary across SCAPS builds: verify each line in the
built-in script editor before running the whole file.
