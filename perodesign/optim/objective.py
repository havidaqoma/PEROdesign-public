"""Paper A objective: design vector -> validated design -> SimSS -> module -> factory-gate USD/W (Malaysia).

Everything here is fixed by docs/PaperA_preregistration.md. Nothing is fitted or tuned.

Search spaces (thickness bounds read from the physics library, stripe width from the pre-registration):
  p-i-n  NiOx / MAPbI3 / C60 / SnO2 (+ Cu)   4 thicknesses + stripe width  -> 5-D
  n-i-p  C60 / MAPbI3 / PTAA (+ Au)          3 thicknesses + stripe width  -> 4-D
Scenarios move the two top P2 drivers (MAPbI3 N_t_bulk, mu_n) by x/÷ sqrt(10) through design overrides.
Objectives: maximise module PCE (%), minimise USD/W (base prices). A failed sim or a module-model error is
infeasible: it uses a call and gets no objective value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from perodesign.library import load_library
from perodesign.module import ModuleError, ModuleGeometry, module_from_cell
from perodesign.tea import Tagged, evaluate_cost, materials_per_m2, cost_per_watt, region_line, region_line_MY_bottom_up

SCHEMA = "perodesign.design/1"
STRIPE_MM = (2.0, 10.0)                                    # pre-registered search range
DEAD_MM, TCO_OHM_SQ, EDGE = 0.2, 10.0, 0.03               # fixed; same assumed geometry as P1/P2
GEOMETRY_TAG = "assumed:dead 0.2 mm / 10 ohm/sq / 3% edges (P1 scenario, not sourced)"
PCE_FLOOR = 5.0                                            # module PCE (%) of the hypervolume reference point
# PTAA has no open-access density; same labelled assumption as scripts/compare_devices.py
ASM = {"density:PTAA": {"g_cm3": 1.1, "note": "ASSUMED: no open-access PTAA density found (amorphous polymer ~1.1)"}}

STACKS = {
    "p-i-n": [("HTL", "NiOx"), ("absorber", "MAPbI3"), ("ETL", "C60"), ("buffer", "SnO2")],
    "n-i-p": [("ETL", "C60"), ("absorber", "MAPbI3"), ("HTL", "PTAA")],
}
# reference (starting) designs: Liu 2025 industrial stack and the P1 lab-grid best, both at 6 mm stripes
REFERENCE = {"p-i-n": [15, 600, 30, 10, 6.0], "n-i-p": [10, 500, 10, 6.0]}

LIB_NT, LIB_MU = 1.0e20, 1.0e-4                            # MAPbI3 library values (checked in the tests)
S10 = math.sqrt(10.0)
SCENARIOS = {
    "base": {},
    "worse": {"N_t_bulk_m3": LIB_NT * S10, "mu_n_m2_Vs": LIB_MU / S10},
    "better": {"N_t_bulk_m3": LIB_NT / S10, "mu_n_m2_Vs": LIB_MU * S10},
}


@dataclass(frozen=True)
class Space:
    arch: str
    names: tuple
    lo: tuple
    hi: tuple

    @property
    def dim(self) -> int:
        return len(self.names)


def space(arch: str, library: dict | None = None) -> Space:
    lib = library or load_library()
    names, lo, hi = [], [], []
    for role, mat in STACKS[arch]:
        t = lib["materials"][mat]["thickness_nm"]
        names.append(f"{mat}_nm")
        lo.append(float(t["min"]))
        hi.append(float(t["max"]))
    names.append("stripe_mm")
    lo.append(STRIPE_MM[0])
    hi.append(STRIPE_MM[1])
    return Space(arch, tuple(names), tuple(lo), tuple(hi))


def to_unit(sp: Space, x) -> list[float]:
    return [(v - a) / (b - a) for v, a, b in zip(x, sp.lo, sp.hi)]


def from_unit(sp: Space, u) -> list[float]:
    return [a + min(max(float(v), 0.0), 1.0) * (b - a) for v, a, b in zip(u, sp.lo, sp.hi)]


def design(arch: str, x, scenario: str = "base") -> tuple[dict, ModuleGeometry]:
    """Physical vector x (thicknesses in nm in stack order, then stripe mm) -> (design dict, module geometry).
    Thicknesses are rounded to 0.1 nm and stripe width to 0.01 mm, so equal designs share a cache hash."""
    n = len(STACKS[arch])
    if len(x) != n + 1:
        raise ValueError(f"{arch}: expected {n + 1} values, got {len(x)}")
    layers = []
    for (role, mat), t in zip(STACKS[arch], x[:n]):
        L = {"role": role, "material": mat, "thickness_nm": round(float(t), 1)}
        if role == "absorber" and SCENARIOS[scenario]:
            L["overrides"] = dict(SCENARIOS[scenario])
        layers.append(L)
    geom = ModuleGeometry(round(float(x[n]), 2), DEAD_MM, TCO_OHM_SQ, EDGE)
    return {"schema": SCHEMA, "architecture": arch, "layers": layers}, geom


def cost_line(region: str = "MY"):
    """Malaysia bottom-up line (P2 base). CN/IN: the same line with only the capital rate swapped (A3)."""
    line = region_line_MY_bottom_up()
    if region != "MY":
        line.rate = region_line(region).rate
        line.name += f" [rate from {region}]"
    return line


def usd_per_W(d: dict, module_pce_pct: float, line=None) -> dict:
    line = line or cost_line()
    r = evaluate_cost(d, module_pce_pct, line, assumptions=ASM)
    if r["usd_per_W"] is None:
        raise RuntimeError(f"cost incomplete: {r.get('reason')}")
    return {"usd_per_W": r["usd_per_W"], "usd_per_W_high_prices": r["usd_per_W_high_prices"],
            "cost_status": r["status"], "materials_usd_m2": r["materials"]["total_usd_m2"]}


def reference_point(arch: str) -> tuple[float, float]:
    """(module PCE %, USD/W) of the hypervolume reference point, fixed before any run: PCE_FLOOR, and the USD/W of
    the most material-hungry design in the space (every thickness at its maximum) at that PCE."""
    sp = space(arch)
    d, _ = design(arch, list(sp.hi))
    return PCE_FLOOR, usd_per_W(d, PCE_FLOOR)["usd_per_W"]


def evaluate(sim, arch: str, x, scenario: str = "base") -> dict:
    """One simulator call. Returns a flat JSON-able record; feasible=False for failed/partial sims or module errors."""
    d, geom = design(arch, x, scenario)
    r = sim.run(d)
    rec = {"arch": arch, "scenario": scenario, "x": [L["thickness_nm"] for L in d["layers"]] + [geom.stripe_width_mm],
           "design_hash": r.design_hash, "sim_status": r.status, "reason": r.reason, "seconds": r.seconds,
           "cell_pce_pct": r.metrics.get("pce_pct"), "voc_V": r.metrics.get("voc_V"), "ff": r.metrics.get("ff"),
           "jsc_mA_cm2": r.metrics.get("jsc_mA_cm2"), "feasible": False, "module_pce_pct": None, "usd_per_W": None}
    if r.status != "complete":
        return rec
    try:
        m = module_from_cell(r.metrics, geom)
    except ModuleError as e:
        rec["reason"] = f"module: {e}"
        return rec
    rec.update(gff=m["gff"], p_tco=m["p_tco"])
    if not 0 < m["module_pce_pct"] < 40:          # cost engine domain (tea.cost_per_watt); outside it = infeasible
        rec["reason"] = f"module PCE {m['module_pce_pct']} outside (0, 40)"
        return rec
    rec.update(module_pce_pct=m["module_pce_pct"], **usd_per_W(d, m["module_pce_pct"]))
    rec["feasible"] = math.isfinite(rec["usd_per_W"])
    return rec


__all__ = ["STACKS", "SCENARIOS", "REFERENCE", "space", "to_unit", "from_unit", "design", "evaluate",
           "reference_point", "usd_per_W", "cost_line", "materials_per_m2", "cost_per_watt", "Tagged"]
