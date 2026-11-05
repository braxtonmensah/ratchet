# REGISTERED 2026-11-05 17:08 ET as silicyte-0132 (codes arm T), after VERDICT_ARMT.md GO (14:19) and the POSCTL PASS (17:07: adapter 128/144 vs base 108/144 at d >= planted d, Fisher p 0.0017), before any arm T round-1 sample. Text below unchanged from PREREG_ARMT_DRAFT.md sha256 d95219e2...

# PREREG_ARMT_DRAFT v3: codes arm T, climb-trained proposer weights (silicyte-0122 follow-on)

DRAFT for the lead, written 2026-11-05 14:1x ET before any arm T sample exists. It supersedes v2 (verifier NO-GO, 09:41 ET; ARMT_FIXES.md lists every change). Once registered (a deviation in registry/HUNT_REGISTRY.md, with the armT files hashed), nothing below changes without a logged deviation written before the data it affects.

## Prior evidence this design answers

- **RESULT_SELFTRAIN_V2_RUN2A.md**, Qwen3-8B LoRA self-training against a frozen twin, 640 rollouts per seed:
  - not a pass (3/64 vs 3/64);
  - lora_B reached about 2.46 and KL about 0.016, so the weights moved;
  - validity went to 64/64 and copies rose. The programs became VALID, not BETTER (SHARPENING).
- **RESULT_TPROBE_V1.md:** no transfer.
- **Verifier, v2:** a copied or derived warm-start matrix could make a PASS. 57 of the 138 gap points were free subcodes of a shown matrix, and the sha-based tie rule let a pasted BASE into the SFT set.

So v3:
- measures progress against the FREE-DERIVATION CLOSURE of everything known;
- trains only on strict climbs proven not to be free derivations;
- checks copies at code level;
- runs 3 seeds per arm.

## Hypothesis

**H1.** Fine-tuning Qwen3-8B on its own exactly verified strict improvements makes it climb further than the same model with frozen weights, given equal samples, prompts and seeds, in the closure sense on cells where a better code is known (and not by re-deriving known matrices).

**H0.** It does not. Either the gap is within FROZEN-vs-FROZEN spread, or the gap is explained by derivations of known matrices, or the pattern is sharpening.

## Arms

Both arms use:
- Qwen3-8B in non-thinking mode;
- the same prompts, with a FIXED warm start, so any gain must be in the weights. Snapshot files: elites.json d853af31..., train_elites.json 4c5f1d63..., known_warm.json 83cad728..., failures a4b84f04..., and the archive pinned to its first 14,366 lines (sha d1a5b910...). TRAIN prompts show the 2 source matrices of each cell's d0;
- the same cells and N, the same per-sample seeds and sampling (T 0.7, top_p 0.8, top_k 20, max 8,192 tokens);
- one vLLM engine per round;
- the registered scorer (MAXIDX 4) on equal core shares.

**TRAINED_s<k>** (k = 0, 1, 2) samples from LoRA A_{r-1} (A_0 = base). Its SFT set, TRAIN cells only, contains every template whose best instance is PROVEN not to be a free derivation of a known matrix (code-level test `derives`; warm-start matrices plus the arm's earlier-round climb matrices) and beats the arm's running best. There is no tie rule and nothing at or below the running best. An instance whose test is unknown does not qualify. Training is one pass from A_{r-1} (no reset), LoRA r16/a32, lr 1e-4, accumulation 4, response-only loss. An empty set skips training.

**FROZEN_s<k>** (k = 0, 1, 2): base weights; it keeps its own running bests by the same rule.

Round 1 is shared: TRAINED r01 = FROZEN r01.

**Cells.**
- **TRAIN (12; trained on).** PCB2_4 [75,19]_4, PCB2_1 [100,9]_7, PCB2_2 [109,9]_8, T01 [106,6]_8, T02 [107,6]_8, T03 [94,10]_3, T04 [100,15]_7, T05 [100,16]_7, PCB2_3 [75,17]_4, T06 [75,16]_4, T07 [75,18]_4, T08 [107,26]_8.
  - Corrected gaps (closure d0 to best known d): 1, 3, 3, 5, 6, 4, 11, 14, 3, 4, 2, 25. Total 81 (138 before the closure).
  - None is 0. None lies in a registered plateau.
  - Cells sharing a source matrix move together: {PCB2_4, PCB2_3, T06, T07}, {T01, T02, T08}, {PCB2_1, T04, T05}.
  - N = 9 each.
- **EVAL (10; never trained on):** #8, #11, #14, #15, #25, #26, #34, #37, #39, #55, with N = 2 each. #8 and #55 are CONFOUNDED: their elites or templates appear in TRAIN prompts, so they are excluded from the tertiary transfer read. Claims on them still count.

**Volume:** 128 rollouts per stream per round, 1,280 per seed over 10 rounds (1,080 on TRAIN cells), against the prior study's 640.

**Positive control (gate, run first).**
- POSCTL is trained only on 1 planted snapshot elite at d = table lb for each of 9 cells: EVAL elites plus PCB2_4, in a separate adapter that is never reused. The dose is 36 rows (9 steps), more than a loop round's 0 to about 15.
- It is compared with BASECTL on the same prompts and seeds, N = 16.
- PASS = POSCTL reaches d >= the planted d more often than BASECTL (one-sided Fisher p < 0.05).
- It shows the update moves the proposer, not that it climbs. BASECTL can also copy the shown elites, which limits power.

## Definitions

Free derivation: subcode, shortening, puncturing, padding, extension (and, for the copy test only, lengthening by the all-ones augment), with column order kept.

For arm A, seed k and TRAIN cell c (all values are exact d from the registered scorer):
- d0_c = the closure of the pinned warm start: max over pinned matrices [n2, k2, d2] with k2 >= k of d2 - max(0, (n2 - n) - (k2 - k)), a proven bound.
- rb_c(r) = max(rb_c(r-1), the closure of every valid instance of round r onto c).
- rb_nd_c(r) = the same, but only over instances PROVEN not to be free derivations of a warm-start or earlier-round matrix.
- t_c = the best known d.
- closure_c(r) = min(rb_c(r), t_c) - d0_c, and closure_nd_c(r) likewise.

## Metrics

- **PRIMARY:** G_k(R) = sum_c closure_c(R) for TRAINED_s<k> minus FROZEN_s<k>, and Gnd_k(R) the same with closure_nd, at R = 10.
- **SECONDARY:** the per-round climb gap TRAINED minus FROZEN, and its OLS slope over r = 2..10 per seed (mean, t across seeds, df 2).
- **TERTIARY:** EVAL cells excluding #8 and #55. The summed best (d - lb) gap per round, plus every instance with d >= lb + 1 in claims/ (any EVAL cell).
- **DIAGNOSTICS** (every round, both arms, printed whatever the verdict):
  - valid share;
  - copy share: the derivation share of a fixed 48-matrix sample, the first 48 distinct by sha256;
  - row-overlap >= 0.5 share;
  - for every climb event: derivation status and overlap;
  - distinct matrices;
  - lora_B norm, and KL(adapter || base) on a fixed probe (the EVAL #11 prompt and elite, 2,048 tokens);
  - SFT rows.

## Decision rule (fixed before any data; read_armt.py --R 10)

**PASS** iff ALL of these hold:
1. 3 seeds per arm, with round 10 complete;
2. for EVERY seed k: G_k(10) >= M AND Gnd_k(10) >= M, where M = max(2, D_F) and D_F = the largest FROZEN-vs-FROZEN closure spread over seed pairs at R;
3. **copy rule:** fewer than half of TRAINED's TRAIN-cell climb events (rounds 2 to 10, all seeds) are copy-like, meaning not proven novel or row overlap >= 0.5 with a known matrix;
4. no COLLAPSE or NO_UPDATE flag.

**Outcomes:**
- **FAIL** otherwise. It is labelled COPY_PASS when only items 2 (Gnd) or 3 fail, and SHARPENING when, at R, TRAINED's valid or copy share is >= 0.10 above FROZEN's or its distinct matrices are < 0.8 x FROZEN's.
- **INCOMPLETE** if round 10 is missing in any seed.

**False-positive rate**, from fpr_sim.js:
- **Model:** 12 cells with the corrected gaps, in 5 clusters sharing a source, so climbs are lumpy and propagate through the closure; 9 regimes of climb rate and size; round 1 shared; arms independent under H0.
- **Result:** the worst-case FPR of items 2 (G part) is **0.025 at K = 3** (0.111 at K = 2; 5,000 reps per regime).
- The Gnd and copy items only lower it. Shared sampling seeds are not modelled, which lowers it further.
- **Power** (same sim): TRAINED at 2x FROZEN's climb rate gives 0.10 to 0.36; at 3x, 0.23 to 0.67. The test detects only a large effect, and a FAIL is "no large effect", not "no effect".

## Stop rules

1. Positive control FAIL: do not launch TRAINED or FROZEN (a retry is a new registration).
2. End: rounds 1 to 10; any extension is a new registration.
3. NO_UPDATE: if every TRAINED SFT set in every seed is empty through round 6 (the adapter never left the base), stop. The result is FAIL (NO_UPDATE).
4. COLLAPSE: if a TRAINED seed's TRAIN-cell distinct matrices are < 0.5 x FROZEN's for 3 consecutive rounds, stop. The result is FAIL (SHARPENING).
5. UNSCORED: a stream-round with more than 5% of its instances unscored is re-scored before it counts. If that is impossible, the round is excluded for both arms of that seed.
6. Time: if round 2 takes more than 150 min, N_TRAIN goes 9 to 6 for both arms from round 3 (logged).
7. Allocation end before round 10: INCOMPLETE. Resume with the same command; it is resumable and deterministic.
8. STOP file: INCOMPLETE unless round 10 is done.

## Fairness asymmetries (stated)

- Only TRAINED pays training time.
- LoRA requests decode somewhat slower than base requests inside the shared engine.
- The 35 min per-stream score deadline could leave unequal unscored shares below the 5% flag.
- A copy test that hits its budget, or needs more than 10 column deletions, is 'unknown'. It never counts as novel, for SFT or for Gnd.
- The copy test misses column permutations that do not keep order, so its copy share is a lower bound.

## Claim and submission rule (unchanged from the hunt registry, D8 items 5, 8, 15)

- **EVAL cells.** An instance (or its proven free derivation) with d >= stored lb + 1 is a candidate only: armT/claims/<stream>/rNN/<tag>/ with the claim_check.py `route` line and NOT_SUBMITTED.txt. No submit path, and `claim` is never called.
  - **Bar** = max(codes_selected.json lb, table_bounds.json lb, live BKLC.php lb) + 1. The stored lbs must agree.
  - **The lead runs** stage B/C (verify_code -x; score.py --xcheck with md_interim at 2 or more information-set seeds; GUAVA where q^k <= 2e7) and HUNT_PLAN_V2 2.8 items 2 to 8 on a fresh node.
  - **A claim that rests on a derivation** needs the derived matrix built and scored first.
- **TRAIN cells are not registered cells.** Reaching the known best is a rediscovery. Exceeding it goes to claims_unregistered/ for the lead and needs its own registration.
- **Credit line:** "Qwen3-8B proposer program (armT, LoRA climb-trained, adapter <sha256>), template <sha256>".
- **Nothing is submitted to codetables.de or anywhere else by any agent.** Submission waits for the founder's exact words "YES, YOU MAY SUBMIT <file>".

## Files to hash at registration

The sha256 values are in BUILD_ARMT.md section 1 (they are taken after the final smoke).
