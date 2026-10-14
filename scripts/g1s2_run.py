"""G1 step 2 simulations (docs/G1_step2_preregistration.md + amendments B1, B2). Runs in WSL next to the SimSS binary.
Library = production materials_v2.yaml + perodesign/library/g1s2_overlay.yaml, merged in memory (the production file is
not touched). Per device:
  * back-metal optics from the database back contact (Au/Ag/Al, SimSS nk files, L_BE 101 nm = SimSS default);
  * contacts (amendment B2): barrier-free band-edge work functions: cathode = E_c of the electron-side layer it
    touches, anode = E_v of the hole-side layer it touches (n-i-p: left = cathode; p-i-n: left = anode).
Case 'main' = sources verbatim; case 'S1' = TiO2-c doping flipped to N_D 9e22 / N_A 0 m^-3 (pre-declared sensitivity).
Measured values are NOT read or printed here.
Usage: python scripts/g1s2_run.py [main|S1] [workers]  -> phase0/g1s2/sim_<case>.json"""
import copy
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from perodesign.library import load_library
from perodesign.physics import simss
from perodesign.physics.simss import SimSS
from perodesign.schema import DesignError

REPO = Path(__file__).resolve().parents[1]
CASE = sys.argv[1] if len(sys.argv) > 1 else "main"
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 12
METAL_NK = {"Au": "nk_Au.txt", "Ag": "nk_Ag.txt", "Al": "nk_Al.txt"}
# Round switch (amendment C1): round 1 (default) = g1s2_overlay.yaml -> phase0/g1s2/; round 2 = g1s2r2_overlay.yaml ->
# phase0/g1s2/round2/. Designs, contacts (B2), solver (B3) are identical in both rounds.
ROUND = __import__("os").environ.get("G1S2_ROUND", "1")
OV_PATH = REPO / "perodesign" / "library" / ("g1s2_overlay.yaml" if ROUND == "1" else "g1s2r2_overlay.yaml")
OUT_DIR = REPO / "phase0" / "g1s2" / ("" if ROUND == "1" else "round2")
# p-i-n2 (4-layer p-i-n) uses the production p-i-n solver policy (full sweep): amendment B1
simss.SOLVER_ARGS_BY_ARCH.setdefault("p-i-n2", simss.SOLVER_ARGS_BY_ARCH["p-i-n"])
# Solver variant (preregistration §2 allows solver-only changes, applied to ALL step-2 runs and disclosed).
# 'reg' = production solver. Chosen variant is recorded in amendment B3 and in every result file.
SOLVER = __import__("os").environ.get("G1S2_SOLVER", "b3")
SOLVER_VARIANTS = {
    "reg": {},
    "np500": {"NP": 500},
    "np500_vmin0": {"NP": 500, "Vmin_V": 0},
    "np500_rev": {"NP": 500, "_reverse": True},
    # warm-up: start the sweep 0.1 V lower so the first few (settling) points lie outside [0, Vmpp]; the MPP rule
    # then only needs convergence from -0.04 V upward, as in production (amendment B3)
    "np500_vmin-0.14": {"NP": 500, "Vmin_V": -0.14},
    "b3": {"NP": 500, "timeout_s": 120},          # amendment B3: the registered step-2 solver
}
SV = SOLVER_VARIANTS[SOLVER]
if SV.get("_reverse"):                    # reverse sweep from Vmax down (full sweep), all architectures
    for a in ("n-i-p", "n-i-p2"):
        simss.SOLVER_ARGS_BY_ARCH[a] = ["-Vmax", "1.4", "-varFile", "none", "-untilVoc", "0"]
# Amendment B3 MPP-rule refinement (all step-2 runs): a non-converged point at NEGATIVE bias (outside the [0, Voc]
# power quadrant) is ignored, but only if the V = 0 point itself converged (so Jsc is a solved value, not an
# extrapolation). Non-convergence anywhere in [0, Vmpp] still fails the run, exactly as in production.
import re as _re                          # noqa: E402
_orig_parse = simss.parse_stdout


def _parse_b3(text):
    zero_ok = _re.search(r"^At Vint=\s*-?0\.000 converged", text, _re.M) is not None
    if zero_ok:
        text = _re.sub(r"^No convergence for Vint=\s*-\d[\d.]*.*$", "", text, flags=_re.M)
    return _orig_parse(text)


simss.parse_stdout = _parse_b3


def base_library():
    lib = copy.deepcopy(load_library())
    ov = yaml.safe_load(OV_PATH.read_text(encoding="utf-8"))
    lib["materials"].update(copy.deepcopy(ov["materials"]))
    for name, patch in ov["material_patches"].items():
        lib["materials"][name].update(copy.deepcopy(patch))
    lib["interfaces"].update(copy.deepcopy(ov["interfaces"]))
    lib["architectures"] = copy.deepcopy(ov["architectures"])
    lib["architecture_setup"] = copy.deepcopy(ov["architecture_setup"])
    if CASE == "S1":
        lib["materials"]["TiO2-c"]["params"].update({"N_D_m3": 9.0e22, "N_A_m3": 0})
    lib["device_setup"]["params"].update({k: v for k, v in SV.items() if not k.startswith("_")})
    if SV.get("_reverse"):
        for a in ("n-i-p", "n-i-p2"):
            lib["architecture_setup"][a]["Vscan"] = -1
    return lib


BASE = base_library()


def contacts(design):
    """Amendment B2: electrode work function = majority band edge of the layer it touches."""
    first, last = design["layers"][0]["material"], design["layers"][-1]["material"]
    p = lambda m: BASE["materials"][m]["params"]
    if design["architecture"].startswith("n-i-p"):          # left cathode (electron side), right anode
        return p(first)["E_c_eV"], p(last)["E_v_eV"]
    return p(first)["E_v_eV"], p(last)["E_c_eV"]             # p-i-n: left anode, right cathode


def step2_library(metal, wl, wr):
    lib = copy.deepcopy(BASE)
    for a in lib["architecture_setup"].values():
        a.update({"nkBE_file": METAL_NK[metal], "L_BE_m": 1.01e-7, "W_L_eV": wl, "W_R_eV": wr})
    lib["_sha256"] = hashlib.sha256((load_library()["_sha256"] + hashlib.sha256(OV_PATH.read_bytes()).hexdigest()
                                     + f"{metal}|{wl}|{wr}|{CASE}|B2|B3|{SOLVER}").encode()).hexdigest()
    return lib


_SIMS, _LOCK = {}, threading.Lock()


def sim_for(metal, wl, wr):
    key = (metal, wl, wr)
    with _LOCK:
        if key not in _SIMS:
            _SIMS[key] = SimSS(library=step2_library(metal, wl, wr), timeout_s=130,
                               work_root=Path.home() / "perodesign_p1" / "g1s2_work",
                               cache_dir=Path.home() / "perodesign_p1" / "g1s2_cache" / (f"{CASE}_{SOLVER}" if ROUND == "1" else f"r{ROUND}_{CASE}_{SOLVER}"))
        return _SIMS[key]


def run(job):
    kind, i, j, metal, d = job
    if CASE == "S1" and not any(L["material"] == "TiO2-c" for L in d["layers"]):
        return {"kind": kind, "i": i, "j": j, "status": "skipped", "reason": "no TiO2-c (S1 only changes TiO2)"}
    missing = sorted({L["material"] for L in d["layers"]} - set(BASE["materials"]))
    if missing:                                  # round 2 (C1): material without a qualifying source = not simulable
        return {"kind": kind, "i": i, "j": j, "status": "invalid", "reason": f"not in step-2 library: {missing}"}
    wl, wr = contacts(d)
    try:
        r = sim_for(metal, wl, wr).run(d)
    except DesignError as e:
        return {"kind": kind, "i": i, "j": j, "status": "invalid", "reason": "; ".join(e.problems)[:300]}
    return {"kind": kind, "i": i, "j": j, "status": r.status, "reason": r.reason, "metrics": r.metrics,
            "W_L_eV": wl, "W_R_eV": wr, "warnings": r.warnings[:3], "seconds": r.seconds, "design_hash": r.design_hash}


def main():
    D = json.loads((REPO / "phase0" / "g1s2" / "designs.json").read_text(encoding="utf-8"))
    jobs = [("series", i, j, s["back_metal"], p["design"]) for i, s in enumerate(D["series"])
            for j, p in enumerate(s["points"])]
    jobs += [("family", i, j, dv["back_metal"], dv["design"]) for i, f in enumerate(D["families"])
             for j, dv in enumerate(f["devices"])]
    print("jobs", len(jobs), "case", CASE, flush=True)
    out, n = [], 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for res in ex.map(run, jobs):
            out.append(res)
            n += 1
            if n % 50 == 0:
                st = {}
                for o in out:
                    st[o["status"]] = st.get(o["status"], 0) + 1
                print(n, st, flush=True)
    st = {}
    for o in out:
        st[(o["kind"], o["status"])] = st.get((o["kind"], o["status"]), 0) + 1
    any_sim = next(iter(_SIMS.values()))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"sim_{CASE}.json").write_text(json.dumps({
        "README": __doc__.split("Usage:")[0].strip(), "round": ROUND, "case": CASE, "solver_variant": SOLVER, "solver_settings": {k: v for k, v in SV.items()}, "binary_sha256": any_sim.binary_sha256,
        "overlay_sha256": hashlib.sha256(OV_PATH.read_bytes()).hexdigest(),
        "status_counts": {f"{k[0]}:{k[1]}": v for k, v in st.items()}, "results": out}, indent=0), encoding="utf-8")
    print("DONE", {f"{k[0]}:{k[1]}": v for k, v in st.items()}, flush=True)


if __name__ == "__main__":
    main()
