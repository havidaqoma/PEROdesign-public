"""Cell-to-module model v1 (plan v1 s5.3): module PCE from the simulated cell and the module geometry.

    module_PCE = cell_PCE x GFF x (1 - p_TCO)

  GFF    geometric fill factor of a monolithic stripe module = w / (w + d), with w the active stripe width
         and d the dead (P1-P2-P3 scribe) width. Edge margins are a separate factor, `edge_area_fraction`.
  p_TCO  fractional power lost in the front TCO of one stripe, first-order (Vmp and Jmp fixed):
             p_TCO = R_sq * J_mp * w^2 / (3 * V_mp)
         Derivation (checked numerically in tests/test_tea.py): current collected uniformly over the
         stripe flows laterally to the interconnect; at distance x from the far edge the TCO carries
         J*x per unit stripe length, so the Joule loss per unit length is  int_0^w (J x)^2 R_sq dx
         = J^2 R_sq w^3 / 3, while the stripe produces J V w. Ratio = J R_sq w^2 / (3 V).
         Valid only while the loss is small: p_TCO > MAX_P_TCO is refused, not extrapolated.

All geometry and R_sq values are DESIGN / SCENARIO inputs. Nothing here is a sourced constant.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

MAX_P_TCO = 0.15


class ModuleError(ValueError):
    pass


@dataclass(frozen=True)
class ModuleGeometry:
    stripe_width_mm: float          # active cell (stripe) width w
    dead_width_mm: float            # P1-P3 interconnect width d
    tco_sheet_res_ohm_sq: float     # front TCO sheet resistance
    edge_area_fraction: float = 0.0  # fraction of module area lost to edges/busbars/margins (0..0.5)

    def check(self):
        for k in ("stripe_width_mm", "dead_width_mm", "tco_sheet_res_ohm_sq", "edge_area_fraction"):
            v = getattr(self, k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ModuleError(f"{k} must be a finite number, got {v!r}")
        if not 0.5 <= self.stripe_width_mm <= 20.0:
            raise ModuleError(f"stripe_width_mm {self.stripe_width_mm} outside [0.5, 20]")
        if not 0.0 < self.dead_width_mm < self.stripe_width_mm:
            raise ModuleError(f"dead_width_mm {self.dead_width_mm} must be in (0, stripe_width_mm)")
        if not 0.0 < self.tco_sheet_res_ohm_sq <= 100.0:
            raise ModuleError(f"tco_sheet_res_ohm_sq {self.tco_sheet_res_ohm_sq} outside (0, 100]")
        if not 0.0 <= self.edge_area_fraction <= 0.5:
            raise ModuleError(f"edge_area_fraction {self.edge_area_fraction} outside [0, 0.5]")


def gff(g: ModuleGeometry) -> float:
    return g.stripe_width_mm / (g.stripe_width_mm + g.dead_width_mm) * (1.0 - g.edge_area_fraction)


def p_tco(g: ModuleGeometry, j_mp_A_m2: float, v_mp_V: float) -> float:
    if not (j_mp_A_m2 > 0 and v_mp_V > 0):
        raise ModuleError(f"need J_mp > 0 and V_mp > 0, got {j_mp_A_m2}, {v_mp_V}")
    w = g.stripe_width_mm * 1e-3
    return g.tco_sheet_res_ohm_sq * j_mp_A_m2 * w * w / (3.0 * v_mp_V)


def module_from_cell(cell_metrics: dict, g: ModuleGeometry) -> dict:
    """cell_metrics = SimResult.metrics (needs pce_pct, mpp_W_m2, vmpp_V). Returns module result + factors."""
    g.check()
    pce, mpp, vmp = cell_metrics.get("pce_pct"), cell_metrics.get("mpp_W_m2"), cell_metrics.get("vmpp_V")
    if pce is None or mpp is None or vmp is None:
        raise ModuleError("cell metrics need pce_pct, mpp_W_m2 and vmpp_V (use a complete/partial SimSS result)")
    j_mp = mpp / vmp                         # A/m2
    loss = p_tco(g, j_mp, vmp)
    if loss > MAX_P_TCO:
        raise ModuleError(f"TCO loss {loss:.3f} > {MAX_P_TCO}: outside the first-order model; narrow the stripe")
    f = gff(g)
    return {"module_pce_pct": pce * f * (1.0 - loss), "cell_pce_pct": pce, "gff": f, "p_tco": loss,
            "j_mp_A_m2": j_mp, "v_mp_V": vmp, "geometry": asdict(g),
            "model": "module-v1: GFF x (1 - R_sq J_mp w^2 / 3 V_mp)"}
