"""Paper B runs (docs/PaperB_preregistration.md). One process per (stack, scenario, method, seed) run; each run writes
phase0/paperB/runs/<run_id>.json atomically when it finishes, so the job is resumable (finished runs are skipped).

  python scripts/paperB_run.py run [workers]     -> phase0/paperB/runs/*.json
  python scripts/paperB_run.py analyse           -> phase0/paperB/result.json
  python scripts/paperB_run.py swf               -> phase0/paperB/swf.json   (sensitivity S-WF, after analyse)
Run in WSL from a native-FS clone: ~/venvs/perodesign-dev/bin/python scripts/paperB_run.py ...
"""
import os
import sys

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import json  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ProcessPoolExecutor, as_completed  # noqa: E402
from pathlib import Path  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
OUT = REPO / "phase0" / "paperB"
RUNS = OUT / "runs"
CACHE = Path(os.environ.get("PAPERB_CACHE", Path.home() / "perodesign_p1" / "paperB_simss_cache"))
WORK = Path(os.environ.get("PAPERB_WORK", Path.home() / "perodesign_p1" / "paperB_work"))
CENSORED = 241
DPCE_MIN = 0.2          # prereg §7 practical PCE resolution for the wording rule (convention; model noise 0.003, diag D1)
ARCHS = ("p-i-n", "n-i-p")
SCENS = ("base", "worse", "better")
METHODS = ("random", "nsga2", "mixbo")
SEEDS = (0, 1, 2, 3, 4)


def run_id(arch, scen, method, seed):
    return f"{arch}__{scen}__{method}__s{seed}"


def jobs():
    """All 90 (stack, scenario, method, seed) jobs. PAPERB_ONLY (comma-separated run ids) restricts a runner process to
    a disjoint subset, so a second runner can share the work (A3 addendum: scheduling only)."""
    allj = [(a, s, m, k) for a in ARCHS for s in SCENS for m in METHODS for k in SEEDS]
    only = os.environ.get("PAPERB_ONLY")
    if only:
        keep = set(only.split(","))
        allj = [j for j in allj if run_id(*j) in keep]
        if len(allj) != len(keep):
            raise SystemExit(f"PAPERB_ONLY names unknown run ids: {sorted(keep - {run_id(*j) for j in allj})}")
    return allj


def _one(job):
    from perodesign.optim import objective_b as B
    from perodesign.optim import search_b as S
    arch, scen, method, seed = job
    sp = B.space(arch)
    ref = B.reference_point(arch)
    recs = []

    def evalf(points):
        out = []
        for uc, cats in points:
            r = B.evaluate(arch, uc, cats, scen, cache_dir=CACHE, work_root=WORK)
            r["u"] = [float(v) for v in uc]
            recs.append(r)
            out.append((r["module_pce_pct"], r["log10_usd_per_W"]) if r["feasible"] else None)
        return out

    t0 = time.time()
    log = S.run_method(method, evalf, sp, seed, ref)
    for rec, entry in zip(recs, log):
        assert rec["u"] == entry["u"] and rec["cats"] == entry["cats"], "call log and records out of step"
        rec["call"], rec["batch"] = entry["call"], entry["batch"]
    res = {"run_id": run_id(*job), "arch": arch, "scenario": scen, "method": method, "seed": seed,
           "space": {"names": sp.names, "cat_names": sp.cat_names, "cat_values": sp.cat_values},
           "ref_point": ref, "budget": S.BUDGET, "seconds": round(time.time() - t0, 1),
           "overlay_sha256": B.overlay_sha256(), "n_infeasible": sum(not r["feasible"] for r in recs),
           "hv_final": S.hv_curve(log, ref)[-1], "calls": recs}
    RUNS.mkdir(parents=True, exist_ok=True)
    tmp = RUNS / f".{res['run_id']}.tmp"
    tmp.write_text(json.dumps(res))
    os.replace(tmp, RUNS / f"{res['run_id']}.json")
    return res["run_id"], res["seconds"], res["n_infeasible"]


def run(workers, bo_max=None):
    """Amendment A2: at most bo_max mixed-BO runs at once (one qLogNEHVI step holds ~3.5-5.7 GB; 12 at once hit the
    47 GB WSL limit and the OOM killer broke the pool). The other slots run random/NSGA-II. Scheduling only: the
    designs a run evaluates depend on its seed alone. A broken pool is rebuilt and unfinished runs are resubmitted
    once (prereg §7: a crashed run is re-run once with the same seed)."""
    from concurrent.futures import FIRST_COMPLETED, wait
    from concurrent.futures.process import BrokenProcessPool
    bo_max = int(os.environ.get("PAPERB_BO_MAX", 6)) if bo_max is None else bo_max
    RUNS.mkdir(parents=True, exist_ok=True)
    attempts = {}
    for round_ in (1, 2):
        todo = [j for j in jobs() if not (RUNS / f"{run_id(*j)}.json").exists()]
        todo.sort(key=lambda j: (j[2] != "mixbo", j[2] != "nsga2"))      # slow BO runs first
        print(f"round {round_}: runs {len(jobs())} todo {len(todo)} workers {workers} bo_max {bo_max}", flush=True)
        if not todo:
            break
        broken = False
        with ProcessPoolExecutor(max_workers=workers) as ex:
            running = {}
            queue = list(todo)
            while queue or running:
                n_bo = sum(1 for j in running.values() if j[2] == "mixbo")
                while queue and len(running) < workers:
                    pick = next((j for j in queue if j[2] != "mixbo" or n_bo < bo_max), None)
                    if pick is None:
                        break
                    queue.remove(pick)
                    attempts[pick] = attempts.get(pick, 0) + 1
                    running[ex.submit(_one, pick)] = pick
                    n_bo += pick[2] == "mixbo"
                done, _ = wait(list(running), return_when=FIRST_COMPLETED)
                for f in done:
                    j = running.pop(f)
                    try:
                        rid, sec, ninf = f.result()
                        print(f"done {rid} {sec:.0f}s infeasible {ninf}", flush=True)
                    except BrokenProcessPool as e:                 # OOM or kill: rebuild the pool in round 2
                        print(f"ERROR {run_id(*j)}: BrokenProcessPool: {e}", flush=True)
                        broken = True
                    except Exception as e:                         # a crashed run is reported, never silently skipped
                        print(f"ERROR {run_id(*j)}: {type(e).__name__}: {e}", flush=True)
                if broken:
                    for f, j in running.items():
                        f.cancel()
                    break
        if not broken and round_ == 1:
            missing = [j for j in jobs() if not (RUNS / f"{run_id(*j)}.json").exists()]
            if not missing:
                break
    missing = [run_id(*j) for j in jobs() if not (RUNS / f"{run_id(*j)}.json").exists()]
    print("DONE missing", len(missing), missing, flush=True)


# ------------------------------------------------------------------ analysis (prereg §7)
def load_runs():
    out = {}
    for j in jobs():
        p = RUNS / f"{run_id(*j)}.json"
        if not p.exists():
            raise FileNotFoundError(f"run missing: {p.name}")
        out[j] = json.loads(p.read_text())
    return out


def combo(c):
    return f"{c['HTL']}/{c['metal']}"


def wording(n_combos, gap_small, d_pce):
    """Prereg §7 wording taxonomy (complete: every case maps to exactly one label)."""
    if n_combos == 1:
        return "one_material_set_dominates"
    if gap_small:
        return "near_identical_materials"
    if d_pce < DPCE_MIN:
        return "cost_differs_efficiency_practically_equal"
    return "material_trade_off_exists"


def igd_plus(points, front, lo, span):
    """IGD+ (Ishibuchi 2015) of a run's feasible points to the reference front, both as (pce, log10 usd), in the
    minimisation form (-pce, log10 usd) normalised by the pooled feasible range. Lower is better; inf if no point."""
    if not points:
        return math.inf
    tot = 0.0
    for zp, zc in front:
        z = ((-zp - lo[0]) / span[0], (zc - lo[1]) / span[1])
        best = math.inf
        for ap, ac in points:
            a = ((-ap - lo[0]) / span[0], (ac - lo[1]) / span[1])
            best = min(best, math.hypot(max(a[0] - z[0], 0.0), max(a[1] - z[1], 0.0)))
        tot += best
    return tot / len(front)


def q4_break_even(arch, scen, by_pt, q2):
    """Prereg Q4: for each metal m in (Cu, Ag): D_P = pooled PTAA/m design with the highest module PCE, D_N = pooled
    NiOx/m design with the highest module PCE. p* = PTAA price (USD/g) at which USD/W(D_P) = USD/W(D_N), everything
    else fixed. USD/W is linear in the PTAA price: dUSD/W/dp = PTAA item (USD/m2) / p0 / good W per m2.
    Also p*_front = price at which D_P reaches the cost-optimal USD/W of the pooled front."""
    from perodesign.optim import objective as A
    from perodesign.optim import objective_b as B
    from perodesign.tea import evaluate_cost, load_cost_library
    lib_c = load_cost_library()
    p0 = next(e for e in lib_c["entries"] if e["id"] == lib_c["layer_materials"]["PTAA"]["price"])["value"]
    out = {"ptaa_price_base_usd_g": p0, "by_metal": {}}
    for m in ("Cu", "Ag"):
        cs = {h: [c for c in by_pt.values() if c["HTL"] == h and c["metal"] == m] for h in B.HTLS}
        if not cs["PTAA"] or not cs["NiOx"]:
            out["by_metal"][m] = None
            continue
        dp = sorted(cs["PTAA"], key=lambda c: (-c["module_pce_pct"], c["design_hash"]))[0]
        dn = sorted(cs["NiOx"], key=lambda c: (-c["module_pce_pct"], c["design_hash"]))[0]
        lib = B.physics_library(arch, "PTAA", m)
        d, _ = B.design(arch, dp["x"], "PTAA", scen)
        r = evaluate_cost(d, dp["module_pce_pct"], A.cost_line(), assumptions=A.ASM,
                          physics_setup=B.physics_setup(lib, arch), physics_library=lib)
        item = next(i["usd_m2"] for i in r["materials"]["items"] if i["item"] == "layer:HTL:PTAA")
        slope = item / p0 / r["breakdown"]["good_W_per_m2"]          # USD/W per (USD/g)
        base_usd = r["usd_per_W"]
        pstar = p0 + (dn["usd_per_W"] - base_usd) / slope
        pfront = p0 + (q2["cost_optimal"]["usd_per_W"] - base_usd) / slope
        adv = dp["module_pce_pct"] - dn["module_pce_pct"]
        status = ("PTAA not competitive at any price in this model" if (adv <= 0 or pstar <= 0)
                  else "break-even below current price" if pstar < p0 else "PTAA already competitive at current price")
        out["by_metal"][m] = {"PTAA_best": {"x": dp["x"], "module_pce_pct": dp["module_pce_pct"], "usd_per_W": base_usd},
                              "NiOx_best": {"x": dn["x"], "module_pce_pct": dn["module_pce_pct"], "usd_per_W": dn["usd_per_W"]},
                              "ptaa_item_usd_m2": item, "slope_usd_W_per_usd_g": slope, "status": status,
                              "break_even_vs_NiOx_usd_g": (pstar if status != "PTAA not competitive at any price in this model"
                                                           else None),
                              "break_even_vs_NiOx_algebraic_usd_g": pstar,
                              "break_even_vs_front_cost_optimal_usd_g": pfront if pfront > 0 else None,
                              "ptaa_pce_advantage_points": adv}
    return out


def analyse(runs=None, out_path=None, q4=True):
    from scipy.stats import spearmanr
    from perodesign.optim import objective as A
    from perodesign.optim import objective_b as B
    from perodesign.optim import search_b as S
    R = runs if runs is not None else load_runs()
    res = {"schema": "perodesign.paperB_result/1", "preregistration": "docs/PaperB_preregistration.md",
           "claim_scope": "model predictions (G1 NO-GO, MASTER §25); optimal = inside this model, these bounds and "
                          "these 6 material combinations; contacts = rule B2 (barrier-free)", "cases": {}}
    combos = [f"{h}/{m}" for h in B.HTLS for m in B.METALS]
    for arch in ARCHS:
        ref = B.reference_point(arch)
        for scen in SCENS:
            case = {"ref_point": ref, "methods": {}}
            runs_here = [R[(arch, scen, m, k)] for m in METHODS for k in SEEDS]
            def ylog(r):
                return [{"y": ([c["module_pce_pct"], c["log10_usd_per_W"]] if c["feasible"] else None)} for c in r["calls"]]
            best_hv = max(S.hv_curve(ylog(r), ref)[-1] for r in runs_here)
            allpts = []
            for m in METHODS:
                hvs, n95, inf, share = [], [], [], {k: 0 for k in combos}
                for k in SEEDS:
                    r = R[(arch, scen, m, k)]
                    curve = S.hv_curve(ylog(r), ref)
                    hvs.append(curve[-1])
                    n95.append(next((i + 1 for i, h in enumerate(curve) if h >= 0.95 * best_hv), CENSORED))
                    inf.append(r["n_infeasible"])
                    allpts += [c for c in r["calls"] if c["feasible"]]
                    for c in r["calls"]:
                        share[combo(c)] += 1
                mean, half = S.t_ci95(hvs)
                med = sorted(n95)[len(n95) // 2]
                tot = sum(share.values())
                case["methods"][m] = {"hv_final": hvs, "hv_mean": mean, "hv_ci95_half": half,
                                      "calls_to_95pct_best": n95,
                                      "calls_to_95pct_best_median": (f">{S.BUDGET}" if med == CENSORED else med),
                                      "n_infeasible": inf, "max_infeasible_frac": max(inf) / S.BUDGET,
                                      "call_share_by_combo": {k: v / tot for k, v in share.items()}}
            ms = case["methods"]
            def beats(a, b):
                return ms[a]["hv_mean"] - ms[a]["hv_ci95_half"] > ms[b]["hv_mean"] + ms[b]["hv_ci95_half"]
            case["q1"] = {f"{a}>{b}": beats(a, b) for a in METHODS for b in METHODS if a != b}
            case["unreliable"] = any(v["max_infeasible_frac"] > 0.05 for v in ms.values())
            case["best_hv_any_run"] = best_hv
            # Q2: pooled front on (PCE, USD/W); exact ties keep the lowest design hash
            by_pt = {}
            for c in sorted(allpts, key=lambda c: (c["design_hash"], c["library_sha256"])):
                by_pt.setdefault((c["module_pce_pct"], c["usd_per_W"]), c)
            front = S.pareto(by_pt)
            # Q1b (registered co-primary, agy review): IGD+ of each run to the pooled front, in (PCE, log10 USD/W)
            # normalised by the pooled feasible range; plus the no-Au HV (reference = worst Cu/Ag corner).
            fl = [(p, math.log10(u)) for p, u in front]
            allp = [(c["module_pce_pct"], c["log10_usd_per_W"]) for c in by_pt.values()]
            lo = (min(-p for p, _ in allp), min(c for _, c in allp))
            span = (max(max(-p for p, _ in allp) - lo[0], 1e-12), max(max(c for _, c in allp) - lo[1], 1e-12))
            ref_noau = B.reference_point_no_au(arch)
            for m in METHODS:
                ig, hn = [], []
                for k in SEEDS:
                    r = R[(arch, scen, m, k)]
                    pts = [(c["module_pce_pct"], c["log10_usd_per_W"]) for c in r["calls"] if c["feasible"]]
                    ig.append(igd_plus(pts, fl, lo, span))
                    hn.append(S.hv2d([p for p, c in zip(pts, [c for c in r["calls"] if c["feasible"]])
                                      if c["metal"] != "Au"], ref_noau))
                im, ih = S.t_ci95(ig)
                nm, nh = S.t_ci95(hn)
                ms[m].update(igd_plus=ig, igd_plus_mean=im, igd_plus_ci95_half=ih,
                             hv_no_au=hn, hv_no_au_mean=nm, hv_no_au_ci95_half=nh)
            def beats_igd(a, b):
                return ms[a]["igd_plus_mean"] + ms[a]["igd_plus_ci95_half"] < ms[b]["igd_plus_mean"] - ms[b]["igd_plus_ci95_half"]
            case["q1_igd"] = {f"{a}>{b}": beats_igd(a, b) for a in METHODS for b in METHODS if a != b}
            case["ref_point_no_au"] = ref_noau
            p_opt, c_opt = by_pt[front[0]], by_pt[front[-1]]
            d_pce = p_opt["module_pce_pct"] - c_opt["module_pce_pct"]
            d_cost = p_opt["usd_per_W"] / c_opt["usd_per_W"] - 1
            def summ(c):
                lib = B.physics_library(arch, c["HTL"], c["metal"])
                d, _ = B.design(arch, c["x"], c["HTL"], scen)
                rows = {reg: B.usd_per_W(d, c["module_pce_pct"], lib, A.cost_line(reg))["usd_per_W"]
                        for reg in ("MY", "CN", "IN")}
                return {"combo": combo(c), "x": dict(zip(B.space(arch).names, c["x"])),
                        "module_pce_pct": c["module_pce_pct"], "cell_pce_pct": c["cell_pce_pct"],
                        "voc_V": c["voc_V"], "ff": c["ff"], "jsc_mA_cm2": c["jsc_mA_cm2"],
                        "usd_per_W": c["usd_per_W"], "usd_per_W_high_prices": c["usd_per_W_high_prices"],
                        "materials_usd_m2": c["materials_usd_m2"], "back_electrode_usd_m2": c["back_electrode_usd_m2"],
                        "usd_per_W_by_rate_region": rows, "design_hash": c["design_hash"]}
            per_combo = {}
            for k in combos:
                cs = [c for c in by_pt.values() if combo(c) == k]
                if cs:
                    bp = max(cs, key=lambda c: c["module_pce_pct"])
                    bc = min(cs, key=lambda c: c["usd_per_W"])
                    per_combo[k] = {"n_feasible": len(cs), "best_pce": bp["module_pce_pct"],
                                    "usd_per_W_at_best_pce": bp["usd_per_W"], "min_usd_per_W": bc["usd_per_W"],
                                    "pce_at_min_usd": bc["module_pce_pct"]}
            rho = spearmanr([c["module_pce_pct"] for c in by_pt.values()], [c["usd_per_W"] for c in by_pt.values()]).statistic
            gap_small = bool(d_pce < 1.0 and 100 * d_cost < 5.0)
            combos_front = sorted({combo(by_pt[pt]) for pt in front})
            case["q2"] = {"front_size": len(front),
                          "front": [[p, u, combo(by_pt[(p, u)])] for p, u in front],
                          "combos_on_front": combos_front,
                          "pce_optimal": summ(p_opt), "cost_optimal": summ(c_opt),
                          "gap_pce_points": d_pce, "gap_cost_pct": 100 * d_cost, "gap_small": gap_small,
                          "wording": wording(len(combos_front), gap_small, d_pce),
                          "n_feasible_pooled": len(by_pt), "spearman_pce_usd_pooled": rho,
                          "per_combo": per_combo}
            res["cases"][f"{arch}/{scen}"] = case
            case["q4"] = q4_break_even(arch, scen, by_pt, case["q2"]) if q4 else None
    for arch in ARCHS:
        cs = [res["cases"][f"{arch}/{s}"] for s in SCENS]
        same_q1 = all(c["q1"] == cs[0]["q1"] for c in cs)
        some_beats_random = any(all(c["q1"][f"{m}>random"] for c in cs) for m in ("nsga2", "mixbo"))
        same_igd = all(c["q1_igd"] == cs[0]["q1_igd"] for c in cs)
        some_beats_random_igd = any(all(c["q1_igd"][f"{m}>random"] for c in cs) for m in ("nsga2", "mixbo"))
        mats = {w: [c["q2"][w]["combo"] for c in cs] for w in ("pce_optimal", "cost_optimal")}
        res.setdefault("q3", {})[arch] = {
            "q1_same_in_all_scenarios": same_q1, "some_method_beats_random_in_all": some_beats_random,
            "q1_robust": bool(same_q1 and some_beats_random),
            "q1_igd_robust": bool(same_igd and some_beats_random_igd), "optimal_combos_by_scenario": mats,
            "materials_robust": bool(all(len(set(v)) == 1 for v in mats.values())),
            "gap_small_by_scenario": [c["q2"]["gap_small"] for c in cs],
            "wording_by_scenario": [c["q2"]["wording"] for c in cs]}
    (out_path or OUT / "result.json").write_text(json.dumps(res, indent=1))
    for k, c in res["cases"].items():
        print(k, {m: (round(v["hv_mean"], 4), round(v["hv_ci95_half"], 4), "igd+", round(v["igd_plus_mean"], 4))
                  for m, v in c["methods"].items()},
              "front", [(round(p, 2), round(u, 3), cb) for p, u, cb in c["q2"]["front"]], c["q2"]["wording"],
              "gap", round(c["q2"]["gap_pce_points"], 3), "pt", round(c["q2"]["gap_cost_pct"], 1), "%",
              "unreliable" if c["unreliable"] else "", flush=True)
    print("q3", res["q3"])
    return res


def swf():
    """Sensitivity S-WF (prereg §7): n-i-p, every scenario; for each combination the pooled best-PCE design is
    re-simulated with the metal's bare work function as the anode (metal_wf) instead of B2."""
    from perodesign.optim import objective_b as B
    from perodesign.optim import search as SA
    res0 = json.loads((OUT / "result.json").read_text())
    R = load_runs()
    out = {"schema": "perodesign.paperB_swf/1", "cases": {}}
    for scen in SCENS:
        pts = [c for m in METHODS for k in SEEDS for c in R[("n-i-p", scen, m, k)]["calls"] if c["feasible"]]
        rows = {}
        for h in B.HTLS:
            for mt in B.METALS:
                cs = [c for c in pts if c["HTL"] == h and c["metal"] == mt]
                if not cs:
                    continue
                best = sorted(cs, key=lambda c: (-c["module_pce_pct"], c["design_hash"]))[0]
                sp = B.space("n-i-p")
                lo, hi = B.bounds("n-i-p", h)
                u = [(v - a) / (b - a) for v, a, b in zip(best["x"], lo, hi)]
                r = B.evaluate("n-i-p", u, best["cats"], scen, cache_dir=CACHE, contact_rule="metal_wf", work_root=WORK)
                rows[f"{h}/{mt}"] = {"x": best["x"], "B2": [best["module_pce_pct"], best["usd_per_W"]],
                                     "metal_wf": [r["module_pce_pct"], r["usd_per_W"]], "metal_wf_status": r["sim_status"],
                                     "metal_wf_voc_V": r["voc_V"], "B2_voc_V": best["voc_V"]}
        feas = {k: v["metal_wf"] for k, v in rows.items() if v["metal_wf"][0] is not None}
        front = SA.pareto(list(feas.values()))
        out["cases"][scen] = {"rows": rows, "front_metal_wf": [[p, u, next(k for k, v in feas.items() if tuple(v) == (p, u))]
                                                               for p, u in front],
                              "combos_on_B2_front": res0["cases"][f"n-i-p/{scen}"]["q2"]["combos_on_front"]}
        print(scen, {k: (v["B2"], v["metal_wf"]) for k, v in rows.items()}, "front", out["cases"][scen]["front_metal_wf"])
    (OUT / "swf.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 12)
    elif cmd == "analyse":
        analyse()
    elif cmd == "swf":
        swf()
    else:
        raise SystemExit(f"unknown command {cmd}")
