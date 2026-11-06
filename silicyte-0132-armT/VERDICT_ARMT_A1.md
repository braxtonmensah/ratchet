VERDICT: GO

Scope of this GO: it covers the two GPU pre-switch steps (a1gpucheck, then a1probe) on holder 12693135 after a STOP at a round boundary. The SWITCH itself (writing AMENDMENT_A1.json and relaunching with armt_a1.py from K) is GO ONLY IF A1_GPUCHECK PASS and A1_PROBE_PASS both appear. If either fails, the study continues as registered (fallback below), with NO_UPDATE expected at round 6.

Verifier: independent, 2026-11-05, written 19:37 ET. Read-only except this file and its Quartz copy. No job, step, STOP file or process touched.

## Files verified (sha256, laptop and Quartz byte-identical, re-taken 19:3x ET)

| file | sha256 |
|---|---|
| AMENDMENT_A1_DRAFT.md (laptop) | f2bca6e20e1ceb8bc9047fb4d5e5caf5b2563b819a5a5c261de87506c5fb627e |
| armt_a1.py | 5d7db6b8d6e27e77ebcca16dd1d4389efebd4569f23292a1b9d96fe6983f0114 |
| smoke_cpu_a1.sh | 449f6c92e62af981aef74203e7948ca8c759b521dcbd05478b0b89fd67b97bc9 |
| armt.py (Quartz, registered) | 8fce8dadae38d0144d6b3cdef79893ae0041d30e5a6ac3b4fe76479ecd8fcea9 |
| a1_build/armt_registered.py (laptop) | 8fce8dad... (same bytes) |
| read_armt.py | 9090cb56d80c3553ec2f1c2e7d0c4184e581555c26236a86494807dabdab9c97 |
| smoke_cpu.sh | 82dbdee0e5fe14efd6c78f6355bf8a71b80d13b0becdfd4a59b984102a15e1af |

Quartz state at 19:35 ET: no AMENDMENT_A1.json, no STOP, no a1_probe/, no a1_gpucheck/ in the study tree. So the probe gate text exists before any probe data. Live loop attempt_20261105T230017Z: META armt_sha=8fce8dad..., ROUND_DONE r=2 total_s=3920, ROUND_START r=3, STATUS RUNNING step 12693135.2. Round 2: SFT_SET rows=0 on all 3 seeds, EMPTY_SFT_SKIP.

I read the full diff `diff armt_registered.py armt_a1.py` (all A1 code), score_round_rows, sft_select, train_lora, cmd_sample, cmd_loop, cmd_fork1, stream_seed_tag, stream_adapter, pinned_archive_rows, and PREREG_ARMT.md's decision rule.

## 1. Copy-safety rule

Byte-identical exclusion: COMPLETE, hunt-wide and stream-wide.
- `a1_seen_matrices(stream, R)` = every matrix_sha256 in `pinned_archive_rows()` (the first SNAPSHOT.json archive_rows lines of the hunt archive, refused unless they hash to archive_sha256) plus every matrix_sha256 in this stream's OWN archive `runs/<stream>/hunt/archive/archive.jsonl` with round < R.
- The round field is zero-padded ("r01", "r02"; 477 rows each in TRAINED_s0) and R = rname(r) = "r%02d", so the string compare `< R` is correct through r99 and excludes the current round.
- `a1_near_status` disqualifies a template if ANY instance at implied d >= rb - 2 is seen, is not 'novel' (unknown never qualifies), or sits at or above rb. Smoke: a1count r1 gives A1_rows=0 on all 3 seeds with `seen_matrix` on PCB2_2; builder's r2 count also 0.
- Strict climbs need v > rb >= d0 = the archive closure, so they cannot be archive copies.

Derived (non-identical) exclusion: NOT complete. Non-blocking, but say it in the registry entry.
- The code-level `derives` test checks against `warm_known()` (the shown matrices) plus `state['known']`, which holds only matrices that raised a running best (climbs, KNOWN_CAP 300).
- So two kinds of variant can still enter as near rows: (a) a derived or permuted variant of an UNSHOWN archive matrix (the amendment states this in sec. 4), and (b) a derived variant of one of this stream's OWN earlier near-row matrices. Near-row matrices are never added to `known`. The amendment does NOT state (b).
- Neither can create G or Gnd. A free derivation of a matrix at rb - 1 or rb - 2 does not reach rb, and the closure covers the archive. The risk is paste-and-perturb training. That shows up as SHARPENING or COLLAPSE (distinct matrices < 0.8x or 0.5x FROZEN), which the registered labels already punish.
- Minor: two different templates in one round that emit the same NEW matrix can both enter (one row per template sha). That is the model's own new matrix, not a copy.

No FROZEN signal reaches TRAINED's rows.
- `seen` reads only this TRAINED stream's own hunt dir and the pinned archive. `sft_select_a1` reads only this stream's recs and `state['cells']`. Each stream has its own `runs/<stream>/hunt`.
- The only FROZEN-origin data in TRAINED's tree is r01. cmd_fork1 copies FROZEN_s<k> r01 into TRAINED_s<k>, and PREREG says round 1 is shared. No FROZEN round >= 2 data is read.
- TRAINED-only extra copy tests (window instances) are appended AFTER the climb candidates and the registered 48-matrix sample, with `sample` = False. Effects:
  - copy_share, copy_unknown_share and overlap50_share use only `sample` tests, so they are unchanged.
  - Every instance with v > rb_nd is already a climb candidate, so extras cannot change rb_nd, closure_nd, Gnd or climb status.
  - The extras change only the unused `best_status` field and the TRAINED score time.
  - The registered tests run first under the same 300 s deadline, so they lose no budget.

## 2. Sampling change and the comparison

- `a1_sampling(stream, r)` returns (1.0, 1.0, 20, 'A1') for every name matching ^(TRAINED|FROZEN)_s\d+$ once r >= start_round, and the registered (0.7, 0.8, 20) otherwise and always for POSCTL/BASECTL.
- cmd_sample computes one value per stream, refuses if the arm streams of the round differ, prints `A1_SAMPLING ... rule=` per stream, and writes `sampling` into each samples.jsonl row and into sample_stats.json. cmd_loop samples all 6 streams in one call, so the refusal covers both arms.
- Per-sample seeds are unchanged and paired: stream_seed_tag gives 's<k>' to both TRAINED_s<k> and FROZEN_s<k>.
- Smoke CHECK_OK: R3 (1.0, 1.0, 20, 'A1') for both arms, R2 and CTL registered, INERT without the file, 2 malformed files refused.
- No metric definition changes: closure, closure_nd, climb, valid share, copy share and distinct matrices use the same code.

Decision rule (PREREG):
- G_k(10) = sum_c closure_c(10) for TRAINED_s<k> minus FROZEN_s<k>, and Gnd_k the same, both required >= M = max(2, D_F) in every seed.
- D_F is the FROZEN-vs-FROZEN spread at R.
- SHARPENING compares TRAINED with FROZEN at R. COLLAPSE compares the same seed's arms in the same round. NO_UPDATE reads only whether TRAINED's SFT sets are empty.

Every contrast is within-seed and same-round (or same-R cumulative over an identical sampling schedule). No rule compares rounds K..10 with rounds 1..K-1, or an arm with its own earlier rounds. So the switch is a shift common to both arms, not a TRAINED-vs-FROZEN confound.

- Under H0 the arms stay exchangeable round by round, and D_F is measured on the same mixed schedule.
- Caveat: fpr_sim (0.025 worst case) did not model a mid-study regime change. The symmetry argument still holds.
- Per-round tables across the switch should be read as two regimes, descriptively only.

## 3. Probe gate

- The rule is pre-registered in sec. 5 of the amendment, and the code matches it exactly: `ok = len(rows) == 3 and len(vs) == 3 and sum(x >= 3) >= 2 and min(vs) >= 0.42`.
- rows = A1_rows per stream from a1count. vs = tpl_valid_share = TRAIN template records with a valid best_d / TRAIN samples.
- No probe output exists yet on Quartz.
- The probe samples only FROZEN_s7, FROZEN_s8 and FROZEN_s9:
  - stream_adapter returns None (base model) for FROZEN.
  - Seed tags s7..s9 are unused by the study.
  - It runs in armT/a1_probe with ARMT_DIR set to that tree, its own AMENDMENT_A1.json {"start_round": 2}, state_1 = the snapshot closure (rb = d0), and the 12 TRAIN cells only.
  - It refuses if the study tree already has AMENDMENT_A1.json.
- No TRAINED stream exists in the probe, so no arm comparison can be read from it.
- Not yet tested: a1probe has never executed on GPU (the smoke is CPU only). A crash counts as a FAIL and leads to the fallback.

## 4. Weighted loss

- `ex.append((pi, ti, float(x.get('weight', 1.0))))` and `(loss * wt / ACCUM).backward()`.
- Registered rows carry no weight key: sft_rows adds `weight` only when the pick has one, which happens only in sft_select_a1. So registered rows get wt = 1.0 exactly, and the gradient is bit-identical.
- The other additions do not change training: the norm read under detach, the A1_INIT_LOAD log (init path only), the return value of the same clip_grad_norm_ call, and two extra log fields.
- AdamW weight_decay = 0.0, and lora_B starts at 0. So the a1gpucheck w0 test (weight 0.0 gives lora_B_norm == 0) is a valid proof that the weight reaches the gradient.
- A1_INIT_LOAD is logged only when an init adapter loads, so `len(loads) == 1` is correct for the w0 / w1 / w025-from-w1 sequence.
- a1gpucheck also tests a weighted row (0.25) on GPU, warm-started from w1.

## 5. CPU smoke

- smoke_a1_run1.log (Quartz h1, 18:43 ET) ran armt_a1.py sha 8039eb02b10a364966b9ea665c7b04d5b7f2fa23ecb783c65bd94f62575904d2.
- All CHECK_OK lines are present, as are SMOKE_ALL_PASS (registered) and SMOKE_A1_ALL_PASS.
- I did not re-run it (45 min, beyond the round-3 deadline). Instead I removed the 4 lines `import gc`, `import torch`, `gc.collect()` and `torch.cuda.empty_cache()` at lines 1729 to 1732 of the final file, and the result hashes to exactly 8039eb02b10a364966b9ea665c7b04d5b7f2fa23ecb783c65bd94f62575904d2.
- Those lines sit inside the loop body of cmd_a1gpucheck, which no CPU path calls, so the CPU path is identical.

## 6. Switch procedure (sec. 10)

The procedure is correct:
- STOP is checked only at the top of each round in cmd_loop, so the running round finishes in full.
- K = last ROUND_START + 1 (K = 4 if STOP is touched during round 3).
- qrun.sh takes `HOLDER RUN_NAME NEED_MB CPUS SCRIPT args`, refuses unless the holder is RUNNING, and takes a per-name LOCK. armT_loop_a1 is a new name.
- The registered relaunch with `--r-from K` is already proven: the live attempt is itself an r=2..10 relaunch.
- a1_cfg refuses any JSON other than exactly {"start_round": k} with k >= 2.

One step is missing from the command list: the HUNT_REGISTRY deviation entry. It must be written BEFORE the JSON. It is included below.

Open, non-blocking:
- The laptop armt.py is 7629128d..., not the registered file. Restore it with `cp a1_build/armt_registered.py armt.py`.
- Gap 1(b) above should be named in the registry entry as a stated residual.

## Exact command sequence for the lead (run from WSL; replace K with the number)

1. `timeout 60 ssh -n -o BatchMode=yes -o ControlPath=none quartz "touch /N/scratch/bsmensah/silo/hunt/armT/STOP"`
   Wait for `STOP file present: stopping before round K`, then `ARMT_LOOP_EXIT` in /N/scratch/bsmensah/leecomp/runs/armT_loop/attempt_20261105T230017Z/log.txt, and for that attempt's STATUS.json to read DONE.
2. `timeout 120 ssh -n -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh 12693135 armT_a1gpucheck 75000 8 /N/scratch/bsmensah/silo/hunt/armT/armt_a1.py a1gpucheck"`
   Wait until its STATUS.json reads DONE. Read `A1_GPUCHECK PASS|FAIL` in runs/armT_a1gpucheck/attempt_*/log.txt and armT/a1_gpucheck/A1_GPUCHECK.json.
3. Only if PASS: `timeout 120 ssh -n -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh 12693135 armT_a1probe 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt_a1.py a1probe"`
   Read `A1_PROBE_PASS|FAIL` in runs/armT_a1probe/attempt_*/log.txt and armT/a1_probe/A1_PROBE.json. Confirm `A1_SAMPLING stream=FROZEN_s7 r=2 temp=1.0 top_p=1.0 top_k=20 rule=A1` is in the log.
4. If either step FAILED (or crashed): do not switch.
   - `timeout 60 ssh -n -o BatchMode=yes -o ControlPath=none quartz "rm /N/scratch/bsmensah/silo/hunt/armT/STOP"`
   - `VERIFIED=C:/Users/bmens/NQ_local/records_hunt/armT/VERDICT_ARMT.md timeout 120 ssh -n -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh 12693135 armT_loop 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt.py loop --r-from K --r-to 10 --seeds 0,1,2"`
5. If both PASSED:
   - (a) Log A1 as a deviation in registry/HUNT_REGISTRY.md with the amendment sha f2bca6e2..., the armt_a1.py sha 5d7db6b8..., the probe result, and residual 1(b). Do this BEFORE round K's data exist.
   - (b) `timeout 60 ssh -n -o BatchMode=yes -o ControlPath=none quartz "cd /N/scratch/bsmensah/silo/hunt/armT && rm STOP && echo '{\"start_round\": K}' > AMENDMENT_A1.json && cat AMENDMENT_A1.json && sha256sum armt.py armt_a1.py"`. The cat must print exactly {"start_round": K}, and the shas must be 8fce8dad... and 5d7db6b8....
   - (c) `VERIFIED=C:/Users/bmens/NQ_local/records_hunt/armT/VERDICT_ARMT_A1.md timeout 120 ssh -n -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh 12693135 armT_loop_a1 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt_a1.py loop --r-from K --r-to 10 --seeds 0,1,2"`
   - (d) Check for these lever markers in runs/armT_loop_a1/attempt_*/log.txt at round K. If any arm lacks rule=A1 in round K, that round is LEVER_VOID for A1.
     - `META ... armt_sha=5d7db6b8...`
     - `A1_STATE ... "start_round": K`
     - six `A1_SAMPLING ... rule=A1` lines (FROZEN_s0..2, TRAINED_s0..2)
     - `SFT_RULE stream=TRAINED_s<k> r=K AMENDMENT_A1`
     - no `SFT_RULE stream=FROZEN`
