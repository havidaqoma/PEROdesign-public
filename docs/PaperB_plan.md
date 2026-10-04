# Paper B: plan (2026-10-01; decisions B1–B5 taken by the agent under Havid's standing grant, 2026-10-01 00:15:
"continue ... and decide what is the best until everything is finished". Each can be overridden; see §1.)

**What:** the follow-up that Paper A's result asked for (PaperA_results.md, "What this means" 2). Paper A found that
inside one stack, with only thicknesses and stripe width to choose, efficiency and cost do not compete: the front had
1–5 points and the gap was small in all 6 cases. Paper B lets the optimiser **also choose materials**: the hole
transport layer (NiOx | PTAA) and the back-electrode metal (Cu | Ag | Au), in both stacks. This is a mixed
categorical + continuous search.
**Riskiest assumption:** that material choice creates a real trade-off. The pilot (§3) says it does, but mostly through
cost, and one of the HTL costs (PTAA) is a lab-catalogue price that its own source calls arbitrary. So the paper
also reports a computed break-even PTAA price, and the result reads "trade-off exists if ...", not "PTAA is too
expensive".

Status labels: **[measured]** = from a file in this repo; **[estimated]** = projection; **[assumed]** = a choice.

## 1. Decisions (defaults taken; Havid can change any)

| # | Decision | Taken | Alternative | Why this one |
|---|---|---|---|---|
| B1 | **Material options** | HTL ∈ {NiOx, PTAA}, metal ∈ {Cu, Ag, Au}, in both stacks; ETL C60 and (p-i-n) SnO2 buffer fixed. 6 combinations per stack. | Add Spiro-OMeTAD, TiO2, PEDOT:PSS, PCBM. | Only these have both simulable physics AND a sourced price [measured]: Spiro fails SimSS convergence with every device-fitted source (MASTER §24); TiO2-c has physics but no price; PEDOT:PSS/PCBM have no device-fitted source. Ag needed only a density source (added, provenance gate passes). |
| B2 | **Contacts** | Rule B2 for every combination: electrode work function = majority band edge of the layer it touches (barrier-free). | Keep Paper A's production contacts. | Production n-i-p uses fixed 4.05 / 5.2 eV. With NiOx on top (E_v 5.7 eV) that is a 0.5 eV barrier, so material choice would be confounded with a contact artefact. B2 was already registered and used in G1 step 2. Cost of the change is measured (gate G0 deltas: +0.31 / +0.41 cell-PCE points at the reference designs). |
| B3 | **Metal work function** | Not in the main runs (B2). One registered sensitivity S-WF for n-i-p (metal touches the HTL): anode = bare metal work function from one SCAPS input table (Au 5.1, Ag 4.7, Cu 4.6 eV). | Use metal work functions in the main runs. | These are simulation inputs chosen by other authors, not measurements (same caveat as P1). A barrier-free main case plus a labelled sensitivity keeps the main claim clean. p-i-n: the metal sits behind Liu's 300 nm ITO, so its work function does not enter. |
| B4 | **Search, budget, seeds** | Same as Paper A: 240 calls, 5 seeds, 3 scenarios, 2 stacks, 3 methods (Sobol random, mixed-variable NSGA-II, mixed BO = qLogNEHVI on MixedSingleTaskGP). 90 runs, 21,600 calls. | 480 calls (larger space). | Keeps the budget comparable with Paper A. The pilot shows the 6 combinations differ mainly in cost, which a model learns fast. |
| B5 | **Cost axis for the optimisers** | log10(USD/W). The gap and all reported costs stay in USD/W. | Linear USD/W. | Au designs cost ~30× Cu designs [measured, pilot]; on a linear axis the Cu/Ag front would be a sliver of the hypervolume. |

## 2. Known unknowns

| Unknown | Handling |
|---|---|
| PTAA price is a lab-catalogue value ("the price is arbitrary", Shahinuzzaman 2022 Table 2) | Registered Q4: the break-even PTAA price at which PTAA designs reach the cost-optimal end. The high-price case (2000 USD/g) is reported as before. |
| NiOx on top of the absorber (n-i-p) is uncommon in practice | Reported as a model-only option; the physics values are the same NiOx library values. |
| New interfaces PTAA\|MAPbI3 and MAPbI3\|NiOx have no source | SimSS default hole-side interface transferred (the same values as the production MAPbI3\|PTAA); labelled. |
| Wall time | 21,600 calls, pilot median 5.0 s per sim at 12 workers [measured] → about 2.5 h of simulation plus BO overhead (~90 s per mixed-BO batch on a synthetic function [measured]) → **4–6 h** [estimated]. |

## 3. Work done before the pre-registration (all disclosed in its §9)
- Sources: Ag density (PMC5784555, CC-BY-4.0) and Aug-2026 silver price (World Bank Pink Sheet, already saved) pass
  the provenance gate; McPeak 2015 optics for Ag and Au built with a converter that reproduces the committed Cu
  table byte for byte.
- Code (new files, Paper A code unchanged): `perodesign/library/paperB_overlay.yaml`, `perodesign/optim/objective_b.py`,
  `perodesign/optim/search_b.py`, `scripts/paperB_run.py`; tea gained an optional `physics_setup`/`physics_library`
  argument (default = old behaviour, tested).
- Gate G0 (baseline reproduction): PASS, 8/8 designs identical to Paper A (`phase0/paperB/gate0.json`).
- Pilot: 156 sims, all complete (`phase0/paperB/pilot.json`).

## 4. After the runs
`paperB_run.py analyse` → `result.json`; `swf` → `swf.json`; `docs/PaperB_results.md`; MASTER §29; then the
manuscript (same toolchain as Paper A) if Havid wants Paper B written up as a paper.
