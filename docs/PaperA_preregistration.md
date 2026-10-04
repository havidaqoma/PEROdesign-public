# Paper A: optimiser comparison and efficiency–cost gap (pre-registration)

Written 2026-09-30, **before any optimisation run**. The plan and Havid's decisions (A1–A4) are in `docs/PaperA_plan.md`.
Code: `perodesign/optim/objective.py`, `perodesign/optim/search.py`, `scripts/paperA_run.py`. The objective was
checked on 16 hand-picked designs: the reference design and two box corners per stack, 3 scenarios for the
reference (listed in §9). No optimiser had run at that point.

## 1. Question
- **Q1 (method):** on this environment, does multi-objective BO (qNEHVI) find a better efficiency–cost front than
  NSGA-II, for the same number of simulator calls? Is either better than random search?
- **Q2 (result):** inside one device stack, how much module efficiency does the cheapest good design give up, and
  how much cost does the most efficient design add? This is the **efficiency–cost gap**.
- **Q3 (robustness):** do the answers to Q1 and Q2 hold when the two top P2 drivers are made worse or better?

## 2. Environment (fixed)
- **Physics:** SimSS 5.36 through `perodesign.physics.simss.SimSS`. Library `materials_v2.yaml`, ideal contacts
  (library default; the contact P1 spread is an upper bound and is labelled so). Wrapper defaults as in P1/P2.
- **Module:** `module_from_cell`, dead width 0.2 mm, 10 ohm/sq TCO, 3% edges (assumed, as in P1/P2). A design whose
  TCO loss is above the model limit (0.15) is infeasible.
- **Cost:** `region_line_MY_bottom_up()` (Malaysia, lending rate, low electricity, with maintenance and TNB
  demand), base prices. PTAA density 1.1 g/cm3 is an assumption, as in `compare_devices.py`.
- **Objectives:** maximise module PCE (%) and minimise USD/W.

## 3. Search spaces
Bounds are the library `thickness_nm` min/max, and 2–10 mm for the stripe width.

| Stack | Variables (nm, then mm) | Bounds |
|---|---|---|
| p-i-n NiOx / MAPbI3 / C60 / SnO2 / Cu | NiOx, MAPbI3, C60, SnO2, stripe | 5–40, 200–1000, 10–100, 5–30, 2–10 |
| n-i-p C60 / MAPbI3 / PTAA / Au | C60, MAPbI3, PTAA, stripe | 10–100, 200–1000, 10–70, 2–10 |

Thicknesses are rounded to 0.1 nm and the stripe width to 0.01 mm before simulation.

## 4. Scenarios (from P2)
The two top P2 drivers for both outputs, applied as design overrides on MAPbI3:

| Scenario | N_t_bulk (m^-3) | mu_n (m^2/Vs) |
|---|---|---|
| base | 1e20 (library) | 1e-4 (library) |
| worse | 1e20 × √10 | 1e-4 / √10 |
| better | 1e20 / √10 | 1e-4 × √10 |

√10 is half of the P2 range on a log scale. It is a convention, not a measured spread.

## 5. Methods and budget
- **Budget:** 240 simulator calls per run. A cache hit, a failed sim and an infeasible design each count as one call.
- **Seeds:** 5 per method: 0, 1, 2, 3, 4. With 2 stacks and 3 scenarios, that is 3 × 5 × 2 × 3 = 90 runs, or 21,600
  calls.
- **Random (floor):** the first 240 points of a scrambled Sobol sequence (scipy, seed = run seed).
- **NSGA-II (pymoo 0.6.2):** population 24, 10 generations. Operators are the pymoo defaults (SBX crossover,
  polynomial mutation). The first population is the same as the first 24 random points. Infeasible designs are
  constraint-violating.
- **qNEHVI (BoTorch 0.18.1, `qLogNoisyExpectedHypervolumeImprovement`):**
  - The first 24 calls are the same 24 random points; after that, 18 batches of q = 12.
  - Model: one `SingleTaskGP` per objective, on unit-cube inputs and standardised outputs.
  - Acquisition: optimised with 4 restarts and 256 raw samples, 64 QMC samples; sequential greedy.
    - These are smaller than the BoTorch tutorial values (10 / 512 / 128). Measured on a synthetic test function,
      the smaller settings take 15–55 s per batch and 549 s per 240-call run. The C++ fused kernel is not
      available (no g++ in WSL).
  - Infeasible points are given the worst feasible value seen so far on each objective (lowest PCE, highest
    USD/W). The reference point is used only while nothing is feasible. This keeps a 38 USD/W outlier out of the
    n-i-p cost model (agy review, §9).
  - The reference point is §6.
  - torch uses float64 on the CPU with 1 thread.
- The designs a run evaluates depend only on the seed, not on scheduling.
- **Cache:** SimSS results are cached by design hash in a cache outside the repo. A cache hit still counts as a
  call, so it changes wall time only.

## 6. Reference point and hypervolume
- **Reference point per stack:** module PCE 5% and the USD/W of the most material-hungry design (every thickness at
  its maximum) at 5% PCE.
  - p-i-n: (5%, 1.854 USD/W).
  - n-i-p: (5%, 49.58 USD/W).
- **Hypervolume (HV):** in (PCE, −USD/W) space, from the feasible points of a run only. The score is HV after 240
  calls. The curve of HV against calls is also reported.

## 7. Analysis rules (decided now)
- **Q1:**
  - For each (stack, scenario), report the mean and 95% CI (t, 4 degrees of freedom) of the final HV for each method.
  - "A beats B" only when the two CIs do not overlap. Otherwise the result is "no difference found".
  - Random search is the floor. If a method does not beat random, say so.
  - Secondary: calls needed to reach 95% of the best HV found by any run for that (stack, scenario). Report the
    **median over the 5 seeds**. A run that never reaches 95% within 240 calls counts as ">240". If 3 or more
    seeds never reach it, the median is reported as ">240".
  - **HV scale:** the HV is dominated by the PCE axis, because the reference cost is far above the front. This is
    worst for n-i-p (49.6 vs ~11 USD/W). So HV mainly rewards finding high PCE. This is a property of the
    registered reference point, and the paper says so. The front plots show the cost trade-off directly.
- **Q2:** pool every feasible point from all runs of one (stack, scenario), then take the Pareto front.
  - Exact (PCE, USD/W) ties keep the design with the lowest design hash.
  - *PCE-optimal design* = the front point with the highest module PCE. *Cost-optimal design* = the front point with
    the lowest USD/W.
  - **Gap:** ΔPCE = PCE(PCE-optimal) − PCE(cost-optimal), in absolute points. ΔCost = USD/W(PCE-optimal) /
    USD/W(cost-optimal) − 1, in %.
  - Also report the cost parts (materials, capital, other opex), the thicknesses of both designs, and the front
    size.
  - A gap is "small" if ΔPCE < 1 point **and** ΔCost < 5%. This line is set now so a small gap can be reported
    plainly.
  - If the front is a single point, the gap is 0 / 0% ("small"). The paper then says that inside this stack the
    most efficient design is also the cheapest per watt.
  - The **CN / IN row** reports only the re-costed USD/W of the two Malaysian designs, with the capital rate
    replaced by the CN and IN WDI lending rates. It does not build new fronts or new gaps. Every gap claim uses
    the Malaysia line.
- **Q3:** repeat Q1 and Q2 for each scenario.
  - The optimiser comparison is **robust** only if both hold:
    1. at least one of NSGA-II / qNEHVI beats random in all 3 scenarios, and
    2. all 6 pairwise Q1 verdicts are the same in the base, worse and better scenarios.

    An all-tie result is reported as "no difference found in any scenario", not as "robust".
  - The optimal **designs are robust** only if, for both the PCE-optimal and the cost-optimal design separately,
    the peak-to-peak spread of absorber thickness over the 3 scenarios is < 20% of the absorber range (< 160 nm).
- **Cross-stack:** n-i-p and p-i-n are reported side by side. The large cost difference between them comes mostly
  from gold and PTAA, which is known (MASTER §16). It is **not** counted as the gap.
- **Failures:**
  - The infeasible count and reasons are reported for every run.
  - If any single one of the 15 runs of a (stack, scenario) has more than 12 infeasible calls (> 5% of 240), that
    (stack, scenario) is flagged "unreliable" in every table and in the text. The analysis is **not** changed.
  - A run that crashes is re-run with the same seed. If it crashes again, it is reported as missing and
    `analyse` refuses to produce a result.
- **Claims:**
  - These are model predictions: G1 was a NO-GO (MASTER §25), and the simulator is not validated for p-i-n NiOx.
  - "Optimal" means optimal inside this model and these bounds.

## 8. Things that are not allowed after this commit
- Changing the budget, seeds, bounds, reference point, rules or scenarios after any run.
- Adding runs because a result looks weak.
- If code has to change, the change goes into a dated §10 Amendment, committed before any affected result is
  looked at. It must also say what had already been seen.

## 9. Disclosure: checks done before this commit
- **Objective check:** 16 designs.
  - p-i-n reference (15/600/30/10 nm, 6 mm): module 18.19%, 0.427 USD/W (base). This equals P1
    `p1_my_bottom_up.json` (0.427).
  - Also computed for the p-i-n reference: worse 8.81% / 0.882, better 21.27% / 0.365.
  - n-i-p reference (10/500/10 nm, 6 mm): base 20.63% / 11.17 USD/W.
  - All 16 were complete. These points are in no run.
- **Smoke test** of the search code: a synthetic 5-D test function only (no SimSS, no real objective). It was
  used to check the budget, seeds and timing. Its numbers say nothing about Paper A.
- **Independent review (agy / gemini-3.8-flash-high, 2026-09-30, read-only):** the file hashes were the same
  before and after. Adopted before this commit:
  1. A module PCE outside the cost engine's (0, 40)% domain is now infeasible instead of crashing the run.
  2. Infeasible points get the worst-feasible fill in the BO model instead of the reference point.
  3. The §7 rewrites: censored median, single-run unreliable rule, CN/IN row scope, strict Q3 robustness.
  4. Deterministic tie-breaking and the SimSS cache.

  Not adopted:
  - Installing ninja for the fused BoTorch kernel. It needs g++, which is not in WSL, and the measured speed
    without it is acceptable.
  - agy argued the cost-optimal end cannot be a thin low-PCE design because USD/W carries 1/PCE, so the front may
    be very narrow. That is reasoning, not a measurement, so the registered gap definition is kept. The
    single-point rule in §7 covers the narrow case.

## 10. Amendments
(none yet)
