# OPEN0129_FIXES: one line per VERDICT_OPEN0129 item (CPU only, no jobs; loop code, generator, rulers and launch lines unchanged)

- Fix 1a, freeze XMIN: done before any scoring; frozen/RULER_<s>_XMIN.json = reduce_ub(max_iter=100) for all 1,200 tasks; shas 49100 d9017c43..., 49200 9fa48b03..., 49300 4e45b7d7..., 49400 48039fce..., index RULER_SHA256_XMIN.json 80b45abb... (freeze_xmin.py 45d47620).
- Fix 1b, reader fits the XMIN axis: read_open0129.py 950ad078 -> 7fa9481c; sha-checks XMIN, verbatim bootllm.logistic_d50 (200 / 200 equal).
- Fix 1c, two-axis rule: TAKEOFF-SHAPE iff t > 2.605 AND t^x > 2.605 (SATURATING likewise); common series; both t printed; self-test STEADY on linear, TAKEOFF on m 1.08.
- Fix 1d, sim re-run (xorshift128+, sim_open0129_x.js 472164a2, 2,000 x 4 seeds, two truths): two-axis FP 0.002 to 0.030 (verifier 0.015 to 0.048); nominal-only FP under the XMIN truth 0.037 to 0.146; power at onset 10, m 1.1, 0.83 to 0.99 (verifier 0.88 to 0.99). PREREG sec. 8a.
- Fix 1e, BUILD "no kink" corrected: capped bound hid uncapped slopes 0.93 (4..12) / 0.87 (12..20) / 0.69 (20..40); BUILD sec. 2 and sec. 9.1.
- Fix 2, hashes registered: reader md5 and XMIN shas in PREREG secs. 4 and 5; BUILD sec. 1 table and sec. 10.
- Fix 3a, fresh LoRA every round, weights do not carry over, scope of the label: PREREG sec. 2 and the "Scope of every label" paragraph in sec. 7.
- Fix 3b, d50 not comparable to 0128's d50_fixed or MEAS_DEEP: PREREG sec. 4 "Scale".
- Fix 3c, round 0 is the frozen-twin control for LEVEL only: PREREG sec. 11 (and the bridge is not a concurrent capped arm).
- Fix 3d, a round-15 takeoff is caught about 0.2 by R 20 (0.15 to 0.21 two-axis), 0.77 to 0.84 by R 25, 0.87 to 0.95 by R 30: PREREG sec. 8a.
- Fix 3e, PREREG 7.1 now matches the reader: any audit hit makes the whole label VOID.
- Compute note (item 5): realistic R corrected to 25 to 35 per seed in BUILD sec. 10.
- Final hashes: PREREG_OPEN0129_DRAFT.md sha256 b7fe10f08c6e146ca9c81f19c0005af90f876d9cc15f75379cacde67a373c1a8; BUILD_OPEN0129.md sha256 949adea5bfeee3c24746d95d1742577c28727efe47deb6273f17fb6dbb024272.
