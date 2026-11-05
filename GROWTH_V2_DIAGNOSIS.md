# Run v2 growth: the library never formed (2026-11-05 06:37 ET, before any sealed read)

Run v2 (code b636ce5, S = 4, R = 4, INSTRUCTION_V1 at max_tokens 4,096 after the F3 screen fell back) finished growth
at 06:04 ET and wrote freeze/FREEZE.json (sha256 730ec199...). The lead has NOT acked it. No sealed file or key has
been opened. The measured facts below come from the run's own files on Quartz (runs/v2).

## What growth produced

| arm | library or pool after growth | growth demo-pass tasks of 400, rounds 1..4 |
|---|---|---|
| STOCK | 0 helpers in L_1, L_2, L_3, L_4 (n_accepted 0 every round) | 165, 162, 168, 162 |
| STATIC | L_1 = the empty STOCK round-1 library | 165, 168, 174, 164 |
| EXEMPLAR | pool_R.json n = 0 (cause under diagnosis) | 165, 159, 169, 171 |
| ONESHOT | L_one 0 helpers | 221 (one round, 16 samples per task) |
| SHAM | 0 helpers (size-matched to STOCK) | n/a |
| PLANT-L1 / PLANT-DRIP | 36 / 96 planted helpers (built, not grown) | n/a |

So STOCK, STATIC, ONE-SHOT, SHAM and EXEMPLAR would all send the FLAT prompt in the sealed phase. Every registered
contrast in section 6 would be zero by construction, and a NULL read from this run would say nothing about library
compounding.

## Why

1. **Truncation.** In STOCK round 1, 1,225 of 1,600 samples stop at the 4,096-token cap (finish_reason "length"), the
   same share the pilot measured (V1_FLAT_A 0.775; the F3 instruction 0.69). Thinking is off, but the model still
   traces the grids cell by cell in prose and never reaches the code block. Only the PLANT_SOLVE pilot arm, whose
   library already solves the task, brought the share down (0.43).
2. **No helpers to harvest.** INSTRUCTION_V1 asks for "a Python function `def transform(grid):`". Of the 431 to 439
   demo-passing programs per round, only 1 to 4 define a top-level helper (PREREG 4's unit of extraction) and 6 to
   11 a nested one. The acceptance rule is permissive (2 distinct tasks, or an MDL gain of at least 20 tokens), but
   it has nothing to accept. Hoisting the closure-free nested defs would accept 1, 1, 0 and 2 trivial helpers in
   rounds 1 to 4 (diag/hoist_probe.py, read-only).
3. The pilot did measure (1). Nothing in the pilot gates measured (2): PLANT_SOLVE showed the model USES a library
   it is given (49 vs 22 demo-pass tasks of 50), but no gate checked that growth could BUILD one.

## What happens next

- v2's FREEZE stays unacked, so no sealed sampling runs for v2. The lead will write a dated amendment that withdraws
  v2 before any sealed read, with this file as the reason. VOID in section 6 is a different case (PLANT-DRIP failing
  to beat PLANT-L1), so v2 is not counted as a VOID attempt.
- Smoke (growth pilot ids only, never the seal) for the candidate fix: an assistant prefill of "```python" so the
  model writes code at once, plus one instruction sentence that asks for reusable top-level helpers which transform
  calls. It measures truncation, demo-pass, the helper-definition rate and how many helpers the registered rule
  accepts. An amendment and a run v3 are registered only if the smoke shows that a library can form, and only with an
  independent verifier's GO. The section 6 decision rule, the gates and the 400 sealed tasks stay as registered.
