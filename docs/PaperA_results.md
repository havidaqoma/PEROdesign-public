# Paper A results (2026-09-30)

Pre-registration: `docs/PaperA_preregistration.md`, commit `1bdbecc` (before any run).
Data: `phase0/paperA/runs/*.json` (90 files), `phase0/paperA/result.json`, `phase0/paperA/run.log`.
Every number below is in `paper/paperA/numbers.json` with its source. Status labels: **measured** = read from
run files; **rule** = the pre-registered §7 verdict; **post-hoc** = analysis added after the runs.

## Run health (measured)

- 90/90 runs, `EXIT=0`, 21,600 simulator calls, 1 infeasible call (p-i-n worse qNEHVI seed 4). No case is
  flagged unreliable (rule: >12 infeasible calls or >5% in a run).
- Median SimSS time 2.2 s. qNEHVI runs took 1,635-2,053 s; NSGA-II 244-684 s.

## Q1: optimiser comparison (rule: 95% t-CI of final HV, 5 seeds, non-overlap)

| Case | Verdicts | qNEHVI HV over random | Median calls to 95% of best HV (R / N / Q) |
|---|---|---|---|
| p-i-n base | N>R, Q>R, Q>N | +8.0% | >240 / 194 / 26 |
| p-i-n worse | N>R, Q>R, Q>N | +19.4% | >240 / >240 / 47 |
| p-i-n better | N>R, Q>R | +5.0% | >240 / 75 / 26 |
| n-i-p base | N>R, Q>R | +4.7% | 93 / 78 / 27 |
| n-i-p worse | N>R, Q>R | +8.2% | >240 / 112 / 34 |
| n-i-p better | N>R, Q>R, Q>N | +2.7% | 46 / 48 / 25 |

qNEHVI has the highest mean HV in all 6 cases. It separates from NSGA-II in 3 of 6.

**Post-hoc (agy review):** the final HV of a run tracks the best module PCE it found (Spearman 0.99-1.00 in every
case, 15 runs each). The same far reference point drives the qNEHVI acquisition. So Q1 in practice compares how fast
each method maximises PCE, not how it traces a trade-off.

## Q2: efficiency-cost gap (rule: "small" if < 1 PCE point and < 5% cost)

- Pooled Pareto fronts have 1-5 points per case, from ~3,200 feasible designs each.
- Largest gap: n-i-p better, 0.010 points and 0.188%. **Small in all 6 cases.**
- p-i-n base optimum: 21.52% module PCE (model), 0.339 USD/W. The P1 reference design gives 18.19%, 0.427 USD/W.
- n-i-p costs about 32× more per watt (Au + PTAA). This is not counted as part of the gap (pre-registered).
- CN/IN capital rates: 0.338 / 0.346 USD/W against 0.339 for Malaysia (p-i-n base optimum).

**Post-hoc explanation (labelled so in the paper):** capital and opex per m² do not depend on the design.
Materials cost per m² varies by at most 39% (p-i-n) / 7.6% (n-i-p). Total cost per m² varies by at most 29% / 7.5% (any scenario),
while module PCE varies by a factor of 1.77 / 1.59. Spearman ρ(PCE, USD/W) is -0.96 to -0.999. The thin transport
layers that save material also raise PCE, so there is nothing to trade.

## Q3: robustness over scenarios (rule: all pairwise verdicts identical; designs move < 20% of range)

- **Strict Q1 robustness: NOT met** for either stack (Q>N holds in some scenarios only).
- "Some method beats random in every scenario": met for both stacks.
- **Design robustness: NOT met.** The optimal absorber moves 44% (p-i-n) and 67% (n-i-p) of its range:
  p-i-n 212 / 383 / 563 nm (worse / base / better); n-i-p 232 / 398 / 764 nm.
- The gap itself is small in every scenario.

## What this means

1. Inside one stack, with thickness and stripe width as the only design variables, efficiency and cost do not
   compete in this model. A PCE-only reward would find the same designs.
2. The trade-off lives in stack and material choice (Au/PTAA vs Cu/SnO2). A future design space should include
   material choices before a cost objective becomes useful.
3. The best absorber thickness depends strongly on trap density and mobility. Measure the film before choosing it.
4. All efficiencies are model predictions (G1 NO-GO, no device validation).

## Not done / open

- The optimisers were compared at one budget (240 calls) and 5 seeds; Q>N ties may separate with more seeds.
- The HV reference point makes HV reward PCE almost entirely (pre-registered caveat); the paper says so.
