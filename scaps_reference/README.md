# UniDD reference data for SCAPS-1D cross-check

Fill TEMPLATE_*.csv from SCAPS exports (rename to dark_JV.csv, light_JV.csv, EQE.csv, generation_profile.csv) and put them in one directory, then run:

    python compare_scaps.py --scaps-dir <dir>

See ../SCAPS1D交叉验证方案.md for the GUI procedure, parameter alignment table and acceptance criteria. Record the SCAPS version and every setting in metadata.txt.
