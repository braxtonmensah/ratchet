# BUILD_V2: Ratchet harness v2 (silicyte-0119)

Builder report, 2026-11-04 (ET). Commit `e2a9c2dd4635fe49d09b204dbdf6c57e2ac30d76` in `C:/Users/bmens/NQ_local/ratchet` (local only, not pushed), synced to
`/N/scratch/bsmensah/silo/ratchet/code` with `CODE_SHA` = that sha. No Slurm job submitted, no `ratchet init`, PREREG.md not
edited, runs/v1 not touched (PILOT_STOP.json stays), selfft/ tests_selfft/ testpower/ not touched or committed.

## 1. Numbers (all measured on Quartz CPU, login node h2, through the real sandbox: bwrap, zygote)

| quantity | value |
|---|---|
| INSTRUCTION_V1 sha256 | `cf85bc1b0ccc002e3bc93edd9e8285e41c35b28f022d517f85c011e4c7d22340` |
| INSTRUCTION_F3 sha256 | `3c511b3f1db6cf3a8a1c32d499137dd0210a19bf7026937ea7cb540e7db2191e` |
| ratchet suite (`python -m unittest discover -s tests`) | 338 run: **335 pass, 2 fail, 1 skip** (the 2 failures are the pre-existing timeout test, section 6; v1 was 304 run, 303 pass, 1 skip) |
| selfft torch-free (`SELFFT_TEST_NO_TORCH=1 ... discover -s tests_selfft`) | 8 run, OK (3 pass, 5 skipped), after this change |
| replay of the 41 v1 PLANT1 helper-crash programs through the adapter | **24 of 41 demo-pass** (10 tasks; 12 DEMO_FAIL, 5 BAD_OUTPUT = truncated programs returning None); v1 boundary (adapter off): 41 of 41 ERROR "too many values to unpack" |
| the 4 other v1 helper-referencing programs | unchanged (3 OK, 1 DEMO_FAIL, identical test outputs) |
| LEVER ADAPTER on L_plant_1 (as the pilot builds it, 36 helpers in context, 2,746 tokens with header and legend) | `grid_helpers=13 list_smoke_ok=13`, ok on all 50 pilot first-demo grids; v1 boundary positive control: `grid_helpers=13 list_smoke_ok=4`, refused (mostcolor, objects, width, height, underfill, palette, shape, numcolors raise; tophalf returns a list where the tuple call returns a tuple, so "results differ") |
| LEVER ADAPTER on the 50 PLANT_SOLVE libraries | 50 of 50 ok; grid_helpers 360 in total, list_smoke_ok 358 (2 helpers raise on both list and tuple with the default arguments, which the rule does not refuse) |
| PLANT_SOLVE closure size | max **3,418 tokens** (model tokenizer, rendered callable block incl. header and legend; task 9d9215db, 50 helpers); all 50 under the 6,000 cap |
| PLANT_SOLVE plumbing check: `transform = solve_this(grid)` through the sandbox | **50 of 50 demo-pass and test-correct**; under the v1 boundary 8 of 50 |

The diagnosis's 3,182-token maximum counted the closure without the v2 header sentence and legend; 3,418 is the exact
block the model will see. Amendment 3's `<maxtok>` should read 3,418.

## 2. A second v1 bug found while building (not in the diagnosis): the call counter hid every helper's arity

With the adapter alone, `solve_this` passed only 31 of 50. Cause (code read, then measured): arc-dsl `rbind` and `lbind`
choose the returned lambda's arity from `function.__code__.co_argcount`, and the sandbox's call-counting wrapper was
`def w(*a, **k)` (co_argcount 0), in v1 and in the F1 design as written. Every solver that binds a library function
(`rbind(bordering, grid)`) then raised `TypeError: rbind.<locals>.<lambda>() missing ... arguments`. Fix: both wrappers (the
counter and the adapter) are generated with the wrapped function's exact parameter list (`sandbox_child._clone_signature`),
so `co_argcount`, positional-only, keyword-only and defaults are preserved; counting is unchanged (same increments, same
place). After the fix: 50 of 50. The same bug would have hit any model program that passes a library function to
`rbind`/`lbind`, and PLANT-DRIP's later tranches (which contain rbind, lbind, fork, compose).

## 3. What changed, file by file

- `ratchet/config.py`: `INSTRUCTION_V1` (the v1 text; `INSTRUCTION` stays bound to it, so selfft and every caller that
  passes no instruction get v1 bytes); `INSTRUCTION_F3` = v1 + " " + the F3 sentences; hard-coded sha256 of both, checked at
  import (a drifted text refuses to import); `INSTRUCTION_TAILS` (where notes go); `INSTRUCTION_DEFAULT_RUN = 'F3'`;
  `LIB_HEADER_CALLABLE` gains the grid-contract sentence exactly; `ADAPTER_GRID_TYPES`; `TYPE_LEGEND` (the 16 arc_types
  aliases, model view); pilot v2 names (`PILOT_WHICH` = FLAT_A, FLAT_B, PLANT1, PLANT_SOLVE; `PILOT_SCREEN` = FLAT_S;
  `PILOT_PHYSICAL`; `PILOT_AFTER_SCREEN`); screen and gate constants (`SCREEN_GEN_BUDGET` 1,451,835,
  `SCREEN_MIN_DEMO_TASKS` 23, `SCREEN_MIN_PASS2_TASKS` 22, `PILOT_PLANT_SOLVE_MIN_GAIN` 5, `SCREEN_MAX_N_PER_REQUEST` 16);
  `PLANT_SOLVE_NAME`, `PLANT_SOLVE_DOCSTRING`. MAX_TOKENS 4,096 and VLLM_MAX_MODEL_LEN 20,480 unchanged.
- `ratchet/adapter.py` (new): parent-side static analysis only (never executes library code): the adapter rule's
  signature reading, the type legend, the list of grid-typed helpers, the lever-check program and its decoder.
- `ratchet/sandbox_child.py`: F1. The library executes in its own namespace `lib_g`; counters wrap the functions inside
  `lib_g` (internal calls counted as in v1); every public library name is copied into the program's globals, functions
  through `_adapt` (identity, the same object, unless the helper's own string annotations name Grid, Element or Piece),
  other values as is. Both wrappers keep the wrapped signature (section 2). Request key `adapter` (default true) exists so
  tests can reproduce the v1 boundary.
- `ratchet/sandbox.py`: `run_program(..., adapter=True)` (only tests pass False; `ExecJob`/`run_batch` carry no such field,
  and a test asserts no driver file contains `adapter=False`); `adapter_smoke(library_src, grid)` runs the lever check
  through the real sandbox path (list call and tuple call per grid-first helper, defaults per the diagnosis); refuses on
  list-raises-tuple-does-not, on results that differ, and if the check itself did not run.
- `ratchet/prompt.py`: `build_messages(..., instruction=None)` (default v1 text); `with_notes` puts the library, inline or
  exemplar note immediately before the instruction's tail; the callable block opens its code fence with the legend, and
  the legend is inside the text whose exact token count meets the cap. Inline (non-callable) blocks get no legend.
- `ratchet/library.py`: fallback header text; `is_pilot_only`; `save` refuses a PLANT_SOLVE library outside a `pilot/`
  dir; `merge` refuses a PLANT_SOLVE library or helper.
- `ratchet/plant.py`: `PlantSource.solvers_src`; `solver_source` (rename `solve_<task>` to `solve_this(grid: 'Grid') ->
  'Grid'`, parameter `I` renamed to `grid`, registered docstring); `solver_library` (solver plus primitive and constant
  closure, completeness checked, meta `pilot_only`).
- `ratchet/arms.py`: `init_run` records `instruction` (F3), `instruction_sha`, `instruction_history`, `harness: v2`; a piloted
  run cannot start at V1. `run_instruction` refuses a run that records no instruction (every pre-v2 run, v1 included), an
  unknown name, or a sha that is not the sha of the text the code would send. `sample()` checks it before any model call,
  prints `LEVER INSTRUCTION sha=<sha> name=<name> max_tokens=4096` once per (arm, phase) log per job (the NOTHINK rule, so
  lever_check.py finds it in every arm's log), runs `lever_adapter` (one `LEVER ADAPTER grid_helpers=<n>
  list_smoke_ok=<n> lib=<sha16> task=<id> ok=<0|1>` per distinct library source per job, refusal before any model call),
  refuses a PLANT_SOLVE library outside a pilot-phase prompt on a pilot task, and refuses pilot exemplars; every sample row
  carries `instruction_sha`. `step()` prints the instruction marker at job start (inside the try, so a refusal is recorded
  as FAILED and chain.sh's failed-twice rule stops the chain). Pilot v2: `run_pilot_round` for every physical dir (FLAT_S at
  S_screen in requests of at most 16, seeds `pilot:FLAT_S`; PLANT_SOLVE per-task libraries under
  `pilot/PLANT_SOLVE/libs/`, built once, cap-checked, paired seeds with FLAT_A; V1_* dirs), each round refusing an
  instruction other than its own and refusing resume under a different sha; `pilot_screen` (writes `pilot/SCREEN.json`
  once; on failure sets RUN.json to V1, history appended); `code_git_sha` reads the `CODE_SHA` file before the (stale)
  .git of the Quartz copy.
- `ratchet/rounds.py`: plan = FLAT_A, FLAT_S, pilot_screen, then FLAT_B, PLANT1, PLANT_SOLVE (F3 stands) or V1_FLAT_A,
  V1_FLAT_B, V1_PLANT1, V1_PLANT_SOLVE (fallback), then pilot_choose; an invalid SCREEN.json decision stops the plan.
- `ratchet/pilot.py`: logical-to-physical dir map from SCREEN.json; `step2_plant_solve` (gate, +5) and `step2_plant`
  (L_plant_1, report-only, `gates: False`); `screen_decision` (both thresholds, demo-pass-but-test-wrong share, realized
  screen tokens vs budget); rates read the rate arms (FLAT_A, FLAT_B, PLANT1) under the instruction in force; the decode
  fit is per job (a pilot spanning jobs no longer counts the gap between jobs as idle intervals); PILOT.md adds the screen,
  the PLANT_SOLVE gate with solver reference and call counts, the L_plant_1 report line, a per-dir table (finish=length
  share, median and mean gen tokens, share with `def transform`, demo-pass tasks, demo-pass test-wrong), and the
  library-to-FLAT token price per sample (measured PLANT1/FLAT and at the cap; v1 2.26).
- `ratchet/freeze.py`: `_entry` refuses any pilot or PLANT_SOLVE library (by path and by the JSON's own arm / pilot_only).
- `ratchet/cli.py`: `ratchet pilot --step {rates,screen,choose,all}` follows the v2 plan.
- `score_sealed.py` (coordinator's item): an amendment id authorises a repeated key read only if its own paragraph (from
  `- AMENDMENT <id> (` to the next `- AMENDMENT ` or end of file, whitespace collapsed) contains `grants one key access`;
  otherwise `AMENDMENT_GRANTS_NO_KEY_ACCESS`. The three planned v2 amendments and the registered AMENDMENT 0 grant nothing.
- `slurm/serve_and_step.sh`: `CODE_SHA` file wins over the Quartz copy's stale .git (which reads 09bd355); an exported
  `RATCHET_CODE_SHA` that disagrees with the file is refused (`CODE_SHA_MISMATCH`, exit 6).
- Tests: `tests/test_v2_harness.py` (new, 34 tests), `tests/fixtures/plant1_v1_helper_programs.json` (the 45 v1 helper
  programs, their v1 results, L_plant_1.py and the 22 training tasks they touch, copied read-only from runs/v1),
  `tests/fixtures/ratchet_v2_amendments_block.txt` (verbatim code block of RATCHET_V2_AMENDMENTS.md); updated
  test_d_fakes (instruction kwarg, solver_library, library_block, screen_decision), test_d_rounds and
  test_d_rounds_resume (v2 plan, full F3 pilot through PLANT_SOLVE), test_e_pilot and test_g_review_fixes (PLANT_SOLVE
  rows; amendment rule end to end on a copied code tree), test_d_integration and test_f_e2e_growth (pinned to V1: their
  StubLLM picks responses by prompt hash, so a new instruction text changes the draw they assert on).

## 4. Exact texts

INSTRUCTION_F3:

```
Write a Python function `def transform(grid):` that takes the input grid as a list of lists of ints and returns the output grid as a list of lists of ints (values 0 to 9, at most 30 by 30). It must produce the correct output for every example above and for the test input. You may import math, itertools, collections, functools, copy, typing and numpy. Return one ```python fenced block containing the complete program. State the rule in at most three sentences, then give the code block. Do not trace the grids cell by cell; your program is run on every example for you.
```

Callable header: `These functions are already defined; call them directly. Pass grids exactly as transform receives them;
these functions accept and return grids as lists of lists of ints.`

Note placement (library prompt, F3): `... Return one ```python fenced block containing the complete program. The library
functions above are already defined in your environment; you may call them. State the rule in at most three sentences,
then give the code block. Do not trace the grids cell by cell; your program is run on every example for you.` Under V1 the
note goes before "Return one ```python fenced block containing the complete program." FLAT prompts carry the instruction
verbatim, and round 1 of STOCK, STATIC and EXEMPLAR (empty context) is byte-identical under both (tested).

## 5. Decisions a verifier should check (where the brief left room)

1. F3 tail = both appended F3 sentences, so the registered F3 text stays contiguous and the instruction's last sentence
   is still last. The alternative reading (note before only the very last F3 sentence) is one line in
   `config.INSTRUCTION_TAILS`.
2. The legend sits inside the code fence, as its first lines (comment syntax), not above the header.
3. Lever check refuses on two cases beyond the brief's "raises where the tuple call does not": results that differ
   between the list and the tuple call (a silent wrong answer, as v1's width/height on 2-column grids), and a check that
   did not run (sandbox error or timeout). It runs before every `client.run` of a job, once per distinct library source
   and arm log, on the spec task's first demo input.
4. The adapter's argument rule is exactly the brief's: any non-empty list whose items are lists or tuples. A program that
   builds an Object as a list of `(value, (i, j))` pairs and passes it at a Piece parameter gets it converted to a tuple
   of tuples, which arc-dsl then treats as a grid. arc-dsl Objects are frozensets, so this needs a list-built object; not
   seen in v1.
5. Library-internal name resolution moved from the program's globals to `lib_g` (the F1 design). Consequence for grown
   (unannotated) helpers: a program that redefines a helper's name no longer changes what other helpers call. Calls,
   counts and returned values are otherwise identical to v1.
6. A pre-v2 run dir (v1) cannot be stepped by v2 code (no recorded instruction: refused). Test runs (skip_pilot, refused in
   production) may record V1 and drive FLAT_A / FLAT_B under it.
7. The F3 screen reads g from FLAT_A's samples.jsonl gen_tokens (the definition behind the 1,451,835 figure) and splits
   S_screen into requests of 16.

## 6. Not done, or outside this commit

- The one failing test, `test_a_sandbox ... test_timeout_swallowed_by_bare_except` (both spawn modes), fails the same way
  on the untouched v1 code (`git archive 08d4a56` copied to Quartz: 13.4 s, limit 7 s) on today's login node; it is not
  caused by this change. It kills at the 10 s hard limit instead of finishing under 7 s, under login-node load (load average 2.6 to 12 during these runs).
- RESULT.md's report of the library-to-FLAT price ratio (Amendment 1) is not built here; PILOT.md reports it.
- Amendment 3's `<maxtok>` placeholder: 3,418 (section 1). Amendment 1's `<f3>` / `<v1>`: section 1.
