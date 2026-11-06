# RESULT (exploratory, CPU): a beam with NO learning, ranking moves by plain string similarity, matches 0128's self-trained 8B model

Silicyte lead, 2026-11-05 20:10 ET (PowerShell clock). Gates written before each run: GATE_NOLEARN_HEURISTIC_1105.md (20:03 ET) and
GATE_NOLEARN_MEAS_1105.md (20:06 ET). Code nolearn.py (30e54ffa), nolearn_meas.py (1208bba3). Stdlib plus 0128's world lib, read-only.

## The rule
Exactly 0128's beam (B 4, all 54 ops expanded, exhaustive target check at every step, correct = all demo rows reached and both test
rows right), except that children are ranked by the mean over the 4 demo rows of difflib.SequenceMatcher(child, target).ratio().
No model, no training, no data.

## Results
| ruler | rule | zero-learning similarity beam | the LLM policy |
|---|---|---|---|
| 0129 RULER_49100 (300 tasks, depths 1-40) | max_steps max(12, d + 2) | d50 4.854, 44 / 300 | P_0 (exp_n256): d50 3.059, 26 / 300 (0129 det.log) |
| 0128 MEAS 29000 (300 tasks, depths 1-10; tids verified equal to 0128's fixed_rows in order) | max 10 steps | d50 4.871, 125 / 300 | round 0 mean 2.78; round 10: 4.68 / 4.90 / 4.30 / 4.47 (mean 4.59) |

Per depth on MEAS (similarity beam): 1: 26/26, 2: 24/25, 3: 23/28, 4: 18/33, 5: 4/28, 6: 13/27, 7: 9/37, 8: 4/37, 9: 0/26, 10: 4/33.
**GATE_NOLEARN_MEAS: SIMILARITY_BEATS_P10** (4.871 >= the round-10 mean 4.59; 3 of 4 seeds are below it, FRONTIER_s2 at 4.90 is level).

## What it means
- At round 0 the 8B LLM's guidance is worse than a one-line similarity rule (3.06 vs 4.85 on the 0129 ruler; 2.78 vs 4.87 on MEAS).
- Ten rounds of self-training raise the LLM from below that rule to about level with it. Most of what the 0128 loop "learned" is
  something a trivial, general distance measure gives for free; it learned it slowly, per pattern (alpha about 1.2 / depth).
- Any self-improvement claim in this world must be measured against this baseline, which 0128, 0129, 0133 and SELFMOD never were.
- The lever is not more memorization. It is a learner that represents the rule (a distance to the goal, the effect of each op, subgoals)
  and reuses it everywhere; and, for his real goal (smarter in all domains), a test outside this toy world.

## Addendum 20:43 ET: handing a real search the TRUE intermediate states buys 1.5x, and hop reliability is the limit (GATE_SUBGOAL_SEARCH_1105.md)
Same zero-learning similarity beam on RULER_49100 (300 tasks, depths 1-40), oracle intermediate states from each reference program:
| arm | d50 | solved / 300 | solved at depth >= 20 |
|---|---|---|---|
| PLAIN (one search, max(12, d + 2) steps) | 4.854 | 44 | 0 |
| MID (true midpoint given) | 6.587 | 61 | 0 |
| HOP4 (true state every 4 steps) | 7.418 | 73 | 1 |
- **GATE: LIMITED** (HOP4 / PLAIN = 1.53, under the 2x bar). Depth 13: 1 / 1 / 7 of 10; depths 14-40: almost all 0 even with oracle states.
- Why: with oracle subgoals every 4 steps, a depth-d task needs d/4 hops in a row; each 4-step hop succeeds about 0.7 for this search,
  so 0.7^5 = 0.17 at depth 20 and 0.03 at depth 40. Reach with subgoals is about hop_length x ln 0.5 / ln p_hop.
- Design consequence (0139 SUBGOAL): what decides reach is per-hop reliability, not the subgoal alone. At p_hop 0.98 for 4-step hops the
  same arithmetic gives about 137 steps; at 0.9, about 26. A learner must make short hops near-perfect (short-distance steps learn
  fastest: alpha 0.637 at 2 hops) and the loop must measure p_hop directly.
