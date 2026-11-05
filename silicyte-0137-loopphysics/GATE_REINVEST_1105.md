# GATE (exploratory, stored rows): how much would reinvesting saved search add to the feedback exponent?

Written 2026-11-05 18:58 ET (PowerShell clock) by the Silicyte lead, BEFORE any quantity below was computed.
Data: 0128 search_t.json rounds 0..10 of FRONTIER_s2..s4 (s1 keeps no search files). Stdlib, login node.

- For each seed and round, and separately for the frontier pool (tr, 200 tasks) and the data pool (dp, 300 tasks):
  cost per verified solve c_t = (sum of exec over all tasks of that pool) / (number with v true).
- beta = -(OLS slope of ln c_t on ln d50_t), with d50_t the registered d50_fixed of round t.
- Under a FIXED execution budget per round (instead of a fixed task count), rows per round would scale as d50^(gamma + beta). With
  0128's alpha 0.175 and gamma 1.19 (RESULT_LOOP_PHYSICS_1105), report alpha (1 + gamma + beta) per seed.
- Reading: REINVEST_HELPS iff the frontier beta > 0 in all 3 seeds; REINVEST_CROSSES iff alpha (1 + gamma + beta) > 1 in all 3 seeds.
  Otherwise reinvestment alone cannot make this loop accelerate, and alpha must rise.
