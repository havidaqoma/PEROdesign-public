"""Paper A: objective mapping, metrics and search plumbing (no SimSS needed; fast)."""
import math

import pytest

from perodesign.library import load_library
from perodesign.optim import objective as O
from perodesign.optim import search as S
from perodesign.schema import validate


def test_spaces_come_from_library_bounds():
    lib = load_library()
    for arch, stack in O.STACKS.items():
        sp = O.space(arch)
        assert sp.dim == len(stack) + 1 and sp.names[-1] == "stripe_mm"
        for (role, mat), a, b in zip(stack, sp.lo, sp.hi):
            t = lib["materials"][mat]["thickness_nm"]
            assert (a, b) == (float(t["min"]), float(t["max"]))
        assert (sp.lo[-1], sp.hi[-1]) == O.STRIPE_MM
        assert sp.names[1] == "MAPbI3_nm"             # analysis assumes the absorber is index 1


def test_scenarios_move_top_p2_drivers_by_sqrt10():
    p = load_library()["materials"]["MAPbI3"]["params"]
    assert (p["N_t_bulk_m3"], p["mu_n_m2_Vs"]) == (O.LIB_NT, O.LIB_MU)
    w, b = O.SCENARIOS["worse"], O.SCENARIOS["better"]
    assert math.isclose(w["N_t_bulk_m3"] / O.LIB_NT, math.sqrt(10)) and math.isclose(O.LIB_MU / w["mu_n_m2_Vs"], math.sqrt(10))
    assert math.isclose(O.LIB_NT / b["N_t_bulk_m3"], math.sqrt(10)) and math.isclose(b["mu_n_m2_Vs"] / O.LIB_MU, math.sqrt(10))


@pytest.mark.parametrize("arch", ["p-i-n", "n-i-p"])
@pytest.mark.parametrize("scen", ["base", "worse", "better"])
def test_design_is_valid_at_box_corners(arch, scen):
    sp = O.space(arch)
    for x in (sp.lo, sp.hi, O.REFERENCE[arch]):
        d, g = O.design(arch, list(x), scen)
        validate(d)
        g.check()


def test_unit_round_trip_and_clipping():
    sp = O.space("p-i-n")
    x = O.REFERENCE["p-i-n"]
    assert all(math.isclose(a, b) for a, b in zip(O.from_unit(sp, O.to_unit(sp, x)), x))
    assert O.from_unit(sp, [-1, 2, 0.5, 0.5, 0.5])[:2] == [sp.lo[0], sp.hi[1]]


def test_reference_cost_matches_p1():
    """p-i-n reference at P1 module PCE 18.189 % must cost 0.427 USD/W (phase0/sim_bench/p1_my_bottom_up.json)."""
    d, _ = O.design("p-i-n", O.REFERENCE["p-i-n"])
    assert round(O.usd_per_W(d, 18.189336543476127)["usd_per_W"], 3) == 0.427


def test_reference_point_values():
    assert O.reference_point("p-i-n")[0] == O.PCE_FLOOR
    assert round(O.reference_point("p-i-n")[1], 3) == 1.854
    assert round(O.reference_point("n-i-p")[1], 2) == 49.58


def test_pareto_and_hv_exact():
    pts = [(20, 1.0), (18, 0.5), (15, 0.4), (17, 0.9), (10, 0.3)]
    assert S.pareto(pts) == [(20, 1.0), (18, 0.5), (15, 0.4), (10, 0.3)]
    ref = (5, 2.0)
    # strips: (10-5)*(2-0.3) + (15-10)*(2-0.4) + (18-15)*(2-0.5) + (20-18)*(2-1.0)
    assert math.isclose(S.hv2d(pts, ref), 5 * 1.7 + 5 * 1.6 + 3 * 1.5 + 2 * 1.0)
    assert S.hv2d([(4, 0.1), (30, 3.0)], ref) == 0.0          # outside the reference box
    log = [{"y": None}, {"y": [10, 0.3]}, {"y": [20, 1.0]}]
    assert S.hv_curve(log, ref) == [0.0, 5 * 1.7, 5 * 1.7 + 10 * 1.0]


def _fake(U):
    return [None if u[0] > 0.95 else (20 * (1 - (u[1] - 0.4) ** 2) - 3 * u[0], 0.3 + 0.5 * u[1] + 0.2 * u[2]) for u in U]


@pytest.mark.parametrize("method", ["random", "nsga2"])
def test_methods_use_exact_budget_and_are_seeded(method):
    a = S.run_method(method, _fake, 5, 1, (5.0, 1.85), budget=48)
    b = S.run_method(method, _fake, 5, 1, (5.0, 1.85), budget=48)
    assert len(a) == 48 and [r["u"] for r in a] == [r["u"] for r in b]
    assert all(0.0 <= v <= 1.0 for r in a for v in r["u"])


def test_all_methods_share_first_24_points():
    r = S.run_method("random", _fake, 4, 3, (5.0, 1.85), budget=24)
    n = S.run_method("nsga2", _fake, 4, 3, (5.0, 1.85), budget=24)
    assert [x["u"] for x in r] == [x["u"] for x in n]


def test_t_ci95():
    m, h = S.t_ci95([1, 2, 3, 4, 5])
    assert m == 3 and math.isclose(h, 2.7764451051977987 * math.sqrt(2.5) / math.sqrt(5))


def test_infeasible_fill_uses_worst_feasible_not_reference():
    ref = (5.0, 49.58)
    assert S.infeasible_fill([{"y": None}], ref) == ref
    log = [{"y": None}, {"y": [20.0, 11.2]}, {"y": [18.0, 11.5]}]
    assert S.infeasible_fill(log, ref) == (18.0, 11.5)


class _FakeSim:
    """Stands in for SimSS: returns fixed cell metrics so the module/cost path runs without the binary."""
    def __init__(self, pce, status="complete"):
        self.pce, self.status = pce, status

    def run(self, d):
        class R:
            pass
        r = R()
        r.status, r.reason, r.seconds, r.design_hash = self.status, None, 0.0, "h"
        mpp = self.pce * 10.0                               # W/m2 at 1000 W/m2
        r.metrics = {"pce_pct": self.pce, "mpp_W_m2": mpp, "vmpp_V": 0.9, "voc_V": 1.05, "ff": 0.8, "jsc_mA_cm2": 22.0}
        return r


def test_evaluate_marks_out_of_domain_pce_infeasible_without_crashing():
    x = O.REFERENCE["p-i-n"]
    assert O.evaluate(_FakeSim(1e-6), "p-i-n", x)["feasible"] is True
    r0 = O.evaluate(_FakeSim(0.0), "p-i-n", x)
    assert r0["feasible"] is False and "module" in r0["reason"]        # module model rejects J_mp = 0
    rf = O.evaluate(_FakeSim(20.0, status="failed"), "p-i-n", x)
    assert rf["feasible"] is False and rf["usd_per_W"] is None
    ok = O.evaluate(_FakeSim(20.0), "p-i-n", x)
    assert ok["feasible"] and 0 < ok["module_pce_pct"] < 20 and ok["usd_per_W"] > 0


def test_analyse_rules_on_fake_runs(tmp_path, monkeypatch):
    """Exercise scripts/paperA_run.analyse (the §7 rules) on synthetic run files: no SimSS, no real result."""
    import importlib.util
    import json
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("paperA_run", Path(__file__).resolve().parents[1] / "scripts" / "paperA_run.py")
    P = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(P)
    monkeypatch.setattr(P, "OUT", tmp_path)
    monkeypatch.setattr(P, "RUNS", tmp_path / "runs")
    (tmp_path / "runs").mkdir()
    for arch, scen, method, seed in P.jobs():
        sp = O.space(arch)
        calls = []
        for i in range(S.BUDGET):
            x = list(O.REFERENCE[arch])
            x[1] = 300 + i                                  # absorber sweep
            good = not (method == "random" and i < 13)       # 13 infeasible -> 'unreliable'
            pce = 15 + (3 if method == "qnehvi" else 0) + i / 100 + seed / 1000
            calls.append({"x": x, "feasible": good, "module_pce_pct": pce if good else None, "cell_pce_pct": pce,
                          "usd_per_W": (0.5 - i / 1000) if good else None, "usd_per_W_high_prices": 0.6,
                          "materials_usd_m2": 29.0, "design_hash": f"{method}{seed}{i:04d}"})
        rid = P.run_id(arch, scen, method, seed)
        (tmp_path / "runs" / f"{rid}.json").write_text(json.dumps(
            {"calls": calls, "n_infeasible": sum(not c["feasible"] for c in calls)}))
    res = P.analyse()
    c = res["cases"]["p-i-n/base"]
    assert c["unreliable"] is True                          # 13 > 12 in single random runs
    assert c["q1"]["qnehvi>random"] and c["q1"]["qnehvi>nsga2"] and not c["q1"]["random>qnehvi"]
    assert c["methods"]["random"]["calls_to_95pct_best_median"] == ">240"
    q2 = c["q2"]
    assert q2["pce_optimal"]["module_pce_pct"] >= q2["cost_optimal"]["module_pce_pct"]
    assert set(q2["pce_optimal"]["usd_per_W_by_rate_region"]) == {"MY", "CN", "IN"}
    assert res["q3"]["p-i-n"]["q1_robust"] is True and res["q3"]["p-i-n"]["designs_robust"] is True
    (tmp_path / "runs" / f"{P.run_id('n-i-p', 'worse', 'nsga2', 3)}.json").unlink()
    with pytest.raises(FileNotFoundError):
        P.analyse()
