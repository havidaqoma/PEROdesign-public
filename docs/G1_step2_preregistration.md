# G1 step 2 — pre-registration (written 2026-09-29, BEFORE any step-2 simulation and before any material source was chosen)

Decision D3 (plan v2 §20): after step 1, G1 continues with the Perovskite Database fit, capped at 3 weeks. Step 1
ended in a final NO-GO (`docs/G1_step1_preregistration.md`, amendment A1). Havid chose on 2026-09-29, after a
plain-English explanation (MASTER_SUMMARY §22 and chat):
- **Q1 = A:** the main test is same-paper absorber-thickness series. The plan's cross-lab family ranking is
  reported alongside as a secondary result.
- **Q2 = A:** each new material is taken from one open-access parameter table, quoted verbatim and tested. Stacks
  with mesoporous layers are skipped, and every value is labelled "simulation-paper value".

**Already visible when this was written (disclosure):**
- Database metadata in `phase0/g1s2/feasibility.json`: family sizes, per-family PCE median and IQR, thickness IQR.
- The list of same-paper thickness series and their stack strings. The device-level PCE values of the series and
  families were NOT looked at, and nothing about how PCE depends on thickness in the data was looked at.
- The production library's own behaviour: MAPbI3 PCE vs thickness on its own stacks (Phase 0 grid: 22.5% at 500 nm).

## 1. Data
The Perovskite Database (Archive) v1.0.1, Zenodo doi 10.5281/zenodo.5837035, CC BY 4.0 (Jacobsson et al., Nat.
Energy 7, 107 (2022)). The zip md5 is 1119f05607ebe4bbf46ad7cc3258c6b0 and the CSV sha256 is in
`phase0/g1s2/pdb_csv.sha256`. The data are not committed; `scripts/get_perovskite_db.sh` re-downloads and checks them.
Rows used: `JV_default_PCE` present, polycrystalline 3D, `Cell_architecture` nip or pin. Thicknesses are in nm as
the database states.

## 2. What can be simulated (fixed now)
- **Absorber:** `MAPbI` only, using the PRODUCTION library MAPbI3 unchanged (SimSS default values: this is the
  thing being validated). Other compositions are excluded.
- **Transport layers allowed:** HTL ∈ {Spiro-MeOTAD, PTAA, PEDOT:PSS, NiO-c}; electron side ∈ {TiO2-c, SnO2-c, C60,
  PCBM-60, BCP}. PTAA, NiO-c (= production NiOx), SnO2-c (= production SnO2) and C60 use the production library.
  Spiro-MeOTAD, TiO2-c, PEDOT:PSS, PCBM-60 and BCP are new. Any other layer, including every mesoporous
  (`-mp`), nanowire, nanoparticle (`-np`) or interlayer entry, makes the stack not simulable.
- **Back contact:** exactly one of Au, Ag, Al (optics from the SimSS nk files). Multi-layer back contacts are
  excluded.
- **Contacts:** `sfb` work functions on both sides for every device (no contact barrier), as in the production
  `ideal` scenario. Contact effects are therefore NOT tested.
- **New-material values:** from ONE open-access paper (CC licence) with a single table giving eps_r, Eg, electron
  affinity, Nc, Nv, mu_n, mu_p and doping for as many of the 5 new materials as possible. It is chosen by a fixed
  Europe PMC query (script committed with its output) as the table covering the most of the 5 materials. Ties go to
  the newer paper. A material the table lacks is taken from the next table by the same rule.
  - SimSS has one density of states: N_c(SimSS) = sqrt(Nc·Nv).
  - No bulk traps in transport layers, as in the production transport layers.
  - New interfaces copy the production interface of the same side (electron side from `MAPbI3|C60`, hole side from
    `MAPbI3|PTAA`), labelled `simss_default_transferred`.
  - The source is chosen once and **not swapped after any step-2 simulation.**
- **Optics:** SimSS nk files where they exist. Spiro-MeOTAD has no SimSS nk file, so it gets a constant n = 1.7,
  k = 0 (flagged approximation).
- **Transport-layer thickness:** the device's own value if the database gives one per layer. Otherwise a fixed
  default: Spiro-MeOTAD 200, PTAA 20, PEDOT:PSS 40, NiO-c 20, TiO2-c 50, SnO2-c 30, C60 30, PCBM-60 60, BCP 8 nm.
  These defaults are flagged. The absorber thickness is always the device's own value, and only 50–2000 nm is used.
- **Solver:** production settings. A simulation that fails is a missing point, and every failure is counted and
  reported. The solver may be changed only for convergence (grid or voltage step), applied to ALL step-2 runs, and
  disclosed.

## 3. Main test: same-paper absorber-thickness series (decides GO / NO-GO)
- **Series:** rows with the same `Ref_DOI_number` and identical architecture | composition | HTL | ETL | back
  contact, with ≥ 4 distinct absorber thicknesses spanning max/min ≥ 1.5. Rows at the same thickness are averaged
  (PCE, Jsc, Voc, FF).
- **Eligible:** the whole stack is simulable under §2, and ≥ 4 thickness points simulate successfully.
- **Per series:** Spearman ρ between simulated and measured PCE across thicknesses (ρ_sim). Also reported:
  ρ for Jsc, Voc and FF, and the **thickness-only baseline** ρ_base = Spearman(thickness, measured PCE).
- **GO if all of these hold:**
  1. ≥ 10 eligible series;
  2. median ρ_sim ≥ 0.5;
  3. ρ_sim > 0 in ≥ 60% of eligible series;
  4. mean ρ_sim beats chance: permutation test that shuffles measured PCE within each series (10,000 shuffles),
     one-sided p < 0.05.
- **Otherwise NO-GO.** It is reported per series and not widened afterwards.
- **Required wording:** if mean(ρ_sim) − mean(ρ_base) ≤ 0.10, the verdict must say "**the simulator adds no
  ranking information beyond thickness itself**", even when it is GO.

## 4. Secondary test: plan v2 §12 family ranking (reported, does not gate)
- **Families:** architecture × composition × HTL × ETL, with ≥ 20 devices that have complete per-layer
  thicknesses (as in `feasibility.json`) and a stack simulable under §2. Each device is simulated with its own
  thicknesses and back metal.
- **Per family:** Spearman ρ(simulated PCE, measured PCE). Reported: how many families have ρ ≥ 0.5, against the
  plan's "≥ 15 families".
- If fewer than 15 families are simulable, this is stated as "**the plan's 15-family bar cannot be reached with a
  1D model of these materials**". It is not counted as a model failure.
- **No parameters are fitted anywhere in step 2.** Every value is fixed before any run, so no held-out split is
  needed and the plan's 70/30 split does not apply.

## 5. Budget
3 weeks from 2026-09-29 (plan D3). One source search for the new materials, as defined in §2.

## Changes after registration

### Amendment B1 (2026-09-29, written BEFORE any step-2 simulation) — source outcome and one pre-declared sensitivity
The source search ran as registered (`scripts/find_g1s2_sources.py`, 73 open-access candidates, 0 failed requests
after Europe PMC 502/503 retries; output `phase0/g1s2/sources_search.json`).

**What the §2 rule selected:**
- **Primary table:** PMC12617105 (doi 10.1039/d5ra06604b, CC BY 3.0, 2025), table 1. It covers Spiro-OMeTAD,
  PC61BM and TiO2, 3 of 5 materials. It ties with PMC9694249 (2022) on count and wins on year. The paper is about
  a dye-sensitised cell; its table gives the transport-layer values as materials. Flagged, not a reason to swap.
- **PEDOT:PSS:** from the next table in rule order that has it: PMC9694249 (doi 10.3390/molecules27227927,
  CC BY 4.0, 2022).
- **BCP:** no qualifying table in any of the 73 candidates. **Every stack containing BCP is not simulable.**

**Reading check:** a looser header scan found 5 more tables naming 3–4 of the materials. All 5 are device-
performance or literature-review tables (PCE and year columns), not parameter tables, so the selection stands.

**Anomaly in the selected TiO2 column:** it lists "Density of p-type doping, N_A = 9.0 × 10^16" and N_D = 0 for an
electron-transport layer. PMC9694249 lists the same magnitude as donor doping (N_D 9 × 10^16), so this is likely a
row swap in the source. The registered rule keeps the value verbatim, and the MAIN result uses it as written.
**Pre-declared sensitivity S1:** the same runs with TiO2 N_D = 9e16 and N_A = 0. S1 is reported next to the main
verdict and does NOT replace it. PC61BM doping (N_D 1e-3, N_A 2e-3 cm⁻³) is used verbatim; it is effectively
undoped.

**Implementation (no new physics values):** the step-2 library is the production library plus an overlay file
(`perodesign/library/g1s2_overlay.yaml`). The production library file is not edited. The overlay adds:
- the 4 materials above and a constant-index Spiro nk file;
- `n-i-p2` = [buffer, ETL, absorber, HTL] for TiO2-c | PCBM-60 double ETLs;
- `p-i-n` roles [HTL, absorber, ETL] (no buffer), used only in step 2;
- MAPbI3 thickness bounds 50–2000 nm;
- SnO2 allowed as an ETL;
- transport-layer thickness bounds 5–300 nm (Spiro 20–1000 nm). These are input-validation guards, not physics
  values, so database thicknesses outside the old Phase 0 convergence bounds can be run. Failures are counted.
- For p-i-n stacks with a 4th layer (`p-i-n2`), the production p-i-n solver policy (full sweep, `untilVoc 0`) is
  applied.
Contacts: `sfb` both sides; back-metal optics are set per device (Au/Ag/Al).

### Amendment B2 (2026-09-29, before any database-device result) — contact rule corrected
**Error in §2:** §2 said "`sfb` work functions on both sides for every device (no contact barrier), as in the
production `ideal` scenario". That is wrong on two counts:
1. Production `ideal` uses `sfb` only for p-i-n, where the contact layers are doped (NiOx, SnO2). Production n-i-p
   uses fixed 4.05 / 5.2 eV.
2. `sfb` puts the electrode at the adjacent layer's own Fermi level. For an UNDOPED transport layer (C60, PTAA,
   PCBM, Spiro) that level is mid-gap, which gives a ~1 eV contact barrier. That is the opposite of the registered
   intent "no contact barrier".

**How it was found:** on generic stacks only, with no database device and no measured value. The production stack
C60/MAPbI3/PTAA (400 nm, Au) gives 20.58% with production contacts, and FAILS (no MPP) with `sfb`/`sfb`
(`scripts/g1s2_diag_sfb.py`). Four database test points had been run to debug the plumbing; all failed with no
PCE, so no simulated or measured value was seen.

**Corrected rule (keeps the intent "no contact barrier"):** each electrode's work function equals the MAJORITY band
edge of the transport layer it touches:
- cathode = E_c of the electron-side layer it touches;
- anode = E_v of the hole-side layer it touches.

This applies to every architecture. It is the thermionic, barrier-free contact. For the doped production p-i-n
layers it is within a few kT of `sfb`. Contact effects are still NOT tested.

### Amendment B3 (2026-09-29, before any database-device result) — solver settings for all step-2 runs
§2 allows solver-only changes if they apply to ALL step-2 runs and are disclosed. Found on GENERIC stacks only
(`scripts/g1s2_diag_*.py`, no database device):
- **Grid NP 500** (production 250). With NP 250, doped Spiro-OMeTAD (N_A 2e24 m⁻³ from the source) does not
  converge at any voltage. With NP 500 the J-V converges from 0 V upward. The production reference stack gives
  20.65% (NP 500) against 20.71% (NP 250).
- **MPP rule, one refinement:** a non-converged point at NEGATIVE bias (the first 1–2 settling points of the
  sweep) is ignored, but ONLY if the V = 0 point itself converged, so Jsc is a solved value. Non-convergence
  anywhere in [0, Vmpp] still fails the run, as in production.
- **SimSS timeout 120 s** per run (production 300 s). Converging runs take 5–40 s; a run over 120 s is a failure
  and is counted.
- Tried and **rejected**: finer voltage step, pre-conditioning bias, coupling, grid shape, acceleration, starting
  at 0 V or −0.14 V (all timed out or still failed).
- **Known remaining failure:** SnO2-c / MAPbI3 / Spiro does not converge at any voltage with any tried setting.
  Those points are failures, counted and reported. They are NOT fixed by changing physics values.

Generic-stack results with B3 (not database devices), all complete:
- C60 / MAPbI3 / PTAA (production reference): 20.65%
- C60 / MAPbI3 / Spiro: 17.65%
- PEDOT:PSS / MAPbI3 / PCBM: 21.43%
- NiOx / MAPbI3 / PCBM: 23.67%
- PTAA / MAPbI3 / C60: 21.73%

### Amendment C1 (2026-09-29, Havid chose "1") — round 2 with a stricter material-source rule
Written and committed BEFORE the round-2 source search and before any round-2 simulation.

**Round 1 stays on record.** Its verdict (NO-GO, 2 of 24 series eligible) is kept in `phase0/g1s2/result_main.json`
and MASTER §23, and is not overwritten. Round 2 writes to `phase0/g1s2/round2/`.

**Already visible when this was written (disclosure):** all round-1 results, including the measured PCE of the
2 eligible series, the 5 family ρ values, and which stacks failed to converge. Step 1 also showed that
Mukherjee 2024 (doi 10.1039/d4ma00873a) has a SCAPS table for its own NiO/PCBM cell. Round 2 is therefore NOT blind
to round 1. The only protection is that the new rule picks sources without reference to any database device or
measured value.

**What changes (only this):** the source of the 4 new materials Spiro-OMeTAD, TiO2-c, PEDOT:PSS and PCBM-60. BCP
stays not simulable unless the rule below finds a BCP table.

**What does NOT change:**
- the device selection (`phase0/g1s2/designs.json`, the same 24 series and 5 families, unchanged file);
- the absorber and production transport layers (MAPbI3, PTAA, NiOx, SnO2, C60);
- the conversion rules of §2 (N_c = sqrt(Nc·Nv), no transport-layer traps, transferred interfaces, Spiro constant
  n = 1.7);
- the contacts (B2) and the solver (B3);
- the pass criteria of §3 and §4 and the analysis script `scripts/g1s2_analyse.py`.

There is no sensitivity case in round 2: the S1 case (TiO2 doping flip) is dropped unless the new TiO2 source shows
the same row anomaly, in which case the value is used verbatim and the anomaly is reported.

**Source rule C1.** A material value qualifies only if ALL of these hold:
1. **Open access.** Europe PMC full text with a Creative Commons licence.
2. **Device-fitted.** In the same paper, the authors fabricated a perovskite solar cell containing that material
   AND ran a drift-diffusion simulation (SCAPS, SIMsalabim/SimSS, SETFOS, Driftfusion, IonMonger, gpvdm, COMSOL,
   ASA or AFORS-HET) that they compare with their own measured J-V or measured PCE/Voc/Jsc/FF. The sentence
   showing this is quoted verbatim, saved in `data/sources/g1s2r2/` and checked by a test. A paper that simulates
   only, or cites someone else's measurement, does not qualify.
3. **Complete table.** One table gives eps_r, Eg, electron affinity, Nc, Nv, mu_n, mu_p and doping for that
   material (the same 8 properties as §2).

**Selection (fixed now):**
- Candidates come from fixed Europe PMC queries in `scripts/find_g1s2r2_sources.py`, committed with their output.
  Any failed request stops the script with an error (never read as "no results").
- Candidate tables are ranked first by how many of the 4 materials they cover, then by the newer paper.
- For each material, the top-ranked table that passes rules 1–3 and the pre-check is used.

**Convergence pre-check (generic stacks only, no database device).** Each candidate material is tested on one
stack whose other layers are production materials, so a failure can be blamed on that material:
| Material | Pre-check stack |
|---|---|
| Spiro-OMeTAD | C60 (30) / MAPbI3 / Spiro (200) / Au, n-i-p |
| TiO2-c | TiO2-c (50) / MAPbI3 / PTAA (20) / Au, n-i-p |
| PEDOT:PSS | PEDOT:PSS (40) / MAPbI3 / C60 (30) / Ag, p-i-n |
| PCBM-60 | NiOx (20) / MAPbI3 / PCBM (60) / Ag, p-i-n |

The absorber is run at 200, 400 and 700 nm with the B2 contacts and the B3 solver.
- **Pass:** all 3 runs `complete`.
- **If a material fails:** the next-ranked qualifying table for it is tried. At most 3 tables are tried per
  material.
- **If all 3 fail:** stacks containing that material are not simulable in round 2. They are counted and reported.

This pre-check selects values that RUN, never values that AGREE with the database. It looks only at convergence
status, never at PCE. It is disclosed as a selection step.

**Labels:** values are labelled "from device-fitted simulation papers". This is still not a measurement of the
material, and cells built from different papers are a mix of sources.

**Final rule:** the round-2 verdict under §3 is the final step-2 verdict. There are no further source rounds. The
budget stays within the 3-week cap (plan D3).

**C1 outcome (recorded before the round-2 batch):**
- Search: 166 candidates, 72 with a parameter table. **3 pass C1**: Stanić 2022 (10.3390/ma15207310), Stanić 2021
  (10.3390/ma14216341) and Sajid 2023 (10.3390/nano13060983). First authors were checked on Crossref. All 3 cover
  only Spiro-OMeTAD and/or TiO2. **No qualifying source for PEDOT:PSS, PCBM or BCP.**
- Pre-check (`phase0/g1s2/round2/precheck.json`):
  - TiO2-c (Stanić 2022) passes.
  - Spiro-OMeTAD fails with both Stanić tables, so Spiro stacks are not simulable.
- Simulable stacks left: MAPbI3 with PTAA, NiOx, SnO2, C60, TiO2-c. That gives **1 of 24 series** (TiO2-c/MAPbI3/PTAA,
  4 points) and **0 of 5 families**. The §3 rule needs at least 10 eligible series, so the round-2 verdict is NO-GO by
  construction. It is known from stack metadata alone, before any round-2 simulation. The registered batch is still
  run and analysed unchanged.

**C1 correction (2026-09-29, after the agy review of round 2):** Sajid 2023 (10.3390/nano13060983) fails C1.2. The
authors fabricated a cell only to check an earlier simulation (19.03% simulated vs 11.77% measured) and did not fit
any parameter to its J-V. It is reclassified as rejected. **2 sources qualify** (Stanić 2022, Stanić 2021). No value
changes: the TiO2-c overlay comes from rank-1 Stanić 2022, so the overlay file, the round-2 batch and the verdict are
unchanged.
