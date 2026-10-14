# Reproducing the results

There are three levels. Each one checks more of the chain and takes longer.

| Level | What it checks | Needs SIMsalabim | Time |
|---|---|---|---|
| 1. Check | the stored run files are complete and consistent; the tests pass | no | minutes |
| 2. Re-analyse | every number, table, figure and Source Data workbook is recomputed from the stored runs | no | minutes |
| 3. Re-run | optimisation runs and designs are re-simulated with the real simulator | yes | minutes per run up to days for everything |

All commands are run from the repository root. They were tested on Ubuntu 22.04 (WSL 2 on Windows 11) with
Python 3.11.

## Environment

```bash
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
uv pip install -r requirements-cpu.txt
```

`requirements-cpu.txt` is the frozen environment of the runs with the CPU build of PyTorch, plus openpyxl for the
Source Data workbooks. The runs themselves
used the CUDA build listed in `requirements-wsl-dev.txt`; the code does not use the GPU. With plain pip, run the same two
install commands without `uv`.

Use a Linux file system (for example your WSL home directory, not `/mnt/c`) for level 3: the runners write many
small files.

## Level 1: check

```bash
python scripts/paperB_verify_runs.py    # deterministic checks of the 90 material-choice run files
python -m pytest -q                     # tests that need SIMsalabim skip when it is not installed
```

## Level 2: re-analyse

```bash
python scripts/paperA_numbers.py        # -> paper/paperA/numbers.json   (thickness-only numbers)
python scripts/paperB_numbers.py        # -> phase0/paperB/numbers.json  (material-choice numbers)
python scripts/paperAB_numbers.py       # -> paper/paperAB/numbers.json  (every number in the paper)
python scripts/paperA_figures.py        # -> phase0/paperA/figures/
python scripts/paperB_figures.py        # -> phase0/paperB/figures/
python scripts/paperB_moox_bound.py     # POST-HOC interlayer cost bound -> phase0/paperB/posthoc_moox.json
python scripts/paperA_sourcedata.py --merged   # -> paper/paperAB/build/SourceData_thickness_only.xlsx
python scripts/paperB_sourcedata.py            # -> paper/paperAB/build/SourceData_material_choice.xlsx
git status                              # the JSON outputs should be unchanged
```

The number files and post-hoc JSON files should come out identical to the committed ones; `git status` shows any
that differ. With the CPU build of PyTorch, the one expected difference is the PyTorch version string recorded
in `paper/paperA/numbers.json` and `paper/paperAB/numbers.json` (`2.14.0+cpu` instead of `2.14.0`). Figures may differ in bytes (fonts and library versions) but not in content. The two workbooks are
written to `paper/paperAB/build/`; compare them with the copies in `source_data/`. Each Source Data script re-reads
its workbook and checks row counts and sample values against the run files.

Three scripts need SIMsalabim and are part of level 3: `scripts/paperB_si_verify.py` (the checks of Supplementary
Note S15; its last check re-simulates 60 stored designs), `scripts/paperB_posthoc.py` (the POST-HOC contact
attribution of Supplementary Note S16 re-simulates the optimised NiOx designs) and `scripts/paperAB_mesh_check.py`
(the POST-HOC grid check of Supplementary Note S19 re-simulates the 24 stored front ends at 250, 500 and 1000 grid
points, 72 simulations, output `phase0/paperB/posthoc_mesh.json`).

## Level 3: re-run with SIMsalabim

### Install SIMsalabim 5.36

The runs used SIMsalabim release `v5.36` (commit `d48e0e78cb2be8462363fb93f639c8081009dc33`), compiled for Linux
with Free Pascal 3.2.2 (the binary reports `FPC 3.2.2+dfsg-32`). The binary's SHA-256 was
`1d9072f5a8049d26bec59dd7101adb53fcc3290db76f2598d2a493e7ac4bae55`. It is recorded in every thickness-only run
file. The material-choice run files do not record it; the same binary re-simulates their stored designs
bit for bit (Supplementary Note S15, and the release check below).

```bash
sudo apt install fpc                    # Free Pascal 3.2.x
git clone --branch v5.36 https://github.com/kostergroup/SIMsalabim.git ~/SIMsalabim
(cd ~/SIMsalabim/SimSS && fpc simss)    # the compile command of the SIMsalabim README
export PERODESIGN_SIMSALABIM=~/SIMsalabim
python -m pytest -q tests/test_simss.py # the simulator tests now run instead of skipping
```

SIMsalabim also offers pre-compiled binaries on its releases page. A binary built with another compiler version or
options can give results that differ in the last digits; the result cache (below) is keyed on the binary's hash, so the
stored cache is never mixed with a different binary.

Optional settings:

| Variable | Meaning | Default |
|---|---|---|
| `PERODESIGN_SIMSALABIM` | root of the SIMsalabim checkout (the folder holding `SimSS/` and `Data/`) | the path used for the published runs |
| `PERODESIGN_SIMSS_DIR`, `PERODESIGN_SIMSS_DATA` | the `SimSS` and `Data` folders, if not under one root | from `PERODESIGN_SIMSALABIM` |
| `PAPERA_CACHE`, `PAPERB_CACHE` | simulator result cache; point at an empty folder to force real simulations | `~/perodesign_p1/...` |
| `AUTOTEA_ROOT` | a full AutoTEA checkout instead of `third_party/autotea` | `third_party/autotea` |

### Re-execute a stored run and compare

```bash
export PAPERA_CACHE=$(mktemp -d)        # no cache: every call is a real simulation
python scripts/paperA_si_rerun.py . p-i-n__worse__nsga2__s2
cat phase0/paperA/si/rerun_p-i-n__worse__nsga2__s2.json   # identical_x and identical_objectives out of 240
```

For the paper, four thickness-only runs (covering all three optimisers and both stacks) were re-executed this way: all 240 designs
and objectives of each run were identical to the stored ones. 96 stored designs were also re-simulated from
scratch with identical results (Supplementary Note S8). For the material-choice design, `paperB_si_verify.py`
re-simulates 60 stored designs (Supplementary Note S15).

### Re-run everything

```bash
python scripts/paperA_run.py run 12     # 90 runs; resumable, finished runs are skipped
python scripts/paperA_run.py analyse    # -> phase0/paperA/result.json
python scripts/paperB_run.py run 12
python scripts/paperB_run.py analyse    # -> phase0/paperB/result.json
python scripts/paperB_run.py swf        # bare metal work function check
```

The runners skip any run whose file already exists, so move `phase0/paperA/runs/` and `phase0/paperB/runs/` aside
first. Summed over all runs, the original runs took about 27 hours (thickness-only) and 110 hours
(material-choice) of single-process time, most of it in the Bayesian optimiser of the material-choice design; they
ran in parallel on a 14-thread machine. The global sensitivity analysis is `python scripts/p2_sensitivity.py run 12`
followed by `analyse`.

Memory: a mixed-variable Bayesian optimiser run grows to about 7 GB as its training data accumulate. The original
runs therefore executed at most 6 of them at the same time (`PAPERB_BO_MAX`, default 6) in 47 GB of memory
(analysis plan, Amendment A2). With less memory, set `PAPERB_BO_MAX` lower; this changes wall time only, because
the designs a run evaluates depend only on its seed.

## Release check

Before publication this tree was cloned into a new Python 3.11 environment built from `requirements-cpu.txt` and
checked at all three levels. Level 1: the run-file checks passed and the tests passed (193 passed, 16 skipped
without SIMsalabim). Level 2: every number file and post-hoc file came out identical, and the two rebuilt Source
Data workbooks matched the shipped ones in all 1,291,828 cells apart from the PyTorch version string. Level 3,
with SIMsalabim 5.36 (binary hash above): the simulator tests passed; the thickness-only run
`p-i-n__worse__nsga2__s2` re-executed without a cache gave all 240 designs and objectives identical to the stored
run (about 10 minutes); `paperB_si_verify.py` passed all six checks, including the fresh re-simulation of 60
material-choice designs; and `paperB_posthoc.py` reproduced `phase0/paperB/posthoc.json` exactly.

## Checking a single number

Every number in the paper is an entry in `paper/paperAB/numbers.json` (main text) or `numbers_si.json` (SI). Each
entry holds the printed value, the raw value and the file and field it came from. For example, the 0.010-point
efficiency gap in the abstract is the entry `gpce_nip_better`: raw value 0.009765..., read from
`phase0/paperA/result.json`, field `cases['n-i-p/better'].q2.gap_pce_points`.
