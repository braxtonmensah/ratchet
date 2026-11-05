# BUILD_SMOKE_A5 (Amendment 5 candidate smoke, silicyte-0119)

Builder report, 2026-11-05 ET. Built and dry-run only: no GPU job was submitted, nothing was committed or pushed, no
existing file was edited (ratchet/*.py untouched; Quartz code dir b636ce5 only gained the two new files below).

## Files (laptop and Quartz copies equal)

| file | sha256 |
|---|---|
| diag/smoke_a5.py | f765be121421835c59b3f2a9b93edd4b4e132c6e7d499c012acf710e6a28d06d |
| slurm/smoke_a5.sbatch | 745c7cac3647e4fcc51db252012a544a13a973436ebc99eba3481d2d8305b76e |

Quartz copies: /N/scratch/bsmensah/silo/ratchet/code/diag/smoke_a5.py and code/slurm/smoke_a5.sbatch.
Outputs go to /N/scratch/bsmensah/silo/ratchet/diag/ (SMOKE_A5.json, SMOKE_A5.md, smoke_a5/ rows and logs); the script
refuses any out dir under runs/.

What it does: modes `serve` (in the sbatch), `control` (CPU positive control) and `dryrun` (no server). P0 = V1 as growth
sends it, P1 = V1 + assistant prefill, P2 = V1 + the helper sentence + prefill; S = 4 on the 50 pilot ids, registered
sampling, one fixed seed per task shared by all variants (seed_for with phase `smoke_a5`, RUN.json seed_base). Variants
run one after another on one server (so per-variant wall seconds are clean; P1 reuses P0's cached prompt prefix). The
client is `llm.VLLMClient` subclassed only to append `{"role": "assistant", "content": "```python\n"}` and set
`continue_final_message: true`, `add_generation_prompt: false`. Measuring path: extract.extract_code(prefill + completion),
sandbox.run_batch (empty library, callable), test_correct as arms.execute, select.pass2 as pilot.pass2_correct,
helpers.build_solution with an empty library, helpers.accept(dedup_solutions(...), library.empty(...), model tokenizer).
Refusals: ids = arc_io.pilot_ids(50) must equal the task set of runs/v2/pilot/V1_FLAT_A, be a subset of the sha-checked
growth list, and have no overlap with arc_io.sealed_id_list() (the sha-checked repo list; the sealed data dir is never
opened; guard.install_audit_hook() is installed first). Model files are checked by size and mtime against runs/v2/RUN.json
(read-only). The sbatch copies serve_and_step.sh: same TEST_ENV_REFUSED loop, env_vllm.sh, sandbox self-test, identical
vLLM command line and flags, 900 s readiness loop, SIGINT then SIGKILL after 30 s; stop issuing at 3,120 s.

Extra checks the serve log prints: P0 prompt_tokens per task against the v2 V1_FLAT_A ledger (byte-equivalent prompt),
the server-side rendered tail for one P1 and one P2 request via POST /tokenize, and generated-token totals (tokenizer sum
per sample and server usage) per variant.

## Positive control (CPU, login node h1, 2026-11-05 06:58 ET; diag/SMOKE_A5_CONTROL.json)

| target | want | got |
|---|---|---|
| V1_FLAT_A demo-pass tasks | 22 | 22 |
| V1_FLAT_A finish=length share | 0.7750 | 0.7750 |
| STOCK round_1 demo-pass tasks | 165 | 165 |
| STOCK round_1 accept() helpers | 0 | 0 |

ALL_OK=1. Side numbers: code re-extracted from text equals the stored code 400/400 and 1600/1600; gen-token recount equal
400/400 and 1600/1600; per-sample demo_pass agrees with the stored exec rows 398/400 and 1598/1600 (2 flips each, timing
at the sandbox limit; task counts unaffected). STOCK r1: finish=length 0.7656 (1,225/1,600), 437 demo-passing programs,
3 with a reachable top-level helper (0.0069), 5 distinct helper hashes, 405 deduped solutions (stored 407, the 2 flips).
V1_FLAT_A: pass@2 test-correct 22 of 50, 0 programs with a top-level helper.

## Rendered-prompt check

Qwen3.6 chat_template.jinja renders an assistant message as `<|im_start|>assistant\n<think>\n` + reasoning + `\n</think>\n\n`
+ content when it comes after the last user turn, so the empty think block IS rendered before the prefill, byte-equal to
the enable_thinking=0 generation prompt (`prefix_equals_gen_prompt: true` for P1 and P2). But the template applies `|trim`
to message content, and transformers 5.18 (used by vLLM 0.30.0 for continue_final_message) then cuts at the trimmed tag
and rstrips, so the model sees `...</think>\n\n```python` WITHOUT the trailing newline. Offline tail (P1):
`...complete program.<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n```python`. P2 ends the same after
`...keep transform short by calling those functions.<|im_end|>`. Consequence handled in code: the program text is the
EFFECTIVE prefill (taken from the server's /tokenize render in the job, fallback "```python\n") + completion; the model's
first token will normally be the newline. The job log prints RENDER_TAIL and PREFILL_EFFECTIVE so the verifier can confirm
it on the server.

Dry run (login node, no server): 150 requests, 600 unique sample ids, P0 and P1 share seeds and messages, P0 task and
instruction token split equals the v2 V1_FLAT_A ledger 50/50, request bodies carry the two flags only for P1/P2; the
full serve path (sample, extract, sandbox, pass2, build_solution, accept, writing rows) ran on 5 tasks against
llm.StubLLM fed with V1_FLAT_A texts (DRYRUN_RC=0, 07:03 ET; plumbing only, the stub always says finish=stop): P0 3 demo-pass
tasks of 5, P1 and P2 extract code from (effective prefill + cut fixture) and pass demos on 3 and 1 tasks. A first dry run
had cut the fixtures after "```python\n" and so extracted 0 programs for P1/P2; that showed the trimmed-newline issue
above, and both the stub fixture and the re-attachment now use the rendered prefill. Log:
/N/scratch/bsmensah/silo/ratchet/diag/smoke_a5/dryrun.log, rows in diag/smoke_a5_dryrun/.

## EXEMPLAR pool_R.json n = 0: not reproduced

On disk runs/v2/arms/EXEMPLAR/pool_R.json has `"n": 217` and 217 exemplars (round 4, schema ratchet.exemplar_pool.v1), its
sha256 48aca465... equals FREEZE.json libraries.EXEMPLAR.sha256_json and round_4/round_state.json n_exemplars 217. EXEMPLAR
rounds 2, 3, 4 sent exemplars in every one of their 1,600 samples (exemplar_ids non-empty 1600/1600); round 1 is STOCK's
shared round (0, by design). So EXEMPLAR did NOT see the FLAT prompt in rounds 2 to 4. Likely sources of the n = 0
reading: (a) the file is written with sorted keys, so `"n"` sits on the last lines after the 217-entry `exemplars` list
(arms.py:1003 body, written by atomic_write_json); a `head` shows only exemplars; (b) the pool file is written only when
r == R (ratchet/arms.py:1000), so rounds 1 to 3 have no n_exemplars field and no pool file (earlier rounds rebuild the pool
in memory, arms.py:873 -> exemplar.pool_from_rounds, exemplar.py:115); (c) a library-style reader (n_helpers / helpers)
gets 0 because the pool has neither key. Latent inconsistency worth knowing: arms.py:1003 writes its own body (no
`sha256`, no `scaler`), so exemplar.load_pool (exemplar.py:155) would refuse this file; sealed sampling does not use it
(arms.frozen_library reads `exemplars` directly, arms.py:1376 to 1381).

## Command for the lead (after the verifier's GO)

```
cd /N/scratch/bsmensah/silo/ratchet/code && env -u RATCHET_DATA_ROOT -u RATCHET_KEY_ROOT -u RATCHET_SANDBOX_NET -u RATCHET_SANDBOX_SPAWN -u RATCHET_ROOT -u RATCHET_TEST -u RATCHET_PY sbatch -o /N/scratch/bsmensah/silo/ratchet/diag/smoke_a5/%j.out slurm/smoke_a5.sbatch
```

h100-debug allows 1 running job per user, so it queues behind any running maxRATCH job. Expected: vLLM start about 5 min,
3 x 200 samples, then SMOKE_A5.json / SMOKE_A5.md in /N/scratch/bsmensah/silo/ratchet/diag/.
