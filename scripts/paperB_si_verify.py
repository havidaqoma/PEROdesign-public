"""Study 2 (Paper B) deterministic verification for SI Note S15. Output phase0/paperB/si_verify.json.
  V1 every feasible call: USD/W recomputed from the stored design + module PCE with the cost engine (rel 1e-9)
  V2 every feasible call: log10_usd_per_W == log10(usd_per_W)
  V3 every run: hv_final recomputed from the stored calls == stored value (exact)
  V4 every run: shared 24-point start identical across methods (same arch, scenario, seed)
  V5 every call: x == to_physical(u, cats) rounded as in design(); HTL/metal match cats
  V6 fresh re-simulation (cache off) of 60 random feasible calls: cell PCE and module PCE bit-identical
Run in WSL: ~/venvs/perodesign-dev/bin/python scripts/paperB_si_verify.py
"""
import json
import math
import os
import random
import sys
import tempfile
from pathlib import Path

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from perodesign.optim import objective_b as B  # noqa: E402
from perodesign.optim import search_b as S  # noqa: E402

PB = REPO / "phase0" / "paperB"


def main():
    runs = {p.stem: json.loads(p.read_text()) for p in sorted((PB / "runs").glob("*.json"))}
    out = {"schema": "perodesign.paperB_si_verify/1", "checks": {}}
    fail = {k: 0 for k in ("V1", "V2", "V3", "V4", "V5")}
    n_feas = n_calls = 0
    for rid, r in runs.items():
        a, s, m, k = rid.split("__")
        sp = B.space(a)
        for c in r["calls"]:
            n_calls += 1
            x, htl, metal = B.to_physical(sp, c["u"], c["cats"])
            d, g = B.design(a, x, htl, s)
            xs = [L["thickness_nm"] for L in d["layers"]] + [g.stripe_width_mm]
            if xs != c["x"] or htl != c["HTL"] or metal != c["metal"]:
                fail["V5"] += 1
            if not c["feasible"]:
                continue
            n_feas += 1
            lib = B.physics_library(a, htl, metal)
            u = B.usd_per_W(d, c["module_pce_pct"], lib)["usd_per_W"]
            if not math.isclose(u, c["usd_per_W"], rel_tol=1e-9):
                fail["V1"] += 1
            if not math.isclose(c["log10_usd_per_W"], math.log10(c["usd_per_W"]), rel_tol=1e-12):
                fail["V2"] += 1
        log = [{"y": ([c["module_pce_pct"], c["log10_usd_per_W"]] if c["feasible"] else None)} for c in r["calls"]]
        if S.hv_curve(log, tuple(r["ref_point"]))[-1] != r["hv_final"]:
            fail["V3"] += 1
    starts = {}
    for rid, r in runs.items():
        a, s, m, k = rid.split("__")
        starts.setdefault((a, s, k), set()).add(json.dumps([(c["u"], c["cats"]) for c in r["calls"][:24]]))
    fail["V4"] = sum(len(v) != 1 for v in starts.values())
    out["checks"] = {"V1_cost_recompute": {"n": n_feas, "fail": fail["V1"]},
                     "V2_log_cost": {"n": n_feas, "fail": fail["V2"]},
                     "V3_hv_final": {"n": len(runs), "fail": fail["V3"]},
                     "V4_shared_start": {"n": len(starts), "fail": fail["V4"]},
                     "V5_design_mapping": {"n": n_calls, "fail": fail["V5"]}}
    # V6 fresh re-simulation (cache off): cell PCE, module PCE and USD/W must be bit-identical
    rng = random.Random(2026)
    pool = [(rid, c) for rid, r in runs.items() for c in r["calls"] if c["feasible"]]
    sample = rng.sample(pool, 60)
    f6 = 0
    rows = []
    with tempfile.TemporaryDirectory() as wd:
        for rid, c in sample:
            a, s, m, k = rid.split("__")
            r = B.evaluate(a, c["u"], c["cats"], s, cache_dir=None, work_root=wd)
            same = (r["cell_pce_pct"] == c["cell_pce_pct"] and r["module_pce_pct"] == c["module_pce_pct"]
                    and r["usd_per_W"] == c["usd_per_W"])
            f6 += not same
            rows.append({"run": rid, "call": c["call"], "combo": f"{c['HTL']}/{c['metal']}", "identical": same})
    out["checks"]["V6_fresh_resim"] = {"n": len(sample), "fail": f6}
    out["fresh_sample"] = rows
    out["n_runs"], out["n_calls"], out["n_feasible"] = len(runs), n_calls, n_feas
    (PB / "si_verify.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["checks"]))
    return 0 if all(v["fail"] == 0 for v in out["checks"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
