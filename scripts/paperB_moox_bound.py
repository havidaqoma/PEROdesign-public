"""POST-HOC cost bound for a hole-side interlayer (MoOx) in Study 2, n-i-p stack. Not pre-registered; no new simulations.

Why: with bare metal work functions (sensitivity S-WF) copper and silver on NiOx failed in the n-i-p stack, so the Study 2
front assumes an ohmic hole contact. In real devices that contact is commonly made with a thin evaporated MoOx layer
between the hole-transport layer and the metal. This script asks how much such a layer may cost before the Study 2
conclusions change, assuming it delivers the ohmic contact the model already assumes (no efficiency change).

Method (exact, same closed form as scripts/paperB_posthoc.py): cost per watt is linear in the materials bill, so adding
K USD/m2 to a design gives usd_per_W + K / good_W, good_W = module PCE x 1000 W/m2 x line yield. K is added to every
n-i-p design whose back metal is Cu or Ag (both HTLs; gold designs keep their contact). The p-i-n stack is not changed:
its metal sits on the electron side. Electricity and tool time for the extra evaporation step are NOT included.
Outputs: break-even K per scenario (front materials or pre-registered wording change), and K for a 10 nm layer at the
copper evaporation utilisation of the library with density 4.69 g/cm3, as a price per gram of MoO3.
Run in WSL: ~/venvs/perodesign-dev/bin/python scripts/paperB_moox_bound.py  ->  phase0/paperB/posthoc_moox.json
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
from paperB_posthoc import front_stats  # noqa: E402
from perodesign.optim import objective as A  # noqa: E402
from perodesign.tea import INCIDENT_W_M2, cost_per_watt, load_cost_library  # noqa: E402

PB = REPO / "phase0" / "paperB"
SCENS = ("base", "worse", "better")
MOOX_NM = 10.0                 # common evaporated MoOx/MoO3 interlayer thickness (SI Note S16, sources there)
MOOX_G_CM3 = 4.69              # MoO3 density (PubChem CID 14802)
USGS_MOO3_USD_KG = 51.0        # U.S. molybdic oxide (MoO3) price 2025e, USGS Mineral Commodity Summaries 2026


def main():
    lib = load_cost_library()
    util = next(e for e in lib["entries"] if e["id"] == "liu_cu_util")["value"]
    g_m2 = MOOX_NM * 1e-7 * 1e4 * MOOX_G_CM3 / util          # nm -> cm, x 1e4 cm2/m2, / utilisation
    line = A.cost_line()
    calls = {s: [] for s in SCENS}
    worst = 0.0
    for p in sorted((PB / "runs").glob("n-i-p__*.json")):
        r = json.loads(p.read_text())
        for c in r["calls"]:
            if not c["feasible"]:
                continue
            u0 = cost_per_watt(c["materials_usd_m2"], c["module_pce_pct"], line)["usd_per_W"]
            worst = max(worst, abs(u0 / c["usd_per_W"] - 1))
            c["_good_W"] = c["module_pce_pct"] / 100.0 * INCIDENT_W_M2 * line.yield_fraction.value
            calls[r["scenario"]].append(c)
    if worst > 1e-9:
        raise SystemExit(f"cost recompute does not reproduce stored USD/W (max rel err {worst})")

    def recost(c, k):
        return c["usd_per_W"] + (k / c["_good_W"] if c["metal"] in ("Cu", "Ag") else 0.0)

    chk = max(abs(recost(c, 0.7) / cost_per_watt(c["materials_usd_m2"] + 0.7, c["module_pce_pct"], line)["usd_per_W"] - 1)
              for c in calls["base"][:400] if c["metal"] in ("Cu", "Ag"))
    if chk > 1e-9:
        raise SystemExit(f"closed-form re-costing disagrees with the cost engine ({chk})")

    def stats(s, k):
        return front_stats([(c["module_pce_pct"], recost(c, k), f"{c['HTL']}/{c['metal']}") for c in calls[s]])

    out = {"schema": "perodesign.paperB_moox/1",
           "label": "POST-HOC (citation review 2026-10-02), not pre-registered; no new simulations",
           "assumes": "the interlayer gives the ohmic hole contact already assumed by rule B2 (efficiency unchanged); "
                      "added to every n-i-p Cu/Ag design; p-i-n unchanged; deposition electricity and tool time excluded",
           "recompute_max_rel_err": worst, "linear_check_max_rel_err": chk,
           "layer": {"thickness_nm": MOOX_NM, "density_g_cm3": MOOX_G_CM3, "utilisation": util,
                     "g_per_m2": g_m2}, "cases": {}}
    for s in SCENS:
        base = stats(s, 0.0)
        key = (tuple(base["combos"]), base["wording"])
        lo, hi = 0.0, 1.0
        while (tuple(stats(s, hi)["combos"]), stats(s, hi)["wording"]) == key and hi < 1e4:
            lo, hi = hi, hi * 2
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            lo, hi = (mid, hi) if (tuple(stats(s, mid)["combos"]), stats(s, mid)["wording"]) == key else (lo, mid)
        after = stats(s, hi)
        cu_best = min((c for c in calls[s] if c["metal"] == "Cu"), key=lambda c: c["usd_per_W"])
        out["cases"][f"n-i-p/{s}"] = {
            "no_interlayer": base, "breakeven_usd_m2": hi, "after_breakeven": after,
            "breakeven_usd_per_g_moo3": hi / g_m2,
            "usd_per_W_per_usd_m2_cheapest_cu": 1.0 / cu_best["_good_W"],
            "cheapest_cu_usd_per_W": cu_best["usd_per_W"]}
        print(s, base["combos"], base["wording"], "-> breakeven", round(hi, 3), "USD/m2 =",
              round(hi / g_m2, 1), "USD/g ->", after["combos"], after["wording"], flush=True)
    out = illustrative(out, lib, line)
    print("illustrative", json.dumps(out["illustrative"]), {k: (round(v["illustrative_add_usd_per_W_cheapest_cu"], 5),
          round(v["illustrative_add_pct_cheapest_cu"], 2)) for k, v in out["cases"].items()}, flush=True)
    (PB / "posthoc_moox.json").write_text(json.dumps(out, indent=1))


def illustrative(out, lib, line):
    """A sourced low estimate of K: MoO3 at the USGS bulk molybdic-oxide price (a floor: evaporation-grade powder costs
    more) plus the electricity of one extra vacuum step, proxied by the library's Cu sputtering step (Tian 2020) at the
    Malaysian MV energy charge. Tool capital and time are not included."""
    E = {e["id"]: e["value"] for e in lib["entries"]}
    usd_g = USGS_MOO3_USD_KG / 1000.0
    k_mat = out["layer"]["g_per_m2"] * usd_g
    k_el = E["tian_cu_sputter"] * E["tnb_mv_energy"] / E["wdi_fx_my_2025"]
    out["illustrative"] = {"moo3_usd_per_g_usgs_2025e": usd_g, "k_material_usd_m2": k_mat,
                           "k_step_electricity_usd_m2": k_el, "k_total_usd_m2": k_mat + k_el,
                           "excluded": "evaporator capital and tool time; evaporation-grade powder premium"}
    for k, v in out["cases"].items():
        add = (k_mat + k_el) * v["usd_per_W_per_usd_m2_cheapest_cu"]
        v["illustrative_add_usd_per_W_cheapest_cu"] = add
        v["illustrative_add_pct_cheapest_cu"] = 100 * add / v["cheapest_cu_usd_per_W"]
        v["breakeven_over_illustrative"] = v["breakeven_usd_m2"] / (k_mat + k_el)
    return out


if __name__ == "__main__":
    main()
