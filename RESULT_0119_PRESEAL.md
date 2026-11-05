# RESULT silicyte-0119 (Ratchet): LIBRARY_CANNOT_FORM, ended before any sealed read (2026-11-05 07:44 ET)

## Verdict

Qwen3.6-35B-A3B fp8, thinking off, at max_tokens 4,096, does not build an in-context helper library under PREREG 4's
acceptance rule. The rule accepts a helper when it is the same function up to renaming (one canonical hash) and is
defined in demo-passing solutions of at least 2 tasks, or carries an MDL gain of at least 20 tokens. Run v2 grew
nothing in 4 rounds. Under the decision rule committed before the smoke ran, neither candidate fix qualified.
silicyte-0119 therefore ends here. The 400 sealed tasks were never opened and stay sealed.

Under PREREG section 9 Silicyte drops in-context library compounding, as registered, for this model and budget.

## Evidence

1. **Run v2 growth** (code b636ce5; S = 4, R = 4; INSTRUCTION_V1): STOCK accepted 0 helpers in every round, and ONE-SHOT
   and SHAM are empty. In STOCK round 1, 1,225 of 1,600 samples stop at the token cap, and only 1 to 4 of about 435
   demo-passing programs per round define a top-level helper. EXEMPLAR is the only arm whose prompt differs from FLAT
   (217 exemplars). FREEZE.json (730ec199...) was never acked; v2 is WITHDRAWN_PRE_SEAL. Details:
   GROWTH_V2_DIAGNOSIS.md.
2. **Decision rule fixed before the smoke.** It was committed and pushed at 06:46:35 ET (f59281e); the smoke job was
   submitted at 07:14:34 and started at 07:27:12 (sacct).
   - A variant qualifies if A >= 5 accepted helpers, H >= 0.20 and D >= D(P0) - 5.
   - The exact definitions of A and H were pushed at 07:14 (bdec369), before submission.
   - The verifier's GO is in diag/VERDICT_SMOKE_A5.md; it re-ran the CPU control (22 / 0.7750 / 165 / 0) and checked
     A and H on a synthetic shared helper.
3. **Smoke** (job 12686909, 07:27:12 to 07:41:34, h100-debug g37). The run used the 50 pilot growth ids, S = 4, the
   registered sampling, and all three variants in one server. Source: diag/SMOKE_A5.md and SMOKE_A5.json on Quartz.

   | variant | finish=length | demo-pass tasks /50 | pass@2 /50 | H | distinct helper hashes | A | qualifies |
   |---|---|---|---|---|---|---|---|
   | P0 V1 (control) | 0.755 | 19 | 18 | 0.019 | 1 | 0 | no |
   | P1 V1 + prefill "```python" | 0.585 | 22 | 20 | 0.000 | 0 | 0 | no (A, H) |
   | P2 P1 + helper sentence | 0.500 | 20 | 17 | 0.268 | 28 | 0 | no (A) |

   - P2 got the model to write helpers: 15 of 56 demo-passing programs define a reachable, valid top-level helper.
     None of the 28 helper hashes occurs twice, even across the 4 samples of one task.
   - By name, 41 helper names appear and only 2 recur across tasks (`solve` and `find_nonzero_positions`, 3 tasks each);
     their code differs.
   - P0 reproduces v2's control: 0.755 vs 0.7750 truncation, and its prompt tokens equal V1_FLAT_A's on 50 of 50.

## Limits (stated, not tested)

- The rule was set at the smoke's scale: 50 tasks and about 56 demo-passing programs per variant. Growth runs 400
  tasks per round. At that scale more programs could recur by chance, and the smoke cannot rule that out. What it
  measured is 0 recurrences among 28 helpers. The registered rule says stop, and this result follows it.
- The negative is about exact (alpha-equivalent) acceptance. A library that merges helpers by behaviour (same outputs on
  the same inputs) is a different hypothesis. It would need its own registration and its own sealed set; this study
  does not test it.
- The prefill lowered truncation (0.755 to 0.585 and 0.500), but the model still often ran past 4,096 tokens inside
  the code block: P2 had 64 SYNTAX and 26 NO_CODE outcomes of 200.

## Files

- GROWTH_V2_DIAGNOSIS.md
- AMENDMENT_5_DRAFT.md (parts A and C apply; parts B and D are moot)
- diag/BUILD_SMOKE_A5.md, diag/VERDICT_SMOKE_A5.md, diag/hoist_probe.py
- diag/smoke_a5.py (f765be12...), slurm/smoke_a5.sbatch (745c7cac...)
- On Quartz under /N/scratch/bsmensah/silo/ratchet/: runs/v2 (growth evidence), plus the smoke outputs
  diag/SMOKE_A5.{json,md} and diag/smoke_a5/{P0,P1,P2}_{samples,exec}.jsonl
