"""Paper A runs (docs/PaperA_preregistration.md). One process per (stack, scenario, method, seed) run; inside a run the
simulator calls of a batch run one after another. Each run writes phase0/paperA/runs/<run_id>.json when it
finishes (atomic), so the job is resumable: finished runs are skipped.

  python scripts/paperA_run.py run [workers]     -> phase0/paperA/runs/*.json
  python scripts/paperA_run.py analyse           -> phase0/paperA/result.json
Run in WSL from a native-FS clone (see skill grpo-simulator-reward): ~/venvs/perodesign-dev/bin/python ...
"""
import os
import sys

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import json  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ProcessPoolExecutor, as_completed  # noqa: E402
from pathlib import Path  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO / "phase0" / "paperA"
RUNS = OUT / "runs"
# SimSS result cache (keyed on design + library + binary hashes). A cache hit still counts as a call. Kept outside
# the repo (large); set PAPERA_CACHE to override.
CACHE = Path(os.environ.get("PAPERA_CACHE", Path.home() / "perodesign_p1" / "paperA_simss_cache"))
CENSORED = 241                                        # calls-to-95% value for a run that never reaches 95% (§7)
ARCHS = ("p-i-n", "n-i-p")
SCENS = ("base", "worse", "better")
METHODS = ("random", "nsga2", "qnehvi")
SEEDS = (0, 1, 2, 3, 4)


def run_id(arch, scen, method, seed):
    return f"{arch}__{scen}__{method}__s{seed}"


def jobs():
    return [(a, s, m, k) for a in ARCHS for s in SCENS for m in METHODS for k in SEEDS]


def _one(job):
    from perodesign.optim import objective as O
    from perodesign.optim import search as S
    from perodesign.physics.simss import SimSS
    arch, scen, method, seed = job
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
    for rec, entry in zip(recs, log):
        assert rec["u"] == entry["u"], "call log and records out of step"
        rec["call"], rec["batch"] = entry["call"], entry["batch"]
    res = {"run_id": run_id(*job), "arch": arch, "scenario": scen, "method": method, "seed": seed,
           "space": {"names": sp.names, "lo": sp.lo, "hi": sp.hi}, "ref_point": ref, "budget": S.BUDGET,
           "seconds": round(time.time() - t0, 1), "sim_binary_sha256": sim.binary_sha256,
           "library_sha256": sim.library["_sha256"], "n_infeasible": sum(not r["feasible"] for r in recs),
           "hv_final": S.hv_curve(log, ref)[-1], "calls": recs}
    RUNS.mkdir(parents=True, exist_ok=True)
    tmp = RUNS / f".{res['run_id']}.tmp"
    tmp.write_text(json.dumps(res))
    os.replace(tmp, RUNS / f"{res['run_id']}.json")
    return res["run_id"], res["seconds"], res["n_infeasible"]


def run(workers):
    RUNS.mkdir(parents=True, exist_ok=True)
    todo = [j for j in jobs() if not (RUNS / f"{run_id(*j)}.json").exists()]
    # slow BO runs first, so they do not form the tail
    todo.sort(key=lambda j: (j[2] != "qnehvi", j[2] != "nsga2"))
    print(f"runs {len(jobs())} todo {len(todo)} workers {workers}", flush=True)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_one, j): j for j in todo}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                rid, sec, ninf = f.result()
                print(f"{i}/{len(todo)} done {rid} {sec:.0f}s infeasible {ninf}", flush=True)
            except Exception as e:                     # a crashed run is reported, never silently skipped
                print(f"{i}/{len(todo)} ERROR {run_id(*futs[f])}: {type(e).__name__}: {e}", flush=True)
    missing = [run_id(*j) for j in jobs() if not (RUNS / f"{run_id(*j)}.json").exists()]
    print("DONE missing", len(missing), missing, flush=True)


# ------------------------------------------------------------------ analysis (§7)
def load_runs():
    out = {}
    for j in jobs():
        p = RUNS / f"{run_id(*j)}.json"
        if not p.exists():
            raise FileNotFoundError(f"run missing: {p.name}")
        out[j] = json.loads(p.read_text())
    return out


def analyse():
    from perodesign.optim import objective as O
    from perodesign.optim import search as S
    R = load_runs()
    res = {"schema": "perodesign.paperA_result/1", "preregistration": "docs/PaperA_preregistration.md",
           "claim_scope": "model predictions (G1 NO-GO, MASTER §25); optimal = inside this model and these bounds",
           "cases": {}}
    for arch in ARCHS:
        ref = O.reference_point(arch)
        sp = O.space(arch)
        for scen in SCENS:
            case = {"ref_point": ref, "methods": {}}
            allpts, runs_here = [], [R[(arch, scen, m, k)] for m in METHODS for k in SEEDS]
            best_hv = max(S.hv2d([(c["module_pce_pct"], c["usd_per_W"]) for c in r["calls"] if c["feasible"]], ref)
                          for r in runs_here)
            for m in METHODS:
                hvs, n95, inf = [], [], []
                for k in SEEDS:
                    r = R[(arch, scen, m, k)]
                    log = [{"y": ([c["module_pce_pct"], c["usd_per_W"]] if c["feasible"] else None)} for c in r["calls"]]
                    curve = S.hv_curve(log, ref)
                    hvs.append(curve[-1])
                    n95.append(next((i + 1 for i, h in enumerate(curve) if h >= 0.95 * best_hv), CENSORED))
                    inf.append(r["n_infeasible"])
                    allpts += [c for c in r["calls"] if c["feasible"]]
                mean, half = S.t_ci95(hvs)
                med = sorted(n95)[len(n95) // 2]
                case["methods"][m] = {"hv_final": hvs, "hv_mean": mean, "hv_ci95_half": half,
                                      "calls_to_95pct_best": n95,
                                      "calls_to_95pct_best_median": (f">{S.BUDGET}" if med == CENSORED else med),
                                      "n_infeasible": inf, "max_infeasible_frac": max(inf) / S.BUDGET}
            # Q1 verdicts: CI non-overlap only
            ms = case["methods"]
            def beats(a, b):
                return ms[a]["hv_mean"] - ms[a]["hv_ci95_half"] > ms[b]["hv_mean"] + ms[b]["hv_ci95_half"]
            case["q1"] = {f"{a}>{b}": beats(a, b) for a in METHODS for b in METHODS if a != b}
            case["unreliable"] = any(v["max_infeasible_frac"] > 0.05 for v in ms.values())   # any single run > 12 calls
            case["best_hv_any_run"] = best_hv
            # Q2: pooled front; exact (PCE, USD/W) ties keep the lowest design hash (deterministic)
            by_pt = {}
            for c in sorted(allpts, key=lambda c: c["design_hash"]):
                by_pt.setdefault((c["module_pce_pct"], c["usd_per_W"]), c)
            front = S.pareto(by_pt)
            p_opt, c_opt = by_pt[front[0]], by_pt[front[-1]]
            d_pce = p_opt["module_pce_pct"] - c_opt["module_pce_pct"]
            d_cost = p_opt["usd_per_W"] / c_opt["usd_per_W"] - 1
            def summ(c):
                d, g = O.design(arch, c["x"], scen)
                parts = O.cost_per_watt(c["materials_usd_m2"], c["module_pce_pct"], O.cost_line())["parts_usd_per_W"]
                rows = {reg: O.usd_per_W(d, c["module_pce_pct"], O.cost_line(reg))["usd_per_W"] for reg in ("MY", "CN", "IN")}
                return {"x": dict(zip(sp.names, c["x"])), "module_pce_pct": c["module_pce_pct"],
                        "cell_pce_pct": c["cell_pce_pct"], "usd_per_W": c["usd_per_W"],
                        "usd_per_W_high_prices": c["usd_per_W_high_prices"], "materials_usd_m2": c["materials_usd_m2"],
                        "parts_usd_per_W": parts, "usd_per_W_by_rate_region": rows, "design_hash": c["design_hash"]}
            case["q2"] = {"front_size": len(front), "front": front, "pce_optimal": summ(p_opt), "cost_optimal": summ(c_opt),
                          "gap_pce_points": d_pce, "gap_cost_pct": 100 * d_cost,
                          "gap_small": bool(d_pce < 1.0 and 100 * d_cost < 5.0), "n_feasible_pooled": len(by_pt)}
            res["cases"][f"{arch}/{scen}"] = case
    # Q3 robustness per stack
    for arch in ARCHS:
        sp = O.space(arch)
        span = sp.hi[1] - sp.lo[1]                     # absorber is index 1 in both stacks
        cs = [res["cases"][f"{arch}/{s}"] for s in SCENS]
        same_q1 = all(c["q1"] == cs[0]["q1"] for c in cs)
        some_beats_random = any(all(c["q1"][f"{m}>random"] for c in cs) for m in ("nsga2", "qnehvi"))
        moves = {}
        for which in ("pce_optimal", "cost_optimal"):
            t = [c["q2"][which]["x"]["MAPbI3_nm"] for c in cs]
            moves[which] = (max(t) - min(t)) / span        # peak-to-peak over the 3 scenarios
        res.setdefault("q3", {})[arch] = {
            "q1_same_in_all_scenarios": same_q1, "some_method_beats_random_in_all": some_beats_random,
            "q1_robust": bool(same_q1 and some_beats_random),
            "absorber_move_frac_of_range": moves, "designs_robust": bool(all(v < 0.20 for v in moves.values()))}
    (OUT / "result.json").write_text(json.dumps(res, indent=1))
    for k, c in res["cases"].items():
        print(k, {m: (round(v["hv_mean"], 4), round(v["hv_ci95_half"], 4)) for m, v in c["methods"].items()},
              "gap", round(c["q2"]["gap_pce_points"], 2), "pt", round(c["q2"]["gap_cost_pct"], 1), "%",
              "unreliable" if c["unreliable"] else "")
    print("q3", res["q3"])
    return res


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 12)
    elif cmd == "analyse":
        analyse()
    else:
        raise SystemExit(f"unknown command {cmd}")
