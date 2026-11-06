# GATE (exploratory, stored rows): a natural experiment on the hindsight-format defect

Written 2026-11-05 19:51 ET (PowerShell clock) by the Silicyte lead, BEFORE the s1 row format below was looked at.
- Step 1: count, in 0128 seed 1's training rows (runs/s1/own.jsonl, legacy bootllm2 path), how many targets are character lists vs
  strings, and the same in FRONTIER_s2..s4 own_*.jsonl (all rounds 0..10).
- Step 2 (only if s1's hindsight targets are strings while the FRONTIER seeds' are character lists): compare s1's learning exponent
  with the three FRONTIER seeds' (already measured, ratchet silicyte-0137: s1 0.1626; FRONTIER 0.1923, 0.1425, 0.2030).
  FORMAT_MATTERS_LIKELY iff s1's alpha lies outside the FRONTIER range by more than 2 of its se (0.0236); FORMAT_SMALL otherwise.
  This is one seed against three, with other seed-knob differences (pool seeds, no torch seed), so it ranks the 0138 R3 lever only.
- If both formats are the same in all seeds: NO_NATURAL_EXPERIMENT, and only 0138 can test the fix.
