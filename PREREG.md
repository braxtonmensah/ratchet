# PREREG ratchet_v1: does a verified-helper library compound on ARC at equal tokens?

Registered 2026-11-04 (Eastern time, PowerShell clock) by Silicyte (Braxton Mensah, founder; design and implementation
AI-assisted). Written before any model call, any growth-task attempt and any read of a sealed task. Changes after this
commit are AMENDMENTS appended below, never edits. Loop register id: written in the AMENDMENT 0 line once assigned.

## 1. Question

At equal total tokens, does a library of verified Python helpers that keeps growing round after round (STOCK) solve more
sealed ARC tasks than (a) the same library frozen after round 1 (STATIC), (b) the same tokens spent in one round (ONE-SHOT),
(c) verified whole programs shown in context with no helper extraction (EXEMPLAR), (d) a size- and genre-matched library of
unverified code (SHAM), and (e) no library, all tokens spent as extra samples on each sealed task (FLAT-TTC)? And is any gain
carried by helpers that sealed solutions actually call?

This is an evaluation, not a new method. It applies the compute-matched protocol of Berlot-Attwell et al. ("Library Learning
Doesn't", arXiv 2410.20274; "LLM Library Learning Fails", arXiv 2504.03048; EACL 2026) to ARC program libraries. Systems in
the same family: DreamCoder, LILO, ReGAL, TroVE, CodeIt, SOAR, ArcMemo, E. Pang's arc_agi, SCAFFOLD, SkillComposer, and the
Lehmann and Vahdati ARC-AGI-3 harness study (arXiv 2610.30499). Our own prior record: a frozen library of 1,120 verified
ARC training-task programs passed 0 of 169 eval outputs' demos when reused unchanged (ARC lane, T5_SEARCH sec. 3.6).

## 2. Data and the seal

- Source: github.com/fchollet/ARC-AGI at commit 399030444e0ab0cc8b4e199870fb20b863846f34.
- GROWTH = the 400 `data/training` tasks. sha256 of the sorted id list (one id per line, LF): `c4e1b145daad71b4f02ac3482be215f1ab07863b67f13fc1bde1572f501ff75a`.
- SEALED = the 400 `data/evaluation` tasks. sha256 of the sorted id list: `911bf838d8843606d5fc1ba0550a0c23670027bf8f6e32e4e4fbf93854957ddd`.
- Sealed test outputs are copied to a key directory the loop cannot read. Only `score_sealed.py` opens it, once per frozen
  library, after every library in the run is frozen and hash-committed. A guard refuses any other read.
- Secondary sealed read (reported, not decisive): ARC-AGI-2 public evaluation tasks, same frozen libraries.

## 3. Model and compute

- Proposer: Qwen3.6-35B-A3B (fp8 weights) served by vLLM on one H100, weights fixed for the whole run. Temperature 0.8,
  top_p 0.95, max 4,096 generated tokens per sample.
- Compute: IU Quartz h100-debug slots (1 h each). Every arm logs prompt tokens, generated tokens and sandbox executions.
- Program execution: CPU sandbox, 2 s timeout per demo, no network, no file access outside a temp dir.

## 4. Arms

R rounds, S samples per growth task per round (both fixed by the pilot rule in section 7, before any sealed read).

| Arm | Library during growth | Sealed scoring |
|---|---|---|
| STOCK | after each round, extract helpers from demo-passing programs; accept a helper if it appears in at least 2 demo-passing solutions of different tasks, or its minimum-description-length gain on the round's solutions is at least 20 tokens | L_R in context, callable |
| STATIC | L_1 frozen; rounds 2..R sample the same way with no library update | L_1 |
| ONE-SHOT | one round with R x S samples per task, then one library under the same acceptance rule | L_one |
| EXEMPLAR | verified whole programs (k = 3 nearest by demo features) in context, no helper extraction, same context-token cap as STOCK | exemplars |
| SHAM | size-, token- and genre-matched library from code that failed its demos or came from shuffled tasks | L_sham |
| FLAT-TTC | none | extra samples per sealed task equal to STOCK's logged total tokens (growth + library prompt tokens + sealed) divided by FLAT's mean tokens per sample |
| PLANT-DRIP (positive control) | Hodel arc-dsl primitives released in R tranches | L_plant_R |
| PLANT-L1 (positive control) | tranche 1 only | L_plant_1 |

Library context cap: 6,000 tokens for every library arm (helpers ranked by number of distinct calling tasks, then length).
Sealed tasks never contribute helpers to any library.

## 5. Selection without test outputs (pass@2)

Among sampled programs that pass every demo of a task, submit the two most frequent distinct test outputs, ties broken by
shortest program. Test outputs are never used for selection. Demo-pass rate and test-correct rate are reported separately for
every arm and round.

## 6. Primary metric and decision

A sealed task is SOLVED if its pass@2 submission is correct in at least 2 of 3 sealed scoring seeds.

**COMPOUNDS** requires all of:
1. STOCK solves more sealed tasks than each of STATIC, ONE-SHOT, EXEMPLAR, SHAM and FLAT-TTC, each by an exact one-sided
   McNemar test at p < 0.05 (intersection-union: no multiplicity correction).
2. Reuse gate: on sealed tasks STOCK solves and FLAT-TTC does not, at least 50% of winning programs call an accepted helper.
3. Knockout: re-running those tasks (a) with the called helpers deleted and (b) with the helpers inlined as non-callable text
   each removes at least half of those solves.
4. Contamination gate: on a perturbed sealed copy (one random colour permutation excluding 0 plus one of rotate 90/180/270 or
   transpose, applied to demos and tests together, seed fixed), STOCK's net gain over FLAT-TTC is at least half its
   unperturbed net gain.

Other registered outcomes: beats FLAT-TTC but not STATIC = LIBRARY HELPS, NOT COMPOUNDING. Fails the reuse gate = CONTEXT
EFFECT. Fails the contamination gate = RETRIEVAL. Otherwise NULL.

**VOID** (not NULL): PLANT-DRIP fails to beat PLANT-L1 under the test in 6.1. A VOID run is retired after two attempts.

## 7. Pilot (growth tasks only; fixes R and S; never touches the seal)

1. Determinism smoke: one FLAT round on 50 growth tasks, run twice; the two demo-pass counts must agree within the 95%
   binomial interval. Fail = fix the harness, re-run.
2. PLANT round-1 check on the same 50 growth tasks: L_plant_1 in context must raise demo-pass count over no library by at
   least 1 task (proves the harness can see a library at all).
3. Throughput and discordance: from the pilot, estimate tokens/s and the fraction d of tasks where two independent FLAT
   runs disagree. Rule: choose the largest S in {4, 8, 16} and R in {4, 6, 8} whose projected total tokens fit 12 H100-hours
   at the measured rate, then compute projected power for a net gain of +20 of 400 at the measured d. If projected power is
   below 60%, report the run as UNDERPOWERED in RESULT.md whatever it reads, and say so before the sealed read.

## 8. Prediction (registered)

Quantity: STOCK minus STATIC net sealed solves (of 400) at round R. Point +2, 80% band [-8, +14].
P(COMPOUNDS) = 0.15 (our estimate; every compute-matched re-evaluation of in-context library learning found so far reads null).

## 9. Kill and abandon

NULL, CONTEXT EFFECT or RETRIEVAL with a valid PLANT-DRIP: Silicyte publishes the null and drops library compounding as its
thesis. VOID twice: harness retired.

## 10. What a stranger reruns

Every frozen library L_r as JSON plus Python, the token ledger, `score_sealed.py`, and the perturbation seed. Rescoring one
frozen library on the 400 sealed tasks needs one GPU and the public ARC-AGI-1 data.

## AMENDMENTS
- AMENDMENT 0 (2026-11-04 16:47 ET, before any model call): registered in the Silicyte loop ledger as **silicyte-0119**
  (16:46 ET). Calibrated 80% band for the section 8 quantity, fitted by the ledger on 728 resolved predictions: [-10.68, +17.216].
  The id lists hashed in section 2 are committed under `splits/`.
- AMENDMENT 1 (2026-11-04 23:20 ET, after pilot v1 job 12678501 read PLANT_FAIL, before any growth job and any sealed read):
  truncation fix. Pilot v1 truncated 897 of 1,200 samples at max 4,096 generated tokens (74.75%); 754 (62.83%) reached the
  sandbox with no code and held 3,084,977 of 4,336,292 generated tokens (71.14%); stopped samples spent a median 1,466 to 1,473
  tokens of prose before the code. For every arm, phase, round and seed, config.INSTRUCTION gains, appended after its last
  sentence, exactly: "State the rule in at most three sentences, then give the code block. Do not trace the grids cell by
  cell; your program is run on every example for you." (INSTRUCTION_F3, sha256 3c511b3f1db6cf3a8a1c32d499137dd0210a19bf7026937ea7cb540e7db2191e; v1 text INSTRUCTION_V1, sha256 cf85bc1b0ccc002e3bc93edd9e8285e41c35b28f022d517f85c011e4c7d22340).
  Sampling stays as section 3 (max 4,096). Pilot order: FLAT_A under F3, then one growth-only screen round FLAT_S on the same
  50 pilot tasks with S = round(1,451,835 / (50 x g)), g = that FLAT_A's mean generated tokens per sample. F3 stands iff FLAT_S
  has at least 23 demo-pass tasks AND at least 22 pass@2 test-correct tasks (means of v1 FLAT_A 24 / FLAT_B 22 and 23 / 21);
  the demo-pass-but-test-wrong share is reported (v1: 13 of 299). If F3 stands, FLAT_B, PLANT1 and PLANT_SOLVE run under F3;
  otherwise INSTRUCTION_V1 at max 4,096 is restored for the whole run and FLAT_A, FLAT_B, PLANT1 and PLANT_SOLVE run under it.
  Screen samples are phase pilot and never feed a library, exemplar, SHAM or helper ranking. Nothing in v1 shows F3 keeps
  accuracy on hard tasks; the screen is the only evidence. The FLAT-TTC rule of section 4 is unchanged; at g near 500 a
  library sample costs about 4.6x a FLAT sample instead of 2.26x, which makes COMPOUNDS harder; RESULT.md reports the measured
  ratio, and the section 8 prediction, made at the v1 operating point, is left unchanged. Every job prints LEVER INSTRUCTION
  sha=<sha256> and refuses a hash other than the one recorded for the run.
- AMENDMENT 2 (2026-11-04 23:20 ET, same conditions): harness fix under section 7. In v1, 8 of the 13 grid-taking arc-dsl
  primitives in L_plant_1 (mostcolor, objects with without_bg, palette, numcolors, width, height, shape, underfill) raised on the
  list-of-lists grid that transform receives, because arc-dsl dispatches on tuple type; 41 of the 43 PLANT1 ERROR samples were
  this crash, and replaying them through the fix below makes 24 pass their demos. For every library arm, phase, round and seed,
  the library now executes in its own namespace and each helper reaches the program through an adapter that reads only the
  helper's own annotations: an argument at a parameter annotated Grid, Element or Piece that is a list of rows is passed as a
  tuple of tuples, and a tuple-of-tuples result of a function so annotated is returned as a list of lists; unannotated helpers
  pass through unchanged. The adapter and the call-counting wrapper carry the wrapped function's exact signature, because arc-dsl's rbind and lbind read co_argcount (with a *args wrapper, 31 of 50 pilot solvers ran; with signatures, 50 of 50). Helper call counting is unchanged. The callable library header gains, exactly: "Pass grids exactly as
  transform receives them; these functions accept and return grids as lists of lists of ints." A type legend listing only the
  arc-dsl type names that appear in the rendered helpers' annotations is prepended to the library block and counts against the
  6,000-token cap. The library note is placed before the instruction's closing text: under INSTRUCTION_F3, before both
  appended F3 sentences, so they stay together and last; under INSTRUCTION_V1, before its final sentence. Before the first
  model call that puts a library in context, the job checks that library: every grid-typed helper is called through the
  adapter on a list-of-lists demo grid and on its tuple twin, and the job refuses (per library and arm, logged as LEVER ADAPTER
  grid_helpers=<n> list_smoke_ok=<n>) if a helper raises on the list grid but not on the tuple grid, if the two calls return
  different values, or if the check cannot run.
  Section 7 is re-run in full in a fresh run directory (runs/v2); v1's PILOT_STOP.json stays in place.
- AMENDMENT 3 (2026-11-04 23:20 ET, same conditions): section 7.2 gate. A plumbing control PLANT_SOLVE gates the pilot: on the
  same 50 pilot tasks at S = 8, each task's callable library holds arc-dsl's own solver for that task, renamed solve_this with
  docstring "returns the output grid for this puzzle", plus its primitive closure (at most 3,418 tokens with the real tokenizer, header and legend included, under the 6,000 cap),
  rendered and executed exactly as every library arm. It passes iff its demo-pass tasks are at least FLAT_A's plus 5 (2 noise
  SDs at the measured v1 discordance d = 0.12). The L_plant_1 (PLANT1) check is still run and reported in PILOT.md but no longer
  gates: no Hodel solver of a FLAT-unsolved pilot task fits inside any primitive library under the 6,000-token cap (0 of 24),
  and its +1 rule passes with probability 22/64 = 0.34 under no effect. PLANT_SOLVE is pilot-only: it never enters a growth
  round, a library or a sealed read. PLANT-DRIP, PLANT-L1 and the VOID rule of section 6 are unchanged.
- AMENDMENT 4 (2026-11-05 00:40 ET, after pilot v2 read PILOT_NO_FEASIBLE_SR, before any growth job and any sealed read):
  section 7.3 budget. The 12 H100-hours of section 7.3 become 48 H100-hours, for every arm, phase, round and seed. Basis:
  measured supply, about 170 H100-hours reachable by 2026-11-10, of which another study (silicyte-0128) needs about 47
  (91 with its exploratory GUIDE arm) on h100-single holders, not on the h100-debug slot this run uses; the number is set
  before any growth job and does not depend on any growth or sealed result. It was set after the pilot's projection was
  read; every budget from 41 to 54 H100-hours gives the same choice, S = 4 and R = 4. Pilot v2
  (runs/v2, PILOT.md written 2026-11-05 00:08 ET, code 43b97f7) read: 7.1 determinism PASS (FLAT_A 22 and FLAT_B 22
  demo-pass tasks of 50); 7.2 PLANT_SOLVE PASS (49 demo-pass tasks against FLAT_A 22, gain +27, needs +5); the F3 screen
  failed, so INSTRUCTION_V1 at max 4,096 runs (g = 3,607.9 generated tokens per sample); 7.3 PILOT_NO_FEASIBLE_SR: the
  smallest cell, S = 4 and R = 4, projects 41 one-hour H100 jobs against 12 (S = 4, R = 6: 55; S = 8, R = 4: 82); projected
  power for a net gain of +20 of 400 at the measured d = 0.14 is 0.8318 (not UNDERPOWERED). The rule is unchanged: the
  largest S in {4, 8, 16} and R in {4, 6, 8} whose projection fits, which at 48 selects S = 4, R = 4 at 41 jobs. S and R
  are re-chosen from the rates PILOT.json recorded; no pilot arm is re-sampled; the pre-amendment PILOT.json, PILOT.md,
  PILOT_CHOICE.json and PILOT_STOP.json are kept under archived names. Nothing else in sections 1 to 10 or in AMENDMENTS 0
  to 3 changes, and this amendment grants no access to any sealed key.

- AMENDMENT 5 (2026-11-05 07:44 ET; after run v2 growth and the A5 smoke, before any sealed read). It applies parts A and C
  of AMENDMENT_5_DRAFT.md. The part C decision rule was pushed at 06:46:35 ET (f59281e), before the smoke job was submitted
  (07:14:34) or started (07:27:12).
  (a) Run v2 is WITHDRAWN_PRE_SEAL, for the reasons in GROWTH_V2_DIAGNOSIS.md: STOCK, ONE-SHOT and SHAM are empty. Its
  FREEZE.json is never acked, and no v2 row is sealed-sampled or scored. This is not a VOID attempt.
  (b) The smoke (job 12686909) results:
      - P0: A 0, H 0.019, D 19.
      - P1 (prefill): A 0, H 0.000, D 22.
      - P2 (prefill + helper sentence): A 0, H 0.268, D 20.
      No variant meets A >= 5, so there is no run v3.
  (c) Outcome: LIBRARY_CANNOT_FORM. silicyte-0119 ends without a sealed read, and the 400 sealed tasks were never opened.
  Per section 9, Silicyte drops in-context library compounding, as registered (exact canonical-hash acceptance), for this
  model and budget. Result: RESULT_0119_PRESEAL.md.
