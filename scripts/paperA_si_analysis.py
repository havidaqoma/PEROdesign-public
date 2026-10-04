"""Paper A Supplementary Information: verification checks and POST-HOC analyses on the finished run files.
  python scripts/paperA_si_analysis.py      -> phase0/paperA/si/si_result.json

Nothing here re-runs SimSS or changes a pre-registered result. Every analysis re-reads phase0/paperA/runs/*.json and
either (a) recomputes a stored quantity from its inputs (verification) or (b) re-scores the SAME simulated designs
under a changed module or cost assumption (post-hoc sensitivity). (b) is exact for module geometry and cost inputs,
because the simulated cell (PCE, J_mp, V_mp) does not depend on them; it is a re-scoring of the designs the optimisers
sampled, not a new optimisation, so a new search could only find a front at least as good.
"""
import glob
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from scipy.stats import spearmanr  # noqa: E402

from perodesign.optim import objective as O  # noqa: E402
from perodesign.optim import search as S  # noqa: E402
from perodesign.module import MAX_P_TCO  # noqa: E402
from perodesign.tea import (_dcf, load_cost_library, maintenance_usd_per_m2, materials_per_m2,  # noqa: E402
                            region_line_MY_bottom_up)

A = REPO / "phase0" / "paperA"
OUT = A / "si"
ARCHS, SCENS, METHODS = ("p-i-n", "n-i-p"), ("base", "worse", "better"), ("random", "nsga2", "qnehvi")
SMALL_PCE, SMALL_COST = 1.0, 5.0            # pre-registered "small" line (docs/PaperA_preregistration.md §7)
T_REF_ABS = 600.0                           # Liu 2025 absorber thickness; the line's stated capacity refers to it


def load_runs():
    runs = {}
    for p in sorted((A / "runs").glob("*.json")):
        r = json.loads(p.read_text())
        runs[(r["arch"], r["scenario"], r["method"], r["seed"])] = r
    if len(runs) != 90:
        raise SystemExit(f"expected 90 runs, found {len(runs)}")
    return runs


# ------------------------------------------------------------------ cost decomposition (from the cost engine itself)
def cost_structure():
    """Per stack: materials M(x) = M_fixed + sum_i a_i t_i (USD/m2), and the design-independent per-m2 line cost
    F = C CRF/T + O. Slopes a_i come from the cost engine at the reference design and are checked for linearity."""
    lib = load_cost_library()
    line = O.cost_line()
    crf = float(_dcf().crf(line.rate.value, line.depreciation_years.value))
    cap_m2 = line.capex_usd.value * crf / line.throughput_m2_per_yr.value
    opex_m2 = line.other_opex_usd_per_m2.value
    out = {"line": {"name": line.name, "capex_usd": line.capex_usd.value, "throughput_m2_per_yr": line.throughput_m2_per_yr.value,
                    "depreciation_years": line.depreciation_years.value, "rate": line.rate.value,
                    "yield_fraction": line.yield_fraction.value, "crf": crf, "capital_usd_m2": cap_m2,
                    "other_opex_usd_m2": opex_m2, "opex_parts_usd_m2": getattr(line, "opex_parts_usd_m2", {}),
                    "opex_omitted": getattr(line, "opex_omitted", []),
                    "tags": {k: getattr(line, k).tag for k in ("capex_usd", "throughput_m2_per_yr", "depreciation_years",
                                                                "rate", "yield_fraction", "other_opex_usd_per_m2")}}}
    for a in ARCHS:
        d, _ = O.design(a, O.REFERENCE[a])
        m = materials_per_m2(d, lib, O.ASM)
        layer = {}
        fixed = {}
        for it, L in ((it, None) for it in m["items"]):
            fixed[it["item"]] = it["usd_m2"]
        for L in d["layers"]:
            key = f"layer:{L['role']}:{L['material']}"
            layer[L["material"]] = {"usd_m2_at_ref": fixed.pop(key), "t_ref_nm": L["thickness_nm"]}
            layer[L["material"]]["usd_m2_per_nm"] = layer[L["material"]]["usd_m2_at_ref"] / L["thickness_nm"]
        # linearity check: at the upper corner of the box, M must equal M_fixed + sum(a_i t_i)
        x2 = list(O.space(a).hi)
        d2, _ = O.design(a, x2)
        m2 = materials_per_m2(d2, lib, O.ASM)["total_usd_m2"]
        names = [mm for _, mm in O.STACKS[a]]
        pred = sum(fixed.values()) + sum(layer[n]["usd_m2_per_nm"] * t for n, t in zip(names, x2[:-1]))
        out[a] = {"layers": layer, "fixed_items_usd_m2": fixed, "fixed_total_usd_m2": sum(fixed.values()),
                  "materials_items_at_reference": m["items"], "linearity_check_rel_err": abs(m2 - pred) / m2}
    return out


def materials_lin(cs, a, x, mult=None):
    mult = mult or {}
    names = [m for _, m in O.STACKS[a]]
    v = sum(cs[a]["fixed_items_usd_m2"][k] * mult.get(k, mult.get("_fixed_items", 1.0)) for k in cs[a]["fixed_items_usd_m2"])
    return v + sum(cs[a]["layers"][n]["usd_m2_per_nm"] * t * mult.get(n, 1.0) for n, t in zip(names, x[:-1]))


# ------------------------------------------------------------------ verification
def verify(runs, cs):
    lab = {}
    sp = {a: O.space(a) for a in ARCHS}
    Y = cs["line"]["yield_fraction"]
    F = cs["line"]["capital_usd_m2"] + cs["line"]["other_opex_usd_m2"]
    err = Counter()
    worst = {"module_pce_abs": 0.0, "gff_abs": 0.0, "materials_rel": 0.0, "usd_rel": 0.0, "vmp_over_voc_max": 0.0}
    n_feas = n_calls = 0
    for (a, s, m, k), r in runs.items():
        if len(r["calls"]) != S.BUDGET:
            err["budget"] += 1
        if sum(1 for c in r["calls"] if not c["feasible"]) != r["n_infeasible"]:
            err["n_infeasible_mismatch"] += 1
        # stored final HV = recomputed exact 2-D HV
        ys = [{"y": [c["module_pce_pct"], c["usd_per_W"]] if c["feasible"] else None} for c in r["calls"]]
        if not math.isclose(S.hv_curve(ys, r["ref_point"])[-1], r["hv_final"], rel_tol=1e-12):
            err["hv_final"] += 1
        for c in r["calls"]:
            n_calls += 1
            # u -> x mapping and rounding (the design that was simulated is the one the optimiser asked for)
            xx = O.from_unit(sp[a], c["u"])
            xr = [round(v, 1) for v in xx[:-1]] + [round(xx[-1], 2)]
            if any(abs(p - q) > 1e-9 for p, q in zip(xr, c["x"])):
                err["u_to_x"] += 1
            if not c["feasible"]:
                continue
            n_feas += 1
            w = c["x"][-1]
            g = w / (w + O.DEAD_MM) * (1 - O.EDGE)
            mp = c["cell_pce_pct"] * g * (1 - c["p_tco"])
            worst["gff_abs"] = max(worst["gff_abs"], abs(g - c["gff"]))
            worst["module_pce_abs"] = max(worst["module_pce_abs"], abs(mp - c["module_pce_pct"]))
            # p_TCO = R J w^2/(3V) with P = J V -> V = sqrt(P R w^2 / (3 p)); must lie below Voc
            P = c["cell_pce_pct"] * 10.0                      # W/m2 at 1000 W/m2
            kk = 3 * c["p_tco"] / (O.TCO_OHM_SQ * (w * 1e-3) ** 2)
            vmp = math.sqrt(P / kk)
            worst["vmp_over_voc_max"] = max(worst["vmp_over_voc_max"], vmp / c["voc_V"])
            M = materials_lin(cs, a, c["x"])
            worst["materials_rel"] = max(worst["materials_rel"], abs(M - c["materials_usd_m2"]) / c["materials_usd_m2"])
            usd = (c["materials_usd_m2"] + F) / (c["module_pce_pct"] / 100 * 1000 * Y)
            worst["usd_rel"] = max(worst["usd_rel"], abs(usd - c["usd_per_W"]) / c["usd_per_W"])
            if c["cell_pce_pct"] > 33.7 * 1.05 or c["p_tco"] > MAX_P_TCO:
                err["gate"] += 1
    # shared initial design and seeded Sobol for random search
    shared = sobol = 0
    for a in ARCHS:
        for s in SCENS:
            for k in range(5):
                u0 = [runs[(a, s, m, k)]["calls"][i]["u"] for m in METHODS for i in range(S.N_INIT)]
                n = S.N_INIT
                if not (np.allclose(u0[:n], u0[n:2 * n], atol=1e-12) and np.allclose(u0[:n], u0[2 * n:], atol=1e-12)):
                    shared += 1
                ref_u = S.sobol_points(sp[a].dim, S.BUDGET, k)
                if not np.allclose(np.array([c["u"] for c in runs[(a, s, "random", k)]["calls"]]), ref_u, atol=1e-12):
                    sobol += 1
    # provenance hashes are identical across all runs (one simulator binary, one library)
    bins = sorted({r["sim_binary_sha256"] for r in runs.values()})
    libs = sorted({r["library_sha256"] for r in runs.values()})
    # duplicates (cache hits inside a run): same design hash asked again
    dup = {m: [] for m in METHODS}
    for (a, s, m, k), r in runs.items():
        seen, n = set(), 0
        for c in r["calls"]:
            n += c["design_hash"] in seen
            seen.add(c["design_hash"])
        dup[m].append(n)
    lab = {"n_runs": len(runs), "n_calls": n_calls, "n_feasible": n_feas, "errors": dict(err), "worst": worst,
           "materials_linearity_rel_err": {a: cs[a]["linearity_check_rel_err"] for a in ARCHS},
           "shared_init_mismatch_groups": shared, "random_sobol_mismatch_runs": sobol, "binary_sha256": bins,
           "library_sha256": libs,
           "duplicate_calls_per_run": {m: {"total": int(sum(v)), "max": int(max(v)), "runs_with_any": int(sum(x > 0 for x in v))}
                                       for m, v in dup.items()}}
    return lab


# ------------------------------------------------------------------ re-scoring under changed assumptions
def pooled(runs, a, s):
    return [c for (aa, ss, m, k), r in runs.items() if aa == a and ss == s for c in r["calls"] if c["feasible"]]


def rescore(calls, a, cs, R=O.TCO_OHM_SQ, dead=O.DEAD_MM, edge=O.EDGE, mult=None, fixed_line_mult=1.0,
            alpha=0.0, extra_usd_m2=0.0, Y=None):
    Y = Y or cs["line"]["yield_fraction"]
    F = (cs["line"]["capital_usd_m2"] + cs["line"]["other_opex_usd_m2"]) * fixed_line_mult
    i_abs = [m for _, m in O.STACKS[a]].index("MAPbI3")
    pts = []
    for c in calls:
        w = c["x"][-1]
        p = c["p_tco"] * R / O.TCO_OHM_SQ
        if p > MAX_P_TCO:
            continue
        mod = c["cell_pce_pct"] * w / (w + dead) * (1 - edge) * (1 - p)
        if not 0 < mod < 40:
            continue
        s_thr = max(0.05, 1 + alpha * (c["x"][i_abs] / T_REF_ABS - 1))
        M = materials_lin(cs, a, c["x"], mult)
        usd = (M + F * s_thr + extra_usd_m2) / (mod / 100 * 1000 * Y)
        pts.append((mod, usd, c))
    return pts


def gap(pts):
    front = S.pareto([(p, u) for p, u, _ in pts])
    P = max(front, key=lambda t: t[0])
    C = min(front, key=lambda t: t[1])
    look = {(p, u): c for p, u, c in pts}
    return {"front_size": len(front), "pce_opt": P, "cost_opt": C, "gap_pce": P[0] - C[0],
            "gap_cost_pct": 100 * (P[1] - C[1]) / C[1], "small": (P[0] - C[0]) < SMALL_PCE and 100 * (P[1] - C[1]) / C[1] < SMALL_COST,
            "x_pce_opt": look[P]["x"], "x_cost_opt": look[C]["x"], "n_designs": len(pts)}


def sensitivity(runs, cs):
    lib = load_cost_library()
    lineB = O.cost_line()
    rows = []
    maint = maintenance_usd_per_m2(lineB, lib).value
    fac = region_line_MY_bottom_up(include_facilities_proxy=True).other_opex_usd_per_m2.value - cs["line"]["other_opex_usd_m2"]
    group = {
        "module": [("R_sq 5 ohm/sq", dict(R=5.0)), ("R_sq 15 ohm/sq", dict(R=15.0)), ("R_sq 20 ohm/sq", dict(R=20.0)),
                   ("dead width 0.1 mm", dict(dead=0.1)), ("dead width 0.4 mm", dict(dead=0.4)),
                   ("edge fraction 0%", dict(edge=0.0)), ("edge fraction 6%", dict(edge=0.06))],
        "prices": [("absorber price x0.5", dict(mult={"MAPbI3": 0.5})), ("absorber price x2", dict(mult={"MAPbI3": 2.0})),
                   ("absorber price x10", dict(mult={"MAPbI3": 10.0})),
                   ("all layer prices x2", dict(mult={n: 2.0 for n in ("NiOx", "MAPbI3", "C60", "SnO2", "PTAA")})),
                   ("PTAA price x0.1", dict(mult={"PTAA": 0.1})), ("C60 price x0.1", dict(mult={"C60": 0.1})),
                   ("rear ITO removed (p-i-n)", dict(mult={"bom:ITO_rear_electrode": 0.0})),
                   ("front glass (FTO proxy) x1.5", dict(mult={"bom:FTO_glass": 1.5}))],
        "line": [("yield 0.9 (from 0.5)", dict(Y=0.9)), ("capital + other opex x0.5", dict(fixed_line_mult=0.5)),
                 ("capital + other opex x2", dict(fixed_line_mult=2.0)),
                 ("maintenance 3%/yr (from 1%)", dict(extra_usd_m2=2 * maint)),
                 ("maintenance 7%/yr (from 1%)", dict(extra_usd_m2=6 * maint)),
                 ("+ facilities/rent (Cai 2017 proxy)", dict(extra_usd_m2=fac))],
        "throughput": [(f"absorber-time alpha {al:g}", dict(alpha=al)) for al in (0.25, 0.5, 1.0)],
    }
    base = {(a, s): gap(rescore(pooled(runs, a, s), a, cs)) for a in ARCHS for s in SCENS}
    for g, items in group.items():
        for label, kw in [("baseline (as run)", {})] + items if g == "module" else items:
            for a in ARCHS:
                for s in SCENS:
                    r = gap(rescore(pooled(runs, a, s), a, cs, **kw))
                    rows.append({"group": g if label != "baseline (as run)" else "baseline", "change": label, "arch": a, "scenario": s,
                                 "front_size": r["front_size"], "pce_opt_module_pct": r["pce_opt"][0], "pce_opt_usd_W": r["pce_opt"][1],
                                 "cost_opt_module_pct": r["cost_opt"][0], "cost_opt_usd_W": r["cost_opt"][1],
                                 "gap_pce_pt": r["gap_pce"], "gap_cost_pct": r["gap_cost_pct"], "small": r["small"],
                                 "x_pce_opt": r["x_pce_opt"], "x_cost_opt": r["x_cost_opt"], "n_designs": r["n_designs"],
                                 "pce_opt_shift_pt": r["pce_opt"][0] - base[(a, s)]["pce_opt"][0]})
    # break-even scans: where does the pre-registered "small" line first fail?
    scans = {}
    for name, grid, mk in (("absorber_price_mult", [1, 2, 5, 10, 20, 50, 100, 200], lambda v: dict(mult={"MAPbI3": v})),
                           ("all_layer_price_mult", [1, 2, 5, 10, 20, 50, 100, 200],
                            lambda v: dict(mult={n: v for n in ("NiOx", "MAPbI3", "C60", "SnO2", "PTAA")})),
                           ("throughput_alpha", [0, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5], lambda v: dict(alpha=v)),
                           ("R_sq_ohm", [2, 5, 10, 15, 20, 30, 40], lambda v: dict(R=v))):
        scans[name] = []
        for v in grid:
            for a in ARCHS:
                for s in SCENS:
                    r = gap(rescore(pooled(runs, a, s), a, cs, **mk(v)))
                    scans[name].append({"value": v, "arch": a, "scenario": s, "gap_pce_pt": r["gap_pce"],
                                        "gap_cost_pct": r["gap_cost_pct"], "small": r["small"], "front_size": r["front_size"],
                                        "pce_opt_x": r["x_pce_opt"], "cost_opt_x": r["x_cost_opt"]})
    return {"rows": rows, "scans": scans, "maintenance_1pct_usd_m2": maint, "facilities_proxy_usd_m2": fac}


# ------------------------------------------------------------------ Q1 with a tighter reference point and other scores
def q1_alternatives(runs):
    out = {}
    for a in ARCHS:
        for s in SCENS:
            allc = pooled(runs, a, s)
            nadir = (min(c["module_pce_pct"] for c in allc), max(c["usd_per_W"] for c in allc))
            front = S.pareto([(c["module_pce_pct"], c["usd_per_W"]) for c in allc])
            # "tight": a reference point just beyond the pooled front's own range (10% of the pooled range)
            pr = max(c["module_pce_pct"] for c in allc) - nadir[0]
            ur = nadir[1] - min(c["usd_per_W"] for c in allc)
            tight = (min(p for p, _ in front) - 0.1 * pr, max(u for _, u in front) + 0.1 * ur)
            case = {"ref_nadir": nadir, "ref_tight": tight, "methods": {}}
            for m in METHODS:
                hvn, hvt, bp, bc = [], [], [], []
                for k in range(5):
                    cs_ = runs[(a, s, m, k)]["calls"]
                    pts = [(c["module_pce_pct"], c["usd_per_W"]) for c in cs_ if c["feasible"]]
                    hvn.append(S.hv2d(pts, nadir))
                    hvt.append(S.hv2d(pts, tight))
                    bp.append(max(p for p, _ in pts))
                    bc.append(min(u for _, u in pts))
                case["methods"][m] = {k: {"values": v, "mean": S.t_ci95(v)[0], "ci95_half": S.t_ci95(v)[1]}
                                      for k, v in (("hv_nadir", hvn), ("hv_tight", hvt), ("best_module_pce", bp),
                                                   ("lowest_usd_W", bc))}
            # verdicts: non-overlap of 95% t-CIs (higher is better except lowest_usd_W)
            ver = {}
            for metric, higher in (("hv_nadir", True), ("hv_tight", True), ("best_module_pce", True), ("lowest_usd_W", False)):
                v = []
                for x, y in (("nsga2", "random"), ("qnehvi", "random"), ("qnehvi", "nsga2")):
                    X, Yy = case["methods"][x][metric], case["methods"][y][metric]
                    lo_x, hi_x = X["mean"] - X["ci95_half"], X["mean"] + X["ci95_half"]
                    lo_y, hi_y = Yy["mean"] - Yy["ci95_half"], Yy["mean"] + Yy["ci95_half"]
                    if (higher and lo_x > hi_y) or (not higher and hi_x < lo_y):
                        v.append(f"{x[0].upper()}>{y[0].upper()}")
                ver[metric] = v
            # HV-vs-best-PCE rank correlation under each reference (15 runs)
            for metric in ("hv_nadir", "hv_tight"):
                hv = [v for m in METHODS for v in case["methods"][m][metric]["values"]]
                bp = [v for m in METHODS for v in case["methods"][m]["best_module_pce"]["values"]]
                case[f"rho_{metric}_vs_best_pce"] = float(spearmanr(hv, bp)[0])
            hv0 = [runs[(a, s, m, k)]["hv_final"] for m in METHODS for k in range(5)]
            bp0 = [v for m in METHODS for v in case["methods"][m]["best_module_pce"]["values"]]
            case["rho_hv_prereg_vs_best_pce"] = float(spearmanr(hv0, bp0)[0])
            case["verdicts"] = ver
            out[f"{a}/{s}"] = case
    return out


# ------------------------------------------------------------------ descriptive: best-so-far module PCE curve
def best_pce_curves(runs):
    out = {}
    for (a, s, m, k), r in runs.items():
        best, cur = [], -math.inf
        for c in r["calls"]:
            if c["feasible"]:
                cur = max(cur, c["module_pce_pct"])
            best.append(cur if math.isfinite(cur) else None)
        out[f"{a}__{s}__{m}__s{k}"] = best
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    runs = load_runs()
    cs = cost_structure()
    res = {"schema": "perodesign.paperA_si/1",
           "status": "POST-HOC (after the pre-registered analysis); verification checks are deterministic recomputations",
           "cost_structure": cs, "verification": verify(runs, cs), "sensitivity": sensitivity(runs, cs),
           "q1_alternatives": q1_alternatives(runs), "best_pce_curves": best_pce_curves(runs)}
    (OUT / "si_result.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    v = res["verification"]
    print(json.dumps({k: v[k] for k in ("n_calls", "n_feasible", "errors", "worst", "shared_init_mismatch_groups",
                                        "random_sobol_mismatch_runs", "duplicate_calls_per_run")}, indent=1))


if __name__ == "__main__":
    main()
