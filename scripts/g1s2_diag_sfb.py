"""Diagnostic: production n-i-p stack (C60/MAPbI3/PTAA) through the step-2 library, varying ONE device setting at a
time back toward production (W_L/W_R sfb vs 4.05/5.2; back metal Au 101 nm is already the production default).
Usage (WSL): python scripts/g1s2_diag_sfb.py"""
import copy
import hashlib
import sys
from pathlib import Path

sys.argv = [sys.argv[0], "main", "1"]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import g1s2_run as g  # noqa: E402
from perodesign.physics.simss import SimSS  # noqa: E402

des = {"schema": "perodesign.design/1", "architecture": "n-i-p",
       "layers": [{"role": "ETL", "material": "C60", "thickness_nm": 30},
                  {"role": "absorber", "material": "MAPbI3", "thickness_nm": 400},
                  {"role": "HTL", "material": "PTAA", "thickness_nm": 20}]}
for wl, wr, uv in (("sfb", "sfb", None), (4.05, 5.2, None), ("sfb", 5.2, None), (4.05, "sfb", None),
                   ("sfb", "sfb", "untilVoc0")):
    lib = copy.deepcopy(g.step2_library("Au"))
    lib["architecture_setup"]["n-i-p"].update({"W_L_eV": wl, "W_R_eV": wr})
    lib["_sha256"] = hashlib.sha256((lib["_sha256"] + f"{wl}{wr}{uv}").encode()).hexdigest()
    import perodesign.physics.simss as s
    old = dict(s.SOLVER_ARGS_BY_ARCH)
    if uv:
        s.SOLVER_ARGS_BY_ARCH["n-i-p"] = ["-Vmax", "1.4", "-varFile", "none", "-untilVoc", "0"]
    r = SimSS(library=lib).run(des)
    s.SOLVER_ARGS_BY_ARCH.clear(); s.SOLVER_ARGS_BY_ARCH.update(old)
    m = r.metrics
    print(f"W_L {wl!s:5} W_R {wr!s:5} {uv or '':9} {r.status:8s} PCE {m['pce_pct']} Jsc {m['jsc_mA_cm2']} "
          f"Voc {m['voc_V']} | {r.reason}", flush=True)
