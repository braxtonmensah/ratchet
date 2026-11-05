# RESULT (exploratory, stored rows): 0128's policy amortises search. The same task needs less search as the model trains.

Read 2026-11-05 18:49 ET (PowerShell clock) by the Silicyte lead, under GATE_STORED_AMORT_1105.md (written 18:46 ET before any
quantity was computed; source amendment 18:48 ET, also before any quantity). Code amort_stored.py sha256 8d278e33...; gate sha256
812dfddb... (final text); output /N/scratch/bsmensah/silo/oneshot0136/amort_stored_1105.out. Stdlib, login node, no GPU.
Data: silicyte-0128 round_t.json fixed_rows (MEAS pool 29000, the same 300 tasks every round), rounds 0..10, s1 and FRONTIER_s2..s4.

## What was measured
bootseed0128.beam2 (B 4, 54 ops, fixed op order, last step exhaustive) logs `exec`, the number of op executions. For a solve of length
L >= 2, exec = 54 + 216 (L - 2) + 54 j + (o + 1), where j in 0..3 is the beam rank of the correct parent at the final step.
- Lever check: on 5,701 solved data-pool and frontier rows (which store the program), decoded L equals len(prog) on all 5,701; 0
  mismatches. The decoder is exact.

## Results (rule fixed in the gate)
| seed | Q1 slope per round | Q1 at rounds 0 -> 10 | solves at rounds 0 -> 10 | shortcut share 0 -> 10 |
|---|---|---|---|---|
| s1 | +0.02016 | 0.432 -> 0.625 | 65 -> 118 | 0.062 -> 0.127 |
| FRONTIER_s2 | +0.01795 | 0.523 -> 0.511 (0.636 at round 9) | 64 -> 125 | 0.047 -> 0.128 |
| FRONTIER_s3 | +0.02082 | 0.444 -> 0.563 | 63 -> 107 | 0.063 -> 0.121 |
| FRONTIER_s4 | +0.02176 | 0.392 -> 0.596 | 57 -> 114 | 0.018 -> 0.123 |

- Q1 = share of MEAS solves (L >= 2) whose correct parent was the TOP-ranked beam state at the last step, stratified by L with weights
  fixed from the pooled L distribution (L 2: 0.339, 3: 0.309, 4: 0.137, 5: 0.082, 6: 0.084, 7: 0.030, 8: 0.016, 9: 0.001, 10: 0.002).
  Mean slope +0.02017 per round, sd 0.00162, t 24.90 (crit 2.353), positive in all 4 seeds.
- Q2 = the same task solved early (rounds 0-2) and late (rounds 8-10) at the same length: late exec lower 96, higher 17, equal 183;
  one-sided sign-test p 7.4e-15. Per seed (lower, higher, equal): s1 26/0/48, s2 24/8/45, s3 25/5/47, s4 21/4/43.
- **GATE_STORED_AMORT: SIGNAL.**

## What this means, and what it does not
- The self-training loop distils search into the policy (the expert-iteration / AlphaZero mechanism, meaning (d) of his "one-shot"
  hunch): about 2 points per round more of the final-step choices are the policy's first choice, and fixed tasks need less search.
- It does NOT show compounding. j reflects only the last step's ranking, not greedy (beam 1) reach; the 0136 GPU test measures that.
- The likely reason 0128 does not accelerate despite this: its search budget is FIXED (B 4, max_steps 10 or D + 2). The search that
  the policy no longer needs is never reinvested at the frontier. A loop that turns amortised search into deeper search per GPU-second
  (shrink beam effort where the policy is sure, spend it on depth) is the concrete mechanism to test next; LADDER's fixed GPU-second
  budget is the closest design and should log this reinvestment.
- Shortcut share (solutions shorter than nominal depth) roughly doubles, 0.02-0.06 -> 0.12-0.13. Telemetry only.
- Curvature of Q1 over rounds was not computed (not in the gate).
