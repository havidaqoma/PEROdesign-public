"""Paper A SI verification V-det: re-run selected runs with the SAME code (clone at commit 1bdbecc) and compare every
proposed design (unit-cube u, rounded x) and objective with the stored run file. Run from the run clone in WSL:
  ~/venvs/perodesign-dev/bin/python scripts/paperA_si_rerun.py <repo-with-stored-runs> run_id [run_id ...]
  ~/venvs/perodesign-dev/bin/python scripts/paperA_si_rerun.py <repo-with-stored-runs> fresh <n>   (no cache: real SimSS)
Writes <repo>/phase0/paperA/si/rerun_<run_id>.json (comparison only; never touches runs/)."""
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
CLONE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLONE))
from perodesign.optim import objective as O  # noqa: E402
from perodesign.optim import search as S  # noqa: E402
from perodesign.physics.simss import SimSS  # noqa: E402

CACHE = Path(os.environ.get("PAPERA_CACHE", Path.home() / "perodesign_p1" / "paperA_simss_cache"))


def rerun(stored_repo, rid):
    arch, scen, method, seed = rid.split("__")
    seed = int(seed[1:])
    stored = json.loads((Path(stored_repo) / "phase0" / "paperA" / "runs" / f"{rid}.json").read_text())
    sim = SimSS(cache_dir=CACHE)
    sp = O.space(arch)
    ref = O.reference_point(arch)
    recs = []

    def evalf(U):
        out = []
        for u in U:
            r = O.evaluate(sim, arch, O.from_unit(sp, u), scen)
            r["u"] = [float(v) for v in u]
            recs.append(r)
            out.append((r["module_pce_pct"], r["usd_per_W"]) if r["feasible"] else None)
        return out

    t0 = time.time()
    log = S.run_method(method, evalf, sp.dim, seed, ref)
    du = max(abs(a - b) for r1, r2 in zip(recs, stored["calls"]) for a, b in zip(r1["u"], r2["u"]))
    same_x = sum(r1["x"] == r2["x"] for r1, r2 in zip(recs, stored["calls"]))
    same_y = sum((r1["module_pce_pct"] == r2["module_pce_pct"] and r1["usd_per_W"] == r2["usd_per_W"])
                 for r1, r2 in zip(recs, stored["calls"]))
    first_diff = next((i for i, (r1, r2) in enumerate(zip(recs, stored["calls"])) if r1["x"] != r2["x"]), None)
    out = {"run_id": rid, "code_commit_of_clone": os.popen(f"git -C {CLONE} rev-parse --short HEAD").read().strip(),
           "n_calls": len(recs), "identical_x": same_x, "identical_objectives": same_y, "max_abs_du": du,
           "first_differing_call": first_diff, "hv_final_rerun": S.hv_curve(log, ref)[-1], "hv_final_stored": stored["hv_final"],
           "seconds": round(time.time() - t0, 1)}
    dst = Path(stored_repo) / "phase0" / "paperA" / "si" / f"rerun_{rid}.json"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, indent=1))
    print(json.dumps(out), flush=True)


def fresh(stored_repo, n, seed=20261001):
    """Re-simulate n randomly chosen stored calls WITHOUT the cache and compare every output exactly."""
    import random
    from concurrent.futures import ProcessPoolExecutor
    files = sorted((Path(stored_repo) / "phase0" / "paperA" / "runs").glob("*.json"))
    calls = [(json.loads(p.read_text()), p.stem) for p in files]
    pool = [(r["arch"], r["scenario"], c, rid) for r, rid in calls for c in r["calls"]]
    pick = random.Random(seed).sample(pool, n)
    with ProcessPoolExecutor(max_workers=12) as ex:
        out = list(ex.map(_fresh_one, pick))
    keys = ("sim_status", "cell_pce_pct", "voc_V", "ff", "jsc_mA_cm2", "module_pce_pct", "usd_per_W", "materials_usd_m2", "feasible")
    same = {k: sum(o["new"].get(k) == o["stored"].get(k) for o in out) for k in keys}
    res = {"n": n, "sample_seed": seed, "identical_by_field": same, "all_identical": all(v == n for v in same.values()),
           "code_commit_of_clone": os.popen(f"git -C {CLONE} rev-parse --short HEAD").read().strip(),
           "rows": [{"run": o["rid"], "call": o["stored"]["call"], "x": o["stored"]["x"],
                     **{f"stored_{k}": o["stored"].get(k) for k in keys}, **{f"new_{k}": o["new"].get(k) for k in keys},
                     "new_seconds": o["new"]["seconds"]} for o in out]}
    dst = Path(stored_repo) / "phase0" / "paperA" / "si" / "fresh_simss_check.json"
    dst.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("n", "identical_by_field", "all_identical")}), flush=True)


def _fresh_one(item):
    arch, scen, c, rid = item
    sim = SimSS(cache_dir=None)
    r = O.evaluate(sim, arch, c["x"], scen)
    return {"rid": rid, "stored": c, "new": r}


if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor
    if sys.argv[2] == "fresh":
        fresh(sys.argv[1], int(sys.argv[3]))
        sys.exit(0)
    repo, ids = sys.argv[1], sys.argv[2:]
    with ProcessPoolExecutor(max_workers=len(ids)) as ex:
        list(ex.map(rerun, [repo] * len(ids), ids))
