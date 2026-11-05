# AUDIT PART 2: the UNCHECKED items of AUDIT_RSI_CONCLUSIONS_1105.md

Second adversarial auditor, read only, 2026-11-05 18:2x to 18:5x ET. Nothing registered was edited, no Slurm job or step was touched,
nothing was committed. All numbers were recomputed on Quartz (login h1/h2, /usr/bin/python3 3.6.8 -I, stdlib only) by scripts in
/N/scratch/bsmensah/audit1105b/ (a0133.py, aleak.py, aleak2.py, amap.py, alora.py; logs beside them).

## Verdict table

| # | Claim | Verdict | Key numbers |
|---|---|---|---|
| 1 | 0133 premise: "top-20 bigram macros shrink 0128's programs 27.4%, so there is macro fuel" | OVERSTATED | 28.1% reproduced (4,713 programs). 11 of the 20 bigrams (61.8% of their uses) are compositions inside one op family that equal a single would-be op exactly. The world's own i.i.d. Zipf generator, with no learner, gives 16.3%. With drop/trim/rot k unbounded and sub runs as one base map, the saving falls to 13.2%. |
| 1b | "shorter programs mean deeper reach per search step" | NOT SUPPORTED (the build's own smoke says no) | smoke/beam.log: reach 4 with primitives and with the 64-macro library; the library costs 2.07x action executions and 3.76x primitive executions. smoke/budget.log: 12 vs 13 verified per 120 cal-s. Cost floor: per call 0.1280 s at 54 actions, 0.1384 at 74, 0.1614 at 118. |
| 1c | world size | 54 ops | world.json n_ops 54; the policy prompt (reachlaw.py DESC) and the beam list all 54. "42" is the number of distinct ops in 0128's verified programs: the 12 cutL/cutR ops are never used. |
| 2 | 0128 leakage: training never touched MEAS 29000 or MEAS_DEEP_k | SUPPORTED | 0 tid, 0 task, 0 input overlap in all 44 rebuilt rounds (4 seeds x rounds 0-10) vs MEAS 29000, and 0 of 41,836 actual trained rows. The stored logs cover MEAS_DEEP_k only. |
| 3 | s3/s4 redone round 10 equals the archived scored-only round 10 | SUPPORTED | fixed_rows 300 of 300 equal for s2, s3 and s4; d50_fixed 4.900 / 4.305 / 4.473 unchanged. |
| 4 | LoRA: "consecutive dW cosine 0.05-0.09 shows the weights reset" | WRONG as evidence (reset is true by code only) | lora2.py output does not exist anywhere; recomputed with stdlib. Raw A cos is within +/-0.0015 for every pair, so there is no shared init, s1 included. A row-space overlap is 0.004-0.010 (random 0.0035), the same consecutive and cross-seed at a given round. dW cos is 0.051-0.063 consecutive (80-88% shared rows) vs 0.033-0.050 cross-seed (about 5% shared rows). |
| 5 | MAP held-out vs map concept types | DIFFERENT TYPES (strengthens "underpowered") | 36 of 82 BASE held-out solves (43.9%) come from 5 constant-output concepts (5 of 40 held, 3 of 60 map). 6 held concepts have the same target function as a map/dev concept and give 2 of 82 solves. |
| 6 | published claims after 745b4a9 | 9 still OVERSTATED or STALE | sec. 6 |

## 1. 0133 premise (macros)

Corpus. I rebuilt the programs independently from runs/*/own*.jsonl (src == own rows, chains r = L..1, one tid; GUIDE own_0 skipped as
a copy of FRONTIER round 0). Snapshot 18:34 ET: 4,713 programs, 3,016 distinct, 0 broken chains, and all 4,713 re-execute to their
stored targets with consol.run_prog. The corpus grows while the loops run, so counts differ by snapshot: the LADDER smoke at 18:07
saw 4,552 / 2,911. No cut of my snapshot gives 2,604 exactly (rounds <= 9 distinct 2,600; non-GUIDE rounds <= 10 distinct 2,634).
The 27.4% does not depend on the count: I get 28.1% on all programs, and 25.7-27.6% early -> late per FRONTIER seed (smoke: 25.7-27.6%).

Op semantics (/N/scratch/bsmensah/silo/bootseed/lib/consol.py, the 0128 world; a copy is at fourth_law/consol.py):
- drop k = s[k:], trim k = s[:-k], rot k = s[k:] + s[:k] for k = 1..5; sub_XY = s.replace(X, Y). run_prog returns None only if a
  state is empty or the final string is shorter than 4. Slicing never errors, so nothing truncates differently.
- drop3 drop3 equals a would-be drop6 on 3,000 of 3,000 random strings, including the step-wise validity check the macro executor
  uses. The same holds for drop3 drop5 = drop8, drop3 drop4 = drop7, drop5 drop5 = drop10, rot3 rot3 = rot6, drop3 trim3 = slice.
- Every sub-sub bigram equals one base map (sub_CT sub_TA = map C,T -> A).
- None of the top 20 equals an existing single op, which is why the MDL check (REJECT_EQUIV) keeps them. drop6 is indeed not a
  primitive. But it is missing only because the op set stops at 5.

Top 20 bigrams (15,679 adjacent pairs). obs/exp is against independence of the two ops:

| bigram | count | obs/exp | same family | equals |
|---|---|---|---|---|
| drop3 drop3 | 2326 | 1.84 | yes | drop6 |
| sub_CT drop3 | 1147 | 1.64 | no | |
| sub_TA sub_CT | 466 | 2.41 | yes | base map |
| sub_CT sub_TA | 459 | 2.37 | yes | base map |
| drop3 drop5 | 459 | 1.91 | yes | drop8 |
| mask_GAATTC sub_CT | 429 | 3.78 | no | |
| drop3 drop4 | 414 | 2.27 | yes | drop7 |
| rot3 drop3 | 303 | 1.13 | no | |
| sub_TA drop3 | 294 | 0.84 | no | |
| rot3 rot3 | 292 | 5.10 | yes | rot6 |
| drop3 rot3 | 277 | 1.03 | no | |
| sub_CT rot3 | 266 | 1.78 | no | |
| drop3 trim3 | 254 | 1.85 | no (drop+trim) | slice 3,3 |
| sub_CT sub_GT | 226 | 4.31 | yes | base map |
| drop5 drop5 | 197 | 4.31 | yes | drop10 |
| sub_TA sub_CA | 193 | 15.25 | yes | base map |
| sub_GT drop3 | 178 | 1.88 | no | |
| sub_CT sub_AG | 165 | 3.28 | yes | base map |
| sub_CT sub_TG | 157 | 2.98 | yes | base map |
| drop3 rot4 | 155 | 1.28 | no | |

What the 28% is made of:
- Within-family members: 11 of 20 types, 5,354 of 8,657 uses (61.8%). With only the 9 cross-family members the saving is 13.6%.
- Op-set poverty. Merge drop/trim/rot runs into one op with unbounded k (E1): programs get 22.0% shorter with no macros, and the
  top-20 saving on top falls to 19.7%. Also merge sub runs into one base map (E2): programs get 34.2% shorter, and the top-20 saving
  left is 13.2%.
- The generator's Zipf prior. The world draws ops i.i.d. Zipf(1.1) over a fixed order (consol.py docstring: "NOT a designed
  hierarchy"); sub_CT and drop3 are Zipf ranks 1 and 2. Gold programs from W.make_task at the same length distribution, with no
  learner, give 16.3%. Raw i.i.d. Zipf sequences give 17.5%. 11 of the generator's top 20 are the same bigrams.
- Why own exceeds the generator (obs/exp up to 15): the solver writes many different gold programs in one canonical form, for example
  any drop6 as drop3 drop3.
- Persistence (early library covers late rounds, 26-27% vs 28-29%) is what a stationary i.i.d. generator gives by construction. It is
  not evidence of an abstraction that grows. The smoke's per-round MDL compression rises over rounds 1-5 and then sits at 24-34%
  through round 10 in every seed: a plateau, not growth.

Reach per search step.
- Physics floor, from the frozen cost model (ladder0133.py:95: 0.0998 + 0.000522 x n_actions per policy call):
  - per call: 0.1280 s at 54 actions, 0.1384 at 74, 0.1614 at 118;
  - steps x per-call cost relative to primitives: 0.778 (top 20) and 0.764 (64 MDL macros).
  - So the best case is about 22-24% more tasks per cal-s. That holds only if per-step policy accuracy does not drop with 74-118
    choices. It is a one-time level shift, not a gain that grows.
- The build's own smoke already measured this. smoke/beam.log, stub policy, 64 tasks at depths 2-16:
  - primitives: reach 4 [8 4 0 2 0 0 0 0];
  - library(64): reach 4 [8 5 0 2 1 0 0 0], at 2.07x action executions and 3.76x primitive executions.
  - smoke/budget.log, sharp stub: 13 verified per 120 cal-s with primitives, 12 with the library.
- No measured row shows deeper reach per step or per cal-s.

Verdict.
- "Macros shorten programs 27% so there is macro fuel": OVERSTATED. The 27-28% is real, but about half of it (14.5-14.9 of 28.1
  points: 28.1 -> 13.6 without the within-family members, 28.1 -> 13.2 on the completed op set) is the op set stopping at k = 5 plus
  the sub family, and what is left (13.2-13.6%) is below what the i.i.d. Zipf generator gives with no learner (16.3%).
- "Shorter programs mean deeper reach per search step": NOT SUPPORTED. The project's own smoke shows equal reach at higher cost.
- A fair LADDER control is a WARM arm whose op set is enriched once with the would-be family members (drop/trim/rot 6-15, base maps).
  The library must beat that, not the 54-op primitives.

## 2. 0128 leakage

- Stored logs (ext/):
  - overlap_actual_1323.log: 37 rounds, s1 r0-10, s2 r0-8, s3 r0-7, s4 r0-6, GUIDE r0. ACTUAL_TOTAL data and frontier [0, 0, 0].
  - overlap_deep_k_t30_hi10.log: constructed pools k 1-4, t 0-30, 297,600 frontier tasks per deep pool, 0 tid, 0 task, 0 input;
    MEAS_DEEP_k vs MEAS 29000: 0; deep pools pairwise: 0.
  - Both check MEAS_DEEP_k only. No stored log checks the training pools against MEAS 29000, the ruler of the registered A1 read.
- My check (aleak.py, aleak2.py) against MEAS 29000 (300 tasks, 1,800 inputs, tid md5 4fb14802):
  - Rebuilt data and frontier pools of all 44 completed rounds (s1, FRONTIER_s2..s4, rounds 0-10, with the round files' own seeds and
    windows): tid 0, task 0, input 0. The legacy s1 frontier has no MEAS skip, so this was a real check, and it is still 0.
  - All 41,836 actually trained rows (20,918 own + 20,918 hindsight): 0 tids in MEAS, 0 states equal to a MEAS input, 0 rows equal
    to a MEAS task, 0 states in any MEAS_DEEP_k input set.
  - 160 own rows have a target string equal to some MEAS output. All 15 strings are homopolymers (GGG..., AAA..., TTT...), which any
    sub chain produces. Their inputs differ, so this is not leakage.
- Verdict: SUPPORTED, 0 overlap on both rulers.

## 3. s3/s4 round-10 equality

- runs/FRONTIER_sk/round_10.json (redone: has train_pool_depths) vs ext/archive/FRONTIER_sk/round_10.scored_only.json:
  - s2: 300 of 300 fixed_rows equal (md5 cae59d8f), d50_fixed 4.900;
  - s3 (written 18:07): equal (766a9ed3), 4.305;
  - s4 (17:59): equal (c8c733e2), 4.473.
- This agrees with ratchet silicyte-0128/post_1105_postfix.log (POST OK x3, commit e3157e7).
- Verdict: SUPPORTED. The archived round 10 used in the A1 read equals the trained round 10.

## 4. LoRA anatomy

- lora2.py and its output do not exist. I searched /N/scratch/bsmensah to depth 6, /tmp on login h1 and h2, and the laptop
  rsi_sprint tree. Only the first job's files are on h1 /tmp (bsm_lora_anatomy.py, lora_anatomy_s1.json, 14:07).
- I recomputed with stdlib from the adapters: alora.py reads the F32 lora_A tensors from adapter_model.safetensors directly.
  - Raw A cosine is computed on all 252 modules.
  - A row-space overlap ||Q1 Q2^T||_F^2 / 16 is computed on 28 modules (layers 0, 12, 24, 35 x 7). The random value is 16/d_in, 0.0035
    on average.

- I also computed dW = (alpha/r) B A cosine on the same 28 modules (adw.py) for a few consecutive and cross-seed pairs.
- Shared training rows: P_{t+1} is fit on seed256 + own_0..own_t (replay-all), so consecutive fits share 80-88% of their rows (s2:
  N_4/N_5 = 3,394/4,232, N_8/N_9 = 6,618/7,530). Cross-seed fits share only seed256 (256 rows, 3-6%).

| pair | raw A cos (252 modules) | A row-space overlap (random 0.0035) | dW cos, 28 modules pooled |
|---|---|---|---|
| s1 consecutive P_1-P_2 ... P_9-P_10 | -0.0010 to +0.0015 | 0.0052 -> 0.0093 (rises every round) | P_5-P_6 0.052 |
| s2 consecutive P_0-P_1 ... P_9-P_10 | -0.0009 to +0.0013 | 0.0042 -> 0.0096 | P_5-P_6 0.051, P_9-P_10 0.063 |
| s3 consecutive P_0-P_1 ... P_9-P_10 | -0.0007 to +0.0005 | 0.0041 -> 0.0100 | |
| cross-seed, round 1 (s1s2, s2s3, s3s4) | -0.0004 to -0.0001 | 0.0050 / 0.0051 / 0.0050 | |
| cross-seed, round 5 | -0.0002 to +0.0002 | 0.0071 / 0.0066 / 0.0061 | s2s3 P_6: 0.033 |
| cross-seed, round 10 | -0.0004 to +0.0004 | 0.0085 / 0.0084 / 0.0087 | s2s3 0.040, s1s2 0.050 |

Reading:
- The first audit's hypothesis that s1 reuses one A init across rounds (no torch.manual_seed) is WRONG. The raw A cosine is
  |cos| <= 0.0015 for every pair, s1 included, so every fit starts from an independent A.
- A barely leaves its random row space. The overlap is 1.2-2.9x the random value, and it grows with round in the same way within a
  seed and across seeds, which tracks the number of optimizer steps, not carry-over.
- Consecutive fits share 80-88% of their data, yet their dW cosine (0.051-0.063) is only 1.0-1.9x that of cross-seed fits with
  about 5% shared data (0.033-0.050). So the 0.05-0.09 is what independent inits give on similar data in the same world.
- The cosine shows neither a reset nor a carry. The reset is true by code only (fresh get_peft_model each round, reachlaw.py, and
  per-round torch seeds 1000 k + t + 1 at bootseed0128.py:451).
- The same-data refit baseline below would close this; cross-seed is the nearest baseline already on disk.

Same-data refit baseline: the GPU job to run (NOT submitted).
- One H100, about 2 x the round train time; FRONTIER_s2, round t = 5, so the fit is P_6, train_examples 4,232, adapter_md5
  022540b217bc.
- Rows: inputs/seed256.jsonl, then runs/FRONTIER_s2/own_0..own_5.jsonl in file order (bootseed0128.py:452,
  train(seed_rows + allown, ...)).
- Train with bootseed0128.train's exact recipe (reachlaw.train r 16, lr 2e-4, one pass, its Random(0) visit order). Write sd and tmp
  into a scratch dir such as /N/scratch/bsmensah/audit1105b/refit/, NEVER into runs/FRONTIER_s2 (train() rmtree's its tmp and the
  outdir).
- Three fits:
  - FIT_A: torch_seed 2006, order_seed 2006 (= 1000 k + t + 1). Positive control: the adapter md5 should equal 022540b217bc, and
    if not, compare FIT_A with P_6 to measure GPU nondeterminism.
  - FIT_B: torch_seed 902006, order_seed 2006 (same rows, same order, other init).
  - FIT_C: torch_seed 2006, order_seed 902006 (same init, other order).
- Read: dW cosine (lora_anatomy.py inner/fro), raw A cosine and A row-space overlap (alora.py) for FIT_A vs FIT_B, FIT_A vs FIT_C,
  FIT_A vs P_6, and P_6 vs P_7.
- FIT_A vs FIT_B is the same-data refit baseline. If it is at or above 0.045-0.087, the consecutive-round cosine says nothing beyond
  "similar data".

## 5. MAP held-out vs map concepts (phi1/out_map2, BIG-bench list_functions target functions)

- Held BASE solves 82 / 320. Five held concepts are constant-output or concatenate-a-constant: c042 [5, 2], c047, c091, c041 [9],
  c092. They give 6 + 8 + 8 + 6 + 8 = 36 solves (43.9%). Add c052 (repeat element 1 ten times, 8) and c048 (element 1, 8): 52 of 82
  from 7 trivial concepts.
- The map set (60) has 3 such concepts (c090 constant list, c068 concatenate constant, c045 identity). Stage A per concept was not
  saved (only 132/960 and 16/60 with any solve), so a per-concept map-side rate cannot be recomputed.
- Same function on both sides:
  - held c003, c083, c084 = "remove all but element 7" = map c004;
  - held c002 = map c081 (element 3);
  - held c095 = dev c064 (remove first and last);
  - held c062 = map c127 (remove last).
  - These 6 held concepts give 2 of 82 BASE solves. (map c036 and dev c089 are also identical.)
- Arithmetic, sort, filter and index-dependent held concepts (c206, c217, c113, c201, c226, c134, c183, c180, c039, c152, c246) are
  all 0/8 at BASE.
- Verdict: yes, held-out solves come from a different concept type than the map's mass. Almost half are constant-output concepts that
  sit at the 8/8 ceiling, where no edit can raise them. Any held-out effect of a neuron edit has to come from the about 10 movable
  concepts (first audit, sec. 3). This strengthens "underpowered", not "inert".

## 6. Published claims still OVERSTATED, WRONG or STALE after 745b4a9 (corrected sentences)

ratchet silicyte-0128/r10/RESULT_0128_A1R10.md:
1. "The weights reset every round: ... consecutive rounds' weight changes have cosine 0.05 to 0.09 (...). What accumulates is the
   self-made dataset, not the weights." OVERSTATED (not touched by 745b4a9). Corrected: "Each round fits a fresh LoRA from the base
   model (lib/reachlaw.py:125); this is true by code. The 0.05-0.09 cosine between consecutive weight changes is not evidence for it:
   fits from different seeds, sharing only about 5% of their rows, give 0.033-0.050, while consecutive fits share 80-88% of their rows."
2. "The loop reliably improves itself: +0.18 depth per round on a never-trained ruler ... It does not speed up within 10 rounds."
   OVERSTATED. Corrected: "Refitting a fresh LoRA each round on the growing self-made dataset raises d50 on a never-trained ruler by
   0.18 per round (0.127 model-free), with no detectable speed-up; the test cannot see a speed-up of 10% per round (power 0.30) or one
   starting after round 5, and there is no fixed-teacher control, so this is not evidence that self-generated data does better than
   other data of the same volume."
3. "So acceleration of 20% per round or more is ruled out over these 10 rounds; 10% per round is not." Withdrawn in the CORRECTION,
   but it still stands in the body unmarked. Corrected in place: "(WITHDRAWN 18:12 ET: endpoint-matched power is 0.67 at m 1.2 and
   0.30 at m 1.1.)"
4. "UNDERPOWERED gate: ... power at the measured noise is above 0.6." Corrected: "Power above 0.6 holds only for m >= 1.2 with the
   endpoint matched (0.67); at m 1.1 it is 0.30."
5. "that check is pending; if it fails, this note will say so." STALE. Corrected: "The check passed for all three seeds: 300 of 300
   redone round-10 MEAS rows equal the archive (POST OK, post_1105_postfix.log, e3157e7)."
6. Appendix: "So the linear d50 is not hiding an acceleration at the frontier." OVERSTATED. Corrected: "No depth band shows
   detectable acceleration; at d7-10 the seed spread (c sd 0.0172, t -1.00) is too wide to rule one out." Also: "The hardest tasks
   improve 5 to 10x" -> "d7-10 solve rates rise from 0.00-0.02 to 0.07-0.12."
7. CORRECTION bullet "The search-space caveat used 42 ops; the world has 54." Incomplete. Corrected: "The world and the policy have 54
   ops; 42 is the number of distinct ops in the loop's verified programs (the 12 cut ops never appear). In 54-op search units the
   logistic gain is 54^0.181 = 2.06x per round (54^0.127 = 1.66x model-free)."

ratchet silicyte-0129-open/PREREG_OPEN0129.md:102 (registered, so it needs a dated note, not an edit):
8. "Weights do not carry over between rounds (RESULT_LORA_ANATOMY_S1: consecutive dW cosine 0.045 to 0.087)". Corrected note: "Weights
   do not carry over between rounds by code (fresh get_peft_model each round); the cosine is not evidence of it (see AUDIT PART 2
   sec. 4)."

SILICYTE_HANDOFF.md secs. 4 and 5:
9. Sec. 4: "The kill test passed: over 0128's own 2,604 verified programs, the top-20 bigram macros shrink programs 27.4% ... drop6 is
   not a primitive." OVERSTATED. Corrected: "Over 0128's 4,713 verified programs the top-20 bigrams shorten programs 28.1%, but 61.8%
   of their uses are same-family compositions (drop3 drop3 = drop6 exactly). With the drop/trim/rot/sub families completed the saving
   is 13.2%. The i.i.d. Zipf generator alone gives 16.3%. The LADDER smoke shows the same reach (4) with and without macros at 2.07x
   executions. The kill test shows a one-time compression of a sparse op set, not a compounding mechanism."
   - Sec. 4: "0128 refits a fresh LoRA each round (consecutive dW cosine 0.05-0.09; reachlaw.py:125)" -> drop the cosine and keep
     the code citation.
   - Sec. 5: "Power 0.999 at m 1.2" -> "power 0.67 at m 1.2 endpoint-matched (0.999 withdrawn)".
   - Sec. 5: "in search-space units, +0.18 depth with 42 ops is about 1.96x per round" -> "with 54 ops, 2.06x per round (1.66x
     model-free)".
   - Sec. 5: "B17 LEVEL +1.3 logits, RISE flat" -> "B17 LEVEL +1.3 logits; RISE unmeasurable (self-trained arm at 8/8 ceiling)".
   - Sec. 5a: "Random inits give about 0.004, so it hints at a shared direction" -> "Cross-seed fits (different data, different
     init) already give dW cosine 0.033-0.050 and the same A row-space overlap as consecutive rounds, so the 0.05-0.09 is generic
     same-world similarity, not a carried direction; the reset is true by code."
   - Sec. 5a: "The world has 54 ops, not 42" -> add "42 is the count of distinct ops in the verified programs".
   - Sec. 5a: "UNCHECKED: the 0133 bigram recount, the leakage logs, and the s3/s4 round-10 equality" -> "Checked in AUDIT PART 2:
     leakage 0, s3/s4 round 10 equal, 0133 premise OVERSTATED."

Not re-checked here: arm T POSCTL 128/144 vs 108/144, the A4 deep ruler DETERMINISM 120/120, the SELFMOD smoke, and B16 per item.
