# Power of compounding rules for the SELF-FT HELD design, with training-seed noise (2026-11-04 21:2x ET)

Script `sim_selfft_power.js` (main cells) and `sim_supp.js` (g1 = 0.10 cells), node, seed 20261104 / 20261105, 200 runs per
cell, 200 task-bootstrap resamples. Raw: `power_selfft_stdout.txt`, `power_selfft.json`.

## Why this extends testpower/sim_compounding_power.js

1. SELF-FT samples S = 64 programs per HELD task per round, so the outcome per task per round is a pass fraction, not one solve.
2. Every round retrains a LoRA adapter from base, so each adapter A_r carries its own random offset eps_r ~ N(0, sa) on the logit
   scale, shared by all 80 tasks. A bootstrap over tasks cannot see this noise. sa = 0 is the world the original sim assumed.

World: 80 HELD tasks, z_i ~ N(0, 1), per-sample pass prob sigmoid(theta_r + eps_r - 1.5 z_i), theta_0 set so the mean per-sample
pass rate is p0, gain g_r = g1 m^(r-1) logit per round (m = 1 is linear growth, NOT compounding). Statistic on
y_r = logit(mean over tasks of pass fraction under A_r), rounds r = 1..R (h_0 excluded).

## Results (share of 200 runs declaring compounding, one-sided alpha 0.05)

QUAD_TB = quadratic coefficient c with a task-bootstrap lower bound (the drafted rule). QUAD_T = same c, OLS t-test with R - 3 df.
GT_T = OLS slope of per-round gains, t-test.

| p0 | g1 | sa | R | rule | m=1.00 (false +) | 1.10 | 1.20 | 1.50 |
|---|---|---|---|---|---|---|---|---|
| 0.05 | 0.25 | 0 | 6 | QUAD_TB | 0.040 | 0.405 | 0.980 | 1.000 |
| 0.05 | 0.25 | 0.1 | 6 | QUAD_TB | **0.245** | 0.430 | 0.835 | 1.000 |
| 0.05 | 0.25 | 0.25 | 6 | QUAD_TB | **0.380** | 0.560 | 0.680 | 1.000 |
| 0.15 | 0.25 | 0.25 | 6 | QUAD_TB | **0.410** | 0.490 | 0.710 | 1.000 |
| 0.10 | 0.10 | 0.1 | 10 | QUAD_TB | **0.205** | 0.730 | 1.000 | 1.000 |
| 0.05 | 0.25 | 0.1 | 6 | QUAD_T | 0.065 | 0.100 | 0.430 | 1.000 |
| 0.10 | 0.10 | 0.1 | 6 | QUAD_T | 0.045 | 0.090 | 0.130 | 0.885 |
| 0.10 | 0.10 | 0.1 | 8 | QUAD_T | 0.065 | 0.185 | 0.620 | 1.000 |
| 0.10 | 0.10 | 0.1 | 10 | QUAD_T | 0.055 | 0.340 | **0.975** | 1.000 |
| 0.05 | 0.25 | 0.1 | 10 | QUAD_T | 0.030 | 0.795 | 1.000 | 1.000 |
| 0.05 | 0.25 | 0.25 | 10 | QUAD_T | 0.030 | 0.330 | 0.995 | 0.995 |
| 0.15 | 0.25 | 0.25 | 10 | QUAD_T | 0.055 | 0.405 | 1.000 | 0.685 |
| 0.15 | 0.25 | 0.1 | 10 | QUAD_T | 0.025 | 0.965 | 1.000 | 0.725 |

## What it decides

1. **The task-bootstrap convexity rule is invalid for a retrained-adapter loop.** With adapter noise of 0.1 logit it calls linear
   growth compounding 15.5 to 24.5% of the time, 37.5 to 41% at 0.25. Any SELF-FT rule must carry the round-level noise.
2. **QUAD_T (OLS t on the round means, df R - 3) holds 1.5 to 6.5% false positives in every cell** (200 runs: SE about 0.016).
3. **R is the power lever, not n or S.** QUAD_T at m = 1.2: 0.13 at R = 6, 0.62 at R = 8, 0.975 at R = 10 (p0 0.10, g1 0.10,
   sa 0.1); at R = 10 it is 0.975 to 1.000 in every world tested. m = 1.1 stays at 0.33 to 0.97 even at R = 10.
4. Saturation still bites at m = 1.5 over 10 rounds when p0 = 0.15 (0.685 to 0.725): runaway growth there reads as a ceiling,
   and the level read carries it.
5. GT_T (gain-trend slope) is valid but weaker than QUAD_T in every cell; RATIO is not carried forward (0 power, R7).

Registered consequence (SELF-FT amendment): R = 10 rounds (R_min 8 for a non-UNDERPOWERED read), S = 64 per task per round,
shape rule QUAD_T on logit HELD means over rounds 1..R. World parameters g1 and sa are unmeasured: sa is read from the round-1
two-seed A/A, and the achieved power at the measured values is printed in RESULT.md before any label.

## CORRECTION (2026-11-04 21:53 ET)

This sim drew the training noise as an independent offset per round. The independent sim verdict (ratchet/testpower/VERDICT_SIM.md,
sec. 2c) draws it as a random walk (each adapter samples the next round's data, so a lucky round persists), which is the better
model for a loop whose rows come from its own last adapter. Under the random walk a single trajectory cannot be tested at S = 64 by
any rule: false compounding 0.18 to 0.51 for one seed. Finding 1 above (task bootstrap invalid) stands. Findings 2 and 3 (QUAD_T valid,
R = 10 single seed sufficient) are withdrawn as gate inputs. The registered design is now K = 4 seeds x R = 8 with a seed-level
Rasch curvature t-test (AMENDMENT_SELFFT_FINAL.md, A1).

## CORRECTION 2 (2026-11-05 06:27 ET): the stated range and the rule's name

- Finding 1 above quoted "15.5 to 24.5% at sa 0.1, 37.5 to 41% at sa 0.25". Over all 9 simulated cells with seed noise (power_selfft.json,
  m = 1.0, 200 runs each, Monte Carlo SE about 1.8 to 3.5 points), QUAD_TB's false-compounding rate is **0.070 to 0.410**: the table above
  omitted the R = 10 cells (0.070 at p0 0.05, sa 0.1; 0.175 at p0 0.15, sa 0.1). The 0.070 cell is not clearly above 0.05; the other 8 are
  (0.155 to 0.410).
- QUAD_TB (convexity with a task bootstrap) is the R7 candidate rule, not silicyte-0127's drafted rule. The 0127 draft's HELD read was an OLS
  slope with a task-cluster bootstrap (AMENDMENT_1_SELF_FT_DRAFT.md:216-217), which fires on any improvement (R7: 0.995 to 1.000 on linear
  growth); its COMPOUNDS gate also required McNemar wins over ONESHOT and FROZEN8B (line 232). Any sentence that this sim showed "the drafted
  rule would have produced a fake positive" overstates it: it shows a false-positive RATE for the R7 convexity rule.
- Unchanged: single-trajectory task-bootstrap rules are invalid under training-seed noise; the independent VERDICT_SIM.md (random-walk noise)
  gives 0.150 to 0.327 (logit task bootstrap) and 0.487 to 0.690 (probability scale) at S = 64 (lines 68 to 71). The registered designs use
  seed-level tests (0127 A1; 0128).
