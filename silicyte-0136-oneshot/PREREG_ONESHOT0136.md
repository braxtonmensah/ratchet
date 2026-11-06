# PREREG DRAFT: silicyte-0136 ONE-SHOT (d) AMORTISATION on 0128's saved adapters

Status: DRAFT, written 2026-11-05 about 19:10 ET by the 0136 builder, BEFORE any one-shot reading exists. It becomes registered only
when a verifier says GO and the lead timestamps it. No GPU step has run. Nothing here trains.

Verifier amendment, 2026-11-05 evening, BEFORE any one-shot reading exists (VERDICT_ONESHOT0136.md): the lead's decision on the
builder's open question is applied. PRIMARY = per-seed OLS slope of log(B1 d50 / S d50) (sec. 4); the difference slope is
SECONDARY. Sections 3, 4, 6, 7 and a new sec. 9 (reruns and launch order) are rewritten accordingly; sections 1, 2, 5, 8 unchanged.

## 1. Question

His 18:12 hunch: "one-shotting might be the way to go for RSI". Meaning (d): an expert-iteration loop (search finds programs, the
policy is trained on them) compounds if it CONVERTS SEARCH INTO WEIGHTS. Then the policy alone (one shot, no search) reaches deeper
each round, faster than the searched reach grows, and the search budget it frees can be spent at the frontier. This is the ExIt /
AlphaZero mechanism (PRIOR_ART_ONESHOT0136.md). 0128 trained 11 policies per seed with a fixed beam (B 4); we ask whether the
one-shot reach of those same policies closes on their searched reach round over round.

## 2. Data (fixed now)

- Policies: P_t for t = 0..10 of s1, FRONTIER_s2, FRONTIER_s3, FRONTIER_s4 (44 policies). s1 P_0 = inputs/exp_n256 (canonical
  md5); k >= 2 P_0 = runs/FRONTIER_sk/P_0; P_t (t >= 1) = runs/<run>/P_t, read-only.
- Adapter provenance (gate): k >= 2: wsum(P_t)[:12] equals round_{t-1}.json summary.adapter_md5 (t >= 1) or the run log's LEVER
  tag=P0 line (t = 0); all 33 checked OK on the login node. s1 (legacy code, no stored md5): mtime of P_t equals mtime of
  round_{t-1}.json (same second, the loop's write order) and precedes round_t.json; P_t's wsum is recorded.
- Ruler: MEAS = bootllm.make_pool(consol_v1, 29000, 300, 10): 300 tasks, depth 1..10 (26/25/28/33/28/27/37/37/26/33), max 10 steps.
  It is 0128's registered A1 ruler, never trained on.
- SEARCHED reading S_t: 0128's STORED round_t.json fixed_rows (registered B 4 beam, max 10, scored by the round's own resident
  scorer). Not re-scored. Its d50 recomputed by bootllm.summarize equals summary.d50_fixed for all 44 (login check OK).
- ONE-SHOT readings, new (GPU):
  - B1 (PRIMARY) = bootllm.beam(task, B = 1, max_steps = 10): the registered beam at width 1. Every step it executes all 54
    children of the single kept state and stops if any equals the target, so its last step is free: a depth-d task needs d - 1
    correct greedy choices.
  - O0 (secondary) = pure greedy rollout: apply the argmax op, execute it, stop at the target or after 10 steps; no sibling
    lookahead. It shares the B1 policy calls (memoised per task and state), so it costs almost no extra forwards.

## 3. Quantities

- d50 = registered logistic d50 (bootllm.logistic_d50 on hidden-correct c). iso d50 = model-free: per-depth rates, weighted PAV
  (non-increasing), anchored at P = 1 at depth 0, linear interpolation of the first fitted depth below 0.5; censored at 10.
- A_t = d50(B1) / d50(S) (amortisation ratio); G_t = d50(S) - d50(B1) (gap); both also on iso d50.
- Per seed k: slope_S,k and slope_O,k = OLS slopes of d50 over t = 0..10. diff_k = slope_O,k - slope_S,k = -(OLS slope of G_t).
- Per seed k: b_k = OLS slope over t = 0..10 of log A_t = log(B1 d50_t / S d50_t) (PRIMARY quantity).

## 4. Kill test (primary, fixed now; lead's decision applied by the verifier)

- PRIMARY statistic: the 4 per-seed b_k (OLS slope of log(B1 d50 / S d50) over rounds 0..10); T = mean / (sd / 2); one-sided,
  df 3, alpha 0.05, critical value 2.3534. AMORTISES iff T >= 2.3534.
- Why the log ratio and not the difference: a policy that stays a CONSTANT FRACTION of searched reach is not amortising, and the
  difference slope reads that proportional growth as GAP_GROWS (builder's planted smoke: difference t -13.5, log ratio t -0.20;
  verifier sim: the difference test calls GAP_GROWS on 28-96% of constant-ratio nulls, sec. 6). The log ratio is scale-free.
- OLS (not the endpoint LEVEL) as in the builder's sim (OLS power >= LEVEL in 13 of 16 cells).
- Labels, in order:
  1. VOID: any gate in sec. 5 fails. No numbers are interpreted.
  2. AMORTISES: T >= 2.3534. One-shot reach rises as a growing fraction of searched reach.
  3. RATIO_FALLS: T <= -2.3534. One-shot reach falls as a fraction of searched reach; search out-runs the policy.
  4. NO_AMORTISATION_DETECTED: otherwise, quoted with the MDE at the measured rho_hat and c_hat (sec. 6).
- SECONDARY (printed, no label): the difference slope (mean diff_k, its t), the same on iso d50, and the per-step-error scale. A
  sign disagreement between the primary and the difference or per-step-error mean is printed as UNIT-DEPENDENT.
- O0 TELEMETRY (printed, no label): slope of log(O0 iso d50 / S iso d50) and the O0-minus-S difference slope, both on iso d50
  (a pure greedy rollout's logistic d50 is often unfittable); o0_invalid counts per policy.
- COMPOUNDING-CANDIDATE (added to AMORTISES only) iff ALL hold: (i) AMORTISES; (ii) searched reach still rises: one-sided t of the
  4 slope_S,k >= 2.3534; (iii) the iso d50 log-ratio mean slope > 0; (iv) the O0 iso log-ratio mean slope > 0; (v) the
  difference mean slope > 0 (the absolute gap in d50 also shrinks, point estimate).
- Known reading of the primary (verifier sim, sec. 6): a policy that keeps a CONSTANT ABSOLUTE gap while searched reach rises has a
  rising ratio and reads AMORTISES in 25-97% of sims. That is the intended meaning of the ratio (the policy keeps pace in depth),
  and condition (v) keeps it out of COMPOUNDING-CANDIDATE.
- THIS RESULT IS NOT A COMPOUNDING CLAIM BY ITSELF, under any label. COMPOUNDING-CANDIDATE means the channel exists in the loop's
  weights. 0128 never spent the freed budget (fixed B 4), so it is not evidence of compounding; it licenses a loop that re-spends
  the freed search at the frontier, which must be tested separately against a matched control.
- d50 None rule (fixed now, before data): if ANY B1 or S logistic d50, in any seed and any round (round 0 included), is None (no
  fit) or <= 0, so that a log ratio is undefined anywhere, the primary is computed on iso d50 for B1 and S in ALL seeds and all
  rounds (no per-cell mixing of scales). iso d50 is always in (0, 10]; any iso value censored at 10 is flagged in the output with
  no label change. The stored S d50 is non-None for all 44 policies (2.635-4.900, verifier read), so only B1 can trigger it.

## 5. Gates (any failure = VOID)

1. md5 of lib/consol.py, reachlaw.py, ident.py, bootllm.py and of code/bootseed0128.py (c54e21d2) and ext/score_deep.py (c7fc4099).
2. Adapter provenance (sec. 2) for all 44; adapter files' md5 + mtime unchanged across scoring.
3. MEAS (tid, depth) equals every stored fixed_rows row for row (login check OK for 44 of 44).
4. First-expansion identity: every task the stored B 4 beam solved within its first expansion (exec <= 54) has an identical
   (tid, depth, v, c, exec) row under B1. (Pure beam-code check; it does not exercise the scorer.)
5. CONTROL_B4 (scorer check, per seed): in the same multi-adapter process, the registered B 4 beam on the first 60 MEAS tasks for
   P_0 and P_10 equals the stored fixed_rows row for row. This proves the one-base-model, 11-named-adapter scorer and adapter
   switching reproduce 0128's readings.
6. A/A: s1 P_0 B1 scored twice in separate processes: rows equal (the beam draws no random numbers; A4 measured 120/120).
7. LEVER_ONESHOT marker per policy (active adapter = P_t, B=1, max_steps=10): `CPU_OK=1 python -I C:/Users/bmens/NQ_local/lane/lever_check.py <log dir> ONESHOT="LEVER_ONESHOT run=\S+ t=\d+ B=1 max_steps=10 active=P_\d+"`.

## 6. Power, false positives, MDE

### 6a. PRIMARY (log ratio), verifier sim /N/scratch/bsmensah/verify0136/sim_logratio0136.py, 8,000 sims per cell, seed 20261106

Same 0128 noise (tau 0.158, s_e 0.127, sg 0.021, K 4, rounds 0..10, searched gain 0.181, start 2.78). One-shot latent =
A0 x exp(beta t) x (a walk with the searched gain whose steps correlate with S's by rho, scaled by c); B1 reading noise c x 0.127 in
ABSOLUTE d50 units (conservative on the log scale at small A0); between-seed sd of beta 0.006. beta = true slope of log A_t.

| A0 | rho | c | FP (beta 0) | power beta 0.01 / 0.02 / 0.03 / 0.04 / 0.06 | MDE at 80% | diff test GAP_GROWS at beta 0 | constant-gap case reads AMORTISES |
|---|---|---|---|---|---|---|---|
| 0.45 | 0.0 | 1.0 | 0.052 | 0.21 / 0.48 / 0.76 / 0.92 / 1.00 | 0.033 | 0.776 | 0.782 |
| 0.45 | 0.0 | 1.5 | 0.053 | 0.17 / 0.35 / 0.58 / 0.77 / 0.96 | 0.043 | 0.704 | 0.542 |
| 0.45 | 0.8 | 1.0 | 0.054 | 0.35 / 0.78 / 0.97 / 1.00 / 1.00 | 0.021 | 0.956 | 0.973 |
| 0.45 | 0.8 | 1.5 | 0.049 | 0.24 / 0.56 / 0.82 / 0.95 / 1.00 | 0.029 | 0.964 | 0.746 |
| 0.70 | 0.0 | 1.0 | 0.050 | 0.21 / 0.51 / 0.78 / 0.93 / 1.00 | 0.031 | 0.339 | 0.325 |
| 0.70 | 0.0 | 1.5 | 0.051 | 0.17 / 0.37 / 0.60 / 0.79 / 0.97 | 0.041 | 0.278 | 0.245 |
| 0.70 | 0.8 | 1.0 | 0.053 | 0.40 / 0.85 / 0.99 / 1.00 / 1.00 | 0.019 | 0.630 | 0.684 |
| 0.70 | 0.8 | 1.5 | 0.056 | 0.28 / 0.63 / 0.89 / 0.97 / 1.00 | 0.027 | 0.571 | 0.395 |

- FP of the primary 0.049-0.056 (Monte Carlo sd about 0.0025): at alpha. Its lower tail (RATIO_FALLS) at beta 0: 0.041-0.050.
- MDE 0.019-0.043 per round in log A_t, i.e. the ratio must grow about 2-4.4% per round (21-54% over 10 rounds) to be seen.
- After the data (descriptive, no label change): rho_hat and c_hat from the reader; the sim is re-run near (A0_hat, rho_hat, c_hat)
  and that MDE is quoted with any null.

### 6b. SECONDARY (difference slope), builder's sim_oneshot0136.py, 4,000 sims per cell, seed 20261105 (kept for the record)

Noise model = 0128's: random-walk step tau 0.158, white reading noise s_e 0.127, between-seed gain sd 0.021 (also used for the
diff), K 4, rounds 0..10, searched gain 0.181. The one-shot reading's random-walk step correlates with the searched one by rho
(same adapter; unknown now) and its noise is scaled by c. delta = slope_O - slope_S (d50 per round).

| rho | c | FP (delta 0) | power delta 0.04 / 0.06 / 0.08 / 0.10 / 0.14 | MDE at 80% |
|---|---|---|---|---|
| 0.00 | 1.0 | 0.048 | 0.19 / 0.32 / 0.47 / 0.61 / 0.85 | 0.133 |
| 0.00 | 1.5 | 0.056 | 0.16 / 0.24 / 0.34 / 0.46 / 0.70 | 0.169 |
| 0.50 | 1.0 | 0.050 | 0.27 / 0.47 / 0.67 / 0.82 / 0.96 | 0.097 |
| 0.50 | 1.5 | 0.052 | 0.22 / 0.35 / 0.48 / 0.65 / 0.87 | 0.127 |
| 0.80 | 1.0 | 0.051 | 0.41 / 0.69 / 0.87 / 0.97 / 1.00 | 0.072 |
| 0.80 | 1.5 | 0.052 | 0.28 / 0.49 / 0.68 / 0.84 / 0.98 | 0.095 |
| 0.95 | 1.0 | 0.057 | 0.61 / 0.88 / 0.98 / 1.00 / 1.00 | 0.054 |
| 0.95 | 1.5 | 0.053 | 0.40 / 0.65 / 0.85 / 0.95 / 1.00 | 0.075 |

- FP 0.048-0.057 (Monte Carlo sd about 0.0035): at alpha.
- MDE 0.054-0.169 d50 per round, i.e. the one-shot slope must exceed the searched slope (about 0.18) by 30-95% to be seen.
- After the data (descriptive, no label change): rho_hat = correlation of the round-to-round increments of S and B1 pooled over
  seeds, c_hat from the residual sd ratio; the sim is re-run at (rho_hat, c_hat) and that MDE is quoted with any null.

## 7. Prior expectation, units, and what would mislead

- Unit dependence (audit sec. 1a): under uniform per-step sharpening of the policy, a searched ruler sits further up the
  hyperbola d50 = ln 2 / -ln(per-step success), so the d50 scale FAVOURS the searched slope. AMORTISES on d50 is therefore a
  strong result, and GAP_GROWS on d50 alone is weak. Reported secondary (no label): slopes of -log(per-step error) with per-step
  success 0.5^(1/d50), and the slope of log A_t. A sign disagreement between scales is printed as UNIT-DEPENDENT.
- Measured on the reader smoke (smoke_read0136.py, planted data): a one-shot policy that stays a CONSTANT FRACTION of searched
  reach (B1 = 0.55 x S, no planted excess) reads GAP_GROWS on the d50 slope test (t -13.5) while the log A_t slope is flat
  (t -0.20). So the difference slope penalises proportional growth. RESOLVED by the lead: the log A_t slope is the sole PRIMARY
  (sec. 4); the difference slope is SECONDARY. Verifier re-ran the builder's smoke under the amended reader: delta 0 ->
  NO_AMORTISATION_DETECTED (t -0.20), +0.15 -> AMORTISES + COMPOUNDING-CANDIDATE, -0.15 -> RATIO_FALLS, +0.05 -> AMORTISES with
  UNIT-DEPENDENT (difference t -5.12, so no COMPOUNDING-CANDIDATE), a B1 d50 None at s3 round 0 -> iso scale for all seeds.
- B1's free last step means B1 d50 >= O0 d50 by roughly one step; both are reported.
- Ceiling: none expected (B1 d50 will sit below S's 2.6-4.9, inside depth 1..10). Floor: depth 1 is solved by both (first
  expansion), so B1 d50 >= 1.
- Round-10 s3/s4 rows are the archive scoring of P_10 (audit sec. 1); they are the stored registered reading of that adapter
  and are used as such.

## 8. Cost and deadline

44 policies x one B1 pass (about 2,600 forwards each, at most 3,000) + 8 B4 control prefixes (about 1,600 forwards each) + 1 A/A.
At 0.13-0.18 s per forward on a shared H100: about 5.5-7.5 min per policy, 70-97 min per seed process, 4.8-6.6 GPU-hours of
shared-card occupancy in total, peak about 19-21 GB per process (cap 0.30 x 80 GB = 24 GB). Read: read_oneshot0136.py on the
login node. Deadline: label before the end of Nov 10.

## 9. Launch order and reruns (fixed now)

- Control first: the first GPU call is `score s1 --ts 0-1 --tag rep`: it loads P_0 and P_1 in one scorer, scores both B1+O0, then
  runs CONTROL_B4 (registered B 4 beam, first 60 MEAS tasks) for P_0 and P_1 against stored fixed_rows, so adapter switching is
  exercised. Any mismatch stops everything (about 25 min spent). The full `score s1` then repeats CONTROL_B4 on P_0 and P_10 with
  11 adapters resident, as do the other three seeds.
- A/A: s1 P_0.B1.rep.json and P_1.B1.rep.json (first call) vs P_0.B1.json and P_1.B1.json (full s1 process): rows must be equal.
- run_oneshot0136.sh always exits 0 (its last command is an echo), so the chain checks `ONESHOT_EXIT rc=0` in the log after every
  call and stops otherwise (verifier finding; see the launch line in VERDICT_ONESHOT0136.md).
- Reruns: a seed process that dies without a gate verdict (OOM inside its own 0.30 cap, node failure, preemption, time limit) is
  rerun ONCE in full after its partial out/<run>/ files are moved to out_void/<run>_<n>/, which is never read. A CONTROL_B4,
  identity, provenance or A/A failure is never rerun: the label is VOID. No re-scoring after any label is seen.

## REGISTRATION

Registered 2026-11-05 19:04 ET (Quartz clock, TZ America/New_York) by the Silicyte lead. Text above is PREREG_ONESHOT0136_DRAFT.md byte for byte (sha256 13f79839a8b4b6320dfc66b82d304068d1dfcabd26da3d0c3850e9d9f334b483), as amended by the independent verifier (VERDICT_ONESHOT0136.md, GO) to apply the lead decision: PRIMARY = per-seed slope of log(one-shot d50 / searched d50); the difference slope is secondary and a fifth condition for COMPOUNDING-CANDIDATE. Code: oneshot0136.py f90101f4, read_oneshot0136.py d00f6b79, run_oneshot0136.sh a7d0c178. Launch only with the verifier launch line (exit-code checked chain, B4 control first). No one-shot score file existed at registration. Prior exploratory context, read before registration: RESULT_STORED_AMORT_1105.md (ratchet 2302ec1) and RESULT_LOOP_PHYSICS_1105.md (ratchet 65c85b7).
