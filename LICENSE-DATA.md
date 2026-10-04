# Licence for data, results and documentation

Copyright (c) 2026 Havid Aqoma.

Unless a file states otherwise, the data, results and documentation in this repository are licensed under the
Creative Commons Attribution 4.0 International licence (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/.
This covers:

* `phase0/` (stored runs, result files, figures, logs, post-hoc analyses)
* `source_data/` (Source Data workbooks)
* `paper/` (number tables, reference records, assumption records)
* `docs/` (pre-registrations and plans)
* `perodesign/library/*.yaml` and `perodesign/tea/cost_library_v1.yaml` (the material and cost libraries; each
  sourced value also carries the citation of its original source, which should be cited too)
* `README.md` and the other documentation files

The code (all `.py` files) is under the MIT licence in `LICENSE`.

## Third-party material

* `data/sources/`: excerpts and full texts of published sources, kept so that the cost model can check every quoted
  value. Each file keeps the licence of its source, stated in its header and listed in
  [data/sources/README.md](data/sources/README.md). Two of them are non-commercial (CC BY-NC 4.0 and
  CC BY-NC-ND 4.0); three are public tariff, statutory-rate or quotation records with no licence stated.
* `data/nk/`: optical constants; see [data/nk/README.md](data/nk/README.md) for their origin.
* `third_party/autotea/`: by the same author, under the MIT licence of this repository.
* SIMsalabim is not included. It is distributed by its authors under the GNU LGPL.
