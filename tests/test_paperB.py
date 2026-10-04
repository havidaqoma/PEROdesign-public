"""Paper B: objective_b / search_b / overlay tests (no optimiser run against SimSS here)."""
import math

import pytest

from perodesign.library import load_library
from perodesign.optim import objective as A
from perodesign.optim import objective_b as B
from perodesign.optim import search_b as S
from perodesign.schema import validate
from perodesign.tea import back_electrode_cost, load_cost_library, TROY_OZ_G


def test_production_mode_returns_the_production_library_object():
    for arch, (htl, metal) in B.PRODUCTION_COMBO.items():
        assert B.physics_library(arch, htl, metal, "production", "production") is load_library()
    with pytest.raises(ValueError):
        B.physics_library("p-i-n", "PTAA", "Cu", "production", "production")


def test_overlay_does_not_touch_production_library():
    before = load_library()["_sha256"]
    lib = B.physics_library("p-i-n", "PTAA", "Ag")
    assert load_library()["_sha256"] == before
    assert "PTAA|MAPbI3" not in load_library()["interfaces"] and "PTAA|MAPbI3" in lib["interfaces"]
    assert lib["_sha256"] != before


def test_new_interfaces_copy_the_production_hole_side_values():
    prod = load_library()["interfaces"]["MAPbI3|PTAA"]["params"]
    ov = B.overlay()["interfaces"]
    for pair in ("PTAA|MAPbI3", "MAPbI3|NiOx"):
        assert ov[pair]["params"] == prod
        assert ov[pair]["provenance"]["status"] == "simss_default_transferred"


@pytest.mark.parametrize("arch", ["p-i-n", "n-i-p"])
def test_b2_contacts_are_band_edges(arch):
    lib = load_library()
    p = lambda m: lib["materials"][m]["params"]  # noqa: E731
    for htl in B.HTLS:
        wl, wr = B.b2_contacts(arch, htl)
        if arch == "n-i-p":
            assert (wl, wr) == (p("C60")["E_c_eV"], p(htl)["E_v_eV"])
        else:
            assert (wl, wr) == (p(htl)["E_v_eV"], p("SnO2")["E_c_eV"])
        s = B.physics_setup(B.physics_library(arch, htl, "Ag"), arch)
        assert (s["W_L_eV"], s["W_R_eV"]) == (wl, wr)


@pytest.mark.parametrize("arch", ["p-i-n", "n-i-p"])
@pytest.mark.parametrize("htl", ["NiOx", "PTAA"])
@pytest.mark.parametrize("metal", ["Cu", "Ag", "Au"])
def test_every_combination_is_valid_at_corners_and_costed_with_its_own_metal(arch, htl, metal):
    lib = B.physics_library(arch, htl, metal)
    s = B.physics_setup(lib, arch)
    assert s["nkBE_file"] == f"nk_{metal}_McPeak2015.txt"
    assert s["L_BE_m"] == B.overlay()["metal_thickness_m"][arch]
    for x in B.bounds(arch, htl):
        d, _ = B.design(arch, x, htl)
        validate(d, lib)
        c = B.usd_per_W(d, 20.0, lib)
        assert c["back_electrode_item"] == f"bom:back_electrode:{metal}"
        assert c["cost_status"] in ("sourced_with_proxies", "with_assumptions")


def test_silver_cost_from_sourced_values():
    """150 nm x 10.49 g/cm3 x 65.4 USD/toz / 31.1034768 g / 0.25, recomputed here."""
    lib = load_cost_library()
    s = B.physics_setup(B.physics_library("p-i-n", "NiOx", "Ag"), "p-i-n")
    be = back_electrode_cost(lib, architecture="p-i-n", physics_setup=s)
    want = 150 * 1e-3 * 10.49 * 65.4 / 31.1034768 / 0.25
    assert TROY_OZ_G == 31.1034768
    assert math.isclose(be["usd_m2"], want, rel_tol=1e-12)
    assert be["item"] == "bom:back_electrode:Ag"


def test_mcpeak_gold_costs_the_same_as_production_gold_at_equal_thickness():
    lib = load_cost_library()
    s = B.physics_setup(B.physics_library("n-i-p", "PTAA", "Au"), "n-i-p")
    assert math.isclose(back_electrode_cost(lib, architecture="n-i-p", physics_setup=s)["usd_m2"],
                        back_electrode_cost(lib, architecture="n-i-p")["usd_m2"], rel_tol=1e-12)


def test_default_cost_path_unchanged_without_physics_setup():
    """Paper A callers pass no physics_setup; the production answer must not move."""
    d, _ = A.design("p-i-n", A.REFERENCE["p-i-n"])
    assert math.isclose(A.usd_per_W(d, 18.189336543476127)["usd_per_W"], 0.42739665975133573, rel_tol=1e-12)


def test_htl_coordinate_maps_to_the_chosen_htl_bounds():
    sp = B.space("n-i-p")
    for hi, htl in enumerate(B.HTLS):
        x, h, _ = B.to_physical(sp, [0.0, 0.0, 1.0, 0.5], [hi, 0])
        assert h == htl and x[2] == load_library()["materials"][htl]["thickness_nm"]["max"]


def test_relaxed_decoding_edges():
    sp = B.space("p-i-n")
    assert B.decode_relaxed(sp, [0.5] * 5 + [0.0, 0.0])[1] == [0, 0]
    assert B.decode_relaxed(sp, [0.5] * 5 + [0.49, 0.34])[1] == [0, 1]
    assert B.decode_relaxed(sp, [0.5] * 5 + [1.0, 1.0])[1] == [1, 2]


def test_reference_point_is_the_worst_corner():
    pr, lc = B.reference_point("n-i-p")
    assert pr == A.PCE_FLOOR
    worst = max(B.usd_per_W(B.design("n-i-p", B.bounds("n-i-p", h)[1], h)[0], A.PCE_FLOOR,
                            B.physics_library("n-i-p", h, m))["usd_per_W"] for h in B.HTLS for m in B.METALS)
    assert math.isclose(lc, math.log10(worst))


def _fake(points):
    """Synthetic objective: PCE from the continuous coords, cost from the categories (no SimSS)."""
    out = []
    for uc, cats in points:
        if uc[0] > 0.97:
            out.append(None)
            continue
        out.append((20 - 5 * sum((v - 0.4) ** 2 for v in uc) + cats[0], math.log10(0.3 * (1 + 10 * cats[1]))))
    return out


@pytest.mark.parametrize("method", ["random", "nsga2"])
def test_methods_use_exact_budget_valid_categories_and_are_seeded(method):
    sp = B.space("p-i-n")
    ref = (5.0, 1.0)
    a = S.run_method(method, _fake, sp, 3, ref, budget=48)
    b = S.run_method(method, _fake, sp, 3, ref, budget=48)
    assert len(a) == 48 and a == b
    assert all(0 <= c < K for r in a for c, K in zip(r["cats"], sp.cat_sizes))
    assert all(len(r["u"]) == sp.n_cont and all(0 <= v <= 1 for v in r["u"]) for r in a)
    assert len({tuple(r["cats"]) for r in a}) >= 4        # explores the categories


def test_all_methods_share_the_first_24_points():
    sp = B.space("n-i-p")
    ra = S.run_method("random", _fake, sp, 1, (5.0, 1.0), budget=24)
    rn = S.run_method("nsga2", _fake, sp, 1, (5.0, 1.0), budget=24)
    assert [(r["u"], r["cats"]) for r in ra] == [(r["u"], r["cats"]) for r in rn]


@pytest.mark.slow
def test_mixbo_runs_on_the_fake_objective():
    sp = B.space("n-i-p")
    log = S.run_method("mixbo", _fake, sp, 0, (5.0, 1.0), budget=36)
    assert len(log) == 36
    assert all(0 <= c < K for r in log for c, K in zip(r["cats"], sp.cat_sizes))


def test_metal_work_functions_are_in_their_source():
    from pathlib import Path
    from perodesign.tea.provenance import canon
    wf = B.overlay()["metal_work_function_eV"]
    pv = wf["provenance"]
    txt = canon((Path(__file__).resolve().parents[1] / "data" / "sources" / pv["source"]).read_text(encoding="utf-8"))
    assert canon(pv["quote"]) in txt
    metals, vals = pv["quote"].split("Metal work function (eV)")
    cols = ["Au", "Ag", "Fe", "Cu", "Cu Doped C"]
    assert metals.strip().endswith("Au Ag Fe Cu Cu Doped C")
    got = dict(zip(cols, vals.split()))
    assert {m: float(got[m]) for m in B.METALS} == {m: wf[m] for m in B.METALS}


def test_metal_wf_sensitivity_sets_only_the_anode_and_only_for_nip():
    s = B.physics_setup(B.physics_library("n-i-p", "PTAA", "Ag", "metal_wf"), "n-i-p")
    assert s["W_R_eV"] == 4.7 and s["W_L_eV"] == B.b2_contacts("n-i-p", "PTAA")[0]
    with pytest.raises(ValueError):
        B.physics_library("p-i-n", "NiOx", "Ag", "metal_wf")


def test_analyse_rules_on_fake_runs(tmp_path, monkeypatch):
    """scripts/paperB_run.analyse on synthetic run files (no SimSS, no real result): material trade-off on the front."""
    import importlib.util
    import json
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("paperB_run", Path(__file__).resolve().parents[1] / "scripts" / "paperB_run.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    monkeypatch.setattr(P, "OUT", tmp_path)
    monkeypatch.setattr(P, "RUNS", tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    for arch, scen, method, seed in P.jobs():
        calls = []
        for i in range(S.BUDGET):
            htl, metal = B.HTLS[i % 2], B.METALS[i % 3]
            x = list(B.bounds(arch, htl)[0])
            x[1] = 300 + i
            good = not (method == "random" and i < 13)
            # Ag: +0.3 points PCE and +30% cost against Cu; Au far more expensive; mixbo finds higher PCE
            pce = 15 + (3 if method == "mixbo" else 0) + i / 100 + seed / 1000 + (0.3 if metal == "Ag" else 0)
            usd = 0.4 * (1.3 if metal == "Ag" else 30 if metal == "Au" else 1.0) - i / 10000
            calls.append({"x": x, "HTL": htl, "metal": metal, "cats": [B.HTLS.index(htl), B.METALS.index(metal)],
                          "feasible": good, "module_pce_pct": pce if good else None, "cell_pce_pct": pce,
                          "voc_V": 1.1, "ff": 0.8, "jsc_mA_cm2": 22.0,
                          "usd_per_W": usd if good else None, "log10_usd_per_W": math.log10(usd) if good else None,
                          "usd_per_W_high_prices": usd, "materials_usd_m2": 29.0, "back_electrode_usd_m2": 0.3,
                          "design_hash": f"{method}{seed}{i:04d}", "library_sha256": f"{htl}{metal}"})
        rid = P.run_id(arch, scen, method, seed)
        (tmp_path / "runs" / f"{rid}.json").write_text(json.dumps(
            {"calls": calls, "n_infeasible": sum(not c["feasible"] for c in calls)}))
    res = P.analyse()
    c = res["cases"]["p-i-n/base"]
    assert c["unreliable"] is True
    assert c["q1"]["mixbo>random"] and not c["q1"]["random>mixbo"]
    q2 = c["q2"]
    assert "Au" not in " ".join(q2["combos_on_front"])
    assert q2["pce_optimal"]["combo"].endswith("/Ag") and q2["cost_optimal"]["combo"].endswith("/Cu")
    assert q2["gap_cost_pct"] > 5 and q2["gap_small"] is False
    assert q2["wording"] == "material_trade_off_exists"                 # Ag +0.3 pt >= DPCE_MIN 0.2
    assert c["q1_igd"]["mixbo>random"] and not c["q1_igd"]["random>mixbo"]
    assert all(v >= 0 for v in c["methods"]["mixbo"]["igd_plus"])
    assert c["ref_point_no_au"][1] < c["ref_point"][1]
    assert abs(sum(c["methods"]["random"]["call_share_by_combo"].values()) - 1) < 1e-12
    assert res["q3"]["p-i-n"]["materials_robust"] is True
    (tmp_path / "runs" / f"{P.run_id('n-i-p', 'worse', 'nsga2', 3)}.json").unlink()
    with pytest.raises(FileNotFoundError):
        P.analyse()


def test_q4_slope_matches_the_engine_high_price_case(tmp_path):
    """Q4 assumes USD/W is linear in the PTAA price. Check the slope against the engine's own high-price case
    (PTAA is the only layer with a price_high entry)."""
    import importlib.util
    from pathlib import Path
    from perodesign.tea import evaluate_cost
    lib_c = load_cost_library()
    assert [k for k, v in lib_c["layer_materials"].items() if v.get("price_high")] == ["PTAA"]
    spec = importlib.util.spec_from_file_location("paperB_run", Path(__file__).resolve().parents[1] / "scripts" / "paperB_run.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    arch = "n-i-p"
    mk = lambda h, pce, usd, x: {"HTL": h, "metal": "Cu", "x": x, "module_pce_pct": pce, "usd_per_W": usd,  # noqa: E731
                                  "design_hash": h}
    xp = [30.0, 500.0, 40.0, 6.0]
    xn = [30.0, 500.0, 20.0, 6.0]
    by_pt = {1: mk("PTAA", 21.0, 0.0, xp), 2: mk("NiOx", 20.5, 0.35, xn)}
    q = P.q4_break_even(arch, "base", by_pt, {"cost_optimal": {"usd_per_W": 0.30}})["by_metal"]["Cu"]
    lib = B.physics_library(arch, "PTAA", "Cu")
    d, _ = B.design(arch, xp, "PTAA")
    r = evaluate_cost(d, 21.0, A.cost_line(), assumptions=A.ASM, physics_setup=B.physics_setup(lib, arch),
                      physics_library=lib)
    p_hi = next(e["value"] for e in lib_c["entries"] if e["id"] == lib_c["layer_materials"]["PTAA"]["price_high"])
    slope_engine = (r["usd_per_W_high_prices"] - r["usd_per_W"]) / (p_hi - 1145)
    assert math.isclose(q["slope_usd_W_per_usd_g"], slope_engine, rel_tol=1e-9)
    assert math.isclose(q["PTAA_best"]["usd_per_W"] + (q["break_even_vs_NiOx_usd_g"] - 1145) * slope_engine, 0.35,
                        rel_tol=1e-9)


def _runner():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("paperB_run", Path(__file__).resolve().parents[1] / "scripts" / "paperB_run.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    return P


def test_wording_taxonomy_is_complete():
    P = _runner()
    assert P.DPCE_MIN == 0.2
    assert P.wording(1, True, 0.0) == P.wording(1, False, 3.0) == "one_material_set_dominates"
    assert P.wording(2, True, 0.5) == "near_identical_materials"
    assert P.wording(2, False, 0.05) == "cost_differs_efficiency_practically_equal"   # Ag vs Cu optics case
    assert P.wording(3, False, 0.2) == "material_trade_off_exists"


def test_igd_plus_zero_on_front_and_positive_when_dominated():
    P = _runner()
    front = [(22.0, -0.4), (21.0, -0.5)]
    lo, span = (-22.0, -0.5), (1.0, 0.1)
    assert P.igd_plus(front, front, lo, span) == 0.0
    assert P.igd_plus([(21.0, -0.4)], front, lo, span) > 0
    assert P.igd_plus([(23.0, -0.6)], front, lo, span) == 0.0          # dominating point: IGD+ = 0
    assert P.igd_plus([], front, lo, span) == math.inf


def test_q4_status_when_ptaa_has_no_pce_advantage():
    P = _runner()
    mk = lambda h, pce, usd, x: {"HTL": h, "metal": "Cu", "x": x, "module_pce_pct": pce, "usd_per_W": usd,  # noqa: E731
                                  "design_hash": h}
    by_pt = {1: mk("PTAA", 20.0, 0.0, [30.0, 500.0, 40.0, 6.0]), 2: mk("NiOx", 21.0, 0.30, [30.0, 500.0, 20.0, 6.0])}
    q = P.q4_break_even("n-i-p", "base", by_pt, {"cost_optimal": {"usd_per_W": 0.30}})["by_metal"]["Cu"]
    assert q["status"] == "PTAA not competitive at any price in this model"
    assert q["break_even_vs_NiOx_usd_g"] is None and q["ptaa_pce_advantage_points"] < 0


@pytest.mark.slow
def test_bo_step_isolated_equals_in_process():
    """Amendment A3: the child-process BO step returns exactly the in-process candidates (same seed, same data)."""
    from perodesign.optim.bo_step import bo_step, run_isolated
    sp = B.space("n-i-p")
    pts = S.initial_points(sp, 24, 7)
    Y = _fake(pts)
    spec = {"X": [S._enc(sp, uc, c) for uc, c in pts], "Y": [[y[0], -y[1]] if y else [15.0, -1.0] for y in Y],
            "cat_idx": list(range(sp.n_cont, sp.dim)), "cat_sizes": list(sp.cat_sizes), "n_cont": sp.n_cont,
            "ref": [5.0, -1.0], "q": 2, "restarts": 2, "raw": 32, "mc": 16, "seed": 7001}
    a = bo_step(spec)
    b = run_isolated(spec, timeout_s=600)
    assert a == b and len(a) == 2 and all(len(r) == sp.dim for r in a)
