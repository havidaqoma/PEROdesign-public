"""SimSS wrapper: parser/classifier on REAL captured stdout, CLI mapping, and (marker 'simss')
end-to-end runs of the real binary against Phase 0 measured values."""
import json
import os
from pathlib import Path

import pytest

from perodesign.library import load_library
from perodesign.physics.simss import (INTERFACE_KEYMAP, LAYER_KEYMAP, SimSS, SimSSConfigError, classify,
                                      parse_stdout)
from perodesign.schema import DesignError, from_thicknesses

FIX = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIX / f"simss_{name}.txt").read_text(), json.loads((FIX / f"simss_{name}.meta.json").read_text())


# ------------------------------------------------------------------ parser + classifier (no binary needed)
def test_parse_complete_run():
    txt, meta = fixture("complete")
    assert meta["returncode"] == 0
    p = parse_stdout(txt)
    assert p["mpp_W_m2"] == 225.1 and p["voc_V"] == 1.2235 and p["ff"] == 0.806
    assert p["jsc_A_m2"] == -228.2527 and p["vmpp_V"] == 1.07
    status, reason, m, _ = classify(p)
    assert status == "complete" and reason is None
    assert m["pce_pct"] == pytest.approx(22.51) and m["jsc_mA_cm2"] == pytest.approx(22.82527)


def test_parse_partial_run_keeps_mpp_drops_voc():
    txt, meta = fixture("partial")
    assert meta["returncode"] == 95
    p = parse_stdout(txt)
    assert p["could_not_determine"] and p["voc_V"] is None and p["ff"] is None
    assert p["n_conv_above_vmpp"] >= 2 and p["first_nonconv_V"] == pytest.approx(1.08)
    status, reason, m, warns = classify(p)
    assert status == "partial" and m["pce_pct"] == pytest.approx(13.55)
    assert m["voc_V"] is None and m["ff"] is None and warns          # never guessed


def test_parse_thick_htl_run():
    """PTAA 100 nm (outside the design bounds): Vmpp 0.94 V, first non-convergence 1.20 V, 12 contiguous
    converged points in between (counted from the captured file) -> bracketed -> partial, PCE 18.20%."""
    txt, _ = fixture("failed_thick_htl")
    p = parse_stdout(txt)
    assert p["vmpp_V"] == 0.94 and p["first_nonconv_V"] == 1.2 and p["n_conv_above_vmpp"] == 12
    status, _, m, _ = classify(p)
    assert status == "partial" and m["pce_pct"] == pytest.approx(18.20)


@pytest.mark.parametrize("name,vmpp,mpp,status", [
    ("pin_liu", 1.01, 198.4, "complete"),
    ("pin_thin", 1.04, 213.3, "complete"),
    ("pin_thick_htl", 0.987, 151.2, "complete"),     # rc 95: 3 points ABOVE Voc failed (1.40-1.36 V), all params printed
])
def test_parse_downward_pin_sweeps(name, vmpp, mpp, status):
    """p-i-n sweeps run DOWN (Vscan -1). Values checked against max(-V*J) of the run's JV.dat
    (scripts/pin_parser_check.py): 198.4 / 213.3 / 151.2 W/m2 at 1.02 / 1.04 / 0.98 V."""
    txt, meta = fixture(name)
    assert meta["architecture"] == "p-i-n"
    p = parse_stdout(txt)
    assert p["vmpp_V"] == vmpp and p["mpp_W_m2"] == mpp
    s, _, m, _ = classify(p)
    assert s == status and m["jsc_mA_cm2"] > 0 and m["voc_V"] > m["vmpp_V"]
    if name == "pin_thick_htl":
        assert p["first_nonconv_V"] == 1.36 and p["nonconv_below_vmpp"] is False


def _parsed(**kw):
    base = {"jsc_A_m2": -200.0, "vmpp_V": 1.0, "mpp_W_m2": 200.0, "voc_V": 1.2, "ff": 0.8,
            "could_not_determine": False, "finished": True, "n_converged": 60, "n_nonconverged": 0,
            "first_nonconv_V": None, "n_conv_above_vmpp": 10, "n_conv_below_vmpp": 50,
            "nonconv_below_vmpp": False}
    base.update(kw)
    return base


@pytest.mark.parametrize("kw,status,frag", [
    ({"mpp_W_m2": None}, "failed", "no MPP"),
    ({"n_conv_above_vmpp": 1}, "failed", "not bracketed"),
    ({"mpp_W_m2": 400.0}, "failed", "sanity gate"),          # 40% > SQ gate
    ({"mpp_W_m2": -5.0}, "failed", "sanity gate"),
    ({"jsc_A_m2": 10.0}, "failed", "non-generating"),
    ({"ff": 1.3}, "failed", "FF"),
    ({"voc_V": None}, "partial", "Voc/FF"),
    ({"jsc_A_m2": None}, "partial", "Jsc missing"),                       # never 'complete' without Jsc
    ({"n_conv_below_vmpp": 1}, "failed", "below"),                        # peak at the sweep start
    ({"nonconv_below_vmpp": True, "first_nonconv_V": 0.9}, "failed", "non-converged point"),
    ({"vmpp_V": -0.1}, "failed", "not positive"),
    ({"vmpp_V": 1.3}, "failed", "Vmpp < Voc"),
    ({}, "complete", None),
])
def test_classify_rules(kw, status, frag):
    s, reason, _, _ = classify(_parsed(**kw))
    assert s == status
    if frag:
        assert frag in reason
    else:
        assert reason is None


def test_gap_above_vmpp_is_not_bracketing():
    """agy review: converged points AFTER a non-converged gap must not count as bracketing."""
    lines = [f"At Vint={v:.3f} converged in 10 loop(s), Jext=-100.00 +- 0.00" for v in (0.0, 0.2, 0.4, 0.6, 0.8)]
    lines += ["No convergence for Vint=0.920", "No convergence for Vint=0.940"]
    lines += [f"At Vint={v:.3f} converged in 10 loop(s), Jext=50.00 +- 0.00" for v in (1.38, 1.40)]
    lines += ["Jsc:  -200.0 +/- 0.0   A/m2", "Vmpp: 0.90 +/- 0.01  V", "MPP:  180.0 +/- 0.3  W/m2",
              "Could not determine (all) solar cell parameters."]
    p = parse_stdout("\n".join(lines))
    assert p["n_conv_above_vmpp"] == 0
    assert classify(p)[0] == "failed"


def test_parse_garbage():
    p = parse_stdout("segfault\n")
    assert classify(p)[0] == "failed"


def test_keymaps_and_library_match_exactly():
    """Every material defines EVERY mapped layer key, every interface every interface key, and
    device_setup every setup key: nothing can fall back to a template value."""
    from perodesign.physics.simss import SETUP_KEYMAP
    lib = load_library()
    for name, m in lib["materials"].items():
        assert set(m["params"]) == set(LAYER_KEYMAP), (name, set(m["params"]) ^ set(LAYER_KEYMAP))
    for pair, it in lib["interfaces"].items():
        assert set(it["params"]) == set(INTERFACE_KEYMAP), (pair, set(it["params"]) ^ set(INTERFACE_KEYMAP))
    assert set(lib["device_setup"]["params"]) == set(SETUP_KEYMAP)


def test_keymaps_cover_every_template_parameter():
    """Compare against the ACTUAL SimSS template files (captured in Phase 0), not against the keymap itself."""
    from perodesign.physics.simss import NOT_PASSED, SETUP_KEYMAP
    d = json.loads((Path(__file__).parents[1] / "phase0/sim_bench/simss_default_params.json").read_text())
    layer_names = set(LAYER_KEYMAP.values()) | set(INTERFACE_KEYMAP.values()) | {"L"}
    for f in ("L1_parameters.txt", "L2_parameters.txt", "L3_parameters.txt"):
        assert set(d[f]) - layer_names == set(), (f, set(d[f]) - layer_names)
    left = set(d["simulation_setup.txt"]) - set(SETUP_KEYMAP.values()) - NOT_PASSED
    assert left == set(), left


# ------------------------------------------------------------------ real binary
def _sim(tmp_path, **kw):
    try:
        return SimSS(work_root=tmp_path / "work", **kw)
    except SimSSConfigError as e:
        pytest.skip(f"SimSS not available: {e}")


@pytest.mark.simss
def test_config_error_on_missing_install(tmp_path):
    with pytest.raises(SimSSConfigError):
        SimSS(simss_dir=tmp_path / "nope", work_root=tmp_path)


@pytest.mark.simss
def test_args_are_explicit_and_si(tmp_path):
    s = _sim(tmp_path)
    a = s.build_args(from_thicknesses(500, 10, 10))
    kv = dict(zip(a[0::2], a[1::2]))
    assert kv["-l2.L"] == "5.000000e-07" and kv["-l1.L"] == "1.000000e-08" and kv["-l3.L"] == "1.000000e-08"
    assert kv["-Vmax"] == "1.4" and kv["-untilVoc"] == "1" and kv["-varFile"] == "none"
    assert kv["-l2.N_t_bulk"] == "1.000000e+20" and kv["-l1.N_t_int"] == "4.000000e+12"
    assert kv["-l2.nkLayer"].endswith("Data/nk_MAPI.txt")
    assert "-l3.N_t_int" not in kv                    # last layer: no interface to the right
    assert kv["-T"] == "295" and kv["-W_L"] == "4.050000e+00" and kv["-genProfile"] == "calc"
    assert kv["-spectrum"].endswith("Data/AM15G.txt") and kv["-NP"] == "250"
    # every L2 template key appears on the command line (compared with the real file, not the keymap)
    from perodesign.physics.simss import _template_keys
    for k in _template_keys(s.simss_dir / "L2_parameters.txt"):
        assert f"-l2.{k}" in kv, k


@pytest.mark.simss
def test_invalid_design_never_runs(tmp_path):
    s = _sim(tmp_path)
    with pytest.raises(DesignError):
        s.run(from_thicknesses(150, 10, 10))
    assert not list((tmp_path / "work").glob("simss_*"))


@pytest.mark.simss
def test_grid_best_reproduces_phase0(tmp_path):
    """Phase 0 grid best 500/10/10 = 22.51% (landscape_grid45.json, grid_recheck.json)."""
    r = _sim(tmp_path).run(from_thicknesses(500, 10, 10))
    assert r.status == "complete", r.reason
    assert r.metrics["pce_pct"] == pytest.approx(22.51, abs=0.01)
    assert r.metrics["voc_V"] == pytest.approx(1.2235, abs=1e-3)
    assert r.provenance["library_sha256"] == load_library()["_sha256"]
    assert not list((tmp_path / "work").glob("simss_*")), "run dir not cleaned"


@pytest.mark.simss
def test_phase0_designs_reproduce(tmp_path):
    """Designs re-simulated in Phase 0 (grid_recheck.json) reproduce through the new wrapper."""
    rows = json.loads((Path(__file__).parents[1] / "phase0/grpo_smoke/grid_recheck.json").read_text())
    s = _sim(tmp_path)
    res = s.run_many([from_thicknesses(r["design"]["absorber_nm"], r["design"]["etl_nm"], r["design"]["htl_nm"])
                      for r in rows], workers=4)
    for row, r in zip(rows, res):
        assert r.status in ("complete", "partial"), r.reason
        assert r.metrics["pce_pct"] == pytest.approx(row["sim"]["PCE_pct"], abs=0.01), row["design"]


@pytest.mark.simss
def test_template_with_unknown_parameter_is_refused(tmp_path):
    import shutil
    base = _sim(tmp_path)
    tpl = tmp_path / "tpl_extra"
    shutil.copytree(base.simss_dir, tpl, ignore=shutil.ignore_patterns("*.dat", "log.txt", "scPars.txt", "none"))
    txt = (tpl / "L2_parameters.txt").read_text(errors="replace")
    (tpl / "L2_parameters.txt").write_text(txt.replace("mu_n = ", "newKnob = 1  * hypothetical\nmu_n = ", 1))
    with pytest.raises(SimSSConfigError, match="newKnob"):
        SimSS(simss_dir=tpl, data_dir=base.data_dir, work_root=tmp_path / "w")


@pytest.mark.simss
def test_cache_key_depends_on_template_files(tmp_path):
    import shutil
    base = _sim(tmp_path)
    tpl = tmp_path / "tpl_edit"
    shutil.copytree(base.simss_dir, tpl, ignore=shutil.ignore_patterns("*.dat", "log.txt", "scPars.txt", "none"))
    (tpl / "simulation_setup.txt").write_text((tpl / "simulation_setup.txt").read_text(errors="replace") + "\n** edited\n")
    other = SimSS(simss_dir=tpl, data_dir=base.data_dir, work_root=tmp_path / "w")
    assert other._cache_key("x") != base._cache_key("x")


@pytest.mark.simss
def test_parallel_cache_writes_are_atomic(tmp_path):
    s = _sim(tmp_path, cache_dir=tmp_path / "cache")
    d = from_thicknesses(absorber_nm=450, etl_nm=20, htl_nm=20)
    res = s.run_many([d] * 8, workers=8)            # 8 threads race on the same cache key
    assert len({json.dumps(r.metrics, sort_keys=True) for r in res}) == 1
    files = list((tmp_path / "cache").iterdir())
    assert [f.suffix for f in files] == [".json"]     # no leftover temp files
    json.loads(files[0].read_text())                  # complete, parseable
    (files[0]).write_text("{truncated")               # corrupt entry -> ignored, re-simulated
    assert s.run(d).metrics == res[0].metrics


@pytest.mark.simss
def test_deterministic_and_cached(tmp_path):
    s = _sim(tmp_path, cache_dir=tmp_path / "cache")
    d = from_thicknesses(420, 25, 30)
    a = s.run(d)
    b = SimSS(work_root=tmp_path / "work").run(d)          # fresh, uncached
    assert a.metrics == b.metrics and a.design_hash == b.design_hash
    c = s.run(d)                                            # from cache
    assert c.metrics == a.metrics and len(list((tmp_path / "cache").glob("*.json"))) == 1


@pytest.mark.simss
def test_stale_template_result_file_is_ignored(tmp_path):
    """Phase 0 bug: a scPars.txt in the template made failed runs look valid. Plant one and a
    bogus JV.dat in a COPY of the template dir; the result must not change."""
    import shutil
    base = _sim(tmp_path)
    tpl = tmp_path / "tpl"
    shutil.copytree(base.simss_dir, tpl, ignore=shutil.ignore_patterns("*.dat", "log.txt", "scPars.txt", "none"))
    (tpl / "scPars.txt").write_text("Jsc Voc FF MPP\n-999 9 0.99 999\n")
    s2 = SimSS(simss_dir=tpl, data_dir=base.data_dir, work_root=tmp_path / "w2")
    d = from_thicknesses(500, 10, 10)
    assert s2.run(d).metrics == base.run(d).metrics


@pytest.mark.simss
def test_override_changes_result(tmp_path):
    s = _sim(tmp_path)
    lo = from_thicknesses(500, 10, 10)
    hi = from_thicknesses(500, 10, 10)
    hi["layers"][1]["overrides"] = {"N_t_bulk_m3": 1e22}
    r_lo, r_hi = s.run_many([lo, hi], workers=2)
    assert r_hi.metrics["pce_pct"] < r_lo.metrics["pce_pct"] - 1.0   # 100x more bulk traps must hurt
