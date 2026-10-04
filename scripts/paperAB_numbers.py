"""Numbers for the merged manuscript (paper/paperAB). Study 1 = Paper A tokens (copied unchanged from
paper/paperA/numbers.json + numbers_si.json); Study 2 = Paper B tokens, prefix b_, computed here from
phase0/paperB/{result.json,swf.json,gate0.json,diag.json,pilot.json,runs/*.json} and the code.
Every entry carries its source. Run in the WSL venv (imports the optimiser and cost engine):
  python scripts/paperAB_numbers.py -> paper/paperAB/numbers.json, paper/paperAB/numbers_si.json
"""
import json
import math
import sys
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from perodesign.optim import objective_b as OB  # noqa: E402
from perodesign.optim import search_b as SB  # noqa: E402

PA, PB, OUT = REPO / "paper" / "paperA", REPO / "phase0" / "paperB", REPO / "paper" / "paperAB"
ARCHS, SCENS, METHODS = ("p-i-n", "n-i-p"), ("base", "worse", "better"), ("random", "nsga2", "mixbo")
TAG = {"p-i-n": "pin", "n-i-p": "nip"}
SHORT = {"random": "R", "nsga2": "N", "mixbo": "B"}
N = {}


def put(tok, raw, fmt, source):
    tok = "b_" + tok
    if tok in N:
        raise KeyError(f"duplicate token {tok}")
    val = fmt.format(raw) if not isinstance(raw, str) else raw
    N[tok] = {"value": val, "raw": raw, "source": source}


def rng(tok, vals, fmt, source):
    put(tok + "_lo", min(vals), fmt, source + " (min)")
    put(tok + "_hi", max(vals), fmt, source + " (max)")


def main():
    res = json.loads((PB / "result.json").read_text())
    swf = json.loads((PB / "swf.json").read_text())
    g0 = json.loads((PB / "gate0.json").read_text())
    diag = json.loads((PB / "diag.json").read_text())
    pilot = json.loads((PB / "pilot.json").read_text())
    runs = {p.stem: json.loads(p.read_text()) for p in sorted((PB / "runs").glob("*.json"))}
    R = "phase0/paperB/result.json"
    # --- design and environment (code)
    put("nhtl", len(OB.HTLS), "{:d}", "objective_b.HTLS")
    put("nmetal", len(OB.METALS), "{:d}", "objective_b.METALS")
    put("ncombo", len(OB.HTLS) * len(OB.METALS), "{:d}", "len(HTLS) x len(METALS)")
    for a in ARCHS:
        sp = OB.space(a)
        put(f"ncont_{TAG[a]}", sp.n_cont, "{:d}", f"objective_b.space('{a}').n_cont")
        put(f"refcost_{TAG[a]}", 10 ** OB.reference_point(a)[1], "{:.1f}", "10**objective_b.reference_point(arch)[1]")
        put(f"refnoau_{TAG[a]}", 10 ** OB.reference_point_no_au(a)[1], "{:.2f}", "10**objective_b.reference_point_no_au(arch)[1]")
    ov = OB.overlay()
    put("lbe_nip", 1e9 * ov["metal_thickness_m"]["n-i-p"], "{:g}", "paperB_overlay.yaml metal_thickness_m n-i-p (nm)")
    put("lbe_pin", 1e9 * ov["metal_thickness_m"]["p-i-n"], "{:g}", "paperB_overlay.yaml metal_thickness_m p-i-n (nm)")
    for m in OB.METALS:
        put(f"wf_{m}", ov["metal_work_function_eV"][m], "{:g}", "paperB_overlay.yaml metal_work_function_eV (doi:10.3390/nano11051218)")
    lib = OB.physics_library("n-i-p", "NiOx", "Cu")
    pp = lambda mat, k: lib["materials"][mat]["params"][k]  # noqa: E731
    put("ev_niox", pp("NiOx", "E_v_eV"), "{:g}", "materials_v2.yaml NiOx E_v_eV")
    put("ev_ptaa", pp("PTAA", "E_v_eV"), "{:g}", "materials_v2.yaml PTAA E_v_eV")
    put("ec_c60", pp("C60", "E_c_eV"), "{:g}", "materials_v2.yaml C60 E_c_eV")
    put("ec_sno2", pp("SnO2", "E_c_eV"), "{:g}", "materials_v2.yaml SnO2 E_c_eV")
    from perodesign.tea import load_cost_library, _v
    cl = load_cost_library()
    put("ag_price", _v(cl, "wb_silver_2026_aug", "USD/toz"), "{:g}", "cost_library_v1.yaml wb_silver_2026_aug")
    put("ag_density", _v(cl, "ag_density", "g/cm3"), "{:g}", "cost_library_v1.yaml ag_density")
    put("au_price", _v(cl, "wb_gold_2026_aug", "USD/toz"), "{:,.0f}", "cost_library_v1.yaml wb_gold_2026_aug")
    put("ptaa_price", _v(cl, "ptaa_price_review_2022", "USD/g"), "{:,.0f}", "cost_library_v1.yaml ptaa_price_review_2022")
    put("price_month", "August 2026", "{}", "cost_library_v1.yaml wb_silver_2026_aug / wb_gold_2026_aug notes (last Pink Sheet column)")
    put("dpce_min", 0.2, "{:g}", "scripts/paperB_run.py DPCE_MIN (prereg §7)")
    put("bo_restarts", 4, "{:d}", "search_b.run_mixbo restarts (amendment A1)")
    put("bo_maxparallel", 6, "{:d}", "scripts/paperB_run.py PAPERB_BO_MAX default (amendment A2)")
    put("ver_botorch", metadata.version("botorch"), "{}", "importlib.metadata in the run venv")
    put("ver_pymoo", metadata.version("pymoo"), "{}", "importlib.metadata in the run venv")
    put("nruns", len(runs), "{:d}", "phase0/paperB/runs/*.json count")
    put("ncalls", sum(len(r["calls"]) for r in runs.values()), "{:,}", "sum of calls over phase0/paperB/runs")
    put("ninf", sum(r["n_infeasible"] for r in runs.values()), "{:d}", "sum n_infeasible over phase0/paperB/runs")
    put("ninf_max", max(r["n_infeasible"] for r in runs.values()), "{:d}", "max n_infeasible in one run")
    put("commit_prereg", "2b32a78", "{}", "git commit of docs/PaperB_preregistration.md before any run")
    # --- gate G0 and diagnostics
    put("g0_n", len(g0["g0_checks"]), "{:d}", "phase0/paperB/gate0.json g0_checks")
    for d in g0["deltas"]:
        t = TAG[d["arch"]]
        put(f"g0_{t}_prod", d["production"]["module_pce_pct"], "{:.2f}", "gate0.json deltas production module_pce_pct")
        put(f"g0_{t}_b2", d["step2_b2_contacts"]["module_pce_pct"], "{:.2f}", "gate0.json deltas step2_b2_contacts module_pce_pct")
        put(f"g0_{t}_d", d["step2_b2_contacts"]["module_pce_pct"] - d["production"]["module_pce_pct"], "{:.2f}",
            "gate0.json step2 - production module_pce_pct")
    sds = [diag["d1"][a][m]["resid_sd_points"] for a in ARCHS for m in ("Cu", "Ag")]
    put("noise_sd", max(sds), "{:.3f}", "diag.json d1 max resid_sd_points (module PCE)")
    agcu = [diag["d1"][a]["ag_minus_cu"]["mean"] for a in ARCHS]
    rng("agcu_ref", agcu, "{:.3f}", "diag.json d1 ag_minus_cu mean (reference design)")
    d2 = {(r["HTL"], r["W_R_eV"]): r for r in diag["d2"]}
    lead = d2[("NiOx", 5.7)]["module_pce_pct"] - d2[("PTAA", 5.4)]["module_pce_pct"]
    same = d2[("NiOx", 5.4)]["module_pce_pct"] - d2[("PTAA", 5.4)]["module_pce_pct"]
    put("d2_lead", lead, "{:.2f}", "diag.json d2 NiOx@5.7 - PTAA@5.4 module PCE")
    put("d2_same", same, "{:.2f}", "diag.json d2 NiOx@5.4 - PTAA@5.4 module PCE")
    put("d2_contact", lead - same, "{:.2f}", "diag.json d2 lead - same-anode lead")
    put("snr_lo", min(agcu) / max(sds), "{:.0f}", "diag.json min ag_minus_cu mean / max resid_sd_points")
    put("snr_hi", max(agcu) / max(sds), "{:.0f}", "diag.json max ag_minus_cu mean / max resid_sd_points")
    wfgap = [pp("NiOx", "E_v_eV") - ov["metal_work_function_eV"][m] for m in ("Cu", "Ag")]
    rng("wfgap", wfgap, "{:.1f}", "NiOx E_v_eV - metal_work_function_eV for Cu and Ag (eV)")
    for a in ARCHS:
        put(f"pilot_rho_{TAG[a]}", pilot["summary"][a]["spearman_pce_usd"], "{:.2f}", f"pilot.json summary.{a}.spearman_pce_usd")
    # --- per case
    hvg, hvgn, c95b, share_b, share_r, gp, gc, rho, padv, au_ratio, au_dpce, igd_b = ([] for _ in range(12))
    for a in ARCHS:
        for s in SCENS:
            c = res["cases"][f"{a}/{s}"]
            t, src = f"{TAG[a]}_{s}", f"{R} cases['{a}/{s}']"
            ms = c["methods"]
            for m in METHODS:
                v = ms[m]
                put(f"hv_{t}_{m}", v["hv_mean"], "{:.2f}", src + f".methods.{m}.hv_mean")
                put(f"hvci_{t}_{m}", v["hv_ci95_half"], "{:#.2g}", src + f".methods.{m}.hv_ci95_half")
                put(f"igd_{t}_{m}", v["igd_plus_mean"], "{:.4f}", src + f".methods.{m}.igd_plus_mean")
                put(f"igdci_{t}_{m}", v["igd_plus_ci95_half"], "{:#.2g}", src + f".methods.{m}.igd_plus_ci95_half")
                put(f"n95_{t}_{m}", str(v["calls_to_95pct_best_median"]), "{}", src + f".methods.{m}.calls_to_95pct_best_median")
            for key, name in (("q1", "q1v"), ("q1_igd", "q1i")):
                wins = [k.split(">") for k, b in c[key].items() if b]
                put(f"{name}_{t}", ", ".join(f"{SHORT[x]}>{SHORT[y]}" for x, y in wins) or "no separation", "{}", src + f".{key}")
            q = c["q2"]
            put(f"front_{t}", q["front_size"], "{:d}", src + ".q2.front_size")
            put(f"gpce_{t}", q["gap_pce_points"], "{:.3f}", src + ".q2.gap_pce_points")
            put(f"gcost_{t}", q["gap_cost_pct"], "{:.1f}", src + ".q2.gap_cost_pct")
            put(f"rho_{t}", q["spearman_pce_usd_pooled"], "{:.2f}", src + ".q2.spearman_pce_usd_pooled")
            WORD = {"one_material_set_dominates": "one set dominates", "near_identical_materials": "near-identical",
                    "cost_differs_efficiency_practically_equal": "cost differs only", "material_trade_off_exists": "trade-off"}
            put(f"word_{t}", WORD[q["wording"]], "{}", src + ".q2.wording")
            for end, e in (("pce_optimal", "P"), ("cost_optimal", "C")):
                dd = q[end]
                put(f"combo_{t}_{e}", dd["combo"].replace("NiOx", "NiO$_x$"), "{}", src + f".q2.{end}.combo")
                put(f"mpce_{t}_{e}", dd["module_pce_pct"], "{:.2f}", src + f".q2.{end}.module_pce_pct")
                put(f"usd_{t}_{e}", dd["usd_per_W"], "{:.3f}", src + f".q2.{end}.usd_per_W")
                put(f"cpce_{t}_{e}", dd["cell_pce_pct"], "{:.2f}", src + f".q2.{end}.cell_pce_pct")
                for n, val in dd["x"].items():
                    put(f"x_{t}_{e}_{n}", val, "{:g}", src + f".q2.{end}.x.{n}")
            hvg.append(100 * (ms["mixbo"]["hv_mean"] / ms["random"]["hv_mean"] - 1))
            hvgn.append(100 * (ms["mixbo"]["hv_mean"] / ms["nsga2"]["hv_mean"] - 1))
            put(f"dhv_{t}", hvg[-1], "{:.1f}", src + " 100*(hv_mean[mixbo]/hv_mean[random]-1)")
            c95b.append(ms["mixbo"]["calls_to_95pct_best_median"])
            share_b.append(100 * (ms["mixbo"]["call_share_by_combo"]["NiOx/Cu"] + ms["mixbo"]["call_share_by_combo"]["NiOx/Ag"]))
            share_r.append(100 * (ms["random"]["call_share_by_combo"]["NiOx/Cu"] + ms["random"]["call_share_by_combo"]["NiOx/Ag"]))
            gp.append(q["gap_pce_points"]); gc.append(q["gap_cost_pct"]); rho.append(q["spearman_pce_usd_pooled"])
            igd_b.append(ms["mixbo"]["igd_plus_mean"])
            for mt in ("Cu", "Ag"):
                padv.append(c["q4"]["by_metal"][mt]["ptaa_pce_advantage_points"])
            pc = q["per_combo"]
            au_min = min(v["min_usd_per_W"] for k, v in pc.items() if k.endswith("/Au"))
            au_ratio.append(au_min / pc["NiOx/Cu"]["min_usd_per_W"])
            au_dpce.append(abs(max(v["best_pce"] for k, v in pc.items() if k.endswith("/Au")) - pc["NiOx/Cu"]["best_pce"]))
            put(f"aumin_{t}", au_min, "{:.1f}", src + ".q2.per_combo min Au min_usd_per_W")
    src = f"{R} over the 6 cases"
    rng("dhv", hvg, "{:.1f}", src + " 100*(hv_mean[mixbo]/hv_mean[random]-1)")
    rng("dhvn", hvgn, "{:.1f}", src + " 100*(hv_mean[mixbo]/hv_mean[nsga2]-1)")
    rng("n95b", [int(x) for x in c95b], "{:d}", src + " mixbo calls_to_95pct_best_median")
    rng("shareb", share_b, "{:.0f}", src + " mixbo call share NiOx/Cu + NiOx/Ag (%)")
    rng("sharer", share_r, "{:.0f}", src + " random call share NiOx/Cu + NiOx/Ag (%)")
    rng("gpce", gp, "{:.2f}", src + " q2.gap_pce_points")
    rng("gcost", gc, "{:.0f}", src + " q2.gap_cost_pct")
    rng("rho", rho, "{:.2f}", src + " q2.spearman_pce_usd_pooled")
    rng("ptaadef", [-x for x in padv], "{:.2f}", src + " -q4.by_metal.*.ptaa_pce_advantage_points (NiOx lead)")
    rng("auratio", au_ratio, "{:.0f}", src + " min Au USD/W / min NiOx/Cu USD/W")
    put("audpce_max", max(au_dpce), "{:.3f}", src + " max |best Au PCE - best NiOx/Cu PCE|")
    put("igdb_max", max(igd_b), "{:.4f}", src + " max mixbo igd_plus_mean")
    fronts = [res["cases"][f"{a}/{s}"]["q2"]["front_size"] for a in ARCHS for s in SCENS]
    rng("front", fronts, "{:d}", src + " q2.front_size")
    q3 = res["q3"]
    for a in ARCHS:
        for k in ("q1_robust", "q1_igd_robust", "materials_robust"):
            put(f"q3_{TAG[a]}_{k}", "yes" if q3[a][k] else "no", "{}", f"{R} q3.{a}.{k}")
    # --- S-WF
    rows = [v for c in swf["cases"].values() for v in c["rows"].values()]
    put("swf_ok", sum(v["metal_wf_status"] == "complete" for v in rows), "{:d}", "phase0/paperB/swf.json complete rows")
    put("swf_n", len(rows), "{:d}", "phase0/paperB/swf.json rows")
    pa = [swf["cases"][s]["rows"]["PTAA/Au"] for s in SCENS]
    rng("swf_auloss", [v["B2"][0] - v["metal_wf"][0] for v in pa], "{:.1f}", "swf.json PTAA/Au B2 - metal_wf module PCE")
    wn = swf["cases"]["worse"]["rows"]
    rng("swf_worse_cuag", [wn["NiOx/Cu"]["metal_wf"][0], wn["NiOx/Ag"]["metal_wf"][0]], "{:.1f}",
        "swf.json worse NiOx/Cu, NiOx/Ag metal_wf module PCE")
    # --- POST-HOC (external review 2026-10-01): phase0/paperB/posthoc.json, SI Note S16
    ph = json.loads((PB / "posthoc.json").read_text())
    S16 = "phase0/paperB/posthoc.json (POST-HOC, not pre-registered)"
    p1 = [r for r in ph["p1"] if r.get("lead_same_contact") is not None]
    put("ph_n", len(ph["p1"]), "{:d}", S16 + " p1 rows")
    rng("ph_contact", [r["contact_part"] for r in p1], "{:.2f}", S16 + " p1 contact_part (module PCE points)")
    put("ph_ahead", sum(r["lead_same_contact"] > 0 for r in p1), "{:d}", S16 + " p1 count lead_same_contact > 0")
    put("ph_notahead", sum(r["lead_same_contact"] <= 0 for r in p1), "{:d}", S16 + " p1 count lead_same_contact <= 0")
    worse = [r for r in p1 if r["scenario"] == "worse"]
    put("ph_worse_contact_lo", min(r["contact_part"] for r in worse), "{:.2f}", S16 + " p1 worse contact_part (min)")
    put("ph_worse_contact_hi", max(r["contact_part"] for r in worse), "{:.2f}", S16 + " p1 worse contact_part (max)")
    exc = [r for r in p1 if r["lead_same_contact"] <= 0]
    put("ph_exc_contact_lo", min(r["contact_part"] for r in exc), "{:.2f}", S16 + " p1 contact_part over the exceptions (lead_same_contact <= 0), min")
    put("ph_exc_contact_hi", max(r["contact_part"] for r in exc), "{:.2f}", S16 + " p1 contact_part over the exceptions, max")
    if not all(r["scenario"] == "worse" for r in exc):
        raise SystemExit("an exception lies outside the worse scenarios: rewrite the Results sentence")
    pr = ph["p2_prices"]
    for m in ("Ag", "Au"):
        put(f"ph_{m}_min", pr[m]["min"], "{:,.1f}" if m == "Ag" else "{:,.0f}", S16 + f" p2_prices.{m}.min (verified Pink Sheet cells)")
        put(f"ph_{m}_max", pr[m]["max"], "{:,.1f}" if m == "Ag" else "{:,.0f}", S16 + f" p2_prices.{m}.max (verified Pink Sheet cells)")
    put("ph_ncells", len(pr["Ag"]["values"]), "{:d}", S16 + " p2_prices.Ag.values count")
    yrs = [int(y) for y in __import__("re").findall(r"20\d\d", pr["Ag"]["header"])]
    put("ph_y0", min(yrs), "{:d}", S16 + " p2_prices.Ag.header first year (Pink Sheet columns)")
    put("ph_y1", max(yrs), "{:d}", S16 + " p2_prices.Ag.header last year (Pink Sheet columns)")
    cor = ph["p2_corners"]
    same = all(v["combos"] == res["cases"][k]["q2"]["combos_on_front"] and v["wording"] == res["cases"][k]["q2"]["wording"]
               for c in cor.values() for k, v in c["cases"].items())
    put("ph_same", "yes" if same else "no", "{}", S16 + " fronts and wording identical at all price corners")
    if not same:
        raise SystemExit("price corners changed a front or a wording: rewrite the text before using these tokens")
    for name in ("silver_min", "silver_max"):
        g = [v["gap_cost_pct"] for v in cor[name]["cases"].values()]
        rng(f"ph_{name}_gcost", g, "{:.0f}", S16 + f" p2_corners.{name} gap_cost_pct")
    sc = [v["factor_gap_becomes_not_small"] for v in ph["p2_scan"]["cases"].values()]
    rng("ph_scan", [100 * x for x in sc], "{:.0f}", S16 + " p2_scan factor_gap_becomes_not_small (x100, % of base silver cost)")
    # --- POST-HOC (citation review 2026-10-02): phase0/paperB/posthoc_moox.json, SI Note S16 (interlayer cost bound)
    mx = json.loads((PB / "posthoc_moox.json").read_text())
    S16m = "phase0/paperB/posthoc_moox.json (POST-HOC, not pre-registered)"
    mc = mx["cases"].values()
    if not all(v["no_interlayer"]["combos"] == v["after_breakeven"]["combos"] for v in mc):
        raise SystemExit("the interlayer bound changes the front materials: rewrite the interlayer sentences")
    if not all(v["after_breakeven"]["wording"] == "near_identical_materials" for v in mc):
        raise SystemExit("the first wording change at the break-even is not 'near-identical': rewrite the text")
    put("mx_nm", mx["layer"]["thickness_nm"], "{:.0f}", S16m + " layer.thickness_nm")
    put("mx_gm2", mx["layer"]["g_per_m2"], "{:.2f}", S16m + " layer.g_per_m2")
    put("mx_k", mx["illustrative"]["k_total_usd_m2"], "{:.2f}", S16m + " illustrative.k_total_usd_m2")
    put("mx_usdg", mx["illustrative"]["moo3_usd_per_g_usgs_2025e"], "{:.3f}", S16m + " illustrative.moo3_usd_per_g_usgs_2025e (USGS 2026)")
    rng("mx_addw", [v["illustrative_add_usd_per_W_cheapest_cu"] for v in mc], "{:.4f}", S16m + " illustrative_add_usd_per_W_cheapest_cu")
    rng("mx_addpct", [v["illustrative_add_pct_cheapest_cu"] for v in mc], "{:.1f}", S16m + " illustrative_add_pct_cheapest_cu")
    rng("mx_be", [v["breakeven_usd_m2"] for v in mc], "{:.0f}", S16m + " breakeven_usd_m2")
    rng("mx_beg", [v["breakeven_usd_per_g_moo3"] for v in mc], "{:.0f}", S16m + " breakeven_usd_per_g_moo3")
    rng("mx_ratio", [v["breakeven_over_illustrative"] for v in mc], "{:.0f}", S16m + " breakeven_over_illustrative")
    # --- cross-study comparison (post-hoc)
    A = json.loads((REPO / "phase0" / "paperA" / "result.json").read_text())
    nipA = A["cases"]["n-i-p/base"]["q2"]["pce_optimal"]["usd_per_W"]
    nipB = res["cases"]["n-i-p/base"]["q2"]["cost_optimal"]["usd_per_W"]
    put("x_nip_ratio", nipA / nipB, "{:.0f}", "Paper A n-i-p/base pce_optimal usd_per_W / Paper B n-i-p/base cost_optimal usd_per_W")
    # merge with Paper A tokens
    NA = json.loads((PA / "numbers.json").read_text(encoding="utf-8"))
    clash = set(NA) & set(N)
    if clash:
        raise SystemExit(f"token clash {clash}")
    NA.update(N)
    (OUT / "numbers.json").write_text(json.dumps(NA, indent=1), encoding="utf-8")
    (OUT / "numbers_si.json").write_text((PA / "numbers_si.json").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"{len(N)} Study-2 tokens + {len(NA) - len(N)} Study-1 tokens -> {OUT / 'numbers.json'}")
    for k in sorted(N):
        if not k.startswith(("b_hv_", "b_hvci_", "b_igd", "b_n95_", "b_x_", "b_q1", "b_cpce", "b_combo", "b_mpce", "b_usd", "b_word", "b_front_", "b_gpce_", "b_gcost_", "b_rho_", "b_dhv_", "b_aumin")):
            print(k, N[k]["value"])


if __name__ == "__main__":
    main()
