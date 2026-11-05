VERDICT: GO

BEST APPROACH: launch v3 as built. Run the posctl first on a NEW running holder, and the loop only after POSCTL_VERDICT PASS. Use the BUILD_ARMT.md §5 commands with HOLDER set to that holder's id.
MOVES THE GOAL: yes, as a test. v3 is a matched test of whether self-training the proposer's own weights on its own proven-new strict climbs beats frozen weights. The copy channels I found in v2 are closed or now count against a PASS.

Independent re-verification, 2026-11-05 14:1x ET, of the files the builder delivered at 14:12. Read-only: no job was launched, held, cancelled or submitted, and nothing was edited except this file.

## SCOPE

I read these files:
- ARMT_FIXES.md;
- BUILD_ARMT.md §3 to §5;
- PREREG_ARMT_DRAFT.md v3;
- armt.py v3 (sha 8fce8dad...), lines 185-516, 831-1345 and 1386-1612;
- read_armt.py v3 (sha 9090cb56...), lines 77-193;
- smoke/cpu_v3/*.

On Quartz (login, 14:14 ET):
- I re-ran the three registry hash checks and re-took every armT and snapshot sha. All match the laptop copies and BUILD.
- I re-checked the pinned prefix.
- I re-ran `armt.py copytest`, plus my own adversarial probes.

On the laptop, I re-ran the false-positive rate in my own node sim and in the builder's fpr_sim.js.

Nothing ran on a GPU.

## WHY GO

Both v2 blockers are fixed, and I reproduced the evidence.

### F1 (d0 understated): FIXED
- **The bound.** d0 is now the free-derivation closure over all pinned valid matrices: d >= d2 - max(0, (n2 - n) - (k2 - k)) for k2 >= k. Code: armt.py:233-252 (implied_d, closure_d0) and 284-316 (build_train_snapshot).
- **Gaps.** The gap goes from 138 to 81, equal to my v2 recomputation (PCB2_3 3, T06 4, T07 2, T03 4). The snapshot refuses any gap of 0 (armt.py:315).
- **Prompts show the source matrices to both arms.**
  - TRAIN prompts show the top-2 source matrices of each closure (armt.py:290-299, read through elites_for at 525-527).
  - The smoke's PCB2_3 prompt prints `BEST SAVED CONSTRUCTION 1 (exact d = 32 at length 75, dimension 19`.
  - So the v2 asymmetry is gone: TRAINED can no longer gain by memorizing a sibling cell's matrix that FROZEN never sees.
- **Running bests.** Both arms' running bests use the same closure for every instance onto every cell (armt.py:891-929). That is stream-agnostic, so it applies to FROZEN too.
- **Pinned prefix.** The prefix still hashes to d1a5b910..., and the archive is now 19,283 lines.

### F2 (copies entering the SFT set): FIXED
- **No tie rule.** The tie rule is gone. SFT takes a template only when its best instance that is PROVEN novel at code level beats the arm's running best (armt.py:968-969 and 994-1005). Unknown tests never qualify.
- **The copy test is code-level.** It checks order-preserving column maps plus a linear map, covering subcode, shorten, puncture, pad, extend and lengthen. It tests against all 44 shown matrices plus the arm's own earlier climb matrices (armt.py:354-489 and 884-888; known_with_rows at 1158).
- **My re-run: `COPYTEST_DONE PASS`, 20 of 20.**
  - All 10 free-operation positives test derived.
  - My three r04 deepseek/PCB2_4_0012 instances test derived.
  - The 6 random negatives test novel.
  - #14 tests unknown.
  - Row operations on BASE also test derived.
- **Offline r04.**
  - The SFT set is 2 strict PCB2_3 climbs (d 35 and 33 over rb 32).
  - There is no tie row, and no PCB2_4_0012 row.

## Evidence on the coordinator's points

1. **Every v2 fix item is done.**
   - **Cross-copy diagnostic and COPY_PASS.** Fields are copy_share, overlap50_share and climb_derived_share_train (armt.py:1134-1141). PASS also needs Gnd >= M in every seed and a copy-like climb share < 0.5. Unknown counts as copy-like, which is conservative (read_armt.py:150-162). Sharpening metrics are printed on every verdict (read_armt.py:167-174).
   - **COLLAPSE and NO_UPDATE give FAIL** (read_armt.py:139-158).
   - **#8 and #55 are excluded from the tertiary read** (armt.py:1115-1132).
   - **3 seeds.** The default is 0,1,2 (armt.py:1634), and the reader needs at least 3 (read_armt.py:152).
   - **$HOLDER is a parameter** (BUILD §5).
2. **The false-positive rate is confirmed by my own sim.**
   - Setup: v3 gaps, total 81. The 4 q=4 cells move together as one cluster (through the closure), and the other cells move alone. 18 regimes, 6,000 reps each, independent arms. This tests only the raw G >= max(2, D_F) rule.
   - Worst case: **K=3 0.022** (K=2 0.10).
   - The builder's fpr_sim.js gives a worst case of K=3 0.024 and K=2 0.110.
   - The Gnd and copy-share conditions can only lower these numbers, and the shared seeds lower them further. So the claimed 0.025 holds.
3. **Round time.** About 108 min (80 to 145) is a credible bandwidth-bound estimate: 10 rounds take about 17 h in a 48 h holder. The N 9 -> 6 rule at more than 150 min for round 2 is pre-stated.
4. **Claims and submission: unchanged and OK.**
   - write_claims writes only under claims*/ with NOT_SUBMITTED.txt and calls only `route` (armt.py:1043-1077).
   - There is no submit path.

## Warm start (the lead's 0128 point)

**Confirmed in code, not yet executed.**
- In cmd_train, the init adapter is `adapters/A_{r-1}` for r >= 2 (armt.py:1309).
- train_lora loads it with `PeftModel.from_pretrained(base, init_adapter, is_trainable=True)` and continues training (armt.py:1228-1229). There is no fresh LoRA unless A_{r-1} is BASE_ONLY, meaning no climb has happened yet (armt.py:1226-1227 and 1231).
- An empty SFT round copies A_{r-1} forward (armt.py:1317).
- So A_r really is A_{r-1} plus one pass, not a refit like 0128.

Caveats:
- **The AdamW state is new every round** (armt.py:1234). The weights carry over but the optimizer moments do not.
- **The path is unexecuted.** The posctl trains with init=None, so the warm-start load first runs at round 2.
- **A silent fresh refit is unlikely.** If is_trainable failed, the parameter list would be empty and AdamW would raise, so that failure is loud. A refit would also show as a reset of the per-round loraB_T column the reader prints.
- **Recommended, non-blocking:** log the lora_B norm right after the load and assert it equals A_{r-1}'s train_info lora_B_norm, plus the consecutive-round dW cosine. I would make this check at round 2 by reading round_2.json.

## Residual limits (non-blocking; state in the RESULT)

- **The copy test is blind to column permutations and single-column scalings.** My probes: a full permutation, a cyclic shift, a reversal and a column scale of the PCB2_4 elite all test `novel`, with row overlap 0.
  - An equivalent code has the same d, so a pure copy still earns 0.
  - This escape admits only a permuted subcode or puncture whose exact d beats the proven bound. That is a real improvement found by search, and it is open to FROZEN equally.
  - It does make copy_share an undercount.
- **copy_share has low resolution.** In the smoke sample, 21 of 48 tests were unknown. Unknowns count as copy-like for the PASS rule, so this lowers power, not validity.
- **Power is modest.** The builder's sim gives a pow3 of about 0.14 to 0.68 across regimes. A FAIL is weak evidence of no effect.
- **Not GPU-smoked:** vLLM LoRA sampling, the peft step, the warm-start load, the KL probe and timings. The posctl is the gate for the first two.
- **Holder.** 12688122 now runs 0128 GUIDE_s3, so a new arm T holder is needed. qrun.sh refuses unless that holder is RUNNING.
