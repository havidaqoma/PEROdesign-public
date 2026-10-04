"""P2 sensitivity analysis (docs/P2_sensitivity_preregistration.md, committed 4041f5a before any run).
  run:     python scripts/p2_sensitivity.py run [workers]    -> phase0/sensitivity/sims.jsonl (resumable, one line/sim)
  analyse: python scripts/p2_sensitivity.py analyse          -> phase0/sensitivity/result.json
Run in WSL (SimSS + SALib): ~/venvs/perodesign-dev/bin/python scripts/p2_sensitivity.py run 12"""
import copy
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# One BLAS thread per process: the delta analysis runs 12 worker processes, and the default OpenBLAS pool
# (one thread per core in each worker) oversubscribed 14 cores about 18x (load ~150). Speed only; the numbers
# are unchanged. Must be set before numpy is imported.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "phase0" / "sensitivity"
N, SEED = 512, 3407
DESIGN = {"schema": "perodesign.design/1", "architecture": "p-i-n", "layers": [
    {"role": "HTL", "material": "NiOx", "thickness_nm": 15}, {"role": "absorber", "material": "MAPbI3", "thickness_nm": 600},
    {"role": "ETL", "material": "C60", "thickness_nm": 30}, {"role": "buffer", "material": "SnO2", "thickness_nm": 10}]}
# name, kind ('log' ranges are given as log10 bounds), lo, hi, target
PHYS = [("P1 MAPbI3 N_t_bulk", "log", 19, 21, ("m", "MAPbI3", "N_t_bulk_m3")),
        ("P2 MAPbI3 mu_n", "log", -5, -3, ("m", "MAPbI3", "mu_n_m2_Vs")),
        ("P3 MAPbI3 mu_p", "log", -5, -3, ("m", "MAPbI3", "mu_p_m2_Vs")),
        ("P4 MAPbI3 E_c", "lin", 3.8, 4.0, ("m", "MAPbI3", "E_c_eV")),
        ("P5 MAPbI3 E_v", "lin", 5.43, 5.63, ("m", "MAPbI3", "E_v_eV")),
        ("P6 MAPbI3 k_direct", "log", -18, -16, ("m", "MAPbI3", "k_direct_m3_s")),
        ("P7 MAPbI3 N_ion", "log", math.log10(5e20), math.log10(5e22), ("ion",)),
        ("P8 NiOx|MAPbI3 N_t_int", "log", 11, 13, ("i", "NiOx|MAPbI3", "N_t_int_m2")),
        ("P9 MAPbI3|C60 N_t_int", "log", math.log10(4e11), math.log10(4e13), ("i", "MAPbI3|C60", "N_t_int_m2")),
        ("P10 NiOx N_A", "log", 21, 23, ("m", "NiOx", "N_A_m3")),
        ("P11 NiOx mu_p", "log", math.log10(4.7e-5), math.log10(4.7e-3), ("m", "NiOx", "mu_p_m2_Vs")),
        ("P12 NiOx E_v", "lin", 5.60, 5.80, ("m", "NiOx", "E_v_eV")),
        ("P13 C60 mu_n", "log", -7, -5, ("m", "C60", "mu_n_m2_Vs")),
        ("P14 C60 E_c", "lin", 3.9, 4.1, ("m", "C60", "E_c_eV")),
        ("P15 SnO2 N_D", "log", 21, 23, ("m", "SnO2", "N_D_m3"))]
COST = [("C1 capital rate", "lin", 0.0482472886111111, 0.102), ("C2 line capex", "log", math.log10(1e7), math.log10(4e7)),
        ("C3 yield", "lin", 0.40, 0.90), ("C4 depreciation years", "lin", 5, 10),
        ("C5 FTO-glass price factor", "log", math.log10(0.5), math.log10(2.0)), ("C6 other opex factor", "lin", 1.0, 3.0),
        ("C7 dead width mm", "lin", 0.1, 0.4), ("C8 TCO sheet res", "log", math.log10(5), math.log10(20))]
ALL = PHYS + COST
NAMES = [p[0] for p in ALL]
PROBLEM = {"num_vars": len(ALL), "names": NAMES, "bounds": [[p[2], p[3]] for p in ALL]}
NP_ = len(PHYS)


def value(p, u):
    return 10 ** u if p[1] == "log" else u


def sample():
    from SALib.sample import sobol
    return sobol.sample(PROBLEM, N, calc_second_order=False, scramble=True, seed=SEED)


def phys_key(row):
    return tuple(round(float(x), 12) for x in row[:NP_])


_SIM = None


def _sim_one(key):
    global _SIM
    from perodesign.library import load_library
    from perodesign.physics.simss import SimSS
    base = load_library()
    if _SIM is None:
        _SIM = SimSS(library=base)
    lib = copy.deepcopy(base)
    setv = {}
    for p, u in zip(PHYS, key):
        v, t = value(p, u), p[4]
        if t[0] == "m":
            lib["materials"][t[1]]["params"][t[2]] = v
        elif t[0] == "i":
            lib["interfaces"][t[1]]["params"][t[2]] = v
        else:                                   # N_anion and N_cation scaled together (ratio 5:3 kept)
            lib["materials"]["MAPbI3"]["params"]["N_anion_m3"] = v
            lib["materials"]["MAPbI3"]["params"]["N_cation_m3"] = v * 3 / 5
        setv[p[0]] = v
    _SIM.library = lib
    r = _SIM.run(DESIGN)
    return {"key": list(key), "status": r.status, "reason": r.reason, "metrics": r.metrics, "seconds": r.seconds}


def run(workers):
    OUT.mkdir(parents=True, exist_ok=True)
    X = sample()
    keys = list(dict.fromkeys(phys_key(r) for r in X))
    f = OUT / "sims.jsonl"
    done = set()
    if f.exists():
        for ln in f.read_text().splitlines():
            if ln.strip():
                done.add(tuple(json.loads(ln)["key"]))
    todo = [k for k in keys if k not in done]
    print(f"rows {len(X)} unique sims {len(keys)} done {len(done)} todo {len(todo)}", flush=True)
    counts = {}
    with ProcessPoolExecutor(max_workers=workers) as ex, f.open("a") as fh:
        for i, res in enumerate(ex.map(_sim_one, todo, chunksize=4), 1):
            fh.write(json.dumps(res) + "\n")
            counts[res["status"]] = counts.get(res["status"], 0) + 1
            if i % 250 == 0:
                fh.flush()
                print(i, counts, flush=True)          # status only
    print("DONE", counts, flush=True)


RESAMPLES = 1000
_DX = _DY = None


def _delta_init(X, Ys):
    global _DX, _DY
    _DX, _DY = X, Ys


def _delta_job(job):
    """One (output, parameter) delta estimate. SALib 1.6 returns delta_raw / delta_balanced / delta_step (no plain
    'delta' key). delta_raw = the given-data Borgonovo/Plischke estimator with a plain with-replacement bootstrap
    (the registered index); delta_balanced is kept only as a robustness check. Seeded per job, so the result does not
    depend on worker scheduling."""
    from SALib.analyze import delta
    k, out, j = job
    prob = {"num_vars": 1, "names": [NAMES[j]], "bounds": [PROBLEM["bounds"][j]]}
    S = delta.analyze(prob, _DX[:, [j]], _DY[out], num_resamples=RESAMPLES, seed=SEED + 1000 * k + j, method="all")
    return out, j, {"delta": float(S["delta_raw"][0]), "delta_conf": float(S["delta_raw_conf"][0]),
                    "delta_balanced": float(S["delta_balanced"][0]),
                    "delta_balanced_conf": float(S["delta_balanced_conf"][0]),
                    "S1": float(S["S1"][0]), "note": (S["notes"][0] if S.get("notes") else "")}


def outputs():
    """Rebuild Y1 (cell PCE), Y2 (USD/W) and module PCE for every sample row from sims.jsonl. Cheap; no index."""
    from perodesign.module import ModuleError, ModuleGeometry, module_from_cell
    from perodesign.tea import cost_per_watt, materials_per_m2, region_line_MY_bottom_up
    X = sample()
    sims = {}
    for ln in (OUT / "sims.jsonl").read_text().splitlines():
        if ln.strip():
            r = json.loads(ln)
            sims[tuple(r["key"])] = r
    mat = materials_per_m2(DESIGN)
    fto = [i["usd_m2"] for i in mat["items"] if i["item"] == "bom:FTO_glass"][0]
    base_line = region_line_MY_bottom_up()
    Y1, Y2, YM, ok = [], [], [], []
    for row in X:
        s = sims[phys_key(row)]
        c = {p[0]: value(p, u) for p, u in zip(COST, row[NP_:])}
        good = s["status"] == "complete"
        y1 = y2 = ym = float("nan")
        if good:
            try:
                mod = module_from_cell(s["metrics"], ModuleGeometry(6.0, c["C7 dead width mm"], c["C8 TCO sheet res"], 0.03))
            except ModuleError:
                good = False
        if good:
            ln_ = copy.deepcopy(base_line)
            ln_.rate.value, ln_.capex_usd.value = c["C1 capital rate"], c["C2 line capex"]
            ln_.yield_fraction.value, ln_.depreciation_years.value = c["C3 yield"], c["C4 depreciation years"]
            ln_.other_opex_usd_per_m2.value = base_line.other_opex_usd_per_m2.value * c["C6 other opex factor"]
            m_tot = mat["total_usd_m2"] + fto * (c["C5 FTO-glass price factor"] - 1)
            y1, ym = s["metrics"]["pce_pct"], mod["module_pce_pct"]
            y2 = cost_per_watt(m_tot, ym, ln_)["usd_per_W"]
        Y1.append(y1), Y2.append(y2), YM.append(ym), ok.append(good)
    Y1, Y2, YM, ok = map(np.array, (Y1, Y2, YM, ok))
    stat = {}
    for s in sims.values():
        stat[s["status"]] = stat.get(s["status"], 0) + 1
    return X, Y1, Y2, YM, ok, stat, sims, mat, fto


def analyse(workers=12):
    from SALib.analyze import sobol
    X, Y1, Y2, YM, ok, stat, sims, mat, fto = outputs()
    res = {"README": "P2 sensitivity (docs/P2_sensitivity_preregistration.md). Ranges are an ASSUMED convention (x/÷10 "
                     "densities/rates/mobilities, ±0.1 eV energies) except C1 (sourced ends). Maintenance (1% of capex) "
                     "is inside other opex and does not follow C2.",
           "n_rows": int(len(X)), "n_unique_sims": len(sims), "sim_status": stat,
           "rows_usable": int(ok.sum()), "failure_fraction_rows": float(1 - ok.mean()),
           "base_materials_usd_m2": mat["total_usd_m2"], "fto_item_usd_m2": fto}
    method = "sobol_ST" if ok.all() else "borgonovo_delta"
    res["method"] = method
    out = {}
    D = {}
    if method == "borgonovo_delta":
        import importlib.metadata
        res["delta_estimator"] = {"salib": importlib.metadata.version("SALib"), "index": "delta_raw",
                                  "robustness_check": "delta_balanced", "num_resamples": RESAMPLES,
                                  "note": "docs/P2_sensitivity_preregistration.md §5 (amendment before any index)"}
        Ys = {"cell_pce_pct": Y1[ok], "usd_per_W": Y2[ok]}
        jobs = [(k, o, j) for k, o in enumerate(Ys) for j in range(len(ALL))]
        with ProcessPoolExecutor(max_workers=workers, initializer=_delta_init, initargs=(X[ok], Ys)) as ex:
            for o, j, d in ex.map(_delta_job, jobs):
                D[(o, j)] = d
                print("delta", o, NAMES[j], round(d["delta"], 4), flush=True)
    for name, Y in (("cell_pce_pct", Y1), ("usd_per_W", Y2)):
        yv = Y[ok]
        o = {"p5_p50_p95": [float(np.percentile(yv, q)) for q in (5, 50, 95)], "n": int(len(yv))}
        if method == "sobol_ST":
            S = sobol.analyze(PROBLEM, Y, calc_second_order=False, num_resamples=1000, seed=SEED)
            idx = [(n_, float(S["ST"][i]), float(S["ST_conf"][i]), float(S["S1"][i])) for i, n_ in enumerate(NAMES)]
        else:
            idx = [(n_, D[(name, i)]["delta"], D[(name, i)]["delta_conf"], D[(name, i)]["S1"]) for i, n_ in enumerate(NAMES)]
            bal = sorted(((D[(name, i)]["delta_balanced"], n_) for i, n_ in enumerate(NAMES)), reverse=True)
            o["robustness_top5_delta_balanced"] = [n_ for _, n_ in bal[:5]]
            o["notes"] = {NAMES[i]: D[(name, i)]["note"] for i in range(len(NAMES)) if D[(name, i)]["note"]}
        idx.sort(key=lambda t: -t[1])
        o["ranking"] = [{"param": n_, "index": v, "ci95_half": cf, "S1": s1} for n_, v, cf, s1 in idx]
        r5, r6 = idx[4], idx[5]
        o["top5"] = [t[0] for t in idx[:5]]
        o["top5_resolved"] = bool(r5[1] - r5[2] > r6[1] + r6[2])
        if not o["top5_resolved"]:
            o["tied_with_rank5"] = [t[0] for t in idx[3:] if t[1] + t[2] >= r5[1] - r5[2]]
        out[name] = o
    res["outputs"] = out
    if not ok.all():                              # failure drivers: failure rate in lower vs upper half of each range
        drv = []
        for j, p in enumerate(ALL):
            mid = (p[2] + p[3]) / 2
            lo, hi = X[:, j] < mid, X[:, j] >= mid
            drv.append({"param": p[0], "fail_lower_half": float(1 - ok[lo].mean()), "fail_upper_half": float(1 - ok[hi].mean())})
        drv.sort(key=lambda d: -abs(d["fail_upper_half"] - d["fail_lower_half"]))
        res["failure_drivers"] = drv
    res["module_pce_p5_p50_p95"] = [float(np.percentile(YM[ok], q)) for q in (5, 50, 95)]
    (OUT / "result.json").write_text(json.dumps(res, indent=1))
    for k, o in out.items():
        print(k, o["p5_p50_p95"], "top5", o["top5"], "resolved", o["top5_resolved"])
    print("method", method, "status", stat, "usable rows", int(ok.sum()), "/", len(X))


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(int(sys.argv[2]) if len(sys.argv) > 2 else 12)
    else:
        analyse(int(sys.argv[2]) if len(sys.argv) > 2 else 12)
