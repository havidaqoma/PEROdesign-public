# P2 sensitivity: results

Registered plan: `docs/P2_sensitivity_preregistration.md` (§5 amendment committed in f355799 and 5f35a2d, before
any index was computed). Result file: `phase0/sensitivity/result.json`, computed from `phase0/sensitivity/sims.jsonl`
at commit 5f35a2d (log: `phase0/sensitivity/analyse.log`).

## Runs
| Item | Value |
|---|---|
| Unique SimSS sims | 8,704 of 8,704 |
| Status | 8,624 complete, 71 failed, 9 partial |
| Usable rows | 12,696 of 12,800 (0.81% lost) |
| Method (by §3 rule) | Borgonovo δ (`delta_raw`, SALib 1.6.0, 1,000 resamples) |

## Registered result (computed)
| Output | p5 / p50 / p95 | Top 5 by δ | Top 5 resolved? |
|---|---|---|---|
| Cell PCE (%) | 5.31 / 19.07 / 25.39 | P1 N_t_bulk (0.254), P2 mu_n (0.251), P9 MAPbI3/C60 N_t_int (0.154), P7 N_ion (0.146), P14 C60 E_c (0.141) | Yes |
| Cost (USD/W) | 0.228 / 0.401 / 1.365 | P1 N_t_bulk (0.284), P2 mu_n (0.254), C3 yield (0.203), P7 N_ion (0.195), P12 NiOx E_v (0.155) | No: rank 5 (0.155 ± 0.010) overlaps rank 6, C7 dead width (0.152 ± 0.009) |

Module PCE p5 / p50 / p95: 4.88 / 17.28 / 23.05 %.
Robustness check (`delta_balanced`): cell PCE top 5 is the same set in a different order; USD/W top 5 is the same.

## Post-hoc check (NOT pre-registered; added after the result was seen)
The δ estimator has a positive bias, so a parameter that does nothing still gets δ > 0. The 8 cost parameters
(C1 to C8) cannot change cell PCE, so their δ on cell PCE shows how big that bias is: 0.095 to 0.123. The
highest δ + CI is 0.130.
- Cell PCE: all 5 top parameters are above 0.130 (P14 only just: 0.141 − 0.007 = 0.134). Every other physics
  parameter is at or below that ceiling. So δ values of about 0.10 to 0.13 do not show a real effect.
- USD/W: 6 parameters are above the ceiling (the top 5 plus C7 dead width). This agrees with the rule saying the
  USD/W top 5 is not resolved.
- Use: read δ as "above or below the null ceiling". Do not rank the parameters below about 0.13. This check does
  not change the registered result.
