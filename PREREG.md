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
