VERDICT: GO

# silicyte-0136 ONE-SHOT (d) amortisation: independent verification

Verifier, 2026-11-05 evening ET. All Python ran on the Quartz login node (python3 3.6.8 -I -B, nice 19) in
/N/scratch/bsmensah/verify0136/. No Slurm job or step was submitted, cancelled, held, released or entered; no GPU was used.
GO is conditional on the launch line at the end (it fixes a chain-stop bug and puts a control first). Without it: NO-GO.

## 1. Scorer

- B1 path = registered beam. oneshot0136.py calls bootllm.beam(task, 1, logp, 10); bootllm.beam's search loop is token-for-token
  the same as bootseed0128.beam2 (beam2 adds only hprog/hend on failure). 0128's MEAS fixed_rows were made by BL.solve -> BL.beam
  (bootseed0128.py:408). Run check (check_beam.py, beam2 extracted from bootseed0128.py c54e21d2 by ast): BL.beam vs beam2 equal on
  (v, c, exec, prog) for 300 of 300 MEAS tasks at B 1 and at B 4, under 3 stub policies (two hashed, one gold-boosted with 143 B1
  solves, 117 of length >= 2).
- What "one-shot" means here: B1 keeps ONE state per step, but every step executes all 54 children and returns at once if any
  equals the target. So the last step is exhaustive: a depth-d solve needs d - 1 correct greedy picks plus a free 54-way check
  (measured: 143 of 143 gold-mix B1 solves land inside the L-th expansion, exec <= 54 L). B1 = greedy plus final check. O0
  (rollout0) is the pure greedy rollout: argmax op, execute, stop at target, invalid op ends it; it shares B1's memoised calls.
- logp normalisation in solve_oneshot equals BL.solve's; each logps call is one prompt (1 head + 54 candidates) whatever B is, so
  B1 and B4 use the same per-state numerics.
- CONTROL_B4 (GPU lever check): compares registered B 4 rows (tid, depth, v, c, exec) on the first 60 MEAS tasks to stored
  fixed_rows for P_a and P_b, exit 5 on mismatch. FINDING: in the builder's plan it runs LAST in each process (after all 11
  policies, about 70-100 min), not first. FINDING (blocking as written): run_oneshot0136.sh always exits 0 (its last command is
  `echo ONESHOT_EXIT rc=...`; no `exit $RC`, no `set -e`), so the builder's `&&` chain NEVER stops on exit 5/6/7. Both are fixed
  in the launch line without touching the builder's code: first call `score s1 --ts 0-1 --tag rep` (2 adapters resident, B1 on
  P_0/P_1, then CONTROL_B4 on P_0 and P_1, about 25 min), and every call is followed by a check of `ONESHOT_EXIT rc=0` in the log.
  The r() stop logic was tested with a fake run script (verify0136/chaintest.sh): rc 0 -> CHAIN_DONE; rc 5 -> CHAIN_STOP at the
  first call, exit 1.
- Selftest (builder log logs/selftest_full2.out) was run on code md5 a6353b89; the current oneshot0136.py has md5 a6353b89
  (sha256 f90101f4...): same code.

## 2. Memory

- oneshot0136.py:252-255: torch.cuda.init(); torch.cuda.set_per_process_memory_fraction(ONESHOT_MEM_FRAC=0.30, 0) BEFORE
  ident.Scorer loads the model. Peaks logged: per policy summary.peak_gb / peak_reserved_gb and the SCORED_B1 line; SCORE_DONE
  prints the process peak.
- Physics floor (Qwen3-8B config: 36 layers, 8 KV heads, head_dim 128 -> 147,456 B KV per token): weights 16.4 GB + 11 adapters
  x 174,655,536 B = 1.92 GB + KV of the 54-row repeat. MEAS prompt length, greedy vocab estimate: 302 / 398 / 494 tokens (min /
  median / max) + about 12 template tokens -> KV 4.03 GB at the longest (5.03 GB at +25% estimate error). Peak about 22.8 GB
  (23.8 GB worst) vs cap 0.30 x about 85 GB = 25.5 GB. Margin 1.7-2.7 GB. An overrun OOMs only this process, inside its own cap.
- Trainer neighbours: the chain must run on a non-trainer holder. Running single-GPU holders that are NOT H1-H6, H8, H9, H10:
  H7 12693135 (g44), H11 12694678 (g78), H12 12694679 (g70); I1 12694854 has 3:40 left (too short). I could not read their free
  memory (no srun into holders allowed); the launch line refuses to start below 25,600 MiB free. The lead must confirm the chosen
  holder runs inference only (a reachlaw trainer grows to 71 GB).

## 3. Reader on synthetic data (new primary)

verify0136/sim_logratio0136.py, 8,000 sims per cell, 0128 noise (tau 0.158, s_e 0.127, sg 0.021), constant-fraction null
A0 in {0.45, 0.70}, rho in {0, 0.8}, c in {1, 1.5}; full table in PREREG sec. 6a, raw output verify0136/sim_logratio0136.out.
- FP under the constant-ratio null: 0.049-0.056 (MC sd 0.0025). At alpha.
- Power: MDE at 80% = 0.019-0.043 per round in log(B1/S); e.g. beta 0.03 -> 0.58-0.99, beta 0.04 -> 0.77-1.00.
- The old difference test on the same nulls calls GAP_GROWS in 28-96% of sims: confirms the lead's choice.
- A constant ABSOLUTE gap reads AMORTISES on the primary in 25-97% of sims (the ratio rises as S rises). Declared in PREREG and kept
  out of COMPOUNDING-CANDIDATE by a new condition (v): difference mean slope > 0.
- Builder's planted smoke re-run with the amended reader: delta 0 -> NO_AMORTISATION_DETECTED (t -0.20); +0.15 -> AMORTISES +
  COMPOUNDING-CANDIDATE (t 45.05); -0.15 -> RATIO_FALLS (t -19.39); +0.05 -> AMORTISES, UNIT-DEPENDENT, no candidate (difference
  t -5.12); B1 d50 None at s3 round 0 -> iso scale for all seeds. Real dir now: GATES missing -> VOID_OR_INCOMPLETE (correct).

## 4. PREREG text (amended)

States: the primary (per-seed OLS slope of log(B1 d50 / S d50), rounds 0..10, one-sided t over 4 seeds, crit 2.3534, AMORTISES iff
it passes); the difference slope as SECONDARY; O0 telemetry on iso d50; the d50 None rule (any B1 or S logistic d50 None or <= 0,
any seed, any round incl. 0 -> iso d50 for all seeds; iso censored at 10 flagged); reruns (a crashed seed rerun once in full after
moving partials to out_void/; control, identity, provenance or A/A failures never rerun, VOID); control-first launch order; and
"THIS RESULT IS NOT A COMPOUNDING CLAIM BY ITSELF". Stored S d50 non-None for all 44 (2.635-4.900).

## 5. Hashes

Builder files (BUILD, DESIGN_B, PRIOR_ART, oneshot0136.py, sim, smoke, run .sh, SHA256SUMS.txt, GATE_STORED, amort_stored.py):
laptop sha256 = Quartz sha256, all equal to SHA256SUMS.txt. RESULT_STORED_AMORT_1105.md was laptop-only; copied to Quartz
(56a67000...). SHA256SUMS.txt is the builder's and was NOT updated: its PREREG and reader lines are now stale by design.
Changed files (laptop = Quartz; builder originals saved in verify0136/*.builder.*):
- PREREG_ONESHOT0136_DRAFT.md 734cd7ad... -> 13f79839a8b4b6320dfc66b82d304068d1dfcabd26da3d0c3850e9d9f334b483
  (amendment note; sec. 3 adds b_k; sec. 4 rewritten to the lead's primary, labels AMORTISES / RATIO_FALLS / NO_AMORTISATION_DETECTED,
  secondary, O0 telemetry, candidate condition (v), d50 None rule, not-a-compounding-claim line; sec. 6a new log-ratio power table,
  old table kept as 6b; sec. 7 question resolved; new sec. 9 launch order and reruns).
- read_oneshot0136.py b48e2983... -> d00f6b790de999efe19a5f963f71085ffa8ab8eee0130598b9838ee939e89ef5
  (primary = log-ratio slope; None/<=0 rule covers B1 and S; difference, iso, per-step-error rows secondary; O0 rows on iso
  consistently (old code mixed scales per cell); candidate adds (v); UNIT-DEPENDENT printed; gates unchanged).
- VERDICT_ONESHOT0136.md (this file) new. Quartz dir also holds other lane files (GATE_GUIDE_ALPHA, GATE_LOOP_PHYSICS*,
  GATE_REINVEST, guide_alpha.py, loop_physics*.py, reinvest.py) that are not part of 0136 and were not checked.

## Launch line (lead only; one card, about 5-7.5 h; H12 shown, H7 12693135 or H11 12694678 if H12 is busy)

```
H=12694679; setsid nohup srun --jobid=$H --overlap -n1 -c 6 --cpu-bind=none bash -c 'O=/N/scratch/bsmensah/silo/oneshot0136; L=$O/logs/score_chainA.log; F=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); echo "PRECHECK job=$SLURM_JOB_ID free_mib=$F $(date -Is)" >> $L; [ "$F" -ge 25600 ] || { echo "PRECHECK_FAIL free_mib=$F"  >> $L; exit 4; }; export ONESHOT_MEM_FRAC=0.30; r(){ bash $O/run_oneshot0136.sh "$@" >> $L 2>&1; tail -n 1 $L | grep -q "^ONESHOT_EXIT rc=0 " || { echo "CHAIN_STOP at [$*]" >> $L; exit 1; }; }; r score s1 --ts 0-1 --tag rep; r score s1; r compare $O/out/s1/P_0.B1.json $O/out/s1/P_0.B1.rep.json; r compare $O/out/s1/P_1.B1.json $O/out/s1/P_1.B1.rep.json; r score FRONTIER_s2; r score FRONTIER_s3; r score FRONTIER_s4; echo CHAIN_DONE >> $L' > /dev/null 2>&1 < /dev/null &
```
Read after CHAIN_DONE (login node):
```
cd /N/scratch/bsmensah/silo/oneshot0136 && grep -E "PRECHECK|CONTROL_B4|DETERMINISM|SCORE_DONE|CHAIN_|peak_gb" logs/score_chainA.log && python3 -I read_oneshot0136.py | tee logs/READ_0136.txt
CPU_OK=1 python -I C:/Users/bmens/NQ_local/lane/lever_check.py <local copy of logs> ONESHOT="LEVER_ONESHOT run=\S+ t=\d+ B=1 max_steps=10 active=P_\d+"
```
The lead timestamps the amended PREREG before launching. A CHAIN_STOP at the first call means the GPU lever failed: VOID, no rerun.
