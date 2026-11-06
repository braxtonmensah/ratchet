# BUILD: silicyte-0136 ONE-SHOT (d) amortisation

Builder, 2026-11-05 about 19:25 ET. All Python ran on the Quartz login node (nice 19). No GPU step has run, no Slurm job or step was
touched, no registered file was edited. Local dir = C:/Users/bmens/NQ_local/silicyte-funding/rsi_sprint/restart/oneshot0136/,
Quartz dir = /N/scratch/bsmensah/silo/oneshot0136/ (bytes equal; sha256 in SHA256SUMS.txt). Quartz-only outputs: logs/, out/
(empty), smoke_read/ (FAKE planted data for the reader smoke only), sim_oneshot0136.json.

## Files
| file | role |
|---|---|
| PRIOR_ART_ONESHOT0136.md | prior art for (d) and (b); no "first" claims |
| PREREG_ONESHOT0136_DRAFT.md | question, data, kill test, gates, power table, units caveat, verifier question |
| DESIGN_B_WEIGHTGEN0136.md | 1-page design for (b), ranked against (d) and (a); not built |
| oneshot0136.py | selftest (CPU) / score (GPU) / compare; imports silo/bootseed/lib read-only after md5 asserts |
| run_oneshot0136.sh | GPU wrapper, the env of ext/run_score_deep.sh; logs nvidia-smi at start and end |
| read_oneshot0136.py | registered read: gates, table, slopes, label, rho_hat (stdlib) |
| sim_oneshot0136.py | FP / power / MDE sim at 0128 noise (stdlib) |
| smoke_read0136.py | planted-effect smoke for the reader (writes only under a non-real root) |

## Byte and second map (physics floor)
- MEAS: 300 tasks, 26-37 per depth 1..10. One policy call = one ident.Scorer.logps = 1 head forward + 54 candidate batch on the
  KV cache; measured 0.124-0.183 s per call on shared H100s (14 stored A4 scorings).
- Searched B 4 at max 10: a failure costs 1 + 9 x 4 = 37 calls (1,998 exec); MEAS total about 7,500-9,200 calls (stored rows),
  1,126 s measured for FRONTIER_s2 P_3 (ctl_meas10). NOT re-scored: stored.
- One-shot B1: a failure costs 10 calls (540 exec). Upper bound 3,000 calls per policy; stub run 2,495 (8.32 per task). O0 rides
  the same memoised calls: B1 and O0 hold the same state unless O0's argmax op is invalid on a demo (then O0 stops), so O0 adds
  about 0 forwards (stub: 4,193 policy calls served by 2,495 forwards).
- Per policy: about 2,500-3,000 forwards x 0.13-0.18 s = 5.5-9 min. Per seed process: 11 policies + 2 B4 control prefixes
  (60 tasks, about 1,600 forwards each, 3.5-5 min) + load about 2 min = 70-105 min.
- Memory: Qwen3-8B bf16 about 16.4 GB + 11 adapters x 174.7 MB = 1.9 GB + a 54-row candidate batch on a short cache. Expected peak
  allocated about 19-21 GB; the process is capped at ONESHOT_MEM_FRAC 0.30 x 80 GB = 24 GB (set right after CUDA init) and logs
  max_memory_allocated and max_memory_reserved per policy and at the end. Needs a card with at least 25 GB free and NO trainer
  (not H1-H6, H8, H9, H10).
- Total: 44 policies + 8 control prefixes + 1 A/A repeat (about 8 min) = about 4.8-7 GPU-hours of shared-card occupancy.

## The constraint nobody uses
The registered beam at B 1 is NOT pure one-shot: every step it executes all 54 children and stops if any hits the target, so its
last step is free (a depth-d task needs d - 1 correct greedy picks). That is why O0 (no lookahead) is also measured, at no cost.

## CPU smoke (login node, logs/selftest_full2.out, 113 s): SELFTEST_OK
- lib md5 OK; bootseed0128.py c54e21d2 and score_deep.py c7fc4099 OK.
- MEAS rebuilt; (tid, depth) equals stored fixed_rows for 44 of 44 policies; recomputed d50 = summary.d50_fixed for 44 of 44.
- Adapter provenance: k = 2,3,4: wsum(P_t)[:12] equals the stored adapter_md5 / LEVER tag=P0 line for 33 of 33. s1 (legacy code,
  no stored md5; the first selftest run failed here, logs/selftest_full.out): now checked by the write order, mtime(P_t) =
  mtime(round_{t-1}.json) and < mtime(round_t.json), 10 of 10; P_0 canonical md5.
- Stub scorer on all 300 MEAS tasks: B1 + O0 repeat rows 300 of 300; first-expansion identity 26 of 26; O0 with an oracle policy
  solves 300 of 300; isotonic d50 recovers planted midpoints 1.5 / 3.0 / 4.6 / 7.2 as 1.500 / 3.000 / 4.556 / 7.222.
- Reader smoke (planted, smoke_read/): delta +0.15 -> AMORTISES + COMPOUNDING-CANDIDATE; delta -0.15 -> GAP_GROWS;
  delta 0 with B1 = 0.55 x S -> GAP_GROWS while log A_t is flat (the scale issue in PREREG sec. 7).
- Not tested on CPU: the real 8B scorer and the multi-adapter switching. GATE 5 (CONTROL_B4) tests both on GPU in every process.

## Power (sim_oneshot0136.py, logs/sim.out)
FP 0.048-0.057; MDE at 80% power 0.054-0.169 d50/round over rho 0-0.95 and one-shot noise x1-1.5 (table in PREREG sec. 6).

## GPU commands (the LEAD runs these after a verifier GO; builder ran none)
Pick an inference-only holder with >= 25 GB free (H12 = 12694679 had about 65 GB in use at 18:27, so it fits only after a step there
ends). One process per seed; chained on one card about 5-7 h, or split over two cards.

```
H=<inference-only holder>; O=/N/scratch/bsmensah/silo/oneshot0136
setsid nohup srun --jobid=$H --overlap -n1 -c 6 --cpu-bind=none bash -c "export ONESHOT_MEM_FRAC=0.30; bash $O/run_oneshot0136.sh score s1 && bash $O/run_oneshot0136.sh score s1 --ts 0-0 --tag rep --no_ctl && bash $O/run_oneshot0136.sh compare $O/out/s1/P_0.B1.json $O/out/s1/P_0.B1.rep.json && bash $O/run_oneshot0136.sh score FRONTIER_s2" > $O/logs/score_chainA.log 2>&1 < /dev/null &
setsid nohup srun --jobid=$H2 --overlap -n1 -c 6 --cpu-bind=none bash -c "export ONESHOT_MEM_FRAC=0.30; bash $O/run_oneshot0136.sh score FRONTIER_s3 && bash $O/run_oneshot0136.sh score FRONTIER_s4" > $O/logs/score_chainB.log 2>&1 < /dev/null &
```
(One card only: put all four `score` calls and the A/A in chain A.) Each `score` exits 5 on a CONTROL_B4 failure, 6 on an adapter
change or provenance mismatch, 7 on an identity failure, so `&&` stops the chain. Then, on the login node:
```
cd /N/scratch/bsmensah/silo/oneshot0136 && grep -E "CONTROL_B4|SCORE_DONE|DETERMINISM|peak_gb" logs/score_chain*.log && python3 -I read_oneshot0136.py | tee logs/READ_0136.txt
CPU_OK=1 python -I C:/Users/bmens/NQ_local/lane/lever_check.py <local copy of logs> ONESHOT="LEVER_ONESHOT run=\S+ t=\d+ B=1 max_steps=10 active=P_\d+"
```
