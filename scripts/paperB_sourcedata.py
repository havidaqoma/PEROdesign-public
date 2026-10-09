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


HV_UNIT = "PCE points x decades of USD/W"


def fmt(v):
    """Readable number for title rows: 4 significant digits, no float artefacts."""
    return f"{v:.4g}" if isinstance(v, float) else str(v)


def prose(d):
    """A dict as prose for a title row (no Python object dumps; review F31)."""
    return "; ".join(f"{k.replace('_', ' ')} {fmt(v)}" for k, v in d.items())


def yes_no(v):
    return "n/a" if v is None else ("yes" if v else "no")


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
                ["How to read: each sheet has a title row, optional note rows and one blank row before the header row; "
                 "the header is the first row whose first cell is a column name (pandas: header=2 when a sheet has no "
                 "note row, header=3 with one note row)."],
                ["Units: efficiencies in % (PCE) or percentage points (differences, 'points'); thicknesses in nm, stripe "
                 "width in mm; cost per watt in USD/W; area costs in USD/m2; hypervolume in " + HV_UNIT + "; IGD+ "
                 "is dimensionless (normalised by the pooled feasible range); fractions run from 0 to 1."],
                ["x: the continuous design in the order given by the x_layers column (p-i-n: "
                 + ", ".join(OB.space("p-i-n").names) + "; n-i-p: " + ", ".join(OB.space("n-i-p").names) + ")."],
                ["Keys: design_hash is the SHA-256 of the device input passed to the simulator; it does not cover the "
                 "stripe width (a module parameter) or the material library, so a call is identified by design_hash "
                 "with library_sha256 and the stripe width in x."],
                ["Abbreviations: B2 = contact rule of the material-choice design (each electrode's work function equals "
                 "the majority band edge of the layer it touches); NP = number of grid points of the drift-diffusion "
                 "solver; hv_no_au = hypervolume of the designs without gold, against the worst Cu/Ag corner; igd_plus = "
                 "IGD+ distance of a run to the pooled front; calls_to_95pct = 241 means the run never reached 95% of "
                 "the best hypervolume within 240 calls."],
                ["Main Figures 4 and 5 have no separate sheet: they plot the feasible rows of Calls_all (module_pce_pct, "
                 "usd_per_W, HTL, metal) per case, with the front points of Q2_front; Figure 5 shows the same data in "
                 "the low-cost corner."],
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
                ["PostHoc_interlayer", "POST-HOC: n-i-p interlayer cost bound (SI Table S26)"],
                ["PostHoc_grid", "POST-HOC: simulation grid check, both front ends at 250/500/1000 grid points (SI Note S19, Table S28)"],
                ["PostHoc_mesh_front", "POST-HOC: every pooled-front member re-simulated at 250/500/1000 grid points (SI Note S19, Table S29)"],
                ["PostHoc_mesh_fronts", "POST-HOC: the fronts rebuilt from those re-simulations, ends and gaps (SI Table S29)"],
                ["PostHoc_PTAA_front", "POST-HOC: n-i-p front from the PTAA designs alone (SI Note S20, Table S30)"],
                ["PostHoc_paired", "POST-HOC: paired per-seed comparison of the final hypervolume, both levels (SI Table S31)"],
                ["PostHoc_JV_optima", "POST-HOC: current-voltage metrics of the PCE-optimal design of every case, both levels (SI Table S32)"],
                ["PostHoc_rho", "POST-HOC: efficiency-cost rank correlation over all feasible calls and over distinct designs, both levels"],
                ["PostHoc_absorber_price", "POST-HOC: published MAPbI3 precursor prices against the library value (SI Note S20)"],
                ["FigS9_HV_curves", "Figure S9 and main Figure 6b: hypervolume vs calls, mean and 95% band per method and case (computed)"],
                ["Numbers_material_choice", "every material-choice number printed in the paper with its source (computed)"]):
        ws.append(row)
    cols = ["arch", "scenario", "method", "seed", "call", "batch", "HTL", "metal", "feasible", "sim_status", "reason",
            "x", "cell_pce_pct", "voc_V", "ff", "jsc_mA_cm2", "module_pce_pct", "usd_per_W", "log10_usd_per_W",
            "usd_per_W_high_prices", "materials_usd_m2", "back_electrode_usd_m2", "design_hash", "library_sha256", "x_layers"]
    xl = {a: ", ".join(OB.space(a).names) for a in ARCHS}
    rows = []
    for (a, s, m, k), r in sorted(runs.items()):
        for c in r["calls"]:
            rows.append([a, s, m, k, c["call"], c["batch"], c["HTL"], c["metal"], bool(c["feasible"]), c["sim_status"],
                         c.get("reason"), json.dumps(c["x"])] + [c.get(x) for x in cols[12:-1]] + [xl[a]])
    SD.sheet(wb, "Calls_all", "Every material-choice simulator call (measured)", cols, rows)
    SD.sheet(wb, "Runs_summary", "One row per run", ["arch", "scenario", "method", "seed", "seconds", "n_infeasible",
             "hv_final (" + HV_UNIT + ")"],
             [[a, s, m, k, r["seconds"], r["n_infeasible"], r["hv_final"]] for (a, s, m, k), r in sorted(runs.items())])
    rows = []
    for key, c in res["cases"].items():
        for m in METHODS:
            v = c["methods"][m]
            for k in range(5):
                rows.append([key, m, k, v["hv_final"][k], v["igd_plus"][k], v["hv_no_au"][k], v["calls_to_95pct_best"][k],
                             v["hv_mean"], v["hv_ci95_half"], v["igd_plus_mean"], v["igd_plus_ci95_half"]])
    SD.sheet(wb, "Q1_scores", "Per-seed scores and their summaries; hypervolume columns in " + HV_UNIT + ", IGD+ "
             "dimensionless", ["case", "method", "seed", "hv_final", "igd_plus", "hv_no_au",
             "calls_to_95pct (241 = not reached)", "hv_mean", "hv_ci95_half (t, 4 dof)", "igd_mean", "igd_ci95_half (t, 4 dof)"], rows)
    SD.sheet(wb, "Q2_front", "Pooled Pareto front points", ["case", "module_pce_pct", "usd_per_W", "material_set"],
             [[key, p, u, cb] for key, c in res["cases"].items() for p, u, cb in c["q2"]["front"]])
    rows = []
    for key, c in res["cases"].items():
        q = c["q2"]
        for end in ("pce_optimal", "cost_optimal"):
            d = q[end]
            rows.append([key, end, d["combo"], json.dumps(d["x"]), xl[key.split("/")[0]], d["module_pce_pct"], d["cell_pce_pct"], d["voc_V"], d["ff"],
                         d["jsc_mA_cm2"], d["usd_per_W"], d["usd_per_W_high_prices"], d["materials_usd_m2"],
                         d["back_electrode_usd_m2"], d["usd_per_W_by_rate_region"]["CN"], d["usd_per_W_by_rate_region"]["IN"],
                         q["gap_pce_points"], q["gap_cost_pct"], q["wording"], q["spearman_pce_usd_pooled"]])
    SD.sheet(wb, "Q2_ends", "Both ends of each pooled front. The rank correlation is over the feasible designs with "
             "distinct efficiency and cost values (PostHoc_rho gives it over all feasible calls too)",
             ["case", "end", "material_set", "x", "x_layers", "module_pce_pct", "cell_pce_pct",
             "voc_V", "ff", "jsc_mA_cm2", "usd_per_W", "usd_per_W_high_prices", "materials_usd_m2", "back_electrode_usd_m2",
             "usd_per_W_CN_rate", "usd_per_W_IN_rate", "gap_pce_points", "gap_cost_pct", "wording",
             "spearman_pce_usd (distinct designs)"], rows)
    SD.sheet(wb, "Per_combo", "Best result per material set (pooled)", ["case", "material_set", "n_feasible", "best_pce",
             "usd_per_W_at_best_pce", "min_usd_per_W", "pce_at_min_usd"],
             [[key, cb, v["n_feasible"], v["best_pce"], v["usd_per_W_at_best_pce"], v["min_usd_per_W"], v["pce_at_min_usd"]]
              for key, c in res["cases"].items() for cb, v in c["q2"]["per_combo"].items()])
    SD.sheet(wb, "Call_share", "Fraction of calls (0 to 1) per material set", ["case", "method"] + [f"{cb} fraction" for cb in COMBOS],
             [[key, m] + [c["methods"][m]["call_share_by_combo"][cb] for cb in COMBOS] for key, c in res["cases"].items() for m in METHODS])
    SD.sheet(wb, "Q4_PTAA", "Break-even PTAA price analysis. A negative algebraic break-even price means PTAA cannot "
             "match NiOx at any price (see status)", ["case", "metal", "ptaa_best_pce", "ptaa_best_usd", "niox_best_pce",
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
    pp = ph["p2_prices"]
    SD.sheet(wb, "PostHoc_prices", "POST-HOC (external review): re-costing at 2023-2026 metal price extremes (SI Tables S24-S25). "
             f"Verified World Bank Pink Sheet values in USD per troy ounce ({pp['Ag']['header']}): "
             f"Ag {', '.join(fmt(v) for v in pp['Ag']['values'])}; Au {', '.join(fmt(v) for v in pp['Au']['values'])}",
             ["price case", "Ag factor", "Au factor", "case", "sets on front", "gap_pce", "gap_cost_pct", "wording"], rows)
    mx = json.loads((PB / "posthoc_moox.json").read_text())
    SD.sheet(wb, "PostHoc_interlayer", "POST-HOC (citation review): n-i-p interlayer cost bound, no new simulations (SI Table S26). "
             f"Layer: {prose(mx['layer'])}. Illustrative cost: {prose(mx['illustrative'])}",
             ["case", "sets on front (no interlayer)", "reading (no interlayer)", "added USD/W (cheapest Cu)", "added %",
              "break-even K USD/m2", "break-even MoO3 USD/g", "reading above break-even"],
             [[k, "; ".join(v["no_interlayer"]["combos"]), v["no_interlayer"]["wording"],
               v["illustrative_add_usd_per_W_cheapest_cu"], v["illustrative_add_pct_cheapest_cu"], v["breakeven_usd_m2"],
               v["breakeven_usd_per_g_moo3"], v["after_breakeven"]["wording"]] for k, v in mx["cases"].items()])
    me = json.loads((PB / "posthoc_mesh.json").read_text())
    SD.sheet(wb, "PostHoc_grid", "POST-HOC (pre-submission review): stored front ends re-simulated at "
             f"{me['NP_values']} grid points (SIMsalabim max {me['simsalabim_max_NP']}); scripts/paperAB_mesh_check.py",
             ["level", "case", "end", "NP", "module_pce_pct", "stored_module_pce_pct", "cell_pce_pct", "usd_per_W", "material set / note"],
             [[r["level"], r["case"], r["end"], r["NP"], r["module_pce_pct"], r["stored_module_pce_pct"], r.get("cell_pce_pct"),
               r["usd_per_W"], r.get("combo")] for r in me["rows"]]
             + [[f["level"], f["case"], "gap", f["NP"], f["gap_pce_points"], None, None, f["gap_cost_pct"],
                 "above the 0.2-point line: " + yes_no(f["above_0p2_line"])
                 + (" (fixed materials: no line applies)" if f["above_0p2_line"] is None else "")] for f in me["fronts"]])
    # --- POST-HOC sheets added with the pre-submission review (SI Notes S17, S19, S20)
    mf = json.loads((PB / "posthoc_mesh_front.json").read_text(encoding="utf-8"))
    pts = {(p["case"], str(p["idx"])): p for p in mf["points"]}
    if any(pts[(r["case"], str(r["end"]))]["combo"] != r["combo"] for r in mf["rows"]):
        raise SystemExit("posthoc_mesh_front.json: a re-simulated row does not match its stored front point")
    SD.sheet(wb, "PostHoc_mesh_front", "POST-HOC (pre-submission review): every member of the six material-choice pooled "
             f"fronts re-simulated at {', '.join(str(n) for n in mf['NP_values'])} grid points, designs not re-optimised "
             "(scripts/paperAB_mesh_front.py; SI Note S19, Table S29)",
             ["case", "point", "NP", "material_set", "x", "x_layers", "status", "cell_pce_pct", "module_pce_pct", "usd_per_W",
              "stored_module_pce_pct", "stored_usd_per_W"],
             [[r["case"], r["end"], r["NP"], r["combo"], json.dumps(pts[(r["case"], str(r["end"]))]["x"]), xl[r["case"].split("/")[0]],
               r["status"], r.get("cell_pce_pct"), r.get("module_pce_pct"), r.get("usd_per_W"), r["stored_module_pce_pct"],
               r["stored_usd_per_W"]] for r in mf["rows"]])
    SD.sheet(wb, "PostHoc_mesh_fronts", "POST-HOC: fronts rebuilt from the re-simulated members (SI Table S29)",
             ["case", "NP", "points simulated", "front_size", "sets on front", "PCE-end set", "cost-end set",
              "PCE-end module_pce_pct", "cost-end module_pce_pct", "gap_pce_points", "gap_cost_pct", "above the 0.2-point line"],
             [[f["case"], f["NP"], f["n_points_simulated"], f["front_size"], "; ".join(f["combos_on_front"]), f["pce_end_combo"],
               f["cost_end_combo"], f["pce_end_pct"], f["cost_end_pct"], f["gap_pce_points"], f["gap_cost_pct"],
               yes_no(f["above_0p2_line"])] for f in mf["fronts"]])
    pr = json.loads((PB / "posthoc_review.json").read_text(encoding="utf-8"))
    SD.sheet(wb, "PostHoc_PTAA_front", "POST-HOC (pre-submission review, stored data only): n-i-p Pareto front of the feasible "
             "PTAA designs alone, pooled over all methods and seeds, distinct designs (scripts/paperAB_posthoc_review.py; "
             "SI Note S20, Table S30)",
             ["scenario", "feasible calls", "distinct designs", "front_size", "metals on front", "PCE-end metal",
              "PCE-end module_pce_pct", "PCE-end usd_per_W", "cost-end metal", "cost-end module_pce_pct", "cost-end usd_per_W",
              "gap_pce_points", "gap_cost_pct", "above the 0.2-point line"],
             [[s, v["n_feasible_calls"], v["n_distinct"], v["front_size"], "; ".join(v["metals_on_front"]), v["pce_end"]["metal"],
               v["pce_end"]["module_pce_pct"], v["pce_end"]["usd_per_W"], v["cost_end"]["metal"],
               v["cost_end"]["module_pce_pct"], v["cost_end"]["usd_per_W"], v["gap_pce_points"], v["gap_cost_pct"],
               yes_no(v["above_0p2_line"])] for s, v in pr["r1_ptaa_nip_front"].items()])
    SD.sheet(wb, "PostHoc_paired", "POST-HOC: paired comparison of the final hypervolume (" + HV_UNIT + "), per-seed "
             "differences, t interval with 4 degrees of freedom (SI Table S31)",
             ["level", "case", "pair (first minus second)", "seeds", "mean difference", "ci95_half", "paired interval excludes 0",
              "separated by CI non-overlap", "winner"],
             [[lvl.replace("_", "-"), r["case"], r["pair"], r["n_seeds"], r["mean_diff"], r["ci95_half"], yes_no(r["paired_separates"]),
               yes_no(r["nonoverlap_separates"]), r["winner"]] for lvl, rr in pr["r2_paired"].items() for r in rr])
    SD.sheet(wb, "PostHoc_JV_optima", "POST-HOC: current-voltage metrics of the PCE-optimal design of every case, from the "
             "stored simulator output (material set 'fixed' = the stack's own materials; SI Table S32)",
             ["level", "case", "material_set", "voc_V", "ff", "jsc_mA_cm2", "cell_pce_pct", "module_pce_pct"],
             [[r["level"].replace("_", "-"), r["case"], r["combo"], r["voc_V"], r["ff"], r["jsc_mA_cm2"], r["cell_pce_pct"],
               r["module_pce_pct"]] for r in pr["r3_jv_pce_optimal"]])
    SD.sheet(wb, "PostHoc_rho", "POST-HOC: Spearman rank correlation between module efficiency and cost per watt over two "
             "populations. The paper quotes all feasible calls for the thickness-only design and distinct designs for the "
             "material-choice design (review F29)",
             ["level", "case", "rho, all feasible calls", "feasible calls", "rho, distinct designs", "distinct designs"],
             [[lvl.replace("_", "-"), c, v["all_feasible_calls"], v["n_calls"], v["distinct_designs"], v["n_distinct"]]
              for lvl, cc in pr["r4_rho"].items() for c, v in cc.items()])
    ap = json.loads((PB / "posthoc_absorber_prices.json").read_text(encoding="utf-8"))
    ch, wu = ap["chang2017"], ap["wu2026"]
    SD.sheet(wb, "PostHoc_absorber_price", "POST-HOC: published MAPbI3 precursor prices against the library value of "
             f"{fmt(ap['library_usd_per_g'])} USD/g (scripts/paperAB_absorber_prices.py; SI Notes S17 and S20). Quotes are verbatim; "
             "source texts are checked by SHA-256",
             ["source", "item", "USD/g", "low USD/g", "high USD/g", "multiple of library value", "verbatim quote", "url", "sha256"],
             [["Chang 2017", "PbI2", ch["PbI2"]["usd_per_g"], ch["PbI2"]["lo"], ch["PbI2"]["hi"], None, ch["PbI2"]["quote"], ch["url"], ch["sha256"]],
              ["Chang 2017", "MAI", ch["MAI"]["usd_per_g"], ch["MAI"]["lo"], ch["MAI"]["hi"], None, ch["MAI"]["quote"], ch["url"], ch["sha256"]],
              ["Chang 2017", f"MAPbI3 (mass-weighted, PbI2 mass fraction {fmt(ch['mass_fraction_PbI2_in_MAPbI3'])})",
               ch["MAPbI3_usd_per_g"]["usd_per_g"], ch["MAPbI3_usd_per_g"]["lo"], ch["MAPbI3_usd_per_g"]["hi"],
               ap["multiples_of_library"]["chang_mid"], "", ch["url"], ch["sha256"]],
              ["Wu 2026", f"precursor mixture ({wu['basis']}; {fmt(wu['eur_per_kg'])} EUR/kg at {fmt(wu['eur_per_usd_2025'])} EUR/USD, "
               "World Bank 2025)", wu["usd_per_g"], None, None, ap["multiples_of_library"]["wu_lab"], wu["quote"], wu["url"], wu["sha256"]]],
             notes=[f"Absorber price scan (p-i-n, base): the gap stays small up to {fmt(ap['scan_pin_base']['last_small_mult'])} times the "
                    f"library price ({fmt(ap['scan_pin_base']['last_small_usd_per_g'])} USD/g) and is not small from "
                    f"{fmt(ap['scan_pin_base']['first_not_small_mult'])} times ({fmt(ap['scan_pin_base']['first_not_small_usd_per_g'])} USD/g)."])
    import numpy as np
    from perodesign.optim import search as HS  # noqa: E402  (hv_curve, as used by Figure S9)
    hv_rows = []
    for key, cres in sorted(res["cases"].items()):
        a, s = key.split("/")
        for m in METHODS:
            C = np.array([HS.hv_curve([{"y": ([c["module_pce_pct"], c["log10_usd_per_W"]] if c["feasible"] else None)}
                                        for c in runs[(a, s, m, k)]["calls"]], cres["ref_point"]) for k in range(5)])
            mu, sd = C.mean(0), C.std(0, ddof=1)
            for i in range(C.shape[1]):
                hv_rows.append([a, s, m, i + 1, mu[i], mu[i] - 2.776 * sd[i] / 5 ** 0.5, mu[i] + 2.776 * sd[i] / 5 ** 0.5]
                               + list(C[:, i]))
    SD.sheet(wb, "FigS9_HV_curves", "Figure S9 / main Figure 6b. Hypervolume (" + HV_UNIT + ") vs simulator calls "
             "(computed). Band = mean +- t(0.975,4) sd/sqrt(5).",
             ["arch", "scenario", "method", "call", "hv_mean", "band_lo", "band_hi"] + [f"seed{k}" for k in range(5)], hv_rows)
    SD.sheet(wb, "Numbers_material_choice", "Every material-choice token printed in the manuscript", ["token", "printed value", "raw", "source"],
             [[k, v["value"], SD.raw_cell(k, v["raw"]), v["source"]] for k, v in sorted(num.items()) if k.startswith("b_")])
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
