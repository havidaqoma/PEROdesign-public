"""Generic discounted-cash-flow and levelized-cost core.

Card 1 of `docs/EXECUTION.md`. Deliberately contains **no technology**: it holds
the finance, the time axis, the uncertainty driver and the summariser that every
archetype needs, and nothing about solar irradiance or battery cycling.

Two design rules that come from defects already measured in this repo:

1. **Nothing fails silently.** `reference/tea_engine_ORACLE.py` ended a
   calculation with a bare `except: return 1.5`, so a parse failure became a
   plausible-looking cost and flowed into LCOE (audited in
   `scripts/05_oracle_audit.py`). Here a bad input raises.
2. **The time axis is explicit and shared.** Degradation and discounting are
   separate, named steps, so an archetype that needs a different axis has to
   say so rather than quietly bending this one.

Scope note: units are not checked here. `pint` and the CEPCI/FX escalation
table are Card 3. Until then every value is in a documented but unenforced
unit (USD, kWh, m2, kWh/kW/yr).

Tracing exists so Card 1 can measure which core functions each archetype
actually calls, rather than asserting reuse in prose.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "Sampler",
    "annual_output",
    "crf",
    "degradation_factor",
    "discount_factor",
    "levelized_cost",
    "monte_carlo",
    "npv",
    "replacement_cost",
    "summarize",
    "unit_capex",
    "variable_opex",
]

# --- instrumentation ---------------------------------------------------------
# Enabled only by the Card 1 harness. Off in normal use, so it cannot perturb a
# production run.
_TRACE: list[str] | None = None


def trace_start() -> None:
    global _TRACE
    _TRACE = []


def trace_stop() -> list[str]:
    """Stop tracing and return the ordered list of core calls seen."""
    global _TRACE
    seen = list(_TRACE or [])
    _TRACE = None
    return seen


def _rec(name: str) -> None:
    if _TRACE is not None:
        _TRACE.append(name)


# --- uncertainty -------------------------------------------------------------

class Sampler:
    """Seeded draw source. One per run, so every archetype shares a driver."""

    def __init__(self, seed: int):
        _rec("Sampler.__init__")
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)

    def normal(self, mean: float, sd: float, n: int) -> np.ndarray:
        _rec("Sampler.normal")
        if sd < 0:
            raise ValueError(f"sd must be >= 0, got {sd}")
        return self.rng.normal(mean, sd, n)

    def uniform(self, lo: float, hi: float, n: int) -> np.ndarray:
        _rec("Sampler.uniform")
        if hi < lo:
            raise ValueError(f"uniform requires hi >= lo, got {lo} > {hi}")
        return self.rng.uniform(lo, hi, n)


def monte_carlo(compute, n: int, sampler: Sampler) -> np.ndarray:
    """Run `compute(n, sampler)` once. Vectorised, not a Python loop.

    The shared MC driver: both archetypes reach the summary through this, so a
    change to how uncertainty is propagated lands in one place.
    """
    _rec("monte_carlo")
    if n <= 0:
        raise ValueError(f"n must be > 0, got {n}")
    out = np.asarray(compute(n, sampler), dtype=float)
    if out.shape != (n,):
        raise ValueError(f"compute must return shape ({n},), got {out.shape}")
    return out


# --- time axis and finance ---------------------------------------------------

def discount_factor(rate: np.ndarray | float, year: int) -> np.ndarray:
    """1 / (1 + r)^year for a year >= 1."""
    _rec("discount_factor")
    if year < 1:
        raise ValueError(f"year must be >= 1, got {year}")
    return 1.0 / (1.0 + np.asarray(rate, dtype=float)) ** year


def degradation_factor(annual_degradation: float, year: int) -> float:
    """Fraction of nameplate output remaining in `year` (year 1 = 1 - d)."""
    _rec("degradation_factor")
    if not 0.0 <= annual_degradation < 1.0:
        raise ValueError(f"annual_degradation must be in [0,1), got {annual_degradation}")
    return (1.0 - annual_degradation) ** year


def crf(rate: np.ndarray | float, years: float) -> np.ndarray:
    """Capital recovery factor: annualises a present value over `years`."""
    _rec("crf")
    if years <= 0:
        raise ValueError(f"years must be > 0, got {years}")
    r = np.asarray(rate, dtype=float)
    # A zero discount rate is legal and must not raise: the closed form divides
    # by zero there, so compute it under errstate and select afterwards.
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = r * (1.0 + r) ** years / ((1.0 + r) ** years - 1.0)
    return np.where(r == 0.0, 1.0 / years, factor)


def npv(rate: np.ndarray | float, cashflows: np.ndarray) -> np.ndarray:
    """Net present value. `cashflows` is (n, t) with t starting at year 1."""
    _rec("npv")
    cf = np.asarray(cashflows, dtype=float)
    r = np.asarray(rate, dtype=float)[:, None]
    years = np.arange(1, cf.shape[1] + 1)[None, :]
    return (cf / (1.0 + r) ** years).sum(axis=1)


# --- cost lines --------------------------------------------------------------

def unit_capex(base_unit_capex: float, bos_unit_capex: float) -> float:
    """Total installed cost per unit of scale (USD per m2, or per kWh).

    Accepts scalars or arrays: the Monte Carlo path passes a draw per sample, so
    validation must be vectorised. A scalar `if x < 0` on an array raises
    "truth value is ambiguous", which is how this was caught.
    """
    _rec("unit_capex")
    base = np.asarray(base_unit_capex, dtype=float)
    bos = np.asarray(bos_unit_capex, dtype=float)
    if np.any(base < 0) or np.any(bos < 0):
        raise ValueError("capex components must be >= 0")
    return base + bos


def variable_opex(annual_opex_per_unit: float, scale: float) -> float:
    """Annual fixed-plus-variable operating cost for a given scale."""
    _rec("variable_opex")
    opex = np.asarray(annual_opex_per_unit, dtype=float)
    s = np.asarray(scale, dtype=float)
    if np.any(opex < 0) or np.any(s < 0):
        raise ValueError("opex and scale must be >= 0")
    return opex * s


def replacement_cost(unit_cost: float, year_discount: np.ndarray) -> np.ndarray:
    """Discounted cost of a one-off replacement, e.g. an inverter in year 15."""
    _rec("replacement_cost")
    return unit_cost * year_discount


# --- the levelised cost, the number both archetypes exist to produce ---------

def annual_output(rated_output_per_unit: float, degradation: float) -> float:
    """Year-t output per unit of scale. The one place 'yield' is defined."""
    _rec("annual_output")
    rated = np.asarray(rated_output_per_unit, dtype=float)
    if np.any(rated < 0):
        raise ValueError("rated_output_per_unit must be >= 0")
    return rated * degradation


def levelized_cost(discounted_costs: np.ndarray, discounted_output: np.ndarray) -> np.ndarray:
    """LCOX = discounted costs / discounted output.

    Guards the division explicitly instead of clipping the denominator to a
    small positive number: clipping (as the vendored oracle did with
    `np.clip(energy_m2, 1e-5, None)`) turns a physically impossible zero-output
    case into a large, plausible-looking LCOE instead of an error.
    """
    _rec("levelized_cost")
    c = np.asarray(discounted_costs, dtype=float)
    o = np.asarray(discounted_output, dtype=float)
    if np.any(o <= 0.0):
        raise ValueError("discounted output must be > 0; zero output has no LCOE")
    return c / o


# --- reporting ---------------------------------------------------------------

def summarize(x: np.ndarray, pcts: tuple[int, ...] = (5, 50, 95)) -> dict[str, float]:
    _rec("summarize")
    a = np.asarray(x, dtype=float)
    if not np.all(np.isfinite(a)):
        raise ValueError("non-finite values in result: refusing to summarise")
    out = {f"p{p}": float(np.percentile(a, p)) for p in pcts}
    out["mean"] = float(a.mean())
    return out
