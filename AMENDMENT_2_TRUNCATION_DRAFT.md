# AMENDMENT 2 (DRAFT): generation truncation in silicyte-0119 (Ratchet), pilot v1

Drafted: 2026-11-04 20:48 ET (PowerShell Get-Date). Status: DRAFT. Not appended to PREREG.md, not registered in the loop ledger,
not committed. Nothing in `ratchet/`, `runs/v1/` or the Quartz code copy was changed. All numbers come from read-only scripts run on
the Quartz login node over `runs/v1/pilot/{FLAT_A,FLAT_B,PLANT1}/samples.jsonl` and `exec.jsonl` (400 + 400 rows per arm) and
`runs/v1/PILOT.json`; token counts use the model's own `tokenizer.json` (`tufa/models/qwen36_35b_a3b_fp8`). Scripts:
`/N/scratch/bsmensah/silo/a2_trunc_analysis/trunc_an.py`, `trunc_an2.py`, `show.py` (they read, print, and write nothing).

Numbering: if AMENDMENT 1 (self-FT, still a draft) is not appended first, this becomes AMENDMENT 1. The line must begin
`AMENDMENT <n> ` exactly.

Pilot v1 state (SOURCE `runs/v1/PILOT.md`, `STATUS.json`): job 12678501 finished all three arms (FLAT_A 20:28 to 20:33, FLAT_B to
20:37, PLANT1 to 20:41 ET). Status **PLANT_FAIL**: PLANT1 21 demo-pass tasks vs FLAT_A 24, gain -3 (needs >= 1). Smoke passed (24 vs 22 of 50). d = 0.12. The run is blocked (`WAITING_BLOCKED_PILOT_PLANT_FAIL`), so a pilot
re-run is required whatever this amendment says.

## 1. The measured problem

### 1.1 Per arm

| quantity | FLAT_A | FLAT_B | PLANT1 | pooled |
|---|---|---|---|---|
| samples | 400 | 400 | 400 | 1,200 |
| finish_reason = length | 304 (76.00%) | 300 (75.00%) | 293 (73.25%) | 897 (74.75%) |
| status NO_CODE | 255 (63.75%) | 260 (65.00%) | 239 (59.75%) | 754 (62.83%) |
| NO_CODE among truncated | 254 of 304 | 259 of 300 | 238 of 293 | 751 of 897 (83.7%) |
| truncated, no fence at all | 82 | 101 | 55 | 238 |
| truncated, only non-code fences (grids) | 172 | 155 | 179 | 506 |
| truncated, cut inside an open code fence | 31 | 24 | 30 | 85 |
| truncated, complete code fence, then kept writing | 19 | 20 | 29 | 68 |
| **truncated with a partial or complete code block** | 50 (16.45%) | 44 (14.67%) | 59 (20.14%) | 153 (17.06%) |
| demo-pass samples: stopped / truncated | 85 of 96 / 21 of 304 | 85 of 100 / 16 of 300 | 79 of 107 / 13 of 293 | 249 of 303 (82.2%) / 50 of 897 (5.6%) |
| tasks with all 8 samples truncated | 27 of 50 | 31 of 50 | 28 of 50 | 86 of 150 |
| demo-pass tasks (all / among tasks with >= 1 stopped sample) | 24 / 20 of 23 | 22 / 17 of 19 | 21 / 18 of 22 | |
| gen tokens total | 1,451,835 | 1,460,787 | 1,423,670 | 4,336,292 |
| gen tokens in NO_CODE samples | 1,043,955 (71.91%) | 1,063,546 (72.81%) | 977,476 (68.66%) | 3,084,977 (71.14%) |
| gen tokens in truncated samples | 1,245,183 (85.77%) | 1,228,797 (84.12%) | 1,200,120 (84.30%) | 3,674,100 (84.73%) |
| gen tokens per demo-pass sample | 13,697 | 14,463 | 15,475 | 14,503 |

Under independence, a 74.75% truncation rate gives 0.7475^8 x 150 = 14.6 all-truncated tasks; 86 were observed. Truncation is a
task property (hard tasks), not a per-sample coin flip.

### 1.2 Tokens before the first code fence, stopped samples (code fence = tagged python or a block with `def`/`import`)

| arm | n | p10 | p25 | p50 | p75 | p90 | max | mean |
|---|---|---|---|---|---|---|---|---|
| FLAT_A | 95 | 363 | 807 | 1,499 | 2,059 | 2,521 | 3,807 | 1,502 |
| FLAT_B | 99 | 358 | 1,003 | 1,584 | 2,314 | 3,084 | 3,599 | 1,683 |
| PLANT1 | 106 | 448 | 670 | 1,245 | 2,123 | 2,729 | 3,430 | 1,429 |
| pooled | 300 | 402 | 801 | 1,473 | 2,142 | 2,791 | 3,807 | 1,536 |

Tokens after the last code fence in stopped samples: 0 in all 300. The model ends at its code block. The code itself is short:
pooled code tokens in stopped samples p10 52, p50 199, p90 392, mean 228, max 2,427. Of a stopped sample's mean 2,185 gen
tokens, 1,536 (70%) come before the first code fence, 228 (10%) are the final program, and the other 421 (19%) are earlier code
drafts and prose between code blocks. In truncated samples that did open a
code fence, it opened late: p50 3,442 (FLAT_A), 3,404 (FLAT_B), 3,073 (PLANT1) tokens in, with 200 to 400 code tokens still needed.

What the prose is (`show.py` on FLAT_A): cell-by-cell coordinate enumeration ("Row 7: (7,3) and (7,5). Separated by (7,4)=0."),
hand-execution of candidate rules on the examples, and hypothesis churn. Hedge words (Wait, Actually, Hmm, Let me re-/check/verify)
per 1,000 gen tokens: stopped 2.27 / 1.97 / 3.38, truncated 3.99 / 3.70 / 6.25 (FLAT_A / FLAT_B / PLANT1). Digit-only grid lines are
only 4.8% to 8.4% of gen tokens, so this is not mainly grid copying. Repetition loops are rare: the last 300 characters recur
earlier in 13 of 897 truncated samples.

### 1.3 Demo-pass rate against output length

| gen tokens | FLAT_A | FLAT_B | PLANT1 |
|---|---|---|---|
| [0, 1000) | 17 of 18 (0.944) | 19 of 19 (1.000) | 20 of 21 (0.952) |
| [1000, 2000) | 22 of 25 (0.880) | 18 of 21 (0.857) | 24 of 30 (0.800) |
| [2000, 3000) | 24 of 28 (0.857) | 21 of 27 (0.778) | 19 of 30 (0.633) |
| [3000, 4096) | 22 of 26 (0.846) | 27 of 36 (0.750) | 16 of 27 (0.593) |
| 4,096 (cut) | 21 of 303 (0.069) | 16 of 297 (0.054) | 13 of 292 (0.045) |

Pooled stopped samples by tokens before the first code fence: [100, 500) 39 of 41 (0.951); [500, 1000) 41 of 52 (0.788);
[1000, 2000) 94 of 114 (0.825); [2000, 4096) 75 of 93 (0.806). Passing stopped samples had median 1,433 pre-code tokens, failing
ones 1,573. Within tasks with both outcomes among stopped samples (4, 4 and 8 tasks), passing samples had fewer pre-code tokens in
4 of 4, 2 of 4 and 4 of 8. On this record, more prose before the code does not buy a higher demo-pass rate (confounded by task
difficulty; the within-task read is too small to decide). A sample that finishes is right 82% of the time; the loss is samples that
never finish.

### 1.4 What the code does (rule 5)

- `prompt.py` / `config.INSTRUCTION`: asks for `def transform(grid):` and "Return one ```python fenced block containing the
  complete program." It neither requests nor forbids reasoning. With `enable_thinking=False` the model writes its reasoning as plain
  text before the block, uncapped except by max_tokens.
- `extract.py`: strips `<think>`; takes the last python block that parses and defines top-level `transform`; **a fence left open at
  the end of the text already counts** (`_FENCE` ends in `(?:```|\Z)`); falls back to the last block with a `def transform(` line so
  the sandbox records SYNTAX rather than NO_CODE. Check: every truncated sample containing `def transform` was extracted in FLAT_A
  (50 of 50) and PLANT1 (55 of 55); FLAT_B 41 of 43. The 85 cut-open code fences already reach the sandbox (pooled SYNTAX 32 come
  from these). **Extracting from unterminated fences is already implemented; its remaining effect is 0.** It is not a candidate.

### 1.5 Not a truncation effect: the PLANT_FAIL

PLANT1 has the lowest truncation share (73.25%) and the fewest NO_CODE (239), yet the fewest demo-pass samples (92 vs 106 and 101).
The difference is ERROR: 43 in PLANT1 vs 4 (FLAT_A) and 2 (FLAT_B), 22 of them in stopped samples (stopped demo-pass 79 of 107 =
0.738 vs 0.885 and 0.850). Sample errors read `ValueError: not enough values to unpack (expected 3, got 2)` and `too many values to
unpack (expected 2)` with `helpers_callable 35`, some with `helper_calls {}` and `static_refs []`. That needs its own audit (name
shadowing between the 35 callable arc-dsl helpers and model code, or arc-dsl's tuple-of-tuples Grid type, are candidates, not
findings). This amendment does not fix it, and the PLANT check will fail again if only truncation is fixed.

## 2. Physics floor (rule 1)

Inputs (SOURCE `PILOT.json` rates): decode fit a = 5,614.7 gen tok/s, b = 1.387 gen-token-equivalents per uncached prefill token;
uncached prompt 587.5 tokens per FLAT request of n = 8; vLLM startup 762 s; jobs stop issuing at 3,120 s (`config.STOP_ISSUE_S`);
sandbox 0.00246 s per executed sample.

- Gen tokens per busy H100-hour: 5,614.7 x 3,600 = 20.21 M. Per 1 h h100-debug job: (3,120 - 762) x 5,614.7 = 13.24 M.
- **Wasted per busy H100-hour: 71.14% x 20.21 M = 14.38 M tokens in samples that reach the sandbox with no code** (9.42 M per job);
  84.73% (17.12 M) sit in truncated samples.
- Delivered now: 446 of 1,200 samples carried code (102.9 programs per M gen tokens), 2,079 programs and 1,394 demo-pass samples
  per busy H100-hour.
- Floor: a sample that is only its program costs mean 228 code tokens + 1.387 x 587.5 / 8 = 102 prefill-equivalents = 330
  token-equivalents, i.e. 61.2 k programs per busy H100-hour: **29.4x the current 2,079**. The gap is the prose.
- The sandbox checks a program on every demo in 0.00246 s. Hand-tracing the demos in prose costs 1,536 pre-code tokens / 5,614.7 =
  0.274 H100-s per stopped sample, 111x the price of running the program. The unused constraint (rule 3): the harness verifies by
  execution for free, and the prompt never tells the model so.

## 3. Candidate fixes

Every fix below is a change to a single global (`config.INSTRUCTION` or `config.MAX_TOKENS`) read by every arm, phase, round and
seed through `prompt.build_messages` and `llm.sampling`, so it applies identically to STOCK, STATIC, ONE-SHOT, EXEMPLAR, SHAM,
FLAT-TTC, PLANT-DRIP and PLANT-L1, to knockout and to the perturbed copy. Each changes g (gen tokens per sample), the demo-pass rate,
throughput and d, so **each requires the full sec. 7 pilot to be re-run** (it must be re-run anyway: PLANT_FAIL).

Compute-matching note that applies to F1 and F3. PREREG sec. 4 gives FLAT-TTC STOCK's logged total tokens (including library prompt
tokens, counted per sample) divided by FLAT's mean tokens per sample. At v1, a FLAT sample costs P_task 1,160.9 + g 3,613.8 = 4,774.7
logical tokens and a library sample at the 6,000 cap 10,774.7: ratio 2.26. If g falls to about 500, the ratio becomes 7,660.9 /
1,660.9 = 4.61. The rule is unchanged and identical for every arm, but the library's context price roughly doubles relative to
FLAT-TTC's samples. This must be stated in RESULT.md, and the re-run pilot's power projection (sec. 7.3) absorbs it automatically
because it uses the measured g.

### F1. Code first, reasoning only as comments inside the code

INSTRUCTION gains: "Reply with the ```python block first, with nothing before it. Put any reasoning as short comments inside the
code. Do not trace the grids cell by cell; your program is run on every example for you."

- Expected effect: g about 230 to 600 (code p50 199, p90 392, plus comments): 6x to 16x more programs per gen token; truncation
  near 0 (1 of 300 stopped samples had a code block over 2,048 tokens). Demo-pass rate per program: **no observation exists** (0
  stopped samples had fewer than 100 pre-code tokens), so this is the least anchored of the three.
- Risk: removes the natural-language rule statement that precedes every observed passing sample.

### F2. max_tokens 4,096 to 8,192, prompt unchanged

- Expected effect from the stop hazard in the last 1,024 tokens (81 stops among 1,916 at-risk sample-bins, 0.0423 per 512 tokens):
  if constant, 1 - 0.9577^8 = 29.2% of truncated samples finish by 8,192, i.e. 262 of 897, at about 3,538 extra gen tokens per
  truncated sample (+73%, 7.51 M vs 4.34 M). At the late-finisher pass rate (3,000 to 4,096 bin, 65 of 89 = 0.730) that adds about
  191 demo-pass samples: 490 per 7.51 M = 65.2 per M vs 69.0 per M now. **No gain per token, and the hazard is optimistic**: 86 of
  150 tasks had 0 of 8 stops, so the hard tasks have a far lower hazard than the average.
- Compute: halves S at fixed 12 H100-hours. Context: 4 of 400 growth task blocks exceed 20,480 - 8,192 - 6,000 - 300 = 5,988
  tokens (growth task-block tokens p50 803, p90 2,175, p99 6,123, max 8,413), so library arms at the cap would exceed
  `VLLM_MAX_MODEL_LEN` 20,480 and be rejected unless it is raised. Sec. 3 registers 4,096, so this is a registered-parameter change.

### F3. Brief rule statement, then code (RECOMMENDED)

INSTRUCTION gains: "State the rule in at most three sentences, then give the code block. Do not trace the grids cell by cell; your
program is run on every example for you."

- Anchor in the existing samples: stopped samples with 100 to 500 pre-code tokens are the closest observed regime: 39 of 41 demo-pass
  (0.951), the highest bin. Expected g about 300 to 700 (a 100 to 300 token rule plus code p50 199): 5x to 12x more programs per gen
  token than v1's 3,613.8; truncation expected under 5%.
- Unlike F1 it keeps a stated hypothesis before the code, which every observed passing sample had; unlike F2 it moves tokens from
  hand-tracing to execution, which is 111x cheaper per check.
- Risk: in non-thinking mode the model may ignore a length instruction. The registered screen below catches that and falls back.

## 4. Recommendation

F3, with F2 as the registered fallback, decided by a token-matched growth-only screen inside the re-run pilot. F1 is dropped
because nothing in the record anchors its pass rate. The screen threshold uses the v1 A/A (FLAT_A 24, FLAT_B 22 demo-pass tasks of
50): the mean, 23.

Kill test, registered before the data: under the amended instruction, run the full sec. 7 pilot (FLAT_A, FLAT_B, PLANT1 at S = 8),
then one screen round FLAT_S on the same 50 tasks with S_screen = round(1,451,835 / (50 x g_new)), where g_new is the re-run FLAT_A's
mean gen tokens per sample, so FLAT_S spends v1 FLAT_A's 1,451,835 gen tokens within 10%. F3 stands iff FLAT_S has at least 23
demo-pass tasks. If not, restore the v1 instruction, set max_tokens 8,192 and `VLLM_MAX_MODEL_LEN` = 8,192 + 6,000 + 8,413 + 300 =
22,905 (rounded up to 24,576), and re-run the pilot again. Either way the PLANT ERROR audit (sec. 1.5) must close before the PLANT
check can pass. Re-run PILOT.md reports the finish_reason=length share, median gen tokens, and the share of samples with a
`def transform` (lever marker: print `LEVER INSTRUCTION sha=<sha256 of config.INSTRUCTION>` once per job and check it equals the
registered text's hash before reading any effect).

## 5. Exact amendment line to append under `## AMENDMENTS` (before any growth job and any sealed read)

```
- AMENDMENT 2 (2026-11-04 HH:MM ET, after pilot v1 job 12678501 read PLANT_FAIL, before any growth job and any sealed read):
  pilot v1 truncated 897 of 1,200 samples at max 4,096 generated tokens (74.75%); 754 (62.83%) reached the sandbox with no code
  and held 3,084,977 of 4,336,292 generated tokens (71.14%); stopped samples spent a median 1,473 tokens of prose before the code
  and passed demos 249 of 303. For every arm, phase, round and seed, config.INSTRUCTION gains, appended after its last sentence,
  exactly: "State the rule in at most three sentences, then give the code block. Do not trace the grids cell by cell; your
  program is run on every example for you." Sampling stays as section 3. Section 7 is re-run in full under the new instruction,
  plus one growth-only screen round on the same 50 pilot tasks with S = round(1,451,835 / (50 x g)), g = the re-run FLAT_A mean
  generated tokens per sample. The instruction stands iff that round has at least 23 demo-pass tasks (mean of v1 FLAT_A 24 and
  FLAT_B 22); otherwise the v1 instruction is restored, max generated tokens becomes 8,192, VLLM_MAX_MODEL_LEN becomes 24,576,
  and section 7 is re-run again. The FLAT-TTC rule of section 4 is unchanged; RESULT.md reports the measured ratio of library to
  FLAT tokens per sample. Each job prints LEVER INSTRUCTION sha=<sha256> and the run refuses a hash other than the registered text's.
```

Fill HH:MM from PowerShell Get-Date at append time. The sha256 of the new INSTRUCTION string is computed after the edit and written
into the loop ledger entry with the amendment.
