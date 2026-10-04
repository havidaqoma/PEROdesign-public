"""Paper A numbers: every value the manuscript prints, each with the artifact it came from.
  python scripts/paperA_numbers.py      (run in the WSL venv; it imports the optimiser and reads the results)
-> paper/paperA/numbers.json   {token: {"value": <printed string>, "raw": <number or str>, "source": <path/key>}}
The manuscript uses only {{token}}s for results; scripts/paperA_build.py refuses untraced numerals."""
import json
import sys
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from perodesign.optim import objective as O  # noqa: E402
from perodesign.optim import search as S  # noqa: E402

A = REPO / "phase0" / "paperA"
N = {}
SCENS, ARCHS, METHODS = ("base", "worse", "better"), ("p-i-n", "n-i-p"), ("random", "nsga2", "qnehvi")
TAG = {"p-i-n": "pin", "n-i-p": "nip"}


def put(tok, raw, fmt, source):
    if tok in N:
        raise KeyError(f"duplicate token {tok}")
    if fmt == "SCI":                                   # LaTeX math, e.g. $3.16\times10^{20}$ or $10^{-4}$
        import math
        e = math.floor(math.log10(abs(raw)))
        m = raw / 10 ** e
        val = f"$10^{{{e}}}$" if abs(m - 1) < 1e-9 else f"${m:.3g}\\times10^{{{e}}}$"
    else:
        val = fmt.format(raw) if not isinstance(raw, str) else raw
    N[tok] = {"value": val, "raw": raw, "source": source}


def main():
    res = json.loads((A / "result.json").read_text())
    runs = {p.stem: json.loads(p.read_text()) for p in sorted((A / "runs").glob("*.json"))}
    src_r = "phase0/paperA/result.json"
    # --- design constants (code)
    put("budget", S.BUDGET, "{:d}", "perodesign/optim/search.py BUDGET")
    put("ninit", S.N_INIT, "{:d}", "perodesign/optim/search.py N_INIT")
    put("q", S.Q, "{:d}", "perodesign/optim/search.py Q")
    put("pop", S.POP, "{:d}", "perodesign/optim/search.py POP")
    put("ngen", S.BUDGET // S.POP, "{:d}", "BUDGET / POP")
    put("nbatch", (S.BUDGET - S.N_INIT) // S.Q, "{:d}", "(BUDGET - N_INIT) / Q")
    put("nseeds", 5, "{:d}", "scripts/paperA_run.py SEEDS")
    put("nruns", len(runs), "{:d}", "phase0/paperA/runs/*.json count")
    ncalls = sum(len(r["calls"]) for r in runs.values())
    put("ncalls", ncalls, "{:,}", "sum of calls over runs/*.json")
    put("stripe_lo", O.STRIPE_MM[0], "{:g}", "objective.STRIPE_MM")
    # analysis-rule constants (docs/PaperA_preregistration.md §7)
    put("ci_level", 95, "{:d}", "prereg §7 (95% t CI)")
    put("t_df", 4, "{:d}", "prereg §7 (5 seeds -> 4 d.o.f.)")
    put("hv_frac", 95, "{:d}", "prereg §7 calls-to-95%")
    put("small_pce", 1, "{:d}", "prereg §7 small-gap line (points)")
    put("small_cost", 5, "{:d}", "prereg §7 small-gap line (%)")
    put("unrel_calls", 12, "{:d}", "prereg §7 unreliable rule (calls)")
    put("unrel_pct", 5, "{:d}", "prereg §7 unreliable rule (%)")
    put("robust_move", 20, "{:d}", "prereg §7 design robustness (% of absorber range)")
    put("max_ptco_pct", 15, "{:d}", "perodesign/module MAX_P_TCO = 0.15")
    put("nt_worse", O.SCENARIOS["worse"]["N_t_bulk_m3"], "SCI", "objective.SCENARIOS")
    put("bo_restarts", 4, "{:d}", "search.run_qnehvi restarts")
    put("bo_raw", 256, "{:d}", "search.run_qnehvi raw")
    put("bo_mc", 64, "{:d}", "search.run_qnehvi mc")
    put("incident_w", __import__("perodesign.tea", fromlist=["x"]).INCIDENT_W_M2, "{:g}", "perodesign/tea INCIDENT_W_M2")
    put("round_nm", 0.1, "{:g}", "objective.design round(t, 1)")
    put("round_mm", 0.01, "{:g}", "objective.design round(stripe, 2)")
    put("nworkers", 12, "{:d}", "scripts/paperA_run.py run 12 (launch log)")
    put("stripe_hi", O.STRIPE_MM[1], "{:g}", "objective.STRIPE_MM")
    put("dead_mm", O.DEAD_MM, "{:g}", "objective.DEAD_MM")
    put("tco_ohm", O.TCO_OHM_SQ, "{:g}", "objective.TCO_OHM_SQ")
    put("edge_pct", 100 * O.EDGE, "{:g}", "objective.EDGE")
    put("pce_floor", O.PCE_FLOOR, "{:g}", "objective.PCE_FLOOR")
    put("ptaa_density", O.ASM["density:PTAA"]["g_cm3"], "{:g}", "objective.ASM")
    put("nt_lib", O.LIB_NT, "SCI", "materials_v2.yaml MAPbI3 N_t_bulk_m3")
    put("mu_lib", O.LIB_MU, "SCI", "materials_v2.yaml MAPbI3 mu_n_m2_Vs")
    for a in ARCHS:
        sp = O.space(a)
        put(f"dim_{TAG[a]}", sp.dim, "{:d}", "objective.space(arch).dim")
        ref = O.reference_point(a)
        put(f"refcost_{TAG[a]}", ref[1], "{:.3g}" if ref[1] > 10 else "{:.3f}", "objective.reference_point")
        for n, lo, hi in zip(sp.names, sp.lo, sp.hi):
            put(f"lo_{TAG[a]}_{n}", lo, "{:g}", "materials_v2.yaml thickness_nm / STRIPE_MM")
            put(f"hi_{TAG[a]}_{n}", hi, "{:g}", "materials_v2.yaml thickness_nm / STRIPE_MM")
    for pkg in ("botorch", "pymoo", "torch", "scipy", "numpy", "SALib"):
        put(f"ver_{pkg.lower()}", metadata.version(pkg), "{}", f"importlib.metadata.version('{pkg}') in the run venv")
    put("ver_simss", __import__("perodesign.physics.simss", fromlist=["x"]).SIMSS_VERSION, "{}", "perodesign/physics/simss.py SIMSS_VERSION")
    line = O.cost_line()
    for k, fm in (("capex_usd", "{:,.0f}"), ("throughput_m2_per_yr", "{:,.0f}"), ("depreciation_years", "{:g}"),
                  ("yield_fraction", "{:.2f}"), ("other_opex_usd_per_m2", "{:.2f}")):
        put(f"line_{k}", getattr(line, k).value, fm, f"objective.cost_line('MY').{k} ({getattr(line, k).tag[:60]})")
    for reg in ("MY", "CN", "IN"):
        put(f"rate_{reg}", 100 * O.cost_line(reg).rate.value, "{:.2f}", f"objective.cost_line('{reg}').rate (x100)")
    # --- P1 reference design and P2
    d, _ = O.design("p-i-n", O.REFERENCE["p-i-n"])
    put("p1_ref_usd", O.usd_per_W(d, 18.189336543476127)["usd_per_W"], "{:.3f}",
        "objective.usd_per_W(reference p-i-n, 18.189 %) = phase0/sim_bench/p1_my_bottom_up.json")
    p2 = json.loads((REPO / "phase0" / "sensitivity" / "result.json").read_text())
    put("p2_nsims", p2["n_unique_sims"], "{:,}", "phase0/sensitivity/result.json n_unique_sims")
    for k, tag in (("cell_pce_pct", "pce"), ("usd_per_W", "usd")):
        rk = p2["outputs"][k]["ranking"]
        for i in range(2):
            put(f"p2_{tag}_d{i + 1}", rk[i]["index"], "{:.3f}", f"phase0/sensitivity/result.json outputs.{k}.ranking[{i}]")
    # --- run-level
    simsec = [c["seconds"] for r in runs.values() for c in r["calls"] if c.get("seconds")]
    simsec.sort()
    put("sim_median_s", simsec[len(simsec) // 2], "{:.1f}", "median calls[].seconds (non-cached calls)")
    put("n_nocache", len(simsec), "{:,}", "calls with seconds > 0")
    ninf = sum(r["n_infeasible"] for r in runs.values())
    put("ninf_total", ninf, "{:d}", "sum runs/*.json n_infeasible")
    put("ninf_pct", 100 * ninf / ncalls, "{:.2f}", "ninf_total / ncalls")
    # --- POST-HOC explanation of the collapsed front (not in the pre-registration; labelled as such in the text)
    from scipy.stats import spearmanr
    for a in ("p-i-n", "n-i-p"):
        for s in ("base", "worse", "better"):
            t = f"{TAG[a]}_{s}"
            cs = [c for k, r in runs.items() if k.startswith(f"{a}__{s}__") for c in r["calls"] if c["feasible"]]
            mat = [c["materials_usd_m2"] for c in cs]
            pce = [c["module_pce_pct"] for c in cs]
            src = f"POST-HOC over feasible calls of phase0/paperA/runs/{a}__{s}__*.json"
            put(f"matlo_{t}", min(mat), "{:.2f}", src + " min materials_usd_m2")
            put(f"mathi_{t}", max(mat), "{:.2f}", src + " max materials_usd_m2")
            put(f"matspan_{t}", 100 * (max(mat) / min(mat) - 1), "{:.1f}", src + " 100*(max/min-1) materials_usd_m2")
            put(f"pcelo_{t}", min(pce), "{:.1f}", src + " min module_pce_pct")
            put(f"pcehi_{t}", max(pce), "{:.2f}", src + " max module_pce_pct")
            tot = [c["usd_per_W"] * c["module_pce_pct"] for c in cs]      # proportional to total cost per m2
            put(f"totspan_{t}", 100 * (max(tot) / min(tot) - 1), "{:.1f}", src + " 100*(max/min-1) of usd_per_W*module_pce_pct (total cost per m2)")
            put(f"pcefac_{t}", max(pce) / min(pce), "{:.2f}", src + " max/min module_pce_pct")
            put(f"rho_{t}", spearmanr(pce, [c["usd_per_W"] for c in cs]).statistic, "{:.3f}",
                src + " Spearman rho(module_pce_pct, usd_per_W)")
    p1 = json.loads((REPO / "phase0" / "sim_bench" / "p1_my_bottom_up.json").read_text())
    put("p1_ref_pce", p1["module_pce_pct"], "{:.2f}", "phase0/sim_bench/p1_my_bottom_up.json module_pce_pct")
    b = res["cases"]["p-i-n/base"]["q2"]["pce_optimal"]
    # POST-HOC (agy review): how far final HV is just "best PCE found" -- Spearman over the 15 runs of each case
    rhos = []
    for a in ("p-i-n", "n-i-p"):
        for s in ("base", "worse", "better"):
            rr = [r for k, r in runs.items() if k.startswith(f"{a}__{s}__")]
            best = [max(c["module_pce_pct"] for c in r["calls"] if c["feasible"]) for r in rr]
            rhos.append(spearmanr(best, [r["hv_final"] for r in rr]).statistic)
    put("hvpce_rho_min", min(rhos), "{:.2f}", "POST-HOC min over 6 cases of Spearman(best feasible module PCE of run, hv_final), 15 runs each")
    put("hvpce_rho_max", max(rhos), "{:.2f}", "POST-HOC max over 6 cases of the same Spearman")
    from perodesign.tea import load_cost_library, _v
    lib = load_cost_library()
    put("liu_capacity_mw", _v(lib, "liu_capacity", "MW"), "{:g}", "cost_library_v1.yaml liu_capacity")
    put("liu_module_eff", _v(lib, "liu_module_eff", "percent"), "{:g}", "cost_library_v1.yaml liu_module_eff")
    put("maint_pct", _v(lib, "kajal_maintenance_frac", "percent"), "{:g}", "cost_library_v1.yaml kajal_maintenance_frac")
    put("rear_ito_nm", 300, "{:d}", "cost_library_v1.yaml liu_ito_vol 0.3 cm3/m2 = 300 nm (Liu stack ITO 300 nm; tea bom ITO_rear_electrode)")
    put("pce_domain_hi", 40, "{:d}", "objective.evaluate: module PCE must lie in (0, 40) (tea.cost_per_watt domain)")
    put("runs_per_case", 15, "{:d}", "3 methods x 5 seeds per stack and scenario")
    put("cai_staff", _v(lib, "cai_line_employees", "count"), "{:g}", "cost_library_v1.yaml cai_line_employees")
    for n_, v_ in zip(O.space("p-i-n").names, O.REFERENCE["p-i-n"]):
        put(f"ref_pin_{n_}", v_, "{:g}", "objective.REFERENCE['p-i-n'] (P1 reference design)")
    put("materials_pin_base_P", b["materials_usd_m2"], "{:.2f}", "result.json cases.p-i-n/base.q2.pce_optimal.materials_usd_m2")
    put("ratio_nip_pin", res["cases"]["n-i-p/base"]["q2"]["pce_optimal"]["usd_per_W"] / b["usd_per_W"], "{:.0f}",
        "result.json n-i-p/base pce_optimal usd_per_W / p-i-n/base pce_optimal usd_per_W")
    put("gain_pin_pce", b["module_pce_pct"] - p1["module_pce_pct"], "{:.2f}", "result p-i-n/base pce_optimal - p1 reference module PCE")
    put("gain_pin_usd", 100 * (1 - b["usd_per_W"] / O.usd_per_W(d, 18.189336543476127)["usd_per_W"]), "{:.0f}",
        "100*(1 - p-i-n/base optimum USD/W / reference-design USD/W)")
    # --- cases
    for a in ARCHS:
        for s in SCENS:
            c = res["cases"][f"{a}/{s}"]
            t = f"{TAG[a]}_{s}"
            src = f"{src_r} cases['{a}/{s}']"
            for m in METHODS:
                v = c["methods"][m]
                fm = "{:.3f}" if v["hv_mean"] < 100 else "{:.1f}"
                put(f"hv_{t}_{m}", v["hv_mean"], fm, src + f".methods.{m}.hv_mean")
                put(f"hvci_{t}_{m}", v["hv_ci95_half"], "{:.0f}" if v["hv_ci95_half"] >= 10 else "{:#.2g}", src + f".methods.{m}.hv_ci95_half")
                put(f"n95_{t}_{m}", str(v["calls_to_95pct_best_median"]), "{}", src + f".methods.{m}.calls_to_95pct_best_median")
                put(f"inf_{t}_{m}", sum(v["n_infeasible"]), "{:d}", src + f".methods.{m}.n_infeasible (sum of 5)")
            q = c["q2"]
            NAME = {"random": "random", "nsga2": "NSGA-II", "qnehvi": "qNEHVI"}
            SHORT = {"random": "R", "nsga2": "N", "qnehvi": "Q"}
            wins = [k.split(">") for k, b in c["q1"].items() if b]
            put(f"q1v_{t}", ", ".join(f"{SHORT[a_]}>{SHORT[b_]}" for a_, b_ in wins) or "no separation", "{}", src + ".q1")
            put(f"unrel_{t}", "yes" if c["unreliable"] else "no", "{}", src + ".unreliable")
            put(f"small_{t}", "yes" if q["gap_small"] else "no", "{}", src + ".q2.gap_small")
            best = max(METHODS, key=lambda m: c["methods"][m]["hv_mean"])
            put(f"best_{t}", NAME[best], "{}", src + " argmax hv_mean")
            for m in ("nsga2", "qnehvi"):
                put(f"dhv_{t}_{m}", 100 * (c["methods"][m]["hv_mean"] / c["methods"]["random"]["hv_mean"] - 1), "{:.2f}",
                    src + f" 100*(hv_mean[{m}]/hv_mean[random]-1)")
            put(f"front_{t}", q["front_size"], "{:d}", src + ".q2.front_size")
            put(f"nfeas_{t}", q["n_feasible_pooled"], "{:,}", src + ".q2.n_feasible_pooled")
            put(f"gpce_{t}", q["gap_pce_points"], "{:.3f}", src + ".q2.gap_pce_points")
            put(f"gcost_{t}", q["gap_cost_pct"], "{:.3f}", src + ".q2.gap_cost_pct")
            for end, e in (("pce_optimal", "P"), ("cost_optimal", "C")):
                dd = q[end]
                put(f"mpce_{t}_{e}", dd["module_pce_pct"], "{:.2f}", src + f".q2.{end}.module_pce_pct")
                put(f"cpce_{t}_{e}", dd["cell_pce_pct"], "{:.2f}", src + f".q2.{end}.cell_pce_pct")
                put(f"usd_{t}_{e}", dd["usd_per_W"], "{:.3f}" if dd["usd_per_W"] < 10 else "{:.2f}", src + f".q2.{end}.usd_per_W")
                put(f"usd4_{t}_{e}", dd["usd_per_W"], "{:.4f}" if dd["usd_per_W"] < 10 else "{:.3f}", src + f".q2.{end}.usd_per_W (table precision)")
                for n, val in dd["x"].items():
                    put(f"x_{t}_{e}_{n}", val, "{:g}", src + f".q2.{end}.x.{n}")
                for part, val in dd["parts_usd_per_W"].items():
                    put(f"part_{t}_{e}_{part}", val, "{:.3f}", src + f".q2.{end}.parts_usd_per_W.{part}")
                for reg, val in dd["usd_per_W_by_rate_region"].items():
                    put(f"rate_{t}_{e}_{reg}", val, "{:.3f}" if val < 10 else "{:.2f}", src + f".q2.{end}.usd_per_W_by_rate_region.{reg}")
    for a in ARCHS:
        q3 = res["q3"][a]
        for w, v in q3["absorber_move_frac_of_range"].items():
            put(f"move_{TAG[a]}_{w}", 100 * v, "{:.0f}", f"{src_r} q3.{a}.absorber_move_frac_of_range.{w} (x100)")
        for k in ("q1_same_in_all_scenarios", "some_method_beats_random_in_all", "q1_robust", "designs_robust"):
            put(f"q3_{TAG[a]}_{k}", "yes" if q3[k] else "no", "{}", f"{src_r} q3.{a}.{k}")
    out = REPO / "paper" / "paperA" / "numbers.json"
    out.write_text(json.dumps(N, indent=1), encoding="utf-8")
    print(f"{len(N)} tokens -> {out}")


if __name__ == "__main__":
    main()
