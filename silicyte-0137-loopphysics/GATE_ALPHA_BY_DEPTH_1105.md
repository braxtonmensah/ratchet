# GATE (exploratory, stored rows): is the learning exponent the same at every depth?

Written 2026-11-05 19:11 ET (PowerShell clock) by the Silicyte lead, BEFORE any quantity below was computed.
Data: 0128 round_0..10.json fixed_rows (MEAS 29000, 30 tasks per depth 1..10), s1 and FRONTIER_s2..s4. Stdlib, login node.

- Per seed, round and depth d: solve share s_{d,t} (v and c), smoothed (k + 0.5) / (n + 1); per-step error at depth d
  e_{d,t} = 1 - s_{d,t}^(1 / d).
- alpha_d = -(OLS slope of ln e_{d,t} on ln N_t) per seed, for d = 2..8 (depth 1 is at ceiling, depths 9-10 near floor).
- Pooled across seeds: mean alpha_d and its se (sd / 2).
- HOMOGENEOUS iff every pooled alpha_d lies within 2 se of the pooled all-depth alpha (0.175) or the spread max - min < 0.1.
  Otherwise HETEROGENEOUS: report where alpha is largest (where rows teach most), as input to the 0138 pruning recipe.
