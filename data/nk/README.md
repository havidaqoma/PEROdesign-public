# Optical constants added by PeroDesign (not shipped with SIMsalabim)

| File | Material | Source | Licence | Range |
|---|---|---|---|---|
| `nk_Cu_McPeak2015.txt` | Cu (thermally evaporated) | McPeak et al., ACS Photonics 2, 326 (2015), doi:10.1021/ph5004237, via refractiveindex.info `main/Cu/nk/McPeak.yml` | CC0 1.0 (refractiveindex.info database) | 300–1700 nm |

Format: SimSS nk file (`lambda n k`, lambda in metres), converted from the database's micrometre table
without interpolation. The original YAML is kept alongside as `McPeak_Cu.yml`.
| `nk_NiOx_const_n2p3.txt`, `nk_SnO2_const_n2p3.txt` | NiOx, SnO2 | **ASSUMPTION**: non-absorbing (k = 0), constant n = 2.3 = midpoint of the range "comparable refractive indices ranging from 2.1–2.5" for perovskite and metal oxides (Hossain et al., RSC Adv. 2020, doi:10.1039/d0ra00939c; quote in `data/sources/hossain2020_rscadv_quote.txt`). No open measured n,k table was found (searched 2026-09-28). Sensitivity n = 2.1 / 2.5 is tested. | n/a (generated) | 300–1200 nm |
