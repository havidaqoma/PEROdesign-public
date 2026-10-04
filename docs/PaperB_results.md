# Paper B results (2026-10-01)

Pre-registration: `docs/PaperB_preregistration.md`, commit `2b32a78` (before any run), amendments A1–A3 (all
committed before the affected results existed). Data: `phase0/paperB/runs/*.json` (90 files),
`phase0/paperB/result.json`, `swf.json`, `numbers.json`, `figures/tables.md`, logs in `phase0/paperB/logs/`.
Labels: **measured** = read from the run files; **rule** = the pre-registered §7 verdict; **post-hoc** = analysis
added after the runs. Every efficiency is a model prediction (G1 NO-GO, MASTER §25).

## Run health (measured)

- 90/90 runs, 21,600 simulator calls, 16 infeasible calls in total (largest in one run: 2). No case is flagged
  unreliable. `scripts/paperB_verify_runs.py`: every run has 240 calls, the shared start is identical across methods,
  and every call's library hash matches its material set.
- The batch needed three restarts for throughput and memory (amendments A1–A3). No run file existed at any restart
  except the 10 NSGA-II runs reused under A3 (their code was unchanged).

## Q1: optimiser comparison (rule: 95% t-CI non-overlap, 5 seeds)

| Case | HV verdicts (Q1a) | IGD+ verdicts (Q1b) | BO HV gain over random | Median calls to 95% of best HV (R / N / BO) |
|---|---|---|---|---|
| p-i-n base | N>R, BO>R, BO>N | N>R, BO>R, BO>N | +11.7% | >240 / 202 / 37 |
| p-i-n worse | N>R, BO>R, BO>N | BO>R, BO>N | +16.8% | >240 / >240 / 38 |
| p-i-n better | BO>R, BO>N | BO>R, BO>N | +6.4% | >240 / 135 / 27 |
| n-i-p base | N>R, BO>R, BO>N | N>R, BO>R, BO>N | +8.0% | >240 / 125 / 36 |
| n-i-p worse | N>R, BO>R, BO>N | N>R, BO>R, BO>N | +10.8% | >240 / 229 / 47 |
| n-i-p better | N>R, BO>R, BO>N | N>R, BO>R, BO>N | +5.0% | 235 / 100 / 25 |

- **Mixed BO beats both random search and mixed NSGA-II in all 6 cases, on both scores.** Paper A's qNEHVI separated
  from NSGA-II in only 3 of 6. Mixed BO reaches 95% of the best HV in 25–47 calls.
- Mixed BO spends 77–83% of its calls on NiOx/Cu and NiOx/Ag, against 33% for random search. It learns which material
  sets matter.
- HV still mostly rewards the best PCE found (disclosed in the pre-registration, §6). IGD+, which scores how much of
  the whole front a run recovers, gives the same BO verdicts.

## Q2: the front and the gap (rule: "small" if < 1 PCE point and < 5% cost)

| Case | PCE-optimal (module %, USD/W) | Cost-optimal (module %, USD/W) | ΔPCE (pt) | ΔCost (%) | Wording (rule, short form; full text in prereg §7) | Spearman ρ |
|---|---|---|---|---|---|---|
| p-i-n base | NiOx/Ag 22.26, 0.4438 | NiOx/Cu 22.15, 0.3293 | 0.117 | 34.8 | cost differs, efficiency practically equal; cheaper set dominates | −0.70 |
| p-i-n worse | NiOx/Ag 19.66, 0.4957 | NiOx/Cu 19.38, 0.3699 | 0.289 | 34.0 | **material trade-off exists** | −0.70 |
| p-i-n better | NiOx/Ag 23.65, 0.4234 | NiOx/Cu 23.60, 0.3149 | 0.055 | 34.5 | cost differs, efficiency practically equal; cheaper set dominates | −0.61 |
| n-i-p base | NiOx/Ag 22.37, 0.3709 | NiOx/Cu 22.27, 0.2944 | 0.099 | 26.0 | cost differs, efficiency practically equal; cheaper set dominates | −0.68 |
| n-i-p worse | NiOx/Ag 19.73, 0.4154 | NiOx/Cu 19.48, 0.3313 | 0.244 | 25.4 | **material trade-off exists** | −0.69 |
| n-i-p better | NiOx/Ag 23.47, 0.3663 | NiOx/Cu 23.31, 0.2862 | 0.163 | 28.0 | cost differs, efficiency practically equal; cheaper set dominates | −0.62 |

- **The front always has two material sets: NiOx/Ag (most efficient) and NiOx/Cu (cheapest).** PTAA and gold are
  never on it. The gap is "not small" in every case (ΔCost 25–35%), unlike Paper A.
- **What the gap is made of:** silver adds 0.06–0.29 PCE points (optics of the back mirror) for 25–35% more cost per
  watt. By the registered 0.2-point line, that is a real trade-off only in the two "worse" scenarios. In the other
  four the cheaper copper wins for practical purposes.
- Gold designs reach the same PCE as NiOx/Cu (within 0.044 points) but cost at least 9.7–17.4 USD/W, which is
  34–47 times the cheapest copper design.
- The pooled ρ(PCE, USD/W) is −0.61 to −0.70, against −0.96 to −0.999 in Paper A. Material choice is what breaks
  the "efficiency equals cost" lock.
- CN / IN capital rates move every optimum by at most 2.3% (table in `figures/tables.md`).

## Q3: robustness over the 3 scenarios (rule)

- **Materials robust in both stacks:** the PCE-optimal set is NiOx/Ag and the cost-optimal set is NiOx/Cu in every
  scenario.
- **Q1 robust for n-i-p** (both scores): all pairwise verdicts identical and BO beats random in every scenario.
  **Not robust for p-i-n:** NSGA-II does not beat random in the "better" scenario (HV) or in "worse" and "better"
  (IGD+). BO beats both everywhere.

## Q4: break-even PTAA price (rule)

- In every case the best PTAA design is **less** efficient than the best NiOx design with the same metal, by
  0.03–0.89 points. So PTAA is "not competitive at any price in this model": even free PTAA would not reach NiOx's
  cost per watt.
- **Post-hoc:** in the pilot at the Paper A reference thicknesses, PTAA was ahead in p-i-n (19.34% vs 18.48% with Cu).
  After optimisation NiOx wins everywhere, at thin layers of 5–14 nm (21 nm in one n-i-p case).
- **Caveat (disclosed before the runs, D2):** the B2 contact rule gives NiOx's deeper valence band a larger built-in
  voltage. In the n-i-p reference design this explained 0.24 of a 0.82-point NiOx lead. The PTAA result is therefore
  partly a property of the contact model.

## Sensitivity S-WF: bare metal work functions (n-i-p, reported, not a verdict)

- The pooled best design of each material set was re-simulated with the anode at the metal's bare work function
  (Au 5.1, Ag 4.7, Cu 4.6 eV) instead of B2. Only **7 of 18** simulations gave a complete J-V. The rest stopped with a
  partial J-V, which counts as failed.
- PTAA/Au completes in all three scenarios and loses 1.2–1.6 points (base 21.48 → 19.97%). Copper and silver on
  NiOx (whose valence band sits 1.0–1.1 eV below these work functions) either fail, or in the "worse" scenario fall to 6.7–8.4%.
- **What this means:** the copper/silver cost advantage in the main result depends on a barrier-free hole contact. In
  real devices that takes an interlayer (for example MoOx), which this model neither simulates nor costs. The main
  result should be read as "copper or silver with an ohmic hole contact".

## What this means (plain English)

1. Letting the optimiser choose materials creates the trade-off that Paper A could not find. The cheapest good design
   is NiOx with copper, and the most efficient is NiOx with silver.
2. Silver's efficiency gain is small (at most 0.29 points) and costs about a third more per watt. With typical film
   quality, copper is the practical choice. Only with a poor absorber (the "worse" scenario, +0.24 to 0.29 points for
   25 to 34% more cost per watt) does the registered rule call it a trade-off. That is a front, not a claim that
   silver pays: at a factory-gate cost per watt it still costs more.
3. Gold and PTAA are never worth it in this model, with two caveats. Gold costs 34–47 times more per watt for no
   efficiency gain, but only under ideal (barrier-free) contacts. Without an interlayer, copper and silver on NiOx
   fail (S-WF) while gold on PTAA still works. PTAA trails NiOx by only 0.03–0.07 points in the p-i-n "worse"
   scenario. That is smaller than the contact-rule effect measured for n-i-p (D2, 0.24 points), and PTAA's thinnest
   allowed layer is 10 nm against 5 nm for NiOx.
4. Mixed-variable BO clearly beats NSGA-II and random search here, more clearly than in Paper A. It finds the right
   materials within about 40 simulator calls.
5. Two model limits matter for any real-world claim: the contacts are ideal (barrier-free), and the cost of the
   interlayer that copper or silver would need is not included.

## Post-hoc comparison with Paper A (not registered)

- n-i-p: Paper A's PTAA/gold optimum cost 10.90 USD/W (base). Paper B's NiOx/copper cost-optimum costs 0.294 USD/W,
  about 37 times less, at a higher model PCE. But the contacts differ (B2 vs production; G0 deltas +0.41 cell / +0.37 module
  points at the reference), and NiOx on top of the absorber in n-i-p is a model-only option.
- p-i-n: the NiOx/copper cost-optimum is 0.329 USD/W vs 0.339 in Paper A (base), again with B2 contacts.

## Independent check (agy / gemini-3.8-flash-high, 2026-10-01, read-only; tracked-file hashes identical before and after)

Verdict "minor corrections". It re-checked more than 50 numbers against the data files and found no mismatch. It
confirmed that amendments A1–A3 came before the affected results and that the 10 reused NSGA-II runs are valid
(`run_nsga2`, `objective_b` and the libraries are unchanged). All 5 minor findings were adopted:
(1) the G0 delta is now given as cell and module PCE (checked: +0.41 / +0.37);
(2) the Q2 wording now shows the registered phrase in its short form;
(3) the PTAA caveat is given for the p-i-n "worse" case;
(4) the claim that silver "pays" was removed;
(5) gold's lack of an efficiency gain is now stated as conditional on ideal contacts.
