"""Paper B gate G0 (baseline reproduction) + the one-change-at-a-time deltas. Committed with its output
phase0/paperB/gate0.json BEFORE the pre-registration is frozen.

G0 (must pass): objective_b in production mode (contact_rule="production", optics="production") gives EXACTLY the
Paper A objective (objective.evaluate) on
  - the two Paper A reference designs (p-i-n 15/600/30/10 nm 6 mm; n-i-p 10/500/10 nm 6 mm), base scenario;
  - the Paper A pooled PCE-optimal designs of all 6 (stack, scenario) cases (phase0/paperA/result.json),
    re-simulated: module PCE must equal the stored value to 1e-9 and USD/W to 1e-9 relative.
Deltas (reported, not gated), production combination only, one change at a time:
  step 1 optics:   production -> McPeak 2015 metal optics (n-i-p: nk_Au.txt -> nk_Au_McPeak2015.txt; p-i-n no change)
  step 2 contacts: production -> B2 band-edge contacts
Usage (WSL): ~/venvs/perodesign-dev/bin/python scripts/paperB_gate0.py
"""
import json
import math
import os
import sys
from pathlib import Path

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from perodesign.optim import objective as A  # noqa: E402
from perodesign.optim import objective_b as B  # noqa: E402
from perodesign.physics.simss import SimSS  # noqa: E402

OUT = REPO / "phase0" / "paperB"


def unit_cont(arch, x, htl):
    lo, hi = B.bounds(arch, htl)
    return [(v - a) / (b - a) for v, a, b in zip(x, lo, hi)]


def cats_of(arch):
    htl, metal = B.PRODUCTION_COMBO[arch]
    return [B.HTLS.index(htl), B.METALS.index(metal)], htl


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    simA = SimSS()
    res = {"schema": "perodesign.paperB_gate0/1", "g0_checks": [], "deltas": []}
    paperA = json.loads((REPO / "phase0" / "paperA" / "result.json").read_text())
    todo = [(arch, "base", list(A.REFERENCE[arch]), "reference") for arch in A.STACKS]
    for key, c in paperA["cases"].items():
        arch, scen = key.split("/")
        p = c["q2"]["pce_optimal"]
        todo.append((arch, scen, [p["x"][n] for n in A.space(arch).names], "paperA_pce_optimal",
                     p["module_pce_pct"], p["usd_per_W"]))
    ok_all = True
    for item in todo:
        arch, scen, x, what = item[:4]
        cats, htl = cats_of(arch)
        ra = A.evaluate(simA, arch, x, scen)
        rb = B.evaluate(arch, unit_cont(arch, x, htl), cats, scen, contact_rule="production", optics="production")
        chk = {"arch": arch, "scenario": scen, "what": what, "x": x,
               "A": [ra["module_pce_pct"], ra["usd_per_W"]], "B": [rb["module_pce_pct"], rb["usd_per_W"]],
               "same_design_hash": ra["design_hash"] == rb["design_hash"],
               "same_library_sha": rb["library_sha256"] == simA.library["_sha256"]}
        ok = (ra["feasible"] and rb["feasible"] and chk["same_design_hash"] and chk["same_library_sha"]
              and abs(ra["module_pce_pct"] - rb["module_pce_pct"]) < 1e-9
              and math.isclose(ra["usd_per_W"], rb["usd_per_W"], rel_tol=1e-9))
        if len(item) == 6:            # also equal to the value stored by the Paper A runs
            chk["stored"] = [item[4], item[5]]
            ok = ok and abs(item[4] - ra["module_pce_pct"]) < 1e-9 and math.isclose(item[5], ra["usd_per_W"], rel_tol=1e-9)
        chk["pass"] = bool(ok)
        ok_all &= chk["pass"]
        res["g0_checks"].append(chk)
        print(what, arch, scen, chk["A"], chk["B"], chk.get("stored"), "PASS" if ok else "FAIL", flush=True)
    res["g0_pass"] = bool(ok_all)
    # deltas, reference designs, base scenario
    for arch in A.STACKS:
        cats, htl = cats_of(arch)
        u = unit_cont(arch, list(A.REFERENCE[arch]), htl)
        row = {"arch": arch, "x": list(A.REFERENCE[arch])}
        for label, cr, op in (("production", "production", "production"), ("step1_mcpeak_optics", "production", "mcpeak"),
                              ("step2_b2_contacts", "B2", "mcpeak")):
            r = B.evaluate(arch, u, cats, "base", contact_rule=cr, optics=op)
            lib = B.physics_library(arch, htl, B.PRODUCTION_COMBO[arch][1], cr, op)
            s = B.physics_setup(lib, arch)
            row[label] = {k: r[k] for k in ("sim_status", "cell_pce_pct", "voc_V", "ff", "jsc_mA_cm2", "module_pce_pct",
                                             "usd_per_W", "back_electrode_usd_m2")}
            row[label]["setup"] = {k: s[k] for k in ("W_L_eV", "W_R_eV", "nkBE_file", "L_BE_m")}
        res["deltas"].append(row)
        print("delta", arch, {k: (v["cell_pce_pct"], v["usd_per_W"]) for k, v in row.items() if isinstance(v, dict)}, flush=True)
    (OUT / "gate0.json").write_text(json.dumps(res, indent=1))
    print("G0", "PASS" if ok_all else "FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
