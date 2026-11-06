# AMENDMENT A1 (DRAFT for an independent verifier; not active): silicyte-0132 codes arm T

Builder: 2026-11-05, 18:2x to 19:xx ET. CPU only (Quartz login h1). I submitted, cancelled, held or released no job, touched no STOP file and no process I did not start, and edited no registered file. The live loop (armT_loop attempt_20261105T230017Z, running its own qrun copy of armt.py, sha256 8fce8dad...) was only read.

A1 lives in `armT/armt_a1.py`. It is the registered armt.py v3 plus a 317-line diff (`diff armt.py armt_a1.py`). It is inert unless `armT/AMENDMENT_A1.json` exists. The registered armt.py, read_armt.py and smoke_cpu.sh are byte-identical to their registered hashes on Quartz (section 9).

**Note for the lead:** the LAPTOP copy of armT/armt.py is NOT the registered file. Its sha256 is 7629128df2ee7f44a7026cf360bead14e628247058c772086eeda55b48b08bcb, 101,696 bytes, and it carries the previous builder's A1 draft edits. The Quartz copy and the loop's attempt copy are both the registered 8fce8dad... (95,475 bytes). I did not change the laptop file because it is a registered name. A verbatim copy of the registered bytes is at armT/a1_build/armt_registered.py, and the lead can restore it with `cp a1_build/armt_registered.py armt.py`.

## 1. The problem, measured (the physics floor)

Round 1 (shared; TRAINED_s<k> r01 = FROZEN_s<k> r01) gave **0 SFT rows on all 3 seeds**, so A_1 = base and TRAINED = FROZEN. The previous draft (advantage over the cell mean) also gave 0 rows: all valid templates in a cell had the same best d.

I read the round-1 rows at the matrix level (price.py and novelty.py; both read-only, outputs in armT/a1_build/). Results:

| quantity, per seed (s0 / s1 / s2) | value |
|---|---|
| TRAIN rollouts | 108 / 108 / 108 |
| distinct template sha256 among them | 25 / 27 / 26 |
| distinct valid matrices on TRAIN cells | 19 / 19 / 19 |
| **TRAIN matrices NOT byte-identical to a pinned hunt-archive matrix** | **0 / 0 / 0** |
| mean template line overlap with its own prompt (stripped non-blank lines) | 0.986 / 0.986 / 0.985 (min 0.857) |
| EVAL matrices not in the pinned archive | 4 / 0 / 4 of 35 |
| BASECTL (N = 16 per cell, same sampling) EVAL matrices not in the archive | 4 of 31; TRAIN (PCB2_3, PCB2_4): 0 of 4 |

So every TRAIN instance in round 1 is an exact re-emission of a matrix the hunt had already scored. At T 0.7 / top_p 0.8 / top_k 20 the base model pastes the shown construction program: 9 different seeds give one identical program in 8 of the 12 TRAIN cells.

**Mechanism (INFERRED, not measured):** top_p 0.8 keeps only the top token wherever that token has p > 0.8. A model in copy mode puts p > 0.8 on the next pasted token, so sampling is greedy exactly where the program is pasted. Any per-seed difference lives only in the free-text IDEA line.

**Floor.** No reward rule that reads these samples can produce a copy-safe row. The samples contain no new matrix, so the only lever that can create rows is the sampling distribution itself.

**The `derives` test has a blind spot here (found by this pricing).** It checks against the 44 matrices shown in the prompts plus the arm's own climbs. It does NOT check the roughly 10.3k other pinned-archive matrices. 22 of the 48 sample matrices tested 'novel' in TRAINED_s0 r01, yet all of them are archive matrices. The copies are the unshown sibling instances (idx 1 to 3) of the pasted template. This does not affect the registered metrics: d0 is the closure over the whole archive, so a re-emission can never climb. It does matter for any SFT rule below the running best.

## 2. Candidates priced on round 1 (stored rows; rows per seed s0 / s1 / s2)

| candidate | rows r01 | copy-safe? | verdict |
|---|---|---|---|
| registered (strict climbs) | 0 / 0 / 0 | yes | starves |
| previous draft: advantage over the cell mean | 0 / 0 / 0 | n/a | every template in a cell has the same best d |
| (a) finer within-d rank (fewer min-weight words) among code-level-novel instances | 0 / 0 / 0 once exact copies are removed | – | no two distinct new codes exist at any d |
| (b) near-misses at rb-1..2, `derives` gate only | **10 / 11 / 9** (PCB2_2 6/7/5, T01 2/2/2, T02 2/2/2; one per distinct template sha) | **NO** | every one of these rows is a byte-identical hunt-archive matrix (PCB2_2 d 76, T01/T02 d 79). Training on them is training to paste |
| (b') near-misses with the archive gate (this amendment's SFT rule) | **0 / 0 / 0** (`a1count --r 1`) | yes | correct and safe, but empty at the registered sampling |
| (c) sampling change for both arms (this amendment's sampling rule) | not measurable on CPU; priced by the pre-registered GPU probe (section 5) | n/a | the only lever that can create new matrices |
| (d1) score PARAMS entries beyond MAXIDX 4 of a pasted template | could give unseen matrices | no | the response text is still a paste, so credit would go to the hunt's authors, not the proposer |
| (d2) reward-weighted RL on closure distance | 0 usable contrast | – | every sample in 8 of 12 cells is the same program. With no variance there is no advantage, whatever the weighting |

Round 2 (live loop, registered sampling) is in section 8 when it lands. Under the registered sampling I expect 0 A1 rows there too.

## 3. The amendment (exact rule; code: armt_a1.py)

**Switch.** `armT/AMENDMENT_A1.json` = `{"start_round": k}` with k >= 2 (any other key, or k < 2, is refused). From round k on:

**(1) Sampling, both arms identically.**
- Every TRAINED_s* and FROZEN_s* stream samples with temperature 1.0, top_p 1.0, top_k 20 (A1_SAMPLING) instead of 0.7 / 0.8 / 20.
- POSCTL and BASECTL never change.
- Per-sample seeds, prompts, N, MAXIDX and max tokens are unchanged.
- `cmd_sample` refuses a round in which two arm streams would sample differently. It prints one `A1_SAMPLING stream=... rule=A1|registered` marker per stream and writes the sampling into every samples.jsonl row and into sample_stats.json.
- Reason: top_p 1.0 lets pasted positions deviate. top_k 20 still bounds the tail.

**(2) SFT rows, TRAINED only (FROZEN never trains; cmd_train still refuses it).** The reward of round r >= k builds the SFT set as follows:
- **Climbs.** The registered strict climbs, unchanged (best instance proven novel and above rb), with loss weight 2.0 + climb.
- **Near-misses.** A template whose best implied d is rb - 1 (weight 0.5) or rb - 2 (weight 0.25). It qualifies only if EVERY one of its instances with implied d >= rb - 2 meets all of:
  - code-level `derives` status 'novel' (unknown or derived disqualifies);
  - matrix sha256 not in the pinned hunt archive;
  - matrix sha256 not among this stream's own matrices from earlier rounds.

  A template with any instance at or above rb is never a near row, so ties never enter (verifier F2 stands).
- **Caps.** One row per distinct template sha256 per cell (the lowest template path, using the model's own full response). At most 4 near rows per cell, closest first.
- **Copy tests.** Window instances go to the copy test AFTER the registered 48-matrix sample. TRAINED's copy-share diagnostic therefore gets the same test budget as FROZEN's, and an instance not reached under the 300 s cap is 'unknown', which never qualifies.

**(3) Training.**
- Per-row loss weight in train_lora: `(loss * weight / ACCUM).backward()`. Registered rows carry no weight field, so they weigh 1.0.
- New marker lines: `A1_TRAIN_ROW ... weight=`, `A1_INIT_LOAD ... lora_B_norm` (the verifier's round-2 warm-start check) and `grad_norm_preclip` per step.
- Weights act within an accumulation step. The registered clip at 1.0 bounds each step, so a step made only of weight-0.25 rows is clipped like any other when its raw norm exceeds 4. The logged pre-clip norm shows whether that happens.

**Unchanged:** the decision rule (read_armt.py, G_k and Gnd_k >= max(2, D_F) in every seed, the copy rule, COLLAPSE/NO_UPDATE), all metrics, the claim and submission rule, the stop rules and FROZEN's no-training rule. No TRAINED-vs-FROZEN number was read to choose A1: only row availability, validity and archive membership on round 1 (shared by construction) and on base-model samples.

## 4. Copy safety and fairness

**Copy safety.**
- Every A1 row's credited instance, and every other instance of that template in the window, passes `derives` AND is not a byte-identical known matrix.
- Strict climbs cannot be archive copies: rb >= d0 = the closure of the whole archive.
- **Residual (as for v3).** `derives` misses non-order-preserving column permutations, and the archive gate is exact-match only. A new-sha permuted or derived variant of an UNSHOWN archive matrix can therefore enter as a near row.
  - It cannot create G or Gnd: the closure covers the archive.
  - It can teach paste-and-perturb. That would show as a rising copy share or falling distinct matrices, which the registered SHARPENING and COLLAPSE labels already catch.
  - Each A1 row's matrix sha and its copy-test overlap are logged in rewards.json (`a1_inst`).

**Fairness.**
- Sampling changes for both arms in the same round, with the same seeds.
- Rounds 1 to k-1 ran at the registered sampling for both arms, and rounds k to 10 run at A1 sampling for both.
- G at R = 10 is a within-seed TRAINED-minus-FROZEN difference, so a common shift in climb rate hits both arms alike.
- D_F (the FROZEN-vs-FROZEN spread) still sets M.
- The fpr_sim worst case (0.025 at K = 3) spans 9 climb-rate regimes. A1 changes the climb rate of both arms, not the H0 symmetry.
- Stated asymmetry, as before: only TRAINED pays training time.
- Possible side effect: higher-entropy sampling may lengthen outputs or raise truncation. Stop rule 6 (round > 150 min means N_TRAIN 9 -> 6 for both arms) still applies.

## 5. Pre-registered probe gate (kill test, written before its data)

A1 is switched on only if A1 sampling actually creates rows. `armt_a1.py a1probe` (GPU, about 40 min) runs in a separate tree, armT/a1_probe/, never in runs/:
- 3 base-model streams (FROZEN_s7..s9: seed tags no study stream uses) sample the 12 TRAIN cells at A1 sampling (N 9 each, 324 rollouts);
- the registered scorer scores them;
- `a1count` prices the A1 rows against the snapshot closure (rb = d0).

**A1_PROBE_PASS** iff A1 rows >= 3 in at least 2 of the 3 streams AND the TRAIN template valid share >= 0.42 in every stream. 0.42 is half of round 1's measured 0.824 to 0.833 at the registered sampling.

- **PASS:** switch at the next round boundary.
- **FAIL:** do NOT switch. The study continues as registered, and its expected outcome is NO_UPDATE at round 6 (stop rule 3), a structural FAIL, not evidence about H1. Accept that null. No second sampling setting is tried under this amendment; a new one would be a new amendment.

The probe reads only base-model samples, so no arm comparison exists in it.

## 6. Checks

**CPU smoke: `smoke_cpu_a1.sh`.** The registered smoke_cpu.sh is hashed in BUILD, so it is untouched. The A1 smoke runs it first and then the A1 checks. Result: see section 9.
- The registered shas, and `SMOKE_ALL_PASS` of the registered smoke.
- The switch: inert without the file. The same A1 sampling holds for FROZEN and TRAINED from start_round, and the registered sampling holds before it and for POSCTL/BASECTL. Two malformed files are refused.
- `a1count --r 1` on the live round 1: A1_rows = 0 on every seed, with the gate reason `seen_matrix` for PCB2_2.
- **End to end in a scratch tree** (fake samples = stored hunt templates, registered scorer, A1 on from round 2):
  - r1 uses the registered rule (`EMPTY_SFT_SKIP`).
  - r2 prints `SFT_RULE ... AMENDMENT_A1`.
  - The r04 PCB2_3_0011 climb enters with weight 5.0 (= 2 + 3).
  - The pasted r03 PCB2_4_0013 copy does not enter.
  - FROZEN samples like TRAINED, has `a1.active false` and no SFT set, and its training is refused.
  - `a1count` on the e2e rows reports the climb.
- **Near-miss positive control:** stream TRAINED_s8 with a PLANTED round-1 state (PCB2_3 rb 36, in the scratch tree only) gives exactly one near row: weight 0.5, gap 1, best_d 35.

**GPU checks (for the lead, on the holder after the STOP boundary; exact commands in section 10):**
1. `armt_a1.py a1gpucheck`: one fixed row through the real train_lora. PASS iff:
   - weight 0.0 from a fresh LoRA leaves lora_B_norm = 0, proving the weight reaches the gradient;
   - weight 1.0 gives a norm > 0;
   - weight 0.25 warm-started from the weight-1.0 adapter logs `A1_INIT_LOAD` with the same norm (rel. 1e-3) and ends with a different norm.

   About 8 min.
2. `armt_a1.py a1probe`: the section-5 gate, about 40 min.

Lever markers to check in the restarted loop log:
- `A1_STATE ... start_round`;
- `A1_SAMPLING stream=FROZEN_s0 r=k temp=1.0 top_p=1.0 top_k=20 rule=A1` (and the same for TRAINED_s0);
- `SFT_RULE ... AMENDMENT_A1`;
- `A1_TRAIN_ROW` and `A1_INIT_LOAD`;
- `META ... armt_sha=<the armt_a1.py sha>`.

If `rule=A1` is missing for either arm in round k, the round is LEVER_VOID for A1 and must be read as registered.

## 7. Expected rows per round

- At the registered sampling: 0 per seed (measured, round 1).
- At A1 sampling: the probe measures it. The gate needs at least 3 per stream in 2 of 3 streams.
- I can only bound it by physics. A new matrix needs an edit to the PARAMS or construction code. Round 1 shows at most 4 new matrices per 20 EVAL samples (seeds 0 and 2) at top_p 0.8, and 0 per 108 on TRAIN. I make no claim about the A1 rate before the probe.

## 8. Round 2 (registered sampling, live loop)

**Timing.** Round 2 ran 18:00 to 19:05 ET (ROUND_DONE total_s 3920: sample 2924 s, score 936 s, train 59 s). The registered rule gave 0 SFT rows on every seed, so A_2 = base. Round 3 started at about 19:05 ET.

**Counts.** `armt_a1.py a1count --r 2` (read-only; log a1_build/a1count_r2.log) and novelty.py r2:

| seed | A1 rows (climb, near) | TRAIN matrices not in the pinned archive | distinct templates / 108 | template valid share |
|---|---|---|---|---|
| s0 | 0 (0, 0) | 0 of 19 | 25 | 0.833 |
| s1 | 0 (0, 0) | 0 of 19 | 28 | 0.824 |
| s2 | 0 (0, 0) | 0 of 19 | 28 | 0.833 |

**Per cell (all 3 seeds alike; every cell 0 rows):**

| cell | gate reason (9 of 9 templates) |
|---|---|
| PCB2_1, PCB2_2, T01, T02 | `seen_matrix` (s1 PCB2_1: 1 template `no_window_instance`) |
| PCB2_3, PCB2_4, T05, T06, T07 | `instance_at_or_above_rb` (a pasted copy at rb) |
| T03, T04, T08 | `no_window_instance` |

**Over rounds 1 and 2:** 648 TRAIN rollouts per arm (324 per round, 3 seeds), and 0 matrices that the hunt had not already scored. Mean template line overlap with the prompt is 0.983 to 0.986. Reward design cannot fix this. Only the sampling lever (or nothing) can.

## 9. Files, sha256 (laptop and Quartz byte-identical unless noted)

Re-taken at 19:3x ET on both sides.

| file | sha256 | note |
|---|---|---|
| armt.py (Quartz, registered) | 8fce8dadae38d0144d6b3cdef79893ae0041d30e5a6ac3b4fe76479ecd8fcea9 | unchanged. The LAPTOP copy is 7629128d... (see top) |
| armt_a1.py | 5d7db6b8d6e27e77ebcca16dd1d4389efebd4569f23292a1b9d96fe6983f0114 | the A1 code |
| smoke_cpu_a1.sh | 449f6c92e62af981aef74203e7948ca8c759b521dcbd05478b0b89fd67b97bc9 | A1 smoke |
| smoke_cpu.sh | 82dbdee0e5fe14efd6c78f6355bf8a71b80d13b0becdfd4a59b984102a15e1af | registered, unchanged |
| read_armt.py | 9090cb56d80c3553ec2f1c2e7d0c4184e581555c26236a86494807dabdab9c97 | registered, unchanged |
| a1_build/price.py | bdb26a885cec3c88540c90abbf3bebb77ac8d67814396a5ffb5165076efda08e | round-1 pricing (read-only) |
| a1_build/novelty.py | f6877fd285e2cb3f3f0ef71d4de37755218bb41eb9ca307e00862349605dc36a | archive-membership count (read-only) |
| a1_build/find_near.py | 39f979696c0d20b8007253b48f9289fe9a06638275020983bc4bfdb51f817a70 | found no stored post-pin near-miss template, hence the planted-state control |
| a1_build/peek.py | 45416b045d08e071bfb6c4dd55a6d2d606872ce45d8be8f3944494e1bcc4d29a | first look at round 1 |
| a1_build/run.sh | 11db95b7cb05e7aee574445cf402be2ad9a317a5117cbe4766d121c2e70e592f | login-node runner (hunt venv, python -I) |
| a1_build/armt_registered.py | 8fce8dad... | laptop copy of the registered bytes |

This file's own sha256 is printed in the builder's final report; it cannot appear inside the file.

**Smoke result.** `SMOKE_A1_ALL_PASS` (Quartz login h1, 18:43 to 19:29 ET). It includes the registered `SMOKE_ALL_PASS`.
- Log: a1_build/smoke_a1_run1.log (laptop and Quartz); run directory smoke/a1_20261105_184327/.
- The smoke ran on armt_a1.py sha 8039eb02.... The final 5d7db6b8... differs from it ONLY by 4 lines inside `cmd_a1gpucheck` (gc.collect and torch.cuda.empty_cache between the three GPU trainings). That code is not reached on CPU.
- After the change, AST passes on py313 and py314.
- The verifier can re-run the whole smoke on the final file with `nohup nice -n 19 bash armT/smoke_cpu_a1.sh > log 2>&1 &` (about 45 min on a loaded login node).

**Key smoke lines:**
- e2e r2 TRAINED: `SFT_SET ... rows=1 (climb 1, near 0, weights [5.0])`;
- planted near control: `SFT_SET stream=TRAINED_s8 r=2 rows=1 (climb 0, near 1, weights [0.5])` with `copy_tests={"novel": 20}`;
- FROZEN_s9 r2: `a1.active false`, sampling `[1.0, 1.0, 20, "A1"]` (the same as TRAINED_s9), sft=None.

## 10. Switch procedure (the lead; only after a verifier GO)

**Holder:** 12693135 (maxARMT_H7, h100-single, RUNNING, about 44 h left at 18:4x ET). The loop step is 12693135.2.

1. **Stop at a round boundary.** The loop checks STOP before each round, so the running round finishes in full (sample, score, reward, train) and the loop then exits before the next one:
   ```
   timeout 60 ssh -n -o BatchMode=yes -o ControlPath=none quartz "touch /N/scratch/bsmensah/silo/hunt/armT/STOP"
   ```
   Done when the log shows `STOP file present: stopping before round K` and `ARMT_LOOP_EXIT`, and the attempt's STATUS.json reads DONE:
   - log: /N/scratch/bsmensah/leecomp/runs/armT_loop/attempt_20261105T230017Z/log.txt
   - STATUS.json: the same attempt folder

   K = the first round not yet started when the verifier GO arrives. Round 3 started at about 19:05 ET, and rounds take about 65 min (round 2: 3920 s), so a STOP touched during round 3 gives K = 4. The loop log's last ROUND_START line names the running round; K is that round + 1.
2. **GPU checks on the now-free card** (run one after the other; each needs the whole card):
   ```
   timeout 120 ssh -n -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh 12693135 armT_a1gpucheck 75000 8 /N/scratch/bsmensah/silo/hunt/armT/armt_a1.py a1gpucheck"
   # after its STATUS.json reads DONE and its log has A1_GPUCHECK PASS:
   timeout 120 ssh -n -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh 12693135 armT_a1probe 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt_a1.py a1probe"
   ```
   - Read A1_GPUCHECK in `runs/armT_a1gpucheck/attempt_*/log.txt` and `armT/a1_gpucheck/A1_GPUCHECK.json`.
   - Read A1_PROBE_PASS or A1_PROBE_FAIL in `runs/armT_a1probe/attempt_*/log.txt` and `armT/a1_probe/A1_PROBE.json`.
   - Before switching, check the lever: `CPU_OK=1 python -I C:/Users/bmens/NQ_local/lane/lever_check.py <probe attempt dir> PROBE='A1_SAMPLING stream=FROZEN_s7 r=2 temp=1.0 top_p=1.0 top_k=20 rule=A1'`.
3. **Then:**
   - **If A1_GPUCHECK FAIL or A1_PROBE_FAIL:** do not switch. Remove STOP and relaunch the REGISTERED loop from round K:
     ```
     timeout 60 ssh -n -o BatchMode=yes -o ControlPath=none quartz "rm /N/scratch/bsmensah/silo/hunt/armT/STOP"
     VERIFIED=C:/Users/bmens/NQ_local/records_hunt/armT/VERDICT_ARMT.md timeout 120 ssh -n -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh 12693135 armT_loop 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt.py loop --r-from K --r-to 10 --seeds 0,1,2"
     ```
     (armT_loop's LOCK was released at its exit.)
   - **If both PASS and a verifier wrote VERDICT_ARMT_A1.md with VERDICT: GO:**
     ```
     timeout 60 ssh -n -o BatchMode=yes -o ControlPath=none quartz "cd /N/scratch/bsmensah/silo/hunt/armT && rm STOP && echo '{\"start_round\": K}' > AMENDMENT_A1.json && cat AMENDMENT_A1.json && sha256sum armt.py armt_a1.py"
     VERIFIED=C:/Users/bmens/NQ_local/records_hunt/armT/VERDICT_ARMT_A1.md timeout 120 ssh -n -o BatchMode=yes -o ControlPath=none quartz "bash /N/scratch/bsmensah/leecomp/qrun.sh 12693135 armT_loop_a1 75000 24 /N/scratch/bsmensah/silo/hunt/armT/armt_a1.py loop --r-from K --r-to 10 --seeds 0,1,2"
     ```
     Replace K with the number. The echo must give exactly `{"start_round": 4}` (for K = 4), or every A1 step refuses.
4. **Lever markers at round K** (in runs/armT_loop_a1/attempt_*/log.txt):
   - `META armT loop ... armt_sha=<armt_a1.py sha>`;
   - `A1_STATE ... "start_round": K`;
   - six `A1_SAMPLING ... rule=A1` lines (FROZEN_s0..2 and TRAINED_s0..2);
   - `SFT_RULE stream=TRAINED_s<k> r=K AMENDMENT_A1`;
   - from round K+1 on, `A1_INIT_LOAD` when A_K is a real adapter.

**No state is lost.** FROZEN is unchanged. TRAINED's A_1 (and every empty round after it) is BASE_ONLY, and state_<r>.json carries the running bests and known matrices. Every phase is resumable by its marker files.

**Register before the switch.** Log A1 as a deviation in registry/HUNT_REGISTRY.md, with this file's sha and armt_a1.py's sha, BEFORE round K's data exist.

## 11. Open points

- The probe has not run. Until it passes, A1 has not been shown to relieve the starvation. It is a correct, copy-safe rule plus one pre-registered sampling bet.
- The weighted loss and the warm-start load are not GPU-checked (a1gpucheck).
- Rows below rb reinforce validity near the frontier. That is the SHARPENING path the prior study saw. A1 does not change how SHARPENING is labelled or punished.
- The laptop armt.py mismatch (top of file) should be restored by the lead.
