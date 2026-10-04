"""Paper B objective: mixed design (material choice + thicknesses) -> SimSS -> module -> factory-gate USD/W (Malaysia).

Fixed by docs/PaperB_preregistration.md. Paper A's objective (objective.py) is untouched and reused for the module
geometry, scenarios, cost line and PTAA density assumption.

Search space per stack (Paper A stacks, plus two categorical choices):
  categorical  HTL   in (NiOx, PTAA)          metal in (Cu, Ag, Au)      -> 6 material combinations per stack
  continuous   p-i-n: HTL, MAPbI3, C60, SnO2 thickness + stripe width   (5)
               n-i-p: C60, MAPbI3, HTL thickness + stripe width         (4)
The HTL thickness is one unit coordinate mapped onto the CHOSEN HTL's own library bounds (NiOx 5-40, PTAA 10-70 nm).

Physics per combination (perodesign/library/paperB_overlay.yaml): McPeak 2015 optics for every metal at the
production metal thickness of the architecture, transferred SimSS-default interfaces for the two new pairs, and
contact rule B2 (work function = majority band edge of the touching layer). `contact_rule="production"` with
`optics="production"` returns the production library object itself (baseline reproduction gate vs Paper A).

Objectives: maximise module PCE (%), minimise USD/W. The optimisers see log10(USD/W) (Au and Cu differ by ~30x).
"""
from __future__ import annotations

import copy
import hashlib
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from perodesign.library import LIB_DIR, load_library
from perodesign.module import ModuleError, ModuleGeometry, module_from_cell
from perodesign.tea import evaluate_cost

from . import objective as A

SCHEMA = A.SCHEMA
OVERLAY_PATH = LIB_DIR / "paperB_overlay.yaml"
HTLS = ("NiOx", "PTAA")
METALS = ("Cu", "Ag", "Au")
CATS = (("HTL", HTLS), ("metal", METALS))
PRODUCTION_COMBO = {"p-i-n": ("NiOx", "Cu"), "n-i-p": ("PTAA", "Au")}
# stack templates: None marks the HTL slot (material chosen); others fixed as in Paper A
STACKS = {
    "p-i-n": [("HTL", None), ("absorber", "MAPbI3"), ("ETL", "C60"), ("buffer", "SnO2")],
    "n-i-p": [("ETL", "C60"), ("absorber", "MAPbI3"), ("HTL", None)],
}
PCE_FLOOR = A.PCE_FLOOR
SCENARIOS = A.SCENARIOS


def overlay() -> dict:
    return yaml.safe_load(OVERLAY_PATH.read_text(encoding="utf-8"))


def overlay_sha256() -> str:
    return hashlib.sha256(OVERLAY_PATH.read_bytes()).hexdigest()


# ------------------------------------------------------------------ physics library per combination
@lru_cache(maxsize=64)
def physics_library(arch: str, htl: str, metal: str, contact_rule: str = "B2", optics: str = "mcpeak") -> dict:
    """Library for one (stack, HTL, metal). Cached: the same object is returned for the same arguments."""
    if htl not in HTLS or metal not in METALS or arch not in STACKS:
        raise ValueError(f"unknown combination {arch}/{htl}/{metal}")
    if contact_rule not in ("B2", "metal_wf", "production") or optics not in ("mcpeak", "production"):
        raise ValueError(f"contact_rule {contact_rule!r} / optics {optics!r}")
    base = load_library()
    prod = PRODUCTION_COMBO[arch] == (htl, metal)
    if contact_rule == "production" and optics == "production":
        if not prod:
            raise ValueError(f"production physics exists only for {PRODUCTION_COMBO[arch]} in {arch}")
        return base
    if contact_rule == "production" and htl != PRODUCTION_COMBO[arch][0]:
        raise ValueError("production contacts are defined only for the production HTL of each stack")
    ov = overlay()
    lib = copy.deepcopy(base)
    lib["interfaces"].update(copy.deepcopy(ov["interfaces"]))
    setup = lib.setdefault("architecture_setup", {}).setdefault(arch, {})
    if optics == "production":
        if metal != PRODUCTION_COMBO[arch][1]:
            raise ValueError("production optics exist only for the production metal of each stack")
    else:
        setup["nkBE_file"] = ov["metals"][metal]
        setup["L_BE_m"] = float(ov["metal_thickness_m"][arch])
    if contact_rule in ("B2", "metal_wf"):
        wl, wr = b2_contacts(arch, htl, lib)
        if contact_rule == "metal_wf":          # sensitivity S-WF (n-i-p only): anode = bare metal work function
            if arch != "n-i-p":
                raise ValueError("metal_wf contacts apply to n-i-p only (p-i-n metal sits behind ITO)")
            wr = float(ov["metal_work_function_eV"][metal])
        setup["W_L_eV"], setup["W_R_eV"] = wl, wr
    tag = f"paperB|{arch}|{htl}|{metal}|{contact_rule}|{optics}"
    lib["_sha256"] = hashlib.sha256((base["_sha256"] + overlay_sha256() + tag).encode()).hexdigest()
    lib["_path"] = f"{base['_path']} + {OVERLAY_PATH.name} [{tag}]"
    return lib


def b2_contacts(arch: str, htl: str, lib: dict | None = None) -> tuple[float, float]:
    """(W_L, W_R) in eV. n-i-p: left cathode on C60 (E_c), right anode on the HTL (E_v).
    p-i-n: left anode on the HTL (E_v), right cathode on SnO2 (E_c)."""
    p = lambda m: (lib or load_library())["materials"][m]["params"]  # noqa: E731
    if arch == "n-i-p":
        return float(p("C60")["E_c_eV"]), float(p(htl)["E_v_eV"])
    return float(p(htl)["E_v_eV"]), float(p("SnO2")["E_c_eV"])


def physics_setup(lib: dict, arch: str) -> dict:
    """device_setup SimSS uses for this library + architecture (ideal contact scenario = no further override)."""
    s = dict(lib["device_setup"]["params"])
    s.update((lib.get("architecture_setup") or {}).get(arch, {}))
    return s


# ------------------------------------------------------------------ space
@dataclass(frozen=True)
class SpaceB:
    arch: str
    names: tuple          # continuous names, in stack order, then stripe_mm
    cat_names: tuple      # ("HTL", "metal")
    cat_values: tuple     # (HTLS, METALS)

    @property
    def n_cont(self) -> int:
        return len(self.names)

    @property
    def n_cat(self) -> int:
        return len(self.cat_names)

    @property
    def dim(self) -> int:
        return self.n_cont + self.n_cat

    @property
    def cat_sizes(self) -> tuple:
        return tuple(len(v) for v in self.cat_values)


def space(arch: str) -> SpaceB:
    names = [("HTL_nm" if mat is None else f"{mat}_nm") for _, mat in STACKS[arch]] + ["stripe_mm"]
    return SpaceB(arch, tuple(names), tuple(n for n, _ in CATS), tuple(v for _, v in CATS))


def bounds(arch: str, htl: str) -> tuple[list[float], list[float]]:
    """Physical bounds of the continuous variables for a given HTL choice."""
    lib = load_library()
    lo, hi = [], []
    for _, mat in STACKS[arch]:
        t = lib["materials"][mat or htl]["thickness_nm"]
        lo.append(float(t["min"]))
        hi.append(float(t["max"]))
    return lo + [A.STRIPE_MM[0]], hi + [A.STRIPE_MM[1]]


def decode_relaxed(sp: SpaceB, u) -> tuple[list[float], list[int]]:
    """Unit-cube point of dimension n_cont + n_cat -> (continuous unit coords, category indices).
    Category k of K is chosen when its coordinate lies in [k/K, (k+1)/K) (u = 1 -> last category)."""
    u = [min(max(float(v), 0.0), 1.0) for v in u]
    cats = [min(int(v * K), K - 1) for v, K in zip(u[sp.n_cont:], sp.cat_sizes)]
    return u[:sp.n_cont], cats


def to_physical(sp: SpaceB, u_cont, cats) -> tuple[list[float], str, str]:
    htl, metal = sp.cat_values[0][cats[0]], sp.cat_values[1][cats[1]]
    lo, hi = bounds(sp.arch, htl)
    x = [a + min(max(float(v), 0.0), 1.0) * (b - a) for v, a, b in zip(u_cont, lo, hi)]
    return x, htl, metal


def design(arch: str, x, htl: str, scenario: str = "base") -> tuple[dict, ModuleGeometry]:
    n = len(STACKS[arch])
    if len(x) != n + 1:
        raise ValueError(f"{arch}: expected {n + 1} values, got {len(x)}")
    layers = []
    for (role, mat), t in zip(STACKS[arch], x[:n]):
        L = {"role": role, "material": mat or htl, "thickness_nm": round(float(t), 1)}
        if role == "absorber" and SCENARIOS[scenario]:
            L["overrides"] = dict(SCENARIOS[scenario])
        layers.append(L)
    geom = ModuleGeometry(round(float(x[n]), 2), A.DEAD_MM, A.TCO_OHM_SQ, A.EDGE)
    return {"schema": SCHEMA, "architecture": arch, "layers": layers}, geom


# ------------------------------------------------------------------ cost
def usd_per_W(d: dict, module_pce_pct: float, lib: dict, line=None) -> dict:
    line = line or A.cost_line()
    r = evaluate_cost(d, module_pce_pct, line, assumptions=A.ASM, physics_setup=physics_setup(lib, d["architecture"]),
                      physics_library=lib)
    if r["usd_per_W"] is None:
        raise RuntimeError(f"cost incomplete: {r.get('reason')}")
    be = [i for i in r["materials"]["items"] if i["item"].startswith("bom:back_electrode")]
    return {"usd_per_W": r["usd_per_W"], "usd_per_W_high_prices": r["usd_per_W_high_prices"],
            "cost_status": r["status"], "materials_usd_m2": r["materials"]["total_usd_m2"],
            "back_electrode_item": be[0]["item"] if be else None,
            "back_electrode_usd_m2": be[0]["usd_m2"] if be else None}


def reference_point(arch: str, contact_rule: str = "B2", optics: str = "mcpeak") -> tuple[float, float]:
    """(PCE_FLOOR, log10 USD/W) of the most expensive corner of the space: every thickness at its maximum, for the
    combination with the highest materials cost, costed at PCE_FLOOR. Fixed before any run."""
    worst = -math.inf
    for htl in HTLS:
        for metal in METALS:
            lib = physics_library(arch, htl, metal, contact_rule, optics)
            d, _ = design(arch, bounds(arch, htl)[1], htl)
            worst = max(worst, usd_per_W(d, PCE_FLOOR, lib)["usd_per_W"])
    return PCE_FLOOR, math.log10(worst)


def reference_point_no_au(arch: str, contact_rule: str = "B2", optics: str = "mcpeak") -> tuple[float, float]:
    """Diagnostic HV reference (prereg §6, agy review): as reference_point but over Cu and Ag combinations only."""
    worst = -math.inf
    for htl in HTLS:
        for metal in ("Cu", "Ag"):
            lib = physics_library(arch, htl, metal, contact_rule, optics)
            d, _ = design(arch, bounds(arch, htl)[1], htl)
            worst = max(worst, usd_per_W(d, PCE_FLOOR, lib)["usd_per_W"])
    return PCE_FLOOR, math.log10(worst)


# ------------------------------------------------------------------ one simulator call
_SIMS: dict = {}


def simulator(arch, htl, metal, cache_dir=None, contact_rule="B2", optics="mcpeak", work_root=None):
    """One SimSS instance per (combination, physics variant), reused inside a process."""
    from perodesign.physics.simss import SimSS
    key = (arch, htl, metal, contact_rule, optics, str(cache_dir), str(work_root))
    if key not in _SIMS:
        _SIMS[key] = SimSS(library=physics_library(arch, htl, metal, contact_rule, optics),
                           cache_dir=cache_dir, work_root=work_root)
    return _SIMS[key]


def evaluate(arch: str, u_cont, cats, scenario: str = "base", cache_dir: str | Path | None = None,
             contact_rule: str = "B2", optics: str = "mcpeak", work_root=None) -> dict:
    """One simulator call. Flat JSON-able record; feasible=False for failed/partial sims or module errors."""
    sp = space(arch)
    x, htl, metal = to_physical(sp, u_cont, cats)
    lib = physics_library(arch, htl, metal, contact_rule, optics)
    sim = simulator(arch, htl, metal, cache_dir, contact_rule, optics, work_root)
    d, geom = design(arch, x, htl, scenario)
    r = sim.run(d)
    rec = {"arch": arch, "scenario": scenario, "HTL": htl, "metal": metal, "cats": list(map(int, cats)),
           "x": [L["thickness_nm"] for L in d["layers"]] + [geom.stripe_width_mm],
           "design_hash": r.design_hash, "library_sha256": lib["_sha256"], "sim_status": r.status,
           "reason": r.reason, "seconds": r.seconds, "cell_pce_pct": r.metrics.get("pce_pct"),
           "voc_V": r.metrics.get("voc_V"), "ff": r.metrics.get("ff"), "jsc_mA_cm2": r.metrics.get("jsc_mA_cm2"),
           "feasible": False, "module_pce_pct": None, "usd_per_W": None, "log10_usd_per_W": None}
    if r.status != "complete":
        return rec
    try:
        m = module_from_cell(r.metrics, geom)
    except ModuleError as e:
        rec["reason"] = f"module: {e}"
        return rec
    rec.update(gff=m["gff"], p_tco=m["p_tco"])
    if not 0 < m["module_pce_pct"] < 40:
        rec["reason"] = f"module PCE {m['module_pce_pct']} outside (0, 40)"
        return rec
    rec.update(module_pce_pct=m["module_pce_pct"], **usd_per_W(d, m["module_pce_pct"], lib))
    rec["feasible"] = math.isfinite(rec["usd_per_W"]) and rec["usd_per_W"] > 0
    if rec["feasible"]:
        rec["log10_usd_per_W"] = math.log10(rec["usd_per_W"])
    return rec


__all__ = ["HTLS", "METALS", "STACKS", "PRODUCTION_COMBO", "SCENARIOS", "physics_library", "b2_contacts",
           "physics_setup", "space", "bounds", "decode_relaxed", "to_physical", "design", "usd_per_W",
           "reference_point", "evaluate", "simulator"]
