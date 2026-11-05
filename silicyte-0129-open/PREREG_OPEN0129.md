# PREREG_OPEN0129_DRAFT: silicyte-0129 OPEN. Does the 0128 loop take off once its depth ceiling is gone?

Draft of 2026-11-05 13:49 ET (PowerShell clock), by the 0129 builder, before any 0129 model call. To be registered unchanged after an
independent verifier's GO and before the first OPEN round json exists. Every rule below is fixed now; nothing in it reads 0129 data.
Build report: BUILD_OPEN0129.md. Revised after VERDICT_OPEN0129 (NO-GO): second ruler axis (secs. 4, 5, 8) and the text of
fix 3 (secs. 2, 4, 7, 8, 11); OPEN0129_FIXES.md lists each item. The loop code, generator and rulers are unchanged.

## 1. Question

silicyte-0128 (PREREG_BOOTSEED_V1 + A1 to A4) trains Qwen3-8B's LoRA on its own verified beam solutions of consol_v1 depth tasks.
VERDICT_A4_0128 found its ceiling by construction: training search stops at 10 steps, data pools hold depths 1..10, and F1's
dmin = floor(d50) starves new rows once the data-pool d50 nears 10 to 11. 0129 keeps the 0128 loop, seeds and frontier recipe and
removes only that ceiling (his words: "just give it infinite puzzles and have it keep figuring that shit out"). The question is the
shape of the reach curve on a fixed ruler that does not move with the loop: does the per-round gain rise (TAKEOFF), stay flat
(STEADY), or fall (SATURATING)?

## 2. The loop (code: open0129.py md5 4e46988a5d47448cbbb63c13d82b2b7b, opengen.py md5 8915e834f9321a85f4db18e9d35d46ce, run_open0129.sh md5 600bf85dffcfeda5a138320b24f26173)

bootseed0128.py's own functions run unchanged (imported from its syntax tree after its md5 c54e21d2 is asserted): beam2, solve2,
frontier_examples (F1 + A1 1:1 hindsight), f3_window (F3), train (reachlaw.train, r16, lr 2e-4, one pass over seed256 + own_0..own_t),
plus the file helpers. **Each round fits a fresh LoRA from the base model** (reachlaw.train initialises a new adapter every call) on
seed256 plus all own rows so far (replay-all); weights do not carry over between rounds. World consol_v1, Qwen3-8B, ident.Scorer, beam B 4, 300 data tasks and 200 frontier tasks per round. The complete
list of differences (open0129.py docstring O1 to O10):
- O1 pools come from opengen.make_task_open (same consol_v1 family: same ops, Zipf weights, inputs and make_task filters; any depth)
  inside bootllm.make_pool's loop (same rng, tid, depth draw, held skip).
- O2 data pool depths 1..D_t, D_0 = 10, D_t = max(10, ceil(d50eff_{t-1}) + 6).
- O3 max_steps = D_t + 2 for the data-pool and frontier searches; the F3 window has no upper clip.
- O4 d50eff = data-pool d50 clamped to [1, D_t + 2]; a failed fit gives D_t if half the pool is correct, else 1.
- O5 the ruler (sec. 4) is scored by a side process on every final P_t; MEAS 29000 is not scored in-loop.
- O6 pool tasks with an input of any ruler, MEAS 29000 or MEAS_DEEP_39x00 are skipped at build and counted.
- O7 every round trains (no scored-only last round). O8 a 60-task start check replaces the 40-minute canonical check.
- O9 P_0^k (k >= 2) is copied from 0128's FRONTIER_s<k>/P_0. O10 telemetry over depths 1..D_t.

## 3. Seeds

K = 4: seed k = 1 follows bootllm2 conventions (pools 9000 + t / 19000 + t, P_0 = exp_n256, no pre-shuffle, no torch seed); k = 2..4 use
the 0128 A1.1 knob (pools 9000 + 100 k + t / 19000 + 100 k + t, pre-shuffle and torch.manual_seed 1000 k + t + 1, hindsight
Random(1000003 k + len(rows)), P_0^k = 0128's). One H100 per seed.

## 4. The ruler (frozen before any 0129 policy exists)

RULER_k = frozen/RULER_<49000 + 100 k>.json, one per seed (VERDICT_A4_0128 WHY 1: a pool shared by all seeds inflates the seed-level
test). 300 tasks each: 10 per depth at depths 1..20 and at the even depths 22..40 (deep-depth subsampling: half the depths above 20,
where every early policy fails and each failure costs the most beam calls). Built by build_ruler.py from opengen; each task's
reference program has exactly its depth and reproduces all 6 pairs under consol.run_prog. Never trained on; excluded from every pool
(O6). Scored with beam B 4 and per-task max_steps max(12, depth + 2), fixed for all rounds, so the ruler cannot move with D_t.
sha256: 49100 8316fee93053531d929c1051e70b8b472d7edfb8e53631819ec4a4ce11d507b0, 49200 bf4a9484aad4b990b7a4bfdd4e140799265dba6f5a25096dc36ff3a5e9ede64a, 49300 0bfeb1c3d971931fa703a902597b473f9549c5667a3e6d5c9db20c7cd5158027, 49400 2eaf9849303b338e9af9d8a980bf902d11f2ca1c2f4f06bc34be631f6b12e15e (frozen/RULER_SHA256.json; open0129.py exits 9 on a mismatch).
**Second axis (XMIN), frozen before any 0129 policy is scored.** For every ruler task, XMIN = opengen.reduce_ub(task, max_iter=100),
the uncapped greedy upper bound on its minimal program length on the 4 demos (freeze_xmin.py). frozen/RULER_<s>_XMIN.json sha256:
49100 d9017c430c0cbe6f2463edf061e25c0f65114a2acdaff5c4246d3a48cb2734b7, 49200 9fa48b03990b665c8f12c1cee4a1aa223f8b22dbbfcdcbc6652c9c1eef7fa9eb,
49300 4e45b7d71ba207ad46e69bfffc8f593a6e2e4215816fff78f6af468adce60acb, 49400 48039fce6483af769e06ee56f3d5aee59e95228fa8eccee46b96935b84c9b55e
(frozen/RULER_SHA256_XMIN.json sha256 80b45abbebc7c7b78e8c00b5b74d10e11a7e8ed3c3029e87b3cfbafd35324729; the reader exits 9 on a mismatch).
Mean XMIN rises 0.93 per nominal depth over 4..12, 0.87 over 12..20 and 0.69 over 20..40 (32.6 at depth 40): nominal depth gets
cheaper per step past about 12, a warp shared by all four rulers, which is why the shape test is required on both axes (sec. 5).
**Scale.** The open generator's outputs are shorter than make_task's from depth 8 (29.7 vs 39.1 characters at depth 10). 0129's d50 is
on its own scale, not comparable to 0128's d50_fixed (pool 29000) or to MEAS_DEEP readings. Levels are compared only through the
optional bridge (sec. 11).
Per-depth count from the noise target: round-to-round sd(d50) <= 0.30 for reach up to depth 20 under both task-effect
calibrations of VERDICT_A4_0128 (sim_open0129_part1.json: 10 per depth gives 0.22 to 0.30; 8 gives 0.24 to 0.34).

## 5. Quantities and rule

y_{k,t} = ruler_t.json summary.d50 (bootllm.summarize on RULER_k) of P_t, t = 0, 1, ... R_k contiguous.
- **R_k** = the last round of the contiguous series, cut before the first round whose d50 is None, before the first round whose
  d50 exceeds 34 (ruler saturation), and at the deadline: P_t counts only if round_{t-1}.json has an mtime before the cutoff
  (the deadline, 2026-11-10 23:59 ET; read_open0129.py CUTOFF).
- **Second-axis series.** y^x_{k,t} = bootllm.logistic_d50 of the same ruler rows with each row's depth replaced by XMIN[tid]. The
  series is common to both axes: R_k is also cut before the first round whose y^x is None.
- **PRIMARY, on both axes.** h_k = floor(R_k / 2); delta_k = OLS slope of y over rounds h_k..R_k minus OLS slope over rounds 0..h_k;
  t = mean(delta) / (sd(delta) / sqrt(4)), df 3, one-sided; delta^x_k and t^x the same on y^x. **TAKEOFF-SHAPE iff t > 2.605 AND
  t^x > 2.605** (alpha 0.04 each). **SATURATING-SHAPE iff t < -2.605 AND t^x < -2.605.** Both t values are printed with every read.
  Basis: with per-seed rulers, delta_k is independent across seeds; requiring both axes keeps the false-positive rate under 0.05
  whether the truth is linear in nominal depth or in minimal length (sec. 8).
- **SECONDARY.** (a) c_k = OLS quadratic coefficient of y on rounds 0..R_k; same t and 2.605. (b) LEVEL: g_k = (y_{R_k} - y_0) / R_k;
  LEVEL passes iff mean(g) - 2.353 sd(g) / 2 > 0 (one-sided 95%, as read_0128.py).
- **m_hat.** Per seed, least squares of y_t = a + g (m^t - 1) / (m - 1) (y_t = a + g t at m = 1) profiled over m in [0.80, 1.30];
  reported as exp(mean log m_hat) with the t(3) 95% interval on log m_hat across seeds. Reported with every label, never a gate.
- Printed with every read: per-seed ruler curves, D_t, max_steps, data d50, d50eff, dmin, window, own_new, hindsight_new,
  train_examples, own_depth_max, search_s, train_s, round_s.
Reader: read_open0129.py md5 7fa9481ce0012cd7c0e5b08a348e32d2 (read / audit / compare; the second axis reads the XMIN files above).

## 6. Stop rules

Every seed runs from round 0 until its holder ends or the deadline (2026-11-10 23:59 ET), whichever is first, relaunched with the same
command in any new holder (resume is per round). No seed is stopped on its data. Rulers missing at the deadline for final P_t are
scored afterwards from the saved adapters (measurement only) and are read only if the adapter's round json predates the deadline.
The round reached per seed (R_k) is reported with the label.

## 7. Labels, in order

1. **VOID**: a code or ruler hash differs from sec. 2 / 4; a START_CHECK fails; the GPU determinism compare (one adapter scored on its
   ruler twice) is not "RULER_DETERMINISM MATCH rows_equal 300 of 300"; or the audit finds a ruler input in any seed's training pools
   (read_open0129.py audit must print AUDIT_TOTAL 0), which makes the whole label VOID (read_open0129.py --final).
2. **UNDERPOWERED**: fewer than 4 seeds with R_k >= 12.
3. **TAKEOFF**: TAKEOFF-SHAPE (both axes) and LEVEL. Worded "the per-round gain rose within R_k rounds", with m_hat and its CI.
4. **SATURATING**: SATURATING-SHAPE (both axes) and LEVEL, with m_hat and its CI.
5. **STEADY**: LEVEL only. Worded "no change in the gain detected within R_k rounds", with the power for that R from sec. 8.
6. **NULL**: LEVEL fails.
The secondary quadratic test is printed and never changes the label.

**Scope of every label.** The ruler d50 of this loop in consol_v1 only. The recipe fits a fresh LoRA from the base model every round,
on seed256 plus all own rows (replay-all). Weights do not carry over between rounds (RESULT_LORA_ANATOMY_S1: consecutive dW cosine
0.045 to 0.087), so a rising gain compounds through the accumulated dataset and the loop's search budget (max_steps = D_t + 2), not
through weights. The label does not attribute the shape to removing the ceiling (there is no concurrent capped arm), and it does not
generalise beyond consol_v1. Replay-all training is also why late rounds slow (train_s about 10,000 s per round by round 30).

## 8. False positives and power

### 8a. Registered rule: shape on both axes (sim_open0129_x.js, fix 1d of VERDICT_OPEN0129)

TAKEOFF label rate (shape and LEVEL), cells "tau 1.2, beta 2.0 / tau 1.35, beta 1.5", 2,000 runs of 4 seeds each, s_eta 0. Each sim
ruler task's minimal length is drawn from the frozen XMIN values of the real rulers at its depth. Truth "nominal": difficulty is
linear in nominal depth. Truth "xmin": difficulty is linear in minimal length (the measured warp). RNG xorshift128+; reader rules
exactly (the series stops at the first None on either axis or a nominal d50 > 34; one 41-round trajectory per seed, truncated at R).

| truth | scenario | rule | R 20 | R 25 | R 30 | R 35 | R 40 |
|---|---|---|---|---|---|---|---|
| nominal | linear (null) | nominal only | 0.034 / 0.042 | 0.030 / 0.043 | 0.035 / 0.037 | 0.030 / 0.041 | 0.037 / 0.032 |
| nominal | linear (null) | two-axis (registered) | 0.022 / 0.029 | 0.015 / 0.019 | 0.010 / 0.009 | 0.009 / 0.007 | 0.004 / 0.002 |
| nominal | onset r10 m 1.05 | nominal only | 0.548 / 0.575 | 0.856 / 0.872 | 0.925 / 0.932 | 0.945 / 0.954 | 0.960 / 0.965 |
| nominal | onset r10 m 1.05 | two-axis (registered) | 0.464 / 0.507 | 0.833 / 0.855 | 0.924 / 0.931 | 0.944 / 0.953 | 0.960 / 0.965 |
| nominal | onset r10 m 1.1 | nominal only | 0.870 / 0.874 | 0.942 / 0.946 | 0.954 / 0.962 | 0.975 / 0.981 | 0.982 / 0.989 |
| nominal | onset r10 m 1.1 | two-axis (registered) | 0.862 / 0.869 | 0.942 / 0.945 | 0.954 / 0.961 | 0.972 / 0.981 | 0.977 / 0.987 |
| nominal | onset r15 m 1.1 | nominal only | 0.210 / 0.230 | 0.855 / 0.857 | 0.947 / 0.942 | 0.968 / 0.963 | 0.983 / 0.978 |
| nominal | onset r15 m 1.1 | two-axis (registered) | 0.151 / 0.176 | 0.837 / 0.837 | 0.946 / 0.942 | 0.967 / 0.962 | 0.982 / 0.976 |
| xmin | linear (null) | nominal only | 0.037 / 0.046 | 0.059 / 0.061 | 0.084 / 0.085 | 0.111 / 0.116 | 0.145 / 0.146 |
| xmin | linear (null) | two-axis (registered) | 0.020 / 0.030 | 0.025 / 0.026 | 0.023 / 0.025 | 0.018 / 0.021 | 0.020 / 0.017 |
| xmin | onset r10 m 1.05 | nominal only | 0.516 / 0.554 | 0.772 / 0.756 | 0.811 / 0.801 | 0.873 / 0.879 | 0.934 / 0.947 |
| xmin | onset r10 m 1.05 | two-axis (registered) | 0.479 / 0.516 | 0.764 / 0.752 | 0.811 / 0.801 | 0.873 / 0.878 | 0.931 / 0.945 |
| xmin | onset r10 m 1.1 | nominal only | 0.843 / 0.830 | 0.874 / 0.879 | 0.939 / 0.939 | 0.978 / 0.975 | 0.984 / 0.987 |
| xmin | onset r10 m 1.1 | two-axis (registered) | 0.840 / 0.828 | 0.874 / 0.879 | 0.938 / 0.938 | 0.973 / 0.973 | 0.979 / 0.984 |
| xmin | onset r15 m 1.1 | nominal only | 0.237 / 0.257 | 0.774 / 0.774 | 0.873 / 0.870 | 0.951 / 0.954 | 0.985 / 0.983 |
| xmin | onset r15 m 1.1 | two-axis (registered) | 0.191 / 0.210 | 0.770 / 0.772 | 0.872 / 0.870 | 0.950 / 0.952 | 0.984 / 0.979 |

Reading: the two-axis rule's false-positive rate is 0.002 to 0.030 under both truths, while the nominal-only rule reaches 0.084 at
R 30 and 0.146 at R 40 when the truth is linear in minimal length. Power is unchanged by the second axis where it matters: onset at
round 10, m 1.1, is caught 0.83 to 0.87 by R 20 and 0.94 to 0.99 from R 30. **A takeoff that starts at round 15 (m 1.1) is caught
only about 0.2 of the time by R 20 (0.15 to 0.21 two-axis), 0.77 to 0.84 by R 25 and 0.87 to 0.95 by R 30.** SATURATING (two-axis)
fires 0.002 to 0.037 under the null; LEVEL passes 0.95 to 0.98 under linear growth at the 0128 gain. Output: sim_open0129_x.json.

### 8b. First sim, nominal axis only, linear-nominal truth (sim_open0129.js; kept for the record, superseded by 8a)

| scenario | R | primary (t > 2.605): tau 1.2 / 1.35, s_eta 0 | same, s_eta 0.1 | SATURATING call (null rows) | quad test | LEVEL |
|---|---|---|---|---|---|---|
| linear (null) | 20 | 0.035 / 0.028 | 0.032 / 0.033 | 0.035 to 0.046 | 0.029 to 0.035 | 0.960 to 0.968 |
| linear (null) | 30 | 0.037 / 0.029 | 0.039 / 0.037 | 0.042 to 0.055 | 0.036 to 0.044 | 0.967 to 0.973 |
| linear (null) | 40 | 0.036 / 0.042 | 0.041 / 0.035 | 0.031 to 0.048 | 0.031 to 0.039 | 0.963 to 0.979 |
| geo m 1.02 | 20 | 0.387 / 0.375 | 0.299 / 0.273 | 0.000 to 0.001 | 0.310 to 0.434 | 0.967 to 0.976 |
| geo m 1.02 | 30 | 0.797 / 0.821 | 0.665 / 0.663 | 0.000 to 0.000 | 0.691 to 0.853 | 0.967 to 0.976 |
| geo m 1.02 | 40 | 0.935 / 0.925 | 0.886 / 0.874 | 0.000 to 0.000 | 0.882 to 0.939 | 0.974 to 0.979 |
| geo m 1.05 | 20 | 0.884 / 0.875 | 0.823 / 0.829 | 0.000 to 0.000 | 0.842 to 0.897 | 0.968 to 0.971 |
| geo m 1.05 | 30 | 0.967 / 0.957 | 0.941 / 0.945 | 0.000 to 0.000 | 0.945 to 0.964 | 0.971 to 0.984 |
| geo m 1.05 | 40 | 0.979 / 0.976 | 0.979 / 0.977 | 0.000 to 0.000 | 0.970 to 0.973 | 0.979 to 0.987 |
| geo m 1.08 | 20 | 0.936 / 0.943 | 0.917 / 0.935 | 0.000 to 0.000 | 0.926 to 0.951 | 0.970 to 0.977 |
| geo m 1.08 | 30 | 0.977 / 0.978 | 0.977 / 0.979 | 0.000 to 0.000 | 0.972 to 0.974 | 0.983 to 0.987 |
| geo m 1.08 | 40 | 0.987 / 0.990 | 0.991 / 0.988 | 0.000 to 0.000 | 0.985 to 0.989 | 0.992 to 0.993 |
| onset r10 m 1.05 | 20 | 0.545 / 0.533 | 0.387 / 0.419 | 0.000 to 0.001 | 0.435 to 0.603 | 0.966 to 0.974 |
| onset r10 m 1.05 | 30 | 0.937 / 0.924 | 0.905 / 0.891 | 0.000 to 0.000 | 0.896 to 0.939 | 0.967 to 0.977 |
| onset r10 m 1.05 | 40 | 0.966 / 0.958 | 0.953 / 0.954 | 0.000 to 0.000 | 0.949 to 0.961 | 0.973 to 0.983 |
| onset r10 m 1.1 | 20 | 0.890 / 0.880 | 0.789 / 0.789 | 0.000 to 0.000 | 0.813 to 0.903 | 0.964 to 0.972 |
| onset r10 m 1.1 | 30 | 0.960 / 0.962 | 0.968 / 0.964 | 0.000 to 0.000 | 0.957 to 0.964 | 0.974 to 0.984 |
| onset r10 m 1.1 | 40 | 0.982 / 0.982 | 0.982 / 0.984 | 0.000 to 0.000 | 0.981 to 0.983 | 0.988 to 0.991 |
| onset r10 m 1.2 | 20 | 0.944 / 0.944 | 0.934 / 0.932 | 0.000 to 0.000 | 0.931 to 0.946 | 0.963 to 0.971 |
| onset r10 m 1.2 | 30 | 0.991 / 0.990 | 0.988 / 0.982 | 0.000 to 0.000 | 0.983 to 0.991 | 0.991 to 0.998 |
| onset r10 m 1.2 | 40 | 0.993 / 0.986 | 0.989 / 0.979 | 0.000 to 0.000 | 0.982 to 0.991 | 0.995 to 0.998 |

1,500 runs of 4 seeds per cell; 10 tasks per depth per seed ruler; s_eta = round-to-round innovation sd of true reach. Gain m^(t-1)
from round 1 ("geo") or after round 10 ("onset r10"); the per-round true gain is capped at 8 (D_t can grow at most 8 per round) and the
d50 > 34 saturation cut is applied. Reading: the false-positive rate of the primary test is 0.028 to 0.042 (alpha 0.04), the
SATURATING call fires 0.031 to 0.055 under the null, and a takeoff from round 10 at m 1.1 is caught 0.79 to 0.89 by R 20 and 0.96 to
0.98 by R 30; the slow m 1.02-from-round-0 path needs R 30 to 40 (0.66 to 0.94). LEVEL passes 0.96 to 0.98 under linear growth at
the 0128 gain. Files: sim_open0129.js, sim_open0129_part1.json, sim_open0129_part2.json (all 84 cells), simparts/.

## 9. Prediction

Quantity: mean delta (d50 per round). Point +0.01, 80% band [-0.05, +0.08]. P(TAKEOFF) 0.12, P(SATURATING) 0.10, most likely STEADY.

## 10. Compute

K = 4 H100s, one seed each, launched by the lead with
`setsid nohup srun --jobid=<holder> --overlap -n1 -c 24 bash /N/scratch/bsmensah/silo/open0129/run_open0129.sh <k> 99 >> /N/scratch/bsmensah/silo/open0129/runs/OPEN_s<k>.log 2>&1 < /dev/null &`
(t_to 99: the deadline stops it first). Round time and the round reached per holder-hour: BUILD_OPEN0129.md sec. 6.

## 11. Relation to B17 and to 0128

0129 is one fixed world with depth as the only difficulty knob and expert iteration (SFT on own verified beam solutions, replay-all);
B17 is a stream of new W3 worlds with per-item policy-gradient updates against a frozen twin. 0129 can show whether the 0128 loop's
reach curve bends upward on a fixed ruler once the ceiling is gone; B17 can show self-training beating a frozen twin across novel
worlds, which a single-world loop cannot. P_0's reading on each ruler is the frozen-twin control for LEVEL only (a frozen policy on a fixed ruler
reads the same every round, which the determinism gate checks). It is not a control for the shape test, whose null is covered by the
simulation and by requiring the shape on both ruler axes (sec. 5). The capped-loop comparison is 0128's saved FRONTIER P_t scored on the same rulers (optional,
measurement only, a fifth GPU): it puts 0128 policies on the 0129 scale, is not a concurrent capped arm, and cannot attribute a
shape to the ceiling's removal. No extra arm is run.

## REGISTRATION

Registered 2026-11-05 18:15 ET (Quartz clock, TZ America/New_York) by the lead. Text above is PREREG_OPEN0129_DRAFT.md byte for byte (sha256 b7fe10f08c6e146ca9c81f19c0005af90f876d9cc15f75379cacde67a373c1a8). Verifier: VERDICT_OPEN0129.md (GO, re-verification of 2026-11-05 17:2x ET) and VERDICT_OPEN0129_DETERMINISM.md. Determinism gate: runs/det.log RULER_DETERMINISM MATCH rows_equal 300 of 300. Code: open0129.py 4e46988a, opengen.py 8915e834, run_open0129.sh 600bf85d, read_open0129.py 7fa9481c. No runs/OPEN_s*/round_*.json existed at registration.
