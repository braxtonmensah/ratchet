VERDICT: GO

BEST APPROACH: one h100-debug job that runs P0, P1 and P2 on the same server, the same 50 pilot ids, the same per-task seeds and the registered growth measurement code. It answers the one open question (can growth BUILD a library under this harness) with the part C rule, which was fixed before any sample. A cheaper offline test cannot answer it, because the open quantity is what the model writes under the prefill. A bigger test is not needed before part C.
MOVES THE GOAL: it produces A, H and D for part C. Either it registers run v3 with a library that can form, or Ratchet reports LIBRARY_CANNOT_FORM before any sealed read. Both are registered pre-seal outcomes for silicyte-0119.

Verifier: independent of the builder. Read-only (no edit, commit, submit, cancel, hold or release). 2026-11-05, 07:05 to 07:15 ET.

## SCOPE

- Code under test: diag/smoke_a5.py (sha256 f765be12...a28d06d) and slurm/smoke_a5.sbatch (745c7cac...305b76e). The laptop and Quartz copies are equal. All 36 ratchet/*.py files and slurm/serve_and_step.sh are also byte-equal between the laptop and /N/scratch/bsmensah/silo/ratchet/code (sha256 compared file by file). CODE_SHA reads b636ce5.
- Read: GROWTH_V2_DIAGNOSIS.md, AMENDMENT_5_DRAFT.md (part C), BUILD_SMOKE_A5.md, PREREG.md sections 2 to 7, and the code paths in llm, prompt, config, extract, sandbox, select, helpers, arms, arc_io, tok and ledger.
- Ran on login node h2: the builder's CPU control (output to diag/verify_a5/, so the builder's file is not overwritten), an id/seal check, a tokenizer probe, an extraction probe, and a synthetic positive check of measure().
- Not covered: the server-side render and generation behaviour. Only the job can show these. See "Lead checks on the job log" at the end.

## WHY

- The ids are the v2 pilot's 50 growth ids, with zero sealed overlap. Nothing opens the sealed data or key dirs, and nothing writes under runs/.
- The measuring path is growth's own functions, called the same way.
- A, H and D match part C (H is pinned down below).
- P0 is growth's V1 prompt. P1 and P2 differ only as the draft says.
- The prefill re-attachment cannot lose or double a line under this tokenizer.
- The vLLM flags are identical to serve_and_step.sh. The job fits h100-debug with the 3,120 s stop.
- I reproduced the control: 22 / 0.7750 / 165 / 0. A synthetic positive check showed that measure() does count and accept a shared helper.
- None of the defects below can make the A/H/D numbers wrong in a way the outputs would not show.

## Evidence

### 1. Seal safety

- The audit hook is installed before any other ratchet import: smoke_a5.py:46-48.
- Ids:
  - smoke_ids() at smoke_a5.py:104-121 refuses unless arc_io.pilot_ids(50) equals the task set of runs/v2/pilot/V1_FLAT_A, has no overlap with arc_io.sealed_id_list(), and is a subset of growth_id_list().
  - sealed_id_list() is the sha-checked repo file splits/sealed_ids_arcagi1_eval.txt (arc_io.py:41, 108-109). It is not the sealed data dir.
  - My independent run gave: pilot n=50, sha 0ac994f4...e004, sealed list n=400, overlap pilot/sealed 0, overlap growth/sealed 0, pilot in growth = 1, equal to the v2 pilot = True.
- Task loading:
  - load_tasks() refuses any split other than pilot/growth (smoke_a5.py:124-127).
  - The pilot split maps to data/growth (arc_io.py:34). Every data read goes through guard.check_data_read (arc_io.py:192-193).
- Reads under runs/v2, all read-only:
  - RUN.json (smoke_a5.py:132, 152)
  - the ledger via ledger.iter_rows, which only reads (smoke_a5.py:145-148)
  - the V1_FLAT_A samples (smoke_a5.py:99-101)
  - in control mode, the pilot and STOCK round_1 rows
- Writes:
  - check_out_dir (smoke_a5.py:87-96) refuses any path under runs/ or a guard-protected root. The sbatch refuses OUT under runs* (smoke_a5.sbatch:20).
  - All writes go to <out>/SMOKE_A5.json, <out>/SMOKE_A5.md and <out>/smoke_a5/* (smoke_a5.py:434-435, 455, 472). The vLLM and driver logs go to diag/smoke_a5/ (sbatch:51, 72).
- After two control runs (builder's and mine), `find runs/v2 -newer diag/smoke_a5.py` returned nothing.

### 2. The measurement equals growth's

- Extraction:
  - Growth: extract.extract_code(text) at arms.py:581. Smoke: extract.extract_code(prefill_eff + completion) at smoke_a5.py:351-352, or of the completion alone for P0.
  - gen_tokens counts the completion only (smoke_a5.py:355), which is the generated text. Growth counts the whole text (arms.py:587), and for P0 the two are the same.
- Execution:
  - ExecJob(library_src='', mode='callable') at smoke_a5.py:261-262. This is the same as growth STOCK round 1 (library None, so library_src '' at arms.py:642-644, 680-683, mode 'callable' at arms.py:925).
  - The NO_CODE row is identical to arms.py:675-678.
  - The in-process exec cache key includes task, code, library and mode (sandbox.py:682-683), so cross-variant hits give identical results.
- demo_pass comes from the sandbox row. test_correct is demo_pass AND outputs_equal (smoke_a5.py:244-248, 268), which is identical to arms.py:632-639, 705-706.
- pass@2 uses select.candidate_from_exec + select.pass2, then checks whether any attempt equals the public test outputs (smoke_a5.py:286-290). This is the pilot.pass2_correct path (pilot.py:303-314).
- build_solution(..., empty.hashes(), demo_pass=True) is applied to demo-passing rows only (smoke_a5.py:291-298). This matches round_solutions (arms.py:952-968).
- Acceptance:
  - helpers.accept(dedup_solutions(sols), library.empty, tk) at smoke_a5.py:305-306 matches finalize_round (arms.py:985-987). accept() re-dedups internally (helpers.py:585), and the thresholds are ACCEPT_MIN_TASKS 2 and ACCEPT_MIN_MDL 20, as in PREREG 4.
  - tk is the real model tokenizer (tok.load_tokenizer). The sbatch sets RATCHET_REQUIRE_REAL_TOKENIZER=1.
  - accept()'s growth-phase check passes because the smoke's sample ids are 'Pk|growth|r1|...' (smoke_a5.py:187). Control rows are relabelled pilot -> growth only for counting (smoke_a5.py:272-277).

What the script reports against part C:
- **A = `helpers_accepted`.** This is len(accept(...)) with an empty previous library, dependency closures included, exactly as growth computes it. It matches part C.
- **D = `demo_pass_tasks`.** This is the number of distinct tasks of 50 with at least one demo-passing sample of 4 (smoke_a5.py:319). It matches round_counts (arms.py:714-725) and part C.
- **H = `share_demo_pass_with_toplevel_helper` = n_with_helper / len(sols)** (smoke_a5.py:301-303, 324).
  - Numerator: demo-passing PROGRAMS (samples, not deduped) whose Solution.helpers is non-empty. Solution.helpers is the set of top-level defs reachable from transform through the call graph that are also valid, meaning no unbound free names and no invalid dependency (helpers.py:468-488, 531). So H counts REACHABLE helpers, and only those PREREG 4 could extract.
  - Denominator: demo-passing programs that parse and have a top-level `def transform` (build_solution not None). It is not tasks and not deduped solutions. In both controls the denominator equals the demo-pass sample count (100/100 and 439/439).
  - This is the right reading of part C, given the diagnosis's "top-level helper (PREREG 4's unit of extraction)". But it is one notch stricter than the bare words: a helper that reads a module-level constant (for example `DIRS = [...]`) is not counted.
  - The lead should state in the amendment, before reading the smoke, that H is this extractable-reachable share. If a looser H is ever wanted, it can be recomputed from diag/smoke_a5/Pk_samples.jsonl and Pk_exec.jsonl without a GPU.
- Synthetic positive check (diag/verify_a5/vpos.py, measure() itself) used 5 demo-passing programs: the same helper `flip_rows` called from transform on 2 tasks, one helper that uses a module constant, one unreachable helper, and one nested helper. Result: H = 2/5 = 0.40, distinct hashes 1, A = 1 (flip_rows, by 'both', tasks 2, mdl_gain 23), D = 3. So the A and H machinery does fire. The v2 control only ever exercised the zero side.

### 3. Prompts, sampling, prefill

- P0:
  - prompt.build_messages(task, tk, instruction=config.INSTRUCTION_V1) at smoke_a5.py:184.
  - Growth calls build_messages(task, tok, library=None, exemplars=None, inline_noncallable=False, cap_tokens=run.cap, instruction=V1 text) (arms.py:476-477). With no library, cap_tokens only bounds the library block (prompt.py:335-342), so the messages are identical.
  - v2 RUN.json has instruction 'V1', with the sha equal to config.INSTRUCTION_V1_SHA256. config refuses to import if the text drifts.
  - The builder's dry run showed the task/instruction token split equal to the v2 V1_FLAT_A ledger 50 of 50. The job also logs P0_PROMPT_TOKENS_EQUAL_V1_FLAT_A against the server count.
- P1 and P2:
  - VARIANTS (smoke_a5.py:57-65): P1 is the V1 instruction plus the prefill. P2 is V1 + ' ' + the helper sentence plus the prefill. The sentence is byte-equal to AMENDMENT_5_DRAFT B.
  - PrefillMixin (smoke_a5.py:159-169) only appends {'role': 'assistant', 'content': '```python\n'} and sets continue_final_message true and add_generation_prompt false. P0 bodies carry neither flag (dry-run BODY lines).
- Sampling: config.SAMPLING is {'temperature': 0.8, 'top_p': 0.95, 'max_tokens': 4096, 'enable_thinking': False}. It is sent via llm.build_body (llm.py:167-171), unchanged.
- Seeds and concurrency:
  - Per task, seed_for(seed_base 1000, 'smoke_a5', 1, task, 0, None) is shared by P0, P1 and P2 (smoke_a5.py:185). The dry run showed the same seed and messages for P0 and P1.
  - max_inflight is 320 // 4 = 80, the same as growth.
- Prefill handling:
  - The offline render (dryrun.log RENDER_OFFLINE) ends `</think>\n\n```python`, with the trailing newline trimmed. The prefix equals the enable_thinking=0 generation prompt.
  - effective_prefill() takes the text after the think-off header from the server's /tokenize render, falling back to '```python\n' (smoke_a5.py:233-238, 416). The program text is effective prefill + completion (smoke_a5.py:351).
  - Tokenizer probe (Qwen3.6 tokenizer.json): '```python\n' encodes as ['```', 'python', 'Ċ'] and the trimmed form as ['```', 'python']. The newline is its own token, so the model sees an in-distribution prefix and its natural first token is 'Ċ'.
  - Extraction probe:
    - prefill + '\nimport...' extracts the full program, first line included.
    - If vLLM ever echoes the prefill, '```python```python\n...' still extracts the one program.
    - If the server render keeps the newline and the fallback re-attaches it, '```python\n\n...' still extracts.
  - Each sample is one row from one completion, so double counting is impossible.
  - Residual risk: a completion whose first token is not a newline ('```pythonimport ...') gives NO_CODE. It shows up as a lower code_extracted_share, not silently. Given the tokenization above it should be rare.

### 4. Positive control (re-run by me, h2, 07:10 ET, diag/verify_a5/SMOKE_A5_CONTROL.json, CONTROL_RC=0)

| target | want | builder | verifier |
|---|---|---|---|
| V1_FLAT_A demo-pass tasks | 22 | 22 | 22 |
| V1_FLAT_A finish=length share | 0.7750 | 0.7750 | 0.7750 |
| STOCK round_1 demo-pass tasks | 165 | 165 | 165 |
| STOCK round_1 accept() helpers | 0 | 0 | 0 |

ALL_OK=1. Side numbers:
- My run agrees with the stored exec rows 400/400 and 1600/1600. The builder's run had 398 and 1598. This confirms that the builder's 2 flips were sandbox timing at the limit, not a code difference.
- STOCK r1: 439 demo-passing programs, 3 with a reachable helper (0.0068), 407 deduped solutions. This equals the stored round_state n_solutions of 407.
- V1_FLAT_A: pass@2 = 22.

### 5. Server and job

- vLLM command line, smoke_a5.sbatch:49-51 against serve_and_step.sh:74-76: identical. The flags are --served-model-name ratchet, --host 127.0.0.1, a free port, --max-model-len 20480, --enable-prefix-caching, --enable-prompt-tokens-details, --max-num-seqs 256, --gpu-memory-utilization 0.90 and --seed 0. The model path, env_vllm.sh and venv python are the same.
- Other parts that match serve_and_step.sh:
  - the 180 x 5 s readiness loop with VLLM_DIED / VLLM_NOT_UP exits (sbatch:60-66)
  - stop_vllm: SIGINT to the process group, then SIGKILL after 30 s, on trap EXIT (sbatch:53-58)
  - the TEST_ENV_REFUSED loop (sbatch:15-17). env_vllm.sh sets no RATCHET_* variable, so running the loop before sourcing is equivalent.
  - the sandbox self-test with exit 4 (sbatch:41-44)
- Resources: -p h100-debug, --gres=gpu:h100:1, -t 01:00:00, 24 CPUs, 180G. These equal ratchet_step.sbatch except that the partition is h100-debug only. The partition's MaxTime is 01:00:00.
- Stops:
  - The deadline is RATCHET_JOB_START_TS + 3,120 s (stop issuing) and + 3,300 s (abandon), from config.STOP_ISSUE_S and HARD_STOP_S (smoke_a5.py:396-397). It is enforced inside llm.VLLMClient.run (llm.py:304-344).
  - No new variant starts after the stop (smoke_a5.py:444-446).
  - Expected load: about 3 x 200 samples at about 3.6k tokens, which is far inside the stop.
- Failure reporting:
  - A server that never comes up exits with rc 2 and VLLM_NOT_UP or VLLM_DIED in diag/smoke_a5/<job>.out.
  - A variant cut by time prints SAMPLE_INCOMPLETE and DEADLINE, and its `samples` field is below 200 in SMOKE_A5.json.
  - A skipped variant is absent from `variants`.
  - The rows for each finished variant are written before the next one starts.
  - SMOKE_RC is echoed and is the job exit code.
- Collisions (squeue, 07:12 ET):
  - The fourth_law lane currently has fl_nb2smoke RUNNING on **h100-debug** (20 min limit, g37), as well as fl_b16 and fl_wide on h100-interactive. The brief assumed fl_* are only on h100-interactive.
  - h100-debug QoS allows 1 running job per user, so the smoke will PEND until fl_nb2smoke ends. It cannot preempt or disturb it. Once running, it holds the user's only h100-debug slot for up to 1 h.
  - The job name maxRATCH_smokeA5 matters only to chain.sh's "a maxRATCH job is already pending" skip (chain.sh:33-34). No ratchet chain is active (no maxRATCH job in the queue), and nothing in the code dir cancels by name.

### 6. Other findings (none blocks GO)

a. **H definition.** Record in the amendment, before the smoke is read, that H = demo-passing programs with at least one PREREG-4-valid top-level helper reachable from transform, divided by demo-passing programs with a top-level def transform (the code's definition, item 2). The bare text could be read more loosely, and the gap matters only near 0.20.

b. **Provenance.** SMOKE_A5.json records code_sha b636ce5 from the CODE_SHA file, but smoke_a5.py and smoke_a5.sbatch are not in that commit. The lead should cite the two sha256 values above next to SMOKE_A5.json, or commit both files before v3. The script does not record its own hash.

c. **Partial variants.** A variant with `samples` != 200 is not a measurement for part C. Treat it as missing rather than reading A/H/D from it. This should not happen at the expected load.

d. **Single point of failure.** render_server() catches only HTTP status errors (smoke_a5.py:219-227). A socket error on /tokenize would kill the job before sampling. That is loud, not silent: SMOKE_RC != 0 and no SMOKE_A5.json. It costs one slot, so it is not a reason to rebuild.

e. **For v3, not the smoke.** If P2 is chosen, INSTRUCTION_TAILS / with_notes (config.py:211-214) must get a P2 entry, so that a library or exemplar note goes in at a registered place. In P2 the sentence is appended after V1's tail sentence, so the V1 tail is no longer the last thing the model reads. The 'P2' instruction also needs a registered sha in INSTRUCTIONS / INSTRUCTION_SHAS.

f. **The draft's open item stays open for part D only.** The EXEMPLAR "n = 0" in v2 is not reproduced (pool_R.json n 217). The builder notes that exemplar.load_pool would refuse that file (no sha256 or scaler key, arms.py:1003). It does not affect the smoke.

## Lead checks on the job log (after it runs, before reading part C)

1. `RENDER_TAIL P1` and `P2` end `<think>\n\n</think>\n\n```python` (or with the newline). `PREFILL_EFFECTIVE` is '```python' or '```python\n'. If the render shows a fresh assistant header after the prefill, or a thinking block that is not empty, P1 and P2 are not the registered variants and must not be scored.
2. `P0_PROMPT_TOKENS_EQUAL_V1_FLAT_A 50 of 50`.
3. `LEVER NOTHINK first_response_has_think=0`.
4. `samples` = 200 for every variant, and SMOKE_RC=0.
5. GEN_TOKENS per_sample_sum is close to usage_completion for each variant. A large gap would mean the prefill was echoed or dropped.
