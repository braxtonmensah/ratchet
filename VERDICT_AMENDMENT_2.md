# VERDICT on AMENDMENT_2_TRUNCATION_DRAFT.md (silicyte-0119, Ratchet, pilot v1)

Written 2026-11-04 20:56 ET (PowerShell Get-Date) by an independent verifier who did not write the draft. Read-only: nothing in
`ratchet/`, `runs/v1/` or the Quartz code copy was changed, nothing appended to PREREG.md, nothing committed. Numbers come from my
own script `/N/scratch/bsmensah/silo/a2_verify/a2vfy.py` (reads `runs/v1/pilot/{FLAT_A,FLAT_B,PLANT1}/samples.jsonl` and
`exec.jsonl`, the model's `tokenizer.json`; prints only) plus `runs/v1/PILOT.json`, `STATUS.json`, `pilot/PILOT_CHOICE.json`,
`pilot/PILOT_STOP.json`, `squeue -u bsmensah` at 20:51 ET, and code at commit 08d4a56 (`config.py`, `prompt.py`, `extract.py`,
`rounds.py`).

VERDICT: GO
BEST APPROACH: F3 (append the brief-rule, no-hand-tracing instruction to config.INSTRUCTION for every arm, max_tokens stays 4,096), with three required changes: the fallback on a failed screen is the v1 instruction at 4,096 (not F2), the screen also requires token-matched pass@2 test-correct tasks >= 22, and the 0.951 "anchor" is removed from the rationale because it is a task-easiness confound.
MOVES THE GOAL: No. The question, arms, metric, decision rules, seal and section 3 sampling are unchanged and the change lands before any growth or sealed data; it does move the operating point (library-to-FLAT token price per sample about 2.26 to about 4.6, so FLAT-TTC gets about 2x more extra samples per library sample), which makes COMPOUNDS harder, not easier, and must be stated in the amendment and RESULT.md.

## 1. Chain state: nothing to stop

The task premise that the pilot is RUNNING is stale. `STATUS.json`: jobs 12678501 and 12678502 both `DONE`, exit
`WAITING_BLOCKED_PILOT_PLANT_FAIL`; `next_unit` = `{"kind": "blocked", "condition": "PILOT_PLANT_FAIL"}`. `pilot/PILOT_STOP.json`
exists (`reason PILOT_PLANT_FAIL`), and `rounds.next_unit` returns `blocked` whenever that file exists (rounds.py lines 423 to 426),
so `chain.sh` prints CHAIN_STOP and submits nothing. `squeue` at 20:51 ET shows no `maxRATCH_*` job pending or running.
`PILOT_CHOICE.json` has `S: null, R: null`, so growth could not start from it even if the stop file were removed.
Required: do not delete `PILOT_STOP.json` or edit `PILOT_CHOICE.json` in v1. Re-run the pilot in a fresh run dir (v2) under the
new commit, after the amendment line is appended.

## 2. Re-derived numbers (mine vs the draft)

| quantity | mine | draft | match |
|---|---|---|---|
| finish_reason=length FLAT_A / FLAT_B / PLANT1 / pooled | 304 / 300 / 293 / 897 of 1,200 | same | yes |
| NO_CODE | 255 / 260 / 239 / 754 | same | yes |
| truncated: no fence / grid-only / open code / code then more | 238 / 506 / 85 / 68 | same | yes |
| truncated with any code block | 50 / 44 / 59 / 153 | same | yes |
| gen tokens total; in NO_CODE | 4,336,292; 3,084,977 (71.14%) | same | yes (ledger counts 4,336,604 from vLLM usage, +312) |
| FLAT_A gen tokens | 1,451,835 (mean 3,629.6 per sample) | 1,451,835 | yes |
| all-8-truncated task-arms | 27 / 31 / 28 = 86 of 150 | same | yes |
| demo-pass tasks | 24 / 22 / 21 | same | yes |
| demo-pass stopped / truncated | 249 of 303 / 50 of 897 | same | yes |
| pre-code tokens, stopped, pooled p10 / p50 / p90 / mean | 402 / 1,466 / 2,777 / 1,536 (n 300, min 163) | 402 / 1,473 / 2,791 / 1,536 | yes (interpolation) |
| tokens after last code fence, stopped | 0 max in every arm | 0 | yes |
| code tokens, stopped, p50 / p90 / mean | 199 / 390 / 228 | 199 / 392 / 228 | yes |
| truncated with `def transform` that were extracted | 50 of 50, 41 of 43, 55 of 55 | same | yes |
| demo-pass by gen-token bin, FLAT_A | 17/18, 22/25, 24/28, 22/26, cut 21/303 | same | yes |
| pre-code [100, 500) stopped | 39 of 41 demo-pass | same | yes, but see 3.3 |
| PLANT1 ERROR | 43 (22 stopped), 19 tasks, `ValueError ... unpack`, helpers_callable 35 | same | yes |
| hedge rate | Wait/Actually/Hmm only: stop 0.79 / 0.71 / 1.10, truncated 1.49 / 1.41 / 2.10 per 1k | 2.0 to 3.4 vs 3.7 to 6.25 (wider word list) | same direction |

Physics floor arithmetic re-checked: 5,614.7 x 3,600 = 20.21 M; x 0.7114 = 14.38 M; (3,120 - 762) x 5,614.7 = 13.24 M, x 0.7114 =
9.42 M; 446 code-carrying samples / 4.336 M = 102.9 per M, x 20.21 = 2,079 per hour; floor 228 + 1.387 x 587.5 / 8 = 330, 20.21 M /
330 = 61.2 k = 29.4x; 1,536 / 5,614.7 = 0.274 s vs 0.00246 s = 111x. F2: 1 - 0.9577^8 = 0.292; 490 / 7.51 = 65.2 vs 299 / 4.336 =
69.0 per M. Compute ratio: 10,774.7 / 4,774.7 = 2.26; 7,660.9 / 1,660.9 = 4.61. F3 context: 8,413 + 6,000 + 4,096 + 300 = 18,809
< 20,480, so no `VLLM_MAX_MODEL_LEN` change is needed under F3. All correct.

## 3. Is F3 the best approach? Yes, with changes

3.1 F3 over F1: agreed. No stopped sample had fewer than 163 pre-code tokens, so code-first has no observation at all.

3.2 F3 over F2, and F2 is not a valid fallback. The draft's own estimate puts F2 at 65.2 demo-pass samples per M tokens vs 69.0
for v1 as it stands, with an optimistic hazard (86 of 150 task-arms had 0 stops), plus it changes a registered section 3 parameter
and `VLLM_MAX_MODEL_LEN`. A fallback that the draft predicts is worse per token than doing nothing, and that edits section 3, should
not be what a failed screen buys. Required change: if the F3 screen fails, restore the v1 instruction at max_tokens 4,096 and
re-run the pilot under v1 (the PLANT fix still applies). F2 can be proposed later only under its own amendment with its own kill test.

3.3 The 0.951 anchor is a task-easiness confound, not evidence for F3. The 41 samples in the [100, 500) pre-code bin sit on only 10
task-arms; the other 39 samples on those same task-arms passed 32 of 37 stopped and only 2 of 39 truncated, so these are easy tasks
where everything works. Within task-arms that have both a short (< 500) and a long (>= 1,500) stopped sample, short passed 1 of 3 and
long 7 of 10 (too small to read, but the wrong sign for the anchor). Required change: delete "anchor ... 0.951" from the F3
rationale and say plainly that nothing in v1 shows F3 keeps accuracy on hard tasks; the registered screen is the only evidence.
The amendment line in section 5 does not cite 0.951 and can stay as is on this point.

3.4 The screen must also guard generalization, not only demo-pass. "Your program is run on every example for you" plus a
three-sentence cap invites demo-fitting (lookup tables, special cases) that raises demo-pass while lowering test-correct. In v1,
demo-pass samples were test-correct 100 of 106, 97 of 101 and 89 of 92 (13 of 299 = 4.3% demo-fit), and pass@2 test-correct tasks
were 23 (FLAT_A) and 21 (FLAT_B) (`PILOT.json` discordance). Growth and pilot test outputs are not sealed and the pilot already
reads them for d, so this costs no seal. Required change: F3 stands iff the token-matched screen round has at least 23 demo-pass
tasks AND at least 22 pass@2 test-correct tasks (mean of 23 and 21). Report the demo-pass-but-test-wrong share.

3.5 Optional (saves a wasted pilot): run FLAT_A under F3 first, compute g and S_screen, run the screen, decide, and only then run
FLAT_B and PLANT1 under the chosen instruction. As drafted, a failed screen discards a full F3 pilot.

## 4. Fairness of every registered comparison

- Applies equally to all arms: yes. `prompt.build_messages` and `_build_knockout_inline` read the single `INSTRUCTION` for every
  arm, phase, round and seed; library and exemplar notes are appended after it in the same way, so round 1 of STOCK, STATIC and
  EXEMPLAR stays byte-identical (SPEC 13 I3). The sentence "your program is run on every example" is true in every phase (demos are
  executed for selection in growth and sealed alike).
- Sealed data: none used. The pilot and the screen run on the 50 pilot growth tasks only.
- Tuning on growth outcomes: the screen reads FLAT outcomes only and picks one instruction for all arms; it cannot favour STOCK.
  If anything it optimizes FLAT efficiency, which strengthens FLAT-TTC (conservative). Required: screen samples are written under
  `pilot/` with phase `pilot` and never feed L_r, exemplars, SHAM or helper ranking.
- Compute matching: the section 4 FLAT-TTC rule is unchanged, but at g about 500 a library sample costs about 4.61x a FLAT sample
  instead of 2.26x, so FLAT-TTC gets about twice the extra samples per library sample. This is honest accounting under the
  registered rule and harder for STOCK; the amendment line already says RESULT.md reports the measured ratio. Also state that the
  section 8 prediction was made at the v1 operating point and is left unchanged.
- PLANT_FAIL is independent and must close first. 43 ERROR in PLANT1 vs 4 and 2 in FLAT, 22 of them in stopped samples, spread over
  19 tasks; messages are tuple-unpack errors with `static_refs` such as `['objects', 'size']`, consistent with model code misreading
  arc-dsl return types (for example `objects` items are `(value, (i, j))` pairs). F3 tells the model not to trace grids, which may
  make helper misuse worse, so the PLANT check must be re-run under F3 and must pass (+1 task) before growth. Its fix is a code or
  prompt change for its own amendment.

## 5. Required changes before appending (summary)

1. Fallback on a failed screen = v1 instruction at max_tokens 4,096, not F2 (edit section 4 and the section 5 line).
2. Screen pass needs >= 23 demo-pass tasks AND >= 22 pass@2 test-correct tasks at the token-matched S; report the
   demo-pass-but-test-wrong share (v1: 13 of 299).
3. Remove the 0.951 anchor from the F3 rationale; cite the confound (10 task-arms, other samples 32 of 37 stopped pass).
4. New commit with the INSTRUCTION edit, the `LEVER INSTRUCTION sha=` marker, the hash refusal and the screen unit, tests updated
   and run; fresh run dir v2; v1's PILOT_STOP.json left in place.
5. PLANT ERROR audit closed under its own amendment before the re-run pilot can pass 7.2.
6. Append only after Amendment 1 is resolved (numbering), with HH:MM from PowerShell Get-Date.
