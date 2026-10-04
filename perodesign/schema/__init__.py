"""PeroDesign design schema v1: the only input format the physics engine accepts.

A design (what the LLM or an optimiser proposes) looks like:

    {
      "schema": "perodesign.design/1",
      "architecture": "n-i-p",
      "layers": [
        {"role": "ETL",      "material": "C60",    "thickness_nm": 10},
        {"role": "absorber", "material": "MAPbI3", "thickness_nm": 500,
         "overrides": {"N_t_bulk_m3": 1e20}},
        {"role": "HTL",      "material": "PTAA",   "thickness_nm": 10}
      ],
      "interface_overrides": {"ETL|absorber": {"N_t_int_m2": 4e12}}
    }

Rules (reject, never repair; plan v1 s4.4 + the unit contract):
  * exact key sets: unknown or missing keys are errors (so "thickness_um" or "thickness" fail);
  * units live in key names; only library-whitelisted override keys are accepted;
  * materials must exist in the library and be allowed in that role;
  * layer order must match the architecture;
  * every number must be finite, a real number (bools rejected), and inside library bounds;
  * interface overrides are keyed by roles "left|right" of ADJACENT layers.
validate() collects ALL problems and raises one DesignError listing them.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

from ..library import load_library

SCHEMA_ID = "perodesign.design/1"
TOP_KEYS_REQUIRED = {"schema", "architecture", "layers"}
TOP_KEYS_OPTIONAL = {"interface_overrides"}
LAYER_KEYS_REQUIRED = {"role", "material", "thickness_nm"}
LAYER_KEYS_OPTIONAL = {"overrides"}


class DesignError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("invalid design:\n  - " + "\n  - ".join(problems))


def _num(x: Any) -> float | None:
    """Finite real number or None. bool is rejected (True would silently become 1)."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def validate(design: Any, library: dict | None = None) -> dict:
    """Return a normalised copy (floats, sorted override dicts) or raise DesignError."""
    lib = library or load_library()
    P: list[str] = []
    if not isinstance(design, dict):
        raise DesignError([f"design must be a JSON object, got {type(design).__name__}"])
    keys = set(design)
    for k in sorted(TOP_KEYS_REQUIRED - keys):
        P.append(f"missing top-level key '{k}'")
    for k in sorted(keys - TOP_KEYS_REQUIRED - TOP_KEYS_OPTIONAL):
        P.append(f"unknown top-level key '{k}'")
    if design.get("schema") != SCHEMA_ID:
        P.append(f"schema must be '{SCHEMA_ID}', got {design.get('schema')!r}")
    arch = design.get("architecture")
    order = lib["architectures"].get(arch) if isinstance(arch, str) else None
    if order is None:
        P.append(f"architecture {arch!r} not supported (supported: {sorted(lib['architectures'])})")
    layers = design.get("layers")
    out_layers: list[dict] = []
    if not isinstance(layers, list) or not layers:
        P.append("'layers' must be a non-empty list")
        layers = []
    roles = [L.get("role") if isinstance(L, dict) else None for L in layers]
    if order is not None and roles != order:
        P.append(f"layer roles {roles} do not match architecture {arch} order {order}")
    for i, L in enumerate(layers):
        tag = f"layers[{i}]"
        if not isinstance(L, dict):
            P.append(f"{tag} must be an object"); continue
        lk = set(L)
        for k in sorted(LAYER_KEYS_REQUIRED - lk):
            P.append(f"{tag}: missing key '{k}'")
        for k in sorted(lk - LAYER_KEYS_REQUIRED - LAYER_KEYS_OPTIONAL):
            P.append(f"{tag}: unknown key '{k}' (units belong in the key name; allowed: "
                     f"{sorted(LAYER_KEYS_REQUIRED | LAYER_KEYS_OPTIONAL)})")
        mat_name = L.get("material")
        mat = lib["materials"].get(mat_name) if isinstance(mat_name, str) else None
        if mat is None:
            P.append(f"{tag}: material {mat_name!r} not in library (known: {sorted(lib['materials'])})")
        elif L.get("role") not in mat["roles"]:
            P.append(f"{tag}: material {mat_name} cannot be used as {L.get('role')!r} (allowed: {mat['roles']})")
        t = _num(L.get("thickness_nm"))
        if "thickness_nm" in L and t is None:
            P.append(f"{tag}: thickness_nm must be a finite number, got {L.get('thickness_nm')!r}")
        elif t is not None and mat is not None:
            lo, hi = float(mat["thickness_nm"]["min"]), float(mat["thickness_nm"]["max"])
            if not lo <= t <= hi:
                P.append(f"{tag}: thickness_nm={t:g} outside [{lo:g}, {hi:g}] for {mat_name}")
        ov = L.get("overrides", {})
        norm_ov: dict[str, float] = {}
        if not isinstance(ov, dict):
            P.append(f"{tag}: overrides must be an object")
        elif mat is not None:
            allowed = mat.get("overridable") or {}
            for k, v in ov.items():
                if k not in allowed:
                    P.append(f"{tag}: override '{k}' not allowed for {mat_name} (allowed: {sorted(allowed)})")
                    continue
                x = _num(v)
                if x is None:
                    P.append(f"{tag}: override {k} must be a finite number, got {v!r}"); continue
                lo, hi = float(allowed[k]["min"]), float(allowed[k]["max"])
                if not lo <= x <= hi:
                    P.append(f"{tag}: override {k}={x:g} outside [{lo:g}, {hi:g}]")
                norm_ov[k] = x
        out_layers.append({"role": L.get("role"), "material": mat_name,
                           "thickness_nm": t, "overrides": dict(sorted(norm_ov.items()))})
    # interfaces
    io = design.get("interface_overrides", {})
    norm_io: dict[str, dict[str, float]] = {}
    adjacent = {f"{roles[i]}|{roles[i + 1]}": i for i in range(len(roles) - 1)}
    if not isinstance(io, dict):
        P.append("interface_overrides must be an object")
        io = {}
    for key, ov in io.items():
        if key not in adjacent:
            P.append(f"interface_overrides: '{key}' is not an adjacent 'left|right' role pair "
                     f"(valid: {sorted(adjacent)})"); continue
        i = adjacent[key]
        if not (isinstance(layers[i], dict) and isinstance(layers[i + 1], dict)):
            P.append(f"interface_overrides: '{key}' refers to malformed layers"); continue
        pair = f"{layers[i].get('material')}|{layers[i + 1].get('material')}"
        itf = lib["interfaces"].get(pair)
        if itf is None:
            P.append(f"interface_overrides: no library interface for {pair}"); continue
        allowed = itf.get("overridable") or {}
        if not isinstance(ov, dict):
            P.append(f"interface_overrides['{key}'] must be an object"); continue
        norm: dict[str, float] = {}
        for k, v in ov.items():
            if k not in allowed:
                P.append(f"interface_overrides['{key}']: '{k}' not allowed (allowed: {sorted(allowed)})"); continue
            x = _num(v)
            if x is None:
                P.append(f"interface_overrides['{key}']: {k} must be a finite number, got {v!r}"); continue
            lo, hi = float(allowed[k]["min"]), float(allowed[k]["max"])
            if not lo <= x <= hi:
                P.append(f"interface_overrides['{key}']: {k}={x:g} outside [{lo:g}, {hi:g}]")
            norm[k] = x
        if norm:
            norm_io[key] = dict(sorted(norm.items()))
    # every adjacent material pair must have library interface data (even without overrides)
    for i in range(len(layers) - 1):
        a, b = (layers[i].get("material"), layers[i + 1].get("material")) if all(
            isinstance(x, dict) for x in (layers[i], layers[i + 1])) else (None, None)
        if a in lib["materials"] and b in lib["materials"] and f"{a}|{b}" not in lib["interfaces"]:
            P.append(f"no library interface data for adjacent pair {a}|{b}")
    if P:
        raise DesignError(P)
    return {"schema": SCHEMA_ID, "architecture": arch, "layers": out_layers,
            "interface_overrides": dict(sorted(norm_io.items()))}


def canonical_json(design: dict, library: dict | None = None) -> str:
    """Validated, normalised, key-sorted JSON: identical designs give identical strings."""
    return json.dumps(validate(design, library), sort_keys=True, separators=(",", ":"))


def design_hash(design: dict, library: dict | None = None) -> str:
    return hashlib.sha256(canonical_json(design, library).encode()).hexdigest()


def from_thicknesses(absorber_nm: float, etl_nm: float, htl_nm: float) -> dict:
    """Convenience: the Phase 0 toy task (C60 / MAPbI3 / PTAA, n-i-p) as a v1 design.
    NOTE argument order is (absorber, ETL, HTL) as in the Phase 0 answer format, NOT stack order.
    Prefer keyword arguments: from_thicknesses(absorber_nm=500, etl_nm=10, htl_nm=10)."""
    return {"schema": SCHEMA_ID, "architecture": "n-i-p", "layers": [
        {"role": "ETL", "material": "C60", "thickness_nm": etl_nm},
        {"role": "absorber", "material": "MAPbI3", "thickness_nm": absorber_nm},
        {"role": "HTL", "material": "PTAA", "thickness_nm": htl_nm}]}


def resolved_layers(design: dict, library: dict | None = None) -> list[dict]:
    """Validated design -> per-layer full parameter sets (library defaults + overrides) and
    per-interface parameters. This is exactly what the simulator wrapper maps to CLI flags."""
    lib = library or load_library()
    d = validate(design, lib)
    out = []
    for i, L in enumerate(d["layers"]):
        m = lib["materials"][L["material"]]
        params = copy.deepcopy(m["params"])
        params.update(L["overrides"])
        itf = None
        if i + 1 < len(d["layers"]):
            nxt = d["layers"][i + 1]
            it = lib["interfaces"][f"{L['material']}|{nxt['material']}"]
            itf = copy.deepcopy(it["params"])
            itf.update(d["interface_overrides"].get(f"{L['role']}|{nxt['role']}", {}))
        out.append({"role": L["role"], "material": L["material"], "thickness_nm": L["thickness_nm"],
                    "params": params, "interface_right": itf})
    return out
