# GATE (exploratory, stored rows): the ceiling on what perfect midpoint subgoals could buy

Written 2026-11-05 19:24 ET (PowerShell clock) by the Silicyte lead, BEFORE any quantity below was computed.
Data: 0128 round_0..10.json fixed_rows, pooled over s1 and FRONTIER_s2..s4 (120 MEAS tasks per depth per round). Stdlib, login node.

- Oracle subgoal at the exact midpoint, hops independent: a depth-d task (d even) succeeds with s_{d/2}^2 instead of s_d.
- Report, per round 0, 5, 10: s_d and s_{d/2}^2 for d = 4, 6, 8, 10; and the depth where the oracle curve s_{d/2}^2 crosses 0.5
  (linear interpolation over even d) against the actual d50 crossing of s_d.
- WORTH_BUILDING iff at round 10 the oracle crossing is at least 1.5x the actual crossing. Otherwise the subgoal lever is small in this
  world even when perfect, and the 0138 subgoal recipe is deprioritised.
- Caveat stated now: real subgoals must be proposed by the model, so this is an upper bound, and hops are not truly independent.
