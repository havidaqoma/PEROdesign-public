# Vendored AutoTEA files

Two files from AutoTEA, the author's techno-economic analysis code, copied byte for byte from commit
`1e8fa5afe7ac8f79a2b27f7069dd49528ea222b7` (2026-09-15):

| File | Used by | sha256 (pinned in the code) |
|---|---|---|
| `src/core/dcf.py` | `perodesign/tea/__init__.py` (capital recovery factor) | `8e7a52b4f38d561428808d1309b447140ab414ffe3b38529548624200dc33cb6` |
| `src/validation/provenance.py` | `perodesign/tea/provenance.py` (text normalisation of the provenance gate) | `f7f360ad2f9032e77a6915033652dcdf6eca6c16fe91a7b7eb076292320b5dfc` |

The `__init__.py` files are empty package markers from the same commit. PEROdesign refuses to load either file if
its sha256 differs from the pinned value, so do not edit them. To use a full AutoTEA checkout instead, set the
environment variable `AUTOTEA_ROOT` to its root; the same hash check applies.

Both files are by the same author as PEROdesign and are distributed here under the PEROdesign licence.
