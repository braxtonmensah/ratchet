VERDICT: GO

# VERDICT_OPEN0129 (re-verification for the seed launch; independent verifier, 2026-11-05 16:56 to 17:2x ET)

Supersedes the NO-GO of 15:0x ET. The determinism-step GO (VERDICT_OPEN0129_DETERMINISM.md) is unchanged.

## SCOPE

This review was read-only. I read:
- OPEN0129_FIXES.md;
- the revised PREREG_OPEN0129_DRAFT.md (sha256 b7fe10f0..., equal to FIXES) and BUILD_OPEN0129.md (sha256 949adea5..., equal to FIXES);
- read_open0129.py (new md5 7fa9481c), freeze_xmin.py (45d47620) and the frozen XMIN files.

Laptop and Quartz bytes are equal. The loop is unchanged on Quartz: open0129.py 4e46988a, opengen.py 8915e834, run_open0129.sh
600bf85d, build_ruler.py e756e9bc, and the four RULER sha256s and RULER_SHA256.json d1d1f3e1.

My own checks ran at nice 19 in /N/scratch/bsmensah/verify0129/, each a bounded command under 590 s:
- vreader.py and vreader2.py: an XMIN recomputation, plus synthetic runs fed to the real read_open0129.py;
- vsim5.js: the two-axis sim, my own implementation, 2,000 reps of 4 seeds per cell.

I launched, cancelled, held and released nothing. I did not touch runs/DET or det.log.

## WHY GO

Every item of the NO-GO is fixed, and I re-checked each one myself:
- **The second axis.** The XMIN values match my own recomputation exactly. The reader applies the two-axis rule exactly as the PREREG
  states it.
- **The synthetic reader test.** On the real reader it gives the expected labels and the expected false-positive rate.
- **The sim.** My independent two-axis sim keeps the false-positive rate at or below 0.041 under both truths, with no loss of power.
- **The text.** Every fix 3 text item is in the PREREG.

The seeds may launch once three gates have passed, in this order:
1. det.log shows the MATCH line (it was still in pass 1 at 17:19 ET);
2. the PREREG is registered (below);
3. the holder's GPU is free.

## EVIDENCE BY NO-GO ITEM

**Fix 1a. XMIN frozen.**
- The frozen/RULER_<s>_XMIN.json sha256s are:
  - 49100 d9017c43...
  - 49200 9fa48b03...
  - 49300 4e45b7d7...
  - 49400 48039fce...
- The index frozen/RULER_SHA256_XMIN.json is 80b45abb..., equal to PREREG secs. 4 lines 50-52.
- I recomputed reduce_ub(task, max_iter=1000), ten times the builder's cap, for every ruler task. The result is 300 / 300 equal in all
  four rulers, with the same tid set. Every value lies in 1..depth, and each file's sha equals its index entry. So max_iter 100 is
  truly uncapped.
- freeze_xmin.py sha-checks the rulers before it runs (:27) and refuses to overwrite (:37-43).
- File mtimes are 16:41 ET. runs/ held only DET, so no 0129 policy reading existed before the freeze.

**Fix 1b. The reader fits the XMIN axis.**
- read_open0129.py:99-106 loads XMIN, checks its sha, and exits 9 on a mismatch.
- :73-96 is bootllm.logistic_d50 verbatim. I diffed it by eye against lib/bootllm.py:65-88.
- :129 fits it on the same ruler rows, with depth replaced by XMIN[tid].
- :130-131 cut the common series when d50_x is None. That matches PREREG sec. 5 lines 67-68.

**Fix 1c. The two-axis rule.**
- :157-159 compute delta_x on the same h split.
- :170 gives t_x.
- :187 is TAKEOFF iff t > crit AND t_x > crit AND LEVEL. :189 is the same for SATURATING.
- Both t values are printed (:206-208).
- This matches PREREG sec. 5 lines 69-73 and sec. 7 lines 95-96.

**Fix 1c. Synthetic test on the real reader (my generator, not the builder's).**
- Setup: 4 fake seeds on the real rulers' tids, with true difficulty = nominal depth or XMIN, plus per-task N(0, 1.2), at beta 2.
  R = 30, with ruler_t.json and round json files laid out as the loop writes them.
- Single runs:
  - linear growth on a nominal truth: t 0.73, t_x -0.36, STEADY;
  - acceleration (onset at round 10, m 1.15) on a nominal truth: t 29.0, t_x 29.1, TAKEOFF;
  - the same acceleration on an XMIN truth: t 6.7, t_x 8.6, TAKEOFF.
- A gate file with "RULER_DETERMINISM MISMATCH" gives VOID in every case.
- Replicates of the null: XMIN truth, 2 TAKEOFF in 45 (0.044, consistent with the sim's 0.033 to 0.041); nominal truth, 0 TAKEOFF in
  24 (2 SATURATING).
- Two harness runs printed no label. I re-ran one (replicate 25) by hand: the reader printed STEADY. The blank lines came from my
  timeout and rmtree race, not from the reader.

**Fix 1d. The two-axis sim, re-run independently** (vsim5.js; tau 1.2 / beta 2.0, plus a tau 1.35 / beta 1.5 null):

| truth | cell | R 20 | R 25 | R 30 | R 35 | R 40 |
|---|---|---|---|---|---|---|
| XMIN | null, nominal-only rule | 0.047 | 0.049 | 0.062 | 0.068 | 0.077 |
| XMIN | null, two-axis (tau 1.2 / 1.35) | 0.036 / 0.041 | 0.033 / 0.038 | 0.040 / 0.037 | 0.033 / 0.035 | 0.030 / 0.027 |
| XMIN | onset 10, m 1.1, two-axis | 0.88 | 0.92 | 0.94 | 0.97 | 0.98 |
| XMIN | onset 15, m 1.1, two-axis | 0.21 | 0.85 | 0.91 | 0.95 | 0.98 |
| nominal | null, two-axis (tau 1.2 / 1.35) | 0.021 / 0.035 | 0.029 / 0.019 | 0.019 / 0.019 | 0.018 / 0.013 | 0.011 / 0.018 |
| nominal | onset 10, m 1.1, two-axis | 0.88 | 0.94 | 0.96 | 0.98 | 0.99 |
| nominal | onset 15, m 1.1, two-axis | 0.19 | 0.85 | 0.95 | 0.96 | 0.97 |

- My sim uses the mean XMIN per depth. The builder's draws each task's own XMIN, which spreads the warp across tasks.
- My two-axis false-positive rate under XMIN (0.027 to 0.041) is a little higher than the builder's 0.017 to 0.030. Both stay under
  alpha 0.04 + 1 SE.
- Power matches within 0.05. The builder's onset-15 rows are a little lower at R 25 to 30 (0.77 to 0.84 and 0.87 to 0.95); I get 0.85
  and 0.91 to 0.95.
- PREREG sec. 8a (lines 109-139) states the rule and the round-15 blind spot correctly.

**Fix 1e.** BUILD sec. 2 (lines 93-96) now says the capped bound hid the drop to 0.69 per depth over 20..40. Sec. 9.1 (line 301) points
to the two-axis rule.

**Fix 2.** The reader md5 7fa9481c is at PREREG line 80. The XMIN shas are at lines 50-52. The loop hashes at line 17 are unchanged.

**Fix 3. Text** (all present):
- (a) Fresh LoRA every round: line 21-22 and the "Scope of every label" paragraph, lines 101-105.
- (b) Scale: lines 55-57.
- (c) Frozen twin for LEVEL only, and the bridge is not a concurrent capped arm: lines 189-193.
- (d) Round-15 power: lines 137-138.
- (e) An audit hit voids the whole label: lines 91-93, matching the reader's --final gate (:178-184).

**Unchanged and still verified (items 2, 3, 5 and 6 of the first verdict):**
- The ceiling is removed at :199-203, :316, :320-329, :192-196.
- The rulers are clean: 0 overlap hits, including 272,000 tasks on a fresh 0129 pool grid and every 0128 search file.
- Ruler noise is 0.22 to 0.30 at n 10.
- Compute: realistic R is 25 to 35 per seed (BUILD sec. 10 now says so).
- The determinism command is the one in VERDICT_OPEN0129_DETERMINISM.md.

## THE A4 DEEP-RULER CONTROL ON H9

**The seed launch does not need to wait for it.**
- A4 is a separate study, of 0128's adapters on MEAS_DEEP_39x00.
- No 0129 rule, gate or file reads its result.
- The 0129 rulers share no task or input with MEAS_DEEP (0 hits, both directions).

The only coupling is the GPU. Do not start a 0129 seed on H9 while the A4 step holds that card. One seed already runs a loop scorer or
the trainer plus a ruler scorer (about 17 GB each, never run together yet). A third model on the same H100 risks an OOM and slows both
studies. Put the H9 seed in last, when nvidia-smi shows the card free.

## REGISTRATION (lead; must finish before the first seed starts)

```
cd /N/scratch/bsmensah/silo/open0129
ls runs/OPEN_s*/round_*.json 2>/dev/null | wc -l          # must print 0
sha256sum PREREG_OPEN0129_DRAFT.md                        # must be b7fe10f08c6e146ca9c81f19c0005af90f876d9cc15f75379cacde67a373c1a8
grep -c "^RULER_DETERMINISM MATCH rows_equal 300 of 300$" runs/det.log   # must print 1
test ! -e PREREG_OPEN0129.md && cp PREREG_OPEN0129_DRAFT.md PREREG_OPEN0129.md
printf '\n## REGISTRATION\n\nRegistered %s ET (Quartz clock, TZ America/New_York) by the lead. Text above is PREREG_OPEN0129_DRAFT.md byte for byte (sha256 b7fe10f08c6e146ca9c81f19c0005af90f876d9cc15f75379cacde67a373c1a8). Verifier: VERDICT_OPEN0129.md (GO, re-verification of 2026-11-05 17:2x ET) and VERDICT_OPEN0129_DETERMINISM.md. Determinism gate: runs/det.log RULER_DETERMINISM MATCH rows_equal 300 of 300. Code: open0129.py 4e46988a, opengen.py 8915e834, run_open0129.sh 600bf85d, read_open0129.py 7fa9481c. No runs/OPEN_s*/round_*.json existed at registration.\n' "$(TZ=America/New_York date '+%Y-%m-%d %H:%M')" >> PREREG_OPEN0129.md
chmod a-w PREREG_OPEN0129.md
sha256sum PREREG_OPEN0129.md | tee PREREG_OPEN0129.md.sha256
```

**Publish.**
- Copy PREREG_OPEN0129.md and its .sha256 to the laptop mirror
  (C:/Users/bmens/NQ_local/silicyte-funding/rsi_sprint/restart/open0129/), compare the sha there, and record the registration time
  and sha in the lane's lead log.
## SEED LAUNCH (lead; once per seed k = 1..4, one H100 each, only after REGISTRATION)

All four holders are RUNNING at 17:19 ET: H9 12694676 (g61), H10 12694677 (g56, running the DET step), H11 12694678 (g78) and H12
12694679 (g70).

Suggested order:
- k = 1 on H11 12694678;
- k = 2 on H12 12694679;
- k = 3 on H10 12694677, after det.log's MATCH line and the DET step's exit;
- k = 4 on H9 12694676, after the A4 step frees the card.

```
K=1; H=12694678          # then K=2 H=12694679; K=3 H=12694677; K=4 H=12694676
cd /N/scratch/bsmensah/silo/open0129
test -e PREREG_OPEN0129.md && sha256sum -c PREREG_OPEN0129.md.sha256          # registered and unchanged
grep -c "^RULER_DETERMINISM MATCH rows_equal 300 of 300$" runs/det.log         # must print 1
md5sum open0129.py opengen.py run_open0129.sh read_open0129.py                  # 4e46988a / 8915e834 / 600bf85d / 7fa9481c
squeue -j $H -h -o "%T %N"                                                      # RUNNING
N=$(squeue -j $H -h -t R -o %N)
ssh -n $N 'nvidia-smi --query-gpu=memory.used --format=csv,noheader; nvidia-smi --query-compute-apps=pid --format=csv,noheader'   # < 1000 MiB, no pids
setsid nohup srun --jobid=$H --overlap -n1 -c 24 bash /N/scratch/bsmensah/silo/open0129/run_open0129.sh $K 99 >> /N/scratch/bsmensah/silo/open0129/runs/OPEN_s$K.log 2>&1 < /dev/null &
```

**Expected in runs/OPEN_s$K.log**, as BUILD sec. 8 lists them:
- META, with code_md5 4e46988a;
- `START_CHECK {... "rows_equal_60": true, "nan": 0 ...}`;
- `P0_COPIED` for k >= 2;
- `RULER_SPAWN ... rounds=[0]`;
- `LEVER_POOL seed=K arm=OPEN t=0 D=10 max_steps=12 ... dp_excl_hits=0 front_excl_hits=0`;
- `LEVER ... n=<256 + rows>`;
- `ROUND 0 {...}`.

**Stop and report on any of these:**
- VOID_* (exit 7, 8 or 9);
- excl_hits > 0;
- a CUDA OOM.

For seed 1, watch round 0 for an OOM, because the ruler scorer and the trainer share the card. Relaunch in any later holder with the
same line; resume is per round.
