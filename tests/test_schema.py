"""Design schema v1 + library: every rejection rule has a test (reject, never repair)."""
import copy
import math

import pytest
import yaml

from perodesign.library import LibraryError, load_library
from perodesign.schema import (DesignError, canonical_json, design_hash, from_thicknesses,
                               resolved_layers, validate)

GOOD = from_thicknesses(500, 10, 10)


def problems(d):
    with pytest.raises(DesignError) as e:
        validate(d)
    return "\n".join(e.value.problems)


def test_library_loads_with_hash():
    lib = load_library()
    assert lib["library_version"] == 2
    assert len(lib["_sha256"]) == 64
    assert set(lib["materials"]) == {"C60", "MAPbI3", "PTAA", "NiOx", "SnO2"}
    v1 = load_library(lib["_path"].replace("materials_v2.yaml", "materials_v1.yaml"))
    assert v1["library_version"] == 1 and set(v1["materials"]) == {"C60", "MAPbI3", "PTAA"}


def test_valid_design_normalises():
    d = validate(GOOD)
    assert d["layers"][1]["thickness_nm"] == 500.0 and isinstance(d["layers"][1]["thickness_nm"], float)
    assert d["interface_overrides"] == {}
    assert all(L["overrides"] == {} for L in d["layers"])


def test_hash_is_stable_across_key_order_and_int_float():
    a = from_thicknesses(500, 10, 10)
    b = {"layers": [{"thickness_nm": 10.0, "material": "C60", "role": "ETL"},
                    {"material": "MAPbI3", "role": "absorber", "thickness_nm": 500.0},
                    {"role": "HTL", "thickness_nm": 10, "material": "PTAA"}],
         "architecture": "n-i-p", "schema": "perodesign.design/1"}
    assert design_hash(a) == design_hash(b)
    assert canonical_json(a) == canonical_json(b)
    assert design_hash(a) != design_hash(from_thicknesses(500, 10, 11))


@pytest.mark.parametrize("mutate,expect", [
    (lambda d: d.update(schema="perodesign.design/0"), "schema must be"),
    (lambda d: d.pop("layers"), "missing top-level key 'layers'"),
    (lambda d: d.update(colour="red"), "unknown top-level key 'colour'"),
    (lambda d: d.update(architecture="tandem"), "architecture 'tandem' not supported"),
    (lambda d: d.update(architecture="p-i-n"), "do not match architecture p-i-n"),     # n-i-p layer order
    (lambda d: d["layers"].reverse(), "do not match architecture"),
    (lambda d: d["layers"][1].update(thickness_nm=150), "outside [200, 1000]"),
    (lambda d: d["layers"][1].update(thickness_nm=1200), "outside [200, 1000]"),
    (lambda d: d["layers"][2].update(thickness_nm=80), "outside [10, 70]"),
    (lambda d: d["layers"][1].update(thickness_nm=float("nan")), "finite number"),
    (lambda d: d["layers"][1].update(thickness_nm=float("inf")), "finite number"),
    (lambda d: d["layers"][1].update(thickness_nm="500"), "finite number"),
    (lambda d: d["layers"][1].update(thickness_nm=True), "finite number"),
    (lambda d: d["layers"][1].update(thickness_um=0.5), "unknown key 'thickness_um'"),
    (lambda d: d["layers"][1].pop("thickness_nm"), "missing key 'thickness_nm'"),
    (lambda d: d["layers"][1].update(material="FAPbI3"), "not in library"),
    (lambda d: d["layers"][0].update(material="PTAA"), "cannot be used as 'ETL'"),
    (lambda d: d["layers"][1].update(overrides={"eps_r": 30}), "override 'eps_r' not allowed"),
    (lambda d: d["layers"][1].update(overrides={"N_t_bulk_m3": 1e25}), "outside [1e+19, 1e+22]"),
    (lambda d: d["layers"][1].update(overrides={"N_t_bulk_cm3": 1e14}), "override 'N_t_bulk_cm3' not allowed"),
    (lambda d: d["layers"][1].update(overrides={"N_t_bulk_m3": None}), "finite number"),
    (lambda d: d.update(interface_overrides={"ETL|HTL": {"N_t_int_m2": 1e12}}), "not an adjacent"),
    (lambda d: d.update(interface_overrides={"ETL|absorber": {"N_t_int_m2": 1e16}}), "outside [1e+10, 1e+14]"),
    (lambda d: d.update(interface_overrides={"ETL|absorber": {"nu_int_n_m_s": 1e5}}), "not allowed"),
    (lambda d: d.update(layers=[]), "non-empty list"),
])
def test_rejections(mutate, expect):
    d = copy.deepcopy(GOOD)
    mutate(d)
    assert expect in problems(d)


def test_all_problems_reported_at_once():
    d = copy.deepcopy(GOOD)
    d["layers"][0]["thickness_nm"] = 500
    d["layers"][2]["thickness_nm"] = 500
    msg = problems(d)
    assert "layers[0]" in msg and "layers[2]" in msg


def test_malformed_layers_with_interface_override_do_not_crash():
    d = {"schema": "perodesign.design/1", "architecture": "n-i-p", "layers": [1, 2, 3],
         "interface_overrides": {"None|None": {}}}
    assert "must be an object" in problems(d)


def test_non_object_design():
    assert "JSON object" in problems([1, 2, 3])


def test_overrides_and_interfaces_resolve():
    d = copy.deepcopy(GOOD)
    d["layers"][1]["overrides"] = {"N_t_bulk_m3": 3e20}
    d["interface_overrides"] = {"absorber|HTL": {"N_t_int_m2": 2e11}}
    R = resolved_layers(d)
    assert R[1]["params"]["N_t_bulk_m3"] == 3e20
    assert R[1]["interface_right"]["N_t_int_m2"] == 2e11
    assert R[0]["interface_right"]["N_t_int_m2"] == 4e12      # library default untouched
    assert R[2]["interface_right"] is None                     # last layer: contact, no interface
    lib = load_library()
    assert lib["materials"]["MAPbI3"]["params"]["N_t_bulk_m3"] == 1e20  # library not mutated


def _write_lib(tmp_path, mutate):
    lib = yaml.safe_load(open(load_library()["_path"], encoding="utf-8"))
    mutate(lib)
    p = tmp_path / "lib.yaml"
    p.write_text(yaml.safe_dump(lib))
    return p


@pytest.mark.parametrize("mutate,expect", [
    (lambda L: L.pop("interfaces"), "missing top-level key 'interfaces'"),
    (lambda L: L["materials"]["C60"].pop("roles"), "missing 'roles'"),
    (lambda L: L["materials"]["C60"]["thickness_nm"].update(min=200, max=100), "bad thickness bounds"),
    (lambda L: L["materials"]["MAPbI3"]["overridable"].update(foo={"min": 0, "max": 1}), "not one of its params"),
    (lambda L: L["interfaces"]["C60|MAPbI3"]["overridable"]["N_t_int_m2"].pop("min"), "needs min and max"),
    (lambda L: L["interfaces"]["C60|MAPbI3"]["params"].update(N_t_int_m2=1e16), "outside its own bounds"),
    (lambda L: L["materials"]["MAPbI3"]["params"].update(N_t_bulk_m3=1e25), "outside its own bounds"),
    (lambda L: L["interfaces"].update({"C60|Unobtainium": {"params": {}}}), "unknown material"),
])
def test_library_errors(tmp_path, mutate, expect):
    p = _write_lib(tmp_path, mutate)
    with pytest.raises(LibraryError, match=expect.replace("(", r"\(").replace("[", r"\[")):
        load_library(p)


def test_every_number_in_library_is_finite():
    """All params are finite numbers except explicitly string-valued ones (file names / 'none')."""
    string_keys = {"nk_file", "bulkTrapFile", "intTrapFile"}
    lib = load_library()
    for m in lib["materials"].values():
        for k, v in m["params"].items():
            if k in string_keys:
                assert isinstance(v, str), k
            else:
                assert isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v)), k
