# GATE (exploratory, CPU): how far does a beam with NO learning reach, using only string similarity to the target?

Written 2026-11-05 20:03 ET (PowerShell clock) by the Silicyte lead, BEFORE the run. His question (19:58): "should we be doing
memorization, or other things?" This measures the floor a zero-learning difference-reduction rule sets.
- Ruler: open0129 frozen RULER_49100.json (300 tasks, depths 1..20 and 22..40), its registered rule max_steps = max(12, depth + 2),
  beam B 4 over the 54 ops (consol.OPN, run_prog), exhaustive check at every step exactly like bootseed0128.beam2; correct = all 4
  demo rows reached (v) and both test rows right (c).
- Only change from beam2: children are ranked by the mean over the 4 demo rows of difflib.SequenceMatcher(None, child, target).ratio()
  (greedy similarity, no accumulated log-prob, no model).
- d50 by the registered logistic fit (read_open0129.logistic_d50, verbatim).
- Reference: the base LLM policy P_0 (exp_n256) scored d50 3.059 on this ruler (0129 det.log, pass 1, 26 correct).
- Reading: if the no-learning d50 is >= 3.059, the learned policy at round 0 is no better than raw string similarity, and the job of
  the learner is to learn a better distance-to-goal (a rule that generalizes), not to memorize step patterns. If it is far below, the
  LLM prior adds real knowledge beyond similarity.
