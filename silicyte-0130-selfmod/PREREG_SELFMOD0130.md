# REGISTERED 2026-11-05 18:02 ET as silicyte-0130 SELFMOD (EXPLORATORY), after VERDICT_SELFMOD0130.md GO (full launch, K = 4 on H8 in one process), before any SELFMOD generation. Code md5s: selfmod.py dc55bed5, run_selfmod.sh 2cbcb326, read_selfmod.py b6fd9bdb, preflight_probe.py 5ebcc86c, overlap_check.py 25c29fc6, knobs.py abe5a72d, smcore.py 9dfb6e77, smtrain.py 40b9a987, proposer.py f55b2e1c.

# PREREG silicyte-0130 SELFMOD (DRAFT, EXPLORATORY): a loop that adjusts everything except its scoreboard

Draft of 2026-11-05 14:15 ET, revised 14:5x ET after VERDICT_SELFMOD0130.md (verifier, 14:20 to 14:40 ET). Registered (see header). The
lead registers it after a verifier GO on the fixes (SELFMOD_FIXES.md) and before the first full GPU generation.

The order (13:39 ET): "stop training shit that's frozen... everything that could be a bottleneck needs to be able to be
optimized... including even what tests to run." The base system is silicyte-0128 (PREREG_BOOTSEED_V1.md, A1 to A4). Coordinator
input (14:08 ET), from weightmap/RESULT_LORA_ANATOMY_S1.md: 0128 refits a fresh LoRA every round, and consecutive rounds' dW have
cosine 0.045 to 0.087. So that loop compounds only through its data, and weight carryover is a first-class knob here.

## 0. Status: EXPLORATORY. No compounding claim.

At this compute no design gives a powered test of compounding. Two independent sims agree: the builder's (sim_m2.json) and the
verifier's (vsim.py, with a cost model from the 0128 tel).
- **The compounding test (SHAPE) is not a test here.** It has power of at most 0.04 to 0.08 in every planted cell, including a
  planted 6x gain.
- **The null expectation is to trail.** With no useful edits, SELFMOD trails the fixed recipe at matched GPU-hours. The matched
  comparison reads BEHIND 90% of the time at 20 GPU-h per seed and 93% at 40 GPU-h.
- **Break-even is about 3.3x.** An edit must add about +0.40 to +0.45 d50 per round, which is 3.0x to 3.3x the base gain of 0.2,
  just to tie the control at matched compute. The cause is cost: each generation pays for about 2.8 candidate rounds and keeps one.

So this study makes no compounding claim, and it carries no COMPOUNDS, LINEAR-GROWTH or NULL label. LEVEL passes 84% of the time
under the null, because the base recipe grows linearly, so it says nothing about self-modification.

Its reads are descriptive. Each is printed beside its sim operating characteristic (sec. 6):
1. knob trajectories;
2. planted-knob recovery (the SABOTAGE arm);
3. REPORT gain per GPU-hour against the 0128 FRONTIER seeds.

MATCHED is the only directional read, and only AHEAD is informative.

## 1. What is built

The loop is Qwen3-8B + LoRA on the consol_v1 depth world, run generation by generation. In each generation the incumbent and its
challengers run one round from A_g, are scored on SELECT, and the best is kept. Everything except the scoreboard is adjustable,
including weight carryover, LoRA anatomy, search, curriculum and the proposer's own context. The proposer is the same 8B model, and
its weights are trained on its past winning edits. No Claude is in the loop.

## 2. Frozen: only the scoreboard, and why

- **SELECT_k**: frozen/SELECT_<59000 + 100 k>.json, 6 tasks x 30 depths = 180. It is the ONLY quantity the loop may use to choose
  between candidates.
- **REPORT_k**: frozen/REPORT_<69000 + 100 k>.json, 10 x 30 = 300. It is never used for a decision. Gen mode opens the REPORT files
  only to read their input strings into the exclusion set that keeps those inputs out of practice pools (smcore.all_ruler_ins). It
  never scores, returns or prints REPORT rows.
- **Depth grid**: 1..20, then even depths 22..40.
- **Generator**: the sibling's opengen.make_task_open. It applies every consol.make_task filter at any depth. Its md5 8915e834 is
  hardcoded in smcore and pinned in frozen/OPENGEN_PIN.json.
- **sha256s** (built 2026-11-05 13:57 ET), hardcoded in smcore.RULER_SHA (F6) and checked at every load against those constants,
  not against a writable json:

  | ruler | sha256 |
  |---|---|
  | SELECT_59100 | e7a80534e2d8c1aa38bf9c28e04bbb7edffa229ccb49036ebc52d09a74a0cb11 |
  | SELECT_59200 | be1970f1643800d7c2f8e9f8983da71d3092ae217f313acf1f87f67f386a7cd0 |
  | SELECT_59300 | f0d978224474451ac1b781f3dc258a01c00ad1277b18b7b69411f45d3b6f9b31 |
  | SELECT_59400 | 7ac8ab76da1f1b86919dde503714170c569aff6e806a76a8701e54e776f2c77e |
  | REPORT_69100 | b65cf1cc3e719082f5c0380fd70a51d67f0ac0da17a46a51300fe77987a1357b |
  | REPORT_69200 | 169c5b359f24769ca9b6bf3c49243591c46228ee7a571a6c5638395de60ab7d5 |
  | REPORT_69300 | 634f6bb8bee5d30d8f3b5ac9a25f411693b43822e86fc9e93a0fa4288563e723 |
  | REPORT_69400 | 4af0f665899c98e269deb67b6e081f7501acb09cdfdd348a7137eb13b4e132a9 |

  frozen/*.json and OPENGEN_PIN.json are made read-only (chmod a-w).
- **Scoring rule**:
  - beam B 4, temperature 1, no rollouts, max_steps max(12, depth + 2);
  - tasks scored in ascending depth;
  - after 3 consecutive grid depths with 0 hidden-correct, every deeper task is recorded as failed and flagged.
- **Verifier**: consol.run_prog.
- **Statistics**:
  - SELECT AUC = sum over grid depths of w_d x the hidden-correct rate, with w 1 up to depth 20 and w 2 above;
  - REPORT d50 (the 0128 unit) and REPORT AUC, reported side by side. Selection maximises AUC, so REPORT AUC is the matching
    descriptive read.

**Why only the scoreboard is frozen.** A system that can change its scoreboard can fake progress. It can pick easier tests, loosen
the verifier, or grade itself on tasks it trained on. Every other part of the loop may be wrong, and the system is allowed to find
that out and change it. The scoreboard is the one part whose errors the system could exploit in its own favour. So it is fixed
before the first model call and its sha256 is checked at every load.

The SELECT and REPORT split follows from the same reasoning. Choosing on SELECT makes SELECT absorb the selection bias. REPORT never
enters a decision, so it stays an unbiased read of the chosen lineage.

**Operator channel (F8).** REPORT values never reach the live holder log: run_selfmod.sh sends the REPORT pass to report/*.json and
report_stdout.log. No amendment made after the first REPORT write may change selection, knobs, margin or the proposer. Only
infrastructure fixes are allowed after that point, and each one is logged with its time.

**Overlap.** The smoke check at G 3 printed OVERLAP_OK. The verifier added the open0129 RULER_49100..49400 comparison: all 32 pairs
are 0. The check is re-run at G 30 before launch into smoke/overlap_check_G30.log, and read_selfmod.py requires OVERLAP_OK there.

## 3. Adjustable (knobs.py SPACE, 27 knobs; C_0 = the 0128 FRONTIER recipe)

| group | knobs (C_0 value) |
|---|---|
| weights and training | init fresh or warm (fresh); lr (2e-4); lr_sched const, cosine or linear (const); epochs (1); rank (16); alpha_ratio (2); targets all7, mlp, mlp_in, attn or q_mlp (all7); layers all, top, ends, bottom or mid (all); batch (16); hind_ratio (1.0); recency (0); meta_rep_max (1) |
| data selection | keep_filter, a sandboxed expression ("True"); dmin_offset (0) |
| search | beam (4); max_steps (10); samples (0); temperature (1.0) |
| curriculum (its own practice tests) | data_maxdepth (10); data_n (300); front_lo_off (-1); front_width (5); front_n (200); front_shape (uniform); zipf_exp (1.1) |
| proposer context | archive_window (16); prop_temp (0.8); a note of at most 400 characters |

**Recency (P5).** recency N keeps the lineage rows of generations gg >= g - N, that is, the last N completed generations. It also
keeps this round's new rows, and seed256 is always in. So with warm, recency 1 means the previous generation's rows plus the new
rows.

**Proposer-context knobs (F4).** archive_window, prop_temp and the note take effect at commit, carried from the generation's model
edit whatever the decision. They never cost a SELECT round:
- random edits never pick them;
- a proposal that sets only these knobs uses its slot without a round;
- any candidate whose (run knobs, torch seed) equal the incumbent's reuses cand 0 with delta 0.

**Validity** (smoke_parts.py; all cases as expected):
- An edit changes 1 to 4 knobs.
- Exact types:
  - choice knobs need the exact type of a listed value;
  - an integral float such as {"beam": 8.0} is safely coerced to the int 8 (E2);
  - bools are rejected for every non-bool knob;
  - range checks apply.
- A warm start keeps rank, alpha, targets and layers.
- **Filter sandbox**:
  - expressions only;
  - names: row, len, min, max and abs;
  - subscripts only of the form row["<key>"];
  - none of: Mult, Mod (E1) or Pow; attributes; other calls; lambdas; comprehensions; dunders;
  - numeric constants up to 1e4 and string constants up to 64 characters.
- **Probe.** The filter is evaluated on 400 probe rows in a child process (python -I) under RLIMIT_AS 1 GB, RLIMIT_CPU 10 s and a
  15 s wall limit. It fails closed. The probe rows have no "meta" source (E5).
- **At training time (F3):**
  - a filter that keeps under 20% of the candidate's real rows refuses the candidate;
  - a runtime error or more than 120 s refuses it (fail closed);
  - the incumbent's filter is never refused; it is reset to "True" instead, and the reset is logged.
- The predicted cost is at most 2x the incumbent's and at most 7,200 s.

WEIGHTMAP edit types (0131) are rejected until the 0131 spec exists. Recipe-code patches are not built.

## 4. One generation (selfmod.py gen k)

1. **Candidates.**
   - The incumbent.
   - A probe (C_g again with another torch seed), at g 0, 1 and every 4th generation.
   - 1 model edit.
   - On odd g, 1 random edit.
   - Every proposer completion is saved to gen_g/proposer_samples.jsonl, with its parse and validity result.
2. **Practice search.**
   - Data pool seed 80000 + 100 k + g; frontier pool seed 90000 + 100 k + g.
   - Common random numbers across the candidates of a generation, and searches are shared where the keys match.
   - Every ruler input is excluded from every pool.
3. **Training.**
   - Rows: seed256, plus the lineage rows, plus this round's rows, plus the proposer's own winning (prompt -> edit) rows.
   - smtrain uses the knobs.
   - A warm start asserts before step 1 that there are more than 0 trainable params and that every saved tensor of A_{t-1} equals
     the live tensor.
   - After training it asserts the adapter changed, and logs cos(B, B_prev) (S2).
4. **SELECT** for every candidate that was trained.
5. **Decision.** The best challenger wins iff its delta exceeds the margin max(0.1, 1.0 x s_diff), with
   s_diff^2 = (2 x 0.35^2 + sum of the probe deltas^2) / (2 + n). Ties go to the incumbent.
6. **Lineage.** lineage.jsonl records:
   - every candidate, its delta, and any refusal or reuse;
   - prop_set;
   - opengen_md5;
   - pred_cost_s and GPU seconds by phase;
   - warm_check.

## 5. Arms and control

- **SELFMOD**: K = 4, k = 1..4. A_0 is seed k's 0128 P_0, and P_0's structure equals C_0 (verified).
- **CONTROL**: the running 0128 FRONTIER seeds k = 1..4, with their saved P_t scored on REPORT_k (report_ctrl, every second round).
  - GPU-hours per control round = round_s - search_s x 300 / 800.
  - MATCHED is read at H*_k = min(SELFMOD hours, control hours). If the control stops early (about 7 GPU-h by round 9 at 14:23 ET),
    MATCHED is read at about SELFMOD generation 5.
- **SABOTAGE** (P6; the positive control, and it takes priority over BESTOF for the first third GPU):
  - 2 seeds, k = 1 and 2, in their own state directories. They do not pair with the control.
  - They start from C_0 plus the planted defect keep_filter 'row["src"] != "own"', which drops every verified own-solution row.
  - Read: per seed REVERTED (the planted filter was replaced by an ACCEPTED edit of the loop), RESET (it was lost only through the
    automatic F3 incumbent filter reset, which does not count), or HELD. REVERTED-ALL iff both seeds read REVERTED.
  - Sim (verifier 4e, at -0.15 per round): recovery per seed is 0.46 to 0.58 with an informed proposer, and 0.11 with a random one.
    So both seeds revert with p about 0.2 to 0.35 if the proposer is informed and about 0.012 if it is random.
  - The harm of this defect is not measured in 0128. The sabotage incumbent's own REPORT curve shows it.
- **BESTOF**: replicate seeds in place of edits. Run only if a fourth GPU frees.

## 6. Reads (descriptive; read_selfmod.py), each with its operating characteristic

Verifier cost model; 20 GPU-h per seed (about 10 generations); K 4.

| read | definition | null expectation / power |
|---|---|---|
| VOID | ruler sha256 vs the hardcoded values; OVERLAP_OK in the G 30 log; opengen md5 equal to the pin in every generation; gen-0 A_0 md5 equal to the 0128 P_0; REPORT used other than as an input-exclusion set | must be clean before any other read is quoted |
| KNOBS | each knob's value per generation, per seed | accepted edits under the null: about 2.5 per seed in 10 generations, all drift |
| SABOTAGE | planted filter reverted in both seeds | random proposer about 0.012; informed about 0.2 to 0.35 |
| REPORT per GPU-hour | REPORT d50 and AUC against cumulative GPU-hours, next to the 0128 FRONTIER seed | descriptive |
| MATCHED | paired SELFMOD minus CONTROL REPORT d50 at H*_k; two-sided t at 0.04 (crit 3.482, df 3) | BEHIND 0.90 under the null; AHEAD 0.015 at +0.4 per round, 0.09 at +0.6, 0.31 at +1.0 |
| SHAPE | second-half minus first-half REPORT slope per GPU-hour | descriptive only; power at most 0.08; no claim |
| PROPOSER | parse and valid rates; model delta minus random delta on odd generations | PROPOSER-WEAK iff the valid rate is below 0.25 after 3 generations, or the mean model-minus-random delta is <= 0; t power 0.07 to 0.11 (close to a coin flip) |

STATUS UNDERPOWERED if fewer than 3 seeds reach 6 generations with REPORT readings by 2026-11-10 23:59 ET.

## 7. Sims

Sources:
- the builder: sim_selfmod.py, sim_m.py and sim_m2.py;
- the verifier: /N/scratch/bsmensah/verify_selfmod0130/sim/vsim.py.
Both use numpy PCG64 with 1,000 to 2,000 reps per cell.

**Cost model (P2, verifier 4b, from the 0128 tel):**
- control round: 2,100 + 150 t s, i.e. round_s - search_s x 300 / 800 on FRONTIER_s2 tel_0..8;
- SELFMOD generation: 1,190 s shared + 660 s per searched challenger + (530 + 180 g) s per trained candidate.

| 20 h per seed | SHAPE | AHEAD | BEHIND | knob found | SELFMOD d50 (control 6.9) |
|---|---|---|---|---|---|
| NULL | 0.002 | 0 | 0.901 | 0.073 | 4.70 |
| +0.2 per round | 0.006 | 0 | 0.397 | 0.493 | 5.34 |
| +0.4 | 0.018 | 0.015 | 0.059 | 0.641 | 6.36 |
| +0.6 | 0.034 | 0.093 | 0.009 | 0.751 | 7.74 |
| +1.0 | 0.041 | 0.305 | 0 | 0.856 | 10.75 |

- At 40 h: NULL BEHIND 0.931; +0.4 diff +0.17.
- Break-even: about +0.45 per round at 20 h and +0.40 at 40 h, i.e. 3.0x to 3.3x the base gain.
- The design choice (1 model edit, a random edit on odd g, probe every 4th, margin z 1.0) comes from sim_m2.json. It is the best
  design that keeps a proposer control. The verifier's replication matches it within MC error.
- One-round greedy selection undervalues edits that pay over several rounds. If the first-round effect is 35% of the steady effect,
  the planted +0.4 is found in 0.44 of seeds, against 0.64 when the full effect shows in the first round. This applies to warm
  start and to curriculum.

## 8. Compute (P3)

- **Cost per seed.** About 2.0 H100-h per generation (1.1 to 2.7 over gens 0..9), so about 20 GPU-h per seed for 10 generations.
- **Holders.** H7 12693135 and H8 12693136 (h100-single, 2 days). At 14:23 ET their start estimates were 20:54 and 21:03 ET.
  - Seeds 1 and 2 run round-robin on H7; seeds 3 and 4 on H8.
  - 10 generations per seed fit in about 40 h, which is one holder life, ending about 2026-11-07 13:00 ET.
  - UNDERPOWERED only if a holder starts after about 2026-11-10 02:00 ET. So P(UNDERPOWERED) is low, and seed drops drive it rather
    than the start time. Mitigation: run_selfmod.sh retries once, and drops a seed only on exit 9 or two failures.
- **Renewal.** A renewal holder must be queued by about 2026-11-07 12:00 ET. The h100-single pend time today is about 7 h.
- **Control REPORT scoring.** About 6.4 H100-h, on the first GPU any other lane frees.
- **SABOTAGE.** 2 seeds, about 40 GPU-h, on a third GPU if one frees.

## 9. Prediction (before any GPU data)

- MATCHED: BEHIND 0.65; NO-DIFFERENCE 0.30; AHEAD 0.05.
- SABOTAGE: REVERTED-ALL 0.25.
- PROPOSER-WEAK: 0.6. The adapter was trained to emit one op-name token; the base-weights rate from the GPU smoke is the cheap
  fallback.
- Knobs most likely to move: init warm, max_steps and data_maxdepth, lr_sched, epochs.
- STATUS UNDERPOWERED: 0.10.

## 10. Prior art (cited; no code copied)

- **Darwin Godel Machine** (Zhang, Hu, Lu, Lange, Clune; Sakana AI 2025): an archive, self-proposed children, empirical selection.
- **STOP** (Zelikman, Lorch, Mackey, Kalai 2023): a self-improving scaffold with a fixed LM, including attempts to escape its
  sandbox. That is the reason for the sandbox and the frozen scoreboard here.
- **ADAS** (Hu, Lu, Clune 2024): a meta agent that reads an archive of designs.
- **Population-based training** (Jaderberg et al. 2017): exploit and explore over hyperparameters, with inherited weights. The sims
  measure the matched-compute cost of this.
- **AlphaEvolve** (Google DeepMind 2025): LLM program edits plus an evaluator. That is the recipe-patch idea, which is not built
  here.
