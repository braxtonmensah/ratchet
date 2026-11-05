VERDICT: GO

# VERDICT_A4_0128 (re-verification after the fixes, 2026-11-05 13:42 ET)

Supersedes the 09:40 ET NO-GO. Independent verifier. Read-only. The only actions on Quartz were login-node CPU checks, read-only
extend_0128.py pre / post calls without --apply, and the requested `continue_k.sh 2 12679725 --dry`. That dry run makes one short
srun pgrep probe step inside the holder. Nothing was moved, launched, cancelled, held or released.

## SCOPE

- Read ext/A4_FIXES.md, BUILD_A4_0128.md section 0, and the new read_0128_ext.py (953d97be), score_deep.py (c7fc4099),
  overlap_actual.py (0c6f3a1e), extend_0128.py (635d26e2), continue_k.sh (9754093a) and sim_late_takeoff_v2.js/.json.
- The registered files are unchanged: bootseed0128.py c54e21d2, run_bootseed0128.sh 42b5c2ac, bootseed.py ee33615f, run_seed.sh
  7fe29bac. The Quartz md5s equal the BUILD table.
- Live state at 13:40 ET:
  - s1: t_to 30 since 13:20, training round 11. No MEASURE_FIXED round 11 line yet.
  - FRONTIER_s2 / s3 / s4: at rounds 8 / 7 / 7.
  - GUIDE_s2 / GUIDE_s3: round 0 done, t_to 30.
  - ext/deep/ does not exist, so no deep reading has been made.

## WHY GO

All three blockers are fixed, and I re-checked each one independently.

1. **Shared pool.** There are now four per-seed pools. I recomputed their sha256 values: 39100 34a86653..., 39200 0beed047...,
   39300 c5d9f77e..., 39400 5e9a9184..., all equal to BUILD 0.1.
   - Each pool has 120 tasks, 6 at every depth 1..20, and tid // 1000003 = its pool seed. Every task re-verifies.
   - No pool shares an input with held.jsonl or with MEAS 29000.
   - All 10 pairs among 39000..39400 share 0 tids, 0 tasks and 0 inputs.
   - I checked every actual search_t.json row of every bootseed0128 run, GUIDE included: 13,500 data-pool and frontier tasks,
     0 / 0 / 0 hits against all four pools.
   - score_deep.py picks the pool from the run name, checks its sha (exit 9) and records pool_seed and pool_sha256 (:34-80, :168).
     The reader refuses a reading made on another pool (read_0128_ext.py:70-71).
   - My task-level sim with per-seed pools gives FP 0.039 to 0.041. The builder's v2 sim gives 0.035 to 0.039, and 0.062 for the
     shared contrast. The two agree.
2. **Loop ceiling.** R*_k is the first round with data-pool summary.d50 >= 9 (:168-171). A seed enters L only with R*_k >= 15
   and contiguous deep rounds 0..R*_k (:182-185). With K < 3 seeds the label is UNDERPOWERED-EXT (:233). The labels carry the
   wording "before the loop's 10-step search ceiling" (:39).
   - The builder's power under this design is 0.48 / 0.79 / 0.83 at m 1.05 / 1.1 / 1.2 from round 10, 0.16 / 0.31 / 0.45 from
     round 15, and 0.06 to 0.17 from round 20.
   - My earlier independent sim gave 0.48 / 0.76 / 0.90, 0.31 / 0.46 and 0.15. These agree within the expected differences
     (the builder adds task effects and a random ceiling between 10 and 11).
   - The exclusion uses the data pool, not the deep reading. Under the null, delta_k does not depend on g_k, so excluding fast
     seeds does not bias it.
3. **Critical value.** crit = T04[df], 2.605 at K = 4, printed with every read (:210-212). The data-dependent alpha rules are
   gone. v2 uses xorshift128+ seeded by splitmix64.

Other items:
- m_hat is replaced by the per-seed rate ratio, with a 95% t interval (:193-194, :220-224).
- Deep LEVEL uses contiguous rounds only (:196-198).
- --final refuses a label unless the gates show DETERMINISM MATCH, CONTROL PASS, POST OK for every run, and an overlap
  ACTUAL_TOTAL of zero (:85-97, :225-230).
- The contamination rule now voids all t > u. overlap_actual.py checks every round against all four pools (:20-50).

## CONTINUATION

**continue_k.sh, read against bootseed0128.py.**
- The steps match the mechanics I verified at 09:40: md5s, then holder RUNNING and owned by us, then no live process matching
  "bootseed0128.py .*runs/FRONTIER_sk " (the python cmdline is `.../bootseed0128.py D FL .../runs/FRONTIER_sk FRONTIER k 10`, so
  the pattern matches, and GUIDE_sk does not), then extend pre, then --apply, then a check that the move happened, then the launch
  `srun --overlap -n1 -c 24 run_bootseed0128.sh FRONTIER k 30`.
- The printed expectations are right: data_seed 9000 + 100k + 10 (bootseed0128.py:93), front_seed 19000 + 100k + 10 (:97), and
  torch_seed 1000k + 11 (:451).

**Dry run on seed 2 at 13:40 ET.** The md5 checks passed (OK x3) and the holder check passed (`OK holder 12679725 RUNNING bsmensah
maxSELFFT_H1`). Then: `STOP: a bootseed0128 process for FRONTIER_s2 is still running in holder 12679725`, rc 1. The guard stopped
it as it should, because seed 2 is mid round 9.

**extend_0128.py pre without --apply.** On FRONTIER_s2 / s3 / s4 it printed "PRE FAIL: round 10 not reached yet; nothing moved",
rc 2 (the new early exit, :76-79). extend post on s1 printed POST OK: rounds 0..10 cumulative counts equal train_examples, and
own.jsonl has 7,456 rows = 7,712 - 256.

**Weakness, not blocking.** If the srun pgrep probe itself fails, the script treats that as "no process" (:31). extend pre's log
check catches this case: it needs BOOTSEED_DONE and then SEED_EXIT rc=0 after the last META.

## AUTOMATIC CONTINUATION INSIDE THE HOLDER

**Do NOT run continue_k.sh without --dry inside an srun step.** Its launch line (:45) backgrounds `setsid nohup srun ... &` as a
child of the step. setsid does not leave the step's cgroup. When continue_k.sh exits, the step ends, and Slurm kills every process
in that cgroup, including the nested srun client. That takes the continued seed step down with it.

**Do NOT use -c 1.** The step that runs the seed gets this step's CPU TRES. The current seed step 12679725.1 has cpu=24, gpu=1,
mem 180G. A -c 1 step would run rounds 10..30 under different resources than rounds 0..9.

**SAFE form.** One --overlap -c 24 step per seed. It sleeps until its seed's SEED_EXIT line appears, runs continue_k.sh --dry
(all checks), applies the move with extend_0128.py, and then **execs** run_bootseed0128.sh inside the same step, so nothing
nested is left to be killed.
- The waiter's own command line does not contain "bootseed0128.py", so the pgrep guard cannot match itself.
- Any failure exits and leaves the seed stopped, with nothing moved or with the move logged.
- A second, manual continue_k.sh would refuse: rounds 0..10 would no longer be complete, and extend's archive assert blocks a
  second move.

Launch from the login node (lead), once per seed. For k = 2:

```
setsid nohup srun --jobid=12679725 --overlap -n1 -c 24 bash -c 'K=2; H=12679725; D=/N/scratch/bsmensah/silo/bootseed; R=FRONTIER_s$K; LOG=$D/runs/$R.log; until grep -q "^SEED_EXIT arm=FRONTIER seed=$K " $LOG; do sleep 300; done; sleep 60; bash $D/ext/continue_k.sh $K $H --dry || exit 1; source /N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh >/dev/null 2>&1; python -I $D/ext/extend_0128.py pre $R $LOG --apply >> $D/ext/continue_s$K.log 2>&1 || exit 1; for f in round_10 search_10 tel_10; do [ -f $D/ext/archive/$R/$f.scored_only.json ] && [ ! -f $D/runs/$R/$f.json ] || exit 1; done; echo "=== continuation $R t_to 30 $(date -Is) (auto waiter)" >> $LOG; exec bash $D/code/run_bootseed0128.sh FRONTIER $K 30 >> $LOG 2>&1' > /N/scratch/bsmensah/silo/bootseed/ext/waiter_s2.log 2>&1 < /dev/null &
```

For k = 3, replace `K=2; H=12679725` with `K=3; H=12679920`, the --jobid with 12679920, and the output file with waiter_s3.log.
For k = 4, use `K=4; H=12679921`, --jobid 12679921 and waiter_s4.log.

After round_10.json reappears, run `python -I $D/ext/extend_0128.py post FRONTIER_sk` and confirm POST OK. That run also confirms
that the redone round-10 MEAS rows equal the archived ones. The waiter's srun client lives on the login node, the same as every
seed launch so far.

## CONDITIONS ON THE GO (they do not change the code)

1. **Register now.** PREREG_BOOTSEED_V1.md (last modified 09:13) still holds the old A4 draft: pool 39000, the old power, the alpha
   rules and NO-TAKEOFF-BY-R. Register A4 with BUILD section 0 and A4_FIXES.md as its text: the four pool shas, R*_k, the R*_k >= 15
   and K >= 3 rules, crit 2.605, the gates, the rate ratio, the contamination rule, and the v2 power table with its stated blind spot
   (a takeoff that starts after about round 15 is mostly invisible).
   - Do this BEFORE anyone reads s1's round-11 output. bootseed.py prints MEASURE_FIXED round 11 after the data-pool and MEAS solves,
     which I expect at about 13:55 to 14:15 ET.
   - Seed 2's round 11 comes after about 17:00 ET.
2. **Find GPU time for deep scoring.** H5 12687462 and H6 12688122 now run GUIDE_s2 / GUIDE_s3, so no free GPU is left. Deep scoring
   needs about 124 FRONTIER policies plus about 62 GUIDE policies at about 18 min each, about 56 GPU-hours. H7 12693135 is pending,
   with an estimated start of Nov 6 11:21 ET. The adapters persist, so scoring can lag the seeds, but the A4.4 read is due Nov 10
   23:59 ET.
3. **GPU steps 1 and 2 first.** Run them before any retro-scoring: determinism (DETERMINISM MATCH) and the positive control
   (CONTROL PASS), on a seed-2 policy with pool 39200.
4. Seed 1 runs t_to 30, so it also trains round 30 (about 2.3 h wasted). It is harmless.
