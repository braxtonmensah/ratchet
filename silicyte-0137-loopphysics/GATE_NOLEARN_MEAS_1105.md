# GATE (exploratory, CPU): the zero-learning similarity beam on 0128's own MEAS ruler, vs 0128's trained policies

Written 2026-11-05 20:06 ET (PowerShell clock) by the Silicyte lead, BEFORE the run. Follows GATE_NOLEARN_HEURISTIC_1105 (on the 0129
ruler RULER_49100: similarity beam d50 4.854, 44/300, vs the LLM P_0 3.059, 26/300).
- Pool: BL.make_pool(WORLD, 29000, 300, 10) rebuilt with 0128's own lib (read-only). LEVER CHECK first: its tid list must equal the tids
  of 0128 s1 round_0.json fixed_rows in order; else STOP.
- Rule identical to 0128's MEAS: beam B 4 over the 54 ops, max 10 steps, exhaustive check, correct = v and c. Only the ranking differs
  (mean difflib ratio of child to target over the 4 demo rows; no model).
- d50 by bootllm.logistic_d50 verbatim. Compare with the registered d50_fixed of 0128's policies, rounds 0..10, all 4 seeds.
- Reading: SIMILARITY_BEATS_P10 iff the no-learning d50 is >= the mean round-10 d50_fixed of the 4 seeds (4.59); MATCHES_EARLY iff it
  lies between round 0 and round 10; BELOW_P0 iff it is under the round-0 mean (2.78).
