"""Post-hoc analyses for Study 2, added after the runs in response to an external review (paperreview.ai, 2026-10-01).
NOT pre-registered; reported as post-hoc in SI Note S16. Output: phase0/paperB/posthoc.json

P1 contact attribution across the optimised designs (review Q2). For every case and metal (Cu, Ag): the pooled best
   NiOx design is re-simulated with its hole-side electrode at PTAA's valence band (the contact PTAA gets under rule B2).
   NiOx's lead over the best PTAA design is then split into a contact part and a remainder.
P2 metal price ranges (review Q7). The World Bank Pink Sheet row already saved for the cost library holds 11 silver and
   gold prices (2023-2026). Each cell is verified with the provenance gate (same rules as the library), and every stored
   feasible design is re-costed at the lowest and highest price (no new simulations: cost per watt is linear in the
   back-electrode cost). Then the pooled front, gap and pre-registered wording are recomputed. A silver cost-factor scan
   (price x utilisation) finds the factor at which the copper/silver cost gap falls below the 'small' line.
Run in WSL: ~/venvs/perodesign-dev/bin/python scripts/paperB_posthoc.py
"""
import copy
import hashlib
import json
import math
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from perodesign.optim import objective as A  # noqa: E402
from perodesign.optim import objective_b as B  # noqa: E402
from perodesign.optim import search as SA  # noqa: E402

PB = REPO / "phase0" / "paperB"
ARCHS, SCENS = ("p-i-n", "n-i-p"), ("base", "worse", "better")
DPCE_MIN = 0.2


def p1_job(job):
    from perodesign.module import module_from_cell
    from perodesign.physics.simss import SimSS
    arch, scen, metal, x = job
    lib = copy.deepcopy(B.physics_library(arch, "NiOx", metal))
    ev_ptaa = float(lib["materials"]["PTAA"]["params"]["E_v_eV"])
    key = "W_R_eV" if arch == "n-i-p" else "W_L_eV"       # hole-side electrode
    lib["architecture_setup"][arch][key] = ev_ptaa
    lib["_sha256"] = hashlib.sha256((lib["_sha256"] + f"|posthocP1|{key}={ev_ptaa}").encode()).hexdigest()
    d, geom = B.design(arch, x, "NiOx", scen)
    r = SimSS(library=lib).run(d)
    out = {"arch": arch, "scenario": scen, "metal": metal, "x": x, "status": r.status, "contact_key": key,
           "contact_eV": ev_ptaa, "module_pce_pct": None}
    if r.status == "complete":
        try:
            out["module_pce_pct"] = module_from_cell(r.metrics, geom)["module_pce_pct"]
        except Exception as e:  # noqa: BLE001
            out["status"] = f"module: {e}"
    return out


def pink_cells(cl):
    """Verify every monthly/annual cell of the silver and gold rows with the library's provenance gate."""
    from perodesign.tea.provenance import check_entry
    out = {}
    for eid in ("wb_silver_2026_aug", "wb_gold_2026_aug"):
        base = next(e for e in cl["entries"] if e["id"] == eid)
        cells = [c.strip() for c in base["quote_span"].split("|")]
        vals = []
        for i in range(3, len(cells)):
            e = copy.deepcopy(base)
            vt = cells[i].replace(",", "")
            e.update(id=f"{eid}_cell{i}", value=float(vt), value_text=vt)
            e["position"] = dict(e["position"], index=i)
            g = check_entry(e, cl["sources"], REPO / "data" / "sources")
            if not g.ok:
                raise SystemExit(f"provenance gate refused {eid} cell {i}: {g}")
            vals.append(float(vt))
        out[base["item"]] = {"values": vals, "base": base["value"], "min": min(vals), "max": max(vals),
                             "header": "2023, 2024, 2025 annual; Q2-Q4 2025; Q1-Q2 2026; Jun, Jul, Aug 2026"}
    return out


def front_stats(pts):
    """pts: list of (pce, usd, combo). Pooled front, gap, wording (same rules as scripts/paperB_run.analyse)."""
    by = {}
    for p, u, cb in pts:
        by.setdefault((p, u), cb)
    fr = SA.pareto(by)
    dp = fr[0][0] - fr[-1][0]
    dc = 100 * (fr[0][1] / fr[-1][1] - 1)
    small = bool(dp < 1.0 and dc < 5.0)
    combos = sorted({by[k] for k in fr})
    if len(combos) == 1:
        word = "one_material_set_dominates"
    elif small:
        word = "near_identical_materials"
    elif dp < DPCE_MIN:
        word = "cost_differs_efficiency_practically_equal"
    else:
        word = "material_trade_off_exists"
    return {"combos": combos, "gap_pce": dp, "gap_cost_pct": dc, "small": small, "wording": word, "front_size": len(fr)}


def main():
    from perodesign.tea import INCIDENT_W_M2 as INCIDENT, cost_per_watt, load_cost_library
    res = json.loads((PB / "result.json").read_text())
    out = {"schema": "perodesign.paperB_posthoc/1", "label": "POST-HOC (external review 2026-10-01), not pre-registered"}
    # ---------------- P1
    jobs = []
    for a in ARCHS:
        for s in SCENS:
            for mt in ("Cu", "Ag"):
                jobs.append((a, s, mt, res["cases"][f"{a}/{s}"]["q4"]["by_metal"][mt]["NiOx_best"]["x"]))
    with ProcessPoolExecutor(max_workers=12) as ex:
        sims = list(ex.map(p1_job, jobs))
    rows = []
    for sm in sims:
        q = res["cases"][f"{sm['arch']}/{sm['scenario']}"]["q4"]["by_metal"][sm["metal"]]
        n_b2, p_b2 = q["NiOx_best"]["module_pce_pct"], q["PTAA_best"]["module_pce_pct"]
        row = {**sm, "niox_b2": n_b2, "ptaa_best_b2": p_b2, "lead_b2": n_b2 - p_b2}
        if sm["module_pce_pct"] is not None:
            row["lead_same_contact"] = sm["module_pce_pct"] - p_b2
            row["contact_part"] = n_b2 - sm["module_pce_pct"]
            row["contact_share"] = row["contact_part"] / row["lead_b2"] if row["lead_b2"] > 0 else None
        rows.append(row)
    out["p1"] = rows
    ok = [r for r in rows if r.get("lead_same_contact") is not None]
    out["p1_summary"] = {"n": len(rows), "n_complete": len(ok),
                         "lead_b2_min": min(r["lead_b2"] for r in rows), "lead_b2_max": max(r["lead_b2"] for r in rows),
                         "contact_part_min": min(r["contact_part"] for r in ok) if ok else None,
                         "contact_part_max": max(r["contact_part"] for r in ok) if ok else None,
                         "lead_same_min": min(r["lead_same_contact"] for r in ok) if ok else None,
                         "lead_same_max": max(r["lead_same_contact"] for r in ok) if ok else None,
                         "n_niox_still_ahead": sum(r["lead_same_contact"] > 0 for r in ok)}
    print("P1", json.dumps(out["p1_summary"]), flush=True)
    # ---------------- P2
    cl = load_cost_library()
    prices = pink_cells(cl)
    out["p2_prices"] = prices
    line = A.cost_line()
    runs = [json.loads(p.read_text()) for p in sorted((PB / "runs").glob("*.json"))]
    calls = {f"{a}/{s}": [] for a in ARCHS for s in SCENS}
    worst = 0.0
    for r in runs:
        for c in r["calls"]:
            if not c["feasible"]:
                continue
            u0 = cost_per_watt(c["materials_usd_m2"], c["module_pce_pct"], line)["usd_per_W"]
            worst = max(worst, abs(u0 / c["usd_per_W"] - 1))
            calls[f"{r['arch']}/{r['scenario']}"].append(c)
    out["p2_recompute_max_rel_err"] = worst
    if worst > 1e-9:
        raise SystemExit(f"cost recompute does not reproduce stored USD/W (max rel err {worst})")

    def recost(c, f_ag, f_au):
        """Exact: USD/W is linear in the materials bill, USD/W = (M + K) / P with P = good W per m2 (design-specific)."""
        f = f_ag if c["metal"] == "Ag" else f_au if c["metal"] == "Au" else 1.0
        if f == 1.0:
            return c["usd_per_W"]
        return c["usd_per_W"] + c["back_electrode_usd_m2"] * (f - 1) / c["_good_W"]

    for cs in calls.values():
        for c in cs:
            c["_good_W"] = c["module_pce_pct"] / 100.0 * INCIDENT * line.yield_fraction.value
    chk = max(abs(recost(c, 1.37, 1.0) / cost_per_watt(c["materials_usd_m2"] + c["back_electrode_usd_m2"] * 0.37,
                                                        c["module_pce_pct"], line)["usd_per_W"] - 1)
              for c in calls["p-i-n/base"][:400] if c["metal"] == "Ag")
    out["p2_linear_check_max_rel_err"] = chk
    if chk > 1e-9:
        raise SystemExit(f"closed-form re-costing disagrees with the cost engine ({chk})")

    ag, au = prices["Ag"], prices["Au"]
    corners = {"silver_min": (ag["min"] / ag["base"], 1.0), "silver_max": (ag["max"] / ag["base"], 1.0),
               "gold_min": (1.0, au["min"] / au["base"]), "gold_max": (1.0, au["max"] / au["base"])}
    out["p2_corners"] = {}
    for name, (fa, fu) in corners.items():
        per = {}
        for k, cs in calls.items():
            per[k] = front_stats([(c["module_pce_pct"], recost(c, fa, fu), f"{c['HTL']}/{c['metal']}") for c in cs])
        out["p2_corners"][name] = {"f_ag": fa, "f_au": fu, "cases": per}
        print("P2", name, round(fa, 3), round(fu, 3), {k: (v["combos"], round(v["gap_pce"], 3), round(v["gap_cost_pct"], 1), v["wording"])
                                                       for k, v in per.items()}, flush=True)
    # silver cost-factor scan: smallest factor at which the gap is no longer 'small' (bisection; the cost gap grows with
    # the factor because only silver designs get dearer)
    scan = {}
    for k, cs in calls.items():
        def small(fa):
            return front_stats([(c["module_pce_pct"], recost(c, fa, 1.0), f"{c['HTL']}/{c['metal']}") for c in cs])["small"]
        lo, hi = 0.001, 1.0
        if small(hi):
            scan[k] = {"factor_gap_becomes_not_small": None}
            continue
        for _ in range(30):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if small(mid) else (lo, mid)
        st = front_stats([(c["module_pce_pct"], recost(c, hi, 1.0), f"{c['HTL']}/{c['metal']}") for c in cs])
        scan[k] = {"factor_gap_becomes_not_small": hi, "at_factor": st}
    out["p2_scan"] = {"what": "silver back-electrode cost factor (price x utilisation, relative to base) above which the "
                              "pooled gap is no longer 'small' (< 1 point and < 5%)", "cases": scan}
    print("P2 scan", scan, flush=True)
    (PB / "posthoc.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
