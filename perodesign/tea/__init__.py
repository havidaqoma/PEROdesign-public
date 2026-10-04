"""Factory-gate cost engine v1 (P1-B): design -> SimSS cell -> module -> USD per good watt.

    cost_per_W = ( materials_per_m2 + other_opex_per_m2 + capex_per_m2_yr ) / good_W_per_m2
    good_W_per_m2   = module_PCE/100 x 1000 W/m2 x yield
    capex_per_m2_yr = line_capex x CRF(rate, years) / throughput_m2_per_yr        (AutoTEA dcf.crf)
    materials       = sum over items of  quantity x unit_price / utilisation       (Liu 2025 Table 1 rule)

This is a factory-gate COST including a return on capital through CRF (no tax, no margin, no BOS,
no installation, no LCOE). Line throughput is in m2/yr, so efficiency lowers capital per watt.

Honesty rules enforced in code:
  * every cost-library number passes perodesign.tea.provenance.check_entry at load time, or loading fails;
  * every number used in a result is tagged sourced:<entry id>, derived:<formula> or assumed:<note>;
  * a design whose layers or BOM include an item with no sourced price is INCOMPLETE: the engine
    returns cost None plus the list of missing items, unless the caller supplies that price in
    `assumptions` (then status = "with_assumptions" and the assumption is listed in the result).
"""
from __future__ import annotations

import hashlib
import math
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from ..schema import validate
from .provenance import AUTOTEA_ROOT, check_entry

REPO = Path(__file__).resolve().parents[2]
COST_LIBRARY = Path(__file__).resolve().parent / "cost_library_v1.yaml"
SOURCE_DIR = REPO / "data" / "sources"
INCIDENT_W_M2 = 1000.0
TROY_OZ_G = 31.1034768      # exact by definition (international troy ounce); a unit conversion, not a sourced value
AUTOTEA_DCF_SHA256 = "8e7a52b4f38d561428808d1309b447140ab414ffe3b38529548624200dc33cb6"


class CostLibraryError(ValueError):
    pass


def _dcf():
    p = AUTOTEA_ROOT / "src" / "core" / "dcf.py"
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    if h != AUTOTEA_DCF_SHA256:
        raise CostLibraryError(f"AutoTEA dcf.py changed (sha256 {h[:12]}); re-review before use")
    if str(AUTOTEA_ROOT) not in sys.path:
        sys.path.insert(0, str(AUTOTEA_ROOT))
    from src.core import dcf  # noqa: E402
    return dcf


@lru_cache(maxsize=4)
def load_cost_library(path: str | Path = COST_LIBRARY, source_dir: str | Path = SOURCE_DIR) -> dict:
    raw = Path(path).read_bytes()
    lib = yaml.safe_load(raw.decode("utf-8"))
    ids = [e["id"] for e in lib["entries"]]
    if len(ids) != len(set(ids)):
        raise CostLibraryError("duplicate entry ids in cost library")
    failures = []
    for e in lib["entries"]:
        r = check_entry(e, lib["sources"], Path(source_dir))
        if not r.ok:
            failures.append(f"{e.get('id')}: {r.rule} {r.reason}")
    if failures:
        raise CostLibraryError("cost library entries fail the provenance gate:\n  " + "\n  ".join(failures))
    lib["_by_id"] = {e["id"]: e for e in lib["entries"]}
    lib["_sha256"] = hashlib.sha256(raw).hexdigest()
    return lib


@dataclass
class Tagged:
    value: float
    tag: str                                   # sourced:<id> | derived:<formula> | assumed:<note>


@dataclass
class LineScenario:
    """Factory line inputs. Each field is a Tagged value so its origin travels with it."""
    name: str
    capex_usd: Tagged
    throughput_m2_per_yr: Tagged
    depreciation_years: Tagged
    rate: Tagged                               # discount / cost-of-capital rate for CRF
    yield_fraction: Tagged
    other_opex_usd_per_m2: Tagged              # electricity + labour + land + maintenance, per m2 processed
    notes: list = field(default_factory=list)


def _v(lib, eid, unit: str | None = None):
    e = lib["_by_id"][eid]
    if unit is not None and e["unit"] != unit:
        raise CostLibraryError(f"entry {eid} has unit {e['unit']}, engine needs {unit}")
    return float(e["value"])


def _assumed(assumptions: dict, name: str) -> dict | None:
    a = assumptions.get(name)
    if a is None:
        return None
    if not a.get("note") or not isinstance(a.get("usd_m2"), (int, float)) or not a["usd_m2"] > 0:
        raise CostLibraryError(f"assumption {name}: needs a note and usd_m2 > 0 (a free material is an "
                               "omission, not an assumption)")
    return {"item": name, "usd_m2": float(a["usd_m2"]), "tag": f"assumed:{a['note']}"}


def liu2025_line(lib: dict | None = None, rate: Tagged | None = None) -> LineScenario:
    """The Liu 2025 China 100 MW line. Capex/capacity/years/yield are sourced. Two values are not:
    (1) the capital rate is not stated in the paper -> must be supplied (the paper's 0.092 USD/W
        implies ~4.85%, which is a BACK-SOLVED number, not a source);
    (2) other opex per m2 is DERIVED from the paper's aggregate 0.088 USD/W at 15% x 50%."""
    lib = lib or load_cost_library()
    eff, yld = _v(lib, "liu_module_eff") / 100.0, _v(lib, "liu_yield") / 100.0
    good_w_m2 = eff * INCIDENT_W_M2 * yld
    thr = _v(lib, "liu_capacity") * 1e6 / (eff * INCIDENT_W_M2)
    return LineScenario(
        name="liu2025_CN_100MW",
        capex_usd=Tagged(_v(lib, "liu_capex_line"), "sourced:liu_capex_line"),
        throughput_m2_per_yr=Tagged(thr, "derived:liu_capacity*1e6/(liu_module_eff/100*1000)"),
        depreciation_years=Tagged(_v(lib, "liu_depreciation"), "sourced:liu_depreciation"),
        rate=rate or Tagged(float("nan"), "assumed:MISSING (not stated in Liu 2025)"),
        yield_fraction=Tagged(yld, "sourced:liu_yield (/100)"),
        other_opex_usd_per_m2=Tagged(_v(lib, "liu_other_per_W") * good_w_m2,
                                     "derived:liu_other_per_W*liu_module_eff/100*1000*liu_yield/100"),
        notes=["nameplate 100 MW interpreted as processed-area capacity at 15% module efficiency"])


def _density(lib, m, name, assumptions):
    """g/cm3 for a layer material: sourced entry, derived from a sourced mass+thickness, or an explicit assumption."""
    if "density_from" in m:
        dens = _v(lib, m["density_from"]["mass"], "g") / (_v(lib, m["density_from"]["thickness"], "nm") * 1e-3)
        tag = f"density({m['density_from']['mass']}/{m['density_from']['thickness']})"
    elif m.get("density"):
        dens, tag = _v(lib, m["density"], "g/cm3"), f"density({m['density']})"
    else:
        a = assumptions.get(f"density:{m['item']}")
        if a is None:
            return None, None
        if not a.get("note") or not isinstance(a.get("g_cm3"), (int, float)):
            raise CostLibraryError(f"assumption density:{m['item']} needs g_cm3 and a note")
        dens, tag = float(a["g_cm3"]), f"ASSUMED density {a['g_cm3']} g/cm3 ({a['note']})"
    if not 0.5 < dens < 25.0:
        raise CostLibraryError(f"{name}: density {dens:.2f} g/cm3 is not physical")
    return dens, tag


def _physics_setup(architecture: str) -> dict:
    """device_setup the PHYSICS engine uses for this architecture (library defaults + architecture_setup)."""
    from ..library import load_library
    pl = load_library()
    s = dict(pl["device_setup"]["params"])
    s.update((pl.get("architecture_setup") or {}).get(architecture, {}))
    return s


def back_electrode_cost(lib: dict, price_case: str = "base", architecture: str = "n-i-p",
                        physics_setup: dict | None = None) -> dict | None:
    """Back electrode from the physics device_setup (the thickness and material SimSS actually simulated).
    physics_setup (Paper B): the device_setup of the SimSS instance that ran this design, when it is not the
    production library's (material choice changes nkBE_file). None = production library (unchanged behaviour)."""
    setup = physics_setup if physics_setup is not None else _physics_setup(architecture)
    m = (lib.get("back_electrode") or {}).get(setup["nkBE_file"])
    if m is None:
        return None
    t_nm = float(setup["L_BE_m"]) * 1e9
    if "mass_price" in m:                        # Liu-style: sourced mass per m2 at a sourced reference thickness
        mp = m["mass_price"]
        g_m2 = _v(lib, mp["mass"], "g") * t_nm / _v(lib, mp["thickness"], "nm")
        cost = g_m2 * _v(lib, mp["price"], "USD/g") / _v(lib, mp["utilisation"], "fraction")
        tag = f"derived:{mp['mass']} x L_BE {t_nm:g}/{mp['thickness']} nm x {mp['price']} / {mp['utilisation']}"
        used = [mp["mass"], mp["price"], mp["utilisation"], mp["thickness"]]
    else:
        dens = _v(lib, m["density"], "g/cm3")
        usd_g = _v(lib, m["price_per_toz"], "USD/toz") / TROY_OZ_G
        cost = t_nm * 1e-3 * dens * usd_g / _v(lib, m["utilisation"], "fraction")
        tag = f"derived:L_BE {t_nm:g} nm x {m['density']} x {m['price_per_toz']}/{TROY_OZ_G} g/toz / {m['utilisation']}"
        used = [m["density"], m["price_per_toz"], m["utilisation"]]
    if m.get("proxy_for"):
        tag += f" [PROXY: {m['proxy_for']}]"
    return {"item": f"bom:back_electrode:{m['item']}", "usd_m2": cost, "tag": tag, "used": used}


def region_line(region: str, lib: dict | None = None, rate_basis: str = "lending") -> LineScenario:
    """Liu 2025 line with a SOURCED capital rate for the region:
      rate_basis="lending"    -> the region's WDI bank lending rate (senior-debt proxy; a LOWER bound for a new
                                 PV factory, per agy review 2026-09-28);
      rate_basis="wacc_kajal" -> Kajal 2022's PV-factory WACC (India, 10.2%; an UPPER-bound scenario, same for all regions).
    Nominal rates, no deflation. Other opex remains Liu's China basis for every region and is labelled so."""
    lib = lib or load_cost_library()
    reg = lib["regions"].get(region)
    if reg is None:
        raise CostLibraryError(f"region {region!r} not in cost library (have {sorted(lib['regions'])})")
    if rate_basis == "lending":
        eid = reg["lending_rate"]
        rate = Tagged(_v(lib, eid, "percent") / 100.0,
                      f"sourced:{eid} (bank lending rate as cost-of-debt proxy: LOWER BOUND for a new PV factory)")
    elif rate_basis == "wacc_kajal":
        rate = Tagged(_v(lib, "kajal_wacc", "percent") / 100.0,
                      "sourced:kajal_wacc [PROXY: India 2022 PV-factory WACC used for every region; UPPER-BOUND scenario]")
    else:
        raise CostLibraryError(f"rate_basis {rate_basis!r} not in ('lending', 'wacc_kajal')")
    line = liu2025_line(lib, rate=rate)
    line.name = f"liu2025_line@{region}/{rate_basis}"
    line.other_opex_usd_per_m2 = Tagged(line.other_opex_usd_per_m2.value,
                                        line.other_opex_usd_per_m2.tag + " [CN BASIS, NOT REGIONALISED]")
    line.notes.append(f"region {region}: only the capital rate is regional; electricity/labour/land/maintenance = Liu China basis")
    return line


def labour_usd_per_m2(region: str, lib: dict | None = None, throughput_m2_per_yr: float | None = None) -> Tagged:
    """Direct labour per m2 processed, from SOURCED values only:
        headcount (Cai 2017 SI: 76 per 100 MW line) x annual wage / line throughput (100 MW / 120 W/m2 = 833,333 m2/yr).
    MY: wage = DOSM 2025 manufacturing MEAN monthly wage x 12 / WDI MYR per USD. Citizens only, EXCLUDES employer
    contributions (EPF/SOCSO/EIS/HRDF) and foreign workers -> reported as a LOWER BOUND, and the staffing is a
    printable-line estimate from 2017 (Cai's own words: 'assumed by considering the balance between ... China and USA')."""
    lib = lib or load_cost_library()
    n = _v(lib, "cai_line_employees", "count")
    # Throughput: by default Cai's OWN line (100 MW at 120 W/m2), which reproduces Cai's 0.0304 USD/W. When costing
    # a line, pass THAT line's throughput so labour and capital are spread over the same m2 (self-review 2026-09-28:
    # region_line_MY_bottom_up used Cai's 833,333 m2/yr while capital used Liu's 666,667 m2/yr).
    thr = throughput_m2_per_yr or _v(lib, "cai_line_capacity", "MW") * 1e6 / _v(lib, "cai_module_W_per_m2", "count")
    thr_txt = ("the costed line's throughput" if throughput_m2_per_yr else "(cai_line_capacity / cai_module_W_per_m2)")
    if region == "MY":
        usd_yr = _v(lib, "dosm_mfg_mean_wage_2025", "MYR/month") * 12 / _v(lib, "wdi_fx_my_2025", "fraction")
        tag = (f"derived:cai_line_employees x dosm_mfg_mean_wage_2025 x 12 / wdi_fx_my_2025 / {thr_txt} "
               "[LOWER BOUND: citizens' gross pay, no employer EPF/SOCSO/EIS/HRDF; PROXY: Cai 2017 headcount]")
    elif region == "GLOBAL_CAI":
        usd_yr = _v(lib, "cai_line_wage", "USD/yr")
        tag = f"derived:cai_line_employees x cai_line_wage / {thr_txt} [PROXY: Cai 2017 assumed wage between CN and US]"
    else:
        raise CostLibraryError(f"no sourced wage for region {region!r} (have MY, GLOBAL_CAI)")
    return Tagged(n * usd_yr / thr, tag)


def process_kwh_per_m2(architecture: str, lib: dict | None = None) -> dict:
    """Process electricity per m2 from Tian 2020 SI step inventories: (low, high) kWh/m2 and the step list.
    's4' steps: Table S4 rows are in MJ (header mislabelled kWh; row sum / 3.6 = stated kWh total). HIGH = calibrated
    row value / 3.6 (includes vacuum-tool base load); LOW = power x time (tool nameplate only)."""
    lib = lib or load_cost_library()
    steps = (lib.get("process_electricity") or {}).get(architecture)
    if steps is None:
        raise CostLibraryError(f"no process electricity inventory for architecture {architecture!r}")
    lo = hi = 0.0
    out = []
    for s in steps:
        if s["kind"] == "listed":
            v = _v(lib, s["entry"], "kWh"); a = b = v
        elif s["kind"] == "s4":
            a = _v(lib, s["power"], "W") * _v(lib, s["time"], "s") / 3.6e6
            b = _v(lib, s["listed"], "MJ") / 3.6
        else:
            raise CostLibraryError(f"unknown process_electricity kind {s['kind']!r}")
        lo += a; hi += b
        out.append({"step": s["step"], "kWh_low": a, "kWh_high": b})
    return {"kWh_low": lo, "kWh_high": hi, "steps": out,
            "note": "LOWER BOUND on line electricity: process tools only (no HVAC/cleanroom, vacuum base load, "
                    "scribing, cleaning); Tian 2020 lab-to-fab tandem inventory used for a single-junction p-i-n line"}


def electricity_usd_per_m2_MY(architecture: str, lib: dict | None = None) -> dict:
    """TNB RP4 medium-voltage ENERGY charges only (energy + fuel adjustment), RM/kWh -> USD with WDI FX.
    Capacity and network charges are per kW of MAXIMUM DEMAND and need a peak-load estimate that no source gives:
    they are EXCLUDED and listed (another reason this is a lower bound)."""
    lib = lib or load_cost_library()
    e = process_kwh_per_m2(architecture, lib)
    rm_kwh = _v(lib, "tnb_mv_energy", "MYR/kWh") + _v(lib, "tnb_mv_afa", "MYR/kWh")
    usd_kwh = rm_kwh / _v(lib, "wdi_fx_my_2025", "fraction")
    return {"usd_m2_low": e["kWh_low"] * usd_kwh, "usd_m2_high": e["kWh_high"] * usd_kwh, "usd_per_kWh": usd_kwh,
            "kWh": e, "excluded": ["TNB capacity + network charges (RM per kW max demand): no sourced peak load",
                                   "fixed user charge RM 200/month; KWTBB 1.6% levy; 8% service tax"],
            "tag": ("derived:process_kwh_per_m2 x (tnb_mv_energy + tnb_mv_afa) / wdi_fx_my_2025 "
                    "[LOWER BOUND: process tools + energy charge only; AFA is the Sep-2026 monthly value]")}


def maintenance_usd_per_m2(line: LineScenario, lib: dict | None = None) -> Tagged:
    """Kajal 2022 'industry-standard' 1% of total capital cost per year, on the costed line's capex and throughput.
    Cai 2017 printed 0.0011 USD/W for an 11 M USD / 100 MW line, i.e. the same 1% (Cai does not state the share; the
    test shows the two printable-line studies agree). BOTH are printable lines; for a vacuum-heavy line (Liu: sputter +
    evaporation) agy review argues 3-7%/yr [UNSOURCED] -> this is a LOWER BOUND for Liu's line."""
    lib = lib or load_cost_library()
    frac = _v(lib, "kajal_maintenance_frac", "percent") / 100.0
    return Tagged(frac * line.capex_usd.value / line.throughput_m2_per_yr.value,
                  "derived:kajal_maintenance_frac x line capex / line throughput [PROXY: India 2022 'industry standard' "
                  "for a PRINTABLE line; LOWER BOUND for a vacuum line]")


def demand_charge_MY(architecture: str, line: LineScenario, lib: dict | None = None, electricity: str = "low") -> dict:
    """TNB RP4 MV capacity + network charges (RM per kW MAXIMUM DEMAND per month) + fixed charge + KWTBB levy.
    Maximum demand = AVERAGE process load = kWh/m2 x line m2/yr / operating hours (Cai 2017: 504,000 min/yr).
    A real line has peaks above its average (load factor < 1; agy review: TNB meters MD over 30-min blocks and
    thin-film lines run at load factor ~0.6-0.75 [UNSOURCED]), so this is a LOWER BOUND on the demand charge.
    Sensitivity with a sourced number: each 450 kW vacuum tool (Liu 2025) that runs at peak adds 450 kW."""
    lib = lib or load_cost_library()
    e = process_kwh_per_m2(architecture, lib)
    kwh_m2 = e["kWh_low"] if electricity == "low" else e["kWh_high"]
    hours = _v(lib, "cai_minutes_per_year", "min") / 60.0
    thr = line.throughput_m2_per_yr.value
    kw_avg = kwh_m2 * thr / hours
    fx = _v(lib, "wdi_fx_my_2025", "fraction")
    rm_kw_month = _v(lib, "tnb_mv_capacity", "MYR/kW/month") + _v(lib, "tnb_mv_network", "MYR/kW/month")
    demand_usd_yr = kw_avg * rm_kw_month * 12 / fx
    fixed_usd_yr = _v(lib, "tnb_mv_fixed", "MYR/month") * 12 / fx
    energy_usd_yr = kwh_m2 * thr * (_v(lib, "tnb_mv_energy", "MYR/kWh") + _v(lib, "tnb_mv_afa", "MYR/kWh")) / fx
    kwtbb = _v(lib, "tnb_mv_kwtbb", "fraction")
    levy_usd_yr = kwtbb * (energy_usd_yr + demand_usd_yr + fixed_usd_yr)
    per_tool = 450.0 * rm_kw_month * 12 / fx / thr     # Liu's '450 KW for each vacuum machine'
    return {"kW_max_demand_assumed": kw_avg, "operating_h_per_yr": hours,
            "usd_m2": (demand_usd_yr + fixed_usd_yr + levy_usd_yr) / thr,
            "parts_usd_m2": {"capacity+network": demand_usd_yr / thr, "fixed": fixed_usd_yr / thr, "kwtbb_levy": levy_usd_yr / thr},
            "usd_m2_per_extra_450kW_tool": per_tool,
            "tag": ("derived:(tnb_mv_capacity + tnb_mv_network) x max demand + tnb_mv_fixed + tnb_mv_kwtbb levy; "
                    "max demand = process kWh/m2 x line m2/yr / cai_minutes_per_year [LOWER BOUND: load factor 1; "
                    "PROXY: Cai 2017 operating hours used with Liu's throughput]"),
            "excluded": ["8% service tax (TNB st: 0.08; recoverable/exempt status for manufacturers not sourced)"]}


def region_line_MY_bottom_up(lib: dict | None = None, rate_basis: str = "lending", electricity: str = "low",
                             include_maintenance: bool = True, include_demand: bool = True,
                             include_facilities_proxy: bool = False) -> LineScenario:
    """Malaysia with BOTTOM-UP other opex = sourced labour (DOSM) + sourced process electricity (Tian x TNB).
    Land/rent and maintenance have NO Malaysian source and are omitted (listed). So other opex is a LOWER BOUND;
    compare with Liu's China aggregate (0.088 USD/W incl. land and maintenance) which stays available as the default."""
    lib = lib or load_cost_library()
    line = region_line("MY", lib, rate_basis)
    lab = labour_usd_per_m2("MY", lib, throughput_m2_per_yr=line.throughput_m2_per_yr.value)
    el = electricity_usd_per_m2_MY("p-i-n", lib)
    e_val = el["usd_m2_low"] if electricity == "low" else el["usd_m2_high"]
    parts = {"labour": lab.value, "electricity_energy": e_val}
    omitted = ["HVAC/cleanroom base load", "employer EPF/SOCSO/EIS/HRDF (KWSP site blocked automated retrieval)",
               "8% service tax"]
    if include_maintenance:
        parts["maintenance"] = maintenance_usd_per_m2(line, lib).value
    else:
        omitted.append("maintenance")
    if include_demand:
        parts["tnb_demand_fixed_levy"] = demand_charge_MY("p-i-n", line, lib, electricity)["usd_m2"]
    else:
        omitted.append("TNB demand charges")
    if include_facilities_proxy:
        # Cai 2017 facilities (rent) 0.033 USD/W at Cai's 120 W/m2 module -> USD/m2 (NOT Malaysian)
        parts["facilities_rent_cai_proxy"] = _v(lib, "cai_facilities_A", "USD/W") * _v(lib, "cai_module_W_per_m2", "count")
    else:
        omitted.append("land/rent/facilities")
    line.other_opex_usd_per_m2 = Tagged(sum(parts.values()),
        f"derived:{' + '.join(parts)} [REGIONAL: MY wage + MY tariff + MY FX only; activity drivers (headcount, kWh/m2, "
        f"hours) and maintenance share are non-MY proxies] [LOWER BOUND: omitted {', '.join(omitted)}]")
    line.name = f"liu2025_line@MY/{rate_basis}/bottom-up-{electricity}"
    line.notes.append("MY bottom-up other opex USD/m2: " + ", ".join(f"{k} {v:.3f}" for k, v in parts.items()))
    line.opex_parts_usd_m2 = parts
    line.opex_omitted = omitted
    return line


def materials_per_m2(design: dict, lib: dict | None = None, assumptions: dict | None = None,
                     price_case: str = "base", physics_setup: dict | None = None,
                     physics_library: dict | None = None) -> dict:
    """Materials cost per m2 of module for a validated design. Returns items, total, missing.
    price_case "high" uses a layer's `price_high` entry where one exists (sensitivity).
    physics_setup: see back_electrode_cost (None = production physics library).
    physics_library: the physics library the design is validated against (Paper B overlay; None = production)."""
    lib = lib or load_cost_library()
    assumptions = assumptions or {}
    d = validate(design, physics_library)
    items, missing, used = [], [], []
    for L in d["layers"]:
        m = lib["layer_materials"].get(L["material"])
        name = f"layer:{L['role']}:{L['material']}"
        if m is None:
            a = _assumed(assumptions, name)
            if a:
                items.append(a)
            else:
                missing.append(name)
            continue
        if "volume_price" in m:                  # priced per cm3 of deposited film (Liu NiOx, SnOx)
            vp = m["volume_price"]
            chk = vp.get("check")
            if chk:  # the source's volume must equal its thickness x 1 m2, else the per-cm3 reading is wrong
                v_ref = _v(lib, chk["volume"], "cm3")
                v_thk = _v(lib, chk["thickness"], "nm") * 1e-3
                if not math.isclose(v_ref, v_thk, rel_tol=1e-6):
                    raise CostLibraryError(f"{name}: source volume {v_ref} cm3 != thickness x 1 m2 = {v_thk} cm3")
            cost = L["thickness_nm"] * 1e-3 * _v(lib, vp["price"], "USD/cm3") / _v(lib, vp["utilisation"], "fraction")
            items.append({"item": name, "usd_m2": cost,
                          "tag": f"derived:thickness x 1 m2 x {vp['price']} / {vp['utilisation']}"})
            used += [vp["price"], vp["utilisation"]] + ([chk["volume"], chk["thickness"]] if chk else [])
            continue
        dens, dtag = _density(lib, m, name, assumptions)
        if dens is None:
            missing.append(f"density:{m['item']}")
            continue
        price_id = m.get("price_high") if (price_case == "high" and m.get("price_high")) else m["price"]
        vol_cm3 = L["thickness_nm"] * 1e-3                       # nm x 1e-7 cm/nm x 1e4 cm2 per m2
        cost = vol_cm3 * dens * _v(lib, price_id, "USD/g") / _v(lib, m["utilisation"], "fraction")
        tag = f"derived:thickness x {dtag} x {price_id} / {m['utilisation']}"
        if m.get("proxy_for"):
            tag += f" [PROXY: {m['proxy_for']}]"
        if dtag.startswith("ASSUMED"):
            tag = "assumed:" + tag
        items.append({"item": name, "usd_m2": cost, "tag": tag})
        used += [price_id, m["utilisation"]] + ([m["density_from"]["mass"], m["density_from"]["thickness"]]
                                                if "density_from" in m else ([m["density"]] if m.get("density") else []))
    for b in lib["bom_per_m2"]:
        name = f"bom:{b['item']}"
        if "mass" in b:
            cost = (_v(lib, b["mass"], "g") / 1000.0 * _v(lib, b["price_per_kg"], "USD/kg")
                    / _v(lib, b["utilisation"], "fraction"))
            used += [b["mass"], b["price_per_kg"], b["utilisation"]]
            tag = f"derived:{b['mass']}/1000 x {b['price_per_kg']} / {b['utilisation']}"
        else:
            pe = lib["_by_id"][b["price"]]
            if pe["unit"] not in ("USD/m2", "USD"):
                raise CostLibraryError(f"bom {b['item']}: price unit {pe['unit']} must be USD/m2 or USD (per module)")
            cost = float(b["quantity"]) * float(pe["value"]) / _v(lib, b["utilisation"], "fraction")
            used += [b["price"], b["utilisation"]]
            tag = f"derived:{b['quantity']} x {b['price']} / {b['utilisation']}"
        if b.get("proxy_for"):
            tag += f" [PROXY: {b['proxy_for']}]"
        items.append({"item": name, "usd_m2": cost, "tag": tag})
    for b in (lib.get("bom_by_architecture") or {}).get(d["architecture"], []):
        cost = _v(lib, b["volume"], "cm3") * _v(lib, b["price_per_cm3"], "USD/cm3") / _v(lib, b["utilisation"], "fraction")
        tag = f"derived:{b['volume']} x {b['price_per_cm3']} / {b['utilisation']}"
        if b.get("proxy_for"):
            tag += f" [PROXY: {b['proxy_for']}]"
        items.append({"item": f"bom:{b['item']}", "usd_m2": cost, "tag": tag})
        used += [b["volume"], b["price_per_cm3"], b["utilisation"]]
    be = back_electrode_cost(lib, price_case, d["architecture"], physics_setup)
    if be is not None:
        used += be.pop("used")
        items.append(be)
    else:
        a = _assumed(assumptions, "bom:back_electrode")
        if a:
            items.append(a)
        else:
            missing.append("bom:back_electrode")
    return {"items": items, "total_usd_m2": sum(i["usd_m2"] for i in items), "missing": missing,
            "sourced_entries_used": sorted(set(used))}


def cost_per_watt(materials_usd_m2: float, module_pce_pct: float, line: LineScenario) -> dict:
    dcf = _dcf()
    for k in ("capex_usd", "throughput_m2_per_yr", "depreciation_years", "rate", "yield_fraction",
              "other_opex_usd_per_m2"):
        v = getattr(line, k).value
        if not math.isfinite(v):
            raise CostLibraryError(f"line scenario '{line.name}': {k} is not set ({getattr(line, k).tag})")
    if not 0 < module_pce_pct < 40:
        raise CostLibraryError(f"module PCE {module_pce_pct} outside (0, 40)")
    if not 0 < line.yield_fraction.value <= 1:
        raise CostLibraryError("yield must be in (0, 1]")
    good_w_m2 = module_pce_pct / 100.0 * INCIDENT_W_M2 * line.yield_fraction.value
    crf = float(dcf.crf(line.rate.value, line.depreciation_years.value))
    capex_m2 = line.capex_usd.value * crf / line.throughput_m2_per_yr.value
    parts = {"materials": materials_usd_m2 / good_w_m2, "capital": capex_m2 / good_w_m2,
             "other_opex": line.other_opex_usd_per_m2.value / good_w_m2}
    return {"usd_per_W": sum(parts.values()), "parts_usd_per_W": parts, "good_W_per_m2": good_w_m2,
            "crf": crf, "capex_usd_per_m2_yr": capex_m2,
            "line": {k: {"value": getattr(line, k).value, "tag": getattr(line, k).tag}
                     for k in ("capex_usd", "throughput_m2_per_yr", "depreciation_years", "rate",
                               "yield_fraction", "other_opex_usd_per_m2")} | {"name": line.name}}


def evaluate_cost(design: dict, module_pce_pct: float, line: LineScenario,
                  assumptions: dict | None = None, physics_setup: dict | None = None,
                  physics_library: dict | None = None) -> dict:
    """Full cost result for one design at a given module PCE (from perodesign.module.module_from_cell).
    physics_setup / physics_library: Paper B material choice (see materials_per_m2); None = production."""
    lib = load_cost_library()
    mat = materials_per_m2(design, lib, assumptions, physics_setup=physics_setup, physics_library=physics_library)
    base = {"cost_library_sha256": lib["_sha256"], "materials": mat, "assumptions": assumptions or {}}
    if mat["missing"]:
        return {"status": "incomplete", "usd_per_W": None, "reason": f"no sourced price for {mat['missing']}", **base}
    c = cost_per_watt(mat["total_usd_m2"], module_pce_pct, line)
    assumed = [k for k, v in c["line"].items() if isinstance(v, dict) and str(v["tag"]).startswith("assumed")]
    assumed += [i["item"] for i in mat["items"] if i["tag"].startswith("assumed")]
    high = materials_per_m2(design, lib, assumptions, price_case="high", physics_setup=physics_setup,
                            physics_library=physics_library)
    c_high = cost_per_watt(high["total_usd_m2"], module_pce_pct, line)
    # A sourced number used for something other than what the source priced is a PROXY; list every one, so
    # "sourced" can never be read as "measured for this device in this region".
    proxies = [i["item"] for i in mat["items"] if "PROXY" in i["tag"]]
    proxies += [k for k, v in c["line"].items()
                if isinstance(v, dict) and ("NOT REGIONALISED" in str(v["tag"]) or "PROXY" in str(v["tag"])
                                            or "LOWER BOUND" in str(v["tag"]) or str(v["tag"]).startswith("derived"))]
    line_meta = {"name": c["line"].get("name"),
                 "regional_inputs": [k for k, v in c["line"].items() if isinstance(v, dict)
                                     and ("wdi_lend_" in str(v["tag"]) or "[REGIONAL:" in str(v["tag"]))],
                 "tags": {k: v["tag"] for k, v in c["line"].items() if isinstance(v, dict)}}
    # status: "sourced" only if nothing is assumed AND nothing is a proxy; otherwise say which it is.
    status = "with_assumptions" if assumed else ("sourced_with_proxies" if proxies else "sourced")
    return {"status": status, "assumed_inputs": assumed, "proxy_inputs": proxies, "line_meta": line_meta,
            "usd_per_W": c["usd_per_W"], "usd_per_W_high_prices": c_high["usd_per_W"], "breakdown": c, **base}
