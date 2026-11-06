# GATE (exploratory, stored rows): does GUIDE's learning-progress curriculum raise the learning exponent alpha?

Written 2026-11-05 19:00 ET (PowerShell clock) by the Silicyte lead, BEFORE any quantity below was computed.
GUIDE (0128 amendment A2, exploratory) chooses each round's training depth window by its own measured learning progress: a data
selection lever. Its registered label (OLS slope of d50, GUIDE minus FRONTIER, at R) is NOT read here and its rules do not change.

- Pairs: GUIDE_s2 vs FRONTIER_s2, GUIDE_s3 vs FRONTIER_s3, on the SAME rounds 0..T, T = the last round GUIDE_sk has on disk (both arms
  cut at the same T; FRONTIER uses only rounds <= T).
- alpha and gamma exactly as GATE_LOOP_PHYSICS_1105 (geometric MLE e; N = rows trained on; rows/round = own_new + hindsight_new).
- LEVER_CANDIDATE iff alpha_GUIDE / alpha_FRONTIER >= 1.5 in both pairs. NO_LEVER iff the ratio is <= 1.1 in both. Otherwise UNCLEAR.
- With T about 5 the slope standard errors will be large; the result only ranks GUIDE against the alpha0138 screen, it decides nothing
  registered.
