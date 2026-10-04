"""Load the versioned material/interface library. The library file is part of every run hash."""
from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

LIB_DIR = Path(__file__).resolve().parent
DEFAULT_LIBRARY = LIB_DIR / "materials_v2.yaml"   # v2 adds the p-i-n industrial stack; v1 kept for Phase 0 reproduction


class LibraryError(ValueError):
    """The library file itself is malformed."""


@lru_cache(maxsize=8)
def load_library(path: str | Path = DEFAULT_LIBRARY) -> dict:
    p = Path(path)
    raw = p.read_bytes()
    lib = yaml.safe_load(raw.decode("utf-8"))
    for key in ("library_version", "materials", "interfaces", "architectures"):
        if key not in lib:
            raise LibraryError(f"library {p.name}: missing top-level key '{key}'")
    def _check_bounds(where, params, overridable):
        for k, b in (overridable or {}).items():
            if k not in params:
                raise LibraryError(f"library {p.name}: {where} overridable '{k}' is not one of its params")
            if not isinstance(b, dict) or "min" not in b or "max" not in b:
                raise LibraryError(f"library {p.name}: {where} overridable '{k}' needs min and max")
            if not (float(b["min"]) <= float(params[k]) <= float(b["max"])):
                raise LibraryError(f"library {p.name}: {where} default {k}={params[k]} outside its own bounds")

    for name, m in lib["materials"].items():
        for key in ("roles", "provenance", "thickness_nm", "params", "overridable"):
            if key not in m:
                raise LibraryError(f"library {p.name}: material '{name}' missing '{key}'")
        t = m["thickness_nm"]
        if not (0 < float(t["min"]) < float(t["max"])):
            raise LibraryError(f"library {p.name}: material '{name}' has bad thickness bounds {t}")
        _check_bounds(f"material '{name}'", m["params"], m["overridable"])
    for pair, it in lib["interfaces"].items():
        left, _, right = pair.partition("|")
        if left not in lib["materials"] or right not in lib["materials"]:
            raise LibraryError(f"library {p.name}: interface '{pair}' names an unknown material")
        _check_bounds(f"interface '{pair}'", it.get("params") or {}, it.get("overridable"))
    lib["_sha256"] = hashlib.sha256(raw).hexdigest()
    lib["_path"] = str(p)
    return lib
