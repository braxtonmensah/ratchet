# GATE (exploratory, CPU): how far does a real search reach when it is handed the true intermediate states?

Written 2026-11-05 20:30 ET (PowerShell clock) by the Silicyte lead, BEFORE the run.
Ruler: open0129 frozen RULER_49100.json (300 tasks, depths 1-20 and 22-40, each with its reference program). Search: the zero-learning
similarity beam of GATE_NOLEARN_HEURISTIC_1105 (B 4, 54 ops, exhaustive target check, children ranked by difflib similarity).
Correct = the full program found reproduces all 4 demo rows and both test rows.
- ARM PLAIN: one search, max_steps max(12, d + 2). (Measured already: d50 4.854, 44/300; re-run here for an exact pairing.)
- ARM MID: the true midpoint state (reference program's first floor(d/2) ops applied to the 4 demo inputs) is given as an intermediate
  target; search start -> mid, then mid -> target, each hop with max_steps max(6, hop + 2); the two hop programs are concatenated and
  checked on the test rows.
- ARM HOP4: a true intermediate state every 4 reference steps; each hop searched in turn with max_steps max(6, hop + 2).
- Reported: d50 (bootllm.logistic_d50 verbatim) and solves per arm, and solves at depth >= 20.
- Reading: SUBGOALS_BUY_DEPTH iff HOP4 d50 >= 2 x PLAIN d50. This bounds what a learned subgoal proposer can buy: it can at best match
  the oracle; a learned proposer that is wrong costs the hop.
