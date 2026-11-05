# SELF-FT sub-study of silicyte-0119: registration text (final; replaces AMENDMENT_1_SELF_FT_DRAFT.md sections 4 to 6 and 14)

Written 2026-11-04 21:3x ET (PowerShell clock) by the Silicyte lane lead, before any SELF-FT model call. Sources: the draft
(AMENDMENT_1_SELF_FT_DRAFT.md), its approach verdict (VERDICT_APPROACH_SELFFT.md, GO-WITH-CHANGES), the measured 8B throughput
(job 12678665: fp8 + fp8 KV 131,704 programs per H100-hour, 244.3 tokens per program, 0.25% at max_tokens, 100% `def transform`),
the builder's design as coded (`selfft/README.md`, 21:00 ET), and the power simulation with training-seed noise
(`power_selfft/POWER_SELFFT.md`). The line appended to PREREG.md is section 9 below; the rest is its body, committed beside it.

## 1. Question

Does Qwen3-8B, trained round after round on its own verified and hindsight-relabelled ARC programs, improve on held-out tasks
faster each round (compounding), merely improve (iterates), or only gain a one-time head start, against compute-matched controls?

## 2. Fixed before any model call

- Model: Qwen3-8B (`/N/scratch/bsmensah/arc26/fourth_law/models/Qwen3-8B`, sha256 of config.json and the index in META), vLLM,
  non-thinking, temperature 0.8, top_p 0.95, max 4,096 generated tokens, fp8 weights served with the LoRA (LORA_FP8_FALLBACK to
  bf16 is printed and allowed; the probe then checks the logprob delta, not the absolute value).
- Prompt: `code_only` (Ratchet FLAT render plus "Reply with the ```python block only, with no explanation before or after it.").
  Same render for sampling and training rows (`core.prompt_of`).
- Split: HELD = `random.Random(20261104).sample(sorted 400 growth ids, 80)`, TRAIN = the other 320; both sha256 printed by
  `init` and copied into RESULT.md. Sealed tasks are never loaded (`core.lock_seal`). No HELD task ever contributes a row to
  SELF, ONESHOT or PC (PC0 is the one diagnostic exception; its adapter never serves another measurement).
- Rows (RELABEL, SOAR hindsight): every program that runs without error on every demo input trains on the task defined by its
  own outputs; per TRAIN task, pooled over all rounds, at most 16 rows (8 best on the original demos, then 8 most different by
  greedy max-min Hamming over outputs); deduped by code sha and by output signature; identity, constant-output and
  finish_reason=length responses never become rows.
- Recipe: LoRA r 256, alpha 32, RS-LoRA, q k v o gate up down, lr 5e-5 constant after 10 warmup steps, 32,768 trained tokens per
  optimizer step, 1 epoch, max_len 12,288 (rows over it are dropped and counted, never cut), loss on completion tokens only,
  restart from base every round on the pooled rows.
- Budget: S = 64 samples per task per round on TRAIN and on HELD; R = 10 rounds; R_min = 8.
- Never changed after the first HELD read: R, S, the recipe, the row rule, the prompt.

## 3. Arms

| arm | what | role |
|---|---|---|
| SELF | rounds r = 1..10: sample S on TRAIN from A_{r-1} (A_0 = zero adapter), add rows, train A_r from base, sample S on HELD under A_r | primary |
| SELF_S2 | round 1 only with disjoint sampling and row-order seeds, HELD pass under its A_1 | A/A: training-seed noise sa |
| ONESHOT | R x S base samples per TRAIN task in one round (the first S are SELF round 1's), rows under the same cap, ONE training with SELF's recipe (1 epoch), HELD pass at S | iteration control |
| FROZEN | zero adapter on HELD, samples per task FLOP-matched to SELF including every retraining (units = SELF logical sampling tokens + 3 x trained tokens, divided by 80 x SELF eval_0 tokens per sample, never below S x (4R + 1)) | compute control |
| PC | Hodel arc-dsl solvers rendered as self-contained programs for the 320 TRAIN tasks (kept only if they pass all demos and the test), 2 epochs from base, HELD pass at S | positive control (transfer) |
| PC0 | the same on the 80 HELD tasks, HELD pass at S | lever check (the update reaches sampling) |
| PERT | after round R: A_R, ONESHOT and FROZEN on a perturbed HELD copy (Ratchet `perturb.py`: one colour permutation excluding 0 plus one of rot90/180/270 or transpose, demos and test together, seed 20261104) | contamination gate |

## 4. Quantities (all on HELD, read before 2026-11-11; nothing here touches the seal)

- y_r = logit of the mean over the 80 HELD tasks of the per-task demo-pass fraction among S = 64 samples under A_r (clamped to
  [1e-4, 1 - 1e-4]), r = 0..R (y_0 = base).
- SHAPE: c = quadratic coefficient of the OLS fit y_r = a + b r + c r^2 over r = 1..R; t = c / se(c) with R - 3 df. The
  round-0 to round-1 jump is excluded (it is the HEAD-START read). Basis: POWER_SELFFT.md, false positives 1.5 to 6.5% in every
  simulated world, power at m = 1.2 of 0.975 to 1.000 at R = 10; the task-bootstrap version calls linear growth compounding
  15.5 to 41% of the time once adapters carry seed noise, so it is not used.
- LEVEL: HELD tasks solved = pass@2 test-correct (PREREG sec. 5 selection on demo-passing programs, public growth test outputs)
  under A_R at S, vs ONESHOT at S, vs FROZEN at its matched budget; exact one-sided McNemar on the paired solved sets.
- Printed with every read: per-round gains y_r - y_{r-1}; sa_hat from SELF vs SELF_S2 at round 1; achieved power of SHAPE at the
  measured sa_hat and the fitted g1 (the sim re-run at those values); the training share of SELF's FLOPs; COLLAPSE
  distinct_per_task and top_copy_share per round; demo-pass-but-test-wrong share of rows.

## 5. Labels, applied in this order

1. VOID: PC0 net gain on HELD under +20 of 80 (the update does not reach sampling); or PC net gain under +5 of 80 or its exact
   one-sided McNemar p >= 0.05 against base HELD (no supervised transfer at this scale); or any FT_PROBE / FT_ADAPTER_LIVE /
   FT_UPDATE proof missing or wrong (adapter sha unchanged after a training, a0 not equal to base within 1e-3, a1+ not moving
   by more than 1e-3 in the trainer's direction); or clipped rows over 5% of any training; or any HELD task in a SELF, SELF_S2,
   ONESHOT or PC row. A VOID run is retired after two attempts.
2. UNDERPOWERED_BASE (before round 1): fewer than 8 of 80 HELD tasks have any demo-passing sample under the base at S.
3. COLLAPSED: COLLAPSE_STOP fires (distinct programs per task under A_r below half the base reading at the same S). Published
   as a measured collapse, with the round it fired.
4. UNDERPOWERED: fewer than R_min = 8 SELF rounds exist on 2026-11-10 23:59 ET (the read happens anyway and is labelled so).
5. COMPOUNDS: SHAPE t > t(0.95, R - 3) AND LEVEL beats ONESHOT and FROZEN (p < 0.05 each) AND on PERT, A_R keeps at least half
   its net solved-task gain over ONESHOT.
6. ITERATES: LEVEL beats ONESHOT and FROZEN, SHAPE fails (or PERT fails: then ITERATES-RETRIEVAL).
7. HEAD-START: beats FROZEN, not ONESHOT.
8. NULL: none of the above. Published as NULL AT THIS BUDGET with the training share printed.

## 6. Prediction (for the ledger)

Quantity: c, the SHAPE coefficient (logit per round squared) over rounds 1..R. Point 0.00, 80% band [-0.03, +0.03] (to be
replaced by the ledger's calibrated band). P(COMPOUNDS) = 0.04. Most likely labels in order: NULL or HEAD-START, then
ITERATES. Basis against: 0 PASS among the 15 weight-update rows of RESULT_PORL_CRL_AUDIT_1031; fourth-law rho_match 0.981 on this
8B (weights give head starts, not rates); the RSI lane's selftrain run 1b collapsed in 2 rounds on this 8B (5 distinct of 32);
64 samples per task per round vs SOAR's 6,000. For: SOAR (arXiv 2507.14172) is a published positive in this exact setting
(7B, Python programs, ARC-AGI-1, 14.25% to 36.25% over iterations) and relabelling is its ablated load-bearing part.

## 7. Compute and order

About 0.6 H100-hours per SELF round (25,600 programs at 101,587 to 131,704 per H100-hour plus one from-base training on at most
5,120 pooled rows), about 6 H100-hours for SELF, plus PC, PC0, SELF_S2, ONESHOT, FROZEN and PERT: ESTIMATE 12 to 15 H100-hours.
Slots: the h100-single holder when it runs, else h100-debug jobs behind the Ratchet pilot v2. Job 1 order: PC0 and base eval
(prints BASE_RATE; stops at UNDERPOWERED_BASE), then PC, then rounds. Every launch carries VERIFIED=<code verdict file>.

## 8. What a stranger reruns

Every adapter (safetensors + sha), every row file, the HELD id list, samples and exec rows, the token and seconds ledger, the
power script, and the analysis script that computes y_r, c, t and the labels from those files.

## 9. Line appended to PREREG.md `## AMENDMENTS`

```
- AMENDMENT <n> (2026-11-04 HH:MM ET, before any SELF-FT model call; Ratchet main arms unchanged): a weight-training
  sub-study on Qwen3-8B, registered as silicyte-0127 (ledger, 2026-11-04 21:50 ET, calibrated band [-0.038, +0.038]), body in AMENDMENT_SELFFT_FINAL.md (sha256 <sha>). Arms SELF (SOAR
  hindsight relabel, from-base LoRA retraining on pooled rows each round, R = 10, S = 64 per task per round), SELF_S2,
  ONESHOT, FROZEN (FLOP-matched), PC, PC0, PERT on a seeded HELD split of 80 growth tasks (seed 20261104). Primary reads
  on HELD before 2026-11-11, never on the seal: SHAPE = OLS quadratic coefficient of logit HELD demo-pass means over rounds
  1..R with a t-test on R - 3 df (task bootstrap rejected: 15.5 to 41% false compounding under simulated adapter-seed
  noise, power_selfft/POWER_SELFFT.md), LEVEL = exact McNemar on HELD pass@2 vs ONESHOT and FROZEN. Labels in order:
  VOID, UNDERPOWERED_BASE, COLLAPSED, UNDERPOWERED, COMPOUNDS, ITERATES, HEAD-START, NULL. Draft
  AMENDMENT_1_SELF_FT_DRAFT.md's sealed primary is withdrawn for this sub-study.
```

## A1 (2026-11-04 21:53 ET, before any SELF-FT model call; supersedes sections 2 "Budget", 3 row SELF_S2, 4 SHAPE, 5 item 4 and the ledger quantity of silicyte-0127)

Trigger: the independent sim verdict ratchet/testpower/VERDICT_SIM.md (21:47 ET) models training randomness as a random walk in skill
(each adapter samples the next round's data, so a lucky round persists). Under that noise, any single-trajectory curvature test is
invalid at S = 64: false compounding 0.18 to 0.51 for one seed at any n (its sec. 2c). My own sim (power_selfft/POWER_SELFFT.md) drew
independent per-round adapter offsets, which is why its OLS t-test looked valid; that finding holds only for independent offsets and
is withdrawn as a gate basis. Changes:
- Budget: K = 4 independent seeds, R = 8 rounds per seed, S = 64 per task per round on TRAIN and HELD. One run directory per seed
  (runs/v2_s1 .. v2_s4), same HELD/TRAIN split (seed 20261104), different sampling and training seeds. Round 0 (base) is scored once
  in v2_s1 and shared. FROZEN, ONESHOT, PC and PC0 live in v2_s1. SELF_S2 is dropped (seeds 2 to 4 replace it).
- SHAPE (primary): per seed k, Rasch skill theta_{k,r} for r = 0..R from the per-task demo-pass counts out of S (binomial logit with
  one difficulty per HELD task, fit jointly over all seeds and rounds; tasks with zero or all passes in every unit carry no
  information and drop out); c_k = OLS quadratic coefficient of theta_{k,r} on r = 0..R; t = mean(c_k) / (sd(c_k) / sqrt(K)),
  df K - 1; COMPOUNDS-SHAPE iff t > t(0.96, K - 1) (one-sided alpha 0.04, because the Rasch rule's realized false-positive rate
  reads 0.037 to 0.065 across VERDICT_SIM's 18 stress cells). ST_LQ (logit of pooled per-seed solve rate) is reported beside it.
  Basis: VERDICT_SIM sec. 4: n = 80, R = 8, K = 4 holds power 1.000 / 1.000 / 0.986 at tau 0.05 / 0.10 / 0.20 for m = 1.2, and 0.913
  at g1 0.10; false positives 0.020 to 0.054 in every grid cell. Definition claimed: ACCELERATION (H0 m <= 1), the handoff's
  "per-round multiplier m > 1 with a lower bound above 1".
- LEVEL: per seed, HELD pass@2 under A_R vs ONESHOT and vs FROZEN; the gate uses the seed-majority (at least 3 of 4 seeds beat each
  control by exact one-sided McNemar p < 0.05) and reports all four.
- UNDERPOWERED: fewer than K = 3 seeds reach R = 6 by 2026-11-10 23:59 ET (VERDICT_SIM minimum design); the read is still made.
- Printed before any label: tau_hat (between-seed sd of round-to-round gains), g1_hat, the per-task difficulty spread, and the power
  of the registered rule re-simulated at those values.
- Ledger: silicyte-0127's quantity becomes mean over seeds of c_k (Rasch theta scale); point 0.00, band unchanged.

## A2 (2026-11-04 21:58 ET, before any SELF-FT model call)

- Secondary read, reported, never gating: NON-DIMINISHING (H0 m <= 0.9). Per seed, m_hat by profile least squares on the Rasch theta
  curve (VERDICT_SIM sec. 2a, sim_verify_m.js); one-sided t-test of log m_hat across seeds against log 0.9. At R = 8, K = 4, tau 0.10
  its power at m = 1.0 is 0.638 (VERDICT_SIM table), so a miss is reported as underpowered for that claim, not as diminishing.
- Primary definition stays ACCELERATION (H0 m <= 1), the handoff's "per-round multiplier m > 1 with a lower bound above 1".
- Cited trap on our own record, to be quoted beside any SHAPE read: RESULT_BOOTLLM_FRONTIER_V1.md, rounds 0 to 5 read COMPOUNDING
  (one seed, task bootstrap, Delta slope 0.237 [0.057, 0.420]) and the registered confirmation over rounds 6 to 9 read LINEAR (slope
  -0.008 [-0.060, 0.049]).

## A3 (2026-11-04 22:03 ET, before any SELF-FT model call; from the code verdict selfft/VERDICT_SELFFT_CODE.md)

- PC and PC0 recipe: 6 epochs (was 2) with warmup = max(1, round(0.1 x total optimizer steps)); the verdict found PC0 would get 16
  optimizer steps, 10 of them warmup, too few for a lever check whose gate is +20 of 80. SELF and ONESHOT recipes unchanged. PC0's
  gate stays +20; PC's stays +5 net with exact one-sided McNemar p < 0.05.
- Seeds: run-level seed (0 for v2_s1, 1 to 3 for v2_s2 to v2_s4) enters the per-request sampling seed hash, the trainer seed and the
  LoRA init; seeds 2 to 4 read round 0 from v2_s1 (shared base unit) and never sample their own eval_0.
- Pinned per run: served quant (fp8 or bf16, recorded per unit; a run never mixes them), prompt sha (RUN.json), code sha covering
  selfft and the Ratchet modules it imports. A job stops issuing work 300 s before its 3,300 s deadline and resumes in the next job.
- Only SELF can write the run-wide collapse STOP; a0 is checked against base on a fixed probe at its first serve.

## A4 (2026-11-04 22:08 ET, before any SELF-FT model call; from rsi48/VERDICT_RSI_48H_PLAN.md required changes 1 to 10 and 13)

1. 0127 is the only GPU spine of the 48 h plan. RSI_48H_PLAN.md sec. 3 Rank 1 (dual-scale gate, tau rule, R-MATCH) is not registered
   and never gates; E_r and R-MATCH may be printed as single-seed descriptions. No "0119 Amendment 1 v2" is written into PREREG.md.
2. One read time: when K = 4 x R = 8 is complete, or at 2026-11-10 23:59 ET, whichever is first. No interim label. Before then only
   J1 numbers, PC0/PC, tau_hat, g1_hat, the re-simulated power and the instrument results are published.
3. One launcher: ratchet/selfft/debug_step.sbatch (or launch_in_holder.sh in a running holder); a launch counts only when the step's
   own META line and STATUS.json appear within 45 s. KV cache dtype is fixed once, before the first job, at the vLLM default (auto,
   bf16 KV): fp8 KV buys 1.064x (8,936.9 vs 8,665.6 tok/s, job 12678665) and has never been run with LoRA; it is recorded per unit.
4. J1 quantities (read from the first pc0 job on v2_s1, registered here before they exist): BASE_RATE (HELD tasks with any demo-pass
   at 64 under a0; kill UNDERPOWERED_BASE if < 8 of 80; prediction 18 [8, 32]); P = programs per busy H100-hour on the LoRA serve
   path (prediction 75,000 [40,000, 118,000]); p = demo-pass per program (0.05 [0.015, 0.12]); Y = P x p; trained tokens per second
   (6,000 [3,500, 9,000]); STARTUP_S (200 [120, 400]); offline-bench node control (bench_throughput_8b.py, fp8 weights, auto KV, no
   LoRA, 10 growth tasks x 64): must reach 0.85 x 123,808 programs per hour, else the job is VOID for P and reruns on another node.
   Jobs per round j = 1 if a full round fits 3,240 s at the measured rates, else 2; the reachable K x R follows and is printed.
5. PLANT pair (instrument control, required for COMPOUNDS): PLANT set = 15 HELD tasks with base demo-pass fraction under 0.5 at 64
   (from SELF eval_0), drawn by seed 20261105 (scaled monotone if fewer qualify). PLANT-RISE: adapters from base on the Hodel renders
   of cumulative planted sets of 1, 3, 7, 15 tasks (gains double). PLANT-LINEAR: cumulative 2, 4, 6, 8 (constant gains). Each with
   K = 3 planting seeds (planted order and training seed differ), each adapter sampled on all 80 HELD at 64, classified by
   read_selfft.py exactly as SELF. Predicted: RISE reads COMPOUNDS-SHAPE, LINEAR does not. Both as predicted = INSTRUMENT-OK; else
   INSTRUMENT-VOID and no rate is read. Scope: PLANT tests the scorer and classifier, not the random-walk noise model (planted
   adapters train independently from base). Planted adapters are diagnostic only. PLANT-STEP dropped.
6. ONESHOT: 2 seeds. Each gets SELF's extra training cost converted to extra TRAIN base samples by FROZEN's unit rule (3 x trained
   tokens), relabelled under the same 16-row cap, one training with SELF's final-round recipe; never converted to HELD samples.
   LEVEL vs ONESHOT: per SELF seed k, per-task score SELF_k (pass@2 solved, 0/1) minus the mean of the two ONESHOT seeds (0, 0.5, 1);
   one-sided exact sign test on non-zero differences, p < 0.05; gate = at least 3 of 4 SELF seeds; spread reported.
7. NEW-REACH (secondary): HELD tasks with a demo-pass under A_R in any seed and zero in FROZEN's full matched budget, against the
   FROZEN leave-one-chunk null (chunks of 64; 95th percentile). Every positive is tagged SHARPENING unless NEW-REACH fires.
8. Every result sentence names the definition: "accelerating (m > 1)", with m_hat and its CI. NON-DIMINISHING (H0 m <= 0.9) needs
   K = 6 (VERDICT_SIM sec. 2a, 4) and is reported as underpowered for that claim.
9. Basis against (record): bootllm2 LINEAR on confirmation (rsi48/R2_OUR_RECORD.md:84; RESULT_BOOTLLM_FRONTIER_V1.md), CONT = ORIG and
   mext KILL (R2_OUR_RECORD.md:86), fourth-law rho_match 0.981; SOAR adjudication VERDICT_APPROACH_SELFFT.md:25-47. A NULL reads "at
   S = 64, R = 8, no mutation, no refinement (SOAR: 6,000 per task per round with refinement; CodeIt: 100 meta-iterations with mutation)".
10. Named next arm, NOT run in this window, prior art CodeIt (2024): task-creating mutation (a mutated verified program run on a task's
    demo inputs defines a new task correct by construction). Recall run 22:1x ET: ecall.py q "task-creating mutation CodeIt mutated
    program new task correct by construction" -> RESULT_D90_MECHANICS_1031.md (mutation testing for demo-passing-but-wrong programs, a
    different mechanism), RESULT_EXEMPLARS.md, PREREG_ENGINE_VS_FRONTIER.md; no prior run of this mechanism. Runs only under a GPU
    release, with its own ONESHOT and seeds, under its own registration.
11. Slots: h100-debug jobs from 2026-11-06 00:00 to 06:00 ET go to 0127 rounds, not the Ratchet pilot.

## A5 (2026-11-04 23:27 ET, before any SELF-FT model call; supersedes the "round 0 scored once and shared" lines of A1 and A3)

- Every seed samples its OWN round 0 (SELF eval_0 under the zero adapter, its own sampling seed, 80 HELD x 64); +0.13 H100-h in all.
  Measured (power_selfft/sim_registered_0127.js, 1,000 runs per cell, n 80, R 8, K 4, S 64, p0 0.2, g1 0.25): with one shared round 0
  and the joint fit, false compounding at m = 1.0 is 0.079 at tau 0.02 (0.102 at 600 runs) and 0.043 at tau 0.10; with an own round 0
  per seed and the joint fit it is 0.045 and 0.035; power at m = 1.2 is 1.000 in all four. The joint Rasch fit over all seeds and rounds
  stays (equal to the per-seed fit in every cell).
- Zero-cost diagnostics printed every round (RESEARCH_COMPOUNDING_LEVERS_1104.md, structural note): rows selected, share of rows new
  this round, TRAIN tasks demo-passed for the first time, and how many TRAIN tasks have filled their 16-row cap. The pooled cap tops out
  at 5,120 rows; a run whose rows stop changing is reported as ROW-SATURATED beside its label.
- Named conditional arm, not run unless supply after SELF's 4 x 8 schedule allows (cut first): FRONT, the same TRAIN sampling budget
  moved from mastered tasks to tasks with zero or rare passes, paired seed by seed with SELF, kill at round 3 if its newly passed TRAIN
  tasks do not exceed SELF's in at least 3 of 4 seeds. Its power for the arm-minus-SELF curvature contrast is simulated and registered
  in its own amendment before its first job.
