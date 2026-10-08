# Source Data

Two Excel workbooks hold the data behind the paper: every simulator call, the data behind every figure and
table, the material and cost libraries with their sources, every assumption, and every number printed in the
paper. They are written from the stored files by `scripts/paperA_sourcedata.py --merged` and
`scripts/paperB_sourcedata.py`, which re-read each workbook and check it against the run files.

Each workbook starts with a `README` sheet. Its status labels: **measured** (read from a simulator call),
**computed** (derived by a script from measured values), **sourced** (a published value, with its quotation and
source), **assumed** (a value chosen by the author, with the reason) and **post-hoc** (analysis added after the
pre-registered analysis). All efficiencies and costs are model predictions.

Units: efficiencies in percent (PCE) or percentage points (differences), thicknesses in nm, cost per watt in
USD/W, area costs in USD/m2; hypervolume units are given in the table captions of the paper. Column names carry
their unit where one applies.

## `SourceData_thickness_only.xlsx`: thickness-only design (fixed materials)

| Sheet | Content | Rows in sheet (with header) | Columns |
|---|---|---|---|
| `Calls_all` | every simulator call of all 90 runs (21,600 rows): inputs, simulator outputs, module factors, objectives | 21,604 | `arch`, `scenario`, `method`, `seed`, `call`, `batch`, `u (unit cube)`, `x1_nm`, `x2_nm`, `x3_nm`, `x4_nm`, `stripe_mm`, ... (30 in total) |
| `Runs_summary` | one row per run: final hypervolume, infeasible calls, calls to 95%, wall time, hashes | 93 | `arch`, `scenario`, `method`, `seed`, `hv_final`, `n_infeasible`, `calls_to_95pct_best (241 = not reached)`, `best_module_pce_pct`, `lowest_usd_per_W`, `wall_seconds`, `ref_pce_pct`, `ref_usd_per_W`, ... (14 in total) |
| `Table1_space` | main Table 1: search spaces | 12 | `stack`, `variable`, `lower`, `upper`, `provenance` |
| `Table5_Q1_HV` | main Table 5: final hypervolume mean and 95% CI, verdicts | 21 | `case`, `method`, `hv_mean`, `hv_ci95_half (t, 4 dof)`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4`, `verdicts (CI non-overlap)` |
| `Table6_speed` | main Table 6: median calls to 95% of the best hypervolume | 21 | `case`, `method`, `median`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `Table2_gap` | main Table 2: two ends of the pooled Pareto front per case | 9 | `case`, `front_size`, `n_feasible_pooled`, `PCE-opt module_pce_pct`, `PCE-opt usd_per_W`, `cost-opt module_pce_pct`, `cost-opt usd_per_W`, `gap_pce_points`, `gap_cost_pct`, `gap_small (<1 pt and <5%)` |
| `Table3_designs` | main Table 3 and both front ends: designs, cell PCE, cost parts, CN/IN rate rows | 15 | `case`, `end`, `design (nm, stripe mm)`, `cell_pce_pct`, `module_pce_pct`, `usd_per_W`, `materials_usd_m2`, `part materials USD/W`, `part capital USD/W`, `part other opex USD/W`, `USD/W MY rate`, `USD/W CN rate`, ... (13 in total) |
| `Fig6_HV_curves` | main Figure 6: mean and 95% band of hypervolume vs calls (and every seed) | 4,323 | `arch`, `scenario`, `method`, `call`, `mean`, `band_lo`, `band_hi`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `Fig2_front_points` | main Figure 2: Pareto front points per case (all feasible points are in Calls_all) | 16 | `arch`, `scenario`, `module_pce_pct`, `usd_per_W`, `materials_usd_m2`, `design`, `cell_pce_pct` |
| `Fig3_cost_parts` | main Figure 3: cost-part shares at the PCE-optimal design | 9 | `arch`, `scenario`, `total usd_per_W`, `materials %`, `capital %`, `other opex %` |
| `FigS1_bestPCE` | SI Figure S1: best module PCE so far vs calls (mean, band, every seed) | 4,323 | `arch`, `scenario`, `method`, `call`, `mean`, `band_lo`, `band_hi`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `FigS2_final_scores` | SI Figure S2 and Table S13: per-seed final scores and alternative verdicts | 117 | `case`, `method`, `metric`, `mean / value`, `ci95_half`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
| `FigS5_scans` | SI Figure S5 and Table S12: post-hoc gap scans | 184 | `scan`, `value`, `arch`, `scenario`, `gap_pce_pt`, `gap_cost_pct`, `small`, `front_size`, `PCE-opt design`, `cost-opt design` |
| `TableS11_sensitivity` | SI Table S11: post-hoc gap under single changed assumptions | 153 | `group`, `change`, `arch`, `scenario`, `front_size`, `PCE-opt module %`, `PCE-opt USD/W`, `cost-opt module %`, `cost-opt USD/W`, `gap_pce_pt`, `gap_cost_pct`, `small`, ... (15 in total) |
| `FigS7_repeats` | SI Figure S7: repeated designs per run | 93 | `arch`, `scenario`, `method`, `seed`, `repeats` |
| `FigS8_P2_sensitivity` | SI Figure S8 and Table S8: earlier global sensitivity ranking | 50 | `output`, `rank`, `parameter`, `Borgonovo delta`, `ci95_half`, `S1` |
| `Verification` | SI Table S9/S10: deterministic checks, re-execution and fresh re-simulation | 20 | `check`, `result` |
| `Verification_fresh` |  | 99 | `run`, `call`, `x`, `stored_sim_status`, `stored_cell_pce_pct`, `stored_voc_V`, `stored_ff`, `stored_jsc_mA_cm2`, `stored_module_pce_pct`, `stored_usd_per_W`, `stored_materials_usd_m2`, `stored_feasible`, ... (22 in total) |
| `Physics_library` | every layer, interface and device parameter passed to SimSS, with provenance | 273 | `kind`, `material / pair`, `parameter`, `value`, `provenance status`, `source file`, `overridable range` |
| `Cost_library` | every cost-library entry: value, unit, verbatim quotation, source, confidence | 94 | `id`, `value`, `unit`, `role`, `item`, `source`, `verbatim quote`, `confidence`, `basis year`, `geography`, `notes` |
| `Cost_sources` | registered source files with DOI, licence and SHA-256 | 15 | `key`, `citation`, `doi`, `licence`, `geography`, `file`, `sha256`, `notes` |
| `Cost_structure` | line inputs, operating-cost parts, materials bill decomposition (USD/m2) | 41 | `group`, `item`, `value`, `tag / note` |
| `Assumptions` | every assumption, proxy and fixed setting of the study, with where it is used | 36 | `area`, `assumption / setting`, `value`, `unit`, `status`, `where in code / library` |
| `Numbers_main_text` | every number printed in the manuscript: token, printed value, raw value, source | 483 | `token`, `printed`, `raw`, `source`, `file` |

## `SourceData_material_choice.xlsx`: material-choice design (the optimiser also chooses the hole-transport layer and the back metal)

| Sheet | Content | Rows in sheet (with header) | Columns |
|---|---|---|---|
| `Calls_all` | every simulator call of the 90 runs (measured) | 21,603 | `arch`, `scenario`, `method`, `seed`, `call`, `batch`, `HTL`, `metal`, `feasible`, `sim_status`, `reason`, `x`, ... (24 in total) |
| `Runs_summary` | one row per run (measured / computed) | 93 | `arch`, `scenario`, `method`, `seed`, `seconds`, `n_infeasible`, `hv_final` |
| `Q1_scores` | hypervolume, IGD+ and no-Au hypervolume per seed, with mean and CI (computed) | 93 | `case`, `method`, `seed`, `hv_final`, `igd_plus`, `hv_no_au`, `calls_to_95pct`, `hv_mean`, `hv_ci95_half`, `igd_mean`, `igd_ci95_half` |
| `Q2_front` | pooled Pareto front points per case (computed) | 45 | `case`, `module_pce_pct`, `usd_per_W`, `material_set` |
| `Q2_ends` | PCE-optimal and cost-optimal designs per case (computed) | 15 | `case`, `end`, `material_set`, `x`, `module_pce_pct`, `cell_pce_pct`, `voc_V`, `ff`, `jsc`, `usd_per_W`, `usd_per_W_high_prices`, `materials_usd_m2`, ... (19 in total) |
| `Per_combo` | best PCE and lowest USD/W per material set and case (computed) | 39 | `case`, `material_set`, `n_feasible`, `best_pce`, `usd_per_W_at_best_pce`, `min_usd_per_W`, `pce_at_min_usd` |
| `Call_share` | share of calls per material set and method (computed) | 21 | `case`, `method`, `NiOx/Cu`, `NiOx/Ag`, `NiOx/Au`, `PTAA/Cu`, `PTAA/Ag`, `PTAA/Au` |
| `Q4_PTAA` | break-even PTAA analysis (computed) | 15 | `case`, `metal`, `ptaa_best_pce`, `ptaa_best_usd`, `niox_best_pce`, `niox_best_usd`, `ptaa_advantage_pts`, `slope_usdW_per_usdg`, `break_even_algebraic_usd_g`, `status` |
| `SWF_sensitivity` | bare metal work function re-simulations (measured) | 21 | `scenario`, `material_set`, `x`, `B2_pce`, `B2_usd`, `metal_wf_pce`, `metal_wf_usd`, `status`, `B2_voc`, `metal_wf_voc` |
| `Overlay_physics` | material-choice physics overlay: metals, thickness, interfaces, contact rule (sourced / assumed) | 15 | `item`, `key`, `value`, `provenance` |
| `New_sources` | silver price, silver density, metal work functions with verbatim quotes (sourced) | 8 | `id`, `value`, `unit`, `citation`, `doi`, `verbatim quote`, `source sha256` |
| `Assumptions` | every assumption and proxy specific to the material choice (assumed) | 12 | `assumption`, `value / rule`, `where used`, `status` |
| `PostHoc_contact` | POST-HOC: contact attribution over the 12 optimised NiOx designs | 15 | `arch`, `scenario`, `metal`, `x`, `niox_B2_pce`, `niox_PTAA_contact_pce`, `ptaa_best_B2_pce`, `lead_B2`, `contact_part`, `lead_same_contact`, `status` |
| `PostHoc_prices` | POST-HOC: re-costing at the 2023-2026 metal price extremes | 33 | `price case`, `Ag factor`, `Au factor`, `case`, `sets on front`, `gap_pce`, `gap_cost_pct`, `wording` |
| `Numbers_material_choice` | every material-choice number printed in the paper with its source (computed) | 386 | `token`, `printed value`, `raw`, `source` |
| `PostHoc_interlayer` | POST-HOC: n-i-p interlayer cost bound (SI Table S26) | 6 | `case`, `sets on front (no interlayer)`, `reading (no interlayer)`, `added USD/W (cheapest Cu)`, `added %`, `break-even K USD/m2`, `break-even MoO3 USD/g`, `reading above break-even` |
| `PostHoc_grid` | POST-HOC: simulation grid check, both front ends at 250/500/1000 grid points (SI Note S19, Table S28) | 111 | `level`, `case`, `end`, `NP`, `module_pce_pct`, `stored_module_pce_pct`, `cell_pce_pct`, `usd_per_W`, `material set / note` |
| `FigS9_HV_curves` | Figure S9 and main Figure 6b: hypervolume vs calls, mean and 95% band per method and case (computed) | 4,323 | `arch`, `scenario`, `method`, `call`, `hv_mean`, `band_lo`, `band_hi`, `seed0`, `seed1`, `seed2`, `seed3`, `seed4` |
