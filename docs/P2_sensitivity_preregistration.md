# P2 sensitivity analysis: which library parameters drive PCE and cost (pre-registration)

Written and committed 2026-09-29, **before any sensitivity run**. Plan v2 §16 lists this as the top risk:
"parameter library assumptions dominate results; Sobol in P2; report which 5 parameters drive MSP and PCE".
It is not a go/no-go gate. It is a required P2 deliverable, and it feeds the Paper A limitations and the choice of
which library values to re-source first.

## 1. Device and outputs
- **Device:** the industrial p-i-n reference that Paper A costs: NiOx 15 / MAPbI3 600 / C60 30 / SnO2 10 nm (Liu 2025
  thicknesses). Ideal contacts (library default). SimSS 5.36 wrapper defaults (NP 250, the P1 settings), not the G1 B3
  solver. Thickness is a design variable, so it is **not** varied.
- **Cost line:** Malaysia bottom-up (`region_line_MY_bottom_up`, lending rate, low electricity), module geometry
  6.0 / 0.2 mm, 10 ohm/sq, 3% edges (as `compare_devices.py`).
- **Outputs:**
  - Y1 = cell PCE (%);
  - Y2 = factory-gate cost (USD/W, base prices).
  - Module PCE is reported, not ranked.

## 2. Parameters and ranges (23)
Range convention, fixed in advance and the same for every parameter of a kind:
- densities, rates and mobilities: ×/÷ 10 around the library value, log-uniform;
- energies: ±0.1 eV, uniform.

These ranges are **assumed** (a convention, not measured spreads) and are labelled so in every output. The only
exceptions are marked "sourced".

| # | Parameter | Library value | Range |
|---|---|---|---|
| P1 | MAPbI3 N_t_bulk_m3 | 1e20 | 1e19–1e21 |
| P2 | MAPbI3 mu_n_m2_Vs | 1e-4 | 1e-5–1e-3 |
| P3 | MAPbI3 mu_p_m2_Vs | 1e-4 | 1e-5–1e-3 |
| P4 | MAPbI3 E_c_eV | 3.9 | 3.8–4.0 |
| P5 | MAPbI3 E_v_eV | 5.53 | 5.43–5.63 |
| P6 | MAPbI3 k_direct_m3_s | 1e-17 | 1e-18–1e-16 |
| P7 | MAPbI3 N_anion_m3 (= N_cation × 5/3 kept) | 5e21 | 5e20–5e22, N_cation scaled with it |
| P8 | interface NiOx/MAPbI3 N_t_int_m2 | 1e12 | 1e11–1e13 |
| P9 | interface MAPbI3/C60 N_t_int_m2 | 4e12 | 4e11–4e13 |
| P10 | NiOx N_A_m3 | 1e22 | 1e21–1e23 |
| P11 | NiOx mu_p_m2_Vs | 4.7e-4 | 4.7e-5–4.7e-3 |
| P12 | NiOx E_v_eV | 5.70 | 5.60–5.80 |
| P13 | C60 mu_n_m2_Vs | 1e-6 | 1e-7–1e-5 |
| P14 | C60 E_c_eV | 4.0 | 3.9–4.1 |
| P15 | SnO2 N_D_m3 | 1e22 | 1e21–1e23 |
| C1 | capital rate | 4.82% (WDI MY lending) | 4.82–10.2% uniform. **Sourced ends**: WDI MY lending rate and Kajal 2022 PV-factory WACC. |
| C2 | line capex | 20 M USD (Liu, "confidence low") | ×/÷ 2, log-uniform |
| C3 | yield | 50% (Liu) | 40–90%, uniform (assumed) |
| C4 | depreciation years | 5 (Liu) | 5–10, uniform (assumed) |
| C5 | FTO-glass price (largest BOM item, a proxy) | 10.0 USD/m² | ×/÷ 2, log-uniform |
| C6 | other opex (MY bottom-up, a lower bound) | as computed | × 1–3, uniform (the omitted items only add cost) |
| C7 | module dead width | 0.2 mm | 0.1–0.4 mm, uniform |
| C8 | TCO sheet resistance | 10 ohm/sq | 5–20, log-uniform |

The NiOx contact barrier is **not** included. It is already closed as a range (0.43–0.71 USD/W, MASTER §20), and
putting it in would dominate everything.

## 3. Method
- **Sample:** SALib Saltelli/Sobol sample, N = 512, first and total order only (no second order), scrambled with
  seed 3407. That is 512 × 25 = 12,800 rows. Rows that differ only in C-parameters share one simulation, so there are
  512 × 17 = 8,704 simulations.
- **Primary index:**
  - If **every** simulation completes, the primary index is the **Sobol total-order index S_T**, with 95% bootstrap
    CIs (SALib defaults, 1,000 resamples).
  - If **any** simulation fails, Sobol is not computed (its estimator needs every row). The primary index becomes the
    **Borgonovo δ** (SALib `delta`, given-data) on all completed rows. The failure fraction is reported, together
    with a failure-driver table: for each parameter, the failure rate in the lower and upper half of its range.
  - No failed row is imputed.
- **Top 5 for each output:** the 5 largest primary indices. The top 5 is **resolved** if the CI lower bound of rank 5
  is above the CI upper bound of rank 6. Otherwise it is reported as "not resolved", and the tied set is named.
- **Reporting:**
  - range of each output (5th / 50th / 95th percentile);
  - which top-5 parameters come from the SimSS default versus literature;
  - one sentence per top-5 parameter on what re-sourcing it would take.

## 4. What does not change
Nothing in the library or the cost library changes because of this analysis. It ranks uncertainty; it does not fit
anything.

## 5. Amendment (2026-09-30, after the simulations, before any index was computed)
The simulation run finished (8,704 of 8,704 recorded). Some simulations failed, so §3 selects the Borgonovo δ.
No sensitivity index, ranking or top 5 had been computed when this amendment was written. The simulation outcomes
and the §3 method choice are unchanged. Only the estimator call changes, because the one in the committed script did
not work:
- **What broke.** The installed SALib is 1.6.0. Its `delta.analyze` no longer returns a key called `delta`. It
  returns `delta_raw`, `delta_balanced` and `delta_step`. The committed call also ran all 23 parameters in one
  process, and far too slowly. The first analysis attempt was stopped with no output written.
- **Registered index.** The index is `delta_raw`: the Plischke et al. (2013) given-data estimator with a plain
  with-replacement bootstrap. It is the estimator §3 describes (the SALib 1.6.0 docstring describes "raw" as
  "bootstraps the input column as is, with random bootstrap sampling with replacement"). Settings: 1,000 resamples,
  95% CI, all completed rows.
- **Robustness check only.** `delta_balanced` (bin-balanced bootstrap) is reported next to it as
  `robustness_top5_delta_balanced`. It is never used for the ranking or the top-5 rule. SALib's own notes (for
  example "raw differs from balanced by >0.1") are copied into the result.
- **Run shape.** One job per (output, parameter), 46 jobs, run in parallel. Each job has a fixed seed,
  3407 + 1000·k + j (k = output index, j = parameter index), so the result does not depend on how the jobs are
  scheduled.
- **Disclosure.** After this text was written and before it was committed, a 3-resample smoke test ran the whole
  analysis path in a temp folder, to check the code. It printed a ranking. A ranking from 3 resamples is a code
  check, not a result: it is not saved, and nothing above was changed after seeing it.
- **Test.** The fast test rebuilds the outputs from `sims.jsonl` and checks the ranking rules. The full index
  recompute runs only when `PERODESIGN_SLOW=1` is set.
- **Speed fix (2026-09-30, second attempt stopped before any job finished; no index seen).** The first 1,000-resample
  run (commit f355799) had not finished a single job after 70 min. The cause was OpenBLAS: every one of the 12 worker
  processes started a thread per core, and the load reached ~150 on 14 cores. The script now sets one BLAS thread
  per process before numpy is imported. A timing probe on random Y (not a result) went from 22.0 s to 1.2 s for
  20 resamples of one parameter. This is a speed change only: the estimator, resamples, seeds and rows are the same.
