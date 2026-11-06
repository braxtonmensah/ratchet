# GATE (exploratory, stored rows): do decisions far from the target learn slowly?

Written 2026-11-05 19:21 ET (PowerShell clock) by the Silicyte lead, BEFORE any quantity below was computed.
Model: if a step's success depends only on its remaining distance k to the target, then s_d = q_1 q_2 ... q_d, so
q_k = s_k / s_{k-1} (s_0 = 1) is the success of the step taken k hops from the goal.
Data: 0128 round_0..10.json fixed_rows (MEAS 29000, 30 tasks per depth), pooled over s1 and FRONTIER_s2..s4 per round (120 tasks per
depth per round), shares smoothed (k + 0.5) / (n + 1). Stdlib, login node.

- e_k(t) = 1 - min(q_k(t), 0.999); alpha(k) = -(OLS slope of ln e_k on ln mean N_t), k = 1..8; bootstrap over tasks (500 resamples,
  seed 7) for a 90% interval.
- FAR_SLOW iff alpha(k) for k in 5..8 is below alpha(k) for k in 2..4 with non-overlapping 90% intervals of the two band means.
- NEAR_EQUAL iff the band means differ by less than 0.05. Otherwise MIXED.
- Caveat stated now: q_k from ratios of noisy shares is unstable where s_{k-1} is small (k >= 8).
