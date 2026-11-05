# SPEC ratchet_v1 (silicyte-0119): build spec for PREREG.md

Status: build spec, written 2026-11-04 after PREREG commit cc5fb5b and before any code, model call or sealed read.
PREREG.md is binding and is never edited here. Where PREREG is silent, this spec picks one reading and lists it in
section 13 (INTERPRETATIONS) for the lead to accept or amend; builders implement the section 13 reading until an
AMENDMENT says otherwise. All constants live in `ratchet/config.py`; no module inlines a number from this spec.

Tags: MEASURED (read from a file or command on 2026-11-04), ASSUMED (placeholder the pilot replaces), INFERRED (arithmetic
on the two).

---------------------------------------------------------------------------------------------------------------------

## 1. Physics floor (rule 1): what the 12 H100-hours can buy before any code

### 1.1 Measured sizes

| Quantity | Value | Source |
|---|---|---|
| Growth tasks present in the local ARC-AGI-2 training copy | 391 of 400 | MEASURED, `arc-prize-2026/data/ARC-AGI-2/data/training` |
| Grid cells per growth task (all demo pairs plus test pairs, outputs included) | mean 1,066, max 7,200 | MEASURED, digit count over those 391 files |
| Model on disk | 35 GB (`du -sh`) | MEASURED, Quartz |
| Model shape | 40 layers, 10 full-attention (interval 4), 2 KV heads, head_dim 256, 256 experts, 8 active, vocab 248,320 | MEASURED, `config.json` |
| KV bytes per token (full-attention layers only, bf16 KV) | 10 x 2 x 2 x 256 x 2 = 20,480 B (10,240 B at fp8 KV) | INFERRED |
| h100-debug nodes | g37, g38: 96 CPUs, 1,547,800 MB RAM, 4 x H100 each | MEASURED, `sinfo -p h100-debug` |
| H100 HBM bandwidth | 3.35 TB/s if SXM, 2.0 TB/s if PCIe | ASSUMED; the sbatch prints `nvidia-smi --query-gpu=name` in META |

Sealed tasks were not measured (no read of `data/evaluation` content before the seal, even for sizes).

### 1.2 Token shape of one sample (ASSUMED until pilot step 3)

- Task block about 1,100 tokens (cells serialize one digit per token, one newline per row), instructions about 400 tokens:
  P_task = 1,500. Library or exemplar block up to the 6,000 cap. Mean generated tokens g = 1,000 (cap 4,096).
- Logical tokens per sample: STOCK m_S = 1,500 + 6,000 + 1,000 = 8,500; FLAT m_F = 1,500 + 1,000 = 2,500; ratio rho = 3.4.

### 1.3 Samples per full run, in units of 400 x S samples (one sample per task per sample-slot)

- Growth: STOCK R, STATIC R-1, ONE-SHOT R, EXEMPLAR R, minus the shared round-1 slots of section 13 I3 = 4R-3.
  SHAM, PLANT, FLAT: 0 growth units.
- Sealed, per seed: 7 library arms + FLAT base = 8; FLAT extra = T_STOCK / m_F = (R+1) x rho. Three seeds: 24 + 3(R+1)rho.
- Perturbed copy (STOCK and FLAT, three seeds): 6 + 3(R+1)rho. Knockout: 2 modes x 3 seeds x |W| / 400 (under 1 unit).
- Total units U(R) = 4R - 3 + 30 + 6(R+1)rho.
- Review correction 2026-11-04 (pilot.py uses this): STOCK round 1 has an empty context, so T_STOCK / m_F = 1 + R x rho,
  not (R+1) x rho; knockout adds 2 x 3 x |W| / 400 units with |W| ASSUMED 40 (config KO_W_ASSUMED) until measured; and
  sandbox execution seconds (measured per executed sample in the pilot jobs) are added to the job time, since execution
  runs inside the same GPU jobs. U(R) = 4R - 3 + 30 + 6(1 + R rho) + 0.6; at R = 4, rho = 3.4: 131.2 units.

### 1.4 Required mean decode rate to fit 12 H100-hours (43,200 s) at g = 1,000 (INFERRED)

| S \ R | 4 (U = 145.0) | 6 (U = 193.8) | 8 (U = 242.6) |
|---|---|---|---|
| 4 | 232,000 samples, 5,370 tok/s | 310,080, 7,178 tok/s | 388,160, 8,985 tok/s |
| 8 | 464,000, 10,741 tok/s | 620,160, 14,356 tok/s | 776,320, 17,970 tok/s |
| 16 | 928,000, 21,481 tok/s | 1,240,320, 28,711 tok/s | 1,552,640, 35,941 tok/s |

### 1.5 Decode ceiling on one H100 (INFERRED)

At batch 256 every expert is touched each step, so a step reads all 35 GB of weights plus each sequence's KV:
256 x 9,000 tokens x 20,480 B = 47 GB. 82 GB per step at 3.35 TB/s = 24.5 ms, so the bandwidth ceiling is about
10,400 generated tok/s (about 6,200 on PCIe). vLLM usually reaches 30 to 60% of such a ceiling. Each 1 h job also loses
vLLM startup (load 35 GB plus graph capture, ASSUMED 5 min) and the 5 min graceful-stop margin, so about 50 of 60 min
decode.

### 1.6 What the floor says (the gap is where the bugs are)

1. Only S = 4, R = 4 is plausibly feasible, and only near the ceiling. The pilot rule (PREREG 7.3) has no registered outcome
   if no (S, R) fits; the pilot code stops with `PILOT_NO_FEASIBLE_SR` and the lead amends.
2. The FLAT-TTC token match is 70% of all samples at S = 4, R = 4 (6 x 5 x 3.4 = 102 of 145 units), because STOCK's logged
   total counts the 6,000 library prompt tokens on every sample (PREREG 4 says "growth + library prompt tokens + sealed").
   Sealed scoring (all arms, 3 seeds, perturbed copy) is 132 of 145 units; growth is 13.
3. CPU: about 4.35 programs runs per sample (demos plus tests, ASSUMED ARC-AGI-1 mean) gives 1,009,200 executions at
   S = 4, R = 4. A job gets 24 of 96 CPUs. At 0.05 s mean that is 2,103 s of 24-core wall; each 1% of runs that hit the 2 s
   timeout adds 841 s. Hence: stop a program's demos at the first failure, run tests only after all demos pass, and
   execute each canonical program once per task (cache by `code_sha`).
4. KV pool: about 34 GB free after weights gives about 1.66 M tokens at bf16 KV. Prefix caching of the library block
   (placed first in every prompt) is what lets 256 sequences fit; the pilot must log the prefix-cache hit rate.
   `max_model_len` = 20,480 (worst task 7,200 cells + about 300 newline tokens + 6,000 + 500 + 4,096 = 18,096).
5. Gated DeltaNet layers (30 of 40) hold a per-sequence state that is not in the 20,480 B/token figure; read its size from
   the vLLM startup log in the pilot.

---------------------------------------------------------------------------------------------------------------------

## 2. PREREG section to module map

| PREREG section | Implemented by | Builder |
|---|---|---|
| 1 Question (arms, equal tokens) | `ratchet/arms.py`, `ratchet/budget.py`, `ratchet/verdict.py` | D, E |
| 2 Data, id-list hashes | `ratchet/arc_io.py` (`verify_id_list`) | A |
| 2 Seal, key dir, guard, once-per-library read | `score_sealed.py` (`seal`, `score`), `ratchet/guard.py` | E |
| 2 Secondary ARC-AGI-2 read | `score_sealed.py --condition arcagi2`, `arms.sample_sealed(..., split='arcagi2_sealed')` | E, D |
| 3 Model, sampling params, vLLM | `ratchet/llm.py`, `slurm/serve_and_step.sh` | B, D |
| 3 Token and execution logging | `ratchet/ledger.py`, `exec.jsonl` rows from `ratchet/sandbox.py` | B, A |
| 3 Sandbox (2 s per demo, no network, temp dir only) | `ratchet/sandbox.py`, `ratchet/sandbox_child.py` | A |
| 4 STOCK acceptance rule | `ratchet/helpers.py` (`accept`, `mdl_gain`), `ratchet/library.py` | C |
| 4 STATIC, ONE-SHOT, EXEMPLAR, SHAM, PLANT drivers | `ratchet/arms.py`, `ratchet/rounds.py` | D |
| 4 EXEMPLAR neighbours | `ratchet/exemplar.py` | C |
| 4 SHAM library | `ratchet/sham.py` | C |
| 4 PLANT tranches | `ratchet/plant.py` | C |
| 4 FLAT-TTC token match | `ratchet/budget.py` | D |
| 4 Library context cap 6,000 and ranking | `ratchet/prompt.py` (`library_block`), ranking from `library.rank` | B, C |
| 4 Sealed tasks never contribute helpers | `arms.finalize_round` refuses non-growth samples; test `test_no_sealed_helpers` | D |
| 5 pass@2 selection, test outputs never used | `ratchet/select.py` (no parameter can carry a test output) | A |
| 5 Demo-pass and test-correct reported separately | `ratchet/report.py` (growth: from public growth outputs; sealed: from `score_sealed.py`) | E |
| 6 Solved rule 2 of 3 seeds | `score_sealed.py` (`solved_sets`) | E |
| 6.1 Exact one-sided McNemar | `ratchet/stats.py` | E |
| 6.2 Reuse gate | `ratchet/gates.py` (`reuse_gate`) | E |
| 6.3 Knockout | `ratchet/knockout.py` (libraries), `arms.sample_sealed` (sampling), `score_sealed.py --condition knockout` | E, D |
| 6.4 Contamination gate | `ratchet/perturb.py` (transform), `gates.contamination_gate` | A, E |
| 6 VOID (PLANT-DRIP vs PLANT-L1) | `ratchet/verdict.py` | E |
| 7 Pilot (smoke, PLANT check, throughput, d, S/R choice, power) | `ratchet/pilot.py` (rules), `arms.run_pilot_round` (sampling) | E, D |
| 8 Prediction | `ratchet/verdict.py` (reports STOCK minus STATIC against both bands) | E |
| 9 Kill, VOID retire after two attempts | `ratchet/verdict.py` (reads `runs/ATTEMPTS.json`) | E |
| 10 Rerun artifacts (libraries, ledger, score_sealed, seed) | `ratchet/freeze.py`, `ratchet/library.py` (`save`), `ratchet/ledger.py` | D, C, B |

---------------------------------------------------------------------------------------------------------------------

## 3. Module layout

```
ratchet/                         repo root (github braxtonmensah/ratchet)
  PREREG.md                      binding, never edited by builders
  SPEC.md                        this file
  README.md
  score_sealed.py                E  the only code that opens key/; subcommands seal, score
  splits/                        committed id lists (sha256 in PREREG 2)
  ratchet/
    __init__.py                  E  installs guard audit hook on import (first line of every process)
    config.py                    D  all constants and paths (each builder adds its own constants here)
    types.py                     A  Grid, Pair, Task, Candidate, Submission, ExecResult, Helper, Library dataclasses
    guard.py                     E  protected roots, audit hook, data-read allowlist
    arc_io.py                    A  the single data loader
    sandbox.py                   A  parent side: process pool, timeouts, caching by code_sha
    sandbox_child.py             A  child side: audit hook, rlimits, exec of library + program
    select.py                    A  pass@2
    perturb.py                   A  colour permutation + geometry
    tok.py                       B  tokenizer wrapper (tokenizers.Tokenizer from the model dir) and StubTokenizer
    llm.py                       B  vLLM OpenAI-compatible client, concurrency, deadline, StubLLM
    ledger.py                    B  token ledger rows, totals
    prompt.py                    B  system text, task block, library block, exemplar block, 6,000 cap
    extract.py                   C  code extraction from responses
    helpers.py                   C  AST helper extraction, canonicalization, acceptance, MDL
    library.py                   C  Library merge, rank, save/load (JSON + .py), sha
    sham.py                      C  SHAM builder
    exemplar.py                  C  demo features, scaler, k = 3 neighbours
    plant.py                     C  arc-dsl parsing, solver call counts, tranches
    rounds.py                    D  round state machine, idempotent work units, atomic writes
    arms.py                      D  arm registry and drivers
    budget.py                    D  FLAT-TTC token match
    freeze.py                    D  FREEZE.json and SUBMIT_FREEZE.json
    cli.py                       D  `python -m ratchet <cmd>`
    stats.py                     E  exact McNemar, Clopper-Pearson, power Monte Carlo
    gates.py                     E  reuse, knockout, contamination gates (on score outputs only)
    knockout.py                  E  knockout library construction
    pilot.py                     E  pilot rules and S/R choice
    report.py                    E  per-arm per-round demo-pass and test-correct tables, byte/token/second map
    verdict.py                   E  RESULT.md writer
  slurm/
    ratchet_step.sbatch          D  h100-debug job, name maxRATCH_<phase>
    serve_and_step.sh            D  start vLLM, wait ready, run `python -u -m ratchet step`, graceful stop
    chain.sh                     D  submit the next job when work remains
  tests/                         unittest only (no pytest dependency); every builder owns its files
```

Runtime dependencies: stdlib, numpy, `tokenizers` (both in the vLLM venv; tests check and fall back to StubTokenizer).
HTTP uses stdlib `http.client` in a thread pool (no new dependency). Driver processes run in the vLLM venv
(python 3.13); CPU tests run on the login node with `/N/scratch/bsmensah/sas/venv/bin/python` or `module load python/3.13.5`.

---------------------------------------------------------------------------------------------------------------------

## 4. Data formats

### 4.1 Task JSON on disk

- `data/growth/<id>.json`: the original ARC-AGI-1 file, unchanged bytes: `{"train": [{"input": G, "output": G}, ...],
  "test": [{"input": G, "output": G}, ...]}`. G is a list of rows, each a list of ints 0..9, 1..30 rows and columns.
- `data/sealed/<id>.json`: `{"train": [...], "test": [{"input": G}, ...]}`; no `output` key in any test item.
- `data/sealed_perturbed/<id>.json`: same shape as sealed, perturbation applied to every train grid and test input.
- `data/arcagi2_sealed/<id>.json`: same shape, ARC-AGI-2 public evaluation inputs.
- `key/arcagi1/<id>.json`: `{"id": str, "test_outputs": [G, ...], "src_sha256": hex of the original file}`; mode 000.
- `key/arcagi2/<id>.json`: same.
- In memory (`types.Task`): `Task(id: str, split: str, train: tuple[Pair, ...], test_inputs: tuple[Grid, ...],
  test_outputs: tuple[Grid, ...] | None, src_sha256: str)`. `Grid = tuple[tuple[int, ...], ...]`. `test_outputs` is
  not None only for split `growth` and `pilot`.

### 4.2 Program contract (what the model is asked to write)

`def transform(grid):` receives a list of lists of int (fresh copy per call) and returns a rectangular sequence of sequences
of ints 0..9, at most 30 x 30. Output is normalized to `Grid`; anything else is an error `BAD_OUTPUT`. Library helpers are
already defined in the namespace (the prompt says so). Allowed imports: `math, itertools, collections, functools, copy,
typing, numpy` (config `SANDBOX_IMPORT_ALLOW`).

### 4.3 Library JSON (`L_<r>.json`) and Python (`L_<r>.py`)

```json
{
  "schema": "ratchet.library.v1",
  "arm": "STOCK", "round": 3, "parent_sha": "<sha of L_2 or null>",
  "created_et": "2026-11-05 10:12 ET", "tokenizer_sha": "<sha256 of tokenizer.json>",
  "cap_tokens": 6000, "in_context_tokens": 5873, "n_helpers": 41, "n_in_context": 33,
  "helpers": [
    {
      "name": "flood_region",
      "hash": "<sha256 of canonical source>",
      "source": "def flood_region(grid, r, c):\n    ...",
      "canonical": "def h(a0, a1, a2):\n    ...",
      "token_len": 87,
      "deps": ["neighbors4"],
      "first_round": 2,
      "accepted_by": "two_tasks | mdl | both | plant | sham",
      "calling_tasks": ["007bbfb7", "0d3d703e"],
      "n_calling_tasks": 2,
      "n_solutions": 5,
      "mdl_gain": 348,
      "rank": 7,
      "in_context": true,
      "verified": true,
      "provenance": {"sample_ids": ["STOCK|growth|r2|007bbfb7|s1"], "source_task": "007bbfb7"}
    }
  ],
  "sha256": "<sha256 of the canonical JSON of every field above except sha256>"
}
```

`L_<r>.py` is the rendered module of the in-context helpers in rank order (deps first). Its sha256 is in FREEZE.json too.
`calling_tasks` counts growth tasks only. For PLANT, `calling_tasks` are Hodel solver task ids; for SHAM, the source task
of the failed program, `verified` false.

### 4.4 Token ledger row (`runs/<run>/ledger/ledger_<jobid>.jsonl`, one row per vLLM request)

```json
{
  "ts_et": "2026-11-05 10:12:31", "run": "v1", "job_id": "12345678",
  "arm": "STOCK", "phase": "growth | sealed | perturbed | knockout_delete | knockout_inline | pilot | arcagi2",
  "round": 2, "sealed_seed": null, "task": "007bbfb7", "request_id": "STOCK|growth|r2|007bbfb7|b0",
  "n": 4, "seed": 2913307114,
  "prompt_tokens": 7412, "prompt_tokens_logical": 29648, "cached_prompt_tokens": 6011,
  "library_tokens": 5873, "exemplar_tokens": 0, "task_tokens": 1139, "instruction_tokens": 400,
  "gen_tokens": 3920, "gen_tokens_per_sample": [811, 1203, 1088, 818], "finish_reasons": ["stop", "stop", "stop", "stop"],
  "latency_s": 41.7, "lib_sha": "<sha>", "model_sha": "<sha256 of config.json + model index>",
  "sampling": {"temperature": 0.8, "top_p": 0.95, "max_tokens": 4096, "enable_thinking": false}
}
```

`prompt_tokens` and `gen_tokens` come from vLLM `usage` (exact). `prompt_tokens_logical` = `prompt_tokens` x n; every
token-matching total uses logical prompt tokens plus `gen_tokens` (section 13 I2). `gen_tokens_per_sample` comes from the
local tokenizer; the ledger writer asserts its sum is within n of `gen_tokens` and logs `LEDGER_TOKDIFF` otherwise.

### 4.5 Sample and execution rows

`samples.jsonl` (one row per sample): `{"sample_id", "request_id", "arm", "phase", "round", "sealed_seed", "task",
"seed_idx", "text", "code", "code_sha", "finish_reason", "gen_tokens", "lib_sha", "exemplar_ids", "job_id"}`.
`sample_id` = `ARM|phase|r<round>|<task>|s<seed_idx>` (sealed: `ARM|sealed|k<seed>|<task>|s<i>`).

`exec.jsonl` (one row per sample): `{"sample_id", "code_sha", "status": "OK | NO_CODE | SYNTAX | DEMO_FAIL | TIMEOUT |
ERROR | BAD_OUTPUT", "demo_pass": bool, "n_demo_pass", "n_demos", "first_fail_demo", "test_outputs": [G] | null,
"helper_calls": {"name": count}, "static_refs": ["name"], "wall_s": [float], "timeouts": int, "exec_mode":
"callable | deleted | inline", "cache_hit": bool}`. Growth rows also carry `test_correct` (public growth outputs); sealed
rows never do.

### 4.6 Round state (`arms/<ARM>/round_<r>/round_state.json`, atomic write: temp file + `os.replace`)

```json
{"schema": "ratchet.round.v1", "arm": "STOCK", "round": 2,
 "state": "PENDING | SAMPLING | EXECUTING | EXTRACTING | FROZEN",
 "library_in": "<sha L_1>", "library_out": null,
 "requests_total": 400, "requests_done": 233, "samples_done": 932, "exec_done": 901,
 "demo_pass_tasks": 61, "test_correct_tasks": 44,
 "shared_from": null, "started_et": "...", "updated_et": "...", "jobs": ["12345678"]}
```

Work is keyed by `request_id`; a restart reads `samples.jsonl` and `exec.jsonl`, drops a trailing line that fails to parse,
and skips every done id. `EXTRACTING` to `FROZEN` is a pure function of the round's rows, so it is re-run from scratch if
interrupted. `shared_from` names the round whose rows this round reuses (section 13 I3).

### 4.7 STATUS.json (per job: `runs/<run>/jobs/<jobid>/STATUS.json`; top level: `runs/<run>/STATUS.json`)

```json
{"job_id": "12345678", "job_name": "maxRATCH_grow", "node": "g37", "gpu": "NVIDIA H100 80GB HBM3",
 "state": "STARTING | SERVING | RUNNING | DRAINING | STOPPED_GRACEFUL | DONE | FAILED",
 "meta": "META arm=STOCK phase=growth round=2 model=/N/scratch/.../qwen36_35b_a3b_fp8 temperature=0.8 top_p=0.95 max_tokens=4096 enable_thinking=0 seed_base=1000 S=4 R=4 code_sha=<git sha> job=12345678",
 "started_et": "...", "updated_et": "...", "deadline_et": "...",
 "seconds": {"vllm_startup": 0, "sampling": 0, "exec_only": 0, "drain": 0, "idle": 0},
 "units": {"arm": "STOCK", "round": 2, "requests_done": 0, "requests_total": 400},
 "tokens": {"prompt": 0, "prompt_logical": 0, "cached": 0, "gen": 0},
 "gen_tok_per_s": 0.0, "prefix_cache_hit_rate": 0.0, "exec": {"runs": 0, "timeouts": 0, "cpu_s": 0.0},
 "exit_reason": null, "last_error": null}
```

The top-level STATUS.json holds the PLAN pointer (`next_unit`), per-arm progress and the cumulative ledger totals.

### 4.8 Freeze files (`runs/<run>/freeze/`)

- `FREEZE.json`: `{"schema", "run", "created_et", "code_git_sha", "S", "R", "sealed_seeds": [1, 2, 3], "perturb_seed",
  "libraries": {"STOCK": {"json": path, "py": path, "sha256_json", "sha256_py"}, "STATIC", "ONESHOT", "EXEMPLAR"
  (exemplar pool file), "SHAM", "PLANTDRIP", "PLANTL1", "FLATTTC": null}, "flat_budget": null}` and `FREEZE.sha256`.
- `SUBMIT_FREEZE.json`: sha256 of every `submissions.json` for every arm, condition and seed, written after sealed sampling
  and before any key read, plus `FLAT_BUDGET` (target tokens, m_F, extra samples per seed).
- `KO_FREEZE.json`: sha256 of every knockout library (written before the knockout key read).

---------------------------------------------------------------------------------------------------------------------

## 5. Function signatures by builder

Signatures are contracts; bodies are the builder's. Types come from `ratchet/types.py`.

### Builder A: arc_io, sandbox, pass@2, perturbation

```python
# ratchet/types.py
Grid = tuple[tuple[int, ...], ...]
@dataclass(frozen=True) class Pair: input: Grid; output: Grid
@dataclass(frozen=True) class Task: id: str; split: str; train: tuple[Pair, ...]; test_inputs: tuple[Grid, ...]; test_outputs: tuple[Grid, ...] | None; src_sha256: str
@dataclass(frozen=True) class Candidate: sample_id: str; code_len: int; demo_pass: bool; test_outputs: tuple[Grid, ...] | None
@dataclass(frozen=True) class Attempt: outputs: tuple[Grid, ...]; votes: int; min_len: int; sample_ids: tuple[str, ...]
@dataclass(frozen=True) class Submission: task: str; attempts: tuple[Attempt, ...]; n_candidates: int; n_demo_pass: int
@dataclass class ExecResult: ...   # fields of exec.jsonl (4.5)

# ratchet/arc_io.py  (the single data loader; every data read goes through _read_json)
SPLITS = ('growth', 'pilot', 'sealed', 'sealed_perturbed', 'arcagi2_sealed')
def verify_id_list(path: Path, expected_sha256: str) -> list[str]          # raises IdListMismatch
def task_ids(split: str) -> list[str]
def load_task(task_id: str, split: str) -> Task                           # sealed splits: raises SealedLeak if any test item has 'output'
def load_split(split: str) -> list[Task]
def pilot_ids(n: int = 50) -> list[str]                                    # 50 growth ids with smallest sha256('ratchet-pilot|' + id)
def validate_grid(obj) -> Grid                                             # 1..30 x 1..30, ints 0..9, rectangular
def grid_to_json(g: Grid) -> list[list[int]]
def render_grid(g: Grid) -> str                                            # rows of digits, no spaces, '\n' between rows
def _read_json(path: Path) -> dict                                         # guard.check_data_read(path) first, then open

# ratchet/sandbox.py
@dataclass class ExecJob: sample_id: str; task: Task; code: str; library_src: str; mode: str  # 'callable' | 'deleted' | 'inline'
def probe_isolation() -> str                                                # 'unshare' if `unshare -rn true` works, else 'audit'; prints LEVER SANDBOX line
def run_program(code: str, library_src: str, demo_inputs: list[Grid], demo_outputs: list[Grid], test_inputs: list[Grid],
                *, timeout_s: float = 2.0, trace: list[str] = (), mem_mb: int = 2048, mode: str = 'callable') -> ExecResult
def run_batch(jobs: Iterable[ExecJob], workers: int) -> Iterator[ExecResult]   # cache by (task.id, code_sha, lib_sha, mode)
# Child: one subprocess per program, `python -I sandbox_child.py`, JSON on stdin/stdout, cwd = fresh tempfile.mkdtemp().
# Per input: signal.setitimer(ITIMER_REAL, 2.0). Parent hard-kills at 2.0 x (n_inputs + 2) + 2 s (one window each for
# library exec and program top-level exec; review fix 2026-11-04), recorded as TIMEOUT with error AGG_KILL:*; a library
# exec over 2 s is TIMEOUT with error LIB_TIMEOUT. RLIMIT_CPU = 2.0 x (n_inputs + 2) + 1 + 2 s import pad. Demos stop at the first failure;
# test inputs run only if every demo passed. rlimits: RLIMIT_AS mem_mb, RLIMIT_CPU 2 x n_inputs + 1, RLIMIT_FSIZE 16 MB.
# Child audit hook refuses: socket.*, subprocess.Popen, os.system, os.exec*, os.posix_spawn, os.fork, ctypes import,
# open for write outside the temp dir, open for read outside the temp dir, sys.prefix, sys.base_prefix and site-packages.
# Library helpers named in `trace` are wrapped with a call counter; counts go to helper_calls (test inputs only).
# mode 'deleted': library_src minus the knocked-out helpers; mode 'inline': library_src is not executed at all.
# Isolation (review fix 2026-11-04): production runs every child inside bubblewrap (new user, net, ipc, uts namespaces;
# / read-only; tmpfs over /N/scratch, /N/slate, /N/project, geode3 home/projects/logs, /tmp, /var/tmp, /dev/shm, /run,
# /proc; only the Python install, sandbox_child.py and the temp dir bound back) and refuses to run programs otherwise.

# ratchet/select.py  (no argument can carry a test output: Candidate holds only sampled outputs)
def pass2(task_id: str, candidates: Sequence[Candidate], k: int = 2) -> Submission
# Only demo_pass candidates vote. Vote key = the joint tuple of test outputs. Order: votes desc, then shortest code_len among
# programs giving that tuple, then lexicographic repr (deterministic). Up to 2 distinct tuples.

# ratchet/perturb.py
@dataclass(frozen=True) class Perturbation: perm: tuple[int, ...]; geom: str   # perm[0] == 0; geom in rot90, rot180, rot270, transpose
def draw(task_id: str, seed: int) -> Perturbation                           # random.Random(f'{seed}|{task_id}')
def apply_grid(g: Grid, p: Perturbation) -> Grid
def apply_task(t: Task, p: Perturbation) -> Task                            # train inputs and outputs, test inputs (and outputs if present)
def build_perturbed_split(seed: int, src_split: str = 'sealed', out_dir: Path = ...) -> Path   # writes PERTURB.json too
```

### Builder B: vLLM client, token ledger, prompt builder

```python
# ratchet/tok.py
class Tok(Protocol): def count(self, text: str) -> int
def load_tokenizer(model_dir: Path) -> Tok                                  # tokenizers.Tokenizer.from_file(model_dir/'tokenizer.json')
class StubTokenizer: def count(self, text: str) -> int                      # len(re.findall(r'\w+|\S', text)), for tests

# ratchet/llm.py
@dataclass class GenRequest: request_id: str; messages: list[dict]; n: int; seed: int; meta: dict   # meta goes to the ledger
@dataclass class GenResult: request_id: str; texts: list[str]; finish_reasons: list[str]; usage: dict; latency_s: float
class VLLMClient:
    def __init__(self, base_url: str, model: str, ledger: 'Ledger', tok: Tok, max_inflight: int, timeout_s: float = 900)
    def wait_ready(self, timeout_s: float) -> float                          # polls GET /v1/models inside the job; returns seconds
    def generate(self, req: GenRequest) -> GenResult                        # POST /v1/chat/completions, temperature 0.8, top_p 0.95,
                                                                            # max_tokens 4096, n, seed, chat_template_kwargs {'enable_thinking': False}
    def run(self, reqs: Iterable[GenRequest], on_result: Callable[[GenResult], None],
            stop_issue_ts: float, hard_stop_ts: float) -> dict              # thread pool; stops issuing at stop_issue_ts, abandons at hard_stop_ts
    def server_metrics(self) -> dict                                        # GET /metrics: prefix cache hit rate, running, waiting, preemptions
class StubLLM(VLLMClient):                                                  # deterministic: texts from a fixture pool chosen by sha256(prompt|seed|i)
    def __init__(self, fixtures: Path, ledger: 'Ledger', tok: Tok, gen_tokens: int = 50)

# ratchet/ledger.py
class Ledger:
    def __init__(self, path: Path)                                          # one file per job; append + flush + fsync per 32 rows
    def append(self, row: dict) -> None                                     # validates the 4.4 schema
def iter_rows(run_dir: Path) -> Iterator[dict]                              # all ledger_*.jsonl, dedup by request_id (last wins)
def totals(run_dir: Path, arm: str | None = None, phase: str | None = None, sealed_seed: int | None = None) -> dict
# returns {'prompt', 'prompt_logical', 'cached', 'library', 'gen', 'logical_total', 'samples', 'requests', 'truncated'}

# ratchet/prompt.py
SYSTEM: str                                                                 # in config, frozen before the pilot
@dataclass class PromptBuild: messages: list[dict]; library_tokens: int; exemplar_tokens: int; task_tokens: int;
                              instruction_tokens: int; helpers_in_context: tuple[str, ...]; lib_sha: str | None; exemplar_ids: tuple[str, ...]
def task_block(task: Task) -> str                                           # demos as 'Input:\n<grid>\nOutput:\n<grid>', then test inputs
def library_block(lib: 'Library', cap_tokens: int, tok: Tok, inline_noncallable: bool = False,
                  drop: frozenset[str] = frozenset()) -> tuple[str, tuple[str, ...], int]
# Greedy over library.rank(lib): include a helper only with its whole dep closure, skip if it would cross cap_tokens, continue
# to the next (smaller ones may still fit). Callable header: "These functions are already defined; call them directly."
# Inline header: "Reference code. These functions are NOT defined in your environment; copy any code you need."
def exemplar_block(exemplars: Sequence['Exemplar'], cap_tokens: int, tok: Tok) -> tuple[str, tuple[str, ...], int]
def build_messages(task: Task, tok: Tok, *, library: 'Library | None' = None, exemplars: Sequence['Exemplar'] | None = None,
                   inline_noncallable: bool = False, drop: frozenset[str] = frozenset(), cap_tokens: int = 6000) -> PromptBuild
# Message order: system, then user = [library or exemplar block] + task block + instruction. The block comes first so the
# vLLM prefix cache shares it across tasks of a round.
```

### Builder C: extraction, helpers, acceptance, library, SHAM, EXEMPLAR, PLANT

```python
# ratchet/extract.py
def extract_code(text: str) -> str | None   # last ```python fenced block that defines transform; else the whole text if it
                                            # compiles and defines transform; strips any <think>...</think> first
# ratchet/helpers.py
@dataclass class RawHelper: name: str; source: str; canonical: str; hash: str; deps: tuple[str, ...]; free_names: tuple[str, ...];
                            sample_id: str; task: str; genre: tuple
@dataclass class Solution: sample_id: str; task: str; code: str; code_sha: str; helpers: tuple[RawHelper, ...]; lib_calls: frozenset[str]
def parse_program(code: str) -> ast.Module | None
def extract_helpers(code: str, sample_id: str, task: str, library_names: frozenset[str]) -> list[RawHelper]
# top-level FunctionDef other than transform; nested defs stay inside their parent; a helper whose free names are not builtins,
# allowed modules, its own deps or library names is dropped (logged as UNBOUND)
def canonicalize(fn_src: str) -> tuple[str, str]   # strip docstrings and comments, rename function to h, args a0.., locals v0..,
                                                   # callee helper names to their canonical hashes; ast.unparse; returns (canonical, sha256)
def dedup_solutions(sols: Sequence[Solution]) -> list[Solution]   # one per (task, canonical program hash)
def mdl_gain(h: RawHelper, sols: Sequence[Solution], tok: Tok) -> int   # (k - 1) x token_len(canonical), k = deduped solutions defining h
def accept(round_sols: Sequence[Solution], prev: 'Library', tok: Tok) -> list['Helper']
# accept iff n_distinct_tasks(h) >= 2 or mdl_gain(h) >= 20 (config ACCEPT_MIN_TASKS = 2, ACCEPT_MIN_MDL = 20), counted on
# this round's deduped demo-passing growth solutions only; deps of an accepted helper are accepted with it
# ratchet/library.py
@dataclass class Helper: ...    # fields of 4.3 helpers[]
@dataclass class Library: arm: str; round: int; helpers: list[Helper]; parent_sha: str | None; meta: dict
def empty(arm: str) -> Library
def merge(prev: Library, accepted: Sequence[Helper], round: int, sols: Sequence[Solution]) -> Library
# also adds reuse: tasks whose solutions call an existing helper join its calling_tasks
def rank(lib: Library) -> list[Helper]          # n_calling_tasks desc, token_len asc, name asc
def render_py(lib: Library, names: Sequence[str]) -> str
def save(lib: Library, dir: Path, cap_tokens: int, tok: Tok) -> tuple[Path, Path, str]   # sets in_context via prompt.library_block
def load(path: Path) -> Library                 # verifies sha256; raises LibraryHashMismatch
def sha(lib: Library) -> str
# ratchet/sham.py
def genre(h: RawHelper | Helper) -> tuple       # (arity, return kind from AST: grid|list|int|bool|tuple|none, has_loop, uses_numpy, token_len bin of 25)
def build_sham(target: Library, failed_pool: Sequence[RawHelper], shuffled_pool: Sequence[RawHelper] | None,
               tok: Tok, seed: int, cap_tokens: int = 6000) -> Library
# one candidate per target in-context helper: same genre, nearest token_len, canonical hash not in any accepted library,
# compiles; total tokens within 5% of the target's in_context_tokens; same count; verified = false
def failed_pool(run_dir: Path) -> list[RawHelper]   # helpers from STOCK growth programs whose status is DEMO_FAIL (all rounds)
# ratchet/exemplar.py
@dataclass class Exemplar: task: str; sample_id: str; code: str; token_len: int; features: tuple[float, ...]
def demo_features(task: Task) -> np.ndarray      # config EXEMPLAR_FEATURES: mean over demos of in/out h, w, area ratio,
                                                 # same-shape flag, colour histograms in and out (10 + 10), n colours, bg colour one-hot
class Scaler: def fit(tasks: Sequence[Task]) -> 'Scaler'; def transform(x: np.ndarray) -> np.ndarray   # z-score, fit on growth
def pool_from_rounds(run_dir: Path, arm: str, upto_round: int) -> list[Exemplar]   # shortest demo-passing program per task
def neighbours(task: Task, pool: Sequence[Exemplar], scaler: Scaler, k: int = 3, exclude_task: str | None = None) -> list[Exemplar]
# ratchet/plant.py
@dataclass class PlantSource: primitives: dict[str, str]; constants_src: str; types_src: str; deps: dict[str, set[str]]; solver_calls: dict[str, set[str]]
def load_arcdsl(dir: Path) -> PlantSource        # dsl.py, constants.py, arc_types.py, solvers.py (static AST call counts)
def build_tranches(src: PlantSource, R: int, cap_tokens: int, tok: Tok) -> list[Library]   # cumulative L_plant_1..L_plant_R
# rank primitives by distinct solver tasks calling them desc, token_len asc; fit the capped set; tranche of rank i = i mod R;
# L_plant_r = tranches 0..r-1 plus dep closure plus the constants they use
```

### Builder D: arm drivers, rounds, FLAT token match, slurm

```python
# ratchet/rounds.py
@dataclass class WorkUnit: kind: str; arm: str; phase: str; round: int | None; sealed_seed: int | None; condition: str | None
def load_state(dir: Path) -> dict ; def save_state(dir: Path, state: dict) -> None   # atomic
def done_ids(jsonl: Path, key: str) -> set[str]                             # tolerant of a torn last line
def plan(run: 'Run') -> list[WorkUnit]                                      # deterministic order, section 7.3
def next_unit(run: 'Run') -> WorkUnit | None
# ratchet/arms.py
ARMS = ('STOCK', 'STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'FLATTTC', 'PLANTDRIP', 'PLANTL1')
@dataclass class Run: dir: Path; S: int; R: int; seed_base: int; cfg: dict
def seed_for(run: Run, phase: str, round: int | None, task: str, slot: int, sealed_seed: int | None) -> int
# sha256 of the tuple, first 4 bytes; arm is NOT in the key, so arms with identical prompts share draws (common random numbers)
def grow_round(run: Run, arm: str, r: int, client: VLLMClient, deadline: 'Deadline') -> str   # returns round state
def finalize_round(run: Run, arm: str, r: int, tok: Tok) -> str            # extract, accept, merge, save L_r; returns sha
def run_pilot_round(run: Run, which: str, client: VLLMClient, deadline: 'Deadline') -> None   # which in FLAT_A, FLAT_B, PLANT1
def sample_sealed(run: Run, arm: str, sealed_seed: int, condition: str, client: VLLMClient, deadline: 'Deadline',
                  library_override: 'Library | None' = None, task_ids: Sequence[str] | None = None, mode: str = 'callable') -> None
def write_submissions(run: Run, arm: str, sealed_seed: int, condition: str) -> Path      # select.pass2 per task, before any key read
def step(run: Run, client: VLLMClient, deadline: 'Deadline') -> None       # job entry: loop next_unit until deadline or done
# ratchet/budget.py
@dataclass class FlatBudget: sealed_seed: int; target_tokens: int; m_flat: float; n_extra: int; per_task: dict[str, int]
def flat_budget(run: Run, sealed_seed: int, condition: str = 'sealed') -> FlatBudget
# target = logical_total(STOCK growth, all rounds) + logical_total(STOCK sealed, this seed and condition);
# m_flat = logical tokens per sample over FLAT's base sealed pass of this seed; n_extra = round(target / m_flat);
# per_task = n_extra // 400 each, remainder +1 to the first (n_extra mod 400) ids in sorted order
# ratchet/freeze.py
def freeze_libraries(run: Run) -> tuple[Path, str]      # refuses unless every growth arm round is FROZEN; writes FREEZE.json
def freeze_submissions(run: Run) -> tuple[Path, str]    # refuses unless every sealed and perturbed submission exists
# ratchet/cli.py : section 6
class Deadline: def __init__(self, start_ts: float, stop_issue_s: int = 3120, hard_s: int = 3300); def issue_ok(self) -> bool; def hard(self) -> bool
```

Slurm (D): `slurm/ratchet_step.sbatch` with `#SBATCH -p h100-debug --gres=gpu:h100:1 --cpus-per-task=24 --mem=180G
-t 01:00:00 -J maxRATCH_<phase>`. `serve_and_step.sh`: prints META, `nvidia-smi`, sources env_vllm.sh, starts
`python -m vllm.entrypoints.openai.api_server --model <model> --host 127.0.0.1 --port <free> --max-model-len 20480
--enable-prefix-caching --max-num-seqs 256 --gpu-memory-utilization 0.90 --seed 0` into `logs/vllm_<jobid>.log`, waits for
`/v1/models`, then `python -u -m ratchet step --run <dir> 2>&1 | grep --line-buffered -v '^DEBUG' | tee -a
logs/server_<ARM>_<phase>_<jobid>.log`. At 52 min (`stop_issue_s` 3,120) the driver stops issuing; at 55 min (3,300) it
abandons in-flight requests, flushes, writes STATUS `STOPPED_GRACEFUL`, and the script sends SIGINT then SIGKILL after 30 s
to vLLM. `chain.sh` submits the next job only if `next_unit` is not None; D first reads `sacctmgr show qos` for the
h100-debug submit limit: if more than 1 job may be queued, the job self-chains with `--dependency=afterany:$SLURM_JOB_ID`
at start; else a login-node waiter that passes `waiter_shape.py` resubmits. Log file names must contain the arm tag so
`lever_check.py` finds them (it matches `server_*<ARM>*.log`).

### Builder E: score_sealed, guard, stats, gates, knockout, pilot, verdict

```python
# ratchet/guard.py
KEY_ROOT = Path('/N/scratch/bsmensah/silo/ratchet/key')          # hardcoded, resolved with os.path.realpath
DATA_ROOT = Path('/N/scratch/bsmensah/silo/ratchet/data')
class SealedReadRefused(PermissionError)
def protected_roots() -> tuple[Path, ...]                         # KEY_ROOT plus any added; add-only
def add_protected_root(p: Path) -> None                           # tests add a temp fake key; nothing can remove a root
def install_audit_hook() -> None                                  # idempotent; sys.addaudithook (cannot be removed)
def check_data_read(path: Path) -> Path                           # realpath must be under DATA_ROOT/<one of SPLITS> and not under a protected root
def _unlock(proof: object) -> None                                # accepts only the object score_sealed.main creates after its checks
def is_unlocked() -> bool
# score_sealed.py
def main(argv: list[str]) -> int
def cmd_seal(arcagi1_clone: Path, arcagi2_clone: Path | None) -> None
def cmd_score(run_dir: Path, condition: str, freeze_sha: str, submit_sha: str) -> None   # condition: primary | knockout | arcagi2
def solved_sets(run_dir: Path, condition: str, arms: Sequence[str]) -> dict[str, frozenset[str]]   # 2 of 3 seeds
def correct(sub: Submission, outputs: tuple[Grid, ...]) -> bool  # some attempt equals all test outputs
# ratchet/stats.py
def mcnemar_exact_one_sided(b: int, c: int) -> float             # P(X >= b), X ~ Binomial(b + c, 0.5); b = STOCK-only solves
def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]
def power_mc(d: float, n: int = 400, gain: int = 20, alpha: float = 0.05, sims: int = 100_000, seed: int = 0) -> float
# D ~ Bin(n, d); b ~ Bin(D, q), q = min(1, 0.5 + gain / (2 D)); reject if mcnemar_exact_one_sided(b, D - b) < alpha
# ratchet/gates.py
def compare(solved: dict[str, frozenset[str]], a: str, b: str) -> dict          # b, c, p, net
def reuse_gate(W: frozenset[str], winners: dict[str, list[ExecResult]], accepted: frozenset[str]) -> dict   # pass iff fraction >= 0.5
def knockout_gate(W: frozenset[str], solved_delete: frozenset[str], solved_inline: frozenset[str]) -> dict  # each: |W & solved| <= |W| // 2
def contamination_gate(net_primary: int, net_perturbed: int) -> dict             # pass iff net_perturbed >= 0.5 x net_primary
# ratchet/knockout.py
def called_helpers(winners: list[ExecResult]) -> frozenset[str]
def build_knockout_libraries(L_R: Library, W: frozenset[str], winners: dict[str, list[ExecResult]]) -> dict[str, Library]   # per task
# ratchet/pilot.py
def step1_smoke(run_dir: Path) -> dict                            # pass iff kB in CP95(kA, 50) and kA in CP95(kB, 50)
def step2_plant(run_dir: Path) -> dict                            # pass iff demo-pass tasks(PLANT1) - demo-pass tasks(FLAT_A) >= 1
def step3_rates(run_dir: Path) -> dict                            # a, b of gen_rate = a - b x uncached_prefill_rate (30 s intervals),
                                                                 # startup s, g, P_task, d = discordant pass@2 test-correct fraction
def project(rates: dict, S: int, R: int) -> dict                  # samples, tokens, H100-hours per section 1.3 with measured values
def choose_SR(rates: dict) -> dict                                # feasible = hours <= 12; pick max S x R, tie larger S; none -> PILOT_NO_FEASIBLE_SR
def write_pilot_report(run_dir: Path) -> Path                     # PILOT.md incl. projected power and UNDERPOWERED flag
# ratchet/verdict.py
def verdict(run_dir: Path) -> dict                                # label + every gate value, section 13 I13 precedence
def write_result(run_dir: Path, repo_dir: Path) -> Path           # RESULT.md
```

---------------------------------------------------------------------------------------------------------------------

## 6. CLI (`python -m ratchet <cmd>`; `ratchet` below)

| Command | What it does | Opens key/ |
|---|---|---|
| `python score_sealed.py seal --arcagi1 <clone> [--arcagi2 <clone>]` | verifies commit and id-list sha256, writes `data/growth`, inputs-only `data/sealed`, `key/arcagi1/*` (mode 000), moves the clone's `data/evaluation` into `key/raw_arcagi1_eval/` | writes only |
| `ratchet pilot --run <dir> [--step smoke\|plant\|rates\|choose\|all]` | pilot rounds on the 50 pilot ids (growth only) and the S/R rule; writes `PILOT.md` and `RUN.json` S, R | no |
| `ratchet grow --run <dir> --arm <ARM> [--round r] [--finalize]` | runs or resumes growth rounds; `--finalize` extracts and freezes L_r | no |
| `ratchet step --run <dir>` | job entry: works `PLAN` units until the 55 min deadline | no |
| `ratchet perturb --run <dir> --build` | builds `data/sealed_perturbed` with `perturb_seed` from config | no |
| `ratchet freeze --run <dir> [--submissions]` | writes FREEZE.json (or SUBMIT_FREEZE.json) and prints its sha256 for the lead to commit | no |
| `ratchet sample-sealed --run <dir> --arm <ARM> --seed k [--condition sealed\|perturbed\|arcagi2]` | sealed sampling, then submissions | no |
| `ratchet score --run <dir> --condition primary\|knockout\|arcagi2 --freeze-sha <hex> --submit-sha <hex>` | `os.execv` into `score_sealed.py score ...` | yes, once per condition |
| `ratchet knockout --run <dir> [--build\|--sample]` | builds per-task knockout libraries from `scores/W.json` and `scores/winners.json`, writes KO_FREEZE.json, samples both modes | no |
| `ratchet status --run <dir> [--map]` | STATUS and the byte, token and second map (section 10) | no |
| `ratchet verdict --run <dir>` | RESULT.md | no (reads `scores/` only) |

---------------------------------------------------------------------------------------------------------------------

## 7. Run directory on Quartz

```
/N/scratch/bsmensah/silo/ratchet/
  code/                       rsync of the repo; never rsynced while a job runs (check squeue -u bsmensah -n maxRATCH first)
  data/
    MANIFEST.json             ARC-AGI-1 commit 399030444e0ab0cc8b4e199870fb20b863846f34, arc-dsl and ARC-AGI-2 commits, sha256 per file
    raw/ARC-AGI/              clone without data/evaluation (moved into key by seal)
    raw/arc-dsl/              clone, commit pinned at download
    growth/ pilot_ids.txt sealed/ sealed_perturbed/ PERTURB.json arcagi2_sealed/
  key/                        chmod 700; every file chmod 000; written only by `score_sealed.py seal`
    arcagi1/<id>.json arcagi2/<id>.json raw_arcagi1_eval/ raw_arcagi2_eval/ KEY_MANIFEST.json (sha256 only)
  runs/
    ATTEMPTS.json             VOID count per PREREG 9
    <run>/                    e.g. v1
      RUN.json                S, R, seed_base, sealed_seeds, perturb_seed, model path and sha, code git sha
      PLAN.json STATUS.json PILOT.md RESULT.md
      pilot/{FLAT_A,FLAT_B,PLANT1}/{samples,exec}.jsonl
      arms/<ARM>/round_<r>/{round_state.json,samples.jsonl,exec.jsonl,L_<r>.json,L_<r>.py}
      arms/EXEMPLAR/pool_R.json  arms/SHAM/L_sham.json  arms/PLANT*/L_plant_<r>.json
      sealed/<condition>/<ARM>/seed_<k>/{samples.jsonl,exec.jsonl,submissions.json}
      knockout/<delete|inline>/seed_<k>/{libraries/,samples.jsonl,exec.jsonl,submissions.json}
      ledger/ledger_<jobid>.jsonl
      freeze/{FREEZE.json,FREEZE.sha256,SUBMIT_FREEZE.json,KO_FREEZE.json}
      scores/                 written only by score_sealed.py: KEY_READS.jsonl, solved_<condition>.json, W.json (ids only),
                              winners.json (sample ids only), mcnemar.json, gates.json
      logs/{server_<ARM>_<phase>_<jobid>.log, vllm_<jobid>.log}
      jobs/<jobid>/{STATUS.json,sbatch.out}
```

Sandbox temp dirs live in the node's `$TMPDIR`, never in scratch.

### 7.1 Order of work (PLAN)

1. Pilot: FLAT_A, FLAT_B, PLANT1 on 50 pilot ids at S_pilot = 8, then `choose`. Stop if smoke or PLANT fails, or no S/R fits.
2. Growth: STOCK r = 1..R (round 1 shared by STATIC and EXEMPLAR; its first S slots shared by ONE-SHOT), EXEMPLAR r = 2..R,
   ONE-SHOT (remaining (R-1)S slots), SHAM build, PLANT tranches, STATIC r = 2..R last.
3. `freeze` (libraries). Lead commits FREEZE.json.
4. Sealed sampling: for seeds 1..3: 7 library arms, FLAT base, `flat_budget`, FLAT extra; then perturbed STOCK and FLAT.
5. `freeze --submissions`. Lead commits SUBMIT_FREEZE.json. 6. `score --condition primary` (first key read).
7. Knockout build, KO_FREEZE, sampling, `score --condition knockout` (second key read). 8. `verdict`.
9. ARC-AGI-2 secondary read only after RESULT.md is written (section 13 I16).

---------------------------------------------------------------------------------------------------------------------

## 8. Sealed-read guard

Goal: no process other than `score_sealed.py` can read a test output of a sealed task, by accident or by a generated
program, and every read that does happen is logged and happens only after the libraries and submissions are hash-frozen.

Layers:

1. **Content never on the loop's path.** `seal` writes `data/sealed/*.json` without any test `output` and moves the raw
   evaluation files of both clones into `key/`. The loop reads tasks only from `DATA_ROOT`.
2. **Allowlist in the single loader.** `arc_io._read_json` calls `guard.check_data_read(path)`: realpath (symlinks and `..`
   resolved) must lie under `DATA_ROOT/{growth,pilot,sealed,sealed_perturbed,arcagi2_sealed}` and under no protected root.
   `load_task` for a sealed split raises `SealedLeak` if any test item has an `output` key. No other module opens data
   files (static test 8 below).
3. **Audit hook in every loop process.** `import ratchet` runs `guard.install_audit_hook()`. The hook raises
   `SealedReadRefused` on events `open`, `os.listdir`, `os.scandir`, `os.chmod`, `os.rename`, `shutil.copyfile` whose path
   resolves under a protected root, unless `guard.is_unlocked()`. Python offers no API to remove an audit hook.
4. **Unlock only from score_sealed.** `score_sealed.main` unlocks only if all hold: realpath of `__main__.__file__` equals
   realpath of `<code>/score_sealed.py`; `FREEZE.json` and `SUBMIT_FREEZE.json` (and `KO_FREEZE.json` for knockout) exist,
   every listed file's sha256 matches, and `--freeze-sha`/`--submit-sha` equal the files' own sha256; every key file has
   mode 000 at start (else `KEY_EXPOSED`); `KEY_READS.jsonl` has no prior read of this condition with these shas.
   Review fixes 2026-11-04: the lead's ack of every freeze the read relies on (`freeze/<NAME>.ack` = the file's sha256);
   no row for this condition in `<key root>/KEY_READS.jsonl` (written only by score_sealed.py while unlocked, mode 000,
   one row per read from any run) unless `--amendment <id>` names an `AMENDMENT <id>` in PREREG.md not used before;
   runs/ATTEMPTS.json not retired; for primary, SUBMIT_FREEZE lists PERTURB.json, whose seed equals FREEZE perturb_seed
   and whose perm and geometry per task equal perturb.draw; `--test` is required for (and only allowed with) a
   non-default key or data root.
   It then chmods each key file to 400 inside try/finally, reads it, sets it back to 000, and appends one row per read to
   `KEY_READS.jsonl` (`ts_et, condition, freeze_sha, submit_sha, n_files, job or host, argv`).
5. **Generated programs.** The sandbox child installs its own audit hook (reads only from its temp dir and the Python
   install), runs in a fresh temp cwd, and key files are mode 000, so even a raw `os.open` fails. Network is cut by
   `unshare -rn` when available, else by the hook refusing `socket.*`.
   Review fix 2026-11-04 (PEP 578: an audit hook is not a sandbox): in production the child runs in the bubblewrap mount
   view of section 5, where the key, data and runs trees do not exist at all; anything else stops with SANDBOX_NET_FAIL.
   Every job runs `ratchet sandbox-selftest` on its own node before any work and prints the result in META.
6. **What leaves the key.** `score_sealed.py` writes only per-task booleans, W ids and winning sample ids to `scores/`;
   never a grid. The perturbed key outputs are produced inside `score_sealed.py` with `perturb.apply_grid`.

Refusal tests (`tests/test_guard.py`, E; all use a temp fake key added with `add_protected_root`):
1. `arc_io.load_task` on a file under the fake key raises `SealedReadRefused`.
2. `open(<fake key file>)` after `import ratchet` raises; so does `os.listdir(<fake key dir>)`.
3. A symlink inside a temp DATA_ROOT pointing into the fake key is refused (realpath).
4. A `../` path that escapes DATA_ROOT is refused; a path outside DATA_ROOT (for example the ARC-AGI-2 copy on the laptop
   path) is refused.
5. A sealed task file that contains a test `output` raises `SealedLeak`.
6. A script named `score_sealed.py` at another path cannot unlock; `guard._unlock(object())` raises.
7. `score_sealed.py score` refuses: missing FREEZE, sha mismatch, a library file edited after freeze, a key file with mode
   other than 000, a repeated condition.
8. Static: no file under `ratchet/` except `guard.py` and `arc_io.py` contains `open(` on a data path, and no file except
   `guard.py` and `score_sealed.py` contains the string `key/` or `KEY_ROOT`.
9. Sandbox: a program that opens the fake key file, opens a socket, or writes `/tmp/x` outside its temp dir gets
   `status = ERROR` and the demo fails.
10. After a scoring run in the end-to-end stub test, every fake key file is mode 000 again and `KEY_READS.jsonl` has
    exactly one row per condition.

---------------------------------------------------------------------------------------------------------------------

## 9. Lever markers (rule 6) and META

Every job prints one META line first (fields of 4.7 `meta`). Each lever prints a marker into
`logs/server_<ARM>_<phase>_<jobid>.log`, and no effect is read until
`CPU_OK=1 python -I C:/Users/bmens/NQ_local/lane/lever_check.py <run dir> ARM=REGEX ...` prints LEVER_OK for it.

| Arm tag | Marker regex (the line the code prints) |
|---|---|
| STOCK | `LEVER STOCK library r=[2-9]\d* .*updated=1` (the in-context helper set of L_{r-1} differs from L_1's and is non-empty; review fix 2026-11-04: the sha always differed between rounds. At r = 2 it is 0 by construction, since L_{r-1} = L_1; read the r >= 3 growth lines or the sealed line, r = R) |
| STATIC | `LEVER STATIC library r=\d+ sha=<L_1 sha> frozen=1` |
| ONESHOT | `LEVER ONESHOT round=1 slots_per_task=\d+` (equals R x S) |
| EXEMPLAR | `LEVER EXEMPLAR task=\w+ k=[1-3] exemplar_tokens=\d+` |
| SHAM | `LEVER SHAM matched=\d+ of \d+ tokens=\d+ target=\d+ verified=0` |
| FLATTTC | `LEVER FLATTTC seed=\d extra=\d+ target_tokens=\d+ realized_tokens=\d+` |
| PLANTDRIP | `LEVER PLANTDRIP tranche=\d+ of \d+ primitives=\d+` |
| PLANTL1 | `LEVER PLANTL1 tranche=1 primitives=\d+` |
| every arm | `LEVER SANDBOX lib_sha=\w+ helpers_callable=\d+ net=(unshare\|audit)`; `LEVER NOTHINK first_response_has_think=0`; `LEVER PREFIX hit_rate=0\.\d+` (production run: `net=unshare fs=bwrap`; verdict.py refuses a registered label without every marker) |
| knockout | `LEVER KO_DELETE task=\w+ removed=\S+` and `LEVER KO_INLINE task=\w+ callable=0` (sandbox namespace lacks the names) |
| perturbed | `LEVER PERTURB seed=\d+ tasks=400` |

Noise (A/A): pilot FLAT_A vs FLAT_B is the registered A/A; the three sealed seeds of FLAT give a second one, reported in
RESULT.md next to every arm difference.

---------------------------------------------------------------------------------------------------------------------

## 10. Byte, token and second map (rule 7)

`ratchet status --map` (E's `report.py`) prints, per arm and phase: requests, samples, prompt tokens split into
instruction / task / library / exemplar, cached share, generated tokens, truncated share (`finish_reason = length`), samples
with no code, syntax errors, demo-pass, timeouts, execution CPU seconds, and per job: vLLM startup s, sampling s, drain s,
idle s. Rule-3 constraint counters in the same table: accepted helpers never called by any later program, outputs rejected
for leaving the ARC grid domain (colour above 9, side above 30), and the share of samples that only re-emit a library helper.

---------------------------------------------------------------------------------------------------------------------

## 11. Tests (CPU, login node, stub LLM, no GPU)

Run: `cd /N/scratch/bsmensah/silo/ratchet/code && /N/scratch/bsmensah/sas/venv/bin/python -m unittest discover -s tests -v`.

| File | Owner | Checks |
|---|---|---|
| test_arc_io.py | A | id-list sha256 equals PREREG values; grid validation; render_grid round trip; pilot_ids stable |
| test_sandbox.py | A | 2 s timeout fires on `while True: pass` per demo; first-fail stop; no network; no write outside temp; helper call counts; mode deleted and inline; cache hit |
| test_select.py | A | majority, tie by shortest, two distinct attempts, demo-fail candidates ignored, no test-output parameter exists |
| test_perturb.py | A | perm is a bijection with 0 fixed; same transform on demos and tests; seed reproducible; 4 geometries hit |
| test_prompt.py | B | library block under 6,000 with StubTokenizer and real tokenizer if present; rank order; dep closure; inline header |
| test_llm_ledger.py | B | StubLLM determinism; ledger schema; totals; deadline stops issuing |
| test_helpers.py | C | alpha-equivalent helpers share a hash; 2-task rule; MDL 19 rejects and 20 accepts; unbound names dropped; sealed rows refused |
| test_library.py | C | save/load sha; merge reuse counts; rank |
| test_sham_exemplar_plant.py | C | SHAM count and token match within 5%, no accepted hash; self excluded from neighbours; tranches cumulative and capped |
| test_rounds_resume.py | D | kill a stub run mid-round at random points 20 times; final libraries byte-identical to an uninterrupted run |
| test_budget.py | D | n_extra and per-task allocation on a synthetic ledger |
| test_guard.py | E | section 8 refusal tests 1 to 10 |
| test_stats.py | E | McNemar b = 10, c = 2 gives 79/4096 = 0.019287; b = c gives p >= 0.5; CP bounds; power monotone in d |
| test_end_to_end_stub.py | D, E | 6 growth + 6 fake sealed tasks, fake key, R = 2, S = 2, all arms, freeze, score, knockout, verdict |

---------------------------------------------------------------------------------------------------------------------

## 12. Builder assignment and hand-offs

| Builder | Owns | Delivers first (hour 0) | Depends on |
|---|---|---|---|
| A | types.py, arc_io.py, sandbox.py, sandbox_child.py, select.py, perturb.py | types.py | guard.check_data_read (E; stub that only checks DATA_ROOT until E lands) |
| B | tok.py, llm.py, ledger.py, prompt.py | StubLLM, StubTokenizer, ledger schema | types.py; library.rank (C) |
| C | extract.py, helpers.py, library.py, sham.py, exemplar.py, plant.py | Library dataclass and rank | types.py, tok.py |
| D | config.py, rounds.py, arms.py, budget.py, freeze.py, cli.py, slurm/ | config.py skeleton, PLAN order | all of A, B, C interfaces |
| E | guard.py, ratchet/__init__.py, score_sealed.py, stats.py, gates.py, knockout.py, pilot.py, report.py, verdict.py | guard.py | ledger (B), exec rows (A), Library (C), sample_sealed (D) |

D owns the end-to-end stub test and integration. No builder edits PREREG.md. Before the first GPU job, D reads
`chat_template.jinja` in the model dir to confirm `enable_thinking` is honoured (rule 5), and B confirms from vLLM source in
the venv that per-request `seed` with `n > 1` gives reproducible draws.

---------------------------------------------------------------------------------------------------------------------

## 13. INTERPRETATIONS where PREREG is silent (for the lead: accept, or amend in PREREG AMENDMENTS)

- I1 Sealed samples per task per seed for every library arm = S (PREREG fixes S only for growth).
- I2 Token match: logical prompt tokens (prompt x n, library tokens included) plus generated tokens. FLAT gets its base S
  samples per sealed task plus `round(T_STOCK / m_F)` extra per seed, spread evenly; this gives FLAT slightly more than
  STOCK's total (conservative against STOCK). Realized ratio is reported.
- I3 Identical requests are shared: round 1 of STOCK, STATIC and EXEMPLAR (all empty context) is one set of samples; ONE-SHOT
  slots 0..S-1 reuse it. Seeds exclude the arm name (common random numbers).
- I4 STATIC rounds 2..R are run (PREREG says they sample) but cannot change L_1; they are scheduled last in growth.
- I5 SHAM, PLANT and FLAT do no growth sampling. SHAM is drawn from STOCK's demo-failing programs; the shuffled-task pool is
  sampled only if fewer than 95% of target slots match. Review fix 2026-11-04: the fallback pool is the demo-FAILING
  programs of the other growth arms (EXEMPLAR, ONESHOT, STATIC rounds on disk at the SHAM build), never demo-passing code;
  "failed its demos" = demo_pass false whatever the failing status; a slot may drop the token-length bin but never the
  genre, else SHAM_BUILD_FAILED stops the run for the lead.
- I6 PLANT ranks arc-dsl primitives by distinct Hodel solver tasks calling them; tranche = rank mod R; pilot uses R = 4.
  arc-dsl commit is pinned at download (PREREG names no commit).
- I7 Acceptance counts this round's deduped demo-passing growth solutions only; MDL gain = (k - 1) x canonical token length.
  (Call sites exist in both encodings, with the helper defined locally or in the library, so they cancel; k counts
  solutions, same task included, as PREREG says "on the round's solutions".) Demo-passing = demo_pass true whatever the
  status on the growth test input (review fix 2026-11-04; status OK was also required).
- I8 Cap ranking ties by token length ascending, then name.
- I9 A sealed task with several test inputs is correct only if one attempt matches every test output; ties break on the
  shortest program in characters of extracted code.
- I10 "Calls an accepted helper" = invoked at runtime on a test input; winning programs = STOCK demo-passing programs whose
  outputs equal a correct attempt, pooled over the seeds where the task was correct.
- I11 Knockout uses per-task called sets, same S, 3 seeds, 2-of-3 rule; pass iff solves kept in W are at most |W| // 2.
  Review fix 2026-11-04: K = called helpers plus their dependents. Delete = exactly L_R's in-context helpers minus K (no
  refill of the freed tokens). Inline = the same callable set plus K shown as non-callable text (PREREG 6.3b "the
  helpers"); the whole-L_R non-callable reading is gone. Threshold floor(KNOCKOUT_MAX_FRAC x |W|).
- I12 Contamination: perturbation per task from `Random(f'{seed}|{task}')`, `perturb_seed` = 20261104; the FLAT extra count
  of each seed is recomputed from the perturbed STOCK totals.
- I13 Outcome precedence: VOID; else COMPOUNDS; else LIBRARY HELPS, NOT COMPOUNDING (beats FLAT at p < 0.05, not STATIC);
  else CONTEXT EFFECT (condition 1 holds, reuse fails); else RETRIEVAL (1 and 2 hold, contamination fails); else NULL.
  UNDERPOWERED is a tag added to any label.
- I14 Non-thinking mode (`enable_thinking = False`): with thinking on, the 4,096-token cap would truncate most samples
  before any code.
- I15 Pilot: S_pilot = 8; d = fraction of the 50 pilot tasks where FLAT_A and FLAT_B differ on pass@2 test-correct;
  "12 H100-hours" covers every row of section 1.3 (growth, 3 sealed seeds, perturbed, knockout, job startup), not the
  ARC-AGI-2 read; choose max S x R, ties to larger S; no feasible pair stops the run for an amendment.
- I16 ARC-AGI-2 secondary read: commit pinned at download, sampled and scored only after RESULT.md, outside the 12 h.
- I17 EXEMPLAR during growth never shows a task its own programs.
- I18 Determinism smoke uses Clopper-Pearson 95% in both directions.
- I19 Power uses the Monte Carlo of `stats.power_mc`; the all-five-comparators power is reported, not decisive.
