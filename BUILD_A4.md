# BUILD_A4: AMENDMENT 4 (silicyte-0119, sec. 7.3 budget 12 to 48 H100-hours)

Builder report, 2026-11-05. For the verifier, then the lead. Commit **68cb16d** (local, not pushed, parent 4623152).
PREREG.md is NOT edited; runs/v2, the Quartz code dir and its CODE_SHA are NOT touched (verified after testing:
runs/v2/pilot/PILOT_STOP.json present, runs/v2/PILOT.json sha256 a3b5988a...87f9, code/CODE_SHA 43b97f7).

Chain job 12679664 (h100-debug) is no longer pending: sacct reads COMPLETED, 00:18:00 to 00:18:04 ET, i.e. it started and
stopped on PILOT_STOP. The chain must be resubmitted after the apply below.

## 1. Amendment text (append-ready, under `## AMENDMENTS`, after AMENDMENT 3)

Fill `HH:MM` before applying: the apply refuses a block that still says HH:MM. The same bytes are in
`tests/fixtures/amendment_4_block.txt` and a test applies them (filled) to the v2 fixture.

```
- AMENDMENT 4 (2026-11-05 HH:MM ET, after pilot v2 read PILOT_NO_FEASIBLE_SR, before any growth job and any sealed read):
  section 7.3 budget. The 12 H100-hours of section 7.3 become 48 H100-hours, for every arm, phase, round and seed. Basis:
  measured supply, about 170 H100-hours reachable by 2026-11-10, of which another study (silicyte-0128) needs about 47
  (91 with its exploratory GUIDE arm) on h100-single holders, not on the h100-debug slot this run uses; the number is set
  before any growth job and does not depend on any growth or sealed result. It was set after the pilot's projection was
  read; every budget from 41 to 54 H100-hours gives the same choice, S = 4 and R = 4. Pilot v2
  (runs/v2, PILOT.md written 2026-11-05 00:08 ET, code 43b97f7) read: 7.1 determinism PASS (FLAT_A 22 and FLAT_B 22
  demo-pass tasks of 50); 7.2 PLANT_SOLVE PASS (49 demo-pass tasks against FLAT_A 22, gain +27, needs +5); the F3 screen
  failed, so INSTRUCTION_V1 at max 4,096 runs (g = 3,607.9 generated tokens per sample); 7.3 PILOT_NO_FEASIBLE_SR: the
  smallest cell, S = 4 and R = 4, projects 41 one-hour H100 jobs against 12 (S = 4, R = 6: 55; S = 8, R = 4: 82); projected
  power for a net gain of +20 of 400 at the measured d = 0.14 is 0.8318 (not UNDERPOWERED). The rule is unchanged: the
  largest S in {4, 8, 16} and R in {4, 6, 8} whose projection fits, which at 48 selects S = 4, R = 4 at 41 jobs. S and R
  are re-chosen from the rates PILOT.json recorded; no pilot arm is re-sampled; the pre-amendment PILOT.json, PILOT.md,
  PILOT_CHOICE.json and PILOT_STOP.json are kept under archived names. Nothing else in sections 1 to 10 or in AMENDMENTS 0
  to 3 changes, and this amendment grants no access to any sealed key.
```

Every number is read from runs/v2/PILOT.json (fixture sha256 a3b5988a7749b027d8edb09dd9f0edc170913ae4c62827eaf86aabcbe5b287f9)
or the given supply note. Grid jobs at the recorded rates: S4 R4 41, S4 R6 55, S4 R8 69, S8 R4 82, S8 R6 109, S8 R8 136,
S16 R4 162, S16 R6 217, S16 R8 272. At 48 only S4 R4 fits (S4 R6 needs 55), so the unchanged rule gives S = 4, R = 4.

## 2. Diff summary (68cb16d vs 4623152; harness otherwise identical to 43b97f7)

| file | change |
|---|---|
| ratchet/pilot.py | `budget_hours(run_dir)`: RUN.json `h100_hours_budget` if set (refused as BUDGET_WITHOUT_AMENDMENT unless `budget_amendment` carries an id, the PREREG block sha256 and the same number), else config.H100_HOURS_BUDGET = 12. `project(..., budget=None)` and `choose_SR(..., budget=None, power=None)`: feasibility is `jobs <= budget` (default 12, so every existing caller is unchanged); `power` reuses a recorded power (it depends on d only). `run_pilot_rules` passes `budget_hours(run_dir)`. PILOT.md gains one "Budget:" line above the grid. |
| ratchet/amend.py (new) | `apply_budget_amendment(run_dir, id, budget, prereg, dry_run)`, see 3. |
| ratchet/cli.py | `python -m ratchet amend-budget --run DIR --amendment 4 --budget 48 [--prereg PATH] [--dry-run]`; exit 3 with `AMEND_REFUSED <reason>`, exit 0 with `AMEND_APPLIED A4 budget=48 S=4 R=4`. |
| tests/test_a4_amend.py (new) | 18 tests (below). |
| tests/fixtures/pilot_v2_PILOT.json | byte copy of runs/v2/PILOT.json. |
| tests/fixtures/amendment_4_block.txt | the section 1 text. |

config.H100_HOURS_BUDGET stays 12 (the registered default); the 48 lives only in the run (RUN.json and AMENDMENTS.json),
tied to the PREREG block hash. Nothing after the pilot reads the budget, so growth, sealed and knockout code paths are
unchanged.

## 3. What the apply does (order chosen so a crash never deletes data)

Refusals first, all before any write: block `- AMENDMENT 4 (` not found exactly once under `## AMENDMENTS`
(AMENDMENT_NOT_IN_PREREG), still `HH:MM` (AMENDMENT_TIME_PLACEHOLDER), block does not say `48 H100-hours`
(AMENDMENT_BUDGET_NOT_STATED); any of `arms/`, `sealed/`, `knockout/`, `freeze/`, `scores/` non-empty, PERTURB_DONE.json,
RESULT.md, or any ledger row whose phase is not `pilot` (GROWTH_STARTED); RUN.json S or R set; already amended; no
PILOT_STOP.json or reason other than PILOT_NO_FEASIBLE_SR; PILOT.json status not PILOT_NO_FEASIBLE_SR or smoke or gate
not passed; any re-projected grid cell's jobs differing from the recorded grid (PROJECTION_DRIFT); still no feasible cell
at the budget (STILL_INFEASIBLE, e.g. at 12).

Then: copy PILOT.json, PILOT.md, pilot/PILOT_CHOICE.json to `PILOT.pre_A4.json`, `PILOT.pre_A4.md`,
`pilot/PILOT_CHOICE.pre_A4.json`; write new PILOT.json (status OK, S 4, R 4, `budget_amendment`; rates unchanged), PILOT.md,
PILOT_CHOICE.json; append the record to run-level `AMENDMENTS.json`; set RUN.json S, R, `pilot_choice`,
`pilot_underpowered`, `h100_hours_budget` 48, `budget_amendment` {id 4, prereg_block_sha256, prereg_file_sha256, jobs 41,
power 0.83181, pilot_json_sha256_before, superseded_stop, applied_code_sha, applied_et}; last, rename
pilot/PILOT_STOP.json to pilot/PILOT_STOP.superseded_A4.json. Pilot sample dirs are never touched. After it,
`rounds.next_unit` returns `grow STOCK round 1`.

## 4. Tests (Quartz login node, scratch copy /N/scratch/bsmensah/silo/ratchet/code_a4test, venv_vllm python 3.13)

- tests.test_a4_amend: **18 run, 18 pass** (with RATCHET_A4_REAL_RUN set to a scratch copy of runs/v2's RUN.json,
  PILOT.json, PILOT.md, STATUS.json, pilot/ and ledger/ at code_a4test/_runcopy/v2). Covers: fixture is the v2 pilot
  (22/22, 49 vs 22, g 3,607.9, d 0.14); re-choose at 48 picks S 4, R 4 at 41 jobs, power 0.83181, one feasible cell;
  infeasible at 12 and the default is still 12; at 60 the unchanged rule takes S 4, R 6; projection drift refused; full
  apply (archives byte-identical to the originals, STOP moved, RUN.json and AMENDMENTS.json, PILOT.md Budget line,
  next_unit goes from `blocked PILOT_NO_FEASIBLE_SR` to `grow STOCK 1`); refuses at 12 with no file changed; refuses after
  growth starts (arms round dir, growth ledger row) and on a freeze dir, with no file changed; amendment must exist in
  PREREG (absent, HH:MM, wrong budget, other id, a mere mention in another item); block ends at the next item; second
  apply refused; other stop reason refused; dry run writes nothing; run budget without record refused; CLI exit codes;
  the section 1 text refused with HH:MM and applied once filled; the real-copy dry run and apply reach `grow STOCK 1`.
- Full suite (`python -m unittest discover -s tests`, same scratch copy, RATCHET_A4_REAL_RUN set to a fresh run copy):
  **356 run: 353 pass, 2 fail, 1 skip.** The 2 failures are the known `test_timeout_swallowed_by_bare_except` pair
  (TestSandboxBasics and TestSandboxBasicsSpawn) that BUILD_V2 already lists as failing at 43b97f7. Nothing else fails,
  so the pilot.py change breaks no earlier test. (An earlier run, 355 tests, also had 2 subtest failures in the new file
  from a test bug, fixed before the commit.)

## 5. Apply command for the lead (after the verifier's GO)

1. Append section 1 to PREREG.md with the real time, commit (plain message), giving commit `<P>`, a child of 68cb16d.
2. Put commit `<P>` on Quartz in a code dir of your choice (job 12679664 has finished, so `code/` is free again) and write
   `<P>` into that dir's CODE_SHA, as for v2. The dry run below needs only CPU.
3. One ssh at a time, `wsl -e bash -lc "timeout 120 ssh -o BatchMode=yes quartz bash -s < apply_a4.sh"` with:

```
export BASE=/N/slate/bsmensah/arc26 LIGHT=/N/slate/bsmensah/arc26/lightning
source /N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh >/dev/null 2>&1
C=/N/scratch/bsmensah/silo/ratchet/code      # the dir holding commit <P>
cd $C && export PYTHONPATH=$C && cat CODE_SHA
$LIGHT/venv_vllm/bin/python -m ratchet amend-budget --run /N/scratch/bsmensah/silo/ratchet/runs/v2 --amendment 4 --budget 48 --prereg $C/PREREG.md --dry-run \
 && $LIGHT/venv_vllm/bin/python -m ratchet amend-budget --run /N/scratch/bsmensah/silo/ratchet/runs/v2 --amendment 4 --budget 48 --prereg $C/PREREG.md
$LIGHT/venv_vllm/bin/python -m ratchet next --run /N/scratch/bsmensah/silo/ratchet/runs/v2
ls /N/scratch/bsmensah/silo/ratchet/runs/v2/pilot
```

Expected: the dry run prints a JSON record with S 4, R 4, jobs 41; the apply prints `AMEND_APPLIED A4 budget=48 S=4 R=4`;
`pilot/` shows PILOT_STOP.superseded_A4.json and PILOT_CHOICE.pre_A4.json and no PILOT_STOP.json. Then resubmit the chain.

Note for the lead: RUN.json `code_git_sha` stays 43b97f7 (the run's pilot code); the amendment record carries
`applied_code_sha` (= `<P>` from CODE_SHA). If the chain resumes on a code dir at `<P>`, serve_and_step.sh's CODE_SHA check
must be given `<P>`, as usual.
