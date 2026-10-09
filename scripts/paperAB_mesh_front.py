"""POST-HOC (not pre-registered): grid check of every point on the six material-choice pooled fronts.

`paperAB_mesh_check.py` re-simulated only the two ends of each front. Here every member of each pooled material-choice
front (phase0/paperB/result.json, cases[*].q2.front) is matched to its stored simulator call, re-simulated without the
result cache at NP = 250, 500 and 1000, and the front is rebuilt from those points at each NP. Reported per case and NP:
the rebuilt front, the material sets at its two ends, the efficiency and cost gap between the ends, and the
pre-registered reading (0.2-point line). NP = 250 must reproduce every stored efficiency exactly, or the script fails.

This is a sensitivity check of the fronts the runs found, not a re-optimisation at the fine grid: designs that were
not on a front at NP = 250 are not re-simulated.

Output: phase0/paperB/posthoc_mesh_front.json.  Needs SIMsalabim (see docs/REPRODUCE.md).
Usage: python scripts/paperAB_mesh_front.py [workers]
"""
from __future__ import annotations

import glob
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from paperAB_mesh_check import NPS, PCE_LINE, run_one  # noqa: E402

OUT = ROOT / "phase0/paperB/posthoc_mesh_front.json"


def front_points() -> list[dict]:
    """Every pooled-front member of the six material-choice cases, matched exactly to a stored call."""
    from perodesign.optim import objective_b as B
    cases = json.loads((ROOT / "phase0/paperB/result.json").read_text(encoding="utf-8"))["cases"]
    pts = []
    for case, c in cases.items():
        arch, scen = case.split("/")
        calls = []
        for f in glob.glob(str(ROOT / f"phase0/paperB/runs/{arch}__{scen}__*.json")):
            calls += [k for k in json.loads(Path(f).read_text(encoding="utf-8"))["calls"] if k.get("feasible")]
        names = B.space(arch).names
        for i, (pce, usd, combo) in enumerate(c["q2"]["front"]):
            htl, metal = combo.split("/")
            hit = [k for k in calls if k["HTL"] == htl and k["metal"] == metal
                   and k["module_pce_pct"] == pce and k["usd_per_W"] == usd]
            if not hit:
                raise SystemExit(f"FAIL: front point {case} #{i} ({pce}, {usd}, {combo}) has no stored call")
            x = [float(v) for v in hit[0]["x"]]
            if len(x) != len(names):
                raise SystemExit(f"FAIL: {case} #{i}: x has {len(x)} values, space has {len(names)}")
            pts.append({"case": case, "arch": arch, "scenario": scen, "idx": i, "combo": combo, "htl": htl,
                        "metal": metal, "x": x, "x_named": dict(zip(names, x)), "stored_pce": pce, "stored_usd": usd})
    return pts


def pareto(points: list[dict]) -> list[dict]:
    """Non-dominated set: maximise module PCE, minimise USD/W."""
    return [p for p in points if not any(
        (q["module_pce_pct"] >= p["module_pce_pct"] and q["usd_per_W"] <= p["usd_per_W"])
        and (q["module_pce_pct"] > p["module_pce_pct"] or q["usd_per_W"] < p["usd_per_W"]) for q in points)]


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    pts = front_points()
    jobs = [{"level": "material_choice", "case": p["case"], "end": str(p["idx"]), "NP": n, "combo": p["combo"],
             "arch": p["arch"], "scenario": p["scenario"], "x": p["x"], "htl": p["htl"], "metal": p["metal"],
             "stored_pce": p["stored_pce"], "stored_usd": p["stored_usd"]} for p in pts for n in NPS]
    jobs.sort(key=lambda j: -j["NP"])
    with ProcessPoolExecutor(workers) as ex:
        rows = list(ex.map(run_one, jobs))
    rows.sort(key=lambda r: (r["case"], int(r["end"]), r["NP"]))
    failed = [r for r in rows if r["module_pce_pct"] is None]
    if failed:
        raise SystemExit(f"FAIL: {len(failed)} simulations did not complete: {failed[:3]}")
    base = [r for r in rows if r["NP"] == 250]
    bad = [r for r in base if r["module_pce_pct"] != r["stored_module_pce_pct"] or r["usd_per_W"] != r["stored_usd_per_W"]]
    if bad:
        raise SystemExit(f"FAIL: NP 250 does not reproduce {len(bad)} stored points, e.g. {bad[0]}")
    fronts = []
    for case in sorted({r["case"] for r in rows}):
        for n in NPS:
            pool = [r for r in rows if r["case"] == case and r["NP"] == n]
            fr = sorted(pareto(pool), key=lambda r: -r["module_pce_pct"])
            hi, lo = fr[0], min(fr, key=lambda r: r["usd_per_W"])
            gp = hi["module_pce_pct"] - lo["module_pce_pct"]
            fronts.append({"case": case, "NP": n, "n_points_simulated": len(pool), "front_size": len(fr),
                           "combos_on_front": sorted({r["combo"] for r in fr}),
                           "pce_end_combo": hi["combo"], "cost_end_combo": lo["combo"],
                           "pce_end_pct": hi["module_pce_pct"], "cost_end_pct": lo["module_pce_pct"],
                           "gap_pce_points": gp, "gap_cost_pct": (hi["usd_per_W"] / lo["usd_per_W"] - 1) * 100,
                           "above_0p2_line": gp >= PCE_LINE})
    by = {(f["case"], f["NP"]): f for f in fronts}
    cases = sorted({f["case"] for f in fronts})
    summary = {
        "n_points": len(pts), "n_sims": len(rows), "np250_reproduces_stored_exactly": True,
        "points_per_case": {c: sum(p["case"] == c for p in pts) for c in cases},
        "max_abs_dpce_points_vs_np250": {n: max(abs(r["module_pce_pct"] - r["stored_module_pce_pct"])
                                                for r in rows if r["NP"] == n) for n in NPS[1:]},
        "ends_unchanged_all_np": all(by[(c, n)]["pce_end_combo"] == "NiOx/Ag" and by[(c, n)]["cost_end_combo"] == "NiOx/Cu"
                                     for c in cases for n in NPS),
        "combos_unchanged_all_np": all(by[(c, n)]["combos_on_front"] == by[(c, 250)]["combos_on_front"]
                                       for c in cases for n in NPS),
        "gap_range_by_np": {n: [min(by[(c, n)]["gap_pce_points"] for c in cases),
                                max(by[(c, n)]["gap_pce_points"] for c in cases)] for n in NPS},
        "cost_gap_range_by_np": {n: [min(by[(c, n)]["gap_cost_pct"] for c in cases),
                                     max(by[(c, n)]["gap_cost_pct"] for c in cases)] for n in NPS},
        "max_abs_gap_change_vs_np250": max(abs(by[(c, n)]["gap_pce_points"] - by[(c, 250)]["gap_pce_points"])
                                           for c in cases for n in NPS[1:]),
        "cases_above_line_by_np": {n: [c for c in cases if by[(c, n)]["above_0p2_line"]] for n in NPS},
    }
    out = {"schema": "perodesign.posthoc_mesh_front/v1", "label": "POST-HOC, not pre-registered",
           "scope": "every member of the six material-choice pooled fronts; sensitivity check, not a re-optimisation",
           "NP_values": list(NPS), "summary": summary, "fronts": fronts, "points": pts, "rows": rows}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
