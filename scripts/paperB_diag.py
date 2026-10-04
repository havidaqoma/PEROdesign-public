"""Paper B pre-registration diagnostics (run before the freeze, disclosed in prereg §9; output phase0/paperB/diag.json).

D1 noise floor: module PCE of the reference design (NiOx/Cu and NiOx/Ag, both stacks, base) with the absorber moved in
   0.1 nm steps over 1.9 nm (20 sims each). Noise = SD of the residuals from a straight-line fit; compared with the
   Ag - Cu difference at the same thicknesses (paired).
D2 contact attribution (agy review finding 5): n-i-p, reference design. NiOx/Cu with the anode set to PTAA's E_v
   (5.4 eV) and PTAA/Cu with the anode at NiOx's E_v (5.7 eV), against both under B2. If NiOx's advantage survives with
   the same anode, it is not a contact artefact of rule B2.
Usage (WSL): ~/venvs/perodesign-dev/bin/python scripts/paperB_diag.py
"""
import copy
import hashlib
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO / "phase0" / "paperB"


def _ref_u(arch, htl, dx_abs=0.0):
    from perodesign.optim import objective as A
    from perodesign.optim import objective_b as B
    lo, hi = B.bounds(arch, htl)
    x = [min(max(v, a), b) for v, a, b in zip(A.REFERENCE[arch], lo, hi)]
    x[1] += dx_abs
    return x, [(v - a) / (b - a) for v, a, b in zip(x, lo, hi)]


def d1(job):
    from perodesign.optim import objective_b as B
    arch, metal, k = job
    x, u = _ref_u(arch, "NiOx", 0.1 * k)
    r = B.evaluate(arch, u, [0, B.METALS.index(metal)], "base")
    return {"arch": arch, "metal": metal, "k": k, "absorber_nm": x[1], "x_used": r["x"],
            "module_pce_pct": r["module_pce_pct"], "cell_pce_pct": r["cell_pce_pct"], "status": r["sim_status"]}


def d2(job):
    from perodesign.optim import objective_b as B
    from perodesign.physics.simss import SimSS
    htl, wr = job
    arch = "n-i-p"
    x, _ = _ref_u(arch, htl)
    lib = copy.deepcopy(B.physics_library(arch, htl, "Cu"))
    if wr is not None:
        lib["architecture_setup"][arch]["W_R_eV"] = wr
        lib["_sha256"] = hashlib.sha256((lib["_sha256"] + f"|diagWR{wr}").encode()).hexdigest()
    d, geom = B.design(arch, x, htl)
    r = SimSS(library=lib).run(d)
    from perodesign.module import module_from_cell
    m = module_from_cell(r.metrics, geom) if r.status == "complete" else {}
    s = B.physics_setup(lib, arch)
    return {"HTL": htl, "W_L_eV": s["W_L_eV"], "W_R_eV": s["W_R_eV"], "status": r.status,
            "cell_pce_pct": r.metrics.get("pce_pct"), "voc_V": r.metrics.get("voc_V"), "ff": r.metrics.get("ff"),
            "jsc_mA_cm2": r.metrics.get("jsc_mA_cm2"), "module_pce_pct": m.get("module_pce_pct")}


def main():
    import numpy as np
    OUT.mkdir(parents=True, exist_ok=True)
    j1 = [(a, m, k) for a in ("p-i-n", "n-i-p") for m in ("Cu", "Ag") for k in range(20)]
    j2 = [("NiOx", None), ("NiOx", 5.4), ("PTAA", None), ("PTAA", 5.7)]
    with ProcessPoolExecutor(max_workers=12) as ex:
        r1 = list(ex.map(d1, j1))
        r2 = list(ex.map(d2, j2))
    res = {"schema": "perodesign.paperB_diag/1", "d1_records": r1, "d2": r2, "d1": {}}
    for a in ("p-i-n", "n-i-p"):
        row = {}
        for m in ("Cu", "Ag"):
            rs = sorted([r for r in r1 if r["arch"] == a and r["metal"] == m], key=lambda r: r["k"])
            t = np.array([r["absorber_nm"] for r in rs])
            y = np.array([r["module_pce_pct"] for r in rs])
            fit = np.polyfit(t, y, 1)
            resid = y - np.polyval(fit, t)
            row[m] = {"n": len(rs), "resid_sd_points": float(resid.std(ddof=2)), "resid_max_abs": float(abs(resid).max()),
                      "slope_points_per_nm": float(fit[0]), "range_points": float(y.max() - y.min())}
        cu = {r["k"]: r["module_pce_pct"] for r in r1 if r["arch"] == a and r["metal"] == "Cu"}
        ag = {r["k"]: r["module_pce_pct"] for r in r1 if r["arch"] == a and r["metal"] == "Ag"}
        diff = np.array([ag[k] - cu[k] for k in sorted(cu)])
        row["ag_minus_cu"] = {"mean": float(diff.mean()), "sd": float(diff.std(ddof=1)), "min": float(diff.min()),
                              "max": float(diff.max())}
        res["d1"][a] = row
        print("D1", a, row, flush=True)
    for r in r2:
        print("D2", r, flush=True)
    (OUT / "diag.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
