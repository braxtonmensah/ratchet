VERDICT: GO-WITH-CHANGES
BEST APPROACH: Launch commit e2a9c2d unchanged with launch_pilot_v2.sh, but first correct two sentences of AMENDMENT 2 so the registered text matches the code (where the note goes under F3, and when the adapter lever refuses), then append and re-gate.
MOVES THE GOAL: No. The adapter changes only helpers annotated Grid/Element/Piece, which means the arc-dsl plant arms and PLANT_SOLVE. Grown STOCK/STATIC/ONE-SHOT/SHAM helpers pass through by identity. The FLAT-TTC rule, metric, seal and section 3 sampling are untouched, and F3 makes COMPOUNDS harder, not easier.

Written 2026-11-04 23:14 ET (PowerShell Get-Date) by the independent pair_gate verifier. I did not build this. Read-only: no repo
file edited, nothing committed or pushed, no Slurm job submitted, runs/v1 untouched. All Python ran on the Quartz login node
(h2, nproc 1, load 11 to 24). My outputs are in `/N/scratch/bsmensah/silo/ratchet/verify_v2_unittest.out` and
`/N/scratch/bsmensah/silo/ratchet/verify_v2_plantsolve.out`, and my check script is `/tmp/bsm_ps_check.py` on h2. Before the
parent restart I had only started reading, and I had started no pytest. `pytest` is not installed in the vLLM venv
(`No module named pytest`), so I ran the suite with `unittest discover`, as the builder did.

## Evidence

1. **The Quartz copy is the commit.** `CODE_SHA` = `e2a9c2dd4635fe49d09b204dbdf6c57e2ac30d76` (41 bytes). Its own .git reads
   09bd355, as the builder said. I ran `git hash-object` on every one of the 72 paths in `git ls-tree -r e2a9c2d`: checked=72,
   bad=0. The working tree has no tracked modifications. Only untracked docs and scripts are present (launch_pilot_v2.sh among
   them, not yet on Quartz).

2. **Physics floor (rule 1, 7).** v1 job 12678501: 20:15:56 start, FLAT_A start 20:28:45 (12 m 49 s of vLLM load, modelcheck
   and selftest). Each 400-sample round took 4 m 20 s for about 1.45 M generated tokens (FLAT_A 1,451,835; about 5.6 k gen tok/s
   including exec). Exec is negligible: 1 TIMEOUT in 1,200 v1 exec rows. Worst case for v2 is that F3 does not shorten anything
   (g stays 3,630). Then S_screen = round(1,451,835 / (50 x 3,629.6)) = 8 and every round costs about 4.3 min. The F3 path
   (FLAT_A, FLAT_S, FLAT_B, PLANT1, PLANT_SOLVE) comes to about 34.5 min including startup. The V1 fallback (F3 FLAT_A, FLAT_S,
   then V1_FLAT_A, V1_FLAT_B, V1_PLANT1, V1_PLANT_SOLVE) comes to about 39 min. At g near 500, FLAT_S has the same 1.45 M token
   budget (about 2,900 samples, sent as n <= 16 requests) and the other rounds shrink. So the pilot fits one 1 h h100-debug job
   in every branch. Resume covers the rest: FLAT_S persists its `screen` dict and S in round_state (arms.py:1158, 1255 to 1262),
   seeds are per batch offset, and the decode fit is per job (pilot.py:215). Context:
   8,413 + 6,000 + 4,096 + about 330 < 20,480. The PLANT_SOLVE block is at most 3,418 tokens (median 1,574).

3. **Arm fairness (check 1).**
   - One header for every callable library arm. config.py:262 = v1 header + the grid-contract sentence exactly. The same text is
     in prompt.py `_DEFAULTS` and library.py `CALLABLE_HEADER`.
   - One placement rule for every library and exemplar note: prompt.py:167 `with_notes`, tails at config.py:214. Every caller,
     knockout inline included, goes through it.
   - Instruction: every prompt takes the run's recorded instruction (arms.py:187 `run_instruction`, `build_prompt`).
   - Round 1 of STOCK, STATIC and EXEMPLAR (empty context) is byte-identical under both V1 and F3. This is tested in
     test_v2_harness `test_round1_byte_identity_stock_static_exemplar` and passes on Quartz.
   - Unannotated helpers return the same object (sandbox_child.py:246 `_adapt` returns fn when sig is None; tested).
   - The legend goes into the exact-count text for callable blocks only (prompt.py:151, 243). It is empty unless a rendered
     helper carries a string annotation naming an arc-dsl alias, so grown and SHAM libraries pay 0 tokens.
   - FLAT-TTC computation: no diff line touches it. `price` in pilot.py is report-only.

4. **Adapter and wrappers (check 2).**
   - Counting still wraps the functions inside the library namespace (sandbox_child.py:463, 483), so library-internal calls are
     counted as in v1. Counting stays on test inputs only. The increments did not change.
   - Both wrappers are generated with the wrapped function's own parameter list (sandbox_child.py:202 `_clone_signature`):
     co_argcount, positional-only, keyword-only, `__defaults__` and `__kwdefaults__` are preserved. This is the arc-dsl
     rbind/lbind fix.
   - The adapter changes behaviour only at the list/tuple boundary of grid-annotated parameters and returns.
   - One semantic change from v1: a program that redefines a helper's name no longer changes what other helpers call. This is
     arm-neutral and makes the reuse gate stricter, not looser.
   - Can a program reach `lib_g` or the counters? Yes, through `helper.__wrapped__.__globals__` or `.__closure__`. v1 was the
     same: there `helper.__closure__` and `__globals__` were the program's own globals. The sandbox has never blocked dunder
     attribute access, the threat model is a non-adversarial proposer, and no new hole was opened. NOTE only.
   - I reproduced the lever myself: `transform = solve_this(grid)` on all 50 pilot tasks with real arc-dsl and the model
     tokenizer gives 50 of 50 demo-pass and 50 of 50 test-correct. Under the v1 boundary (adapter off) only 8 of 50 pass, which
     is the positive control of the lever. `adapter_smoke` is ok on 50 of 50 closures. In the suite, L_plant_1 reads
     `grid_helpers=13 list_smoke_ok=13`, and the v1 boundary reads 4 and is refused. The replay of the 41 v1 crash programs
     gives 24 demo-pass over 10 tasks.

5. **F3 screen (check 3).**
   - S_screen = max(1, round(1,451,835 / (n_tasks x g))), with g = mean `gen_tokens` of the F3 FLAT_A's samples
     (arms.py:1158). The thresholds are >= 23 demo-pass tasks AND >= 22 pass@2 test-correct tasks (config.py:303-304,
     pilot.py:162).
   - Plan order: FLAT_A, FLAT_S, pilot_screen, then the remaining arms (rounds.py:318, config.py:88). A failed screen sets
     RUN.json to V1 once (arms.py:1295). It re-runs FLAT_A, FLAT_B, PLANT1 and PLANT_SOLVE as V1_* dirs. MAX_TOKENS stays
     4,096.
   - Each pilot dir refuses an instruction other than its own, and refuses to resume under a different sha.
   - Screen rows are phase pilot. The growth readers (SHAM pool, exemplar pool) never see pilot rows (tested). Exemplars from
     pilot sample ids are refused (arms.py:480).
   - `LEVER INSTRUCTION sha=` prints at job start and once per (arm, phase) log. A tampered sha refuses before any model call
     (tested).

6. **PLANT_SOLVE (check 4).**
   - Gate: kS - kA >= 5 against the same-instruction FLAT_A (pilot.py:139, `physical()` maps it to V1_* after a fallback).
     PLANT1 is computed with `gates: False`.
   - Pilot-only, enforced in four places: `library.merge` and `save` refuse it outside pilot/ (library.py:222, 272); `freeze`
     refuses it by path and by JSON (freeze.py:35, 41); `_check_pilot_only` refuses it in any non-pilot prompt or split.
   - The pilot dirs never reach the sealed scorer (no diff line touches key handling; arc_io.py and guard.py are unchanged).
     arc-dsl has solvers for training tasks only.
   - Can the control pass without the lever? If the model inlines `solve_this`'s body, the primitives it calls still go through
     the adapter, so the lever is still exercised and the library was still read. I accept that for a plumbing control.
     `samples_calling_solver_on_test` and `samples_referencing_solver` are reported (pilot.py:149, 517), but per sample, not per
     demo-pass task. NOTE.

7. **Seal (check 5).**
   - score_sealed.py:502, 522: a re-read needs the exact phrase `grants one key access` inside that amendment's own paragraph.
   - `grep -c "grants one key access"` gives 0 in both RATCHET_V2_AMENDMENTS.md (current 22:2x text) and PREREG.md, so the
     three new amendments mint no read token.
   - The pilot path never calls score_sealed. The v1 selftest shows `read_key=ERROR` from the sandbox.

8. **Launch path (check 6).**
   - launch_pilot_v2.sh exports `RATCHET_CODE_SHA=e2a9c2dd...`. `chain.sh` passes it with `--export=ALL`, and the job-start
     self-chain carries it again. serve_and_step.sh:35-37 compares it with `head -c 40 CODE_SHA` = the same sha, so it passes.
   - `ratchet init` on the login node records the same sha (arms.py:277 reads env first) and instruction F3.
     `SBATCH_PARTITION=h100-debug` overrides the `#SBATCH -p` list.
   - A job whose first unit is `pilot_screen` (CPU) runs `--no-gpu`, exits NEEDS_GPU and re-chains. That costs one short slot,
     the same pattern as v1's pilot_choose.
   - The VERIFIED gate requires a Quartz-side file whose first line is exactly `VERDICT: GO` (`grep -qx`). This file is
     GO-WITH-CHANGES, so the launcher correctly refuses it.

9. **Tests (check 7).** Run 1 was the full suite, run concurrently with my PLANT_SOLVE check: 338 run, 4 fail, 1 skip
   (182 s).
   - The 4 failures were `test_timeout_swallowed_by_bare_except` x2 (10.01 s and 10.06 s vs the 7 s limit),
     `test_spawn_cost_map` (spawn+numpy, 4 of 24 `AGG_KILL:HARD_KILL`) and `TestSandboxRefusalsSpawn.test_ctypes_via_numpy_refused`
     (TIMEOUT, not ERROR).
   - I re-ran `test_a_sandbox.py` alone: 62 run, only the 2 timeout-swallow failures. spawn numpy took 0.36 s per program and
     passed. The two extra failures were spawn-mode numpy imports starved on a 1-CPU login node under my own concurrent load.
   - Production runs zygote: chain.sh and ratchet_step.sbatch refuse `RATCHET_SANDBOX_SPAWN`.
   - The timeout-swallow test still asserts status TIMEOUT first (line 95), and that passes. Only the wall-time bound fails,
     because the parent hard-kills the child at about 10 s. The builder showed the same failure on v1 08d4a56. In the pilot such a
     program is still recorded TIMEOUT and costs at most hard_s of one worker (v1 had 1 TIMEOUT in 1,200 samples). It does not
     matter for the pilot.
   - The skip is not the arc-dsl class: `V2_PLANT_SOLVE tasks=50 max_block_tokens=3418 tokenizer=HFTokenizer` ran.

10. **Anything that makes COMPOUNDS easier (check 8).** I found none.
    - The adapter is inert for unannotated grown helpers. The header sentence is the same for all library arms. F3 raises the
      library-to-FLAT price (about 2.26x to about 4.6x), which favours FLAT-TTC.
    - The screen selects an instruction on FLAT outcomes only.
    - The lib_g isolation can only stop accidental helper/program name cross-talk. It is arm-neutral.

## REQUIRED (blocking launch)

R1. **AMENDMENT 2's text must describe what the code does** (RATCHET_V2_AMENDMENTS.md:36-37). Code is unchanged; this is a
text-only fix before appending.
   - (a) Note placement. Under F3 the code (config.py:214 `INSTRUCTION_TAILS['F3']` = both appended F3 sentences) puts the
     library/exemplar note before "State the rule in at most three sentences, ...". The text says "before the instruction's
     final sentence", which under F3 is "Do not trace the grids ...". Replace with: "The library or exemplar note is placed
     immediately before the instruction's closing text: under INSTRUCTION_V1 before 'Return one ```python fenced block
     containing the complete program.', under INSTRUCTION_F3 before the two appended F3 sentences, which stay contiguous and
     last."
   - (b) Lever timing. The code refuses before the first model call that puts a given callable library in context (per
     distinct library source and arm log, per job). It refuses also when the list and tuple calls return different values or
     the check itself fails to run. It does not refuse at job start. Replace "Each job prints LEVER ADAPTER grid_helpers=<n>
     list_smoke_ok=<n> and refuses to start if any grid-typed helper raises on a list-of-lists demo grid." with: "Before the
     first model call that puts a callable library in context, each job prints LEVER ADAPTER grid_helpers=<n>
     list_smoke_ok=<n> for that library and refuses if any helper whose first parameter is grid-typed raises on a
     list-of-lists demo grid where its tuple call does not, returns a different value, or cannot be checked."
   - Then fill HH:MM from PowerShell Get-Date and append. A re-check of only the appended lines against this list turns this
     into GO, and the launcher needs a Quartz-side file whose first line is exactly `VERDICT: GO` with LF line endings
     (`grep -qx` fails on `VERDICT: GO\r`).

## NOTES (non-blocking)

N1. Launch command checked (unchanged from slurm/launch_pilot_v2.sh). Copy it to Quartz first:
`VERIFIED=/N/scratch/bsmensah/silo/ratchet/code/<GO verdict file> bash /N/scratch/bsmensah/silo/ratchet/code/slurm/launch_pilot_v2.sh`.
It passes CODE_SHA as long as the Quartz `CODE_SHA` file stays e2a9c2d. If the PREREG append is committed and the code dir is
re-synced with a new CODE_SHA, the launcher's hard-coded e2a9c2d is refused with exit 6. That is the safe direction. Either
leave the code copy and CODE_SHA alone (the PREREG commit changes no code file) or update both together. Record the PREREG
commit sha in PILOT.md.
N2. `tests/fixtures/ratchet_v2_amendments_block.txt` still holds the placeholder text (`<f3>`, `<v1>`, `<maxtok>`, no signature
sentence). The test passes and the current text also lacks the grant phrase. Refresh the fixture to the final appended block
in the PREREG commit.
N3. For PILOT.md, report PLANT_SOLVE per demo-pass task as well as per sample: the number of demo-pass tasks that have a
demo-pass sample calling `solve_this`, versus ones that pass only through inlined primitives.
N4. The adapter is partial by registered rule. Returns annotated `Tuple` (hsplit, vsplit) keep tuple-of-tuple grids, which
contradicts the header's "return grids as lists of lists" for those functions. A list grid passed where arc-dsl hashes it
(`initset`, `frozenset`) still raises. These apply to PLANT-DRIP and PLANT-L1 alike. Watch the PLANT1 ERROR mix in PILOT.md.
N5. Dunder reach to counters and lib_g (evidence 4) is unchanged from v1. Close it only if a proposer is ever treated as
adversarial.
N6. The timeout-swallow test's 7 s bound is now environment-dependent (also on v1 code). Either widen it to hard_s or mark it
as a wall-time measurement, so the suite reads green at the pair gate.
