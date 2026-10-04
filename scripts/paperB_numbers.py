"""Paper B derived numbers for docs/PaperB_results.md (every value computed here from the result files).
  python scripts/paperB_numbers.py -> phase0/paperB/numbers.json + prints them"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
B = REPO / "phase0" / "paperB"
r = json.loads((B / "result.json").read_text())
s = json.loads((B / "swf.json").read_text())
a = json.loads((REPO / "phase0" / "paperA" / "result.json").read_text())
N = {}
for k, c in r["cases"].items():
    m = c["methods"]
    q = c["q2"]
    N[k] = {
        "hv_gain_mixbo_vs_random_pct": 100 * (m["mixbo"]["hv_mean"] / m["random"]["hv_mean"] - 1),
        "hv_gain_mixbo_vs_nsga2_pct": 100 * (m["mixbo"]["hv_mean"] / m["nsga2"]["hv_mean"] - 1),
        "calls95": {kk: v["calls_to_95pct_best_median"] for kk, v in m.items()},
        "igd": {kk: v["igd_plus_mean"] for kk, v in m.items()},
        "mixbo_share_NiOx_CuAg": m["mixbo"]["call_share_by_combo"]["NiOx/Cu"] + m["mixbo"]["call_share_by_combo"]["NiOx/Ag"],
        "random_share_NiOx_CuAg": m["random"]["call_share_by_combo"]["NiOx/Cu"] + m["random"]["call_share_by_combo"]["NiOx/Ag"],
        "gap_pce": q["gap_pce_points"], "gap_cost_pct": q["gap_cost_pct"], "wording": q["wording"],
        "rho": q["spearman_pce_usd_pooled"], "front_size": q["front_size"], "combos": q["combos_on_front"],
        "pce_opt": [q["pce_optimal"]["combo"], q["pce_optimal"]["module_pce_pct"], q["pce_optimal"]["usd_per_W"]],
        "cost_opt": [q["cost_optimal"]["combo"], q["cost_optimal"]["module_pce_pct"], q["cost_optimal"]["usd_per_W"]],
        "best_au": max(v["best_pce"] for kk, v in q["per_combo"].items() if kk.endswith("/Au")),
        "min_usd_au": min(v["min_usd_per_W"] for kk, v in q["per_combo"].items() if kk.endswith("/Au")),
        "ptaa_adv": [c["q4"]["by_metal"][mt]["ptaa_pce_advantage_points"] for mt in ("Cu", "Ag")],
        "n_infeasible": sum(sum(v["n_infeasible"]) for v in m.values()),
        "paperA_pce_opt": [a["cases"][k]["q2"]["pce_optimal"]["module_pce_pct"], a["cases"][k]["q2"]["pce_optimal"]["usd_per_W"]],
    }
G = {
    "hv_gain_vs_random_range": [min(v["hv_gain_mixbo_vs_random_pct"] for v in N.values()), max(v["hv_gain_mixbo_vs_random_pct"] for v in N.values())],
    "hv_gain_vs_nsga2_range": [min(v["hv_gain_mixbo_vs_nsga2_pct"] for v in N.values()), max(v["hv_gain_mixbo_vs_nsga2_pct"] for v in N.values())],
    "gap_pce_range": [min(v["gap_pce"] for v in N.values()), max(v["gap_pce"] for v in N.values())],
    "gap_cost_range": [min(v["gap_cost_pct"] for v in N.values()), max(v["gap_cost_pct"] for v in N.values())],
    "rho_range": [min(v["rho"] for v in N.values()), max(v["rho"] for v in N.values())],
    "ptaa_adv_range": [min(min(v["ptaa_adv"]) for v in N.values()), max(max(v["ptaa_adv"]) for v in N.values())],
    "mixbo_share_range": [min(v["mixbo_share_NiOx_CuAg"] for v in N.values()), max(v["mixbo_share_NiOx_CuAg"] for v in N.values())],
    "random_share_range": [min(v["random_share_NiOx_CuAg"] for v in N.values()), max(v["random_share_NiOx_CuAg"] for v in N.values())],
    "n_infeasible_total": sum(v["n_infeasible"] for v in N.values()),
    "swf_status": {sc: {k: v["metal_wf_status"] for k, v in c["rows"].items()} for sc, c in s["cases"].items()},
    "swf_complete": sum(v["metal_wf_status"] == "complete" for c in s["cases"].values() for v in c["rows"].values()),
    "swf_total": sum(len(c["rows"]) for c in s["cases"].values()),
}
out = {"cases": N, "global": G}
(B / "numbers.json").write_text(json.dumps(out, indent=1))
for k, v in N.items():
    print(k, {kk: (round(x, 3) if isinstance(x, float) else x) for kk, x in v.items() if kk not in ("igd",)})
print(json.dumps({k: v for k, v in G.items() if k != "swf_status"}, indent=0))
