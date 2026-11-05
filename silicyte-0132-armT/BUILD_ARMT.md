# BUILD_ARMT v3: codes arm T after the verifier's NO-GO (free-derivation closure, strict climbs, code-level copy test, 3 seeds)

Builder report, 2026-11-05 14:1x ET.
- Quartz: /N/scratch/bsmensah/silo/hunt/armT/. Laptop mirror: C:/Users/bmens/NQ_local/records_hunt/armT/.
- CPU only (Quartz login). I submitted, cancelled, held or released no job. I edited no registered file, hunt archive, pylib or hook. Nothing was submitted, committed or pushed.
- Holder: 12688122 now runs 0128 GUIDE_s3, and arm T gets a new holder (maxARMT_H7). Every command below takes it as `$HOLDER`.
- Every verifier item and lead decision is in ARMT_FIXES.md, one line each.

## 1. Files (sha256; the laptop and Quartz copies are byte-identical, re-taken after the final smoke)

| file | sha256 | role |
|---|---|---|
| armt.py | 8fce8dadae38d0144d6b3cdef79893ae0041d30e5a6ac3b4fe76479ecd8fcea9 | everything per round: snapshot (closure), prompt, sample, score, reward (closure running best, copy tests, strict climbs), train (lora_B, KL probe), fork1, offline, copytest, posctl, loop |
| read_armt.py | 9090cb56d80c3553ec2f1c2e7d0c4184e581555c26236a86494807dabdab9c97 | reader: G, Gnd, copy rule, FPR-checked decision, SHARPENING/COPY_PASS, flags, posctl |
| reader_synth.py | 5b1e23fb518487e3bf01c47aab1e384d66438d3b05742350ad5bd008ba2fff67 | synthetic rounds for the reader smoke |
| run_armt.sh | 6c787d86ce601c56750277975a396b3d80a6948a00a39924280e9a9a80b19381 | plain srun loop (3 seeds; parallel reward) |
| posctl.sh | 469a86de7d1bb81d62970c82d14c7c1fa31f0dd00be4015a2b45fd5eec93d20a | plain srun positive control (unchanged) |
| smoke_cpu.sh | 82dbdee0e5fe14efd6c78f6355bf8a71b80d13b0becdfd4a59b984102a15e1af | the CPU smoke v3 |
| fpr_sim.js | 1c8946a3aa8ef1627fd977ec0d1cb896014e7e9bf7b639dbfa8880813026dff6 | false-positive / power simulation (node) |
| fpr_sim_out.txt | 6f83f418193a6d6901086dab4fb17d8b333dfd1a5f89e93b680d172efce59c0d | its output, 5,000 reps per regime |
| snapshot/elites.json | d853af31ed68a50400fc192840448d75fee7e1fe75731265f92d117e9b828836 | EVAL warm start (hunt elites after r03) |
| snapshot/failures.json | a4b84f04a64da5232d9005642bba636e35f67864237ebff16a500b6015215625 | failure lines (pinned archive) |
| snapshot/train_elites.json | 4c5f1d63e53786b990ccfc1658e18d18d5394287615ca2e2e8d6a74fb3d36862 | TRAIN closure d0, gaps, source elites, eval_d0, eval_confounded |
| snapshot/known_warm.json | 83cad7285e981479cb751f258b5f76dbe196142828b3829315364139f786000c | the 44 matrices shown in the 22 prompts (copy-test warm set) |
| snapshot/SNAPSHOT.json | d856810cd7c4b80b082029fb536bf1456ae7b0a6625888597d9f8ee0f571c451 | shas; pinned archive = first 14,366 lines, sha d1a5b910... |

## 2. What changed from v2 (the design is otherwise as in v2)

1. **Free-derivation closure (verifier F1; lead items 1 and 2).**
   - **d0.** For every cell, d0 = max over all pinned valid matrices [n2, k2, d2]_q (k2 >= k) of d2 - max(0, (n2 - n) - (k2 - k)). That is the proven bound of subcode, shortening, puncturing and padding/extension. It is a bound; the exact d of a derived code can be higher, because picking good positions is search, not free.
   - **Lengthening and augmenting** raise k with no d guarantee, so they are not in the bound; the copy test does cover them.
   - **Running best.** Both arms' running bests rb use the same closure of every valid instance onto every cell, each round. A template that only re-derives a known matrix earns at most the closure value, so 0.
   - **Gaps:** PCB2_3 19 -> 3, T06 22 -> 4, T07 22 -> 2, T03 7 -> 4, others unchanged. **Total 138 -> 81** (the verifier's own figure). No cell reaches 0, so none is replaced (snapshot refuses a 0-gap cell).
   - **Prompts.** TRAIN prompts now show the 2 source matrices of each cell's d0. The PCB2_3, T06 and T07 prompts show the [75,19,32]_4 PCB2_4 elite, and T03 shows the #8 [99,11,54] elite.
2. **Strict climbs only (verifier F2; lead item 3).** The tie_new_matrix rule is gone. A template enters the SFT set iff its best instance that is PROVEN not to be a free derivation of a known matrix beats the arm's running best. An unknown test does not qualify.
3. **Code-level copy test (lead items 3 and 4; verifier fix 3).**
   - **The test.** `derives(q, C, M)` searches for an order-preserving column map sigma and a linear map A with C[:, j] = A . M[:, sigma(j)]. In other words, C lies in the row space of a puncturing of M, which covers subcode, shortening, puncturing, pad, extension and (with an all-ones augment) lengthening, all as seedlib implements them.
   - **Details.** Zero columns may be pads, and trailing parity columns are stripped. The search runs from both ends, and either direction exhausting proves non-derivation.
   - **Budget.** It is 40,000 nodes per direction. More than DELTA_MAX = 10 deleted columns is not searched, and both cases give 'unknown'. 'unknown' never counts as novel.
   - **What gets tested.** Each stream-round tests every climb candidate and a fixed sample (the first 48 distinct matrices by sha256, the same rule for both arms) against all 44 matrices shown in the 22 prompts (known_warm.json) plus the arm's earlier-round climb matrices.
   - **Logged per matrix:** status, source and row overlap.
   - **rb_nd** is the running best rebuilt only from instances proven novel.
4. **PASS rule (lead items 4 and 5).** With 3 seeds per arm, PASS needs all of these:
   - G_k >= M and Gnd_k >= M in EVERY seed, where M = max(2, D_F) and D_F is the FROZEN-vs-FROZEN spread;
   - fewer than half of TRAINED's TRAIN climb events copy-like;
   - no COLLAPSE or NO_UPDATE.

   COPY_PASS and SHARPENING labels are always printed. fpr_sim.js gives a worst-case FPR of 0.025 at 3 seeds (0.111 at 2; 5,000 reps per regime; output in fpr_sim_out.txt).
5. **Reader.** It prints the copy share (TRAINED and FROZEN) next to G and Gnd every round. COLLAPSE and NO_UPDATE map to FAIL. Tertiary EVAL excludes the confounded #8 and #55.
6. **Drivers.**
   - Default seeds are 0,1,2. The reward step now runs as one process per stream in parallel (in both `armt.py loop` and run_armt.sh).
   - The snapshot no longer stats 11.6k matrix files (the stat storm took minutes; it now takes 7 s).
   - CPU-only steps on a login node can set ARMT_LIGHT_TOK=1 to count tokens with the tokenizers library and the Qwen3 non-thinking wrapper (`LightTok`). MEASURED on login h1 at 14:0x ET: tokenizers loads in 3 s; `import transformers` did not finish within 200 s. GPU steps always use transformers, and `sample` logs a TOKCHECK line per prompt comparing the two counts. The smoke pins the light count to the transformers count measured in v2 (c11: 12,419 tokens).

## 3. Volume and an honest round time (one H100, 24 CPUs, 3 seeds per arm)

| quantity | value |
|---|---|
| N per TRAIN / EVAL cell per stream per round | 9 / 2; MAXIDX 4 |
| rollouts per stream per round | 128 (108 TRAIN + 20 EVAL) |
| rollouts per seed over 10 rounds | 1,280 (1,080 on TRAIN cells), against 640 in the prior study, x 3 seeds per arm |
| round >= 2 | 6 streams = 768 samples, at most 3,072 instances |
| sampling | **about 64 min central.** ESTIMATE: 768 x about 5k output tokens, since BASE pastes push toward the 8,192 cap. At about 17k-token contexts decode is KV-bandwidth bound: about 2.9 GB of KV read per sequence step against 3.3 TB/s gives about 1,000 tok/s aggregate. Range 38 min (3k tokens) to 105 min (at the cap). Prefill: 88 distinct (adapter, cell) prefixes x 17k tokens, x 2.5 for evictions, about 6 min |
| scoring | at most about 25 min: 3,072 x 11.9 core-s / 24 cores (the r03 job's rate; template crashes are cheaper) |
| reward with copy tests | at most about 6 min: 6 streams in parallel, copy tests capped at 300 s per stream (COPY_SECONDS). MEASURED: offline r04 (4,917 rows, 102 tested matrices) took more than 6 min before known-matrix dedupe and the 10k budget; the cap now bounds it, and untested matrices are unknown, never novel |
| training | about 8 min (3 seeds x (load + small strict-climb SFT + KL probe)) |
| round total | **about 108 min central, 80 to 145 min range** (rounds >= 2); about 55 min for round 1 (3 FROZEN streams); positive control about 35 min |
| 10 rounds | about 17 h (13 to 22 h) plus the posctl, inside a 48 h holder |

The verifier was right that 44 min was optimistic. Rule: if round 2 takes more than 150 min, N_TRAIN goes 9 to 6 for both arms from round 3.

## 4. Smoke results (CPU only, `bash armT/smoke_cpu.sh` on Quartz login)

**Result: SMOKE_ALL_PASS, 32 of 32 checks, 381 s** (login h1, 14:04 ET).
- Log: smoke/cpu_v3/smoke_log.txt on the laptop, armT/smoke/cpu_20261105_140438/ on Quartz.
- The registered hash checks pass (HASHCHECK_ALL_OK).

1. **Snapshot (F1).**
   - The pinned prefix still hashes to the snapshot sha.
   - `GAP_TOTAL direct=138 closure=81`.
   - PCB2_3 d0 = 32 (gap 3; source r03_gemini_PCB2_4_0013_i002); T07 gap 2; T03 d0 = 50 (gap 4; source the #8 elite r01_gemini_c8_0016_i000).
   - No gap is 0. eval_confounded = ['8', '55'].
2. **Prompts.**
   - 22 build, and the EVAL prompts are byte-identical to propose.js (c11 39e2917a..., c8 971083b9...).
   - The light-tokenizer count of c11 equals the v2 transformers count (12,419).
   - The PCB2_3 prompt now shows `BEST SAVED CONSTRUCTION 1 (exact d = 32 at length 75, dimension 19`.
3. **Code-level copy test: `COPYTEST_DONE PASS`, 20 of 20.**
   - 10 free-operation positives test derived: subcode (first and random), shorten, puncture, pad + extend, shorten + lengthen, puncture + subcode + pad, shorten 3 + puncture 1, and middle deletions.
   - **The verifier's F2 copy instances** r04 deepseek/PCB2_4_0012 i000, i001 and i002 test derived.
   - 6 random negatives (including 2 and 3 deletions) test novel.
   - An unrelated real code (#14, 40 deletions) tests unknown.
4. **Offline on stored hunt rows, r04 against the closure of smoke..r03** (the copy cap was 90 s in the smoke):
   - PCB2_3 rb 32 -> 35 and rb_nd 32 -> 35. All 55 PCB2_3 climb events (r04's abelian [75,17,33..35] codes) are proven novel. Through the closure they lift T06 the same way.
   - SFT set = 2 strict climbs (PCB2_3_0011 at reward 3; PCB2_3_0023 at reward 1).
   - There are no tie rows. **The verifier's PCB2_4_0012 copy is absent** (it only reaches d 32 = rb, so it earns 0).
   - Copy sample: 48 matrices, 6 derived, 21 novel, 21 unknown (budget or time cap; unknowns never count as novel).
5. **End to end, 2 rounds through the registered scorer** (fake samples are stored hunt templates):
   - **Round 1:** the c11_0000 sample is a [94,10,47] code below T03's corrected d0 of 50, and the PCB2_4_0013 template sample copies the warm-start elite. So: no climb, copy share 0.111 of 9, `EMPTY_SFT_SKIP r=1`.
   - **Round 2:** PCB2_3_0011 at MAXIDX 20 gives `rb 32->35 rb_nd 32->35`, 3 climb events, all novel, and SFT 1 row.
   - FROZEN training is REFUSED. Round-3 sampling stops at MISSING_ADAPTER before vLLM loads.
6. **Reader on synthetic rounds (3 seeds):**
   - climb: `PASS G_R=[11, 11, 11] Gnd_R=[11, 11, 11]`;
   - sharpen: `FAIL ... SHARPENING`;
   - copy: `FAIL G_R=[11, 11, 11] Gnd_R=[0, 0, 0] ... COPY_PASS`;
   - two seeds: `INCOMPLETE`;
   - Fisher 0.1053 / 0.6010.
7. **Positive-control plant:** 9 cells, 36 rows.

**Not smoked (needs the GPU):** vLLM LoRA sampling, the peft step, the KL probe and the timings. The positive control is the gate.

## 5. Launch commands (from the laptop; set HOLDER to the new arm T holder id once it is RUNNING; qrun.sh refuses otherwise)

A verifier (not the builder) writes C:/Users/bmens/NQ_local/records_hunt/armT/VERDICT_ARMT.md with `VERDICT: GO`, `BEST APPROACH:` and `MOVES THE GOAL:`. The current file is the v2 NO-GO.

```
HOLDER=<maxARMT_H7 job id>
VERIFIED=C:/Users/bmens/NQ_local/records_hunt/armT/VERDICT_ARMT.md timeout 120 ssh -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh $HOLDER armT_posctl 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt.py posctl --n 16"
# only after POSCTL_VERDICT PASS:
VERIFIED=C:/Users/bmens/NQ_local/records_hunt/armT/VERDICT_ARMT.md timeout 120 ssh -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh $HOLDER armT_r01 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt.py loop --r-from 1 --r-to 1 --seeds 0,1,2"
VERIFIED=C:/Users/bmens/NQ_local/records_hunt/armT/VERDICT_ARMT.md timeout 120 ssh -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh $HOLDER armT_loop 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt.py loop --r-from 2 --r-to 10 --seeds 0,1,2"
```

**Reading results:**
- Status: /N/scratch/bsmensah/leecomp/runs/armT_*/attempt_*/STATUS.json and log.txt.
- Verdict: `python /N/scratch/bsmensah/silo/hunt/armT/read_armt.py --R 10 --json /N/scratch/bsmensah/silo/hunt/armT/READ_R10.json`.
- Stop: `touch armT/STOP`.

**Plain srun path:** `srun --jobid=$HOLDER --overlap -n1 -c 24 bash .../armT/run_armt.sh 1 10 "0 1 2" < /dev/null` (posctl.sh is the same shape).

**Guards:**
- peft comes only from PYTHONPATH=fourth_law/pylib, which qrun.sh, run_armt.sh and posctl.sh all set.
- pair_gate.py does not match these commands (qrun.sh and silo/hunt/armT are outside its patterns). VERIFIED is carried for the record; enforcing it is the lead's call.
- qrun does not need smokestamp. An optional stamp: `CPU_OK=1 python ~/.claude/hooks/smokestamp.py C:/Users/bmens/NQ_local/records_hunt/armT/armt.py --expect SMOKE_ALL_PASS --timeout 900 -- timeout 890 ssh -o BatchMode=yes -o ControlPath=none quartz bash /N/scratch/bsmensah/silo/hunt/armT/smoke_cpu.sh`.

## 6. Open points

1. The GPU path is unsmoked (vLLM LoRA, the peft step, the KL probe, the timings). The positive control is the gate.
2. The copy test has known limits:
   - it misses copies with a non-order-preserving column permutation, or with more than 10 deletions;
   - its copy share is a lower bound;
   - unknowns are excluded from Gnd and from the SFT set (conservative).
3. **Power is modest.** At 3x FROZEN's climb rate the sim gives 0.23 to 0.67. A FAIL means "no large effect".
4. **Found by the build:** the hunt's own r04 re-found PCB2_3 [75,17,35]_4 (r04_gemini_PCB2_3_0011_i018, control_pass and control_clean both true). Arm T's warm start is pinned before r04.
