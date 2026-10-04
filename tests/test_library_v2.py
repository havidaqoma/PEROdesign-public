"""Library v2 (p-i-n industrial stack) + cost of both devices.

Key checks:
  * every 'literature' value in materials_v2.yaml is re-read from the saved source table (not trusted from YAML);
  * the ENGINE (not a test fixture) reproduces Liu 2025 Table 1 for Liu's own stack at Liu's own thicknesses;
  * p-i-n simulations complete, with the right current sign, and the assumed oxide optics barely matter;
  * v1 n-i-p results are unchanged under v2.
"""
import math
import re
from pathlib import Path

import pytest
import yaml

from perodesign.library import load_library
from perodesign.schema import from_thicknesses, validate
from perodesign.tea import back_electrode_cost, load_cost_library, materials_per_m2
from perodesign.tea.provenance import canon

REPO = Path(__file__).resolve().parents[1]


def pin(nio=15, pvk=600, c60=30, sno=10):
    return {"schema": "perodesign.design/1", "architecture": "p-i-n", "layers": [
        {"role": "HTL", "material": "NiOx", "thickness_nm": nio},
        {"role": "absorber", "material": "MAPbI3", "thickness_nm": pvk},
        {"role": "ETL", "material": "C60", "thickness_nm": c60},
        {"role": "buffer", "material": "SnO2", "thickness_nm": sno}]}


def _table(source_file):
    """Parse the '## TABLES' block of a saved source into {row_label: [cells]} and the header row."""
    text = (REPO / "data" / "sources" / source_file).read_text(encoding="utf-8")
    block = text.split("## TABLES", 1)[1].split("## TEXT", 1)[0]
    for tab in block.strip().split("\n\n"):
        rows = [r.split(" | ") for r in tab.splitlines()]
        if rows and rows[0][0] == "Properties":
            return rows[0], {r[0]: r for r in rows[1:]}
    raise AssertionError("parameter table not found")


@pytest.mark.parametrize("mat", ["NiOx", "SnO2"])
def test_literature_cells_match_the_saved_table(mat):
    lib = load_library()
    lit = lib["materials"][mat]["literature"]
    header, rows = _table("dipta2022_heliyon.txt")
    col = header.index(lit["column"])
    for label, cell in lit["cells"].items():
        assert rows[label][col] == cell, (mat, label, rows[label][col], cell)


@pytest.mark.parametrize("mat", ["NiOx", "SnO2"])
def test_literature_mapping_to_simss_units(mat):
    """Recompute every mapped parameter from the table cells (cm -> m, E_v = chi + Eg, N_c = sqrt(Nc Nv), C = sigma v_th)."""
    m = load_library()["materials"][mat]
    c = {k: float(v) for k, v in m["literature"]["cells"].items()}
    p = m["params"]
    assert p["E_c_eV"] == pytest.approx(c["Affinity (eV)"])
    assert p["E_v_eV"] == pytest.approx(c["Affinity (eV)"] + c["Bandgap (eV)"])
    assert p["eps_r"] == pytest.approx(c["Permittivity"])
    assert p["N_c_m3"] == pytest.approx(math.sqrt(c["N C (cm −3 )"] * c["N V (cm −3 )"]) * 1e6, rel=1e-6)
    assert p["mu_n_m2_Vs"] == pytest.approx(c["Electron Mobility (cm 2 /V-s)"] * 1e-4)
    assert p["mu_p_m2_Vs"] == pytest.approx(c["Hole Mobility (cm 2 /V-s)"] * 1e-4)
    assert p["N_t_bulk_m3"] == pytest.approx(c["Nt (cm −3 )"] * 1e6)
    sig_m2 = c["Capture cross-section (Electron and hole)"] * 1e-4
    vth_m_s = c["Electron Thermal Velocity (cm/s)"] * 1e-2
    assert p["C_n_bulk_m3_s"] == pytest.approx(sig_m2 * vth_m_s) and p["C_p_bulk_m3_s"] == pytest.approx(sig_m2 * vth_m_s)
    assert p["E_t_bulk_eV"] == pytest.approx(p["E_v_eV"] - c["Energy level above Ev (eV)"])
    dop = "N A (cm −3 )" if mat == "NiOx" else "N D (cm −3 )"
    assert (p["N_A_m3"] if mat == "NiOx" else p["N_D_m3"]) == pytest.approx(c[dop] * 1e6)


def test_hossain_quote_supports_the_assumed_oxide_index():
    q = (REPO / "data/sources/hossain2020_rscadv_quote.txt").read_text(encoding="utf-8")
    assert "comparable refractive indices ranging from 2.1–2.5" in q
    for f in ("nk_NiOx_const_n2p3.txt", "nk_SnO2_const_n2p3.txt"):
        rows = (REPO / "data/nk" / f).read_text().splitlines()[1:]
        assert {r.split()[1] for r in rows} == {"2.3"} and {r.split()[2] for r in rows} == {"0"}


def test_cu_nk_is_a_faithful_unit_conversion():
    y = yaml.safe_load((REPO / "data/nk/McPeak_Cu.yml").read_text(encoding="utf-8"))
    src = [tuple(map(float, r.split())) for r in y["DATA"][0]["data"].strip().splitlines()]
    out = [tuple(map(float, r.split())) for r in (REPO / "data/nk/nk_Cu_McPeak2015.txt").read_text().splitlines()[1:]]
    assert len(src) == len(out)
    for (um, n, k), (m, n2, k2) in zip(src, out):
        assert m == pytest.approx(um * 1e-6, rel=1e-4) and n2 == pytest.approx(n, rel=1e-5) and k2 == pytest.approx(k, rel=1e-5)


def test_pin_design_validates_and_v1_designs_unchanged():
    assert validate(pin())["architecture"] == "p-i-n"
    assert load_library()["library_version"] == 2
    d = validate(from_thicknesses(absorber_nm=500, etl_nm=10, htl_nm=10))
    assert [L["material"] for L in d["layers"]] == ["C60", "MAPbI3", "PTAA"]


# ------------------------------------------------------------------ cost: engine reproduces Liu's own table
def test_engine_reproduces_liu_layer_rows_on_liu_stack():
    """At Liu's thicknesses the engine's per-layer costs must equal Liu Table 1 row totals (printed, 3 s.f.)."""
    lib = load_cost_library()
    m = materials_per_m2(pin(15, 600, 30, 10), lib)
    it = {i["item"]: i["usd_m2"] for i in m["items"]}
    assert m["missing"] == []
    printed = {"layer:HTL:NiOx": 0.356, "layer:absorber:MAPbI3": 1.89, "layer:ETL:C60": 2.16,
               "layer:buffer:SnO2": 0.304, "bom:ITO_rear_electrode": 3.38, "bom:back_electrode:Cu": 0.320,
               "bom:FTO_glass": 10.2, "bom:POE": 1.97, "bom:back_glass": 1.46, "bom:Al_frame": 4.30,
               "bom:butyl": 0.0306, "bom:junction_box": 2.92}
    for k, v in printed.items():
        assert it[k] == pytest.approx(v, rel=0.01), (k, it[k], v)
    assert set(it) == set(printed)
    assert m["total_usd_m2"] == pytest.approx(29.3, rel=0.005)       # Liu's printed total


def test_back_electrode_follows_the_simulated_architecture():
    lib = load_cost_library()
    assert back_electrode_cost(lib, architecture="n-i-p")["item"].endswith(":Au")
    cu = back_electrode_cost(lib, architecture="p-i-n")
    assert cu["item"].endswith(":Cu") and cu["usd_m2"] == pytest.approx(8 * 0.01 / 0.25)


def test_industrial_device_cost_scales_with_design():
    lib = load_cost_library()
    a = {i["item"]: i["usd_m2"] for i in materials_per_m2(pin(15, 600, 30, 10), lib)["items"]}
    b = {i["item"]: i["usd_m2"] for i in materials_per_m2(pin(30, 300, 60, 20), lib)["items"]}
    assert b["layer:HTL:NiOx"] == pytest.approx(2 * a["layer:HTL:NiOx"])
    assert b["layer:absorber:MAPbI3"] == pytest.approx(0.5 * a["layer:absorber:MAPbI3"])
    assert b["layer:buffer:SnO2"] == pytest.approx(2 * a["layer:buffer:SnO2"])


# ------------------------------------------------------------------ physics (real binary)
def _sim(tmp_path):
    from perodesign.physics.simss import SimSS, SimSSConfigError
    try:
        return SimSS(work_root=tmp_path / "w")
    except SimSSConfigError as e:
        pytest.skip(f"SimSS not available: {e}")


@pytest.mark.simss
def test_pin_liu_stack_simulates(tmp_path):
    r = _sim(tmp_path).run(pin())
    assert r.status == "complete", r.reason
    assert 15 < r.metrics["pce_pct"] < 25 and 1.0 < r.metrics["voc_V"] < 1.3
    assert r.metrics["jsc_mA_cm2"] > 0                       # generating sign handled for anode-left
    assert 0 < r.metrics["vmpp_V"] < r.metrics["voc_V"]
    args = dict(zip(r.provenance["args"][0::2], r.provenance["args"][1::2]))
    assert args["-leftElec"] == "1" and args["-Vscan"] == "-1" and args["-untilVoc"] == "0"
    assert args["-nkBE"].endswith("nk_Cu_McPeak2015.txt") and args["-L_BE"] == "1.500000e-07"
    assert "-l4.L" in args and args["-l4.L"] == "1.000000e-08"


@pytest.mark.simss
def test_nip_unchanged_under_v2(tmp_path):
    r = _sim(tmp_path).run(from_thicknesses(absorber_nm=500, etl_nm=10, htl_nm=10))
    assert r.metrics["pce_pct"] == pytest.approx(22.51, abs=0.01)
    args = dict(zip(r.provenance["args"][0::2], r.provenance["args"][1::2]))
    assert args["-leftElec"] == "-1" and args["-untilVoc"] == "1" and "-l4.L" not in args


# ------------------------------------------------------------------ contact scenarios (P1)
def test_contact_scenario_values_are_in_their_sources():
    lib = load_library()
    cs = lib["contact_scenarios"]["scaps_input_wf"]
    for key, pv in cs["provenance"].items():
        txt = canon((REPO / "data" / "sources" / pv["source"]).read_text(encoding="utf-8"))
        assert canon(pv["quote"]) in txt, key
        assert key.split("_")[1] in pv["quote"], key            # the number in the key appears in the quote
    assert cs["p-i-n"] == {"W_L_eV": 4.4, "W_R_eV": 4.0} and cs["n-i-p"] == {"W_L_eV": 4.0, "W_R_eV": 5.1}


@pytest.mark.simss
def test_contact_scenario_changes_args_and_cache_key(tmp_path):
    from perodesign.physics.simss import SimSS, SimSSConfigError
    try:
        ideal = SimSS(work_root=tmp_path / "w")
        lit = SimSS(work_root=tmp_path / "w", contact_scenario="scaps_input_wf")
    except SimSSConfigError as e:
        pytest.skip(str(e))
    a_i = dict(zip(ideal.build_args(pin())[0::2], ideal.build_args(pin())[1::2]))
    a_l = dict(zip(lit.build_args(pin())[0::2], lit.build_args(pin())[1::2]))
    assert a_i["-W_L"] == "sfb" and a_l["-W_L"] == "4.400000e+00" and a_l["-W_R"] == "4.000000e+00"
    assert ideal._cache_key("x") != lit._cache_key("x")
    with pytest.raises(SimSSConfigError):
        SimSS(work_root=tmp_path / "w", contact_scenario="made_up")


@pytest.mark.simss
def test_bare_fto_on_nio_is_a_failed_simulation(tmp_path):
    """FTO 4.4 eV directly on NiOx (E_v 5.7 eV): ~1.3 eV thermionic hole barrier -> blocked, S-shaped J-V with Voc at
    the sweep edge. agy review: this is a simulation breakdown, not a device result -> status FAILED, no PCE."""
    from perodesign.physics.simss import SimSS, SimSSConfigError
    try:
        r = SimSS(work_root=tmp_path / "w", contact_scenario="scaps_input_wf").run(pin())
    except SimSSConfigError as e:
        pytest.skip(str(e))
    assert r.status == "failed" and "sweep edge" in r.reason
    assert r.metrics["pce_pct"] is None and r.metrics["voc_V"] is None
    assert any(w.startswith("diagnostic (NOT a result)") for w in r.warnings)



# ------------------------------------------------------------------ NiOx from one paper of measurements (Lee 2018)
def _lee_json():
    import json
    return json.loads((REPO / "phase0" / "sim_bench" / "p1_nio_lee2018.json").read_text(encoding="utf-8"))


def test_lee2018_quotes_are_in_the_saved_source():
    """Every measured NiOx value used by scripts/nio_lee2018.py is quoted verbatim from the saved open-access source,
    and the number the script uses appears in its quote."""
    txt = canon((REPO / "data" / "sources" / "lee2018_scirep_nio.txt").read_text(encoding="utf-8"))
    d = _lee_json()
    used = {"WF": "4.9", "EFV": "0.703", "Eg": "3.63", "p": "7.24 × 10 15", "mu": "2.96 × 10 −4"}
    for key, q in d["source_quotes"].items():
        assert canon(q) in txt, key
        assert used[key] in q, key
    assert "41598_2018_23907_MOESM1_ESM" in txt and "Kelvin probe" in txt       # SI saved: WF is a Kelvin-probe value


def test_mukherjee2024_nio_table_is_in_the_saved_source():
    txt = canon((REPO / "data" / "sources" / "mukherjee2024_ma_nio.txt").read_text(encoding="utf-8"))
    assert canon("Work function (eV) | 4.47 ± 0.05 | 4.47 ± 0.05 | 4.70 ± 0.05") in txt
    assert canon("Valence band maximum (eV) | 5.34 ± 0.05 | 5.21 ± 0.05 | 5.46 ± 0.05") in txt


def test_lee2018_result_file_is_consistent():
    """The committed sensitivity rows use the bands the README claims: E_v = 4.9 + E_F-E_V, E_c = E_v - 3.63,
    N_A 7.24e15 cm-3; case B (Lee's SCLC mobility) is a FAILED run with no PCE."""
    rows = _lee_json()["rows"]
    assert len(rows) == 20
    for r in rows:
        assert r["E_v_eV"] in (5.603, 5.668) and r["E_c_eV"] == pytest.approx(r["E_v_eV"] - 3.63, abs=1e-3)
        assert r["N_A_cm3"] == 7.24e15
        assert r["barrier_eV"] == pytest.approx(r["E_v_eV"] - r["W_L_eV"], abs=1e-3)
        if r["case"].startswith("B"):
            assert r["status"] == "failed" and r["pce_pct"] is None
        else:
            assert r["status"] == "complete" and 10 < r["pce_pct"] < 22


@pytest.mark.simss
def test_lee2018_case_a_reproduces(tmp_path):
    """Case A (Lee bands + doping, anode at Lee's measured 4.9 eV work function, E_F-E_V 0.703) re-simulates to the
    committed PCE."""
    import copy
    from perodesign.physics.simss import SimSS, SimSSConfigError
    lib = load_library()
    L2 = copy.deepcopy(lib)
    L2["materials"]["NiOx"]["params"].update({"E_v_eV": 5.603, "E_c_eV": 1.973, "E_t_bulk_eV": 5.203, "N_A_m3": 7.24e21})
    L2["contact_scenarios"]["_lee"] = {"p-i-n": {"W_L_eV": 4.9}}
    L2["_sha256"] = lib["_sha256"] + "|test_lee"
    try:
        r = SimSS(work_root=tmp_path / "w", library=L2, contact_scenario="_lee").run(pin())
    except SimSSConfigError as e:
        pytest.skip(str(e))
    want = next(x for x in _lee_json()["rows"] if x["case"].startswith("A") and x["E_v_eV"] == 5.603)
    assert r.status == "complete" and r.metrics["pce_pct"] == pytest.approx(want["pce_pct"], abs=0.01)
