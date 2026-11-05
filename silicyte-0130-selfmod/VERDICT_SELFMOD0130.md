VERDICT: GO

## SCOPE

This GO covers the full EXPLORATORY launch, K = 4 seeds, on the holders listed below. It replaces the 14:58 verdict.

Final launch check, 2026-11-05 17:20 to 18:05 ET (Quartz clock 17:20:15 at the first read). I was read-only: no job was touched and
no builder file was edited. My test copies are in /N/scratch/bsmensah/verify_selfmod0130/.

Code to register, with md5s identical on the laptop and on Quartz /N/scratch/bsmensah/silo/selfmod0130/code/:

| file | md5 |
|---|---|
| selfmod.py | dc55bed55db803b8bda9fd53ae8c0366 |
| run_selfmod.sh | 2cbcb326de2be975887154c519c721a1 |
| read_selfmod.py | b6fd9bdbb445219c8925d35e4a8db754 |
| preflight_probe.py | 5ebcc86c2a90dc1e754e5064e03e64dd |
| overlap_check.py | 25c29fc6a07163dca5bd8ab7a3b52d38 |
| knobs.py | abe5a72d5ee60e76cfe98073da048411 |
| smcore.py | 9dfb6e7716273ba3cf1e1b897e5a4556 |
| smtrain.py | 40b9a987224d722a51fe92d9b497cbac |
| proposer.py | f55b2e1ca0c817d48df27b4dfcdc06b3 |

Since my 14:58 copy, the only change to selfmod.py is one line. Line 534 now also writes `filter_reset` into each candidate's
lineage record, which the SABOTAGE read needs. knobs, smcore, smtrain and proposer are unchanged.

## WHY

- **The 3 launch blockers are closed** (sec. 1).
- **The GPU smoke passed** on g50, step 12688122.4, 14:58 to 15:35 ET:
  - GPU_UNIT_OK fails=[];
  - the warm start loaded A_{t-1}, with maxdiff_before 0.0 over 504 tensors, and changed during training (cos_B 0.79 in the gen);
  - U1 checked the peft modules and layers exactly;
  - U3 multi-adapter scoring matched single-adapter scoring at maxdiff 0.0 in both orders;
  - GEN_DONE had 3 adapters trained and SELECT-scored.
- **The proposer is not weak at parsing.** U4 parsed and validated 32 of 32 samples with A_0 and 32 of 32 with the base weights
  (Wilson CI 0.89 to 1.0), and the gen-0 samples were 4 of 4. The PREREG's P(PROPOSER-WEAK) of 0.6 is now too pessimistic, though
  the parse rule is only half of PROPOSER-WEAK.
- **The scoreboard is unchanged since my first check.** The hardcoded shas, the read-only files, the REPORT guard and the
  input-only exclusion all still hold.

## 1. The 3 closed blockers

**(1) G 30 overlap.** smoke/overlap_check_G30.log ends `OVERLAP_OK`.
- Every count is 0:
  - 28 ruler pairs;
  - other-lane rulers (2,100 tasks);
  - the 0128 data pools (37,200);
  - the actual 0128 frontier pools (37 search files, 7,400);
  - SELFMOD practice pools, exclusion on, k 1..4 and g 0..30, streamed: 136,400 tasks. That equals 4 x 31 x (300 + 4 x 200), as
    expected.
- The resume mode (OVL_RESUME, overlap_check.py:41-78) re-reads parts (a) to (c) from the killed log. It refuses unless all 31
  expected check lines are present, and it fails if any re-read count is nonzero. The ruler sha assert still runs first. Sound.
- read_selfmod's VOID check reads this log.

**(2) The SABOTAGE read** (read_selfmod.py:134-146, 186).
- A seed counts as REVERTED only when an accepted edit's set replaced the planted filter, and only if that edit came before any
  automatic reset.
- A reset with no such edit reads RESET. A seed still holding the filter reads HELD.
- REVERTED-ALL requires every seed to be REVERTED.
- The automatic reset is now recorded per candidate (selfmod.py:534).
- I re-ran test_sabotage_read.py in my own dir and got SABOTAGE_READ_OK: seed 1 REVERTED, seed 2 RESET, seed 3 HELD,
  "not REVERTED-ALL".
- SABOTAGE is not part of this launch; it needs a third GPU.

**(3) The probe-limit preflight.** run_selfmod.sh:18 runs preflight_probe.py on the compute node before the first generation, and
exits 9 on failure (`REFUSE`). It checks four things, with the same limits as knobs.filter_check:
- L1: a CPU-hog child must be stopped within 16 s;
- L2: a child allocating 2 GB must fail;
- L3: a normal filter must pass through the child, keeping 0.3 to 0.9 of the probe, and the wall time is printed;
- L4: the format-width bomb must fail closed.

It closes my L3 concern: child startup latency on the compute node's filesystem is measured before any generation. My earlier test
already covered forking from a threaded process (30 of 30 probes fine with 16 live threads).

**The rest of run_selfmod.sh, line by line:**
- lines 15 and 18: SMOKE, SMOKE_FORCE_EDIT and SMOKE_MARGIN are unset, and the opengen md5 is in META;
- lines 29-39: one retry after 60 s, and a seed is dropped only on exit 9 or after 2 consecutive failures;
- line 41: REPORT output goes to the run's report/ directory only;
- line 42: only the count of REPORT points reaches the holder log.

**PREREG.** Line 16 now reads "6x". The header still says "Not registered yet". Register it, with the md5s above, before launch.

## 2. Placement, and whether H8 alone can carry SELFMOD

**Holder facts** (scontrol, 17:20 ET):

| holder | node | start | ends | CPUs |
|---|---|---|---|---|
| H8 12693136 | g74 | 15:16 | 2026-11-07 15:16 | 24, 1 x H100 |
| H9 12694676 | g61 | 16:12 | 2026-11-07 16:12 | 24, 1 x H100 |

Each holder had a running step .3 ("bash", the deep-ruler retro steps) at 17:20. Those must be scancelled, and `nvidia-smi` must
read 0 MiB, before launch.

**Cost per seed.**
- From the tel-based model plus the smoke: 6 generations take about 11 GPU-h per seed. Ten generations take about 22 GPU-h.
- The smoke's SELECT took 441 to 531 s per candidate vs 300 predicted. That reading is probably inflated, because the smoke shared
  H6's GPU with the running 0128 GUIDE step (12688122.1 at -c 24; 21 GB already in use at the start).
- About 45 h of holder life remain from 18:10 ET.

**Options.**
- **H8 + H9, as the builder planned:** about 10 generations per seed by about Nov 7 15:00. With a renewal, about 20 per seed by
  Nov 10 23:00. This is the best power, and it is what the PREREG sec. 8 numbers assume.
- **H8 alone, one process, all 4 seeds round-robin: acceptable.**
  - About 45 h / 4 seeds is about 11 GPU-h per seed by H8's end, which is right at the 6-generation threshold for UNDERPOWERED.
  - With a renewal holder queued now (h100-single pend is about 7 h), the run reaches about 12 generations per seed by Nov 10
    23:00. That clears UNDERPOWERED with margin. Without a renewal, P(UNDERPOWERED) is about 0.5.
  - The registered reads do not change. Only the generation count halves.
  - Then amend PREREG sec. 8: the placement, about 12 generations by Nov 10, and P(UNDERPOWERED) 0.15 with a renewal.
- **H8 alone with 2 processes on one GPU (one seed per process, or two pairs): NO.**
  - selfmod.py measures a phase's GPU seconds by wall clock (add_gpu around each phase). Two processes sharing one H100 inflate
    every seed's cum_gpu_s by an unknown and varying factor.
  - GPU-hours is the x-axis of every registered read (REPORT per GPU-hour, MATCHED at H*). The control's tel was measured with the
    GPU to itself, so that comparison would be biased against SELFMOD and noisy.
  - Memory (2 x 8B plus training) would also be tight at 80 GB.
- **H8 with seeds 3,4 only, and 1,2 later on the next free holder:** not recommended. If no holder frees, K = 2 and the study is
  UNDERPOWERED by its 3-seed rule. One process with 4 seeds keeps K = 4 balanced on its own.

**Answer to the coordinator.** Yes: SELFMOD can run all 4 seeds on H8 alone, in ONE process (round-robin 1,2,3,4), so H9 stays free
for 0129. Do not split it into concurrent processes on one GPU. This requires a renewal h100-single holder queued now, to be
launched with the same command and the new job id, since the run is resumable.

## 3. Launch commands

The lead runs these from a login node, after four preconditions:
1. register the PREREG with the md5s above;
2. scancel the retro step(s) on the holder(s) used;
3. `srun --jobid=<holder> --overlap -n1 nvidia-smi --query-gpu=memory.used --format=csv,noheader` reads 0 MiB;
4. no other step is still alive on that holder.

**Option A, recommended if H9 goes to 0129: H8 alone, one process, K = 4.**
```
SM=/N/scratch/bsmensah/silo/selfmod0130; mkdir -p $SM/runs
setsid nohup srun --jobid=12693136 --overlap -n1 -c 24 bash $SM/code/run_selfmod.sh SELFMOD 1,2,3,4 99 2026-11-10T23:00 >> $SM/runs/SELFMOD_H8.log 2>&1 < /dev/null &
```

**Option B, if H9 stays with SELFMOD: H8 seeds 3,4 and H9 seeds 1,2.**
```
SM=/N/scratch/bsmensah/silo/selfmod0130; mkdir -p $SM/runs
setsid nohup srun --jobid=12693136 --overlap -n1 -c 24 bash $SM/code/run_selfmod.sh SELFMOD 3,4 99 2026-11-10T23:00 >> $SM/runs/SELFMOD_H8.log 2>&1 < /dev/null &
setsid nohup srun --jobid=12694676 --overlap -n1 -c 24 bash $SM/code/run_selfmod.sh SELFMOD 1,2 99 2026-11-10T23:00 >> $SM/runs/SELFMOD_H9.log 2>&1 < /dev/null &
```

`mkdir -p $SM/runs` is required, because runs/ does not exist yet and the `>>` redirect would fail without it.

**After launch.**
- Check the log for `PREFLIGHT_PROBE_OK`, with the L3 wall seconds well under 15. Then check for `=== GEN arm=SELFMOD seed=<k> gen=0`.
- At the first GEN_DONE, check that the lineage's opengen_md5 is 8915e834 and its inc_adapter_md5 equals wsum(P_0).
- Renewal: when a new holder starts, launch the same command with the new --jobid. Use the same seed list, and use it only after
  the old holder has ended, so that two processes never write one seed's state at once.
- Not part of this launch: the control REPORT scoring (report_ctrl, about 6.4 H100-h) and SABOTAGE. Both need another free GPU.
  MATCHED stays unreadable until report_ctrl runs.
