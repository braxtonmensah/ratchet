# A4_FIXES: what changed for each item of VERDICT_A4_0128.md (NO-GO, 09:40 ET), 2026-11-05 ET

Applied per the coordinator's instructions, which settle three choices the verdict left open: pool seeds 39000 + 100k for every k,
including s1; a stop rule on data-pool d50 >= 9 only; the critical value 2.605. CPU only. No GPU, no job, no registered file touched.

- WHY 1 (shared deep pool inflates the L false-positive rate): now one pool per seed, MEAS_DEEP_k = frozen/MEAS_DEEP_<39000 + 100k>.json, k = 1..4 (39100 for s1, 39200, 39300, 39400). They are built by build_meas_deep_k.py with the same law as before (depths 1..20, 6 per depth). sha256: 39100 34a86653...00cb4, 39200 0beed047...283e55, 39300 c5d9f77e...5d6f, 39400 5e9a9184...5fca (full values in BUILD 0.1). The overlap of each pool is in BUILD 0.2. score_deep.py picks the pool from the run name and checks its sha (GUIDE_sk uses seed k's pool). read_0128_ext.py refuses any reading made on a different pool. frozen/MEAS_DEEP_39000.json is kept, marked SUPERSEDED (frozen/MEAS_DEEP_39000.SUPERSEDED.txt), and no code scores it.
- WHY 2 (the loop's own depth-10 ceiling): new stop rule. R*_k is the first round whose summary.d50 (data pool) is >= 9, or R_ext otherwise. L uses rounds 11..R*_k. A seed with R*_k < 15 is excluded. Fewer than 3 seeds left gives UNDERPOWERED-EXT. Labels are worded "before the loop's 10-step search ceiling (data-pool d50 < 9)", and NO-TAKEOFF-BY-R is renamed NO-TAKEOFF-BEFORE-CEILING. The honest power is in BUILD 0.5 (sim_late_takeoff_v2.js).
- WHY 3 (crit rule rests on an RNG artifact): crit fixed at 2.605 (T04[K - 1]; t(3) one-sided 0.04 at K = 4, exact FP 0.040 under the Gaussian null), the same as A1. Both data-dependent alpha rules and the 0.05-to-0.062 / 0.034-to-0.054 FP figures are withdrawn. The new sim uses xorshift128+ (splitmix64 seeds), checked against a BigInt reference at start-up, instead of the LCG. The reader prints the crit it uses.
- Item 1 (MEAS_DEEP as described): PASS; superseded by the per-seed pools, which went through the same overlap checks again (BUILD section 3).
- Item 2 (score_deep.py): PASS. The only change is per-seed pool selection, with pool_seed and pool_sha256 recorded in every output. Selftest re-run on all 4 pools.
- Item 3 (continuation): PASS, no change. Optional fix 8 (s1 at t_to 29, then score_deep on P_30) is noted in BUILD section 6 as the lead's choice.
- Item 4a (crit hardcoded): crit is still T04[df] from the registered table, now printed with every read.
- Item 4b (K can shrink silently): exclusions are explicit and printed per seed (R*_k < 15, or a gap in deep rounds 0..R*_k). K < 3 gives UNDERPOWERED-EXT. K = 3 uses T04[2] = 3.320.
- Item 4c (gains across missing rounds): deep LEVEL uses only each seed's contiguous deep rounds from 0.
- Item 4d (label without gates): --final requires --gates logs containing DETERMINISM MATCH, CONTROL PASS, POST OK for every run, and an overlap_actual ACTUAL_TOTAL with all zeros. Otherwise the label is refused.
- Item 4e / fix 5 (m_hat_geo unusable): replaced by the per-seed rate ratio slope_11_R* / slope_0_10, with a 95% t interval across seeds.
- Item 5 (power claim): replaced by the v2 sim table in BUILD 0.5: per-seed pools, task effects (su 1.3, beta 1.75), the stop rule, a ceiling at 10 to 11, and xorshift128+.
- Item 6 (compute): BUILD's "longer than the holders" is withdrawn. The verifier's projection (R 28 to 33 inside the holders) is quoted instead.
- Item 7 / fix 7 (contamination): a hit in seed k's own pool in training at round u voids seed k's deep readings for every t > u. overlap_actual.py now checks every round against all four pools, and the reader refuses a label on any hit.
- Fix 4 (K rule): applied as above, with the coordinator's threshold of at least 5 late rounds (R*_k >= 15).
- Fix 6 (new reader): implemented in place in ext/read_0128_ext.py (not a registered file; new md5 in BUILD section 1).
- Mechanics (no verifier item; added at 13:2x ET at the coordinator's request): ext/continue_k.sh <k> <holder> is the ready round-10 continuation for seeds 2 to 4. It runs all checks, the 3-file move and the launch. Not run. extend_0128.py gained one early exit when round 10 is not reached yet; its new md5 is 635d26e2, pinned in continue_k.sh. Seed 1 and GUIDE_s2 / GUIDE_s3 already run with t_to 30 and need no move.
- Exact audit (fix 7 basis), 13:23 ET: 37 completed rounds across 6 runs, 18,500 real-pool tasks, 0 hits against all four per-seed pools (overlap_actual_1323.log).
