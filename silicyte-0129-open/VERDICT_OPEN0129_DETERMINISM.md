VERDICT: GO

# VERDICT_OPEN0129_DETERMINISM (independent verifier, 2026-11-05 ET)

## SCOPE

This GO covers one thing: the determinism step in BUILD_OPEN0129.md sec. 8. That step scores exp_n256 on RULER_49100 twice in ruler
mode and compares the two readings row by row.

It covers nothing else. VERDICT_OPEN0129.md stays NO-GO for the four seeds until the fixes are re-verified. This step reads no seed
data and trains nothing. It writes only into runs/DET/ and runs/det.log. The pending fixes (the reader's second axis, the XMIN
sidecar, and PREREG text) do not touch open0129.py, opengen.py or the rulers. The step therefore runs the same code that the seeds
will run.

## WHY GO

Checked in VERDICT_OPEN0129.md, item 6:
- Ruler mode with K = 1 and t = 0 loads CANON_AD = exp_n256 (open0129.py:141) and needs no round json.
- RULER_TAG=.rep writes ruler_0.rep.json (:147). The ruler process never overwrites a file (:148-149) and writes it atomically
  (:166-168).
- `read_open0129.py compare` checks tid, depth, v, c, exec and prog for every row. It prints the gate token, or exits 5
  (read_open0129.py:182-189).
- The md5 asserts on lib/, inputs/ and bootseed0128.py and the ruler sha check run at start-up, so a changed file exits 9 before
  any scoring.

**One fix to the BUILD line.** BUILD sec. 8 sends output to `.../open0129/runs/det.log`, but runs/ does not exist yet. The
`mkdir -p runs/DET` runs inside the srun step, after the login shell has already tried to open det.log, so the redirect would fail
and nothing would start. Create the directory first, as below.

## COMMAND (login node, lead only)

```
H=12694677
squeue -j $H -h -o "%T %N"            # must print RUNNING and the node
N=$(squeue -j $H -h -t R -o %N)
ssh -n $N 'nvidia-smi --query-gpu=memory.used --format=csv,noheader; nvidia-smi --query-compute-apps=pid --format=csv,noheader'   # expect < 1000 MiB and no pids
mkdir -p /N/scratch/bsmensah/silo/open0129/runs/DET
setsid nohup srun --jobid=$H --overlap -n1 -c 8 bash -c "cd /N/scratch/bsmensah/silo/open0129; source /N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh >/dev/null 2>&1; export PYTHONPATH=/N/scratch/bsmensah/arc26/fourth_law/pylib CUDA_VISIBLE_DEVICES=0 REACH_SPACED=0 && python -u open0129.py /N/scratch/bsmensah/silo/bootseed /N/scratch/bsmensah/arc26/fourth_law /N/scratch/bsmensah/silo/open0129 ruler runs/DET 1 0 && RULER_TAG=.rep python -u open0129.py /N/scratch/bsmensah/silo/bootseed /N/scratch/bsmensah/arc26/fourth_law /N/scratch/bsmensah/silo/open0129 ruler runs/DET 1 0 && python3 read_open0129.py compare runs/DET/ruler_0.json runs/DET/ruler_0.rep.json" > /N/scratch/bsmensah/silo/open0129/runs/det.log 2>&1 < /dev/null &
```

Expected run time is about 1.7 h: two passes of about 50 min each, plus two model loads.

## PASS CRITERION

runs/det.log must show all of the following:
- two lines of the form `RULER seed=1 t=0 d50=... nan=0`, each with nan=0;
- `RULER_DONE` twice;
- a final line exactly `RULER_DETERMINISM MATCH rows_equal 300 of 300`.

Each of these is a FAIL:
- `RULER_DETERMINISM MISMATCH` (exit 5);
- any `VOID_*` line (exit 9 or 6);
- nan > 0;
- a missing second RULER line.

On a FAIL, do not launch the seeds. PREREG sec. 7.1 makes the study VOID.

Two notes for the read:
- The two `d50=` values must be identical. This follows from rows_equal 300.
- Only the 60 to 80 solved rows can actually differ between the two passes. A failed beam's exec does not depend on its path, and
  its prog is None (VERDICT_OPEN0129.md item 6). That is enough for the property LEVEL needs.

Keep det.log. It is a gate file for `read_open0129.py read ... --final runs/det.log <audit log>`.
