# ADDENDUM to SYNTHESIS_LADDER2_1105.md: a failed prediction refutes that test, not the idea. The pre-committed test ladder

Silicyte lead, 2026-11-05 21:20 ET (PowerShell clock), at his instruction (21:19): "I don't think it should kill the idea if it fails...
you have different ways to test the idea... don't give up at your first failure." Written before any of the deciding data exists
(0138's first-screen fits for R3 and R4S are not on disk; 0139 and 0140 have not run).

## What changes
- P1, P2 and P3 stay exactly as registered: each is scored by its rule and reported as PASS or FAIL. Nothing is softened after data.
- The sentence "A ratio under 1.2 refutes the premise that hop length sets alpha" is narrowed: a P1 FAIL refutes "short-hop rows raise
  alpha in the offline 0138 harness at these N, for Qwen3-8B with LoRA r16". It does not end LADDER-2.
- Every FAIL triggers a diagnosis before any conclusion, in this order:
  1. Did the lever reach the system? (lever_check markers; the row mix actually trained on; the prompts contain no "['").
  2. Was the test powered? (measured noise vs the MDE; an underpowered FAIL is reported as UNDERPOWERED, not as a negative.)
  3. Which component failed? (per-hop alpha, p_hop by hop length, subgoal-proposal accuracy, teacher-student gap, forgetting.)

## The ladder of independent tests of the core idea (short verified hops raise effective alpha enough to cross alpha (1 + gamma) = 1)
| # | test | what it isolates | runs on |
|---|---|---|---|
| T1 | 0138 R4S vs R_fix (P1) | offline: do short-hop rows teach more per row? | H5, running |
| T2 | 0138 R4 (every distance) and R4C | if T1 fails because 2-move rows lack the far-target context, relabelling at every distance keeps it | H5, tier 2 |
| T3 | per-distance alpha from 0129's own rounds as they accrue | the same estimator on a second, ceiling-free loop | stored rows, CPU |
| T4 | direct p_hop from search logs (success of the policy on 2-move hops, by round) | replaces the ratio-of-shares estimator with a direct one | stored rows, CPU |
| T5 | 0139 LADDER2 vs LADDER4 vs FLAT (P2) | the loop itself, with verified subgoals | holders after 0140's split |
| T6 | model size: the T1 contrast on Qwen3-1.7B and Qwen3-4B-Base | whether alpha's dependence on hop length is a capacity effect | shared card |
| T7 | 0142 MEMORY architecture | whether a learner that stores hop rules in fast weights changes alpha | build in progress |
| T8 | 0140 subtask-verified arm on real benchmarks (P3) | the same mechanism outside the toy world | H1-H5 from Nov 6 |

The idea is dropped only if T1, T3 and T4 all fail with the lever confirmed and power adequate, and T5 also fails. Each failure is
published with its diagnosis.

## Amendment to P3 (21:23 ET, before any 0140 data; 0140 has not run on a GPU)
The 0140 build gives every arm the same checker-verified multi-part task format (BUILD_GENERALIST0140.md); no one-question R-Zero-style
arm was built. P3 is therefore restated against the arms that exist: SELF (proposer and solver both train) keeps at least half of its
iteration-1 gain on the paired math average at iteration 4, while FROZEN_CHALLENGER (the solver trains on tasks from the untrained
proposer, compute matched) does not. Scored with the 0140 eval harness, paired, against the measured A/A noise. The SELF_OPD and
SEARCH_OPD arms are read under STOPRULE_SELF_OPD_1105.md and are not part of P3.
