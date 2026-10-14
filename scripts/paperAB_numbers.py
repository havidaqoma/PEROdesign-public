"""Numbers for the merged manuscript (paper/paperAB). Study 1 = Paper A tokens (copied unchanged from
paper/paperA/numbers.json + numbers_si.json); Study 2 = Paper B tokens, prefix b_, computed here from
phase0/paperB/{result.json,swf.json,gate0.json,diag.json,pilot.json,runs/*.json} and the code.
Every entry carries its source. Run in the WSL venv (imports the optimiser and cost engine):
  python scripts/paperAB_numbers.py -> paper/paperAB/numbers.json, paper/paperAB/numbers_si.json
"""
import json
import math
import re
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
    # acquisition-optimiser options, read from both BO code paths (fixed materials and material choice) so the Methods
    # sentence cannot drift from the code
    opts = set()
    for f in ("search.py", "bo_step.py"):
        s = (REPO / "perodesign" / "optim" / f).read_text(encoding="utf-8")
        m = re.search(r'options=\{"batch_limit": (\d+), "maxiter": (\d+)\}', s)
        if not m or "prune_baseline=True" not in s:
            raise SystemExit(f"{f}: acquisition options or prune_baseline=True not found")
        opts.add((int(m.group(1)), int(m.group(2))))
    if len(opts) != 1:
        raise SystemExit(f"the two BO code paths use different acquisition options: {opts}")
    (bl, mi), = opts
    from perodesign.optim import search as SA
    put("ngen_off", SA.BUDGET // SA.POP - 1, "{:d}", "perodesign/optim/search.py BUDGET / POP - 1 (offspring generations)")
    lt = re.findall(r"L_TCO_m:\s*([0-9.eE+-]+)", (REPO / "perodesign" / "library" / "materials_v2.yaml").read_text(encoding="utf-8"))
    if len(lt) != 1:
        raise SystemExit(f"materials_v2.yaml: expected one L_TCO_m, found {lt}")
    put("front_ito_nm", round(float(lt[0]) * 1e9), "{:d}", "perodesign/library/materials_v2.yaml L_TCO_m (front ITO, optics)")
    put("bo_batchlimit", bl, "{:d}", "perodesign/optim/{search,bo_step}.py optimize_acqf options batch_limit")
    put("bo_maxiter", mi, "{:d}", "perodesign/optim/{search,bo_step}.py optimize_acqf options maxiter")
    # decision D1: dates of the two analysis plan commits and of the first upload (Malaysia time, UTC+8)
    from datetime import datetime, timedelta, timezone
    pv = json.loads((REPO / "docs" / "preregistration_provenance.json").read_text(encoding="utf-8"))

    def day(s):
        d = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8)))
        return f"{d.day} {d:%B %Y}"
    PV = "docs/preregistration_provenance.json (scripts/prereg_provenance.py)"
    put("prereg_a_date", day(pv["preregistration"]["thickness-only"]["date"]), "{}", PV + " preregistration.thickness-only.date")
    put("prereg_b_date", day(pv["preregistration"]["material-choice"]["date"]), "{}", PV + " preregistration.material-choice.date")
    put("upload_date", day(pv["github_first_upload"]["timestamp"]), "{}", PV + " github_first_upload.timestamp")
    put("ver_botorch", metadata.version("botorch"), "{}", "importlib.metadata in the run venv")
    put("ver_pymoo", metadata.version("pymoo"), "{}", "importlib.metadata in the run venv")
    put("nruns", len(runs), "{:d}", "phase0/paperB/runs/*.json count")
    put("ncalls", sum(len(r["calls"]) for r in runs.values()), "{:,}", "sum of calls over phase0/paperB/runs")
    put("calls_case", sum(len(r["calls"]) for r in runs.values()) // (len(ARCHS) * len(SCENS)), "{:,}",
        "sum of calls over phase0/paperB/runs / 6 cases")
    put("ninf", sum(r["n_infeasible"] for r in runs.values()), "{:d}", "sum n_infeasible over phase0/paperB/runs")
    put("ninf_max", max(r["n_infeasible"] for r in runs.values()), "{:d}", "max n_infeasible in one run")
    put("commit_prereg", "2b32a78", "{}", "git commit of docs/PaperB_preregistration.md before any run")
    arch = json.loads((REPO / "docs" / "archive.json").read_text(encoding="utf-8"))
    if not (arch["repository_url"].startswith("https://github.com/") and arch["concept_doi"].startswith("10.5281/zenodo.")):
        raise SystemExit("docs/archive.json: repository URL or Zenodo DOI missing or malformed")
    put("repo_url", arch["repository_url"], "{}", "docs/archive.json repository_url")
    put("repo_doi", arch["concept_doi"], "{}", "docs/archive.json concept_doi (Zenodo, all versions)")
    # --- gate G0 and diagnostics
    put("g0_n", len(g0["g0_checks"]), "{:d}", "phase0/paperB/gate0.json g0_checks")
    for d in g0["deltas"]:
        t = TAG[d["arch"]]
        put(f"g0_{t}_prod", d["production"]["module_pce_pct"], "{:.2f}", "gate0.json deltas production module_pce_pct")
        put(f"g0_{t}_b2", d["step2_b2_contacts"]["module_pce_pct"], "{:.2f}", "gate0.json deltas step2_b2_contacts module_pce_pct")
        put(f"g0_{t}_d", d["step2_b2_contacts"]["module_pce_pct"] - d["production"]["module_pce_pct"], "{:.2f}",
            "gate0.json step2 - production module_pce_pct")
    sds = [diag["d1"][a][m]["resid_sd_points"] for a in ARCHS for m in ("Cu", "Ag")]
    put("noise_sd", max(sds), "{:.4f}", "diag.json d1 max resid_sd_points (module PCE); 4 decimals so that b_snr (computed from the unrounded SD) checks against the printed value")
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
    # built-in voltage under the band-edge rule B2 with NiOx (panel review 2026-10-15): anode at the NiOx valence band,
    # cathode at the conduction band of the electron-transport layer of either stack (SnO2 n-i-p, C60 p-i-n)
    vbi = {e: pp("NiOx", "E_v_eV") - pp(e, "E_c_eV") for e in ("SnO2", "C60")}
    if len(set(vbi.values())) != 1:
        raise SystemExit(f"built-in voltage differs between the stacks {vbi}; the wording must name both")
    put("vbi_nio", vbi["SnO2"], "{:.2f}", "materials_v2 NiOx E_v_eV - E_c_eV of SnO2 and of C60 (equal; contact rule B2)")
    put("eg_abs", pp("MAPbI3", "E_v_eV") - pp("MAPbI3", "E_c_eV"), "{:.2f}", "materials_v2 MAPbI3 E_v_eV - E_c_eV")
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
    S16 = "phase0/paperB/posthoc.json (POST-HOC, not pre-specified)"
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
    S16m = "phase0/paperB/posthoc_moox.json (POST-HOC, not pre-specified)"
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
    # --- POST-HOC (pre-submission review 2026-10-08): bound of the PTAA exceptions (same contact, NiOx not re-optimised)
    neg = [-r["lead_same_contact"] for r in ph["p1"] if r["lead_same_contact"] < 0]
    put("ph_neg_hi", max(neg), "{:.2f}", S16 + " p1 max(-lead_same_contact) over rows with lead_same_contact < 0")
    # --- POST-HOC (pre-submission review 2026-10-08): spatial grid check, phase0/paperB/posthoc_mesh.json, SI Note S19
    me = json.loads((PB / "posthoc_mesh.json").read_text())
    S19 = "phase0/paperB/posthoc_mesh.json (POST-HOC, not pre-specified)"
    if not me["np250_reproduces_stored_exactly"] or me["failed_sims"]:
        raise SystemExit("grid check: NP=250 does not reproduce the stored values or a simulation failed")
    flips = me["material_reading_flips"]
    if sorted({f["case"] for f in flips}) != ["n-i-p/better"]:
        raise SystemExit(f"grid check: reading flips are not only n-i-p/better: {flips}; rewrite the grid sentences")
    np0, np1 = me["NP_values"][0], me["NP_values"][-1]
    put("mesh_np0", np0, "{:d}", S19 + " NP_values[0] (grid of every run)")
    put("mesh_np1", np1, "{:d}", S19 + " NP_values[-1] (SIMsalabim 5.36 maximum, Max_NP)")
    put("mesh_n", me["n_designs"], "{:d}", S19 + " n_designs (both front ends of all 12 cases)")
    put("mesh_dpce", me["max_abs_dpce_points_vs_np250"][str(np1)], "{:.2f}", S19 + f" max_abs_dpce_points_vs_np250['{np1}']")
    put("mesh_dcost", 100 * me["max_rel_dcost_vs_np250"][str(np1)], "{:.1f}", S19 + f" max_rel_dcost_vs_np250['{np1}'] (x100, %)")
    fr = {(f["level"], f["case"], f["NP"]): f for f in me["fronts"]}
    put("mesh_thick_gap", max(abs(f["gap_pce_points"]) for f in me["fronts"] if f["level"] == "thickness_only"), "{:.3f}",
        S19 + " max |gap_pce_points| over thickness_only fronts at every NP")
    for n in me["NP_values"][1:]:
        put(f"mesh_nipb_{n}", fr[("material_choice", "n-i-p/better", n)]["gap_pce_points"], "{:.2f}",
            S19 + f" fronts material_choice n-i-p/better NP={n} gap_pce_points")
    # --- POST-HOC (pre-submission review 2026-10-09): every pooled-front point re-simulated at three grids,
    # phase0/paperB/posthoc_mesh_front.json (scripts/paperAB_mesh_front.py), SI Note S19
    mf = json.loads((PB / "posthoc_mesh_front.json").read_text())
    S19f = "phase0/paperB/posthoc_mesh_front.json (POST-HOC, not pre-specified)"
    ms = mf["summary"]
    ffr = {(f["case"], f["NP"]): f for f in mf["fronts"]}
    if not ms["np250_reproduces_stored_exactly"]:
        raise SystemExit("full-front grid check: NP=250 does not reproduce the stored values")
    for (c, n), f in ffr.items():
        if n in (np0, np1) and (f["pce_end_combo"], f["cost_end_combo"]) != ("NiOx/Ag", "NiOx/Cu"):
            raise SystemExit(f"full-front grid check: {c} at NP {n} is no longer NiOx/Ag -> NiOx/Cu; rewrite the grid sentences")
    if sorted(ms["cases_above_line_by_np"][str(np1)]) != ["n-i-p/better", "n-i-p/worse", "p-i-n/worse"] or \
            sorted(ms["cases_above_line_by_np"][str(np0)]) != ["n-i-p/worse", "p-i-n/worse"]:
        raise SystemExit(f"full-front grid check: cases above the line changed {ms['cases_above_line_by_np']}")
    put("mf_n", ms["n_points"], "{:d}", S19f + " summary.n_points (all members of the six material-choice fronts)")
    put("mf_nsim", ms["n_sims"], "{:d}", S19f + " summary.n_sims")
    put("mf_gap_lo", ms["gap_range_by_np"][str(np1)][0], "{:.2f}", S19f + f" summary.gap_range_by_np['{np1}'][0]")
    put("mf_gap_hi", ms["gap_range_by_np"][str(np1)][1], "{:.2f}", S19f + f" summary.gap_range_by_np['{np1}'][1]")
    put("mf_dgap", max(abs(ffr[(c, np1)]["gap_pce_points"] - ffr[(c, np0)]["gap_pce_points"]) for c, n in ffr if n == np1),
        "{:.3f}", S19f + f" max over cases |gap(NP={np1}) - gap(NP={np0})| from fronts[*].gap_pce_points")
    put("mf_nipb", ffr[("n-i-p/better", np1)]["gap_pce_points"], "{:.2f}", S19f + f" fronts n-i-p/better NP={np1} gap_pce_points")
    npm = sorted({n for _, n in ffr if n not in (np0, np1)})
    no_ag = sorted(c for (c, n), f in ffr.items() if n in npm and "NiOx/Ag" not in f["combos_on_front"])
    if len(npm) != 1 or no_ag != ["n-i-p/better"]:
        raise SystemExit(f"full-front grid check: silver-free fronts at the middle grid changed {no_ag}; rewrite the grid sentence")
    put("mf_npmid", npm[0], "{:d}", S19f + " middle NP; the only front without NiOx/Ag there is n-i-p/better (fronts[*].combos_on_front)")
    # --- POST-HOC (pre-submission review 2026-10-09): stored-data analyses, phase0/paperB/posthoc_review.json
    # (scripts/paperAB_posthoc_review.py), SI Note S20
    pr = json.loads((PB / "posthoc_review.json").read_text())
    S20 = "phase0/paperB/posthoc_review.json (POST-HOC, not pre-specified)"
    pt = pr["r1_ptaa_nip_front"]
    if [(pt[s]["pce_end"]["metal"], pt[s]["cost_end"]["metal"]) for s in ("base", "worse", "better")] != \
            [("Ag", "Cu"), ("Ag", "Cu"), ("Au", "Cu")]:
        raise SystemExit("PTAA-only n-i-p front: end metals changed; rewrite the PTAA sentences")
    if not (pt["worse"]["above_0p2_line"] and not pt["base"]["above_0p2_line"] and not pt["better"]["above_0p2_line"]):
        raise SystemExit("PTAA-only n-i-p front: line classification changed; rewrite the PTAA sentences")
    rng("ptaa_n", [pt[s]["n_distinct"] for s in pt], "{:,}", S20 + " r1_ptaa_nip_front[*].n_distinct")
    for s in ("base", "worse", "better"):
        put(f"ptaa_gap_{s}", pt[s]["gap_pce_points"], "{:.3f}", S20 + f" r1_ptaa_nip_front.{s}.gap_pce_points")
    rng("ptaa_gcost", [pt[s]["gap_cost_pct"] for s in ("base", "worse")], "{:.0f}", S20 + " r1_ptaa_nip_front.{base,worse}.gap_cost_pct")
    put("ptaa_au_x", 1 + pt["better"]["gap_cost_pct"] / 100, "{:.0f}", S20 + " 1 + r1_ptaa_nip_front.better.gap_cost_pct/100")
    for lvl, tag in (("thickness_only", "a"), ("material_choice", "b")):
        rows = pr["r2_paired"][lvl]
        for r in rows:
            if r["nonoverlap_separates"] and not r["paired_separates"]:
                raise SystemExit(f"paired test fails to separate a pair the registered rule separates: {r}")
        put(f"pair_{tag}_n", len(rows), "{:d}", S20 + f" len(r2_paired.{lvl})")
        put(f"pair_{tag}_paired", sum(r["paired_separates"] for r in rows), "{:d}", S20 + f" r2_paired.{lvl} count paired_separates")
        put(f"pair_{tag}_reg", sum(r["nonoverlap_separates"] for r in rows), "{:d}", S20 + f" r2_paired.{lvl} count nonoverlap_separates")
    jv = [r for r in pr["r3_jv_pce_optimal"] if r["level"] == "material_choice"]
    rng("jv_voc", [r["voc_V"] for r in jv], "{:.2f}", S20 + " r3_jv_pce_optimal material_choice voc_V")
    rng("jv_ff", [r["ff"] for r in jv], "{:.2f}", S20 + " r3_jv_pce_optimal material_choice ff")
    rho_all = [v["all_feasible_calls"] for v in pr["r4_rho"]["material_choice"].values()]
    rng("rho_calls", rho_all, "{:.2f}", S20 + " r4_rho.material_choice[*].all_feasible_calls")
    # built-in voltage of rule B2 for the n-i-p NiOx stack, from the analysis plan text
    pre = (REPO / "docs" / "PaperB_preregistration.md").read_text(encoding="utf-8")
    m = re.search(r"n-i-p NiOx ([0-9.]+) V vs\s+PTAA ([0-9.]+) V", pre)
    if not m:
        raise SystemExit("PaperB_preregistration.md: built-in voltage sentence not found")
    put("vbi_nip_niox", float(m.group(1)), "{:.2f}", "docs/PaperB_preregistration.md rule B2 consequence: n-i-p NiOx built-in voltage (V)")
    put("vbi_nip_ptaa", float(m.group(2)), "{:.2f}", "docs/PaperB_preregistration.md rule B2 consequence: n-i-p PTAA built-in voltage (V)")
    if abs(float(m.group(1)) - vbi["SnO2"]) > 0.005:
        raise SystemExit(f"plan built-in voltage {m.group(1)} V differs from the library value {vbi['SnO2']:.2f} V")
    # --- POST-HOC (pre-submission review 2026-10-09): published precursor prices against the absorber-price scan,
    # phase0/paperB/posthoc_absorber_prices.json (scripts/paperAB_absorber_prices.py), SI Note S17
    ap = json.loads((PB / "posthoc_absorber_prices.json").read_text(encoding="utf-8"))
    S17p = "phase0/paperB/posthoc_absorber_prices.json (POST-HOC, not pre-specified)"
    sc, ch = ap["scan_pin_base"], ap["chang2017"]["MAPbI3_usd_per_g"]
    if not (ch["usd_per_g"] < sc["last_small_usd_per_g"] < sc["first_not_small_usd_per_g"] < ap["wu2026"]["usd_per_g"]):
        raise SystemExit("absorber prices: the production and laboratory prices no longer straddle the scan; rewrite")
    put("pvk_chang", ch["usd_per_g"], "{:.2f}", S17p + " chang2017.MAPbI3_usd_per_g.usd_per_g")
    put("pvk_chang_lo", ch["lo"], "{:.2f}", S17p + " chang2017.MAPbI3_usd_per_g.lo")
    put("pvk_chang_hi", ch["hi"], "{:.2f}", S17p + " chang2017.MAPbI3_usd_per_g.hi")
    put("pvk_wu", ap["wu2026"]["usd_per_g"], "{:.1f}", S17p + " wu2026.usd_per_g")
    put("pvk_lib", ap["library_usd_per_g"], "{:.2f}", S17p + " library_usd_per_g (cost_library_v1.yaml liu_perovskite_price)")
    put("pvk_x_small", sc["last_small_mult"], "{:d}", S17p + " scan_pin_base.last_small_mult")
    put("pvk_x_open", sc["first_not_small_mult"], "{:d}", S17p + " scan_pin_base.first_not_small_mult")
    put("pvk_small_usd", sc["last_small_usd_per_g"], "{:.2f}", S17p + " scan_pin_base.last_small_usd_per_g")
    put("pvk_open_usd", sc["first_not_small_usd_per_g"], "{:.2f}", S17p + " scan_pin_base.first_not_small_usd_per_g")
    # --- validation record (G1 step 2, round 2): the one testable measured n-i-p thickness series
    g1 = json.loads((REPO / "phase0" / "g1s2" / "round2" / "result_main.json").read_text(encoding="utf-8"))
    sv = [s for s in g1["series"] if s["n_ok"] >= 4]
    if len(sv) != 1:
        raise SystemExit(f"validation record: expected one eligible series, found {len(sv)}")
    G1 = "phase0/g1s2/round2/result_main.json series[eligible] (doi " + sv[0]["doi"] + ")"
    pts = sv[0]["points"]
    put("val_n", len(pts), "{:d}", G1 + " len(points)")
    rng("val_dpce", [p["sim"]["pce_pct"] - p["measured"]["pce"] for p in pts], "{:.1f}", G1 + " sim.pce_pct - measured.pce")
    # relative to the SIMULATED efficiency, the same base as the uniform-bias sensitivity below (panel review p12, qwen)
    vrel = [100 * (p["sim"]["pce_pct"] - p["measured"]["pce"]) / p["sim"]["pce_pct"] for p in pts]
    rng("val_rel", vrel, "{:.0f}", G1 + " 100*(sim.pce_pct - measured.pce)/sim.pce_pct")
    by_t = [v for _, v in sorted(zip([p["t"] for p in pts], vrel))]
    if any(b >= a for a, b in zip(by_t, by_t[1:])):
        raise SystemExit("validation bias no longer falls with absorber thickness; rewrite 'falling with thickness'")
    rng("val_jsc_sim", [p["sim"]["jsc_mA_cm2"] for p in pts], "{:.1f}", G1 + " sim.jsc_mA_cm2")
    rng("val_jsc_meas", [p["measured"]["jsc"] for p in pts], "{:.1f}", G1 + " measured.jsc")
    rng("val_voc_sim", [p["sim"]["voc_V"] for p in pts], "{:.2f}", G1 + " sim.voc_V")
    rng("val_voc_meas", [p["measured"]["voc"] for p in pts], "{:.2f}", G1 + " measured.voc")
    rng("val_ff_sim", [p["sim"]["ff"] for p in pts], "{:.2f}", G1 + " sim.ff")
    rng("val_ff_meas", [p["measured"]["ff"] for p in pts], "{:.2f}", G1 + " measured.ff")
    # pre-specified verdict of that validation, both rounds (panel review 2026-10-15): reported, never re-judged
    g1r1 = json.loads((REPO / "phase0" / "g1s2" / "result_main.json").read_text(encoding="utf-8"))
    for lab, d in (("round 1", g1r1), ("round 2", g1)):
        if d["summary"]["verdict"] != "NO-GO" or d["summary"]["adds_no_information_beyond_thickness"] is not True:
            raise SystemExit(f"validation {lab}: verdict changed; the manuscript wording must be revisited")
    req = [k for k in g1["summary"]["criteria"] if k.startswith("n_eligible_ge_")]
    if len(req) != 1:
        raise SystemExit("validation record: cannot read the required number of eligible series")
    S2, S1 = "phase0/g1s2/round2/result_main.json", "phase0/g1s2/result_main.json"
    put("val_req", int(req[0].rsplit("_", 1)[1]), "{:d}", S2 + " summary.criteria." + req[0])
    put("val_nsel", g1["summary"]["n_series_selected"], "{:d}", S2 + " summary.n_series_selected")
    put("val_elig_r1", g1r1["summary"]["n_eligible"], "{:d}", S1 + " summary.n_eligible")
    put("val_elig_r2", g1["summary"]["n_eligible"], "{:d}", S2 + " summary.n_eligible")
    put("val_rho_sim", sv[0]["rho_sim"], "{:.2f}", G1 + " rho_sim")
    put("val_rho_base", sv[0]["rho_base"], "{:.2f}", G1 + " rho_base")
    put("val_rho_voc", sv[0]["rho_voc"], "{:.2f}", G1 + " rho_voc")
    put("val_rho_ff", sv[0]["rho_ff"], "{:.2f}", G1 + " rho_ff")
    put("val_r1_rho_sim", g1r1["summary"]["mean_rho_sim"], "{:.2f}", S1 + " summary.mean_rho_sim")
    put("val_r1_rho_base", g1r1["summary"]["mean_rho_base"], "{:.2f}", S1 + " summary.mean_rho_base")
    # --- uniform-bias sensitivity of the 0.2-point line (pre-submission review 2026-10-08): the efficiency reduction
    # (%) at which each poor-absorber gap, scaled with every efficiency, falls under DPCE_MIN
    line = float(N["b_dpce_min"]["raw"])
    bias = {a: 100 * (1 - line / res["cases"][f"{a}/worse"]["q2"]["gap_pce_points"]) for a in ARCHS}
    put("bias_lo", bias["n-i-p"], "{:.0f}", R + " 100*(1 - DPCE_MIN / cases['n-i-p/worse'].q2.gap_pce_points)")
    put("bias_hi", bias["p-i-n"], "{:.0f}", R + " 100*(1 - DPCE_MIN / cases['p-i-n/worse'].q2.gap_pce_points)")
    if not bias["n-i-p"] < bias["p-i-n"]:
        raise SystemExit("bias tokens: n-i-p is no longer the lower value; rewrite the sentence")
    # the measured bias falls with thickness, so compare it at the thickness of the poor-absorber end designs
    # (final agy check, p12): only the thinnest measured cell exceeds the n-i-p value; at the end-design thickness
    # linear interpolation between the measured cells gives less; every measured cell stays below the p-i-n value
    tv = sorted(zip([p["t"] for p in pts], vrel))
    over = [t for t, v in tv if v >= bias["n-i-p"]]
    q2n = res["cases"]["n-i-p/worse"]["q2"]
    t_end = (q2n["pce_optimal"]["x"]["MAPbI3_nm"] + q2n["cost_optimal"]["x"]["MAPbI3_nm"]) / 2
    k = next(i for i in range(len(tv) - 1) if tv[i][0] <= t_end <= tv[i + 1][0])
    (t0, v0), (t1, v1) = tv[k], tv[k + 1]
    v_end = v0 + (v1 - v0) * (t_end - t0) / (t1 - t0)
    if not (over == [tv[0][0]] and v_end < bias["n-i-p"] and max(vrel) < bias["p-i-n"]):
        raise SystemExit(f"validation bias by thickness {tv} vs thresholds {bias} (end design {t_end:.0f} nm: "
                         f"{v_end:.1f}%): rewrite the n-i-p/p-i-n bias sentences")
    put("val_t_thin", tv[0][0], "{:.0f}", G1 + " thinnest measured cell, points[].t (nm)")
    put("val_t_end_nip", t_end, "{:.0f}", R + " mean MAPbI3_nm of cases['n-i-p/worse'].q2 pce_optimal and cost_optimal")
    put("val_rel_end_nip", v_end, "{:.0f}", G1 + " relative bias linearly interpolated in t at val_t_end_nip")
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
