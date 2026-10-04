"""P2 sensitivity guards (docs/P2_sensitivity_preregistration.md):
- the script's parameters, ranges, N and seed are the registered ones;
- the committed result follows from sims.jsonl with the committed script and follows the method rule.
  The fast test rebuilds the outputs (percentiles, usable rows, status counts) and checks the ranking rules.
  The full index recompute (46 delta jobs x 1,000 resamples, a few minutes) runs only with PERODESIGN_SLOW=1."""
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
S = REPO / "phase0" / "sensitivity"
pytest.importorskip("SALib")
import p2_sensitivity as P  # noqa: E402

RUN = pytest.mark.skipif(not (S / "result.json").exists(), reason="sensitivity not run")

def test_registered_design_and_sampling():
    assert (P.N, P.SEED) == (512, 3407)
    assert [(L["material"], L["thickness_nm"]) for L in P.DESIGN["layers"]] == [("NiOx", 15), ("MAPbI3", 600), ("C60", 30), ("SnO2", 10)]
    assert len(P.PHYS) == 15 and len(P.COST) == 8
    X = P.sample()
    assert X.shape == (512 * 25, 23)
    assert len({P.phys_key(r) for r in X}) == 512 * 17
    assert P.RESAMPLES == 1000                               # §3 / §5: 1,000 bootstrap resamples


def test_ranges_follow_the_convention():
    from perodesign.library import load_library
    lib = load_library()
    for name, kind, lo, hi, t in P.PHYS:
        if t[0] == "ion":
            base = lib["materials"]["MAPbI3"]["params"]["N_anion_m3"]
        elif t[0] == "m":
            base = lib["materials"][t[1]]["params"][t[2]]
        else:
            base = lib["interfaces"][t[1]]["params"][t[2]]
        if kind == "log":      # x/÷10 around the library value
            assert (lo, hi) == pytest.approx((math.log10(base) - 1, math.log10(base) + 1)), name
        else:                  # ±0.1 eV
            assert (lo, hi) == pytest.approx((base - 0.1, base + 0.1)), name
    c = {p[0]: p for p in P.COST}
    assert c["C1 capital rate"][2:4] == pytest.approx((0.0482472886111111, 0.102))   # WDI MY lending, Kajal WACC


@RUN
def test_result_follows_sims_and_rules():
    committed = json.loads((S / "result.json").read_text())
    sims = [json.loads(ln) for ln in (S / "sims.jsonl").read_text().splitlines() if ln.strip()]
    assert len({tuple(s["key"]) for s in sims}) == committed["n_unique_sims"] == 512 * 17
    assert committed["method"] == ("sobol_ST" if all(s["status"] == "complete" for s in sims) else "borgonovo_delta")
    X, Y1, Y2, YM, ok, stat, *_ = P.outputs()
    assert committed["sim_status"] == stat and committed["rows_usable"] == int(ok.sum())
    assert committed["module_pce_p5_p50_p95"] == pytest.approx([float(np.percentile(YM[ok], q)) for q in (5, 50, 95)])
    if committed["method"] == "borgonovo_delta":
        e = committed["delta_estimator"]
        assert (e["index"], e["robustness_check"], e["num_resamples"]) == ("delta_raw", "delta_balanced", 1000)
    for name, Y in (("cell_pce_pct", Y1), ("usd_per_W", Y2)):
        o = committed["outputs"][name]
        assert o["n"] == int(ok.sum())
        assert o["p5_p50_p95"] == pytest.approx([float(np.percentile(Y[ok], q)) for q in (5, 50, 95)])
        rk = o["ranking"]
        assert sorted(r["param"] for r in rk) == sorted(P.NAMES)
        assert [r["index"] for r in rk] == sorted((r["index"] for r in rk), reverse=True)
        assert o["top5"] == [r["param"] for r in rk[:5]]
        r5, r6 = rk[4], rk[5]
        assert o["top5_resolved"] == (r5["index"] - r5["ci95_half"] > r6["index"] + r6["ci95_half"])


@RUN
@pytest.mark.skipif(os.environ.get("PERODESIGN_SLOW") != "1", reason="full delta recompute ~70 min; set PERODESIGN_SLOW=1")
def test_result_recomputes(tmp_path):
    committed = json.loads((S / "result.json").read_text())
    work = tmp_path / "phase0" / "sensitivity"
    work.mkdir(parents=True)
    shutil.copy(S / "sims.jsonl", work / "sims.jsonl")
    out = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(REPO / 'scripts')!r}); import p2_sensitivity as P; "
                          f"from pathlib import Path; P.OUT = Path({str(work)!r}); P.analyse()"],
                         cwd=REPO, capture_output=True, text=True, env=os.environ)
    assert out.returncode == 0, out.stderr[-800:]
    again = json.loads((work / "result.json").read_text())
    for k in ("cell_pce_pct", "usd_per_W"):
        assert again["outputs"][k]["top5"] == committed["outputs"][k]["top5"]
        assert [r["index"] for r in again["outputs"][k]["ranking"]] == pytest.approx(
            [r["index"] for r in committed["outputs"][k]["ranking"]])
