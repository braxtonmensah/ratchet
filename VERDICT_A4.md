VERDICT: GO-WITH-CHANGES
BEST APPROACH: Apply AMENDMENT 4 with commit 68cb16d's code unchanged, after two text-only fixes to the amendment block: the supply basis quotes a superseded silicyte-0128 cost, and the block must say the budget was set after the pilot projection was read.
MOVES THE GOAL: No. It changes only the sec. 7.3 budget. The S/R rule, the grid, COMPOUNDS and every gate are unchanged. It reads no growth or sealed outcome, and S 4, R 4 is a registered grid cell.

Written 2026-11-05 00:38 ET (PowerShell Get-Date) by the independent verifier. I did not build A4. Read-only on the repo and on
runs/v2: I applied nothing to the real run, committed nothing and submitted no job. All Python ran on the Quartz login node in a
scratch tree, `/N/scratch/bsmensah/silo/ratchet/verify_a4/`: `code/` = `git -c core.autocrlf=false archive 68cb16d`, and
`runcopy*/` = `cp -a` of runs/v2. A plain `git archive` on this Windows checkout writes CRLF, which breaks the fixture shas, so
the lead's sync must disable autocrlf (step 2 below).

## Evidence

1. **Physics floor (rule 1).** runs/v2/PILOT.json has sha256 a3b5988a..., the same as the fixture. Its rates:
   - decode a = 5,879.7 gen tok/s; b = 0.245; g = 3,607.9; P_task = 1,160.9; startup 581 s.
   - usable 2,539 s per 1 h job, at a 3,120 s issue stop.

   At S 4, R 4 the decode is 102,869 s, and 102,869 / 2,539 = 40.5, so 41 jobs. The grid is 41 / 55 / 69 / 82 / 109 / 136 /
   162 / 217 / 272, and the code's re-projection reproduces every cell; it refuses as PROJECTION_DRIFT if any cell differs. So the
   unchanged rule picks S 4, R 4 for every budget from 41 to 54. The 48 is not sharp: any value in that range gives the same run.
   Power 0.83181 at d = 0.14 for +20/400 is one McNemar comparison. The same PILOT.json gives power_all5_independent
   0.3982 (0.83181^5). The five comparisons are positively correlated, so the joint power of rule 6.1 lies between 0.40 and 0.83.
   Not UNDERPOWERED under the registered 60% rule.

2. **(1) No outcome tuning, nothing makes COMPOUNDS easier.**
   - The diff (43b97f7 to 68cb16d, code files ratchet/amend.py, cli.py, pilot.py only) changes feasibility from
     `jobs <= 12` to `jobs <= budget`. Only `run_pilot_rules` reads the budget.
   - Growth, sealed, knockout, perturbation, selection and FLAT-TTC code paths are byte-identical to 43b97f7.
   - The inputs the budget choice saw were the pilot's FLAT/PLANT rates and d on growth tasks. No growth or sealed data exists
     (amend.py's `growth_started` checks this and refuses otherwise).
   - The one post-hoc element: the budget was picked after the projection showed 41. That is not tuning on any outcome the
     hypothesis is judged on, but the block must say so (REQUIRED A).

3. **(2) amend.py scope (code read plus my own runs on copies).**
   - It refuses if `arms/`, `sealed/`, `knockout/`, `freeze/` or `scores/` is non-empty, if PERTURB_DONE.json or RESULT.md
     exists, or on any non-pilot ledger row (amend.py:74-87). It also refuses if S/R is already set, if the run was already
     amended, if the stop reason is wrong, or if the gates were not passed (amend.py:133-156). Every refusal comes before any
     write.
   - It reads only PILOT.json, RUN.json, the run's ledger and listing, and PREREG.md. It opens no key and no sealed path.
   - It only copies, writes and moves. The single `replace` moves PILOT_STOP.json to PILOT_STOP.superseded_A4.json (amend.py:205).
   - My CLI runs on a fresh copy:
     - `--budget 12`: `AMEND_REFUSED STILL_INFEASIBLE ... min_jobs=41` (rc 3).
     - PREREG without the block: `AMENDMENT_NOT_IN_PREREG` (rc 3).
     - Dry run: S 4, R 4, jobs 41, power 0.83181, pilot_json_sha256_before a3b5988a. Apply: `AMEND_APPLIED A4 budget=48 S=4 R=4`.
     - Second apply: `RUN_SR_ALREADY_SET` (rc 3).
     - `ratchet next` afterwards: `grow STOCK growth round 1`.
   - Every original file is still present except PILOT_STOP.json, which was moved. The archives are byte-identical
     (`cmp` OK). FLAT_A, FLAT_S, V1_FLAT_A, V1_FLAT_B, V1_PLANT1 and V1_PLANT_SOLVE are unchanged (`diff -rq`).
   - The real runs/v2 is unchanged: sha256 of every file was the same before and after my runs.
   - tests.test_a4_amend on Quartz with RATCHET_A4_REAL_RUN set to a fresh copy: 18 run, OK. All 93 committed files of the
     scratch tree match 68cb16d (`git hash-object`).

4. **(3) The 12 default governs any run without the amendment.**
   - config.H100_HOURS_BUDGET is still 12.
   - `budget_hours()` returns 12 unless RUN.json carries both `h100_hours_budget` and a matching `budget_amendment`
     (id, block sha, same number). Otherwise it raises BUDGET_WITHOUT_AMENDMENT (pilot.py diff).
   - `project` and `choose_SR` default to 12. Tests cover the default and the refusal.

5. **(4) Worth the compute, and the meaning at R 4.**
   - Cost: 41 one-hour h100-debug jobs, run strictly one at a time (MaxJobsPU 1 per user). That is at least 41 h of wall time,
     about Nov 6 evening if the slot is contiguous. Our user's debug slot ran 4.6 of the last 24 h
     (COMPUTE_SUPPLY_1104.md sec. 1), so the slack exists. The run does displace fourth_law, SELFARCH and leecomp debug jobs.
   - silicyte-0128 runs in h100-single holders, because a 1 h job cannot finish its rounds (VERDICT_BOOTSEED_V1.md:40), so it
     does not compete for this slot. Its cost per DESIGN_0128.md:34 and PREREG_BOOTSEED_V1.md A1 is about 47 H100-h (91 with
     GUIDE), not "about 30". About 30 is the superseded pre-A1 figure (PREREG_BOOTSEED_V1.md:62, "about 28"). 0127 is not pursued
     (00_CAMPAIGN_STATE.md 00:1x). Central supply 170 minus 91 leaves 79, which is at least 48, so the budget is still
     reachable. The basis sentence is wrong as written (REQUIRED B).
   - Value: the registered kill rule (sec. 9) makes a NULL with a valid PLANT-DRIP a thesis decision, and the prior is
     P(COMPOUNDS) 0.15. A test with single-comparison power of 0.83 is worth about 41 debug hours.
   - Main risk, unchanged by A4: VOID. PLANT-DRIP must beat PLANT-L1 on the seal, and the pilot's PLANT1 was 23 vs FLAT_A 22.
     PLANT_FAIL_DIAGNOSIS sec. 4.4 says the same floor applies. A VOID costs the full 41.
   - R 4 is a registered grid value, so COMPOUNDS keeps its meaning: STOCK has 3 library updates beyond STATIC's L_1, ONE-SHOT
     gets 16 samples per task in one round, and FLAT-TTC is token-matched as before. The sec. 8 prediction ("at round R") stands.
     A NULL speaks to R = 4 only; RESULT.md must state R.

## REQUIRED (blocking apply; text only, code 68cb16d unchanged)

A. **State the timing.** After "the number is set before any growth job and does not depend on any growth or sealed result",
add: "It was set after the pilot's projection was read; every budget from 41 to 54 H100-hours gives the same choice, S = 4
and R = 4."

B. **Correct the supply basis.** Replace "of which about 30 are needed by another study (silicyte-0128)" with: "of which
silicyte-0128 plans about 47 H100-hours (91 with its exploratory GUIDE arm; PREREG_BOOTSEED_V1.md AMENDMENT 1) on h100-single
holders, while this run uses the h100-debug slot".

Put the same corrected bytes, still with `HH:MM`, into `tests/fixtures/amendment_4_block.txt`. The fixture test checks for
"48 H100-hours" and fills HH:MM itself. A re-check of the appended block against A and B turns this into GO.

## NOTES

- N1. If the code dir has neither a CODE_SHA file nor RATCHET_CODE_SHA, `applied_code_sha` records `nogit` instead of
  refusing (seen in my scratch run). Step 2 below writes CODE_SHA first.
- N2. The apply is not one transaction. If it crashes between the RUN.json write and the stop move, a re-apply is refused
  (RUN_SR_ALREADY_SET or ARCHIVE_EXISTS) and the fix is manual. Run the dry run first, as below.
- N3. RUN.json `code_git_sha` stays 43b97f7. Growth jobs will print META code_sha <P>, and the amendment record carries
  applied_code_sha. RESULT.md should name both.
- N4. `required_tok_s_12h` in project() still divides by the registered 12. It is cosmetic.

## Apply sequence (after A and B are fixed and re-checked; nothing here was run by me)

1. Fix the block (A, B) in BUILD_A4.md sec. 1 and in tests/fixtures/amendment_4_block.txt. Append the block to PREREG.md
   `## AMENDMENTS` after AMENDMENT 3, with HH:MM from PowerShell `Get-Date -Format HH:mm` taken at append time. Confirm
   `grep -c "grants one key access" PREREG.md` = 0. Commit (plain message, no attribution) as `<P>`, a child of 68cb16d.
2. Sync `<P>` to `/N/scratch/bsmensah/silo/ratchet/code`. Use
   `git -c core.autocrlf=false archive <P> | wsl -e bash -lc "timeout 120 ssh -o BatchMode=yes quartz 'tar -x -C /N/scratch/bsmensah/silo/ratchet/code'"`,
   because a plain archive writes CRLF here. Then write the full 40-character `<P>` plus LF into `code/CODE_SHA`, and check
   `git hash-object` against `git ls-tree -r <P>` for every path (bad=0).
3. On Quartz, from `code/`:
   `cp -a runs/v2` to a scratch copy, then `RATCHET_A4_REAL_RUN=<copy> $LIGHT/venv_vllm/bin/python -B -m unittest tests.test_a4_amend`.
   It must read 18 OK.
4. On Quartz, the builder's apply script (BUILD_A4.md sec. 5, step 3), unchanged: `cat CODE_SHA` (must print `<P>`), then
   `amend-budget ... --dry-run` (S 4, R 4, jobs 41, applied_code_sha `<P>`, not nogit), then the same command without
   `--dry-run` (`AMEND_APPLIED A4 budget=48 S=4 R=4`), then `ratchet next` (must show `grow STOCK growth round 1`, gpu true,
   chain true), then `ls runs/v2/pilot` (PILOT_STOP.superseded_A4.json, PILOT_CHOICE.pre_A4.json, no PILOT_STOP.json).
5. `squeue -u bsmensah -o '%j %T'` must show no maxRATCH job. Then resubmit the chain on Quartz:

```
cd /N/scratch/bsmensah/silo/ratchet/code && env -u RATCHET_DATA_ROOT -u RATCHET_KEY_ROOT -u RATCHET_SANDBOX_NET -u RATCHET_SANDBOX_SPAWN -u RATCHET_ROOT -u RATCHET_TEST -u RATCHET_PY bash -c 'export RATCHET_CODE_SHA=$(cat CODE_SHA) SBATCH_PARTITION=h100-debug BASE=/N/slate/bsmensah/arc26 LIGHT=/N/slate/bsmensah/arc26/lightning; source /N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh; bash slurm/chain.sh /N/scratch/bsmensah/silo/ratchet/runs/v2'
```

   serve_and_step.sh's CODE_SHA check then compares `<P>` with `<P>` and passes. In the first growth job's server_STOCK log,
   read LEVER INSTRUCTION sha=cf85bc1b... (V1, as the screen left the run) and LEVER ADAPTER ... ok=1 before reading any number.
