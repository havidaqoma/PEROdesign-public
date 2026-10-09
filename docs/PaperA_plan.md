# Paper A: plan (2026-09-30; decisions A1–A4 taken by Havid the same day)

> **Decided (Havid, 2026-09-30):** A1 current library · A2 3 scenarios (base / worse / better) · A3 Malaysia main
> case + CN/IN capital-rate row · A4 Digital Discovery. All four match the recommendations below.

**What:** Paper A from plan v2 §15. It is the environment paper: drift-diffusion (SimSS) → module → factory-gate
cost (Malaysia). BO (qNEHVI) and NSGA-II search for designs that trade off efficiency against cost, and the paper
reports the **efficiency–cost gap**.
**Approach:** First, a pre-registered optimiser comparison on the existing library, run under 3 library scenarios
chosen from the P2 top drivers. Then the gap analysis on the combined Pareto fronts.
**Riskiest assumption:** that there *is* a gap inside one architecture. Across architectures the gap is mostly
gold versus copper (MASTER §16), and that is already known. Inside one stack the knobs are layer thicknesses and
stripe width only, so the gap could be small. A small gap is still a result, and the paper will report it either
way.

Status labels: **[measured]** = from a file in this repo; **[estimated]** = my projection; **[assumed]** = a
choice, not a fact.

---

## 1. Decisions you may want to change

| # | Decision | Default (recommended) | Alternative | Cost of changing later |
|---|---|---|---|---|
| A1 | **Design space** | The current library as it stands: n-i-p C60/MAPbI3/PTAA/Au (3 thicknesses) and p-i-n NiOx/MAPbI3/C60/SnO2/Cu (4 thicknesses), plus module stripe width (and TCO sheet resistance as a process knob). The electrode is fixed by the architecture [measured: `device_setup` nkBE_file]. | Add electrode choice (Au/Ag/Cu/carbon) or new materials (SAMs, FAPbI3). Each one needs sourced optics, electrical values and prices. G1 showed that sourcing is the slow part. | High: every new material needs sourcing, tests, and a re-run of all optimisations |
| A2 | **Robustness to the P2 drivers** | Run every optimisation under 3 library scenarios built from the two top P2 drivers (P1 bulk traps, P2 electron mobility): base, "worse" (N_t ×√10, µ_n ÷√10) and "better" (N_t ÷√10, µ_n ×√10). Report whether the optimal designs and the gap change. | Base library only, with P2 reported as a caveat. | Medium: 3× the simulations (still about 5 h) |
| A3 | **Regions** | Malaysia (bottom-up running costs) is the main case. CN and IN appear only as a capital-rate sensitivity row: the library has MY, CN and IN, and only the rate differs [measured: cost_library_v1.yaml]. EU/US are not in the library. | Source EU/US/CN electricity, labour and rent first. That is days of work, with the same blocking risk as KWSP. | Low: cost is recomputed from the stored sims, and no new simulations are needed |
| A4 | **Venue and claim** | Digital Discovery. Claim: "model predictions of design rankings and efficiency–cost trends" (G1 wording, MASTER §25). | Joule / EES. Unlikely, because G1 is a NO-GO: no validated p-i-n or NiOx device. | Low now, high after writing starts |

## 2. Known unknowns and how the plan handles them

| Unknown | Default | What would change it |
|---|---|---|
| BO vs NSGA-II may be tied on a 4–5-D problem | Report hypervolume against the number of simulator calls, with 5 seeds and Sobol random search as the floor. Do not claim that one optimiser wins unless the CIs separate. | If random search matches both, the optimiser comparison becomes a short SI note and the paper leads with the gap |
| SimSS failures inside the search (P2: 0.9% of sims failed [measured]) | A failed sim is recorded as infeasible. It uses up one call from the budget and gets no objective value. The count is reported. | If failures are > 5% inside any optimiser run, stop and add a feasibility model |
| Contact scenario (P1: 0.43–0.71 USD/W spread from contacts [measured]) | Use `ideal` contacts (an upper bound, labelled as such) | If you want the measured-NiOx scenario as a second case, that doubles the p-i-n simulations |
| Long sims (P2 median 4.5 s, p90 29 s [measured]) | 12 workers. BO in batches of q = 12. | — |
| Wall time | Measured throughput sets it: P2 ran about 70–100 sims/min on 12 workers. 3 methods × 5 seeds × 240 calls × 2 architectures × 3 scenarios = 21,600 sims ≈ **4–5 h** [estimated] | Budget per run can go up to 480 calls if the fronts are still moving at 240 |

## 3. Mechanical work (compressed)

1. **Environment:** install `botorch` and `pymoo` into `~/venvs/perodesign-dev`. Both are missing now, and `torch`
   is present [measured]. Add `perodesign/optim/objective.py`: design vector → schema validation → SimSS → module
   → USD/W (MY). Results are cached by design hash; cache hits still count as simulator calls. Tests.
2. **Pre-registration** (`docs/PaperA_preregistration.md`), committed before any optimisation run. It fixes the
   search bounds (library `thickness_nm` min/max, stripe width range), the objectives (max module PCE, min USD/W),
   the hypervolume reference point, the budget, the seeds, the gap metric (ΔPCE in absolute points and ΔUSD/W in %
   between the PCE-optimal and cost-optimal designs on the combined front), the scenarios (A2) and the stop rules.
   agy reviews it, and every reviewer point is checked before adoption.
3. **Run** detached (the P2 lessons apply: setsid + watcher, BLAS pinned, native-FS clone).
4. **Analysis:** hypervolume curves, Pareto fronts per scenario, gap table, cost attribution per layer, the
   CN/IN rate row, a failure count. Tests rebuild every number from the stored runs.
5. **Figures** (5): environment schematic; HV vs calls; Pareto fronts × 3 scenarios; gap and cost-attribution
   waterfall; P2 sensitivity (already computed).
6. **Manuscript:** follows the manuscript-production conventions. Every number traces to a run hash or a DOI.
   The final submission is your decision (the only human gate).

Estimated calendar time [estimated]: build + pre-registration 1–2 days, runs about 5 h, analysis + writing 3–4 days.

## 4. What I need from you

1. **A1:** keep the current library (recommended), or extend the design space first?
2. **A2:** 3 library scenarios (recommended), or base only?
3. **A3:** Malaysia main case + CN/IN rate row (recommended), or source more regions first?
4. **A4:** Digital Discovery (recommended), or aim higher?
