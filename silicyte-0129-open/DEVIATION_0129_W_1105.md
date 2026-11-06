# DEVIATION 1105-W (silicyte-0129 OPEN): training waits for the ruler process (OOM fix). Recorded before any 0129 round result

Written 2026-11-05 19:29 ET (PowerShell clock) by the Silicyte lead. No runs/OPEN_s*/round_*.json existed when it was made.

## What happened
- open0129.py starts the ruler scorer as a subprocess at the start of each round (ruler_kick, :271-287, called at :313) on the same
  H100, and does not wait for it before training.
- Seed 2 (H9, g61), round 0, 19:26 ET: "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 12.24 GiB ... this process has
  47.59 GiB memory in use. Process 1653588 has 21.15 GiB" (the ruler). SEED_EXIT rc=1. The trainer's live need is about 59 GB, so
  trainer plus ruler cannot share an 80 GB card. The independent verifier had flagged this risk before launch ("never run together yet").

## The change (new files; the registered open0129.py 4e46988a and run_open0129.sh 600bf85d are untouched)
- open0129_w.py (md5 76eac073): open0129.py plus two lines immediately before `trs, omd5, amd5 = train(`:
  `if RPROC[0] is not None: RPROC[0].wait(); print("RULER_WAIT_DONE t=... rc=...")`.
- run_open0129_w.sh (md5 da6c3475): run_open0129.sh pointing at open0129_w.py, reporting its own md5s in META.

## Why no registered quantity can change
The ruler scores a fixed, final P_t with a deterministic beam (det.log MATCH 300 of 300); the trainer's rows, seeds and settings are
unchanged; only the order in time of two processes changes. Rounds get longer by the ruler's tail when it outlasts the search. No rule,
ruler, reader, label, threshold or seed changes.

## Status
Independent verifier: VERDICT_OPEN0129_W.md (pending at the time of writing). Relaunch only after its first line reads "VERDICT: GO".
Seeds 1 and 3 run the original code; if they crash the same way they are relaunched on open0129_w.py; if they survive, the mix is
scheduling only.

## Verifier and relaunch (19:32 ET)
- VERDICT_OPEN0129_W.md: GO (independent verifier, md5 70a81a79): diffs are only the two wait lines and three script lines; the ruler
  branch is byte-identical; no code asserts its own md5; resume path for seed 2 is SEARCH 0 cached, RULER_WAIT_DONE, then train; no
  place remains where the trainer can overlap a ruler; worst-case peak is the trainer alone, about 60 of 79.18 GiB.
- Added caveat from the verifier: longer rounds (the ruler's tail when it outlasts the search) may mean fewer rounds finish by the
  deadline; R_k is cut at the deadline exactly as registered.
- Seed 2 relaunched on open0129_w.py at 19:32:33 on H9 12694676 (holder GPU 0 MiB, no step). Seed 1 is OOM-ing (verifier saw the
  warning at 19:29:47); seeds 1 and 3 move to open0129_w.py when they exit.
