# Paper B: the optimiser also chooses materials (pre-registration)

Written 2026-10-01, **before any optimisation run**. Plan and decisions B1–B5: `docs/PaperB_plan.md`.
Code: `perodesign/optim/objective_b.py`, `perodesign/optim/search_b.py`, `perodesign/library/paperB_overlay.yaml`,
`scripts/paperB_run.py`. Paper A's code and results are unchanged; gate G0 (§9) shows that `objective_b` in
production mode reproduces Paper A exactly.

## 1. Questions
- **Q1 (method):** on a mixed categorical + continuous design space, does mixed-variable BO beat mixed-variable
  NSGA-II for the same number of simulator calls? Is either better than random search? Scored two ways (§7): the
  Paper A hypervolume (Q1a), and IGD+ to the pooled front (Q1b), because the review showed HV will again mostly
  measure the best PCE found.
- **Q2 (result):** once the optimiser can choose the HTL and the back-electrode metal, how large is the
  **efficiency–cost gap** (same definition as Paper A), and which material combinations are on the front?
- **Q3 (robustness):** do Q1 and the front materials hold in the worse / better scenarios?
- **Q4 (price robustness):** PTAA's price is a lab-catalogue value. At what PTAA price would the best PTAA design
  cost the same per watt as the best NiOx design (for Cu and for Ag)?

## 2. Environment (fixed)
- **Physics:** SimSS 5.36 via `perodesign.physics.simss.SimSS`, library `materials_v2.yaml` + `paperB_overlay.yaml`
  (in memory; the production file is unchanged), ideal-contact scenario, Paper A wrapper defaults.
  - **Metal optics:** McPeak 2015 (refractiveindex.info, CC0) for Cu, Ag and Au, at the production metal thickness
    of each architecture (n-i-p 101 nm, p-i-n 150 nm), the same for every metal.
  - **Contacts, rule B2** (as registered in G1 step 2 amendment B2): each electrode's work function equals the
    majority band edge of the layer it touches. n-i-p: W_L = E_c(C60) = 4.0 eV, W_R = E_v(HTL) (NiOx 5.7, PTAA 5.4).
    p-i-n: W_L = E_v(HTL), W_R = E_c(SnO2) = 4.0 eV. The metal's own work function does not enter the main runs.
    **Consequence (disclosed):** B2 gives a deeper-valence-band HTL a larger built-in voltage (n-i-p NiOx 1.7 V vs
    PTAA 1.4 V). Diagnostic D2 (§9) measures how much of the NiOx-vs-PTAA difference this explains.
  - **New interfaces** PTAA|MAPbI3 (p-i-n) and MAPbI3|NiOx (n-i-p): SimSS default hole-side values, copied from the
    production MAPbI3|PTAA entry (label `simss_default_transferred`).
- **Module:** as Paper A (dead width 0.2 mm, 10 ohm/sq, 3% edges; assumed).
- **Cost:** as Paper A (`region_line_MY_bottom_up`, base prices, PTAA density 1.1 g/cm3 assumed). The back electrode is
  costed from the metal and thickness SimSS simulated. New sourced values (provenance gate passes): silver
  65.4 USD/toz (World Bank Pink Sheet, Aug 2026) and silver density 10.49 g/cm3 (Thomas et al. 2018, CC-BY-4.0).
  Utilisation for all metals = Liu's evaporated Cu (0.25), labelled a proxy (as for Au in Paper A).
- **Objectives:** maximise module PCE (%); minimise USD/W. The optimisers and the hypervolume use **log10(USD/W)**;
  the gap and every reported cost use USD/W.

## 3. Search space (per stack)

| Stack | Categorical | Continuous (unit cube → physical) |
|---|---|---|
| p-i-n HTL / MAPbI3 / C60 / SnO2 (+ ITO + metal) | HTL ∈ {NiOx, PTAA}; metal ∈ {Cu, Ag, Au} | HTL, MAPbI3 200–1000, C60 10–100, SnO2 5–30 nm; stripe 2–10 mm |
| n-i-p C60 / MAPbI3 / HTL (+ metal) | same | C60 10–100, MAPbI3 200–1000, HTL nm; stripe 2–10 mm |

The HTL thickness is one unit coordinate mapped onto the chosen HTL's library bounds (NiOx 5–40, PTAA 10–70 nm).
Rounding as Paper A (0.1 nm, 0.01 mm). 6 material combinations per stack; Paper A's stacks are 1 of the 6 (NiOx/Cu
for p-i-n, PTAA/Au for n-i-p).

## 4. Scenarios
As Paper A (MAPbI3 N_t_bulk and mu_n moved by ×/÷ √10): base, worse, better.

## 5. Methods and budget
- **Budget 240 calls per run**, 5 seeds (0–4), 3 methods × 2 stacks × 3 scenarios = **90 runs, 21,600 calls**. A cache
  hit, a failed sim and an infeasible design each count as one call.
- **Shared start:** every method's first 24 calls are the same: Sobol points (scipy, scrambled, seed = run seed) in
  5 + 2 (p-i-n) or 4 + 2 (n-i-p) dimensions; a categorical coordinate u picks category ⌊u·K⌋ (u = 1 → last).
- **Random (floor):** the first 240 points of that Sobol sequence.
- **Mixed NSGA-II (pymoo 0.6.2 `MixedVariableGA` + `RankAndCrowding` survival):** Real variables for the unit
  coordinates, Choice variables for the categories, population 24, pymoo default mixed operators; the first
  population is the shared start. Infeasible = constraint-violating.
- **Mixed BO (BoTorch 0.18.1):** `qLogNoisyExpectedHypervolumeImprovement` on a `ModelListGP` of two
  `MixedSingleTaskGP` (categorical kernel on the category indices, default continuous kernel), standardised outputs;
  acquisition optimised by exact enumeration over the 6 material combinations (`optimize_acqf_mixed`, 4 restarts and
  256 raw samples per combination; **Amendment A1**, replacing `optimize_acqf_mixed_alternating` with 8 restarts),
  64 QMC samples,
  q = 12 after the 24 start points (18 batches). Infeasible points get the worst feasible value seen so far on each
  objective (Paper A rule). float64, 1 torch thread.
- Designs a run evaluates depend only on the seed. SimSS cache outside the repo, keyed on design + library hash
  (each material combination has its own library hash).

## 6. Reference point and hypervolume
- **Reference point per stack:** (module PCE 5%, log10 USD/W of the most expensive corner: every thickness at its
  maximum, for the combination with the highest cost, at 5% PCE). Computed before any run:
  - p-i-n: (5%, log10 71.2 = 1.8525) — PTAA/Au.
  - n-i-p: (5%, log10 49.6 = 1.6953) — PTAA/Au.
- **HV** in (PCE, −log10 USD/W) from a run's feasible points; the score is HV after 240 calls.
- **Known limitation (stated in the paper):** the reference point is far from the Cu/Ag front, and the front is
  narrow in PCE. In the pilot the whole Cu/Ag trade-off slice is about 0.25% of the HV (agy review). So HV (Q1a)
  mostly rewards the highest PCE found, as in Paper A. This is why Q1b exists.
- **Diagnostic HV without Au:** the same HV from a run's Cu and Ag points only, with the reference cost at the worst
  Cu/Ag corner, both PTAA/Ag: p-i-n (5%, log10 6.045 = 0.7814), n-i-p (5%, log10 5.701 = 0.7559). Reported, no
  verdict.

## 7. Analysis rules (decided now)
- **Q1:** as Paper A §7: mean and 95% t-CI (4 dof) of final HV per method; "A beats B" only if the CIs do not overlap;
  calls to 95% of the best HV of any run, median over 5 seeds, censored at ">240" (3 or more seeds never reach it).
  Also reported: the share of each method's calls spent on each material combination.
- **Q1b (co-primary): IGD+** (Ishibuchi et al. 2015) of each run's feasible points to the pooled front of its
  (stack, scenario), both in (−PCE, log10 USD/W) normalised by the pooled feasible range of that (stack, scenario).
  Lower is better; 0 means the run found points on or beyond every front point. Same 95% t-CI non-overlap rule
  ("A beats B" only if A's upper CI bound is below B's lower bound). The pooled front includes the run itself, so
  IGD+ measures how much of the best known front each run recovers. Q3 robustness is also reported for Q1b.
- **Q2:** pool all feasible points of one (stack, scenario) from all 15 runs; Pareto front on (PCE, USD/W); exact ties
  keep the lowest (design hash, library hash).
  - PCE-optimal / cost-optimal design, ΔPCE and ΔCost as Paper A; **"small" if ΔPCE < 1 point and ΔCost < 5%**.
  - Report: front size, the material combination of every front point, both optimal designs with thicknesses and
    J-V metrics, cost parts, CN/IN capital-rate row (as Paper A), and per combination the best PCE and the lowest
    USD/W reached.
  - **Wording (complete taxonomy; exactly one applies to each (stack, scenario)):**
    1. front has 1 material combination: "one material set dominates inside this model";
    2. 2 or more combinations and the gap is small: "several material sets perform near-identically";
    3. 2 or more combinations, gap not small, but ΔPCE < 0.2 points: "cost differs between materials while
       efficiency is practically equal; the cheaper set dominates for practical purposes";
    4. 2 or more combinations, gap not small and ΔPCE ≥ 0.2 points: "a material trade-off exists".
    The 0.2-point line is a practical-resolution convention set now (agy review). It is not the model's numerical
    noise, which is much smaller (diagnostic D1, §9: 0.003 points).
  - Spearman ρ(PCE, USD/W) over the pooled points is reported (Paper A comparison, 0.96–0.999 in absolute value).
- **Q3:** Q1 robust as Paper A (some method beats random in all 3 scenarios AND all 6 pairwise verdicts identical).
  **Materials robust** if the PCE-optimal combination is the same in all 3 scenarios and so is the cost-optimal one.
  The absorber-thickness rule of Paper A is not repeated (reported descriptively only).
- **Q4:** for each stack, scenario and metal m ∈ {Cu, Ag}: D_P = pooled PTAA/m design with the highest module PCE,
  D_N = pooled NiOx/m design with the highest module PCE (ties: lowest design hash). The break-even PTAA price p* is
  the price (USD/g) at which USD/W(D_P) = USD/W(D_N), all else fixed (USD/W is linear in the PTAA price; the slope is
  checked against the engine's high-price case in the tests). Also the price at which D_P reaches the pooled
  cost-optimal USD/W. Status labels, in the result file: "PTAA not competitive at any price in this model" if D_P
  has no PCE advantage over D_N or p* ≤ 0 (p* is then null, with the algebraic value kept alongside); "break-even
  below current price" if 0 < p* < 1145 USD/g; "PTAA already competitive at current price" otherwise. Au is excluded
  (the metal cost dominates).
- **Sensitivity S-WF (n-i-p only, reported, never replaces the main result):** after `analyse`, for each scenario and
  combination the pooled best-PCE design is re-simulated with the anode at the bare metal work function (Au 5.1,
  Ag 4.7, Cu 4.6 eV; one SCAPS input table, Nanomaterials 2021, 10.3390/nano11051218; simulation inputs, not
  measurements). Report the new PCE, USD/W and which combinations are on the re-built front.
- **Failures:** as Paper A: infeasible counts and reasons per run; a (stack, scenario) with any single run above 12
  infeasible calls is flagged "unreliable" everywhere, analysis unchanged. A crashed run is re-run once with the same
  seed; if it crashes again it is missing and `analyse` refuses to run.
- **Claims:** model predictions (G1 NO-GO, MASTER §25); "optimal" = inside this model, these bounds and these 6
  combinations; contacts barrier-free by construction (B2), so contact chemistry (e.g. Ag halide corrosion, Au
  diffusion, NiOx/perovskite surface reactions) is outside the model and is said so.

## 8. Not allowed after this commit
As Paper A §8: no change of budget, seeds, bounds, reference point, rules, scenarios, materials or contact rule after
any run; no added runs because a result looks weak; any code change goes into a dated §10 amendment committed before
the affected result is looked at, saying what had been seen.

## 9. Disclosure: work done before this commit
- **Gate G0, baseline reproduction (PASS, `phase0/paperB/gate0.json`, `scripts/paperB_gate0.py`):** `objective_b` in
  production mode (production contacts and optics, production combination) gives module PCE and USD/W identical to
  Paper A's objective (difference 0, same design hash, same library hash) on the two Paper A reference designs and on
  the 6 Paper A PCE-optimal designs, and equal to the values stored by the Paper A runs.
- **One change at a time (reference designs, base scenario; cell PCE %, USD/W):**
  - p-i-n NiOx/Cu: production 19.84 / 0.4274 → McPeak optics 19.84 / 0.4274 (Cu already McPeak) → B2 contacts
    20.15 / 0.4208.
  - n-i-p PTAA/Au: production 22.51 / 11.165 → McPeak Au optics 22.55 / 11.146 → B2 contacts 22.92 / 10.966.
- **Pilot (`phase0/paperB/pilot.json`, `scripts/paperB_pilot.py`), 156 SimSS runs, all complete:** per stack and
  combination the reference design (3 scenarios), the two box corners and 8 Sobol points (seed 1000, not a run seed).
  What was seen (base scenario):
  - PTAA vs NiOx at the reference design: p-i-n PTAA gives +0.8–0.9 module-PCE points (19.34 vs 18.48% with Cu),
    n-i-p NiOx gives +0.8 (21.83 vs 21.01%). Ag vs Cu: +0.05 points, from optics only (B2 contacts).
  - Cost: Au designs 10–30 USD/W, Cu/Ag 0.30–2.5 USD/W; with Cu, PTAA adds 0.14–0.18 USD/W at the reference design.
  - Pilot front (11 base points per combination): 2 points in each stack, NiOx/Ag (highest PCE) and NiOx/Cu
    (cheapest). Pooled Spearman ρ(PCE, USD/W) = −0.37 (p-i-n) and −0.37 (n-i-p), against −0.96 to −0.999 in Paper A.
  - Median SimSS time 5.0 s per call at 12 workers.
  These are pilot numbers on 66 points per stack. They are not results and are not reused by the analysis.
- **Mixed BO smoke test** on a synthetic function (no SimSS): 36 calls in 91 s; category indices always valid.
- **Tests:** `tests/test_paperB.py` (34 tests): production-mode identity, overlay isolation, B2 contacts, every
  combination valid and costed with its own metal at both box corners, silver cost recomputed from the sourced
  values, work functions read from their source, method budgets/seeding/shared start, the §7 rules on synthetic
  runs, the Q4 slope against the engine, the Q4 status labels, the wording taxonomy and IGD+. Full suite green before this commit.
- **Mixed BO acquisition restarts** raised from 4 to 8 after the review. Smoke test with 8: 138 s for 36 synthetic
  calls (full-suite run, 12 other tests in parallel on the machine).
- **Diagnostics after the review (`phase0/paperB/diag.json`, `scripts/paperB_diag.py`), 84 SimSS runs:**
  - **D1, numerical noise:** the reference design (NiOx/Cu and NiOx/Ag) with the absorber moved in 0.1 nm steps
    (20 sims each). Module PCE residual from a straight line: SD 0.0024–0.0028 points, max 0.006. The Ag − Cu
    difference at the same thicknesses: +0.048 ± 0.004 (p-i-n) and +0.040 ± 0.005 points (n-i-p), all 20 pairs
    positive in both stacks. So the Ag optics gain is about 15× the noise and real inside the model, but below the
    0.2-point practical line.
  - **D2, contact attribution (n-i-p reference, Cu):** NiOx at B2 (anode 5.7 eV) 21.83% module; NiOx with the anode
    forced to PTAA's 5.4 eV 21.59%; PTAA at B2 (5.4 eV) 21.01%; PTAA with the anode at 5.7 eV fails to simulate (not
    usable). So with the same 5.4 eV anode NiOx still leads PTAA by 0.58 points; the B2 contact adds 0.24 of the
    0.82-point difference.
- **Independent review (agy / gemini-3.8-flash-high, 2026-10-01, read-only; file hashes identical before and after,
  checked with `sha256sum -c`).** Verdict "major revision before freezing". Each finding was checked:
  1. *Critical, adopted:* the trade-off wording could fire on the ~0.05-point Ag optics gain. Fix: the 4-way wording
     taxonomy with the 0.2-point practical line. D1 measured the noise instead of assuming it (agy estimated about
     0.05; measured 0.003).
  2. *Critical, adopted:* HV will again track best PCE (pilot: the Cu/Ag slice is about 0.25% of HV). Fix: disclosed
     in §6; IGD+ added as co-primary Q1b; no-Au diagnostic HV added. The main HV and its reference point are kept, so
     Paper A and Paper B stay comparable.
  3. *Major, adopted:* Q4 printed a negative price where the pre-registration promised a label. Fix: status labels
     (tested).
  4. *Major, adopted:* the wording taxonomy had a hole (2 or more combinations with a small gap). Fixed above.
  5. *Major, adopted as disclosure plus measurement:* B2 gives NiOx a higher built-in voltage. D2 shows NiOx keeps
     0.58 of its 0.82-point lead with the same anode, so the lead is mostly not the contact rule. agy's statement
     that it is "largely a contact artefact" is therefore not supported; the disclosure stays.
  6. *Minor, adopted:* 8 acquisition restarts instead of 4.
  agy also reported, from its own runs: all 6 combinations appear in every seed's first 24 points, random search
  spends 15.0–18.8% of calls per combination, and mixed NSGA-II produced 1 duplicate in 1,200 calls.

## 10. Amendments

### Amendment A1 (2026-10-01 04:55, before any run finished): mixed-BO acquisition optimiser
**What was seen before this amendment:** the batch was launched at `2b32a78` at 02:30 and stopped by the agent at
04:40. No run file had been written (0 of 90; a run file is written only when all 240 calls of that run are done), so
no hypervolume, front, gap or method comparison existed. The log was read only for errors and warnings. The SimSS
cache held 1,567 new simulations; their values were not read.

**Problem:** throughput. After 2 h 10 min the 12 mixed-BO runs had reached about 120 of 240 calls each, which projects
to about 11 h for the batch. py-spy stacks of 4 workers showed all the time in `optimize_acqf_mixed_alternating` and
the GP posterior calls inside it (about 10 min per q = 12 batch).

**Change (mixed BO only; random, NSGA-II, budgets, model, acquisition function, seeds and analysis unchanged):** the
acquisition is maximised by **exact enumeration over the 6 material combinations**: BoTorch `optimize_acqf_mixed`
with one fixed-features dict per combination, sequential greedy over q = 12, and Paper A's continuous settings for each
combination (4 restarts, 256 raw samples, batch_limit 5, maxiter 200). §5's "optimize_acqf_mixed_alternating
(8 restarts, raw 256)" is replaced by this.
- Measured on synthetic data (3 jobs in parallel, 1 thread each): 250 s per batch at 130 training points, 426 s at
  220 (alternating: about 600 s at about 130). Projected batch time about 6–7 h.
- Enumeration is exact over the categories, while the alternating search is a local search that can miss a
  combination. So the change does not weaken the method, and it is simpler to describe: "Paper A's continuous
  optimiser, run once per material combination".
- Tried and not adopted: 2 restarts / 128 raw samples (310 s at 220 points, only 27% faster).
- The unit test `test_mixbo_runs_on_the_fake_objective` covers the new path. The batch restarts from scratch at the
  A1 commit; the SimSS cache is reused (same design and library hashes give the same simulation, and a cache hit still
  counts as a call).

### Amendment A2 (2026-10-01 05:55, before any run finished): scheduling only (memory)
**What was seen before this amendment:** the A1 batch (`776401b`, launched 04:57) lost its process pool at 05:05 when
the Linux OOM killer stopped one mixed-BO worker (`dmesg`: 5.7 GB resident). All 90 futures failed with
`BrokenProcessPool`; 0 run files were written, so again no result existed. Only the log and `dmesg` were read.

**Cause (measured, synthetic data):** one qLogNEHVI acquisition step raises a worker from 0.66 GB to 3.5 GB
(`mem_probe`: after model fit 0.64 GB, after the first acquisition forward 3.50 GB), and up to 5.7 GB was seen in
the batch. Twelve BO workers at once do not fit in the 47 GB WSL memory. Lowering raw samples, `batch_limit` or
`init_batch_limit` did not bring the peak below 3.5 GB.

**Change (no change to any method, setting, seed or rule):** at most 6 mixed-BO runs execute at the same time
(`PAPERB_BO_MAX`, default 6). The other 6 workers run the random and NSGA-II jobs. A broken pool is rebuilt and the
unfinished runs are resubmitted once, which is the §7 rule "a crashed run is re-run once with the same seed". The
designs a run evaluates depend only on its seed, so the order in which runs execute cannot change any result.
- **Addendum (06:35, 6 of 90 run files written, all NSGA-II; none opened):** mixed-BO workers grow to about 7 GB each
  as training data accumulates (6 × 7 GB ≈ 41 GB of 47 GB). A memory guard (`scripts/paperB_memguard.sh`) pauses the
  largest BO worker with SIGSTOP when free memory drops below 6 GB and resumes it above 14 GB. It pauses only a worker
  that has no running SimSS child, so no simulation is ever paused and the SimSS timeout cannot fire because of it.
  A paused worker resumes in the same state, so this changes wall time only. Every pause and resume is logged in
  `~/perodesign_p1/memguard.log`.

### Amendment A3 (2026-10-01 07:05, before any mixed-BO run finished): each BO step in a child process
**What was seen before this amendment:** the A2 batch (`0adafae` + guard `7f6056b`) wrote 10 run files, all
mixed NSGA-II (p-i-n). None was opened; only file names and the log lines "done ... infeasible k" were read. No
mixed-BO or random run had finished.

**Problem:** memory still grew inside each BO worker: 5 to 8.4 GB after about 40 minutes (`smaps`: 4.8 GB `[heap]`
plus 3.3 GB anonymous maps). The guard then paused 5 of 6 BO workers, which kept their memory, so the batch stalled.
A synthetic probe in one process grew by about 1.4 GB per step (3.9 GB at n = 36, 8.1 GB at n = 72). `malloc_trim`
plus a lower mmap threshold only slowed it (5.9 GB at n = 72). The batch was stopped at 06:45.

**Change (mixed BO only; computation, settings and seeds unchanged):** each BO step (fit both GPs and maximise the
acquisition) runs in a fresh child Python process (`perodesign/optim/bo_step.py`), which returns all of its memory to
the OS when it exits. Input is the same X, Y, reference point and seed, passed as JSON (Python floats round-trip
exactly). Test `test_bo_step_isolated_equals_in_process`: the child and in-process candidates are identical.
Measured at n = 130 (synthetic): the child peaks at 3.5 GB and the step takes 286 s. So 6 BO runs at once need at most
about 21 GB. The memory guard is no longer used.

**Reuse of finished runs:** the 10 NSGA-II run files are kept. NSGA-II code, the objective, the libraries and the
seeds are unchanged since the pre-registration commit (`git diff 2b32a78 -- perodesign/optim/objective_b.py
perodesign/library` is empty; `search_b.run_nsga2` is unchanged), so re-running them would give the same calls.
- **Addendum (10:20, scheduling only; 61 of 90 run files written: all 30 NSGA-II, all 30 random, 1 mixed BO; none
  opened):** with child-process BO steps, BO workers use about 0.7 GB, and total memory reads 3–8 GB. The A2 cap of
  6 concurrent BO runs now leaves 6 workers idle, which projects the last run to about 23:00. A second runner process
  (same code, separate clone at this commit, run files written to the same directory) takes a disjoint list of the 12
  queued BO jobs that come last in the first runner's order (`PAPERB_ONLY`). When all 90 files exist, both runners are
  stopped, so a job the first runner reaches after the second runner has done it is never finished twice.
