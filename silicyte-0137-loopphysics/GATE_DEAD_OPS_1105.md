# GATE (exploratory, stored files): are 12 of the world's 54 ops dead weight for search?

Written 2026-11-05 19:57 ET (PowerShell clock) by the Silicyte lead, BEFORE any op count below was computed.
Atoms (measured): the world has 54 ops (consol_v1 world.json n_ops 54); 0128's verified programs use 42 distinct ops (audit part 2);
beam2 expands all 54 ops at every step (exec counts 54 per expanded state).
- Count op frequencies in (a) the reference programs of the four frozen 0129 rulers (open0129/frozen/RULER_49x00.json) and (b) every
  verified program in 0128's search files (FRONTIER_s2..s4, dp and tr, rounds 0..10).
- DEAD_OPS iff some ops appear in NEITHER (a) nor (b); report them and the share of each beam step's executions they consume.
- If the dead ops are generator-impossible (never in any reference program of a ruler built by the open generator), removing them from
  the action space is a pure search-cost cut for future loops (0139 SUBGOAL, 0133 LADDER) that cannot change what is reachable on
  these rulers. If they appear in references but never in solutions, they are HARD_OPS (a learning target), not dead.
