"""POST-HOC analyses from stored data, added for the pre-submission review (2026-10-09). NOT pre-registered; no new
simulations. Output: phase0/paperB/posthoc_review.json (SI Note S20).

R1 PTAA-only n-i-p front (review H5). The n-i-p material-choice fronts are all NiOx on top of the absorber, an order
   that exists only in the model. The stored runs also sampled PTAA n-i-p designs (the usual n-i-p order). Per scenario,
   all feasible PTAA n-i-p calls of all methods and seeds are pooled, de-duplicated as in the pre-registered analysis,
   and their Pareto front is taken. These designs were sampled, not optimised for PTAA, so the front is a lower bound.
R2 Paired optimiser differences (review F20). All methods of a seed share the same Sobol start, so the final
   hypervolumes can be compared seed by seed. Paired mean difference with a 95% t interval (4 degrees of freedom),
   next to the pre-registered rule (interval non-overlap).
R3 J-V values of the front ends (review F18): Voc, FF and Jsc of the PCE-optimal design of each case, both levels.
R4 Correlation pool (review F29): Spearman rank correlation of module PCE and USD/W over all feasible calls and over
   distinct designs, both levels.
Run in WSL: ~/venvs/perodesign-dev/bin/python scripts/paperAB_posthoc_review.py
"""
import json
import math
import sys
from pathlib import Path

from scipy.stats import spearmanr, t as tdist

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from perodesign.optim import search as SB  # noqa: E402

PA, PB = REPO / "phase0" / "paperA", REPO / "phase0" / "paperB"
ARCHS, SCENS = ("p-i-n", "n-i-p"), ("base", "worse", "better")
DPCE_MIN = 0.2
OUT = PB / "posthoc_review.json"


def load(d):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((d / "runs").glob("*.json"))}


def dedup(calls):
    """Same rule as the pre-registered analysis: one point per (PCE, USD/W), lowest design hash kept."""
    by_pt = {}
    for c in sorted(calls, key=lambda c: (c["design_hash"], c.get("library_sha256", ""))):
        by_pt.setdefault((c["module_pce_pct"], c["usd_per_W"]), c)
    return by_pt


def r1_ptaa_front(runs_b):
    out = {}
    for scen in SCENS:
        calls = [c for r in runs_b.values() if r["arch"] == "n-i-p" and r["scenario"] == scen
                 for c in r["calls"] if c["feasible"] and c["HTL"] == "PTAA"]
        by_pt = dedup(calls)
        front = SB.pareto(by_pt)
        p, c = by_pt[front[0]], by_pt[front[-1]]
        per_metal = {}
        for m in ("Cu", "Ag", "Au"):
            cs = [v for v in by_pt.values() if v["metal"] == m]
            if cs:
                b = max(cs, key=lambda v: v["module_pce_pct"])
                per_metal[m] = {"n_distinct": len(cs), "best_pce": b["module_pce_pct"], "usd_at_best": b["usd_per_W"],
                                "min_usd": min(v["usd_per_W"] for v in cs)}
        out[scen] = {"n_feasible_calls": len(calls), "n_distinct": len(by_pt), "front_size": len(front),
                     "metals_on_front": sorted({by_pt[k]["metal"] for k in front}),
                     "pce_end": {"metal": p["metal"], "module_pce_pct": p["module_pce_pct"], "usd_per_W": p["usd_per_W"]},
                     "cost_end": {"metal": c["metal"], "module_pce_pct": c["module_pce_pct"], "usd_per_W": c["usd_per_W"]},
                     "gap_pce_points": p["module_pce_pct"] - c["module_pce_pct"],
                     "gap_cost_pct": 100 * (p["usd_per_W"] / c["usd_per_W"] - 1),
                     "above_0p2_line": p["module_pce_pct"] - c["module_pce_pct"] >= DPCE_MIN,
                     "per_metal": per_metal}
    return out


def r2_paired(res, methods):
    tq = tdist.ppf(0.975, 4)
    rows = []
    for case, c in res["cases"].items():
        ms = c["methods"]
        for i, a in enumerate(methods):
            for b in methods[i + 1:]:
                d = [x - y for x, y in zip(ms[a]["hv_final"], ms[b]["hv_final"])]
                n = len(d)
                mean = sum(d) / n
                sd = math.sqrt(sum((x - mean) ** 2 for x in d) / (n - 1))
                half = float(tq * sd / math.sqrt(n))
                sep = bool(abs(mean) > half)
                nonoverlap = c["q1"][f"{a}>{b}"] or c["q1"][f"{b}>{a}"]
                rows.append({"case": case, "pair": f"{a}-{b}", "n_seeds": n, "mean_diff": mean, "ci95_half": half,
                             "paired_separates": sep, "nonoverlap_separates": nonoverlap,
                             "winner": (a if mean > 0 else b) if sep else None})
    return rows


def r3_jv(res_a, runs_a, res_b):
    calls = {c["design_hash"]: c for r in runs_a.values() for c in r["calls"] if c["feasible"]}
    out = []
    for level, res in (("thickness_only", res_a), ("material_choice", res_b)):
        for case, c in res["cases"].items():
            e = c["q2"]["pce_optimal"]
            src = e if "voc_V" in e else calls[e["design_hash"]]
            out.append({"level": level, "case": case, "combo": e.get("combo", "fixed"), "voc_V": src["voc_V"],
                        "ff": src["ff"], "jsc_mA_cm2": src["jsc_mA_cm2"], "cell_pce_pct": e["cell_pce_pct"],
                        "module_pce_pct": e["module_pce_pct"]})
    return out


def r4_rho(runs, level):
    out = {}
    for arch in ARCHS:
        for scen in SCENS:
            calls = [c for r in runs.values() if r["arch"] == arch and r["scenario"] == scen
                     for c in r["calls"] if c["feasible"]]
            d = list(dedup(calls).values())
            rho = lambda cs: spearmanr([c["module_pce_pct"] for c in cs], [c["usd_per_W"] for c in cs]).statistic  # noqa: E731
            out[f"{arch}/{scen}"] = {"all_feasible_calls": float(rho(calls)), "n_calls": len(calls),
                                     "distinct_designs": float(rho(d)), "n_distinct": len(d)}
    return out


def main():
    runs_a, runs_b = load(PA), load(PB)
    res_a = json.loads((PA / "result.json").read_text(encoding="utf-8"))
    res_b = json.loads((PB / "result.json").read_text(encoding="utf-8"))
    out = {"schema": "perodesign.posthoc_review/v1", "label": "POST-HOC, not pre-registered; stored data only",
           "r1_ptaa_nip_front": r1_ptaa_front(runs_b),
           "r2_paired": {"thickness_only": r2_paired(res_a, ("qnehvi", "nsga2", "random")),
                         "material_choice": r2_paired(res_b, ("mixbo", "nsga2", "random"))},
           "r3_jv_pce_optimal": r3_jv(res_a, runs_a, res_b),
           "r4_rho": {"thickness_only": r4_rho(runs_a, "a"), "material_choice": r4_rho(runs_b, "b")}}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for s, v in out["r1_ptaa_nip_front"].items():
        print("R1", s, v["n_distinct"], v["metals_on_front"], v["pce_end"]["metal"], "->", v["cost_end"]["metal"],
              round(v["gap_pce_points"], 3), round(v["gap_cost_pct"], 1), {m: round(x["best_pce"], 3) for m, x in v["per_metal"].items()})
    for lvl, rows in out["r2_paired"].items():
        for r in rows:
            if r["paired_separates"] != r["nonoverlap_separates"]:
                print("R2 differs", lvl, r["case"], r["pair"], round(r["mean_diff"], 4), round(r["ci95_half"], 4), r["winner"])
        print("R2", lvl, "paired separates", sum(r["paired_separates"] for r in rows), "nonoverlap", sum(r["nonoverlap_separates"] for r in rows), "of", len(rows))
    for r in out["r3_jv_pce_optimal"]:
        print("R3", r["level"], r["case"], r["combo"], r["voc_V"], r["ff"], round(r["jsc_mA_cm2"], 2))
    for lvl, d in out["r4_rho"].items():
        for k, v in d.items():
            print("R4", lvl, k, round(v["all_feasible_calls"], 3), v["n_calls"], round(v["distinct_designs"], 3), v["n_distinct"])


if __name__ == "__main__":
    main()
