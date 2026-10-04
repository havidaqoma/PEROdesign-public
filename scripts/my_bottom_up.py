"""Print Malaysia bottom-up electricity + labour per m2 and the resulting cost per W for the industrial device."""
import json
from pathlib import Path

from perodesign.module import ModuleGeometry, module_from_cell
from perodesign.physics.simss import SimSS
from perodesign.tea import (electricity_usd_per_m2_MY, evaluate_cost, labour_usd_per_m2, load_cost_library,
                            process_kwh_per_m2, region_line, region_line_MY_bottom_up)

lib = load_cost_library()
e = process_kwh_per_m2("p-i-n", lib)
print("process kWh/m2:", round(e["kWh_low"], 3), "-", round(e["kWh_high"], 3))
for s in e["steps"]:
    print("   ", f"{s['step']:32s}", round(s["kWh_low"], 3), round(s["kWh_high"], 3))
el = electricity_usd_per_m2_MY("p-i-n", lib)
lab = labour_usd_per_m2("MY", lib, throughput_m2_per_yr=region_line("MY", lib).throughput_m2_per_yr.value)
print(f"TNB energy {el['usd_per_kWh']:.4f} USD/kWh -> electricity {el['usd_m2_low']:.3f}-{el['usd_m2_high']:.3f} USD/m2; labour {lab.value:.3f} USD/m2")
d = {"schema": "perodesign.design/1", "architecture": "p-i-n", "layers": [
    {"role": "HTL", "material": "NiOx", "thickness_nm": 15}, {"role": "absorber", "material": "MAPbI3", "thickness_nm": 600},
    {"role": "ETL", "material": "C60", "thickness_nm": 30}, {"role": "buffer", "material": "SnO2", "thickness_nm": 10}]}
mod = module_from_cell(SimSS().run(d).metrics, ModuleGeometry(6.0, 0.2, 10.0, 0.03))
rows = []
for label, ln in [("MY, Liu CN other-opex (0.088 USD/W basis)", region_line("MY", lib)),
                  ("MY bottom-up (labour+electricity only), LOW", region_line_MY_bottom_up(lib, electricity="low", include_maintenance=False, include_demand=False)),
                  ("MY bottom-up + maintenance + TNB demand, LOW", region_line_MY_bottom_up(lib, electricity="low")),
                  ("MY bottom-up + maintenance + TNB demand, HIGH", region_line_MY_bottom_up(lib, electricity="high")),
                  ("  ... + Cai facilities/rent proxy (not MY)", region_line_MY_bottom_up(lib, electricity="high", include_facilities_proxy=True)),
                  ("  ... HIGH + WACC 10.2%", region_line_MY_bottom_up(lib, rate_basis="wacc_kajal", electricity="high"))]:
    r = evaluate_cost(d, mod["module_pce_pct"], ln)
    p = r["breakdown"]["parts_usd_per_W"]
    rows.append({"case": label, "usd_per_W": r["usd_per_W"], "parts": p, "status": r["status"],
                 "opex_parts_usd_m2": getattr(ln, "opex_parts_usd_m2", None), "omitted": getattr(ln, "opex_omitted", None),
                 "regional_inputs": r["line_meta"]["regional_inputs"], "other_opex_tag": r["line_meta"]["tags"]["other_opex_usd_per_m2"]})
    if getattr(ln, "opex_parts_usd_m2", None):
        print("      opex USD/m2:", {k: round(v, 3) for k, v in ln.opex_parts_usd_m2.items()})
    print(f"{label:44s} {r['usd_per_W']:.3f} USD/W  materials {p['materials']:.3f} capital {p['capital']:.3f} other {p['other_opex']:.3f}  "
          f"[{r['status']}] regional={r['line_meta']['regional_inputs']}")
(Path(__file__).resolve().parents[1] / "phase0" / "sim_bench" / "p1_my_bottom_up.json").write_text(json.dumps(
    {"README": "Malaysia bottom-up other opex = DOSM 2025 labour + Tian 2020 process electricity x TNB RP4 energy charge. "
               "Now INCLUDED (sourced): maintenance 1%/yr of capex (Kajal 2022), TNB capacity+network+fixed+KWTBB with max "
               "demand = average process load (LOWER BOUND, load factor 1). STILL OMITTED: HVAC/cleanroom, employer statutory "
               "contributions, 8% service tax; land/rent only as a non-MY Cai 2017 proxy case. "
               "The lower bottom-up total vs Liu's aggregate is an artefact of these omissions, NOT a Malaysia-vs-China finding. "
               "Only wage, tariff and FX are Malaysian; headcount and kWh/m2 are non-MY academic proxies. "
               "Materials and line capex remain Liu 2025 China values.",
     "kWh_per_m2": e, "electricity": el, "labour_usd_m2": lab.value, "labour_tag": lab.tag, "module_pce_pct": mod["module_pce_pct"], "rows": rows},
    indent=1, default=str))
