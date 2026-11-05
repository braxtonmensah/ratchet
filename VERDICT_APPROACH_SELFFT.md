# VERDICT_APPROACH_SELFFT: is SELF-FT the best next test, and does it move the goal?

Verifier half of the builder/verifier pair. Written 2026-11-04 20:17 ET (PowerShell clock). Read-only: no GPU job, no CPU job, no
edit to any other file. I did not design or build what is checked here.

VERDICT: GO-WITH-CHANGES
BEST APPROACH: finish Ratchet main (silicyte-0119) first on the slot, then run this SELF-FT sub-study as the ONE weight-training test of the window, re-scoped so its primary read is the HELD slice before the seal with the gate fixes below; defer TTRL-codes (silicyte-0125), which is the same update rule on the same 8B and the same slot.
MOVES THE GOAL: PARTLY. With the changes, either outcome is a registered, public, compute-matched verdict on whether self-training compounds (the second credential type) and can be read before 2026-11-11; it can never produce a number on someone else's scoreboard, and as drafted its own predicted label is UNDERPOWERED (AMENDMENT_1 line 398), which moves nothing.

GO-WITH-CHANGES unlocks no launch. Only a later code verdict with the GO label does.

## 0. What I read, and what existed when

- `AMENDMENT_1_SELF_FT_DRAFT.md` did not exist at 20:0x; it appeared at 20:08 (42,351 B) and is read in full below. It is already the
  revised design (RELABEL primary, CORRECT-ONLY as control), not the correct-only design the brief described.
- `selfft/` went from two stub files (20:05) to core.py, train.py, step.sh, launch_in_holder.sh, README.md (20:10). core.py changed
  while I read it: at my first grep its defaults were `train_data='correct_only', init='continue', lora_r=16, lr=1e-4`; at 20:1x
  they are the draft's (core.py lines 40 to 47: relabel, restart, r 256, RS-LoRA, lr 5e-5, max_len 12,288). `tests_selfft/` holds one
  file, 7 tests. I judge the approach, not this code; the code verdict comes later.
- PREREG.md (0119), SPEC.md sec. 1, AMENDMENT_TTRL_V1.md (0125), PREREG_STEERING_DIVERSITY_V1.md (0124), RESEARCH_ARC_WINNERS_1104.md,
  RESULT_PORL_CRL_AUDIT_1031.md, RESULT_PORL_CRL_LIT_1031.md, RESUME_1030_CROSS_DOMAIN.md, MOONSHOT_GAMEPLAN_1102.md line 237, and the
  five memory notes named in the brief plus recall-every-research-finding-before-calling-it-open.md.
- No record of Qwen3-8B ever sampled on ARC prompts (grep of NQ_local; draft line 377 says the same). The 8B base rate is unknown.

## 1. Adjudication: is SOAR-style relabelling CLOSED on our record?

Ruling: CLOSED only for hindsight rows fed to the Flash-Next thinking tool loop, scored on the ARC lane's B ruler. UNTESTED in SOAR's
setting (single-turn, non-thinking Python program writer on ARC-AGI-1, relabel isolated by an ablation). The memory note
recall-every-research-finding (line 3, lines 12 to 13) overstates its two citations as "SOAR relabel FAILED twice".

Evidence for the ruling:
1. HS-AONLY (arc-0662, 12/158 vs 93/158; RESULT_PORL_CRL_AUDIT_1031.md lines 11 and 64) was not a relabel test. Its 239 rows each
   taught exactly one `run_python` call and zero `submit_program` calls (RESUME_1030_CROSS_DOMAIN.md line 39); 12 Adam steps on 48 rows
   cut first-turn thinking 2.6x and removed every correct answer (line 110); the rows were canned-reasoning rows (line 122); the lane's
   own row gate later REFUSED them (line 114); and the merge left an orthogonal residual of 0.977524 times the intended update (line 41).
   That is a format and termination collapse plus a merge confound on a thinking model, not evidence about relabelling.
2. LRFT3 (-0.038 [-0.1024, +0.0301], audit line 62) kept 216 hindsight outputs as 285 rows inside a 4,429-row file
   (MOONSHOT_GAMEPLAN_1102.md line 237): 6.4% of rows, stacked with a round-3 rejection SFT and an ACTDIR steer, read as ACTL3 vs
   ACTDIR-on-base. Its interval includes 0 and no arm isolates the relabel rows.
3. Both ran on the B ruler (60 tasks, 158 paired attempts, audit line 6) through stochastic tool-loop lives. Our own records already
   said so at the time: "this project has not reproduced its gains" (RESUME_1030_CROSS_DOMAIN.md line 87); the literature file closed
   the fine-tune half by family resemblance, not by a run ("same family as LEAN-RFT, which failed", RESULT_PORL_CRL_LIT_1031.md line 38).

What does carry a real prior against relabel HERE (and the draft states it, lines 109 to 123): the search budget (8 samples per task
per round vs SOAR's 6k, 750x less; draft line 321), Qwen3-8B's own fourth-law weight reads (rho_match 0.981 [0.843, 1.118], weights
give head starts at par, not faster rates; CONT minus ORIG +0.014 TIE, self-generated rows add about 0; memory fourth-law lines 44 to
46 and 71 to 72), and SOAR's own plateaus (RESEARCH_ARC_WINNERS line 154). So relabel is the right primary arm, with a negative prior
that comes from budget and model, not from those two rows.

## 2. Question 1: ranking of the candidates

Score = P(clean verdict, meaning not VOID and not UNDERPOWERED, readable by about 2026-11-11) x E(fundability move | that verdict) on a
0 to 10 scale. All P and E values are my ESTIMATES; the inputs behind each are cited.

| rank | approach | P(clean verdict in window) | E(move) | score | why |
|---|---|---|---|---|---|
| 1 | Ratchet main, silicyte-0119, as registered (in progress, not "next") | 0.26 | 4.8 | 1.2 | already public (README line 3) and registered before any call; harness built (30+ modules, tests/); slot priority (draft line 347). Against: only S 4, R 4 fits, near the decode ceiling (SPEC lines 65 to 66); 132 of 145 units are sealed scoring (SPEC line 67); PLANT VOID risk; read only on 11/11 by the founder's promise. P(COMPOUNDS) 0.15 (PREREG line 94). |
| 2 | SELF-FT sub-study WITH the changes in sec. 5 (HELD primary before the seal) | 0.15 | 4.4 | 0.65 | SOAR is a published positive in this exact setting, so the outcome is genuinely uncertain and both readings inform; the founder asked for weight training. Against: harness half-built (sec. 0); PC-1 is a real VOID risk; P(pass) 0.07 (draft line 415). |
| 3 | TTRL on the codes hunt, silicyte-0125, codes only, arms rotated one per job | 0.13 | 3.0 | 0.4 | no seal needed, exact dense reward, a record would be a scoreboard number. Against: its 4-GPU-per-job layout is refused by the QOS (draft lines 39 to 40, 354 to 356), so its jobs quadruple and its cuts fire (0125 lines 278 to 289); its own expected label is PROPOSER-ONLY or NULL (0125 line 305); controls reproduce lb exactly with no slack (0125 line 44); the sandbox lets a program import score.py (0125 line 45), a reward hole an RL policy will find. Same update rule as SELF-FT (rejection-sampling LoRA SFT on own verified outputs, 0125 line 107), same 8B, same slot. |
| 4 | Per-task test-time training on demos (ARC winners' lineage) | 0.3 | 1.0 | 0.3 | the largest measured lever in every winner's ablation (RESEARCH_ARC_WINNERS lines 10 to 13, 121), but it resets per task and does not compound across tasks (line 176 to 177), so its verdict cannot answer the RSI question; it is a reproduction (Akyurek 18.3 to 47.1, line 129); needs a transductive model we do not have; our 27B TTT read 0 exact (audit line 79). |
| 5 | SELF-FT exactly as drafted (sealed primary, slope over r = 0..R, ONESHOT up to 6 epochs) | 0.08 | 3.0 | 0.24 | predicted UNDERPOWERED or NULL by its author (line 398); 34 jobs (line 371), 20 of them sealed, read after D_SEAL; and a one-time gain can pass its COMPOUNDS gate (sec. 3). |
| 6 | Steering diversity, silicyte-0124 | 0.4 | 0.3 | 0.12 | not a self-improvement test: nothing learns (0124 line 8); its own pre-registered best case is a diversity lever, and its nearest precedent LATENT-ANTI raised distinct grids, not right outputs (0124 lines 21 to 24). |

Anything better? Not inside the window. The only route to a number on someone else's scoreboard in 7 days is the record hunts
themselves (codetables.de, the FMM catalogue), which are CPU and Opus work; SELF-FT and TTRL must not take GPU time those need. A
stronger RSI test than SELF-FT would need SOAR-scale search (thousands of samples per task per round), which one shared H100 slot
cannot buy by 11/11.

So: SELF-FT is not the best next GPU use (finishing Ratchet main is), but among NEW tests it is the best, provided it is changed
(sec. 5) and TTRL-codes is deferred so the two do not split one slot and both come back UNDERPOWERED.

## 3. Question 2: does the drafted design measure compounding, and how could a positive be fake?

What the draft gets right (credit where due): RELABEL primary with CORRECT-ONLY as the CodeIt A2 control (lines 140 to 150); ONESHOT
built from the SAME base samples, not from the loop's later data (line 164), so it isolates iteration; FROZEN8B matched in FLOPs
including every from-base retraining (lines 185 to 199); HELD 80 never trained on (lines 133 to 136); PC-0 and PC-1 (lines 250 to 257);
an A/A (line 261); the logprob adapter-live probe against HF (lines 279 to 281); rows never selected on growth test outputs (line 151);
clipping fixed (12,288, drop and count, VOID over 5%; 17.9% of tasks would have lost their completion at consol.py's 3,072, line 47).

Where it measures a one-time gain and could call it compounding:
1. The HELD slope includes h_0 (line 216 to 217, gate line 401 "over rounds 0..R"). A jump at round 1 followed by a flat line, e.g.
   h = 0.10, 0.15, 0.15, 0.15, 0.15, 0.15, 0.15, gives a positive OLS slope with a tight bootstrap bound. So any SELFFT that beats
   FROZEN at round 1 passes the slope gate, and label 4 ITERATED-GAIN (slope bound <= 0) is nearly unreachable. "Gain per round
   rising", the founder's meaning of compounding, is only descriptive (lines 218 to 219). The top label COMPOUNDS-WEIGHTS therefore
   means "iteration beat one training on base samples and HELD went up", not compounding.
2. ONESHOT is matched by trained tokens and runs up to 6 epochs over its union (lines 193 to 195), while SELFFT's final adapter A_R is
   one epoch from base (line 176). A SELFFT > ONESHOT read could be ONESHOT over-trained, not iteration helping. The control must get
   the same recipe; leftover units go to extra ONESHOT samples (the draft already has that path for the 6-epoch cap).
3. Compute matching is honest but inverts SOAR's regime. At S_g 8, retraining is 147.5M of 185.9M SELFFT units, 79% (line 202 to 205),
   against about 5% in SOAR (line 50). FROZEN8B gets about 30x the trained arm's sealed samples (line 206 to 207). A NULL at S_g 8
   therefore answers "is retraining worth 4x its FLOPs in extra samples at 8 samples per task", which a reviewer reads as a budget
   artifact. Register the training share as a printed quantity and the NULL as NULL AT THIS BUDGET.
4. HELD contamination. HELD is drawn from ARC-AGI-1 training tasks, and Hodel's arc-dsl solvers (400 `solve_` functions, line 48) are
   public solutions to exactly those tasks. The base 8B may have memorized them, and PC-1 trains on Hodel programs for TRAIN tasks, so
   a HELD rise can be retrieval of memorized solvers. The perturbed-copy gate exists only for the seal (lines 220 to 222). A HELD
   primary needs its own perturbed copy.
5. Adapter not loaded. The draft's probe is right; the code as of 20:1x has no logprob probe (`grep probe core.py` finds none), only
   "the served adapter sha differs ... and vLLM lists it" (selfft/README.md line 38). Listing is not applying: the 27B's runtime LoRA
   silently applied nothing (audit line 129). Code verdict item.
6. Compute not matched in code. core.py's FROZEN is matched on sample count only, on HELD only (core.py lines 7 to 8, 175; README line
   32), not on FLOPs including training as the draft requires. Code verdict item; whichever design is registered must be the one coded.
7. Slot and GPU sharing. `slurm/selfft_hold.sbatch` holds h100-interactive for 4 h (lines 3, 7) and claims it is a separate slot from
   h100-debug (line 12); the brief says they share one per-user slot, and the draft plans 1 h h100-debug jobs (line 323). Resolve with
   `sbatch --test-only -p h100-interactive -A students` while a debug job runs. Also, `srun --overlap` steps on one holder share its
   GPU (memory fourth-law line 59): vLLM and the trainer co-resident on one card must be measured in J1 (draft line 180 to 181).
8. Selection on held-out. No hyperparameter is chosen on HELD in the draft (S_g by throughput only, line 331). Keep it that way:
   register that R, S_g and the recipe never change after the first HELD read.

Which of our 15 failed rows it repeats: the MECHANISM of LRFT1 (BETWEEN), LRFT1F (FAIL), LRFT3 (FAIL), SFT-A1 (FAIL), RSI2G and EI
(never read) (audit lines 60 to 63, 80 to 81): supervised training on the model's own verified outputs. It does not repeat their known
failure causes: thinking-trace rows with clipped tails (memory arc-rl-rows-credit lines 14 to 16), off-format rows (HS-AONLY), a
reward measured through stochastic box lives, 16-row batches in the 73%-noise regime (memory arc-rl-update line 18; RELABEL gives an
ESTIMATED 1,536 rows per round, line 203). What is the same and still binding: a tiny search budget and a model (Qwen3-8B) on which our
own record already measured head starts, not rates.

## 4. Question 3: does it move the goal?

- NULL with PC-0, PC-1 and every lever check passed: publishable and credible as "SOAR-style self-training on an 8B at 8 to 32
  samples per task does not beat compute-matched frozen sampling", with released adapters and ledger (draft sec. 13). Its weight is
  limited by the budget artifact in sec. 3 item 3; it narrows SOAR, it does not refute it.
- UNDERPOWERED (the predicted label, line 398): moves nothing. This is the main reason the plan must change.
- POSITIVE: a sealed ARC-AGI-1 public-eval number for released adapters that a stranger can rescore on one GPU. Credible to a
  technical reader if the gate is fixed (sec. 3 items 1 and 2), but self-reported: ARC-AGI-1 public eval is not a board someone else
  runs. It is the second credential type at best.

## 5. Question 4: the single highest-value change before any GPU time

Make the HELD slice the registered PRIMARY read, taken before D_SEAL, with a gate a one-time gain cannot pass: (a) HELD slope over
rounds 1..R only (h_0 excluded; the round-0 to round-1 jump is the HEAD-START read, judged against ONESHOT); (b) SELFFT vs ONESHOT vs
FROZEN8B compared on HELD, FROZEN8B FLOP-matched on HELD; (c) a perturbed HELD copy as the contamination gate (sec. 3 item 4); (d)
the top label renamed ITERATES, with COMPOUNDS reserved for a per-round gain trend whose lower bound is >= 0 and whose MDE is printed.
The sealed comparison becomes a confirmatory read after D_SEAL. Effect: the verdict exists before 11/11 without breaking the founder's
promise; the plan drops from 34 jobs (line 371) toward about 20 because FROZEN8B's sealed sampling, 86% of sealed decode (line 370),
moves to 80 HELD tasks; and a continuous per-task demo-pass measure has more power than 2-of-3-seed sealed solves.

Required with it (each a condition for the later code verdict, not optional):
1. ONESHOT trains with SELFFT's final-training recipe (1 epoch, same 16-row cap); surplus units become extra ONESHOT samples.
2. One design: draft and code must agree (FROZEN FLOP-matched, logprob adapter probe in code, HELD split rule), hash-committed with the
   HELD id list before any model call.
3. Cut TTRL-codes GPU arms from this window, or run them only after SELF-FT's HELD read; do not interleave two RFT-on-8B studies on
   one slot.
4. Slot facts measured, not assumed (sec. 3 item 7), before J1 is queued behind Ratchet main.
5. J1 must print the 8B's base demo-pass rate on HELD and TRAIN; if fewer than 8 of 80 HELD tasks ever pass a demo at S_g, declare
   UNDERPOWERED before any round, and spend the slot on Ratchet main instead.
6. Appended to PREREG `## AMENDMENTS`, registered in the ledger, and pushed to the public repo before J1, as 0119 was.

## 6. Top three reasons

1. The mechanism is the right one and is untested here: relabelling is the ablated load-bearing part of SOAR and CodeIt, and our two
   "hindsight" failures were a tool-loop format collapse and a 6.4% admixture, not tests of it (sec. 1).
2. As drafted, a one-time gain can be labelled COMPOUNDS (slope over r = 0..R; ONESHOT over-trainable to 6 epochs; acceleration only
   descriptive), and the code on disk still differs from the draft on the frozen control and the adapter probe (sec. 3).
3. As planned it cannot deliver a verdict in the window: its primary needs the seal (after 11/11), 34 one-hour jobs on one slot that
   Ratchet main has priority on, retraining is 79% of its compute, and its author predicts UNDERPOWERED (sec. 2, 4).
