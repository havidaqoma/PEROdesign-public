"""POST-HOC (pre-submission review 2026-10-09, not pre-registered): how the absorber price of the cost library compares
with published perovskite precursor prices, and where those prices sit against the absorber-price scan of Note S9.

The cost library prices the absorber with the 0.63 USD/g of an unspecified production perovskite (Liu 2025). Two
published sources give prices for real precursors:
  - Chang et al. 2017 (Prog. Photovolt., doi:10.1002/pip.2871), Table 8: PbI2 and methylammonium iodide (MAI) in US$/g
    with an uncertainty range, adjusted by the authors for volume. MAPbI3 is formed from PbI2 + MAI (1:1 molar), so the
    price per gram of MAPbI3 is the mass-weighted sum.
  - Wu et al. 2026 (Adv. Mater., doi:10.1002/adma.73266): 1 kg of a virgin mixed-cation, mixed-halide precursor mixture
    at bulk laboratory prices, in EUR; converted with the World Bank official EUR per USD rate (PA.NUS.FCRF, euro area).
Every price is extracted from the fetched source text by regex (nothing typed by hand). Output:
phase0/paperB/posthoc_absorber_prices.json, read by scripts/paperAB_numbers.py and the SI build (Note S17).
"""
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from paperAB_assumptions_verify import fetch, text_of  # noqa: E402  (same cache and text extraction as the quote check)

CHANG = "https://unsworks.unsw.edu.au/bitstreams/a78d60f4-fa61-4fb3-8f5b-c47b9b7e53e8/download"
WU = "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13244800/fullTextXML"
WB = "https://api.worldbank.org/v2/country/EMU/indicator/PA.NUS.FCRF?format=json&date=2025"
AW = {"Pb": 207.2, "I": 126.904, "C": 12.011, "H": 1.008, "N": 14.007}   # IUPAC standard atomic weights (abridged)
OUT = REPO / "phase0" / "paperB" / "posthoc_absorber_prices.json"
NUM = r"([0-9]+(?:\.[0-9]+)?)"


def row(t, material):
    """Table 8 row '<process> <material> g <usage> (<lo>-<hi>) [ref] <cost> (<lo>-<hi>)', cost in US$/g."""
    m = re.search(rf"Coat {material} g {NUM} \({NUM}-{NUM}\) \[\d+ \] {NUM} \({NUM}-{NUM}\)", t)
    if not m:
        raise SystemExit(f"Chang 2017 Table 8: row for {material} not found")
    return {"usd_per_g": float(m.group(4)), "lo": float(m.group(5)), "hi": float(m.group(6)), "quote": m.group(0)}


def main():
    raw_c = fetch(CHANG)
    tc = re.sub(r"\s+", " ", text_of(raw_c))
    if "Cost (US$/unit)" not in tc:
        raise SystemExit("Chang 2017: Table 8 header with the cost unit not found")
    pbi2, mai = row(tc, "PbI2"), row(tc, "MAI")
    m_pbi2 = AW["Pb"] + 2 * AW["I"]
    m_mai = AW["C"] + 6 * AW["H"] + AW["N"] + AW["I"]
    w_pbi2 = m_pbi2 / (m_pbi2 + m_mai)
    mix = {k: w_pbi2 * pbi2[k] + (1 - w_pbi2) * mai[k] for k in ("usd_per_g", "lo", "hi")}
    raw_w = fetch(WU)
    tw = re.sub(r"\s+", " ", text_of(raw_w))
    m = re.search(rf"1 kg of virgin perovskite precursor mixture costs {NUM}\s*€", tw)
    if not m or "representative bulk laboratory pricing" not in tw:
        raise SystemExit("Wu 2026: price sentence or the 'bulk laboratory pricing' basis not found")
    eur_per_kg = float(m.group(1))
    with urllib.request.urlopen(urllib.request.Request(WB, headers={"User-Agent": "PEROdesign"}), timeout=60) as r:
        raw_b = r.read()
    wb = json.loads(raw_b)[1][0]
    if wb["date"] != "2025" or wb["indicator"]["id"] != "PA.NUS.FCRF" or wb["countryiso3code"] != "EMU":
        raise SystemExit(f"World Bank record is not the 2025 euro-area rate: {wb}")
    eur_per_usd = float(wb["value"])
    lab = eur_per_kg / 1000 / eur_per_usd
    lib_price = 0.63
    lib = (REPO / "perodesign" / "tea" / "cost_library_v1.yaml").read_text(encoding="utf-8")
    if not re.search(r"id: liu_perovskite_price, .*value: 0\.63,", lib):
        raise SystemExit("cost library absorber price is no longer 0.63 USD/g")
    scan = json.loads((REPO / "phase0" / "paperA" / "si" / "si_result.json").read_text(encoding="utf-8"))
    pb = sorted(s["value"] for s in scan["sensitivity"]["scans"]["absorber_price_mult"]
                if s["arch"] == "p-i-n" and s["scenario"] == "base")
    small = {s["value"]: s["small"] for s in scan["sensitivity"]["scans"]["absorber_price_mult"]
             if s["arch"] == "p-i-n" and s["scenario"] == "base"}
    first = min(v for v in pb if not small[v])
    last_small = max(v for v in pb if v < first)
    out = {"schema": "perodesign.posthoc_absorber_prices/v1", "label": "POST-HOC, not pre-registered",
           "library_usd_per_g": lib_price,
           "chang2017": {"url": CHANG, "sha256": hashlib.sha256(raw_c).hexdigest(), "PbI2": pbi2, "MAI": mai,
                         "mass_fraction_PbI2_in_MAPbI3": w_pbi2, "MAPbI3_usd_per_g": mix},
           "wu2026": {"url": WU, "sha256": hashlib.sha256(raw_w).hexdigest(), "eur_per_kg": eur_per_kg,
                      "quote": m.group(0), "basis": "representative bulk laboratory pricing (1 kg precursor batches)",
                      "eur_per_usd_2025": eur_per_usd, "wb_url": WB, "wb_sha256": hashlib.sha256(raw_b).hexdigest(),
                      "usd_per_g": lab},
           "scan_pin_base": {"multipliers": pb, "last_small_mult": last_small, "first_not_small_mult": first,
                             "last_small_usd_per_g": last_small * lib_price, "first_not_small_usd_per_g": first * lib_price},
           "multiples_of_library": {"chang_mid": mix["usd_per_g"] / lib_price, "chang_lo": mix["lo"] / lib_price,
                                    "chang_hi": mix["hi"] / lib_price, "wu_lab": lab / lib_price}}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("scan_pin_base", "multiples_of_library")}, indent=1),
          round(mix["usd_per_g"], 3), round(mix["lo"], 3), round(mix["hi"], 3), round(lab, 3))


if __name__ == "__main__":
    main()
