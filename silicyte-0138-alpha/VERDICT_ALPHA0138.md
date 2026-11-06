VERDICT: GO

# VERDICT silicyte-0138 ALPHA (independent verifier, 2026-11-05 ET)

GO for the FIRST SCREEN only: SMOKE, then C1 (a gate), then FS1, FS2, FS3 (R0 + R_fix + R4S, seeds 1, 2, 3). Tier 2 is not
authorised by this verdict. Results are exploratory screens of one model and one trainer, not a compounding claim (PREREG sec. 0).
Evidence: Quartz /N/scratch/bsmensah/verify_alpha0138/logs/ (verify.out, stub_run.out, selftest_v.out, plan_v.out, power_*.out,
px_*.out). Code verified in my scratch, then copied to the study dir. No Slurm job or step was submitted, cancelled, held or released;
no srun; no process touched except the login-node Python I started (python3 -I -B, nice 19, timeouts).

## 1. Harness validity
- 0128 training order, rebuilt from the RAW files (seed256 + own_0..own_t, Random(2001 + t) pre-shuffle, reachlaw's Random(0)), not
  from the harness constants: 11 of 11 FRONTIER_s2 fits r0..r10 reproduce the order_md5 and n logged in runs/FRONTIER_s2.log
  (r0 546cc3a2dc9a n 780 ... r10 62d282b28a4c n 8440). The pool snapshot sha256 da60787e... is the one the harness loads.
- In-loop alpha with my own grid-MLE code: s1 0.1626, FRONTIER_s2 0.1923, FRONTIER_s3 0.1425, FRONTIER_s4 0.2030, mean 0.1751 sd
  0.0277 = ratchet silicyte-0137 exactly.
- Per-depth and per-distance alpha: the builder's reader did NOT match 0137 (no (k + 0.5) / (n + 1) smoothing; per-seed instead of
  pooled distance; near / far = alpha of the band-mean e instead of the mean of alpha_k; builder's plan printed near 0.284, far 0.215
  vs 0137's 0.378 / 0.157, and d8 0.404 vs 0.130). FIXED in the reader (depth_alpha_0137, dist_alpha_0137, 0137 code verbatim). On the
  stored rounds the new functions return 0137's numbers to 4 decimals: d2 0.5688 d3 0.3972 d4 0.2991 d5 0.2413 d6 0.2050 d7 0.1780 d8
  0.1295; k2 0.6373 k3 0.2937 k4 0.2016 k5 0.1183 k6 0.2439 k7 0.1466 k8 0.1206, near 0.3776, far 0.1574. Reported, not gated.
- C1 as the first GPU step that stops the run: as built, C1 sat inside card S1; only an order mismatch stopped it (exit 7), and the
  adapter / MEAS-row match was read only after all of S1 trained, while S2 ran in parallel unchecked. FIXED: card C1 (C1 alone, train
  + score) and `alpha0138.py gate`, which exits 0 only on C1 PASS (exit 8 otherwise; stub test: order OK, rows 255 of 300, gate FAIL,
  rc 8, as it should on a stub scorer). FS cards start only after gate rc 0.
- Note: R0 here is a uniform draw from the FINAL pool, so R0's own alpha is not expected to equal 0.175; that is C3 (tier 2).

## 2. R_fix vs R0
- Seeds 1, 2, 3, N 256 and 2048, compared on what reachlaw actually visits (file_for_visit then Random(0)): same N rows in the same
  order, same keys, every non-tgt field equal, tgt = join(R0 tgt) for every row, rows changed = R0 list-target rows exactly
  (s1 111 / 1,009; s2 113 / 970; s3 127 / 1,002 at N 256 / 2048), torch seed 13800 + s equal, steps 16 / 128 equal. B1_RESULT OK.
- R0 is one nested pass with checkpoints, R_fix fresh fits. reachlaw.train (read in full): LambdaLR warmup 20 then constant,
  lora_dropout 0.0, nothing depends on the total row count, checkpoint after the batch reaching N (256, 2048 are multiples of 16). So
  the computation is the same up to GPU nondeterminism. C2 (tier 2) tests it on GPU.
- List-target rows: R0 1,009 (s1, N 2048) and C1 262 as stated; 0 for R3, R4S, R4, R1, R2, R1E, R3N, R4C at both N and all 3 seeds.
- Finding (disclosed in PREREG sec. 0): R4S is not pure short hops. 5.6-8.8% of R4S rows (26-39 of 256 states, 241-253 of 2048) have
  no stored state within 3 steps and fall back to the full-distance target (m 4-10); 89-96% of those states are hindsight rows.

## 3. Power under 3 seeds, seed-only CI (t on df 4)
Re-run through the amended reader (`power` subcommand; logs power_*.out, px_*.out, pn*.out, selftest_v.out). Design A: R_fix carries
the true ratio vs R0. Design B: R4S carries it vs R_fix. Noise: synth_outs' independent Bernoulli task outcomes alone give sd of ln e
0.070-0.072 per fit (verify.out B5), so sig 0.064 on top is a total about 0.095 (conservative, 1.5x the measured 0.064) and sig 0 is
about 0.07 (closest to measured). PASS rates, N 256 / 2048, 3 seeds:
| true ratio | R_fix, sig 0.064 | R_fix, sig 0 | R4S, sig 0.064 | R4S, sig 0 |
|---|---|---|---|---|
| 1.0 (FP) | 0.017 (300 sims) | 0.007 (300) | 0.000 (300) | 0.010 (300) |
| 1.5 | 0.180 (300) | 0.243 (300) | 0.090 (300) | 0.180 (300) |
| 2.0 | 0.553 (300) | 0.740 (300) | 0.280 (300) | 0.460 (300) |
| 2.6 | 0.885 (200) | 0.960 (200) | 0.555 (200) | 0.805 (200) |
- False PASS of the null lever in the same runs 0.000-0.025. Seed-only CI covers the true ratio in 88-96% of sims (nominal 95%).
- Power at 2.6 is above 0.6 for R_fix, and for R4S under the calibrated noise, but 0.555 for R4S under the conservative noise.
- More seeds do not fix it: x 2.6, sig 0.064: R_fix 0.885 / 0.865 / 0.825 at 3 / 4 / 5 seeds; R4S 0.555 / 0.545 at 3 / 4 seeds.
  "rho > 1 in every seed" gets harder with each seed, so extra seeds (2.60 GPU-h each) buy nothing.
- A wider N span does (planted law assumed to hold to the top N; patched scratch copy, simulation only), 3 seeds, x 2.6:
  | N grid | R_fix sig 0.064 / 0 | R4S sig 0.064 / 0 | FP (x 1.0, both levers) | FS1-3 GPU-h | first screen total |
  |---|---|---|---|---|---|
  | 256 / 2048 (decided) | 0.885 / 0.960 | 0.555 / 0.805 | 0.000-0.025 | 7.80 | 8.19 |
  | 256 / 4096 | 0.985 / 0.995 | 0.825 / 0.955 | 0.000-0.010 | 8.20 | 8.59 |
  | 256 / 8192 | 1.000 / 1.000 | 0.945 / 0.990 | 0.000-0.010 | 9.11 | 9.50 |
  Recommendation (lead's call, before launch): N 256 / 4096 lifts R4S power at 2.6 to 0.825 for +0.40 GPU-h. 8192 uses 97% of the
  8,440-row pool, so the seeds would share almost the same rows (the seed CI then covers init and order only). Adopting either needs
  a builder change beyond the reader (FITS / cards and the selftest's hard-coded _n2048 fit names) plus a selftest re-run and a PREREG
  amendment; I did not make it. This GO is for the design as decided (256 / 2048).

## 4. PREREG
Amended (sec. 0, 2, 4, 5a, 6, 7): exploratory-screen status and no compounding claim; first screen and references (R_fix vs R0, R4S
vs R_fix); seed-only CI; pass rule rho >= 1.5 with seed-CI lower bound > 1 and rho > 1 in every seed, plus d5-10 seed-CI lower bound
> 1; KILL rule; kill test of the first screen (both KILL, or INCONCLUSIVE with d5-10 point rho < 1.3: the data levers tested cannot
close the 2.6x gap, next lever model / trainer); C1 gate; memory caps and stop rule; 0137 definitions; R4S disclosure; power table.

## 5. GPU-hours and packing
- First screen, solo-card speed (plan_v.out, the builder's measured 0.1226 s / forward and 30.5 + 0.2497 s / row, x 0.42 per row for
  string targets, an estimate): SMOKE 0.02 + C1 0.37 + FS1 2.60 + FS2 2.60 + FS3 2.60 = 8.19 GPU-h (training 2.46, scoring 5.73).
  Wall about 3.0 h on 3 cards (C1 about 22 min first, then FS1-FS3 in parallel). 1.28 of the 8.19 GPU-h is R0's pass from 2048 to
  8192 rows (kept so C3 needs only scoring later).
- One process per card: every card is one Python process (cmd_run trains then scores in series). gpu_setup refuses (exit 4) if the
  card has less free memory than its cap + 1 GB (56.6 GB at 0.65 of an 85.5 GB H100) or if any visible GPU runs a bootseed0128.py
  process. Gaps the launch lines must cover: (a) a neighbour that starts AFTER the check is not seen; (b) the name check knows only
  bootseed0128.py (the free-memory check still blocks an uncapped trainer holding more than about 29 GB); (c) run_alpha0138.sh keeps
  Slurm's CUDA_VISIBLE_DEVICES, so two cards launched into the same multi-GPU holder land on the same first GPU. Hence: one 1-GPU holder
  per card (or a distinct CUDA_VISIBLE_DEVICES=<k> inside each bash -c), launched one at a time, never onto a card with a 0128 or 0129
  trainer.
- Memory: run_alpha0138.sh line 7 exports ALPHA_MEM_FRAC=${ALPHA_MEM_FRAC:-0.35}, which overrides the Python default 0.30. The lead's
  0.30 scoring cap holds only if passed explicitly (launch lines below do). The MEM lines after each training fit print "cap" from the
  scoring fraction (cosmetic); the training cap is the "MEM_FRAC init 0.65" line. A training allocation above the cap raises
  OutOfMemoryError, caught as VOID_OOM, exit 10: the stop rule in PREREG sec. 0.

## 6. sha256 (laptop = Quartz)
Compared byte for byte after my copy (laptop sha256sum = Quartz sha256sum):
| file | sha256 | status |
|---|---|---|
| alpha0138.py | 056880964cca2b6f5674fe82467e3937d75344daa863561c57130cb5587f021a (md5 73559ee961beee58b8f035f750e897c0) | CHANGED by verifier (was 02b3d50f...) |
| PREREG_ALPHA0138_DRAFT.md | 984ae9a28a74a141dbb00928fd9c3dfe8e8d6c630b30f7f052c3236837ed3b60 | CHANGED by verifier (was 3caf24a5...) |
| run_alpha0138.sh | 0ae2d629fcc684b5fa88188b6735685cf6fca2c574fafd3e47cbd55d73eb8da6 | unchanged |
| lever_check.py | 88bc2c2fdace9010d8313ea535ad40148cab9d9a235f1735b71397bed1ff6809 | unchanged |
| BUILD_ALPHA0138.md | 870e57f0998da05c2f4bbd3ea624b3e2710bb3d994a98d3ddc06506d0d6fefd4 | unchanged |
| SHA256SUMS.txt | d08d3d1a3539779cefa3113c439ca4b3ae79b18858908b21948a739de9c5ea04 | unchanged, now STALE for the two changed files |
| pool/POOL.jsonl (Quartz only) | da60787e3ca0118903bd11f7330745297223784edfb2d0cd73ff8ce0fe5687fb | unchanged |
Before my edits the six laptop files equalled Quartz too (the builder's sums). SHA256SUMS.txt was outside my write scope; the lead
should regenerate it. No GPU output exists yet (no fits/ or out/ dir), so the code change voids nothing.
Final selftest on this exact code (md5 73559ee9...): SELFTEST_OK (logs/selftest_final.out): 0128 order r0..r10, visit identity, format
rule (R0 1,009, C1 262 list rows, all others 0), stub run, resume no-op, C2 stub.

## Changes made (only PREREG_ALPHA0138_DRAFT.md and the reader in alpha0138.py)
alpha0138.py (reader and the cards it reads; no change to select, train_fit, score_fits, gpu_setup or the recipes):
1. CARDS "C1" (C1 alone) and "FS1" "FS2" "FS3" (R0 + R3 + R4S at seed s); FIRST_SCREEN constant.
2. read_core: ratio CI = seed-only, ln rho +/- t(0.975, df) sd_seed / sqrt(S) (t table t975), task bootstrap printed as task-CI,
   not gated; SEED_SD line per band; nonpositive / undefined ratio -> INCONCLUSIVE, missing seed sd -> INCOMPLETE (both printed);
   "rho > 1 in every seed" now treats a nan seed as not > 1; VERDICT lines name the reference.
3. Per-depth and per-distance alpha replaced by depth_alpha_0137 / dist_alpha_0137 (0137 code verbatim); read_core(extras=False)
   skips them in simulations.
4. New `gate` (C1 gate, exit 0 / 8) and `power` (first-screen planted-alpha FP and power) subcommands; selftest's planted block now
   runs `power` on the first-screen design; plan prints the first-screen GPU-hours.
PREREG_ALPHA0138_DRAFT.md: new sec. 0 (binding amendment), sec. 2 replicates and nested = fresh argument, sec. 3b distance numbers,
sec. 4 CI rule and 0137 definitions, new sec. 5a power table, sec. 6 C1 gate, sec. 7 first-screen kill test.

## Launch lines for the lead (in this order; every line resumable)
```
O=/N/scratch/bsmensah/silo/alpha0138
# H0, H1, H2, H3: holders the lead picks, each with ONE H100 that has >= 57 GB free and no other trainer (no 0128 / 0129).
# 0. login node: files are the verified ones (compare with sec. 6)
cd $O && sha256sum alpha0138.py run_alpha0138.sh lever_check.py PREREG_ALPHA0138_DRAFT.md pool/POOL.jsonl

# 1. SMOKE (about 3 min): real training peak under the 0.65 cap
srun --jobid=$H0 --overlap -n1 -c 6 --cpu-bind=none bash -c "ALPHA_TRAIN_FRAC=0.65 ALPHA_MEM_FRAC=0.30 bash $O/run_alpha0138.sh run SMOKE" > $O/logs/server_SMOKE.log 2>&1; grep -E "^META|^MEM_FRAC|^MEM train|^NEIGHBOURS|REFUSE|VOID|ALPHA_EXIT" $O/logs/server_SMOKE.log
#    GO ON only if: ALPHA_EXIT rc=0, META mem_frac=0.30, "MEM_FRAC init 0.65", lines "MEM train SMOKE_S" and "MEM train SMOKE_H",
#    no VOID_OOM / REFUSE. Record both peak_reserved values. Otherwise STOP (PREREG sec. 0).

# 2. C1 gate card (about 22 min), then the gate on the login node
setsid nohup srun --jobid=$H0 --overlap -n1 -c 6 --cpu-bind=none bash -c "ALPHA_TRAIN_FRAC=0.65 ALPHA_MEM_FRAC=0.30 bash $O/run_alpha0138.sh run C1" > $O/logs/server_C1.log 2>&1 < /dev/null &
#    after "ALPHA_EXIT rc=0" is in server_C1.log:
grep -E "LEVER_C1|LEVER_SCORE|VOID|REFUSE|ALPHA_EXIT" $O/logs/server_C1.log; cd $O && python3 -I alpha0138.py gate; echo GATE_RC=$?
#    GO ON only if GATE_RC=0 (C1 PASS). GATE_RC 8 = STOP, harness does not reproduce 0128; nothing else launches.

# 3. first screen: three cards, one per card, launched one at a time
setsid nohup srun --jobid=$H1 --overlap -n1 -c 6 --cpu-bind=none bash -c "ALPHA_TRAIN_FRAC=0.65 ALPHA_MEM_FRAC=0.30 bash $O/run_alpha0138.sh run FS1" > $O/logs/server_FS1_R0_R3_R4S.log 2>&1 < /dev/null &
setsid nohup srun --jobid=$H2 --overlap -n1 -c 6 --cpu-bind=none bash -c "ALPHA_TRAIN_FRAC=0.65 ALPHA_MEM_FRAC=0.30 bash $O/run_alpha0138.sh run FS2" > $O/logs/server_FS2_R0_R3_R4S.log 2>&1 < /dev/null &
setsid nohup srun --jobid=$H3 --overlap -n1 -c 6 --cpu-bind=none bash -c "ALPHA_TRAIN_FRAC=0.65 ALPHA_MEM_FRAC=0.30 bash $O/run_alpha0138.sh run FS3" > $O/logs/server_FS3_R0_R3_R4S.log 2>&1 < /dev/null &
#    each log must show NEIGHBOURS without a bootseed0128 / 0129 process and META mem_frac=0.30. Any VOID_OOM = STOP the screen.
#    A card that dies is resumed by re-running its own line (trained fits and scores are skipped).

# 4. read (login node), after all three show "ALPHA_EXIT rc=0"
cd $O && grep -l VOID_OOM logs/server_*.log; python3 -I lever_check.py logs R0="LEVER_ALPHA recipe=R0 " R3="LEVER_ALPHA recipe=R3 " R4S="LEVER_ALPHA recipe=R4S " C1="LEVER_C1 t=0 order_md5=546cc3a2dc9a expected=546cc3a2dc9a OK" && python3 -I alpha0138.py read | tee logs/READ_0138.txt
```
Read VERDICT R3 (vs R0) and VERDICT R4S (vs R3) from READ_0138.txt against PREREG sec. 0. Tier 2 needs a new amendment.
