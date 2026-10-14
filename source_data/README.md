# Source Data

Two Excel workbooks hold the data behind the paper: every simulator call, the data behind every figure and
table, the material and cost libraries with their sources, every assumption, and every number printed in the
paper. They are written from the stored files by `scripts/paperA_sourcedata.py --merged` and
`scripts/paperB_sourcedata.py`, which re-read each workbook and check it against the run files.

Each workbook starts with a `README` sheet. Its status labels: **measured** (read from a simulator call),
**computed** (derived by a script from measured values), **sourced** (a published value, with its quotation and
source), **assumed** (a value chosen by the author, with the reason) and **post-hoc** (analysis added after the
pre-specified analysis). All efficiencies and costs are model predictions.

Units: efficiencies in percent (PCE) or percentage points (differences), thicknesses in nm, stripe width in mm,
cost per watt in USD/W, area costs in USD/m2. Hypervolume is in PCE points x USD/W for the thickness-only design
and in PCE points x decades of USD/W for the material-choice design; IGD+ is dimensionless. Column names carry
their unit where one applies, and each README sheet repeats the units.

Reading a sheet: row 1 is a title, then optional note rows and one blank row; the header is the row after the
blank row (pandas: `header=2` with no note row, `header=3` with one). `calls_to_95pct = 241` means the run did not
reach 95% of the best hypervolume within 240 calls. `design_hash` is the SHA-256 of the device input passed to the
simulator; it does not cover the stripe width, so a design is identified by `design_hash` with the stripe width.

## `SourceData_thickness_only.xlsx`: thickness-only design (fixed materials)

| Sheet | Content | Rows in sheet (with header) | Columns |
|---|---|---|---|
| `Calls_all` | every simulator call of all 90 runs (21,600 rows): inputs, simulator outputs, module factors, objectives | 21,601 | `arch`, `scenario`, `method`, `seed`, `call`, `batch`, `u (unit cube)`, `x1_nm`, `x2_nm`, `x3_nm`, `x4_nm`, `stripe_mm`, ... (30 in total) |
| `Runs_summary` | one row per run: final hypervolume, infeasible calls, calls to 95%, wall time, hashes | 91 | `arch`, `scenario`, `method`, `seed`, `hv_final (PCE pt x USD/W)`, `n_infeasible`, `calls_to_95pct_best (241 = not reached)`, `best_module_pce_pct`, `lowest_usd_per_W`, `wall_seconds`, `ref_pce_pct`, `ref_usd_per_W`, ... (14 in total) |
| `Table1_space` | main Table 1: search spaces | 10 | `stack`, `variable`, `lower`, `upper`, `provenance` |
| `Table5_Q1_HV` | main Table 5: final hypervolume (PCE points x USD/W) mean and 95% CI, verdicts | 19 | `case`, `method`, `hv_mean (PCE pt x USD/W)`, `hv_ci95_half (t, 4 dof)`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4`, `verdicts (CI non-overlap)` |
| `TableS33_speed` | SI Table S33 (moved from the main text): median calls to 95% of the best hypervolume | 19 | `case`, `method`, `median`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `Table2_gap` | main Table 2: two ends of the pooled Pareto front per case | 7 | `case`, `front_size`, `n_feasible_pooled`, `PCE-opt module_pce_pct`, `PCE-opt usd_per_W`, `cost-opt module_pce_pct`, `cost-opt usd_per_W`, `gap_pce_points`, `gap_cost_pct`, `gap_small (<1 pt and <5%)` |
| `Table3_designs` | main Table 3 and both front ends: designs, cell PCE, cost parts, CN/IN rate rows | 13 | `case`, `end`, `design (nm, stripe mm)`, `cell_pce_pct`, `module_pce_pct`, `usd_per_W`, `materials_usd_m2`, `part materials USD/W`, `part capital USD/W`, `part other opex USD/W`, `USD/W MY rate`, `USD/W CN rate`, ... (13 in total) |
| `Fig6_HV_curves` | main Figure 6a: mean and 95% band of hypervolume vs calls (and every seed) | 4,321 | `arch`, `scenario`, `method`, `call`, `mean`, `band_lo`, `band_hi`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `Fig2_front_points` | main Figure 2: Pareto front points per case (all feasible points are in Calls_all) | 14 | `arch`, `scenario`, `module_pce_pct`, `usd_per_W`, `materials_usd_m2`, `design`, `cell_pce_pct` |
| `Fig3_cost_parts` | main Figure 3: cost-part shares at the PCE-optimal design | 7 | `arch`, `scenario`, `total usd_per_W`, `materials %`, `capital %`, `other opex %` |
| `FigS1_bestPCE` | SI Figure S1: best module PCE so far vs calls (mean, band, every seed) | 4,321 | `arch`, `scenario`, `method`, `call`, `mean`, `band_lo`, `band_hi`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `FigS2_final_scores` | SI Figure S2 and Table S13: per-seed final scores and alternative verdicts | 115 | `case`, `method`, `metric`, `mean / value`, `ci95_half`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `FigS5_scans` | SI Figure S5 and Table S12: post-hoc gap scans | 181 | `scan`, `value`, `arch`, `scenario`, `gap_pce_pt`, `gap_cost_pct`, `small`, `front_size`, `PCE-opt design`, `cost-opt design` |
| `TableS11_sensitivity` | SI Table S11: post-hoc gap under single changed assumptions | 151 | `group`, `change`, `arch`, `scenario`, `front_size`, `PCE-opt module %`, `PCE-opt USD/W`, `cost-opt module %`, `cost-opt USD/W`, `gap_pce_pt`, `gap_cost_pct`, `small`, ... (15 in total) |
| `FigS7_repeats` | SI Figure S7: repeated cell devices and repeated full designs per run | 91 | `arch`, `scenario`, `method`, `seed`, `cell_device_repeats`, `full_design_repeats` |
| `FigS8_P2_sensitivity` | SI Figure S8 and Table S8: earlier global sensitivity ranking | 47 | `output`, `rank`, `parameter`, `Borgonovo delta`, `ci95_half`, `S1` |
| `Verification` | SI Table S9/S10: deterministic checks, re-execution and fresh re-simulation | 18 | `check`, `result` |
| `Verification_fresh` | SI Table S10: stored calls re-simulated without the cache, stored and new values side by side | 97 | `run`, `call`, `x`, `stored_sim_status`, `stored_cell_pce_pct`, `stored_voc_V`, `stored_ff`, `stored_jsc_mA_cm2`, `stored_module_pce_pct`, `stored_usd_per_W`, `stored_materials_usd_m2`, `stored_feasible`, ... (22 in total) |
| `Physics_library` | every layer, interface and device parameter passed to SimSS, with provenance | 270 | `kind`, `material / pair`, `parameter`, `value`, `provenance status`, `source file`, `overridable range` |
| `Cost_library` | every cost-library entry: value, unit, verbatim quotation, source, confidence | 91 | `id`, `value`, `unit`, `role`, `item`, `source`, `verbatim quote`, `confidence`, `basis year`, `geography`, `notes` |
| `Cost_sources` | registered source files with DOI, licence and SHA-256 | 13 | `key`, `citation`, `doi`, `licence`, `geography`, `file`, `sha256`, `notes` |
| `Cost_structure` | line inputs, operating-cost parts, materials bill decomposition (USD/m2) | 39 | `group`, `item`, `value`, `tag / note` |
| `Assumptions` | every assumption, proxy and fixed setting of the study, with where it is used | 34 | `area`, `assumption / setting`, `value`, `unit`, `status`, `where in code / library` |
| `Numbers_main_text` | every number printed in the manuscript: token, printed value, raw value, source | 481 | `token`, `printed`, `raw`, `source`, `file` |

## `SourceData_material_choice.xlsx`: material-choice design (the optimiser also chooses the hole-transport layer and the back metal)

| Sheet | Content | Rows in sheet (with header) | Columns |
|---|---|---|---|
| `Calls_all` | every simulator call of the 90 runs (measured) | 21,601 | `arch`, `scenario`, `method`, `seed`, `call`, `batch`, `HTL`, `metal`, `feasible`, `sim_status`, `reason`, `x`, ... (25 in total) |
| `Runs_summary` | one row per run (measured / computed) | 91 | `arch`, `scenario`, `method`, `seed`, `seconds`, `n_infeasible`, `hv_final (PCE points x decades of USD/W)` |
| `Q1_scores` | hypervolume, IGD+ and no-Au hypervolume per seed, with mean and CI (computed) | 91 | `case`, `method`, `seed`, `hv_final`, `igd_plus`, `hv_no_au`, `calls_to_95pct (241 = not reached)`, `hv_mean`, `hv_ci95_half (t, 4 dof)`, `igd_mean`, `igd_ci95_half (t, 4 dof)` |
| `Q2_front` | pooled Pareto front points per case (computed) | 43 | `case`, `module_pce_pct`, `usd_per_W`, `material_set` |
| `Q2_ends` | PCE-optimal and cost-optimal designs per case, rank correlation over distinct designs (computed) | 13 | `case`, `end`, `material_set`, `x`, `x_layers`, `module_pce_pct`, `cell_pce_pct`, `voc_V`, `ff`, `jsc_mA_cm2`, `usd_per_W`, `usd_per_W_high_prices`, ... (20 in total) |
| `Per_combo` | best PCE and lowest USD/W per material set and case (computed) | 37 | `case`, `material_set`, `n_feasible`, `best_pce`, `usd_per_W_at_best_pce`, `min_usd_per_W`, `pce_at_min_usd` |
| `Call_share` | fraction of calls (0 to 1) per material set and method (computed) | 19 | `case`, `method`, `NiOx/Cu fraction`, `NiOx/Ag fraction`, `NiOx/Au fraction`, `PTAA/Cu fraction`, `PTAA/Ag fraction`, `PTAA/Au fraction` |
| `Q4_PTAA` | break-even PTAA analysis (computed) | 13 | `case`, `metal`, `ptaa_best_pce`, `ptaa_best_usd`, `niox_best_pce`, `niox_best_usd`, `ptaa_advantage_pts`, `slope_usdW_per_usdg`, `break_even_algebraic_usd_g`, `status` |
| `SWF_sensitivity` | bare metal work function re-simulations (measured) | 19 | `scenario`, `material_set`, `x`, `B2_pce`, `B2_usd`, `metal_wf_pce`, `metal_wf_usd`, `status`, `B2_voc`, `metal_wf_voc` |
| `Overlay_physics` | material-choice physics overlay: metals, thickness, interfaces, contact rule (sourced / assumed) | 13 | `item`, `key`, `value`, `provenance` |
| `New_sources` | silver price, silver density, metal work functions with verbatim quotes (sourced) | 6 | `id`, `value`, `unit`, `citation`, `doi`, `verbatim quote`, `source sha256` |
| `Assumptions` | every assumption and proxy specific to the material choice (assumed) | 10 | `assumption`, `value / rule`, `where used`, `status` |
| `PostHoc_contact` | POST-HOC: contact attribution over the 12 optimised NiOx designs | 13 | `arch`, `scenario`, `metal`, `x`, `niox_B2_pce`, `niox_PTAA_contact_pce`, `ptaa_best_B2_pce`, `lead_B2`, `contact_part`, `lead_same_contact`, `status` |
| `PostHoc_prices` | POST-HOC: re-costing at the 2023-2026 metal price extremes | 31 | `price case`, `Ag factor`, `Au factor`, `case`, `sets on front`, `gap_pce`, `gap_cost_pct`, `wording` |
| `PostHoc_interlayer` | POST-HOC: n-i-p interlayer cost bound (SI Table S26) | 4 | `case`, `sets on front (no interlayer)`, `reading (no interlayer)`, `added USD/W (cheapest Cu)`, `added %`, `break-even K USD/m2`, `break-even MoO3 USD/g`, `reading above break-even` |
| `PostHoc_grid` | POST-HOC: simulation grid check, both front ends at 250/500/1000 grid points (SI Note S19, Table S28) | 109 | `level`, `case`, `end`, `NP`, `module_pce_pct`, `stored_module_pce_pct`, `cell_pce_pct`, `usd_per_W`, `material set / note` |
| `PostHoc_mesh_front` | POST-HOC: every pooled-front member re-simulated at 250/500/1000 grid points (SI Note S19, Table S29) | 127 | `case`, `point`, `NP`, `material_set`, `x`, `x_layers`, `status`, `cell_pce_pct`, `module_pce_pct`, `usd_per_W`, `stored_module_pce_pct`, `stored_usd_per_W` |
| `PostHoc_mesh_fronts` | POST-HOC: fronts rebuilt from those re-simulations, ends and gaps (SI Table S29) | 19 | `case`, `NP`, `points simulated`, `front_size`, `sets on front`, `PCE-end set`, `cost-end set`, `PCE-end module_pce_pct`, `cost-end module_pce_pct`, `gap_pce_points`, `gap_cost_pct`, `above the 0.2-point line` |
| `PostHoc_PTAA_front` | POST-HOC: n-i-p front of the PTAA designs alone (SI Note S20, Table S30) | 4 | `scenario`, `feasible calls`, `distinct designs`, `front_size`, `metals on front`, `PCE-end metal`, `PCE-end module_pce_pct`, `PCE-end usd_per_W`, `cost-end metal`, `cost-end module_pce_pct`, `cost-end usd_per_W`, `gap_pce_points`, ... (14 in total) |
| `PostHoc_paired` | POST-HOC: paired per-seed comparison of the final hypervolume, both levels (SI Table S31) | 37 | `level`, `case`, `pair (first minus second)`, `seeds`, `mean difference`, `ci95_half`, `paired interval excludes 0`, `separated by CI non-overlap`, `winner` |
| `PostHoc_JV_optima` | POST-HOC: current-voltage metrics of the PCE-optimal design of every case, both levels (SI Table S32) | 13 | `level`, `case`, `material_set`, `voc_V`, `ff`, `jsc_mA_cm2`, `cell_pce_pct`, `module_pce_pct` |
| `PostHoc_rho` | POST-HOC: efficiency-cost rank correlation over all feasible calls and over distinct designs, both levels | 13 | `level`, `case`, `rho, all feasible calls`, `feasible calls`, `rho, distinct designs`, `distinct designs` |
| `PostHoc_absorber_price` | POST-HOC: published MAPbI3 precursor prices against the library value (SI Note S20) | 5 | `source`, `item`, `USD/g`, `low USD/g`, `high USD/g`, `multiple of library value`, `verbatim quote`, `url`, `sha256` |
| `FigS9_HV_curves` | Figure S9 and main Figure 6b: hypervolume vs calls, mean and 95% band per method and case (computed) | 4,321 | `arch`, `scenario`, `method`, `call`, `hv_mean`, `band_lo`, `band_hi`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `Numbers_material_choice` | every material-choice number printed in the paper with its source (computed) | 447 | `token`, `printed value`, `raw`, `source` |
