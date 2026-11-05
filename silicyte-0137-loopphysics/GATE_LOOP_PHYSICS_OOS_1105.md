# GATE (exploratory): does the two-exponent law PREDICT? Fit rounds 0..5, forecast rounds 6..10

Written 2026-11-05 18:52 ET (PowerShell clock), after GATE_LOOP_PHYSICS_1105 read CONSISTENT and BEFORE this forecast was computed.
Data: the same 0128 round_t.json rows (s1, FRONTIER_s2..s4). Stdlib, login node.

- Per seed, fit on rounds 0..5 only: alpha and A from ln e(ii) on ln N; gamma and B from ln r on ln d50.
- Forecast rounds 6..10 by iterating the law from round 5's actual N: d50_t = ln 0.5 / ln(1 - A N_t^(-alpha)), N_{t+1} = N_t + B d50_t^gamma.
- Baseline: linear extrapolation of the actual d50 over rounds 0..5 (OLS line).
- Score: mean absolute error over rounds 6..10 against the actual registered d50_fixed, per seed and pooled (20 points).
- PREDICTS iff the law's pooled MAE is below the linear baseline's in at least 3 of 4 seeds and pooled. Otherwise the law fits but
  does not forecast, and it is reported as a description only.
