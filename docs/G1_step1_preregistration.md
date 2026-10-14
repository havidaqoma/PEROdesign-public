# G1 step 1 — pre-registration (written 2026-09-29, BEFORE any candidate device was looked at)

Decision D3 (plan v2 §20): G1 = 3–5 well-characterised literature stacks first, then the family-level Perovskite
Database fit with a 3-week cap. Havid chose the **mixed set** on 2026-09-29. Plan v2 gives no pass rule for this step,
so this file sets it. It is committed before any candidate paper was opened. If the rules change later, the change and
its reason are appended below, and this text is not edited.

**Already visible when this was written (disclosure):** the model's own results on its two stacks (industrial p-i-n
19.84 %, lab n-i-p 22.51 %), the Lee-2018 NiOx sensitivity, and Liu 2025's ~15 % module figure. No candidate
device for this step had been searched for or read.

## 1. What a device needs to qualify
A device qualifies only if ONE open-access paper gives all of these for the SAME device:
1. **Measured** J-V under 1 sun: Voc, Jsc, FF and PCE (champion or mean; record which).
2. A **full drift-diffusion parameter table** for that device: thickness, band edges, doping, mobilities, bulk
   and interface recombination, and contacts. The table must allow a SimSS input with every value either given
   in the paper or explicitly marked as assumed (at most 5 assumed parameters per device, listed).
3. The paper's own **simulated** J-V from that table (so we can separate transcription or simulator errors
   from model-vs-reality error).
4. A licence that allows saving the text (CC BY / CC BY-NC / similar) in `data/sources/`.

Preference order when there are more than enough candidates: (a) the paper used SIMsalabim/SimSS itself (1:1
parameter mapping); (b) some parameters measured independently (SCLC, TPV, PL, UPS) and not only fitted;
(c) newer; (d) more cited.

## 2. The mix (all four required; one device can cover two slots)
- at least 1 **n-i-p** and at least 1 **p-i-n**
- at least 1 **NiOx-HTL** device (closest to the Liu industrial line)
- at least 1 **lab-record-type** device (organic HTL, e.g. PTAA or spiro-OMeTAD)
- 3 devices minimum, 5 maximum. Absorber: any lead-halide perovskite for which an nk file is available
  or published; MAPbI3 is preferred.

## 3. Two checks per device, with fixed tolerances
**Check R (reproduce the paper's simulation):** our SimSS run with the transcribed table vs the paper's simulated
J-V. Tolerance: |ΔVoc| ≤ 0.03 V, |ΔJsc| ≤ 5 % rel, |ΔFF| ≤ 0.05 abs, |ΔPCE| ≤ 1.5 points abs.
A failure means our transcription, optics or simulator differs. It is diagnosed before check M is interpreted.

**Check M (model vs measured):** our SimSS run vs the paper's MEASURED J-V. Tolerance: |ΔVoc| ≤ 0.05 V,
|ΔJsc| ≤ 10 % rel, |ΔFF| ≤ 0.08 abs, |ΔPCE| ≤ 20 % rel.

## 4. Go / no-go
- **GO** if at least 3 devices pass check M on all four metrics, and every one of the 4 mix slots is covered by
  a device that passes check M.
- **NO-GO** otherwise. The failure is reported per device and per metric. This rule is not widened after the
  fact. A NO-GO does not stop the project: plan v2 moves to the family-level fit, with the NO-GO as a stated
  limitation.
- Every device result is labelled: `fitted` (the paper tuned parameters to its own J-V, so check M is partly
  circular) or `independent` (the key parameters were measured separately).
  **A GO carried only by `fitted` devices shows that the simulator reproduces published fits. It does NOT show
  predictive power.** Predictive power is tested by the family-level database fit (G1 step 2).

## 5. Search budget
One systematic Europe PMC open-access search (script committed with its output), plus at most one targeted
follow-up round. If fewer than 3 devices qualify, report how many qualified and why the others were rejected.
Do not loosen §1.

## Changes after registration

### Amendment A1 (2026-09-29, written and committed BEFORE the widened search was run) — search budget only
Decided by Havid (option 1 of MASTER_SUMMARY §22). **§1–§4 are unchanged.** §5 gets ONE extra search round:

- **Why:** the first round (147 Europe PMC papers + SI of 10) found 1 qualifying device. Complete simulator input
  files are more often deposited in data repositories than printed in article text.
- **Sources (only these):** (1) the Zenodo records API, and (2) GitHub via the `gh` CLI (repository search and code
  search).
- **Queries (fixed now):**
  - Zenodo: `SIMsalabim`, `SimSS`, `"drift-diffusion" perovskite solar`, `drift diffusion perovskite J-V`,
    `SCAPS perovskite`, `SCAPS-1D perovskite`, `perovskite solar cell simulation parameters`,
    `perovskite solar cell dataset J-V`. Up to 100 records per query, most relevant first.
  - GitHub repositories: `SIMsalabim`, `SimSS perovskite`, `drift-diffusion perovskite`, `SCAPS perovskite`.
  - GitHub code: `filename:simulation_setup.txt`, `filename:device_parameters.txt`, `"SIMsalabim Layer parameters"`,
    `extension:def SCAPS`.
- **Screen:** a record or repository is read by hand only if it contains BOTH (a) a simulator input file or
  complete parameter table for a named, fabricated device, and (b) measured J-V of that device (file or linked
  paper). Everything else is logged with the reason it was dropped.
- **Near-misses may requalify.** If new material from these sources removes enough unstated parameters that a
  device from round 1 (e.g. Gil-Escrig 2025, Mukherjee 2024) now meets §1 unchanged, it qualifies. The same §1
  counting applies.
- **Already visible when this was written (disclosure):** the Zenodo records of Rodkey 2024 (10656920) and
  Gil-Escrig 2025 (15423599). The latter holds figure data only, with no simulator input files. No other Zenodo or
  GitHub result had been opened.
- **No further rounds.** If fewer than 3 devices qualify, or the 4 slots are not all covered, after this round,
  step 1 is a final NO-GO. G1 step 2 then goes ahead with that stated as a limitation.
