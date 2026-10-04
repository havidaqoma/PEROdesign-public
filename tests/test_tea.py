"""P1-B: provenance gate, cost library, module model, cost engine, and the Liu 2025 reproduction."""
import copy
import math
from pathlib import Path

import pytest
import yaml

from perodesign.module import ModuleError, ModuleGeometry, gff, module_from_cell, p_tco
from perodesign.schema import from_thicknesses
from perodesign.tea import (CostLibraryError, Tagged, cost_per_watt, evaluate_cost, liu2025_line,
                            load_cost_library, materials_per_m2)
from perodesign.tea.provenance import check_entry

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "sources"


@pytest.fixture(scope="module")
def lib():
    return load_cost_library()


# ------------------------------------------------------------------ provenance gate: every rule fires
def _entry(lib, eid):
    return copy.deepcopy(lib["_by_id"][eid])


def test_all_library_entries_pass(lib):
    assert len(lib["entries"]) >= 40
    for e in lib["entries"]:
        assert check_entry(e, lib["sources"], SRC).ok, e["id"]


@pytest.mark.parametrize("mutate,rule", [
    (lambda e: e.pop("quote_span"), "FIELD"),
    (lambda e: e.update(confidence="certain"), "FIELD"),
    (lambda e: e.update(value=11.0), "FIELD"),                                    # value != value_text
    (lambda e: e.update(unit="EUR/m2"), "UNIT"),
    (lambda e: e.update(source="nobody2026"), "SOURCE"),
    (lambda e: e.update(quote_span="FTO Glass1 | 1 m2 | 9.0 $ m−2"), "R1"),       # invented span
    (lambda e: e.update(value=0.98, value_text="0.98"), "POS"),                   # wrong table column (was R3 before POS)
    (lambda e: e.update(value=1.0, value_text="1"), "POS"),                       # '1 m2' column is not the price
    (lambda e: e.pop("position") and e.update(value=0.98, value_text="0.98"), "R3"),  # no position: not currency-marked
    (lambda e: e.update(value=2.0, value_text="2"), "R2"),                        # '2' only inside '10.2'
])
def test_gate_rules_fire(lib, mutate, rule):
    e = _entry(lib, "liu_fto_glass_price")
    mutate(e)
    r = check_entry(e, lib["sources"], SRC)
    assert not r.ok and r.rule == rule, r


@pytest.mark.parametrize("mutate,rule", [
    (lambda e: e.update(value=20.0), "FIELD"),                     # forgot the scale
    (lambda e: e.update(scale_word="thousand", value=20000.0), "SCALE"),
    (lambda e: e.update(scale_word="lakh"), "SCALE"),
    (lambda e: e.pop("scale_word") and e.update(value=20.0), "R3"),  # bare '20' is not currency-marked
])
def test_scale_word_rules(lib, mutate, rule):
    e = _entry(lib, "liu_capex_line")
    assert check_entry(e, lib["sources"], SRC).ok
    mutate(e)
    r = check_entry(e, lib["sources"], SRC)
    assert not r.ok and r.rule == rule, r


def _tmp_source(tmp_path, text):
    import hashlib
    (tmp_path / "s.txt").write_text(text, encoding="utf-8")
    return {"s": {"file": "s.txt", "sha256": hashlib.sha256((tmp_path / "s.txt").read_bytes()).hexdigest()}}


BASE = dict(confidence="low", cost_basis_year=2024, geography="X", source="s")
AGY_TEXT = ("the line costs $10,000 per unit; glass 10.0 $ m-2 | 0.98 | 5 | x; frame 2.71 $ kg-1; "
            "film 0.50 $ g-2 typo; tool 3.0 $ per unit")


@pytest.mark.parametrize("entry,rule", [
    (dict(id="a", value=10.0, value_text="10", unit="USD", quote_span="the line costs $10,000 per unit"), "R2"),
    (dict(id="b", value=10.0, value_text="10.0", unit="USD/W", quote_span="glass 10.0 $ m-2"), "R5"),
    (dict(id="c", value=2.71, value_text="2.71", unit="USD/g", quote_span="frame 2.71 $ kg-1"), "R5"),
    (dict(id="d", value=5.0, value_text="5", unit="fraction", quote_span="glass 10.0 $ m-2 | 0.98 | 5 | x"), "FIELD"),
    (dict(id="e", value=5.0, value_text="5", unit="fraction", position={"sep": "|", "index": 1},
          quote_span="glass 10.0 $ m-2 | 0.98 | 5 | x"), "POS"),
    (dict(id="f", value=0.5, value_text="0.50", unit="USD/g", quote_span="film 0.50 $ g-2 typo"), "R5"),
    (dict(id="g", value=0.5, value_text="0.50", unit="USD/g", denominator_as_printed="g-2",
          quote_span="film 0.50 $ g-2 typo"), "R5"),                             # typo accepted only with a note
    (dict(id="h", value=3.0, value_text="3.0", unit="USD", quote_span="tool 3.0 $ per unit"), "R5"),
])
def test_agy_gate_holes_are_closed(tmp_path, entry, rule):
    """agy review 2026-09-28: comma truncation (was already refused, by R2 after canon), denominator
    blind spot, plain units without position, list/table position, printed-denominator typos."""
    srcs = _tmp_source(tmp_path, AGY_TEXT)
    r = check_entry({**BASE, **entry}, srcs, tmp_path)
    assert not r.ok and r.rule == rule, r


def test_gate_accepts_correct_forms(tmp_path):
    srcs = _tmp_source(tmp_path, AGY_TEXT)
    ok = [dict(id="p", value=0.98, value_text="0.98", unit="fraction", position={"sep": "|", "index": 1},
               quote_span="glass 10.0 $ m-2 | 0.98 | 5 | x"),
          dict(id="q", value=10.0, value_text="10.0", unit="USD/m2", quote_span="glass 10.0 $ m-2"),
          dict(id="r", value=2.71, value_text="2.71", unit="USD/kg", quote_span="frame 2.71 $ kg-1"),
          dict(id="s", value=0.5, value_text="0.50", unit="USD/g", denominator_as_printed="g-2",
               denominator_note="typo", quote_span="film 0.50 $ g-2 typo")]
    for e in ok:
        assert check_entry({**BASE, **e}, srcs, tmp_path).ok, e["id"]


def test_c60_price_is_flagged_as_printed_typo(lib):
    r = check_entry(_entry(lib, "liu_c60_price"), lib["sources"], SRC)
    assert r.ok and "differs" in r.reason


def test_list_position_is_enforced(lib):
    e = _entry(lib, "liu_c60_thickness")
    e.update(value=10.0, value_text="10")          # 10 is SnOx (4th), not C60 (3rd)
    r = check_entry(e, lib["sources"], SRC)
    assert r.rule == "POS"


def test_zero_or_unnoted_assumption_is_refused(lib):
    from perodesign.tea import _assumed
    with pytest.raises(CostLibraryError, match="omission"):
        _assumed({"x": {"usd_m2": 0.0, "note": "free"}}, "x")
    with pytest.raises(CostLibraryError, match="omission"):
        _assumed({"x": {"usd_m2": 1.0}}, "x")
    d = from_thicknesses(absorber_nm=500, etl_nm=10, htl_nm=10)
    with pytest.raises(CostLibraryError, match="note"):
        materials_per_m2(d, lib, {"density:PTAA": {"g_cm3": 1.1}})
    with pytest.raises(CostLibraryError, match="not physical"):
        materials_per_m2(d, lib, {"density:PTAA": {"g_cm3": 90.0, "note": "x"}})


def test_new_gate_rules_cell_and_header(lib):
    g = _entry(lib, "wb_gold_2026_aug")
    assert check_entry(g, lib["sources"], SRC).ok
    g2 = copy.deepcopy(g); g2["unit_cell"]["index"] = 2          # 'c/' footnote column
    assert check_entry(g2, lib["sources"], SRC).rule == "CELL"
    g3 = copy.deepcopy(g); g3["position"]["index"] = 12; g3.update(value=4073.0, value_text="4073")  # July, fine
    assert check_entry(g3, lib["sources"], SRC).ok
    g4 = copy.deepcopy(g); g4["unit"] = "USD/g"
    assert check_entry(g4, lib["sources"], SRC).rule == "CELL"
    p = _entry(lib, "ptaa_price_review_2022")
    assert check_entry(p, lib["sources"], SRC).ok
    p2 = copy.deepcopy(p); p2["unit_header"] = "Price (per Gram, EUR)"
    assert check_entry(p2, lib["sources"], SRC).rule in ("HEADER", "R1")
    p3 = copy.deepcopy(p); p3["unit"] = "USD/kg"
    assert check_entry(p3, lib["sources"], SRC).rule == "HEADER"


def test_gate_currency_mismatch_R4(lib, tmp_path):
    (tmp_path / "s.txt").write_text("glass costs 10.0 EUR per m2", encoding="utf-8")
    import hashlib
    srcs = {"s": {"file": "s.txt", "sha256": hashlib.sha256((tmp_path / "s.txt").read_bytes()).hexdigest()}}
    e = {"id": "x", "value": 10.0, "value_text": "10.0", "unit": "USD/m2", "source": "s", "confidence": "low",
         "quote_span": "glass costs 10.0 EUR per m2", "cost_basis_year": 2024, "geography": "EU"}
    r = check_entry(e, srcs, tmp_path)
    assert r.rule == "R4"


def test_gate_detects_edited_source_file(lib, tmp_path):
    import shutil
    shutil.copy(SRC / "liu2025_nml.txt", tmp_path / "liu2025_nml.txt")
    with open(tmp_path / "liu2025_nml.txt", "a", encoding="utf-8") as f:
        f.write("\nFTO Glass1 | 1 m2 | 1.0 $ m−2\n")
    r = check_entry(_entry(lib, "liu_fto_glass_price"), lib["sources"], tmp_path)
    assert r.rule == "SOURCE" and "changed" in r.reason


def test_library_refuses_to_load_with_a_bad_entry(tmp_path):
    raw = yaml.safe_load((REPO / "perodesign/tea/cost_library_v1.yaml").read_text(encoding="utf-8"))
    raw["entries"][0]["value"] = 12.0
    raw["entries"][0]["value_text"] = "12.0"
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(CostLibraryError, match="provenance gate"):
        load_cost_library(p, SRC)


# ------------------------------------------------------------------ Liu 2025 reproduction (checkpoints)
LIU_ROWS = [("liu_fto_glass_price", None, "liu_fto_glass_util", 1), ("liu_nio_price", "liu_nio_vol", "liu_nio_util", None),
            ("liu_perovskite_price", "liu_perovskite_mass", "liu_perovskite_util", None),
            ("liu_c60_price", "liu_c60_mass", "liu_c60_util", None), ("liu_sno_price", "liu_sno_vol", "liu_sno_util", None),
            ("liu_ito_price", "liu_ito_vol", "liu_ito_util", None), ("liu_cu_price", "liu_cu_mass", "liu_cu_util", None),
            ("liu_poe_price", None, "liu_poe_util", 1), ("liu_backglass_price", None, "liu_backglass_util", 1),
            ("liu_frame_price", "liu_frame_mass", "liu_frame_util", "kg"), ("liu_butyl_price", "liu_butyl_mass", "liu_butyl_util", "kg"),
            ("liu_jbox_price", None, "liu_jbox_util", 1)]


def _liu_materials_total(lib):
    v = lambda i: float(lib["_by_id"][i]["value"])
    tot = 0.0
    for price, qty, util, q in LIU_ROWS:
        quantity = (v(qty) / 1000.0 if q == "kg" else v(qty)) if qty else q
        tot += quantity * v(price) / v(util)
    return tot


def test_reproduces_liu_materials_29_3(lib):
    """Independent check: Liu's rule (quantity x price / utilisation) over its 12 sourced rows."""
    tot = _liu_materials_total(lib)
    assert tot == pytest.approx(float(lib["_by_id"]["liu_materials_total"]["value"]), rel=0.005)   # 29.27 vs 29.3


def test_reproduces_liu_cost_per_watt_with_stated_rate_gap(lib):
    """0.39 materials is reproduced independently. Capital needs a rate the paper does not state: with
    the back-solved 4.85% the 0.092 is matched BY CONSTRUCTION. Other opex is derived from 0.088
    (circular). So only the materials line is a real validation; this test documents that."""
    line = liu2025_line(lib, rate=Tagged(0.0485, "assumed:back-solved from Liu 0.092 USD/W (NOT a source)"))
    c = cost_per_watt(_liu_materials_total(lib), 15.0, line)
    assert c["parts_usd_per_W"]["materials"] == pytest.approx(0.39, abs=0.005)
    assert c["parts_usd_per_W"]["capital"] == pytest.approx(0.092, abs=0.001)
    assert c["parts_usd_per_W"]["other_opex"] == pytest.approx(0.088, abs=1e-9)
    assert c["usd_per_W"] == pytest.approx(0.57, abs=0.005)
    assert line.rate.tag.startswith("assumed")


def test_line_without_rate_refuses(lib):
    with pytest.raises(CostLibraryError, match="rate is not set"):
        cost_per_watt(29.3, 15.0, liu2025_line(lib))


def test_implied_densities_are_physical(lib):
    v = lambda i: float(lib["_by_id"][i]["value"])
    c60 = v("liu_c60_mass") / (v("liu_c60_thickness") * 1e-3)          # g / cm3 (nm x 1 m2 = nm*1e-3 cm3)
    pvk = v("liu_perovskite_mass") / (v("liu_perovskite_thickness") * 1e-3)
    assert 1.4 < c60 < 2.0          # C60 crystal ~1.65 g/cm3
    assert 3.5 < pvk < 5.5          # lead halide perovskites ~4.1-4.9 g/cm3


# ------------------------------------------------------------------ design materials
def test_lab_device_needs_only_the_ptaa_density(lib):
    """Gold and PTAA prices are sourced now; PTAA density has no open-access source -> the only missing item."""
    m = materials_per_m2(from_thicknesses(absorber_nm=500, etl_nm=10, htl_nm=10), lib)
    assert m["missing"] == ["density:PTAA"]
    r = evaluate_cost(from_thicknesses(absorber_nm=500, etl_nm=10, htl_nm=10), 18.0,
                      liu2025_line(lib, rate=Tagged(0.08, "assumed:test")))
    assert r["status"] == "incomplete" and r["usd_per_W"] is None


def test_thicker_layers_cost_more_and_scale_linearly(lib):
    a = materials_per_m2(from_thicknesses(absorber_nm=300, etl_nm=10, htl_nm=10), lib)
    b = materials_per_m2(from_thicknesses(absorber_nm=600, etl_nm=20, htl_nm=10), lib)
    ia = {i["item"]: i["usd_m2"] for i in a["items"]}
    ib = {i["item"]: i["usd_m2"] for i in b["items"]}
    assert ib["layer:absorber:MAPbI3"] == pytest.approx(2 * ia["layer:absorber:MAPbI3"])
    assert ib["layer:ETL:C60"] == pytest.approx(2 * ia["layer:ETL:C60"])
    # 600 nm perovskite = Liu's own 600 nm reference -> exactly Liu's row cost (2.83 x 0.63 / 0.95)
    assert ib["layer:absorber:MAPbI3"] == pytest.approx(2.83 * 0.63 / 0.95)


def test_assumptions_are_labelled(lib):
    d = from_thicknesses(absorber_nm=500, etl_nm=10, htl_nm=10)
    asm = {"density:PTAA": {"g_cm3": 1.1, "note": "TEST ONLY"}}
    r = evaluate_cost(d, 18.0, liu2025_line(lib, rate=Tagged(0.08, "assumed:test")), assumptions=asm)
    assert r["status"] == "with_assumptions"
    assert {"layer:HTL:PTAA", "rate"} <= set(r["assumed_inputs"])
    assert r["usd_per_W_high_prices"] > r["usd_per_W"] > 0


def test_gold_back_electrode_from_sourced_values(lib):
    """101 nm (physics library L_BE) x 19.3 g/cm3 x 4411 USD/toz / 31.1034768 g / 0.25 -- recomputed here."""
    from perodesign.tea import back_electrode_cost
    be = back_electrode_cost(lib)
    expect = 101 * 1e-3 * 19.3 * (4411 / 31.1034768) / 0.25
    assert be["usd_m2"] == pytest.approx(expect, rel=1e-9)
    assert 1100 < be["usd_m2"] < 1150                     # ~1106 USD/m2
    assert "PROXY" in be["tag"]


# ------------------------------------------------------------------ module model
def test_gff():
    assert gff(ModuleGeometry(6.0, 0.2, 10.0)) == pytest.approx(6.0 / 6.2)
    assert gff(ModuleGeometry(6.0, 0.2, 10.0, edge_area_fraction=0.05)) == pytest.approx(6.0 / 6.2 * 0.95)


def test_tco_loss_matches_numerical_integration():
    """Discretise the stripe: current accumulates linearly to the interconnect; sum I^2 R."""
    g = ModuleGeometry(stripe_width_mm=7.0, dead_width_mm=0.2, tco_sheet_res_ohm_sq=12.0)
    J, V = 200.0, 0.95                                   # A/m2, V
    w, n = 7e-3, 20000
    dx = w / n
    loss = sum((J * (i + 0.5) * dx) ** 2 * g.tco_sheet_res_ohm_sq * dx for i in range(n))   # W per m stripe length
    assert p_tco(g, J, V) == pytest.approx(loss / (J * V * w), rel=1e-6)


def test_module_from_cell_and_refusals():
    cell = {"pce_pct": 22.51, "mpp_W_m2": 225.1, "vmpp_V": 1.07}
    m = module_from_cell(cell, ModuleGeometry(6.0, 0.2, 10.0))
    assert m["module_pce_pct"] < 22.51 and m["gff"] == pytest.approx(6 / 6.2)
    assert m["module_pce_pct"] == pytest.approx(22.51 * m["gff"] * (1 - m["p_tco"]))
    with pytest.raises(ModuleError, match="outside the first-order"):
        module_from_cell(cell, ModuleGeometry(20.0, 0.2, 60.0))
    with pytest.raises(ModuleError):
        ModuleGeometry(6.0, 7.0, 10.0).check()
    with pytest.raises(ModuleError):
        module_from_cell({"pce_pct": 20.0}, ModuleGeometry(6.0, 0.2, 10.0))


# ------------------------------------------------------------------ regions (P1): sourced cost of capital
def test_region_rates_are_sourced_and_row_checked(lib):
    from perodesign.tea import region_line
    got = {r: region_line(r, lib).rate for r in ("MY", "CN", "IN")}
    assert got["MY"].value == pytest.approx(0.0482472886111111) and got["MY"].tag.startswith("sourced:wdi_lend_my_2025")
    assert got["CN"].value == pytest.approx(0.0435) and got["IN"].value == pytest.approx(0.0856714285714286)
    e = _entry(lib, "wdi_lend_my_2025")
    e["row_cells"] = {0: "CHN", 1: "FR.INR.LEND", 3: "2025"}           # claim the MY row is China -> refused
    assert check_entry(e, lib["sources"], SRC).rule == "ROW"
    e = _entry(lib, "wdi_lend_my_2025")
    e["row_cells"] = {0: "MYS", 1: "FR.INR.LEND", 3: "2024"}           # wrong year -> refused
    assert check_entry(e, lib["sources"], SRC).rule == "ROW"


def test_region_line_labels_what_is_not_regional(lib):
    from perodesign.tea import region_line
    ln = region_line("MY", lib)
    assert "NOT REGIONALISED" in ln.other_opex_usd_per_m2.tag
    with pytest.raises(CostLibraryError, match="not in cost library"):
        region_line("XX", lib)


def test_my_rate_coincides_with_backsolved_rate_and_that_is_not_validation(lib):
    """AutoTEA coincidence rule: the sourced MY 2025 lending rate (4.82%) happens to sit next to the rate
    back-solved from Liu's China capital line (4.85%). This test documents the coincidence; it proves nothing."""
    from perodesign.tea import region_line
    assert abs(region_line("MY", lib).rate.value - 0.0485) < 0.001



def test_tnb_tariff_is_gated_by_label(lib):
    for eid in ("tnb_mv_energy", "tnb_mv_afa", "tnb_mv_capacity", "tnb_mv_network"):
        assert check_entry(_entry(lib, eid), lib["sources"], SRC).ok, eid
    e = _entry(lib, "tnb_mv_energy")
    e["label"] = "network:"                                   # value 0.2983 is not the network charge
    assert check_entry(e, lib["sources"], SRC).rule == "LABEL"
    e = _entry(lib, "tnb_mv_energy")
    e.pop("unit_basis")
    assert check_entry(e, lib["sources"], SRC).rule == "LABEL"
    # attack found by scripts/label_gate_attack.py: identical numbers in the net-metering block
    e = _entry(lib, "tnb_mv_energy")
    e["quote_span"] = "const NONDOMMVGENNEM = { RETAIL_CHARGE_THRESHOLD: 0, RATES: { energyCharge: 0.2983,"
    r = check_entry(e, lib["sources"], SRC)
    assert not r.ok and r.rule == "LABEL", r
    e = _entry(lib, "tnb_mv_energy")
    e.pop("block")
    assert check_entry(e, lib["sources"], SRC).rule == "LABEL"


def test_sourced_status_still_lists_proxies(lib):
    """'sourced' must never hide stand-ins: the industrial device reports its proxies explicitly."""
    from perodesign.tea import evaluate_cost, region_line
    pin = {"schema": "perodesign.design/1", "architecture": "p-i-n", "layers": [
        {"role": "HTL", "material": "NiOx", "thickness_nm": 15}, {"role": "absorber", "material": "MAPbI3", "thickness_nm": 600},
        {"role": "ETL", "material": "C60", "thickness_nm": 30}, {"role": "buffer", "material": "SnO2", "thickness_nm": 10}]}
    r = evaluate_cost(pin, 18.19, region_line("MY", lib))
    assert r["status"] == "sourced_with_proxies"                   # agy review: plain "sourced" was misleading
    assert {"layer:absorber:MAPbI3", "other_opex_usd_per_m2", "throughput_m2_per_yr", "rate"} <= set(r["proxy_inputs"])
    assert r["line_meta"]["regional_inputs"] == ["rate"]            # the ONLY regional input
    assert "NOT REGIONALISED" in r["line_meta"]["tags"]["other_opex_usd_per_m2"]


def test_wacc_scenario_is_an_upper_bound_and_labelled(lib):
    from perodesign.tea import region_line
    lo, hi = region_line("MY", lib), region_line("MY", lib, rate_basis="wacc_kajal")
    assert lo.rate.value == pytest.approx(0.0482472886111111) and hi.rate.value == pytest.approx(0.102)
    assert "LOWER BOUND" in lo.rate.tag and "UPPER-BOUND" in hi.rate.tag and "India 2022" in hi.rate.tag
    with pytest.raises(CostLibraryError):
        region_line("MY", lib, rate_basis="made_up")


def test_labour_sources_and_header_column_binding(lib):
    for eid in ("dosm_mfg_mean_wage_2025", "cai_line_employees", "cai_line_wage", "cai_module_W_per_m2", "cai_line_capacity"):
        assert check_entry(_entry(lib, eid), lib["sources"], SRC).ok, eid
    e = _entry(lib, "cai_line_wage")                          # attack: employee count (76) as the wage
    e["position"]["index"] = 0
    e.update(value=76.0, value_text="76")
    assert check_entry(e, lib["sources"], SRC).rule == "HEADER"
    e = _entry(lib, "dosm_mfg_mean_wage_2025")                # attack: 2024 column instead of 2025
    e.update(value=3278.0, value_text="3278")
    assert check_entry(e, lib["sources"], SRC).rule == "LABEL"
    e = _entry(lib, "dosm_mfg_mean_wage_2025")                # attack: Total row instead of Manufacturing
    e["quote_span"] = "A:Jumlah2 | B:1936 | C:1959 | D:2052 | E:2186 | F:2377 | G:2487 | H:2657 | I:2879 | J:3087 | K:3224 | L:2954 | M:3049 | N:3219 | O:3441 | P:3652 | Q:3803 | R:Total2"
    e.update(value=3803.0, value_text="3803")
    assert check_entry(e, lib["sources"], SRC).rule == "LABEL"


# ------------------------------------------------------------------ Malaysia bottom-up opex
def test_labour_reproduces_cai_and_scales_with_dosm(lib):
    from perodesign.tea import labour_usd_per_m2
    g = labour_usd_per_m2("GLOBAL_CAI", lib)
    assert g.value / 120 == pytest.approx(0.0304, abs=5e-5)            # Cai's own printed 0.0304 USD/W at 120 W/m2
    my = labour_usd_per_m2("MY", lib)
    assert my.value == pytest.approx(76 * 3357 * 12 / 4.28442415048243 / (100e6 / 120), rel=1e-9)
    assert "LOWER BOUND" in my.tag and "PROXY" in my.tag
    with pytest.raises(CostLibraryError):
        labour_usd_per_m2("XX", lib)


def test_process_electricity_inventory(lib):
    from perodesign.tea import electricity_usd_per_m2_MY, process_kwh_per_m2
    e = process_kwh_per_m2("p-i-n", lib)
    # recompute: S2 listed steps + S4 range steps (power x time low, listed high)
    listed = 0.0107 + 0.515 + 0.359 + 3.74 + 3.53
    assert e["kWh_low"] == pytest.approx(listed + 98300 * 36 / 3.6e6 + 18000 * 600 / 3.6e6)
    assert e["kWh_high"] == pytest.approx(listed + 18.6 / 3.6 + 10.8 / 3.6)          # S4 rows are MJ
    anneal = [s for s in e["steps"] if s["step"] == "perovskite anneal"][0]
    assert anneal["kWh_low"] == pytest.approx(anneal["kWh_high"])                  # resistive step: P x t == row/3.6
    el = electricity_usd_per_m2_MY("p-i-n", lib)
    assert el["usd_per_kWh"] == pytest.approx((0.2983 + 0.0367) / 4.28442415048243)
    assert any("max demand" in x for x in el["excluded"])
    with pytest.raises(CostLibraryError):
        process_kwh_per_m2("n-i-p", lib)                                 # no inventory for the lab stack yet


def test_bottom_up_line_is_labelled_lower_bound(lib):
    from perodesign.tea import electricity_usd_per_m2_MY, labour_usd_per_m2, region_line_MY_bottom_up
    ln = region_line_MY_bottom_up(lib)
    assert "LOWER BOUND" in ln.other_opex_usd_per_m2.tag and "land/rent" in ln.other_opex_usd_per_m2.tag
    # labour must be spread over the SAME line throughput as capital (Liu 100 MW at 15% = 666,667 m2/yr)
    thr = ln.throughput_m2_per_yr.value
    assert thr == pytest.approx(100e6 / 150)
    lab = labour_usd_per_m2("MY", lib, throughput_m2_per_yr=thr).value
    assert ln.opex_parts_usd_m2["labour"] == pytest.approx(lab)
    assert ln.opex_parts_usd_m2["electricity_energy"] == pytest.approx(electricity_usd_per_m2_MY("p-i-n", lib)["usd_m2_low"])
    base = region_line_MY_bottom_up(lib, include_maintenance=False, include_demand=False)
    assert base.other_opex_usd_per_m2.value == pytest.approx(lab + electricity_usd_per_m2_MY("p-i-n", lib)["usd_m2_low"])
    assert lab == pytest.approx(76 * 3357 * 12 / 4.28442415048243 / thr)


def test_regional_inputs_are_reported_for_every_case(lib):
    from perodesign.tea import evaluate_cost, region_line, region_line_MY_bottom_up
    pin = {"schema": "perodesign.design/1", "architecture": "p-i-n", "layers": [
        {"role": "HTL", "material": "NiOx", "thickness_nm": 15}, {"role": "absorber", "material": "MAPbI3", "thickness_nm": 600},
        {"role": "ETL", "material": "C60", "thickness_nm": 30}, {"role": "buffer", "material": "SnO2", "thickness_nm": 10}]}
    got = lambda ln: set(evaluate_cost(pin, 18.19, ln)["line_meta"]["regional_inputs"])
    assert got(region_line("MY", lib)) == {"rate"}
    assert got(region_line("MY", lib, rate_basis="wacc_kajal")) == set()              # Kajal WACC is India, not MY
    assert got(region_line_MY_bottom_up(lib)) == {"rate", "other_opex_usd_per_m2"}
    assert got(region_line_MY_bottom_up(lib, rate_basis="wacc_kajal")) == {"other_opex_usd_per_m2"}


def test_tian_s4_rows_are_megajoules(lib):
    """agy review 2026-09-28: S4 header says kWh but the 16 rows sum to 221.94 and /3.6 = the stated kWh Total."""
    import re as _re
    txt = (SRC / "tian2020_sciadv_si.txt").read_text(encoding="utf-8").split("## TABLE S4", 1)[1]
    rows = _re.findall(r"(\d\.\d+E[+-]\d+) (\d+) (\d\.\d+E[+-]\d+)", txt)
    assert len(rows) == 16
    total_kwh = float(lib["_by_id"]["tian_s4_total_kwh"]["value"])
    assert sum(float(r[2]) for r in rows) / 3.6 == pytest.approx(total_kwh, abs=0.01)
    assert check_entry(_entry(lib, "tian_s4_total_kwh"), lib["sources"], SRC).ok


# ------------------------------------------------------------------ maintenance + TNB demand (P1)
def test_maintenance_share_is_consistent_with_cai(lib):
    """Independent check: Kajal's 1%/yr applied to Cai's own line (11 M USD, 100 MW) = Cai's printed 0.0011 USD/W."""
    frac = float(lib["_by_id"]["kajal_maintenance_frac"]["value"]) / 100
    capex = float(lib["_by_id"]["cai_capex_A"]["value"])
    assert capex == 11e6
    assert frac * capex / 100e6 == pytest.approx(float(lib["_by_id"]["cai_maintenance_A"]["value"]), rel=1e-9)
    from perodesign.tea import maintenance_usd_per_m2, region_line
    ln = region_line("MY", lib)
    assert maintenance_usd_per_m2(ln, lib).value == pytest.approx(0.01 * 20e6 / (100e6 / 150))


def test_demand_charge_recomputed(lib):
    from perodesign.tea import demand_charge_MY, process_kwh_per_m2, region_line
    ln = region_line("MY", lib)
    d = demand_charge_MY("p-i-n", ln, lib, "low")
    kwh = process_kwh_per_m2("p-i-n", lib)["kWh_low"]
    thr, h, fx = 100e6 / 150, 504000 / 60, 4.28442415048243
    kw = kwh * thr / h
    assert d["kW_max_demand_assumed"] == pytest.approx(kw)
    demand = kw * (29.43 + 59.84) * 12 / fx
    fixed = 200 * 12 / fx
    energy = kwh * thr * (0.2983 + 0.0367) / fx
    assert d["usd_m2"] == pytest.approx((demand + fixed + 0.016 * (energy + demand + fixed)) / thr)
    assert "LOWER BOUND" in d["tag"] and d["usd_m2_per_extra_450kW_tool"] == pytest.approx(450 * 89.27 * 12 / fx / thr)


def test_bottom_up_opex_parts_and_omissions(lib):
    from perodesign.tea import region_line_MY_bottom_up
    ln = region_line_MY_bottom_up(lib)
    assert set(ln.opex_parts_usd_m2) == {"labour", "electricity_energy", "maintenance", "tnb_demand_fixed_levy"}
    assert ln.other_opex_usd_per_m2.value == pytest.approx(sum(ln.opex_parts_usd_m2.values()))
    assert "land/rent/facilities" in ln.opex_omitted and any("EPF" in x for x in ln.opex_omitted)
    lf = region_line_MY_bottom_up(lib, include_facilities_proxy=True)
    assert lf.opex_parts_usd_m2["facilities_rent_cai_proxy"] == pytest.approx(0.033 * 120)

