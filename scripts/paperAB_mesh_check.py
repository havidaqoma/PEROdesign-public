"""POST-HOC (not pre-registered): spatial grid convergence of the drift-diffusion model.

Both ends of every pooled Pareto front (thickness-only: 6 cases; material choice: 6 cases; 24 designs) are
re-simulated without the result cache at NP = 250 (the value of every run), 500 and 1000 grid points (1000 is the largest
SIMsalabim 5.36 accepts: Max_NP in Units/TypesAndConstants.pp). Checks:
NP = 250 must reproduce the stored module PCE exactly; the change at 500 and 1000 is reported per design, together
with the efficiency and cost gaps of each front and the pre-registered reading (0.2-point line) at every NP.

Output: phase0/paperB/posthoc_mesh.json.  Needs SIMsalabim (PERODESIGN_SIMSALABIM).  Usage: python scripts/paperAB_mesh_check.py [workers]
"""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

NPS = (250, 500, 1000)   # 1000 = SIMsalabim 5.36 maximum (Max_NP, Units/TypesAndConstants.pp:39)
OUT = ROOT / "phase0/paperB/posthoc_mesh.json"
PCE_LINE = 0.2   # pre-registered practical line for a material trade-off (points)


def _lib_np(lib: dict, n: int) -> dict:
    lib = copy.deepcopy(lib)
    lib["device_setup"]["params"]["NP"] = n
    lib["_sha256"] = f"{lib['_sha256']}|NP={n}"
    return lib


def run_one(job: dict) -> dict:
    from perodesign.library import load_library
    from perodesign.physics.simss import SimSS
    n = job["NP"]
    with tempfile.TemporaryDirectory() as wd:
        t0 = time.time()
        if job["level"] == "thickness_only":
            from perodesign.optim import objective as O
            sim = SimSS(library=_lib_np(load_library(), n), cache_dir=None, work_root=wd, timeout_s=3600)
            r = O.evaluate(sim, job["arch"], job["x"], job["scenario"])
            pce, usd, cell = r.get("module_pce_pct"), r.get("usd_per_W"), r.get("cell_pce_pct")
            status = "complete" if r.get("feasible") else f"infeasible: {r.get('reason')}"
        else:
            from perodesign.optim import objective_b as B
            lib = B.physics_library(job["arch"], job["htl"], job["metal"])
            sim = SimSS(library=_lib_np(lib, n), cache_dir=None, work_root=wd, timeout_s=3600)
            d, geom = B.design(job["arch"], job["x"], job["htl"], job["scenario"])
            r = sim.run(d)
            status, pce, usd, cell = r.status, None, None, r.metrics.get("pce_pct")
            if r.status == "complete":
                m = B.module_from_cell(r.metrics, geom)
                pce = m["module_pce_pct"]
                usd = B.usd_per_W(d, pce, lib)["usd_per_W"]
    return {**{k: job[k] for k in ("level", "case", "end", "NP", "combo")}, "status": status,
            "cell_pce_pct": cell, "module_pce_pct": pce, "usd_per_W": usd, "stored_module_pce_pct": job["stored_pce"],
            "stored_usd_per_W": job["stored_usd"], "seconds": round(time.time() - t0, 1)}


def jobs() -> list[dict]:
    from perodesign.optim import objective as O
    from perodesign.optim import objective_b as B
    out = []
    for level, path in (("thickness_only", "phase0/paperA/result.json"), ("material_choice", "phase0/paperB/result.json")):
        cases = json.loads((ROOT / path).read_text(encoding="utf-8"))["cases"]
        for case, c in cases.items():
            arch, scen = case.split("/")
            for end in ("pce_optimal", "cost_optimal"):
                e = c["q2"][end]
                if level == "thickness_only":
                    names, combo, htl, metal = O.space(arch).names, "fixed", None, None
                else:
                    names, combo = B.space(arch).names, e["combo"]
                    htl, metal = combo.split("/")
                x = [float(e["x"][k]) for k in names]
                for n in NPS:
                    out.append({"level": level, "case": case, "end": end, "NP": n, "combo": combo, "arch": arch,
                                "scenario": scen, "x": x, "htl": htl, "metal": metal,
                                "stored_pce": e["module_pce_pct"], "stored_usd": e["usd_per_W"]})
    return out


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    J = jobs()
    J.sort(key=lambda j: -j["NP"])          # slowest first
    with ProcessPoolExecutor(workers) as ex:
        rows = list(ex.map(run_one, J))
    rows.sort(key=lambda r: (r["level"], r["case"], r["end"], r["NP"]))
    idx = {(r["level"], r["case"], r["end"], r["NP"]): r for r in rows}
    ok = lambda r: r["module_pce_pct"] is not None
    failed = [{k: r[k] for k in ("level", "case", "end", "NP", "status")} for r in rows if not ok(r)]
    keys = sorted({(r["level"], r["case"], r["end"]) for r in rows})
    base_ok = all(idx[k + (250,)]["module_pce_pct"] == idx[k + (250,)]["stored_module_pce_pct"] for k in keys)
    dpce, rel_cost = {}, {}
    for n in NPS[1:]:
        pairs = [(idx[k + (n,)], idx[k + (250,)]) for k in keys if ok(idx[k + (n,)]) and ok(idx[k + (250,)])]
        dpce[n] = max(abs(a["module_pce_pct"] - b["module_pce_pct"]) for a, b in pairs)
        rel_cost[n] = max(abs(a["usd_per_W"] / b["usd_per_W"] - 1) for a, b in pairs)
    fronts = []
    for (l, c) in sorted({(r["level"], r["case"]) for r in rows}):
        for n in NPS:
            a, b = idx[(l, c, "pce_optimal", n)], idx[(l, c, "cost_optimal", n)]
            if not (ok(a) and ok(b)):
                fronts.append({"level": l, "case": c, "NP": n, "gap_pce_points": None, "gap_cost_pct": None,
                               "pce_end_more_efficient": None, "above_0p2_line": None})
                continue
            gp = a["module_pce_pct"] - b["module_pce_pct"]
            gc = (a["usd_per_W"] / b["usd_per_W"] - 1) * 100
            fronts.append({"level": l, "case": c, "NP": n, "gap_pce_points": gp, "gap_cost_pct": gc,
                           "pce_end_more_efficient": gp >= 0,
                           "above_0p2_line": (gp >= PCE_LINE) if l == "material_choice" else None})
    base_read = {(f["level"], f["case"]): f["above_0p2_line"] for f in fronts if f["NP"] == 250}
    flips = [{"case": f["case"], "NP": f["NP"], "gap_pce_points": f["gap_pce_points"]} for f in fronts
             if f["level"] == "material_choice" and f["above_0p2_line"] is not None
             and f["above_0p2_line"] != base_read[(f["level"], f["case"])]]
    out = {"schema": "perodesign.posthoc_mesh/v1", "label": "POST-HOC, not pre-registered",
           "NP_values": list(NPS), "simsalabim_max_NP": 1000, "n_designs": len(keys), "n_sims": len(rows), "failed_sims": failed,
           "np250_reproduces_stored_exactly": base_ok,
           "max_abs_dpce_points_vs_np250": dpce, "max_rel_dcost_vs_np250": rel_cost,
           "material_reading_flips": flips,
           "fronts": fronts, "rows": rows}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows", "fronts")}, indent=1))


if __name__ == "__main__":
    main()
