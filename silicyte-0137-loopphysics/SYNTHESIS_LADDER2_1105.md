# SYNTHESIS: every method's bottleneck is another method's fix. The combination the law says should cross into acceleration

Silicyte lead, 2026-11-05 21:14 ET (PowerShell clock). Built from our measurements (ratchet silicyte-0137, 0136) and three literature
surveys (generalist0140/RESEARCH_SELFPLAY_1105.md, RESEARCH_KNOWLEDGE_1105.md, RESEARCH_DISTILL_1105.md, RESEARCH_FRONTIER_1105.md).
The predictions in the last section are registered now, before any of the tests that decide them has produced data.

## 1. The bottleneck matrix
| method or finding | what it does well | where it fails (measured or reported) | what fixes that failure |
|---|---|---|---|
| Self-training on own verified solutions (0128, ReST, STaR) | real gains, iteration 1 largest | alpha 0.175, alpha(1 + gamma) 0.38 < 1: decelerates; all published loops saturate after iteration 1 | raise effective alpha (rows that teach more per row) |
| Learning per depth (0128) | short decisions learn fast: alpha 0.637 at 2 moves from the goal | alpha about 1.2 / d: deep tasks are memorized case by case; far decisions learn at 0.157 | confine all learning to SHORT hops (decomposition) |
| Subgoal decomposition (kSubS, DeepSeek-Prover-V2 lemmas) | turns far decisions into near ones; oracle midpoint 1.67x on stored rows | real search with TRUE subgoals every 4 steps only 1.53x: hops multiply (0.7 per 4-step hop) | make hops very short (2) and near-perfect, and verify each hop |
| Explorer-Zero (2610.19868): proposer probes the checker, subtasks each rewarded | kept rising where the no-subtask variant flattened at about 60 steps | needs a checker per subtask | our world has an exact executor; 0140 has executors and answer checkers |
| On-policy distillation (Thinking Machines, Qwen3, FM-Pochi) | 10-100x denser signal per sample | shifts the law's A, not alpha; self-distillation at chance on AIME (AUC 0.505, 2608.09263); forgets more (2607.01763) | distil only on VERIFIED hops; keep a teacher whose lead re-opens (search) |
| Search-as-teacher (AlphaZero, rStar-Math) | the teacher's lead re-opens each iteration because search scales with the policy | expensive; 0128 never spent the search it saved | reinvest amortised search (0128: same task needs less search, 96 vs 17) into deeper ladders |
| Amortisation (0136 stored rows) | top choice right +0.020 per round, 4 of 4 seeds | saved search is never reinvested; frontier cost per solve stays flat | spend the saving on more verified short hops per round (raises gamma) |
| Fine-tuning for knowledge (SEAL, raw FT) | self-written notes 32.7 -> 47.0 no-context SQuAD | forgetting (65.5 -> 53.4); facts from separate documents do not combine | varied restatements (46% vs 1% recall, 2607.11020), replay, weight averaging (fourth_law M6 soups PASS p 0.039) |
| A trivial similarity rule (0137) | matches the self-trained 8B with zero learning | it is a fixed distance measure; it cannot improve | make the learned policy learn a DISTANCE (which hop gets closer), not a lookup of whole tasks |

## 2. The combination (LADDER-2)
1. Every training row is a verified hop of at most 2 moves (state, intermediate target, op), taken from the model's own verified
   solutions by hindsight at every intermediate distance. No row asks a far decision.
2. Deep tasks are solved by proposing intermediate states and searching 2-move hops between them; every hop and every proposed
   intermediate state is checked by the executor (Explorer-Zero's checker probing), so a wrong proposal costs a probe, not a row.
3. The teacher signal on those hops is dense and comes from search (the search-verified hop distribution), so the teacher's lead
   re-opens each round; distillation is applied only where the hop was verified.
4. Search saved by amortisation is spent on more hops at the frontier each round (raising gamma).
5. Retention: replay with varied restatements, and averaging of round checkpoints.

## 3. The law's prediction for it (computed from measured inputs only; ladder2_predict.py, output ladder2_predict_1105.out)
| regime | alpha used (measured) | hop | alpha (1 + gamma), gamma 1.19 | predicted shape |
|---|---|---|---|---|
| 0128 as run | 0.175 (pooled) | 1-step rows of whole tasks | 0.38 | decelerates |
| 3-move hops | 0.294 (k = 3) | 3 | 0.64 | decelerates |
| 2-4 move band | 0.378 | 2 | 0.83 | decelerates |
| 2-move ladder | 0.637 (k = 2) | 2 | 1.40 | ACCELERATES |
Caveats: the reach magnitudes from this simulation are not meaningful (the error scale A was fitted on whole-task per-step error, not
per-hop error, so the 2-move curve diverges); only the side of the boundary is the claim. At the lower 90% bound of alpha at k = 2
(0.530) and of gamma (0.86), alpha (1 + gamma) is about 0.99: the 2-move ladder sits near the boundary, not far past it.

## 4. Registered predictions (falsifiable; written before the deciding data)
- P1 (0138 ALPHA, first screen, running now on H5): the learning exponent with short-hop rows (R4S) exceeds the format-fixed whole-row
  recipe (R_fix) by a ratio between 1.5 and 3.6 (law: near band 0.378 / pooled 0.175 = 2.2). A ratio under 1.2 refutes the premise that
  hop length sets alpha.
- P2 (0139 SUBGOAL): with hops capped at 2 moves and every hop verified, the per-hop alpha is at least 0.5 and the law's early read
  gives alpha (1 + gamma) > 1; with hops of 4 moves it gives < 1. If the 2-move arm reads < 1, the ladder premise fails.
- P3 (0140 GENERALIST): the subtask-verified (Explorer-Zero-style) arm's per-iteration gain on the math average does not fall below half
  of its iteration-1 gain by iteration 4, while the R-Zero-style / verifier-only arm does. Scored with the 0140 eval harness, paired,
  against its measured A/A noise.
