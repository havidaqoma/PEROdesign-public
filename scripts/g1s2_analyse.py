"""G1 step 2 analysis (docs/G1_step2_preregistration.md §3-§4, amendments B1-B3). Reads phase0/g1s2/designs.json
(measured values) + sim_<case>.json and applies the registered rules EXACTLY. No parameter is fitted.
Main test (§3): per eligible series (>= 4 thickness points simulated OK) Spearman rho(sim PCE, measured PCE) = rho_sim,
plus rho for Jsc/Voc/FF and the thickness-only baseline rho_base = Spearman(thickness, measured PCE).
GO iff: >= 10 eligible series; median rho_sim >= 0.5; rho_sim > 0 in >= 60 %; permutation p < 0.05 (10,000 within-series
shuffles of measured PCE, one-sided on the mean rho_sim). Wording rule: if mean(rho_sim) - mean(rho_base) <= 0.10 the
verdict must say the simulator adds no ranking information beyond thickness itself.
Secondary (§4): per family Spearman rho over successfully simulated devices; count families with rho >= 0.5 vs 15.
Usage: python scripts/g1s2_analyse.py [main|S1] -> phase0/g1s2/result_<case>.json"""
import json
import random
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CASE = sys.argv[1] if len(sys.argv) > 1 else "main"


def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j + 1]] == v[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 2:
        return None
    ra, rb = rank(a), rank(b)
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return None if den == 0 else num / den


def main():
    D = json.loads((REPO / "phase0" / "g1s2" / "designs.json").read_text(encoding="utf-8"))
    rdir = REPO / "phase0" / "g1s2" / ("" if __import__("os").environ.get("G1S2_ROUND", "1") == "1" else "round2")
    S = json.loads((rdir / f"sim_{CASE}.json").read_text(encoding="utf-8"))
    res = {(r["kind"], r["i"], r["j"]): r for r in S["results"]}
    rows, ineligible = [], []
    for i, s in enumerate(D["series"]):
        pts = []
        for j, p in enumerate(s["points"]):
            r = res.get(("series", i, j))
            if r and r["status"] == "complete" and p["measured"]["pce"] is not None:
                pts.append((p["t_abs_nm"], p["measured"], r["metrics"]))
        n_fail = len(s["points"]) - len(pts)
        if len(pts) < 4:
            ineligible.append({"i": i, "doi": s["doi"], "stack": s["stack"], "n_points": len(s["points"]),
                               "n_ok": len(pts), "statuses": sorted({(res.get(("series", i, j)) or {}).get("status", "missing")
                                                                     for j in range(len(s["points"]))})})
            continue
        t = [x[0] for x in pts]
        mp = [x[1]["pce"] for x in pts]
        sp = [x[2]["pce_pct"] for x in pts]
        row = {"i": i, "doi": s["doi"], "stack": s["stack"], "architecture": s["architecture"], "n_ok": len(pts),
               "n_failed": n_fail, "t_range_nm": [min(t), max(t)], "rho_sim": spearman(sp, mp),
               "rho_base": spearman(t, mp), "points": [{"t": a, "measured": b, "sim": {k: c[k] for k in (
                   "pce_pct", "jsc_mA_cm2", "voc_V", "ff")}} for a, b, c in pts]}
        for k_m, k_s in (("jsc", "jsc_mA_cm2"), ("voc", "voc_V"), ("ff", "ff")):
            pairs = [(x[2][k_s], x[1][k_m]) for x in pts if x[1][k_m] is not None and x[2][k_s] is not None]
            row[f"rho_{k_m}"] = spearman([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 4 else None
        rows.append(row)
    valid = [r for r in rows if r["rho_sim"] is not None]
    rs = [r["rho_sim"] for r in valid]
    rb = [r["rho_base"] for r in valid if r["rho_base"] is not None]
    rng = random.Random(20260929)
    obs = statistics.fmean(rs) if rs else float("nan")
    ge = 0
    for _ in range(10000):
        m = []
        for r in valid:
            meas = [p["measured"]["pce"] for p in r["points"]]
            rng.shuffle(meas)
            v = spearman([p["sim"]["pce_pct"] for p in r["points"]], meas)
            m.append(0.0 if v is None else v)
        ge += statistics.fmean(m) >= obs
    p_perm = (ge + 1) / 10001
    crit = {"n_eligible_ge_10": len(valid) >= 10, "median_rho_ge_0.5": bool(rs) and statistics.median(rs) >= 0.5,
            "frac_positive_ge_0.6": bool(rs) and sum(x > 0 for x in rs) / len(rs) >= 0.6, "perm_p_lt_0.05": p_perm < 0.05}
    go = all(crit.values())
    adds_nothing = bool(rs and rb) and statistics.fmean(rs) - statistics.fmean(rb) <= 0.10
    fam_out = []
    for i, f in enumerate(D["families"]):
        pairs = []
        for j, dv in enumerate(f["devices"]):
            r = res.get(("family", i, j))
            if r and r["status"] == "complete" and dv["measured"]["pce"] is not None:
                pairs.append((r["metrics"]["pce_pct"], dv["measured"]["pce"]))
        fam_out.append({"family": f["family"], "n_devices": f["n_devices"], "n_ok": len(pairs),
                        "rho": spearman([a for a, _ in pairs], [b for _, b in pairs]) if len(pairs) >= 20 else None})
    n_fam_pass = sum(1 for f in fam_out if f["rho"] is not None and f["rho"] >= 0.5)
    summary = {"case": CASE, "solver_variant": S.get("solver_variant"), "status_counts": S["status_counts"],
               "n_series_selected": len(D["series"]), "n_eligible": len(valid), "n_ineligible": len(ineligible),
               "median_rho_sim": statistics.median(rs) if rs else None, "mean_rho_sim": obs if rs else None,
               "mean_rho_base": statistics.fmean(rb) if rb else None,
               "frac_rho_sim_positive": sum(x > 0 for x in rs) / len(rs) if rs else None, "perm_p": p_perm,
               "criteria": crit, "verdict": "GO" if go else "NO-GO",
               "adds_no_information_beyond_thickness": adds_nothing,
               "families_simulable": len(fam_out), "families_rho_ge_0.5": n_fam_pass, "plan_bar": 15,
               "plan_bar_reachable": len(fam_out) >= 15}
    outdir = Path(__import__("os").environ.get("G1S2_OUTDIR", rdir))
    (outdir / f"result_{CASE}.json").write_text(json.dumps(
        {"README": __doc__.split("Usage:")[0].strip(), "summary": summary, "series": rows, "ineligible": ineligible,
         "families": fam_out}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    for r in rows:
        print(f"{r['i']:3d} n {r['n_ok']} rho_sim {r['rho_sim']} rho_base {r['rho_base']} | {r['stack'][:70]}")
    for f in fam_out:
        print("FAMILY", f)


if __name__ == "__main__":
    main()
