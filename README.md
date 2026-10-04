# PEROdesign: cost-aware design of perovskite solar modules

Code and data for the paper

> H. Aqoma, *Cost-aware design of perovskite solar modules with drift-diffusion simulation and multi-objective
> optimisation* (2026). Preprint and journal links will be added here when they exist.

The repository holds everything needed to check and reproduce the paper's results: the evaluation chain, the
optimisers, the two pre-registrations, all 180 stored optimisation runs (43,200 simulator calls), the result files,
the table of every number printed in the paper with the file it came from, and the Source Data workbooks.

## What the study does

Techno-economic studies of perovskite photovoltaics usually price a fixed device, while device models optimise
efficiency without cost. This study links three models and optimises module efficiency and cost per watt together:

```
design (layer thicknesses, stripe width, and at the second level the hole-transport layer and back metal)
  -> device model: SIMsalabim (SimSS 5.36) drift-diffusion, current-voltage curve under AM1.5G
  -> module model: stripe geometry, dead area, series resistance of the transparent electrode
  -> cost model: bottom-up factory-gate cost per watt for a Malaysian production line
  -> objectives: module efficiency (maximise), cost per watt (minimise)
```

Two levels of design freedom were pre-registered and run:

| Level | What the optimiser chooses | Runs | Simulator calls |
|---|---|---|---|
| Thickness-only design | layer thicknesses and stripe width in a fixed p-i-n or n-i-p stack | 90 | 21,600 |
| Material-choice design | the same, plus the hole-transport layer (NiOx or PTAA) and the back metal (Cu, Ag or Au) | 90 | 21,600 |

Each level compares a Bayesian optimiser, NSGA-II and Sobol random search on two stacks under three absorber-quality
scenarios, with 5 seeds and 240 calls per run.

Main results (see the paper for the full statement and its limits):

* With the materials fixed, the two ends of every Pareto front differed by at most 0.010 percentage points of
  efficiency and 0.188% of cost, so efficiency and cost point the same way.
* With material choice, every front split only on the back metal: silver added 0.05 to 0.29 points for 25% to 35%
  more cost per watt than copper, a trade-off only when the absorber is poor. NiOx dominated PTAA, and gold never
  reached a front.
* A mixed-variable Bayesian optimiser beat both alternatives in all six material-choice cases.

All results are model predictions. No device of these stacks was fabricated for this study.

## Repository layout

| Path | Contents |
|---|---|
| `perodesign/` | the package: SIMsalabim wrapper (`physics/`), module model (`module/`), cost model (`tea/`), objectives and optimisers (`optim/`), design schema (`schema/`), material library with a source or assumption tag on every value (`library/`) |
| `perodesign/library/materials_v2.yaml`, `paperB_overlay.yaml` | device parameters of every material; the overlay adds the material-choice options |
| `perodesign/tea/cost_library_v1.yaml` | every cost input with its verbatim quotation, source and confidence |
| `data/sources/` | the source texts behind every sourced cost number; the cost model checks each quotation against them when it loads ([licences](data/sources/README.md)) |
| `data/nk/` | optical constants used by the device model |
| `third_party/autotea/` | two hash-pinned files from the author's AutoTEA code (capital recovery factor, text normalisation) |
| `docs/PaperA_preregistration.md` | pre-registration of the thickness-only design |
| `docs/PaperB_preregistration.md` | pre-registration of the material-choice design, with its dated amendments A1 to A3 |
| `docs/PREREGISTRATION_PROVENANCE.md` | commit hashes, dates and file hashes of both pre-registrations |
| `phase0/paperA/`, `phase0/paperB/` | stored runs (`runs/*.json`, one file per run with every call), result files (`result.json`), figures, post-hoc analyses, logs |
| `phase0/sensitivity/` | global sensitivity analysis of the device model |
| `paper/paperAB/numbers.json`, `numbers_si.json` | every number printed in the paper and SI, with the file and field it came from |
| `paper/paperAB/assumption_support*.json` | every assumed input, the published quotation that supports it and the record of its check |
| `paper/paperAB/refs.json`, `references.bib`, `references_verified.tsv` | the reference list and its DOI check |
| `source_data/` | the two Source Data workbooks ([data dictionary](source_data/README.md)) |
| `scripts/` | runners, analysis, figures, Source Data and verification scripts |
| `tests/` | test suite |

The folder names `paperA` and `paperB` are the internal names of the thickness-only and material-choice designs.
They are kept because the stored run files and the pre-registrations refer to them.

## Quick start: check the stored results (no simulator needed)

Linux or WSL with Python 3.11:

```bash
git clone https://github.com/havidaqoma/PEROdesign-public.git
cd PEROdesign-public
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements-cpu.txt
python scripts/paperB_verify_runs.py        # integrity checks of the 90 material-choice run files
python scripts/paperA_numbers.py            # recompute every thickness-only number from the stored runs
python scripts/paperB_numbers.py
python scripts/paperAB_numbers.py
git status                                  # unchanged, apart from the PyTorch version string (2.14.0+cpu)
python -m pytest -q                         # simulator tests skip when SIMsalabim is not installed
```

This was tested from a fresh clone in a new environment: the tests pass (simulator tests skipped), and the
recomputed number files and Source Data workbooks match the shipped ones in every value.

Re-running the optimisations needs SIMsalabim 5.36. See [docs/REPRODUCE.md](docs/REPRODUCE.md) for the three
levels of reproduction (check, re-analyse, re-run), the expected run times, and how to install SIMsalabim.

## Where each figure and table comes from

| In the paper | Script | Output |
|---|---|---|
| Figure 1 (evaluation chain) | `scripts/paperA_figures.py` | `phase0/paperA/figures/fig1_environment.png` |
| Figure 2 (fronts, fixed materials) | `scripts/paperA_figures.py` | `phase0/paperA/figures/fig3_pareto_fronts.png` |
| Figure 3 (cost parts) | `scripts/paperA_figures.py` | `phase0/paperA/figures/fig4_cost_parts.png` |
| Figure 4 (fronts, material choice) | `scripts/paperB_figures.py` | `phase0/paperB/figures/figB1_fronts.png` |
| Figure 5 (cheap corner, material choice) | `scripts/paperB_figures.py` | `phase0/paperB/figures/figB2_front_zoom.png` |
| Figure 6 (hypervolume against calls) | `scripts/paperA_figures.py` | `phase0/paperA/figures/fig2_hv_vs_calls.png` |
| Tables 1 to 7 and every number in the text | `scripts/paperA_numbers.py`, `paperB_numbers.py`, `paperAB_numbers.py` | `paper/paperAB/numbers.json` (from `phase0/paperA/result.json`, `phase0/paperB/result.json`) |
| Supplementary figures and tables | `scripts/paperA_si_analysis.py`, `paperB_figures.py`, `paperB_posthoc.py`, `paperB_moox_bound.py`, `p2_sensitivity.py` | `phase0/paperA/si/`, `phase0/paperB/`, `phase0/sensitivity/`, `paper/paperAB/numbers_si.json` |
| Source Data workbooks | `scripts/paperA_sourcedata.py --merged`, `paperB_sourcedata.py` | `paper/paperAB/build/` (the published copies are in `source_data/`) |

File names follow the order in which the figures were made, not their order in the paper.

## How the results are kept honest

* **Pre-registration.** Both designs were pre-registered before their first optimisation run; amendments are dated
  and kept in the same files. Post-hoc analyses are labelled POST-HOC wherever they appear.
* **No hand-typed numbers.** Every number in the paper was filled in by the manuscript build from `numbers.json`,
  and the build refuses any number that is not there. Each entry names the file and field it came from. The
  manuscript sources and build scripts will be added here when the preprint is public.
* **Sourced inputs.** Every cost input carries a verbatim quotation; the cost model refuses to load if a quotation is
  not found in its source text. Every reference was resolved against OpenAlex and the DOI registry by a script.
* **Verification.** Stored runs were re-executed and stored designs were re-simulated with fresh simulator calls;
  the comparisons are in `phase0/paperA/si/` and `phase0/paperB/` (Supplementary Notes S8 and S15).

## Use of AI tools

This work is part of a research project on building a reliable autonomous research agent. Under the direction of
the author, an AI agent (Claude Opus 5, Anthropic, run through the Hermes agent framework) wrote the code, ran the
simulations and analyses, and drafted the text, following the two pre-registrations. A second model (Gemini 3.8
Flash High, Google) reviewed the pre-registrations, the material-choice results and the draft without write access.
Simulation, optimisation, statistics, figures and verification are deterministic scripts, not model output. The
author designed the study, fixed the pre-registration decisions and takes responsibility for the content.

## Licence

Code: MIT ([LICENSE](LICENSE)). Data, results and documentation: CC BY 4.0 ([LICENSE-DATA.md](LICENSE-DATA.md)).
Third-party material keeps its own licence: the source texts in `data/sources/` (see
[their table](data/sources/README.md)) and SIMsalabim (GNU LGPL, not included here).

## Citation

Please cite the paper; [CITATION.cff](CITATION.cff) gives the details, and GitHub's "Cite this repository" button
reads it. Please also cite SIMsalabim: M. Koopmans, V. M. Le Corre and L. J. A. Koster, *Journal of Open Source
Software*, 2022, 7, 3727, doi:10.21105/joss.03727.

## Contact

Havid Aqoma, School of Energy and Chemical Engineering, Xiamen University Malaysia
(havidaqoma.khoiruddin@xmu.edu.my, ORCID 0000-0003-1264-1916). Questions and problems: please open an issue.
