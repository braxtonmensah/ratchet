# BUILD silicyte-0138 ALPHA (builder state, 2026-11-05 ET)

Laptop C:/Users/bmens/NQ_local/silicyte-funding/rsi_sprint/restart/alpha0138/ = Quartz /N/scratch/bsmensah/silo/alpha0138/.
No GPU job was submitted, cancelled, held or released; no srun; no process touched that this builder did not start. All Python ran
on the Quartz login node (system python3 3.6.8; the token probe used the venv's `tokenizers` only).

## Files
| file | role |
|---|---|
| alpha0138.py | harness: snapshot, plan, selftest, run CARD, lossprep, read |
| run_alpha0138.sh | GPU launcher, same env as bootseed/code/run_bootseed0128.sh (needed for control C1) |
| PREREG_ALPHA0138_DRAFT.md | prereg draft for the verifier |
| lever_check.py | copy of NQ_local/lane/lever_check.py |
| pool/POOL.jsonl, pool/POOL_META.json (Quartz only) | the one pool snapshot, sha256 da60787e3ca0118903bd11f7330745297223784edfb2d0cd73ff8ce0fe5687fb |
| logs/plan3.out, logs/selftest3.out, logs/probe_tok.out (Quartz) | CPU evidence |
sha256 of every file: SHA256SUMS.txt (laptop and Quartz compared byte for byte, see the end).

## Findings while building (read the code / map every byte)
1. **0128's hindsight rows are malformed.** bootseed0128.py:149 stores hend = [list(x) for x in state]; frontier_examples puts it in
   tgt, so reachlaw.policy_prompt renders each hindsight target as "['A', 'C', 'G', ...]". 4,092 of the 8,440 pool rows (48.5%; the
   same in FRONTIER_s3), a format the test prompt never has. Token cost: hindsight prompts mean 970 tokens (max 1,395) vs 434 (max
   544) for the rest; the same rows with string targets mean 428. Because nearly every batch of 16 holds a hindsight row, 0128's
   batches pad to p50 1,201 tokens instead of about 508: training spends about 2.4x the tokens it needs. Lever R3 fixes the format.
2. **The registered trainer cannot fit a 0.35 cap.** reachlaw.train (bs 16) computes full-vocabulary logits and HF's loss upcasts
   them to fp32: 22,320 tokens x 151,936 vocab = 6.8 GB bf16 + 13.6 GB fp32 + 13.6 GB saved log-softmax (+ grads) on 16.4 GB of
   weights, about 45-55 GB peak for batches with a hindsight row (matches the 71 GB the uncapped 0128 trainer reserves), about
   30-36 GB for string-only batches (R3, R4, R4S, R4C, R3N). So the harness uses two caps: ALPHA_TRAIN_FRAC (default 0.65, training)
   and ALPHA_MEM_FRAC (default 0.30, scoring; 0136 measured the scorer at 19-21 GB), switched between phases with
   set_per_process_memory_fraction after empty_cache. These are ESTIMATES: the SMOKE card measures the real training peak in about
   3 min. If the lead must keep 0.35 for training, the only registered-recipe-preserving option is a card with no neighbour during
   the train phase; changing bs or chunking the loss would change the recipe (needs a verifier amendment).
3. Labels are canonical: 8,440 of 8,440 pool rows carry the first op in OPN order producing their next state (bootllm.beam's `seen`
   rule), so observationally equivalent ops add nothing as extra targets. R2 adds only reordering labels (mean 1.45 per state).
4. MEAS: 0 pool rows share a MEAS input or tid; 325 pool targets equal some MEAS output string (0128 excludes by inputs only;
   telemetry).
5. Speed (stored): 0.1226 s per policy forward (FRONTIER_s2 rounds 1-10, 212,466 forwards); train_s = 30.5 + 0.2497 n.
   One full MEAS B 4 score = 7,000-8,300 forwards = 14-17 min, not 40.

## Validation done on CPU (logs/selftest3.out)
- The snapshot reproduces 0128's own order_md5 for all 11 FRONTIER_s2 fits r0..r10: the pool and the C1 rebuild are 0128's exact
  training sequence.
- Visit-order identity: for R0, R1, R1E, R2, R3, R3N, R4, R4C the file written makes reachlaw's Random(0) shuffle visit exactly the
  intended rows; stub adapters equal the md5 of the intended visit prefix; nested checkpoint = fresh fit (stub).
- R3 targets are strings; R4 targets equal the stored path executed m steps.
- Full run -> read path on stub fits (all recipes, C1, C2, SMOKE_S); a second run is a no-op (resume).
- In-loop alpha recomputed: s1 0.1626, s2 0.1923, s3 0.1425, s4 0.2030 = loop_physics.py exactly.
- Planted alpha through the real reader (4 levers, R1 effective, 2 seeds, fit noise 0.064, 60 sims): PASS 0 / 3 / 13 / 23 of 60 at
  true ratio 1.0 / 1.5 / 2.0 / 2.6; CI coverage 58-60 of 60. The reader is valid but conservative and UNDERPOWERED at 2 seeds
  (PREREG sec. 5 gives the verifier two fixes). Stub C1 FAIL is expected (stub scorer); C2 nested = fresh PASS on stubs.
- After the format rule (levers vs R_fix), logs/selftest6.out: PASS 0 / 0 / 6 / 26 of 60 at true ratio 1.0 / 1.5 / 2.0 / 2.6; coverage 57-60; SELFTEST_OK, code md5 98809da1118bd4cf410b91f94ef76ccd.
- Cost after the format rule (plan6.out): S1 5.16, S2 4.79, tiers 1 + 2 16.75 GPU-h; smallest R1 + R2 screen (MIN1 + MIN2, now with
  R_fix as baseline) 6.90 GPU-h.
- Final selftest: logs/selftest6.out (SELFTEST_OK line and code md5 in that log).

## Coordinator inputs folded in (11/05)
- FORMAT RULE (33de7d5): R0 and C1 as run; R_fix (= R3) is LEVER 1, read against R0; R1, R1E, R1L, R2 now use string targets like
  R3N, R4, R4S, R4C, and every lever except R_fix is read against R_fix. Selftest asserts it (R0 and C1 contain list targets, all
  other recipes none, R3 = R0 with joined targets row for row). MIN cards now carry R_fix (R1 and R2 need it as baseline).
- alpha per depth band (all, d1-4, d5-10) and d x alpha_d per depth for every recipe; PASS needs the d5-10 ratio CI above 1.
- R4 hindsight at every distance and R4C (compute-matched); R4S short hops (m <= 3) ranked FIRST (ratchet 71a4a63); alpha per
  remaining distance k (e_k = 1 - s_k / s_{k-1}) and near / far bands reported. Stored cross-check (plan3.out): in-loop k2 0.651,
  k3 0.278, k4 0.206 vs the ratchet's 0.637 / 0.294 / 0.202. Single far k are noisy (k5 -0.08, k6 0.91); use the bands.
- Subgoal state prediction at test time: not buildable with the registered trainer and beam (both rank 54 op names). Hook only.

## Cost (plan3.out, solo-card speed: 0.1226 s/forward, 30.5 s + 0.2497 s/row, x 0.42 per row for string-target recipes)
| card | content | GPU-h |
|---|---|---|
| SMOKE | training peak, 2 x 64 longest rows | 0.02 |
| S1 | C1 + R0_s1 (pass to 8192, ckpts 256..8192) + R4S R4 R3 R1 R2 at 256, 2048 | 5.39 |
| S2 | same, seed 2, no C1 | 5.02 |
| T2S1 / T2S2 | R1E R3N R4C, C2, R0 512..8192 scores | 3.67 / 3.31 |
| MIN1 + MIN2 | smallest screen deciding R1 and R2 only (C1, R0, R1, R2; 2 seeds) | 3.18 + 2.81 = 5.98 |
| tier 1 + 2 | S1 S2 T2S1 T2S2 | 17.39 |
Scoring is 70% of the cost (13-14 min per policy on 300 tasks). Sharing a card slows every tenant; these are occupancy-free numbers.

## Memory (ESTIMATES, unmeasured; the SMOKE card measures them)
Training: about 45-55 GB peak on 0128-format rows (R0, R1, R2, C1), about 30-36 GB on string-target rows. Scoring: 19-21 GB (0136).
Defaults: ALPHA_TRAIN_FRAC 0.65 (52 GB), ALPHA_MEM_FRAC 0.30 (24 GB). The process refuses to start without cap + 1 GB free, and
refuses if a bootseed0128.py process is on the card. A training OOM prints VOID_OOM and exits 10.

## Launch (the LEAD runs these after a verifier GO; the builder ran none)
```
H=<holder with one card having >= 53 GB free and no 0128 trainer>; O=/N/scratch/bsmensah/silo/alpha0138
srun --jobid=$H --overlap -n1 -c 6 --cpu-bind=none bash $O/run_alpha0138.sh run SMOKE > $O/logs/server_SMOKE.log 2>&1; grep -E "^MEM|VOID_OOM" $O/logs/server_SMOKE.log
setsid nohup srun --jobid=$H --overlap -n1 -c 6 --cpu-bind=none bash $O/run_alpha0138.sh run S1 > $O/logs/server_S1_C1_R0_R4S_R4_R3_R1_R2.log 2>&1 < /dev/null &
setsid nohup srun --jobid=$H2 --overlap -n1 -c 6 --cpu-bind=none bash $O/run_alpha0138.sh run S2 > $O/logs/server_S2_R0_R4S_R4_R3_R1_R2.log 2>&1 < /dev/null &
```
Then on the login node: `cd $O && python3 -I alpha0138.py read | tee logs/READ_0138.txt`, and on a local copy of logs/:
`CPU_OK=1 python -I lever_check.py <logs> R0="LEVER_ALPHA recipe=R0 " R4S="LEVER_ALPHA recipe=R4S " R4="LEVER_ALPHA recipe=R4 "
R3="LEVER_ALPHA recipe=R3 " R1="LEVER_ALPHA recipe=R1 " R2="LEVER_ALPHA recipe=R2 " C1="LEVER_C1 t=0 order_md5=546cc3a2dc9a expected=546cc3a2dc9a OK"`.
If ALPHA_TRAIN_FRAC must differ, prefix `ALPHA_TRAIN_FRAC=<f>` inside the bash -c. Every card is resumable (re-run the same line).
