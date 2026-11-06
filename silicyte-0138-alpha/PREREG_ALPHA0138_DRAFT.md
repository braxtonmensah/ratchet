# PREREG silicyte-0138 ALPHA (DRAFT, for the verifier): can a recipe raise the learning exponent alpha?

Builder draft 2026-11-05 ET. Code alpha0138.py, launcher run_alpha0138.sh (sha256 in BUILD_ALPHA0138.md). Nothing below has been
measured on a GPU. Every number marked "stored" comes from 0128's stored files, read on the Quartz login node (logs/plan2.out).

## 0. VERIFIER AMENDMENT 2026-11-05 ET (binding; applies the lead's decisions; written before any GPU data; VERDICT_ALPHA0138.md)
Where this section and the builder text below disagree, this section rules.
- STATUS: every result of this study is an EXPLORATORY SCREEN of one model (Qwen3-8B), one trainer (reachlaw.train) and one task
  family. It is not, and cannot be reported as, evidence that a loop compounds (sec. 8). A PASS only nominates a lever for a loop study.
- FIRST SCREEN (tier 1 is replaced by this): control C1, then R0 (as-run rows), R_fix (= R3, R0's rows with string targets) and R4S
  (short hops, string targets), seeds s = 1, 2, 3, N 256 and 2048. Cards (alpha0138.py): SMOKE, C1, FS1, FS2, FS3. R4, R1, R2, R4C,
  R3N, R1E, C2 and the C3 grid are tier 2 and wait for the first screen's result (a new amendment chooses them).
- REFERENCES: R_fix is read against R0. R4S is read against R_fix (same string format, so R4S gets no credit for the format fix).
- RATIO CI (replaces the task-bootstrap-plus-seed CI of sec. 4): ln rho +/- t(0.975, df) x sd_seed / sqrt(S), sd_seed = pooled sd of
  the per-seed ln rho over the levers read in that band (R_fix and R4S), df = sum of (S - 1) = 4 with 3 seeds (t = 2.776). The paired
  task bootstrap is printed (task-CI), not gated.
- PASS (per lever, unchanged in form): band all rho >= 1.5 AND seed-CI lower bound > 1 AND rho > 1 in every seed; AND band d5-10
  seed-CI lower bound > 1. KILL: seed-CI upper bound < 1.5 in band all AND in band d5-10. Otherwise INCONCLUSIVE. A nonpositive or
  undefined point ratio is INCONCLUSIVE; no seed sd (fewer than 2 usable seeds) is INCOMPLETE. Neither is a pass.
- KILL TEST OF THE FIRST SCREEN: if R_fix and R4S both read KILL, or INCONCLUSIVE with point rho < 1.3 in band d5-10, then neither the
  format fix nor short-hop training closes the 2.6x alpha gap; tier 2 (R4 / R1 / R2) runs only if a new amendment argues for it
  against this result, and the default next lever is the model or trainer (NARITH, WARM). Accepted in advance.
- C1 IS A GATE: card C1 (train + score the rebuild of 0128's P_1) runs first, alone; `python3 -I alpha0138.py gate` must exit 0
  (C1 PASS, sec. 6) before FS1-FS3 start. Order mismatch also stops card C1 itself (VOID_C1_ORDER, exit 7).
- MEMORY: per-phase caps ALPHA_TRAIN_FRAC 0.65 (training) and ALPHA_MEM_FRAC 0.30 (scoring), passed EXPLICITLY on every launch
  (run_alpha0138.sh defaults ALPHA_MEM_FRAC to 0.35). SMOKE runs first and measures the real training peak (64 longest rows, list and
  string targets). Stop rule: if SMOKE prints VOID_OOM or exits non-zero, or any card prints VOID_OOM (training exceeded the cap;
  exit 10), the screen stops and nothing is relaunched under a higher cap without a new amendment. One process per card; the process
  refuses a card with a bootseed0128.py process or less free memory than its cap + 1 GB.
- PER-DEPTH AND PER-DISTANCE alpha (reported, not gated) now use the silicyte-0137 definitions verbatim (smoothed shares
  (k + 0.5) / (n + 1); depth: e_d = 1 - s_d^(1/d), mean of per-seed alpha_d; distance: outcomes pooled over seeds, q_k clipped 0.999,
  e_k floored 1e-3, near / far = mean of alpha_k over k 2-4 / 5-8). Verified: on 0128's stored rounds these functions return 0137's
  numbers exactly (d2 0.5688 ... d8 0.1295; k2 0.6373, k3 0.2937, k4 0.2016, near 0.3776, far 0.1574). The builder's earlier band
  numbers (near 0.284, far 0.215) used a different band rule and are withdrawn.
- R4S DISCLOSURE: 5.6-8.8% of R4S rows (26-39 of 256 states, 241-253 of 2048; 89-96% of them hindsight states) have no stored state
  within 3 steps and fall back to the state's own full-distance target (m 4-10). R4S is "short hops where the stored path allows".
- POWER under this rule: sec. 5a.

## 1. Question and why
0128's loop obeys e = A N^(-alpha), rows per round ~ d50^gamma; reach accelerates iff alpha (1 + gamma) > 1. Measured alpha 0.175
+/- 0.028, gamma 1.19, so alpha (1 + gamma) = 0.38: alpha is about 2.6x short (RESULT_LOOP_PHYSICS_1105). silicyte-0137 addendum:
alpha_d ~ 1.2 / d per depth, deep steps learn slowest. This study measures alpha outside the loop, with fresh fits on a fixed pool, and
screens recipes that might raise it. It cannot show compounding; it can only say which recipe, if any, moves the binding exponent.

## 2. Fixed objects
- Pool: inputs/seed256 + FRONTIER_s2 own_0..own_10 = 8,440 rows, the exact training set of 0128's P_11 (pool/POOL.jsonl sha256
  da60787e...; 0 rows with a MEAS input or MEAS tid). Stored proof: from this snapshot the harness reproduces 0128's own order_md5 for
  all 11 fits r0..r10 of FRONTIER_s2.
- Fit: reachlaw.train unchanged (r16, lr 2e-4, bs 16, one pass, warmup 20 then constant LR), fresh LoRA, torch.manual_seed(13800 + s)
  (same init across recipes at replicate s: paired). The harness controls the visit order exactly (file written so that reachlaw's own
  Random(0) shuffle yields the intended order).
- Ruler: bootllm.solve B 4, max 10 steps (= bootseed0128.py:408) on ALL 300 MEAS tasks (seed 29000). e = geometric MLE over per-depth
  hidden-correct counts.
- Replicates s = 1, 2, 3 (amended, sec. 0). N points 256 and 2048 (ratio 8) for every lever; R0 is one nested pass to 8192 with
  checkpoints 256..8192 (first screen scores 256 and 2048 only; 512..8192 are tier 2, C3). Nested checkpoint = fresh fit by
  construction: reachlaw.train has warmup 20 steps then constant LR (LambdaLR min(1, (s+1)/20)), lora_dropout 0, and nothing that
  depends on the total row count, so R0's checkpoint at N and R_fix's fresh fit at N run the same steps on the same visit order from
  the same torch seed 13800 + s; they differ only in the target strings and GPU nondeterminism.

## 3. Format rule and baselines (coordinator 11/05, FINDING_HINDSIGHT_FORMAT_1105.md, 33de7d5)
R0 and C1 keep 0128's rows exactly as run (hindsight targets as character lists) so that R0 / C1 / C3 validate against 0128.
LEVER 1 is R_fix (= R3 in the code): R0's rows with each hindsight target joined into a string, all else identical; it is read
against R0. Every other recipe uses string targets and is read against R_fix (same format), so no lever gets credit for the fix.

## 3b. Recipes (all at the same N = number of states taken from the pool), in rank order
Ranking (coordinator, ratchet 71a4a63): per remaining distance k, step success learns at alpha 0.637 / 0.294 / 0.202 for k 2 / 3 / 4,
far k 5-8 at 0.157 vs 0.378 near. Recomputed by the amended reader's 0137 functions from stored rows: k2 0.6373, k3 0.2937, k4 0.2016,
near 0.3776, far 0.1574, exactly 0137 (verifier verify.out; the builder's plan3.out values used other definitions). So:
0. R_fix (R3), against R0.
1. R4S subgoal-style short hops: R0's states, trained only on (state, stored state m <= 3 ahead) -> op (1.75 rows per state at N
   2048). This is the training half of the subgoal recipe. The test-time half (decompose a deep task into short hops) needs a subgoal
   proposer inside the beam; bootllm.beam has none, so it is a hook, not built.
2. R4 hindsight at every distance (below). 3. R3 format fix. 4. R1. 5. R2.
- R0 uniform. U_s = pool shuffled by Random(138100 + s); set at N = U_s[:N].
- R1 hard-first pruning (Sorscher et al. 2022), keep 1/4: candidates U_s[:4N]; hindsight rows kept at their share, other rows by
  longest solution first. R1E easy-first control (tier 2).
- R2 multi-label targets: R0's states, every canonical op that starts a verified reordering of the stored path (mean 1.45 labels per
  state; own rows 1.93). Equivalent ops are not labels (the beam scores only the first op in OPN order per next state).
- R3 hindsight target format fix: R0's rows with hindsight targets as DNA strings. In 0128 all 4,092 hindsight rows (48.5% of the
  pool) render the target as a Python list of characters, a format the test prompt never has, at 970 tokens vs 434. R3N: no hindsight
  rows (tier 2).
- R4 compositional relabelling (0137 addendum): R0's states, each trained on (state, the stored state m steps ahead) -> op for every
  stored m (2.6 rows per state). R4C compute-matched, one m per state (tier 2).
- Not buildable offline: subgoal targets (policy predicts a state k steps ahead). The registered trainer scores one op name and the
  beam ranks 54 op names; a state-valued target needs a new trainer and a new beam. Hooks: NARITH, WARM (register_hook).

## 4. Primary quantity and verdict (per lever R, per depth band)
- Bands: all (d 1-10), d1-4, d5-10. For each band: alpha(R) = [mean_s ln e(R, s, 256) - mean_s ln e(R, s, 2048)] / ln 8, and
  ratio rho(R) = alpha(R) / alpha(base) over the same points and band, base = R0 for R_fix and R_fix for every other lever.
- CI of ln rho (AMENDED, sec. 0): seed component only, t(0.975, df) x sd_seed / sqrt(S), sd_seed pooled over the lever recipes'
  per-seed ln rho, df = levers x (S - 1). The task bootstrap (1,000 resamples of the 300 MEAS tasks, applied jointly to every fit:
  paired) is reported as task-CI and not gated.
- PASS iff band all: rho >= 1.5, CI lower bound > 1, rho > 1 in every seed; AND band d5-10: CI lower bound > 1 (deep steps must learn
  faster too; this is the d x alpha_d >= 5 condition of the 0137 addendum, read as the deep-band ratio).
- KILL iff the upper CI bound is < 1.5 in band all AND in band d5-10. Otherwise INCONCLUSIVE (seed 3 is now in the first screen; an
  INCONCLUSIVE first screen is reported as such, and more data needs a new amendment).
- Reported, not gated (0137 definitions, sec. 0): d x alpha_d per depth d 2..10 for every recipe; alpha per remaining distance k 2..8
  (q_k = s_k / s_{k-1}, smoothed shares, outcomes pooled over seeds) with near (k 2-4) and far (k 5-8) band means of alpha_k and a
  task-bootstrap CI on each band; R4S and R4 vs R3 and vs R4C (format vs relabelling
  vs compute). R4S and R4 carry string targets, so their contrast with R0 includes the R3 format fix; their own effect is the ratio
  to R3.

## 5a. Power of the amended first screen (verifier, 2026-11-05, before data; Quartz /N/scratch/bsmensah/verify_alpha0138/logs)
Planted alpha through the amended reader (`python3 -I alpha0138.py power 300 <sig> <nsim> <S> 20 [ratios]`), 300 MEAS tasks, R0
alpha 0.175. Design A: R_fix carries the true ratio x vs R0 (R4S = R_fix, a null lever vs R_fix). Design B: R4S carries x vs R_fix
(R_fix = R0, null). Per-fit noise: synth_outs draws independent Bernoulli task outcomes (alone sd of ln e 0.070-0.072) PLUS a
gaussian sig on ln e; sig 0.064 gives a total about 0.095 (1.5x the measured 0.064, conservative); sig 0 gives about 0.07 (closest to
the measured 0.064). Values are PASS rates; "null" is the false PASS rate of the null lever in the same runs.
| true ratio x | R_fix PASS, sig 0.064 | R_fix PASS, sig 0 | R4S PASS, sig 0.064 | R4S PASS, sig 0 |
|---|---|---|---|---|
| 1.0 (false PASS) | 0.017 (300 sims) | 0.007 (300) | 0.000 (300) | 0.010 (300) |
| 1.5 | 0.180 (300) | 0.243 (300) | 0.090 (300) | 0.180 (300) |
| 2.0 | 0.553 (300) | 0.740 (300) | 0.280 (300) | 0.460 (300) |
| 2.6 | 0.885 (200) | 0.960 (200) | 0.555 (200) | 0.805 (200) |
- False PASS of the null lever in the same runs: 0.000-0.025 in every cell. Seed-only CI coverage of the true ratio 88-96% (nominal
  95%; df 4 and pooling over levers with different references). The CI is slightly liberal; the every-seed and d5-10 conditions keep
  the false PASS rate at or under 0.025.
- R4S has less power than R_fix at the same x because its reference R_fix is itself a noisy fit pair at a higher alpha.
- More seeds do NOT buy power under this rule: at x 2.6, sig 0.064, R_fix 0.885 / 0.865 / 0.825 at 3 / 4 / 5 seeds, R4S 0.555 / 0.545
  at 3 / 4 seeds, because "rho > 1 in every seed" gets harder with every seed. The lever is the N span (ln of the N ratio), see the
  verifier's VERDICT_ALPHA0138.md sec. 3 for N 256-4096 and 256-8192 and their GPU-hours. The design stays at N 256 / 2048 unless the
  lead amends it before launch.
- Seeds that reach an alpha <= 0 in the deep band make ln rho undefined; then INCOMPLETE (0-3.7% of sims).

## 5. Noise, MDE and power (stored, plan2.out; superseded for the first screen by 5a)
- White noise of one fresh fit's ln e on MEAS, measured as the residual sd of ln e about the in-loop power law (each 0128 round is a
  fresh LoRA fit on the same tasks; conservative, it includes misfit): pooled band 0.064, d5-10 band 0.084 (all 300 tasks). It does
  not shrink below 0.055 for smaller task subsets (fit noise dominates), but the deep band does (0.145 at 120 tasks), so the subset
  is all 300 tasks.
- se of alpha(R) - alpha(R0), 2 seeds, 2 points, independent fits: 2 x 0.064 / (sqrt 2 x ln 8) = 0.0435.
  MDE (80% power, 2-sided 5%) = 0.122 in alpha = ratio 1.70. Power to PASS at a true ratio of 1.5 / 2.0 / 2.6: 0.50 / 0.98 / 1.00.
  Deep band MDE ratio 1.94. With 3 seeds the pooled MDE ratio is 1.57; with 4 seeds 1.49.
- With the format rule (levers read against R_fix, itself a noisy fit), selftest6.out: PASS 0 / 0 / 6 of 60 at true ratio 1.0 /
  1.5 / 2.0 and 26 of 60 at 2.6, CI coverage 57-60 of 60. Power is lower still, because the baseline alpha is now one noisy fit pair
  per seed instead of R0's. The two fixes below apply all the more.
- Earlier, levers read against R0 (selftest5.out; planted alpha, 4 levers of which R1 carries the effect, 2 seeds, 300 tasks,
  fit noise 0.064, 60 sims each): PASS rate 0/60 at null (KILL 3), 3/60 at 1.5x, 13/60 at 2.0x, 23/60 at 2.6x; ratio CI coverage
  58-60 of 60. The analytic numbers above are therefore NOT the power of this verdict rule: the CI adds the task bootstrap on top of
  the pooled seed spread (which already contains task noise) and PASS also needs the d5-10 band. As drafted, 2 seeds cannot decide.
  Verifier choice, before data: (a) 4 seeds (cards S3 plus an S4 copy; tier-1 cost about 2 x 5.0 GPU-h more), or (b) CI of ln rho
  from the seed component alone (sd pooled over levers, df = levers x (S - 1)) with the task bootstrap reported, not gated. Builder
  recommends (b) plus a third seed, then re-run the planted power check (`python3 -I alpha0138.py selftest 300 0.064 60`) before GO.
- Noise units cross-check: 0128 ruler noise tau 0.158 (random-walk step) and s_e 0.127 (white reading noise) are in logistic d50
  units; at d50 4-5 s_e converts to about 0.03-0.04 in ln e, below the 0.064 used here.

## 6. Controls (stated before data)
- C1 harness = 0128: rebuild FRONTIER_s2's fit r0 (P_1, 780 rows, 262 of them list-target rows, seeds 2001). PASS iff the order_md5
  equals 0128's (546cc3a2dc9a, else VOID) and (adapter wsum = 48eb45d12fef, or >= 90% of MEAS rows equal to stored round_1
  fixed_rows) and (all MEAS rows equal, or |d ln e| <= 0.22). It runs first, alone (card C1), and `gate` must exit 0 before the
  first-screen cards start (sec. 0).
- C2 nested checkpoint = fresh fit (tier 2): fresh fit on R0_s1's first 512 visited rows vs R0_s1's checkpoint 512; same rows by
  construction; PASS iff adapters equal or |d ln e| <= 0.22.
- C3 harness alpha (tier 2): R0's alpha over N 256..8192 (6 points, seed mean) within 1.96 sqrt(se^2 + 0.014^2) of 0.175.
  Known, stated now: the harness draws rows uniformly from the FINAL pool, while the loop at N had only early, shallower rows
  (distribution shift with N). A C3 FAIL with C1 PASS is a finding about the loop (its alpha mixes N and row distribution), not a
  harness bug; lever ratios are still read against the harness R0.
- Lever proof: every fit prints LEVER_ALPHA (recipe, n_train, set_md5, L_mean, hind_share, labels_per_state, order_md5, adapter md5);
  every score prints LEVER_SCORE. lever_check on logs/server_*.log must be LEVER_OK for every arm before any ratio is read.

## 7. Kill test of the program (stated before data)
First screen: the kill test in sec. 0 applies. After any tier 2 that a later amendment runs: if every lever R1, R2, R3, R4 reads KILL or INCONCLUSIVE with point ratio < 1.3 in band d5-10, row selection and target relabelling
cannot close the 2.6x alpha gap at this model and trainer; the next lever is the model or trainer (NARITH, WARM, trainer changes),
not the data. Accepted in advance.

## 8. Not decided by this prereg
gamma under each recipe (needs loop rounds); whether a PASS lever compounds in a loop (a follow-up loop study registers that).
