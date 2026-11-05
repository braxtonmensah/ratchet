# PREREG bootseed_v1 (silicyte-0128): does a model that trains on its own verified solutions improve FASTER each round?

Registered 2026-11-05 00:1x ET (PowerShell clock) by the Silicyte lane session, before any bootseed model call. Successor to
silicyte-0127, whose ARC design hit its registered base-rate kill (4 of 80 HELD tasks at 64 samples; floor 8).

## 1. The loop (the improver's own weights change)

Qwen3-8B with a LoRA policy searches the consol_v1 depth-knob world (beam B 4, at most 10 steps), keeps its own verified programs
at the frontier (depth >= floor(d50)) plus 1:1 hindsight paths from failed searches, retrains, and repeats: the fourth-law lane's
bootllm2 frontier loop (PREREG_BOOTLLM_FRONTIER_V1.md, F1 to F3 + A1), copied to /N/scratch/bsmensah/silo/bootseed/code/bootseed.py
(md5 ee33615f328b133c0c0c1c840de1768d) from bootllm2.py (md5 1f9e257480e18b85d9e803497b023d26). Its record: d50 2.842 -> 4.200
over rounds 0 to 9 on one seed, read LINEAR (RESULT_BOOTLLM_FRONTIER_V1.md).

## 2. The one change, and why

bootllm2 scores round t on pool seed 9000 + t, the same pool for every run; beam search is deterministic given the adapter, so pool
difficulty adds the same offset to every seed's curve and a seed-level test would read pool luck as compounding. bootllm2 also TRAINS
on its verified solves from that eval pool (bootllm2.py:122, frontier_examples(tr + ev rows)), so simply fixing the eval pool would
train on the measured tasks. bootseed therefore keeps bootllm2 byte-for-byte (its per-round pool 9000 + t still feeds training and
d50 as before) and ADDS one fixed MEASUREMENT pool, make_pool(consol_v1, 29000, 300 tasks, depth 1 to 10), scored every round of every
seed and never passed to training (it enters only summary.d50_fixed and round_t.json fixed_rows). The primary quantity is d50_fixed.
Copy md5 ee33615f328b133c0c0c1c840de1768d (diff vs bootllm2.py: docstring, 3 lines after summarize(ev), 1 summary.update line, the
round json gains fixed_rows).

## 3. Seeds

K = 4 independent runs (runs/s1 .. s4) of the identical code and arguments. There is no seed knob: runs differ through the training
step's unseeded randomness, as boot_llm2_rep differed from boot_llm2. R = 8 (rounds 0 to 8 scored). The existing boot_llm2 and
boot_llm2_rep trajectories are EXCLUDED: they were scored on per-round pools (sec. 2). Their rounds are never read by this study.

## 4. Quantities and rule

- d50_{k,r}: summary.d50_fixed, the logistic d50 (bootllm.summarize) of seed k's policy P_r on the fixed measurement pool 29000.
- SHAPE (primary): c_k = OLS quadratic coefficient of d50_{k,r} on r = 0..R; t = mean(c) / (sd(c) / sqrt(K)), df K - 1;
  COMPOUNDS-SHAPE iff t > 2.605 (one-sided alpha 0.04, df 3). Basis: the seed-level rule's false-positive rate is 0.020 to 0.054
  across VERDICT_SIM.md sec. 4's grid and 0.035 to 0.045 with an own round 0 per seed (power_selfft/sim_registered_0127.jsonl);
  here round 0 is P_0 on the fixed pool, identical for all seeds by construction (deterministic), so the shared-round-0 inflation of
  0127 is re-simulated at the measured noise before any label (sim_0128.js, design agent) and the alpha is lowered if needed, by an
  amendment dated before seed data beyond round 2.
- LEVEL: mean over seeds and rounds of d50_{k,r} - d50_{k,r-1}; LINEAR-GROWTH iff its 95% lower bound (t across seeds) > 0.
- Printed with every read: per-seed d50 curves, per-round gains, tau_hat (between-seed sd of gains), m_hat per seed with its CI,
  per-depth eval and train solve counts (telemetry from round_t.json eval_rows), own_new, hindsight_new, train_examples, round_s.

## 5. Labels, in order

1. VOID: round 0's summary.d50 (pool 9000, the unchanged bootllm2 path) differs from boot_llm2's round 0 (2.842, 66 correct), or
   round 0's d50_fixed differs across seeds (P_0 and beam search are deterministic); or any run's code md5 differs from sec. 1.
2. UNDERPOWERED: fewer than 3 seeds reach r = 6 by 2026-11-10 23:59 ET, or the re-simulated power at m = 1.2 at the measured tau_hat
   and gain is below 0.6.
3. COMPOUNDS: SHAPE passes AND LEVEL passes ("accelerating (m > 1)", with m_hat and its CI).
4. LINEAR-GROWTH: LEVEL passes, SHAPE fails.
5. NULL: neither.

## 6. Prediction

Quantity: mean c over seeds (d50 units per round squared). Point 0.00, 80% band [-0.03, +0.03]. P(COMPOUNDS) 0.08. Most likely label
LINEAR-GROWTH (the one seed on record: mean gain +0.124 per round, curvature slope -0.008 [-0.060, 0.049]).

## 7. Compute

Measured round_s on boot_llm2 (rounds 0 to 9): 2,095 to 4,494 s, rising with the training set (802 to 6,420 examples). One seed of
R = 8 is about 6.5 to 7.5 H100-hours; K = 4 is about 28 H100-hours. Slots: holder 12678495 (seed 1 from tonight), 2-day holders
12679725 / 12679726 when they start, h100-debug 1 h jobs (rounds resume per round_t.json).

## 8. Named next arm (registered by amendment before its first job)

GUIDE: the same loop whose training depth window is chosen each round by its own measured learning progress per depth (a fixed,
deterministic rule; no Claude in the loop), paired seed by seed with the fixed frontier rule. Prior art: learning-progress curricula
(Oudeyer et al.; Matiisen et al. 2017).

## AMENDMENTS

- A1 and A2 registered 2026-11-05 00:20 ET (PowerShell clock), before any silicyte-0128 model call (no seed has run). Text below is copied verbatim from DESIGN_0128.md secs. 7 and 8 (design agent, independent of the lead's draft); sim_0128.js sha256 prefix c8af0e1fc01b28aa. They replace secs. 3, 4 (critical value per K), 5 (VOID additions) and 7 (compute: about 47 H100-hours for K 4 x R 10, 11.8 per seed; about 91 with GUIDE). Code for every seed, s1 included: bootseed0128.py (A1 seed knob; k = 1 keeps bootllm2's pools; safe per-round resume) once its verifier writes GO; the earlier ee33615f copy is superseded before use.

## 7. AMENDMENT A1 to PREREG_BOOTSEED_V1 (text to date and register before any seed's round-2 data is read)

> **A1 (silicyte-0128).** Basis: sim_0128.js (md5 at registration), sim_0128_stdout.txt. With the training pools 9000 + t and 19000 + t shared
> by every seed and no seed knob, the registered seed t-test calls linear growth compounding 19.8% (measured noise split) to 35.1% (if only GPU
> nondeterminism separates runs) of the time at K = 4, R = 8. No critical value restores both FP 0.04 and usable power. Changes:
> 1. **Seed knob and own pools** for seeds k = 2..K: pool seed 9000 + 100 k + t (feeds training and summary.d50 as in bootllm2) and frontier pool
>    seed 19000 + 100 k + t. Rows are pre-shuffled random.Random(1000 k + t + 1) and torch.manual_seed(1000 k + t + 1) is set before each train. The hindsight
>    shuffle is Random(1000003 k + len(rows)). Own P_0^k = LoRA on seed256.jsonl pre-shuffled Random(k), torch.manual_seed(1000 k). s1 is unchanged.
>    The fixed measurement pool 29000 is unchanged and never trained on.
> 2. **R = 10** (rounds 0..10 scored on pool 29000; round 10 is scored only, not trained). **K = 4** (K = 6 if holder supply allows, decided by
>    date before any seed passes round 3, never from data).
> 3. **VOID additions.** P_1 adapter md5 identical across any two seeds (no seed separation). Any own.jsonl row count different from
>    train_examples - 256 of its round (the duplicate-row defect, sec. 0 point 3). FROZEN pool-9000 reading not 66 / 2.842, or a pool-29000
>    FROZEN reading that differs from the registered value. Positive control FAIL.
> 4. **Resume guard.** Before every restart, own.jsonl is trimmed to the last completed round's train_examples - 256 (boot2_resume.sh:24-30 logic),
>    or the loop writes per-round own_t.jsonl (bootseed0128.py C4).
> 5. **Labels unchanged in order.** The UNDERPOWERED floor (power < 0.6 at m = 1.2) is re-evaluated with the sim at tau_hat measured from the K seeds.
>    The registered critical value 2.605 (df 3) becomes 2.191 if K = 6 (df 5).
> Prediction unchanged: mean c 0.00 [-0.03, +0.03], P(COMPOUNDS) 0.08, most likely LINEAR-GROWTH or, given LEVEL's 0.53 power, NULL.

**Point, band and gate (for the registration table).** Quantity: mean over seeds of c_k (d50 per round^2) on pool 29000. Point 0.00, 80% band
[-0.03, +0.03]. Gate: COMPOUNDS-SHAPE iff t > 2.605 (K = 4) with FP 0.045 and power 0.77 at m = 1.2 (SIM OWN K4 R10). Kill test: LEVEL fails
(across-seed 95% lower bound of mean gain <= 0) means no claim about acceleration is read, whatever c says.

## 8. AMENDMENT A2: GUIDE arm (learning-progress curriculum, paired seeds)

> **A2 (silicyte-0128 GUIDE).** Same loop, same seed knob as A1. For seed k the GUIDE run forks from FRONTIER seed k after round 0 (copies P_0, the round-0
> search and P_1). Each round t >= 1 its training depth window is set by a deterministic rule on its own data, with no model and no Claude in the decision:
> s_t(d) = hidden-correct rate at depth d on the round-t data pool (about 30 tasks per depth); LP(d) = s_t(d) - s_{t-1}(d); L(d) = mean of LP over
> d-1..d+1 within 1..10; c = argmax L (ties: deeper). Window [lo, lo + 5], lo = max(1, c - 1, dmin - 1) (the F3 width). If max L <= 0, use F3.
> F1, F2, A1 and dmin are unchanged. Implementation: bootseed0128.py guide_window.
> Quantity: per pair, OLS slope of d50 (pool 29000, r = 0..R) GUIDE minus FRONTIER, and the same for the quadratic c. Two-sided t across pairs at 0.04.
> Labels: GUIDE-FASTER / GUIDE-SLOWER / NO-DIFFERENCE. NO-DIFFERENCE is read as "below 0.2 d50 per round", not as equal.
> Prior art: learning-progress curricula (Oudeyer, Kaplan and Hafner 2007, intrinsic motivation by learning progress; Matiisen,
> Oliver, Cohen and Schulman 2017, teacher-student curriculum learning, which picks tasks by the slope of the learning curve). Claimed here:
> only its application to an LLM's own-verified-data loop on this rig.

Power (sim_0128.js sec. 3, m = 1, two-sided 0.04):

| noise | pairs K | R | FP | delta 0.05 | 0.10 | 0.15 | 0.20 |
|---|---|---|---|---|---|---|---|
| SPEC (independent) | 4 | 10 | 0.040 | 0.074 | 0.140 | 0.239 | 0.396 |
| SPEC | 6 | 10 | 0.037 | 0.081 | 0.209 | 0.452 | 0.702 |
| MEAS, arms share all common shocks | 4 | 10 | 0.038 | 0.082 | 0.244 | 0.441 | 0.698 |
| MEAS, arms share half | 4 | 10 | 0.032 | 0.059 | 0.164 | 0.318 | 0.479 |

A GUIDE effect has to be at least the size of the whole current gain (0.15 to 0.2 d50 per round more) before K = 4 sees it at 40 to 70%. The arm is
registered as exploratory, and its telemetry (per-depth LP, window choice) is the main deliverable for "watch, guide, help".



- A3 registered 2026-11-05 00:37 ET (PowerShell clock), before any bootseed0128.py model call (seeds 2 to 4 and GUIDE have not run; seed 1 runs ee33615f since 00:27:45 and is unaffected). Text from A3_DRAFT.md with the four fixes of VERDICT_BOOTSEED_K2.md applied:

> **A3 (silicyte-0128, code and measurement pool).** Supersedes the code named in A1 (the reference bootseed0128.py, never run). Basis:
> VERDICT_BOOTSEED_V1.md REQUIRED 1 to 5 and BUILD_0128_K2.md.
> 1. **Code.** Every seed and both arms run /N/scratch/bsmensah/silo/bootseed/code/bootseed0128.py md5 **c54e21d253f53ee246352f74c83e085b**
>    through run_bootseed0128.sh md5 **42b5c2acaa2a27a2c96b6f43c39c2296**. At start the code asserts the lib copies
>    (silo/bootseed/lib: consol.py 002ff8e65f7b2b5ef0021c654e5ff3dd, reachlaw.py 4187b71d89fc61cc0fab23ec34b2cfbe, ident.py
>    fbac440b535c03668f91900f5c1ab2b2, bootllm.py e50ef05ec7a7eb6df7dfe1c7ab5d24c0) and the inputs (silo/bootseed/inputs: seed256.jsonl
>    617d4cc6758fa93bd32dfc7b52f73850, exp_n256/adapter_model.safetensors 141a87874ee48870281173c6dad505b0, exp_n256/adapter_config.json
>    3db28aefa04dbdd8102d937bc08afd0d, boot_llm2_round_0.json bcb164b7e5633591d35ad09feb3eb49c) and exits 9 on any mismatch.
>    FRONTIER seed 1 is runs/s1 running the registered ee33615f bootseed.py (launched 2026-11-05 00:27:45 ET under VERDICT_BOOTSEED_S1.md);
>    it is not modified. bootseed0128.py touches seed 1 only on a takeover from a completed round or for GUIDE_s1. Every launch passes
>    t_to 10 (a smaller t_to saves that round as scored-only and every later round then stops with MISSING_POLICY).
> 2. **Measurement pool rule.** The registered quantity d50_fixed is read only from MEAS = BL.make_pool(consol_v1, 29000, 300, depth 1..10),
>    B 4, max 10 steps, scored on every round of every seed and arm (rounds 0..R; round R is scored only). MEAS rows are stored as round_t.json
>    fixed_rows and summary.d50_fixed and never enter frontier_examples. Frontier pools exclude any task with a MEAS input, and data-pool rows
>    with a MEAS input are dropped from training (both counted per round: front_meas_hits, dp_meas_dropped). Measured before launch: 0 shared
>    tids, 0 identical tasks and 0 shared inputs between MEAS and the data pools of k = 1..4, t = 0..10 (13,200 tasks), and 0 MEAS-input hits in
>    the frontier pools of k = 1..4 at t = 0, windows [1,6], [2,7], [3,8] (2,400 tasks). Pool 9000 is used only by the canonical check and as
>    seed 1's round-0 data pool.
> 3. **Seed 1 is bootllm2.** For k = 1 (both arms) the code follows bootllm2.py md5 1f9e2574 exactly: P_0 = exp_n256 (no P_0 training), data
>    pool BL.make_pool(9000 + t, 300, 10), frontier pool bootllm2.frontier_pool(19000 + t, 200, F3 window) with held-only exclusion (plus the
>    MEAS exclusion of point 2, which removed 0 tasks where measured), training rows seed256 + own_0..own_t in round order with no pre-shuffle
>    and no torch.manual_seed, hindsight shuffle Random(len(rows)). Seeds k >= 2 use the A1.1 knob: data pool 9000 + 100 k + t, frontier pool
>    19000 + 100 k + t, pre-shuffle Random(1000 k + t + 1), torch.manual_seed(1000 k + t + 1), hindsight Random(1000003 k + len(rows)),
>    own P_0^k (seed256 pre-shuffled Random(k), torch.manual_seed(1000 k)). The only additions inside a bootllm2 round are the MEAS solve on the
>    resident scorer (no RNG draw: eval mode, deterministic beam) and the per-round own_t.jsonl files. The same file can take over seed 1 from
>    any completed round of an ee33615f or bootllm2 state dir: a legacy own.jsonl is split into own_u.jsonl per completed round and checked
>    against train_examples - 256 (exit 8 otherwise); rows past the last completed round are ignored.
> 4. **In-run gate.** For k = 1, round 0: exit 7 (VOID) unless the data pool reads 66 correct, d50 2.842, nan 0 and its eval rows
>    (tid, depth, v, c, exec) equal boot_llm2/round_0.json eval_rows. exp_n256's MEAS reading is written once as FROZEN
>    (silo/bootseed/frozen/FROZEN_29000_exp_n256.json) by the FIRST process that produces it (first writer wins; tonight that is the first
>    seed-2-to-4 canonical check, because ee33615f never writes FROZEN); its md5 is printed in the log and is the registered pool-29000 FROZEN
>    value of A1.3. The lead checks by hand, before any seed 2 to 4 data is read, that runs/s1/round_0.json fixed_rows equal FROZEN row for
>    row (the code checks it automatically on a seed-1 takeover); a mismatch is VOID. On every resume and at every start of a k >= 2 process,
>    exp_n256 is re-scored on pool 9000 (must equal boot_llm2 round 0 row for row) and on MEAS (must equal FROZEN row for row), else exit 7.
>    The check restores the torch CPU and CUDA RNG states afterwards, so it is RNG-neutral for the round that follows. A k = 1 fresh start
>    skips it (round 0 is the same reading). Compute: about 10 H100-hours per FRONTIER seed plus about 2,300 s (0.65 h) of canonical
>    check per restart.
> 5. **VOID rule of sec. 5 restricted.** "Round 0 d50_fixed differs across seeds" applies only to k = 1 against FROZEN. For k >= 2 round 0
>    differs by design (own P_0^k) and the A1.3 P_1 adapter md5 rule replaces it.
> 6. **A2 note.** guide_window reads only the data pools (this round's data-pool rows and round_{t-1}.json eval_rows, which are data-pool
>    rows). A depth with no data-pool tasks in either round has LP 0.
> Labels, prediction, K, R and critical values: unchanged from A1.


## AMENDMENT A4 DRAFT: extension for late takeoff (written 2026-11-05 08:36 ET; to be registered after a verifier's GO and before any seed's round-11 data exists. At 08:25 ET seed 1 had finished round 6, seed 2 round 3, seed 3 round 2 and seed 4 round 1. No seed has run past round 10, so this text is fixed before any extension data.)

Why. A 10-round test only sees acceleration that starts inside 10 rounds. The registered R = 10 read stays as written, and a
LINEAR-GROWTH or NULL label from it is worded "within 10 rounds". Two things in the design hide a later takeoff. First, the seeds
stop at round 10. Second, the ruler has a ceiling: MEAS holds depths 1..10, the scoring beam stops at 10 steps, and at the measured
mean gain of 0.26 d50 per round, linear growth alone saturates it near round 25.

1. **Extension.** Every FRONTIER seed continues past round 10, up to R_ext = 30 or the end of holder time on 2026-11-10 at 23:59
   ET, whichever comes first. Every round from 10 to R_ext - 1 is trained, round R_ext is scored only, and the code is otherwise
   unchanged. GUIDE follows the same rule. The mechanics of continuing a seed whose round 10 was scored only must be verified
   before use: the builder reports how, and the verifier checks that no row is duplicated or dropped.
2. **Deep ruler.** MEAS_DEEP is a new fixed pool from the same world (consol_v1): pool seed 39000, depths 1..D_deep with D_deep
   at least 20, and an equal number of tasks per depth. It is scored with beam B 4 and max steps of at least D_deep. Its rows
   are never trained on, and it gets the same exclusions as MEAS (frontier pools drop any task with a MEAS_DEEP input; data-pool
   rows with a MEAS_DEEP input are dropped). It is built, and its sha256 committed, before it scores any policy. Then every saved
   policy P_0..P_R of every seed is scored on it; past adapters are re-scored if their files exist (measurement only). The
   quantity is d50_deep_{k,r}.
3. **Late-takeoff test L** (pre-registered, on d50_deep). For each seed k, delta_k = the OLS slope over rounds 11..R_k minus the
   OLS slope over rounds 0..10. t = mean(delta) / (sd(delta) / sqrt(K)), df K - 1. LATE-TAKEOFF-SHAPE holds iff t > 2.605
   (K = 4, one-sided alpha 0.04), the same unit and alpha as A1's curvature test. Power (ext/sim_late_takeoff.js, 2,000 runs
   per cell, measured noise: gain 0.26, between-seed sd 0.107, measurement sd 0.17):
   - false positive under linear growth, R = 30: 0.034 to 0.054;
   - power for takeoff starting at round 10, 15 or 20 with m = 1.05 to 1.2, R = 30: 0.92 to 0.96;
   - the same on the depth-10 ruler: 0.01 to 0.03, which is why the deep ruler is required.
   The sim is re-run at the measured d50_deep noise before any extension label, and the alpha is lowered if the false-positive
   rate exceeds 0.06.
4. **Extension labels**, read when every seed reaches R_ext or at 2026-11-10 23:59 ET:
   - UNDERPOWERED-EXT if fewer than 3 seeds reach round 20;
   - LATE-TAKEOFF if LATE-TAKEOFF-SHAPE passes and the deep LEVEL (A1's LEVEL rule on d50_deep over all rounds) passes,
     reported with m_hat over rounds 11..R and its CI;
   - NO-TAKEOFF-BY-R if LEVEL passes and SHAPE fails, worded with the R reached;
   - NULL otherwise.
   A1's R = 10 labels are read first and are not changed by any of these.
5. **Prediction** (stated now): P(LATE-TAKEOFF) = 0.10; most likely NO-TAKEOFF-BY-R.
