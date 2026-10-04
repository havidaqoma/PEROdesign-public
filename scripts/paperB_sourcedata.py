"""Study 2 (Paper B) Source Data workbook: every simulator call, the data behind every Study 2 table and figure, the
Study 2 physics overlay, the new sourced values and every assumption. Mirrors scripts/paperA_sourcedata.py.
  python scripts/paperB_sourcedata.py   -> paper/paperAB/build/PaperB_SourceData.xlsx
Re-reads the saved workbook and checks row counts and 500 random calls against the run files (fails loudly)."""
import json
import math
import random
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
import paperA_sourcedata as SD  # noqa: E402
from perodesign.optim import objective_b as OB  # noqa: E402
from perodesign.tea import load_cost_library  # noqa: E402

PB = REPO / "phase0" / "paperB"
OUT = REPO / "paper" / "paperAB" / "build" / "SourceData_material_choice.xlsx"
ARCHS, SCENS, METHODS = ("p-i-n", "n-i-p"), ("base", "worse", "better"), ("random", "nsga2", "mixbo")
COMBOS = [f"{h}/{m}" for h in OB.HTLS for m in OB.METALS]


def main():
    runs = {}
    for p in sorted((PB / "runs").glob("*.json")):
        a, s, m, k = p.stem.split("__")
        runs[(a, s, m, int(k[1:]))] = json.loads(p.read_text())
    res = json.loads((PB / "result.json").read_text())
    swf = json.loads((PB / "swf.json").read_text())
    num = json.loads((REPO / "paper" / "paperAB" / "numbers.json").read_text(encoding="utf-8"))
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    for row in (["SourceData_material_choice.xlsx: material-choice design (the optimiser also chooses the hole-transport layer and the back metal); companion workbook: SourceData_thickness_only.xlsx"],
                ["Author: Havid Aqoma (havidaqoma.khoiruddin@xmu.edu.my), Xiamen University Malaysia"],
                ["Pre-registration: docs/PaperB_preregistration.md, commit 2b32a78 (amendments A1-A3)"],
                ["Status labels: measured = read from run files; computed = derived by the analysis script; sourced = value with a "
                 "verbatim quote in a hashed source; assumed = labelled assumption or proxy"],
                [], ["Sheet", "Content"],
                ["Calls_all", "every simulator call of the 90 runs (measured)"],
                ["Runs_summary", "one row per run (measured / computed)"],
                ["Q1_scores", "hypervolume, IGD+ and no-Au hypervolume per seed, with mean and CI (computed)"],
                ["Q2_front", "pooled Pareto front points per case (computed)"],
                ["Q2_ends", "PCE-optimal and cost-optimal designs per case (computed)"],
                ["Per_combo", "best PCE and lowest USD/W per material set and case (computed)"],
                ["Call_share", "share of calls per material set and method (computed)"],
                ["Q4_PTAA", "break-even PTAA analysis (computed)"],
                ["SWF_sensitivity", "bare metal work function re-simulations (measured)"],
                ["Overlay_physics", "material-choice physics overlay: metals, thickness, interfaces, contact rule (sourced / assumed)"],
                ["New_sources", "silver price, silver density, metal work functions with verbatim quotes (sourced)"],
                ["Assumptions", "every assumption and proxy specific to the material choice (assumed)"],
                ["PostHoc_contact", "POST-HOC: contact attribution over the 12 optimised NiOx designs"],
                ["PostHoc_prices", "POST-HOC: re-costing at the 2023-2026 metal price extremes"],
                ["Numbers_material_choice", "every material-choice number printed in the paper with its source (computed)"]):
        ws.append(row)
    cols = ["arch", "scenario", "method", "seed", "call", "batch", "HTL", "metal", "feasible", "sim_status", "reason",
            "x", "cell_pce_pct", "voc_V", "ff", "jsc_mA_cm2", "module_pce_pct", "usd_per_W", "log10_usd_per_W",
            "usd_per_W_high_prices", "materials_usd_m2", "back_electrode_usd_m2", "design_hash", "library_sha256"]
    rows = []
    for (a, s, m, k), r in sorted(runs.items()):
        for c in r["calls"]:
            rows.append([a, s, m, k, c["call"], c["batch"], c["HTL"], c["metal"], bool(c["feasible"]), c["sim_status"],
                         c.get("reason"), json.dumps(c["x"])] + [c.get(x) for x in cols[12:]])
    SD.sheet(wb, "Calls_all", "Every material-choice simulator call (measured)", cols, rows)
    SD.sheet(wb, "Runs_summary", "One row per run", ["arch", "scenario", "method", "seed", "seconds", "n_infeasible", "hv_final"],
             [[a, s, m, k, r["seconds"], r["n_infeasible"], r["hv_final"]] for (a, s, m, k), r in sorted(runs.items())])
    rows = []
    for key, c in res["cases"].items():
        for m in METHODS:
            v = c["methods"][m]
            for k in range(5):
                rows.append([key, m, k, v["hv_final"][k], v["igd_plus"][k], v["hv_no_au"][k], v["calls_to_95pct_best"][k],
                             v["hv_mean"], v["hv_ci95_half"], v["igd_plus_mean"], v["igd_plus_ci95_half"]])
    SD.sheet(wb, "Q1_scores", "Per-seed scores and their summaries", ["case", "method", "seed", "hv_final", "igd_plus", "hv_no_au",
             "calls_to_95pct", "hv_mean", "hv_ci95_half", "igd_mean", "igd_ci95_half"], rows)
    SD.sheet(wb, "Q2_front", "Pooled Pareto front points", ["case", "module_pce_pct", "usd_per_W", "material_set"],
             [[key, p, u, cb] for key, c in res["cases"].items() for p, u, cb in c["q2"]["front"]])
    rows = []
    for key, c in res["cases"].items():
        q = c["q2"]
        for end in ("pce_optimal", "cost_optimal"):
            d = q[end]
            rows.append([key, end, d["combo"], json.dumps(d["x"]), d["module_pce_pct"], d["cell_pce_pct"], d["voc_V"], d["ff"],
                         d["jsc_mA_cm2"], d["usd_per_W"], d["usd_per_W_high_prices"], d["materials_usd_m2"],
                         d["back_electrode_usd_m2"], d["usd_per_W_by_rate_region"]["CN"], d["usd_per_W_by_rate_region"]["IN"],
                         q["gap_pce_points"], q["gap_cost_pct"], q["wording"], q["spearman_pce_usd_pooled"]])
    SD.sheet(wb, "Q2_ends", "Both ends of each pooled front", ["case", "end", "material_set", "x", "module_pce_pct", "cell_pce_pct",
             "voc_V", "ff", "jsc", "usd_per_W", "usd_per_W_high_prices", "materials_usd_m2", "back_electrode_usd_m2",
             "usd_per_W_CN_rate", "usd_per_W_IN_rate", "gap_pce", "gap_cost_pct", "wording", "spearman"], rows)
    SD.sheet(wb, "Per_combo", "Best result per material set (pooled)", ["case", "material_set", "n_feasible", "best_pce",
             "usd_per_W_at_best_pce", "min_usd_per_W", "pce_at_min_usd"],
             [[key, cb, v["n_feasible"], v["best_pce"], v["usd_per_W_at_best_pce"], v["min_usd_per_W"], v["pce_at_min_usd"]]
              for key, c in res["cases"].items() for cb, v in c["q2"]["per_combo"].items()])
    SD.sheet(wb, "Call_share", "Share of calls per material set", ["case", "method"] + COMBOS,
             [[key, m] + [c["methods"][m]["call_share_by_combo"][cb] for cb in COMBOS] for key, c in res["cases"].items() for m in METHODS])
    SD.sheet(wb, "Q4_PTAA", "Break-even PTAA price analysis", ["case", "metal", "ptaa_best_pce", "ptaa_best_usd", "niox_best_pce",
             "niox_best_usd", "ptaa_advantage_pts", "slope_usdW_per_usdg", "break_even_algebraic_usd_g", "status"],
             [[key, mt, v["PTAA_best"]["module_pce_pct"], v["PTAA_best"]["usd_per_W"], v["NiOx_best"]["module_pce_pct"],
               v["NiOx_best"]["usd_per_W"], v["ptaa_pce_advantage_points"], v["slope_usd_W_per_usd_g"],
               v["break_even_vs_NiOx_algebraic_usd_g"], v["status"]] for key, c in res["cases"].items() for mt, v in c["q4"]["by_metal"].items()])
    SD.sheet(wb, "SWF_sensitivity", "Bare metal work function re-simulations (n-i-p)", ["scenario", "material_set", "x",
             "B2_pce", "B2_usd", "metal_wf_pce", "metal_wf_usd", "status", "B2_voc", "metal_wf_voc"],
             [[s, cb, json.dumps(v["x"]), v["B2"][0], v["B2"][1], v["metal_wf"][0], v["metal_wf"][1], v["metal_wf_status"],
               v["B2_voc_V"], v["metal_wf_voc_V"]] for s, c in swf["cases"].items() for cb, v in c["rows"].items()])
    ov = OB.overlay()
    rows = [["metal optics", m, v, "McPeak et al. 2015, doi:10.1021/ph5004237 (refractiveindex.info, CC0)"] for m, v in ov["metals"].items()]
    rows += [["metal thickness (m)", a, v, "production metal thickness of each architecture (thickness-only design)"] for a, v in ov["metal_thickness_m"].items()]
    rows += [["interface", pair, json.dumps(v["params"]), v["provenance"]["status"] + ": " + v["provenance"]["from"]] for pair, v in ov["interfaces"].items()]
    rows += [["contact rule", "all", ov["contact_rule"], "G1 step 2 amendment B2: work function = majority band edge of the touching layer"]]
    for a in ARCHS:
        for h in OB.HTLS:
            rows.append(["contact work functions (eV)", f"{a} {h}", json.dumps(OB.b2_contacts(a, h)), "rule B2"])
    SD.sheet(wb, "Overlay_physics", "Material-choice physics overlay (perodesign/library/paperB_overlay.yaml)", ["item", "key", "value", "provenance"], rows)
    cl = load_cost_library()
    ent = {e["id"]: e for e in cl["entries"]}
    rows = []
    for eid in ("wb_silver_2026_aug", "ag_density", "wb_gold_2026_aug", "au_density"):
        e = ent[eid]
        src = cl["sources"][e["source"]]
        rows.append([eid, e["value"], e["unit"], src.get("citation"), src.get("doi", ""), e["quote_span"], src["sha256"]])
    wf = ov["metal_work_function_eV"]
    rows.append(["metal work functions (S-WF only)", json.dumps({m: wf[m] for m in OB.METALS}), "eV",
                 "SCAPS input table", wf["provenance"]["doi"], wf["provenance"]["quote"], ""])
    SD.sheet(wb, "New_sources", "Sourced values used by the material choice", ["id", "value", "unit", "citation", "doi", "verbatim quote", "source sha256"], rows)
    SD.sheet(wb, "Assumptions", "Material-choice assumptions and proxies", ["assumption", "value / rule", "where used", "status"], [
        ["contact rule B2 (barrier-free hole and electron contacts)", "W = majority band edge of touching layer", "all material-choice runs", "assumed"],
        ["new interfaces PTAA|MAPbI3, MAPbI3|NiOx", "SimSS default hole-side values", "PTAA in p-i-n, NiOx in n-i-p", "assumed (transferred)"],
        ["metal evaporation utilisation", "Liu 2025 Cu utilisation (0.25)", "Ag and Au cost", "proxy"],
        ["PTAA price", "1145 USD/g lab catalogue (source: arbitrary)", "PTAA cost; Q4", "proxy"],
        ["PTAA density", "1.1 g/cm3", "PTAA cost", "assumed"],
        ["metal thickness", "101 nm (n-i-p), 150 nm (p-i-n), same for all metals", "optics and cost", "assumed (thickness-only values)"],
        ["NiOx on top of absorber (n-i-p), PTAA below absorber (p-i-n)", "same library values as the thickness-only design", "material-choice design space", "model-only stack order"],
        ["practical PCE resolution for the wording rule", "0.2 points", "Q2 wording", "convention (fixed before runs)"],
        ["module geometry, line costs, scenarios", "as the thickness-only design", "all", "see SourceData_thickness_only.xlsx Assumptions"]])
    ph = json.loads((PB / "posthoc.json").read_text())
    SD.sheet(wb, "PostHoc_contact", "POST-HOC (external review): NiOx designs re-simulated with PTAA's contact (SI Table S23)",
             ["arch", "scenario", "metal", "x", "niox_B2_pce", "niox_PTAA_contact_pce", "ptaa_best_B2_pce", "lead_B2",
              "contact_part", "lead_same_contact", "status"],
             [[r["arch"], r["scenario"], r["metal"], json.dumps(r["x"]), r["niox_b2"], r["module_pce_pct"], r["ptaa_best_b2"],
               r["lead_b2"], r.get("contact_part"), r.get("lead_same_contact"), r["status"]] for r in ph["p1"]])
    rows = [[name, c["f_ag"], c["f_au"], k, "; ".join(v["combos"]), v["gap_pce"], v["gap_cost_pct"], v["wording"]]
            for name, c in ph["p2_corners"].items() for k, v in c["cases"].items()]
    rows += [["silver scan threshold", v["factor_gap_becomes_not_small"], 1.0, k, "", "", "", "factor at which gap stops being small"]
             for k, v in ph["p2_scan"]["cases"].items()]
    SD.sheet(wb, "PostHoc_prices", "POST-HOC (external review): re-costing at 2023-2026 metal price extremes (SI Tables S24-S25). "
             f"Verified Pink Sheet values: Ag {ph['p2_prices']['Ag']['values']}; Au {ph['p2_prices']['Au']['values']}",
             ["price case", "Ag factor", "Au factor", "case", "sets on front", "gap_pce", "gap_cost_pct", "wording"], rows)
    SD.sheet(wb, "Numbers_material_choice", "Every material-choice token printed in the manuscript", ["token", "printed value", "raw", "source"],
             [[k, v["value"], json.dumps(v["raw"]) if not isinstance(v["raw"], (int, float, str)) else v["raw"], v["source"]]
              for k, v in sorted(num.items()) if k.startswith("b_")])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    wb2 = load_workbook(OUT, read_only=True)
    data = list(wb2["Calls_all"].iter_rows(values_only=True))
    hdr = next(i for i, r in enumerate(data) if r and r[0] == "arch")
    body = data[hdr + 1:]
    assert len(body) == 21600, len(body)
    idx = {c: i for i, c in enumerate(data[hdr])}
    for row in random.Random(1).sample(body, 500):
        c = runs[(row[idx["arch"]], row[idx["scenario"]], row[idx["method"]], row[idx["seed"]])]["calls"][row[idx["call"]]]
        for key in ("usd_per_W", "module_pce_pct", "cell_pce_pct", "materials_usd_m2"):
            a_, b_ = row[idx[key]], c.get(key)
            assert (a_ is None and b_ is None) or math.isclose(a_, b_, rel_tol=1e-12), (key, a_, b_)
        assert row[idx["HTL"]] == c["HTL"] and row[idx["metal"]] == c["metal"]
    print(json.dumps({"xlsx": str(OUT), "bytes": OUT.stat().st_size, "sheets": wb2.sheetnames, "calls_rows": len(body),
                      "sample_check": "500/500 rows match run files"}))


if __name__ == "__main__":
    main()
