# Source texts behind the cost and material libraries

Every sourced number in `perodesign/tea/cost_library_v1.yaml` and in the material library carries a verbatim
quotation. When the libraries load, the code checks that each quotation appears in the source text named here, so
these files are needed to run the code. Each file starts with a header that gives the full citation, where and when
it was retrieved, and its licence.

The table below is generated from those headers. Each file keeps the licence of its source; the CC BY 4.0 licence of
this repository's data does not apply to them.

* Non-commercial: `tian2020_sciadv_si.txt` (CC BY-NC 4.0, two supplementary tables) and `dipta2022_heliyon.txt`
  (CC BY-NC-ND 4.0, unmodified text and tables, converted from XML). Do not reuse them commercially.
* No licence stated: `tnb_rates_2026_09.txt` (the public electricity tariff table of Tenaga Nasional Berhad),
  `kwsp_epf_rates_2026_10.txt` (the statutory contribution rates published by the Employees Provident Fund of
  Malaysia) and `hossain2020_rscadv_quote.txt` (one sentence, kept as a quotation with citation). They are kept only
  so that the cited values can be checked.

| File | Source | Licence |
|---|---|---|
| `ag_density_pmc5784555.txt` | doi:10.1186/s12989-018-0243-7 | CC BY 4.0 |
| `au_density_pmc3660288.txt` | doi:10.1186/1743-8977-10-19 | CC BY 2.0 |
| `cai2017_advs_si.txt` | doi:10.1002/advs.201600269 | CC BY 4.0 |
| `dipta2022_heliyon.txt` | doi:10.1016/j.heliyon.2022.e11380 | CC BY-NC-ND 4.0 |
| `dosm_salaries_wages_2025.txt` | https://storage.dosm.gov.my/labour/salaries_wages_2025.xlsx | CC BY 4.0 |
| `njema2025_rscadv.txt` | doi:10.1039/d5ra06604b | CC BY 3.0 |
| `pochont2022_molecules.txt` | doi:10.3390/molecules27227927 | CC BY 4.0 |
| `stanic2021_materials.txt` | doi:10.3390/ma14216341 | CC BY 4.0 |
| `stanic2022_materials.txt` | doi:10.3390/ma15207310 | CC BY 4.0 |
| `hossain2020_rscadv_quote.txt` | doi:10.1039/d0ra00939c | not stated |
| `kajal2022_gch.txt` | doi:10.1002/gch2.202100070 | CC BY 4.0 |
| `kwsp_epf_rates_2026_10.txt` | https://www.kwsp.gov.my/en/employer/responsibilities/mandatory-contribution | not stated |
| `lee2018_scirep_nio.txt` | doi:10.1038/s41598-018-23907-0 | CC BY 4.0 |
| `liu2025_nml.txt` | doi:10.1007/s40820-025-01744-x | CC BY 4.0 |
| `mukherjee2024_ma_nio.txt` | doi:10.1039/d4ma00873a | CC BY 3.0 |
| `shahinuzzaman2022_nano.txt` | doi:10.3390/nano12173003 | CC BY 4.0 |
| `tian2020_sciadv_si.txt` | doi:10.1126/sciadv.abb0055 | CC BY-NC 4.0 |
| `tnb_rates_2026_09.txt` | https://www.mytnb.com.my/tariff | not stated |
| `vivo2017_materials.txt` | doi:10.3390/ma10091087 | CC BY 4.0 |
| `wf_fto_au_mi2021.txt` | doi:10.3390/mi12121508 | CC BY 4.0 |
| `wf_ito_au_srep2023.txt` | doi:10.1038/s41598-023-28506-2 | CC BY 4.0 |
| `wf_metals_nano2021.txt` | doi:10.3390/nano11051218 | CC BY 4.0 |
| `worldbank_pink_2026_09.txt` | https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Pink-Sheet-September-2026.pdf | CC BY 4.0 |
| `worldbank_wdi_2026_07.txt` | https://api.worldbank.org/v2/country/MYS | CC BY 4.0 |

The texts are verbatim copies of open-access publications, so some contain the authors' published contact lines
(e-mail addresses in the "Contributor Information" or correspondence blocks, in 12 files). They are left as
published: seven of these files are pinned by SHA-256 in `perodesign/tea/cost_library_v1.yaml`, so changing a byte
would make the cost model refuse to load, and the other five are kept unchanged so that every quotation taken from
them can be checked against the published text.
