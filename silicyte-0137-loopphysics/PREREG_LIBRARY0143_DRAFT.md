# PREREG_LIBRARY0143_DRAFT (silicyte-0143 LIBRARY): wake/sleep abstraction loop in the executor world

Status: DRAFT by the RSI researcher, 2026-11-05, written from 22:16 ET (PowerShell clock). Nothing built or run. Rules below are for a
builder and an independent verifier; any number marked TO_FIX is fixed by the builder's smoke and frozen before the first scored
round. Background and citations: RESEARCH_COMPOUNDING_1105.md (same folder), sec. 2 and 3.

## 0. Why this design (one paragraph)
The law (ratchet silicyte-0137) says reach accelerates iff alpha (1 + gamma) > 1; 0128 reads 0.38, and alpha_d is about 1.2 / d,
so a learner that faces frontier tasks of d / m decisions learns about m times faster per row. A library of abstractions is the
direct way to make m > 1. But the audit of 0133 (AUDIT_RSI_CONCLUSIONS_1105_PART2.md sec. 1) found that in our native world the
library is mostly op-set completion, its per-round compression plateaus at 24-34% (m 1.32-1.52), and the generator is i.i.d. Zipf with
no designed hierarchy. On those numbers the law predicts NO crossing in the native world (0.38 x 1.52 = 0.58 at best) and a crossing
only in a world whose parts nest. So 0143 is a world-structure contrast with a zero-learning searcher first (CPU, cheap, exact
attribution), then an LLM phase only if the symbolic positive case works.

## 1. Question
Q1 (symbolic). Does a wake/sleep loop whose ONLY learning is a growing library of compressed abstractions (no weights) show reach
that grows, and accelerates, round over round on a frozen ruler, at a primitive-execution budget matched to a flat searcher, in
(a) the native world, (b) a one-level motif world, (c) a three-level nested world?
Q2 (LLM, gated). With the same library channel feeding the Qwen3-8B LoRA loop of 0133, does alpha in primitive units rise by the
compression factor, so that alpha (1 + gamma) crosses 1 in the nested world and not in the native world?

## 2. Worlds
All worlds use the consol_v1 executor (lib/consol.py, md5 002ff8e6 in rsi_campaign/rig/boot_llm; the bootseed lib copy on Quartz at
/N/scratch/bsmensah/silo/bootseed/lib must be checked to the same md5), the same 54 ops, the same task format (4 demo pairs + 2 hidden
pairs) and make_task's four acceptance filters (no None or length < 4; no output equals its input; 4 distinct demo outputs; no dead op),
checked with opengen.verify_task.
- NATIVE: opengen.make_task_open with the world's Zipf weights (exactly the 0129 generator). Predicted null.
- RHO50: consol.world_rho's construction (10 two-op motifs drawn with the world seed; each segment is a motif with probability 0.5,
  else one Zipf op), but grown op by op with opengen's sequential rejection so that depths to 20 have usable yield (TO_FIX: yield per
  depth >= 0.3 at depth 20). Note: make_task_rho uses dict | dict (Python >= 3.9); the Quartz /usr/bin/python3 is 3.6.8, so run with
  a >= 3.9 interpreter (the arc26 venv python) or copy the function without that operator.
- HIER_A and HIER_B (new, hier0143.py): two independent planted hierarchies (world seeds 1430001 and 1430002).
  - Motif alphabet: the 27 length-preserving ops (revcomp, complement, reverse, swap_halves, mask_<6 sites>, rot1..rot5, the 12 sub_XY).
  - Level 1: 8 motifs, each 2 or 3 ops from that alphabet (uniform), no two adjacent ops of one family (avoids rot2 rot3 = rot5 style
    collapses).
  - Level 2: 8 motifs, each 2 or 3 level-1 motifs. Level 3: 8 motifs, each 2 level-2 motifs. Expected primitive lengths 2.5, 6.25,
    12.5.
  - Every motif must pass, on 200 PROBE strings (macrolib.PROBE): no internal dead op, and not extensionally equal to any primitive or
    earlier motif (macrolib's REJECT_EQUIV rule); redraw otherwise.
  - A task: choose top level k in {0, 1, 2, 3} and a unit count n in {1, 2, 3, 4}; each unit is a level-k motif with probability 0.85,
    else one Zipf primitive from all 54 ops (noise share 0.15); concatenate, then apply the four filters. Level 0 = NATIVE tasks.
  - Pools ask for a primitive-depth window [lo, hi]: draw (k, n) uniformly among combinations whose expected length lies in the
    window, build, accept iff the actual primitive length lies in the window.
  - TO_FIX: yield >= 0.3 per accepted task at primitive depths up to 30; the share of HIER tasks at depth >= 10 whose reference
    program is the shortest found by opengen.reduce_ub (minimal-length check) >= 0.8.
- The hierarchy files (motif bodies) are written to frozen/HIER_<A|B>_motifs.json, sha256 recorded, and are read ONLY by the
  generator, the PLANT control and the reader's recovery metric, never by any searching arm.

## 3. Searcher and compute unit
- S0, the registered zero-learning similarity beam (ratchet silicyte-0137 nolearn.py, sha recorded there as 30e54ffa): beam B 4,
  children ranked by the mean over the 4 demo rows of difflib.SequenceMatcher(None, child, target).ratio(), greedy (no accumulated
  score), exhaustive target check at every step, max_steps max(12, d + 2) where d is the task's nominal primitive depth.
- With a library, S0 runs over lib.actions() (54 primitives then macros in creation order), executing a macro by lib.run1 (every
  primitive intermediate must be a valid state). Implement as mbeam0143 in a NEW file: a copy of macrolib.mbeam with the greedy
  child-similarity ranking of nolearn.py (macrolib.mbeam accumulates acc + pol[i], which is NOT nolearn's rule). Do not edit the
  registered macrolib.py; import Library, extract, compression and verify_solution from it unchanged.
- Anchor (VOID if it fails): FLAT (empty library) on RULER_49100 must reproduce nolearn exactly: 44 of 300 correct, d50 4.854, task
  by task (v, c, program length, exec).
- Compute unit: primitive executions on the 4 demo strings, prim_exec (mbeam counts pex += len(expand(o)) per action tried). Every
  comparison between arms is at matched mean prim_exec per ruler task.

## 4. Arms
| arm | library | role |
|---|---|---|
| FLAT | none, B 4 | the zero-learning floor (static; scored once per ruler) |
| FLAT-B | none; beam widths B in {4, 6, 8, 12, 16, 24, 32} scored once per ruler, giving d50 as a function of mean prim_exec | budget-matched control: its d50 is read at LIB's mean prim_exec by linear interpolation in log prim_exec (no extrapolation: if LIB exceeds the B 32 budget, add B 48 and 64) |
| FLAT+ | op families completed once: drop/trim/rot 6..15 and every distinct 2-sub base map (enumerate sub_XY sub_ZW, keep extensionally distinct on PROBE, drop those equal to an existing op), B matched as FLAT-B | the audit's fair control: the library must beat op-set completion, not the 54 primitives |
| LIB | wake/sleep: macrolib.extract on ALL verified wake programs so far (primitive form, one per task), MAX_NEW_PER_ROUND 8, MAX_LIB 128, NMAX 4 (macros of macros allowed), MIN_TASKS 2 | the test arm |
| MEMO | each round adds up to 8 whole verified programs (length >= 2, most frequent first, ties by older task) as macros, cap 128 | DreamCoder's Memorize baseline: compression vs memorisation |
| FROZEN | LIB's library after round 1's sleep, then frozen | separates growth from a one-time level shift |
| PLANT (control) | HIER only: L_0 = the 24 true motifs (level order), no extraction | ceiling of what a library can buy this searcher |

## 5. The loop (LIB, MEMO, FROZEN)
- Rounds t = 0 .. 29 (R = 30). Round t: WAKE solves 300 fresh pool tasks with S0 over the current library; SLEEP updates the
  library from the verified programs; the ruler is scored with the library in force after the sleep.
- Wake pool: generated with seed 143000 + 1000 k + t (k = seed index 1..8), depth window by 0133's rule (width 6 starting at
  floor(c - 2.5) plus a +1 shift with probability c - 2.5 - lo, so the mean depth equals the centre c; c below 3.5 uses [1,
  floor(2c - 1)]); c = logistic d50 of the previous round's wake outcomes (t = 0: c = FLAT's ruler d50). Any task with an input on any
  ruler is skipped and counted (AUDIT_TOTAL must be 0, else VOID).
- Verified = all 4 demo rows reached; only verified programs (re-checked by macrolib.verify_solution, primitive form) enter the corpus.
  A program that reaches the demos but fails hidden rows still enters (the system cannot see hidden rows), as in 0128.
- Seeds: 8 per world (HIER: seeds 1-4 on HIER_A, 5-8 on HIER_B). Rulers per seed: NATIVE RULER_49100 + 100 ((k - 1) mod 4).

## 6. Rulers (frozen, never in any pool, never used for any choice)
- NATIVE: open0129 frozen RULER_49100..49400 (sha256 in open0129/frozen/RULER_SHA256.json), plus the XMIN axis
  (RULER_SHA256_XMIN.json). RHO50, HIER_A, HIER_B: new rulers of 300 tasks each, 10 per primitive depth 1..30 (RHO50: 15 per depth
  1..20), seeds 243000 + j, frozen with sha256 before any arm runs; 4 rulers per world.
- Score: correct = verified and both hidden rows right; d50 = the registered logistic fit (nolearn.py logistic_d50, verbatim). The
  system scored is searcher + library in force; max_steps max(12, d + 2) in ACTIONS for every arm. Readings at every round
  (cheap on CPU). A reading with a failed fit is reported and excluded from fits, never imputed.

## 7. Measurements
Per arm, seed and round:
- d50_t; correct by depth; mean prim_exec per ruler task and per wake task; wake verified count.
- Law quantities, with the 0137 estimators unchanged (loop_physics.py cf0a4fcc): e_t = per-primitive-step error from the geometric
  MLE of per-depth ruler shares; N_t = cumulative verified wake rows (one row per primitive step of each verified program, as 0128
  counts rows); r_t = rows added in round t; gamma = slope of ln r_t on ln d50_t; alpha = minus the slope of ln e_t on ln N_t;
  report alpha, gamma, alpha (1 + gamma), alpha gamma, each with the seed sd.
- Lever markers: library size; accepted macros per round; max nesting depth defined and used; m_t = primitive tokens / parsed
  tokens of round t's verified programs under the library BEFORE round t's sleep (compression on unseen work); frontier action depth
  a_t = d50_t / m_t; macro uses per verified program; share of accepted macros whose primitives all lie in one op family (drop1..5,
  trim1..5, rot1..5, sub_XY, mask, cut); HIER and RHO50: planted-motif recovery per level, the share of true motifs whose primitive
  expansion equals some library macro's expansion (recovery round r_l = first round with >= 6 of 8 level-l motifs recovered; level 3:
  >= 4 of 8).
- Every run log carries marker lines: LEVER lib_size=, m_t=, nest_used=, recov_l1/l2/l3=, budget_ratio_vs_flatB=.

## 8. Registered predictions and the tests that score them
One-sided tests across seeds use t_{0.95, 7} = 1.895 (8 seeds). "Acceleration delta" is 0133's statistic: OLS slope of d50 over the
second half of rounds minus over the first half (halves share round 15). Both readings of section 1.3 of the research file are
scored: NON-SATURATION (mean increment over rounds 15-29 at least 0.5 of rounds 0-14, in >= 6 of 8 seeds) and ACCELERATION (delta
t > 1.895, and alpha (1 + gamma) > 1 in >= 6 of 8 seeds).
- P1 NATIVE (null predicted). (a) LIB minus FLAT-B at R30, budget matched: mean in [-0.4, +0.8] d50. (b) LIB minus FLAT+: mean in
  [-0.5, +0.5]. (c) m_t for t >= 8 in [1.2, 1.6] with OLS slope over rounds 8..29 below +0.01 per round. (d) family share of accepted
  macros >= 0.5. (e) LIB acceleration: not passed; alpha (1 + gamma) < 1 in >= 7 of 8 seeds. [my P(all of a-e) 0.6; P(e) 0.9]
- P2 RHO50 (one level: a level shift, not acceleration). (a) LIB / FLAT-B d50 ratio at R30 in [1.15, 2.2] in >= 6 of 8 seeds; (b)
  recovery of >= 8 of 10 planted motifs by round 10; (c) acceleration not passed. [my P 0.55]
- P3 HIER (the positive claim). (a) LIB d50 at R30 >= 2.0 x FLAT-B in >= 7 of 8 seeds [my P 0.65]. (b) recovery rounds exist for
  levels 1 and 2 in >= 6 of 8 seeds, and the compounding signature r_3 - r_2 <= r_2 - r_1 holds in >= 6 of 8 seeds where r_3 exists
  (the next, longer abstraction arrives no slower than the previous one) [my P 0.5]. (c) ACCELERATION passes over rounds 0..min(r_3, 29)
  [my P 0.55]. (d) a_t stays within [1.5, 4.0] for every t >= r_1 while d50_t rises (the law's mechanism: the library keeps the
  frontier short in decisions) [my P 0.6].
- P4 HIER compression vs memorisation: LIB minus MEMO >= 1.0 d50 at R30 in >= 6 of 8 seeds [my P 0.7].
- P5 HIER growth vs level: LIB minus FROZEN >= 1.0 d50 at R30 in >= 6 of 8 seeds [my P 0.7].
- P6 law consistency: across all LIB runs, alpha_eff / alpha_FLAT-learning is undefined (FLAT has alpha 0), so the law is checked
  through a_t instead: if ln e_t regressed on ln a_t has slope > 0 (shorter frontier in actions, lower per-step error) in >= 6 of 8 HIER
  seeds, the mechanism "abstraction lowers effective depth" is supported.
Any P scored FAIL triggers the diagnosis ladder of ADDENDUM_LADDER2_TESTS_1105.md (lever reached? powered? which component?) before
any conclusion; a FAIL refutes this test, not the idea.

## 9. Power
- Level tests (P1a, P3a, P4, P5): paired across 8 seeds. With 0128's seed sd of d50 at round 10 (0.26; values 4.30-4.90) as a stand-in,
  the paired MDE at alpha 0.05 and power 0.8 is (1.895 + 0.896) x 0.26 x sqrt(2) / sqrt(8) = 0.36 d50. P3a's predicted effect (a
  factor 2 at d50 near 5, about 5 d50) is about 14 MDEs. TO_FIX: replace 0.26 with the measured FLAT-B seed sd (rulers differ by
  seed).
- Acceleration test: 0133's simulation (sim_ladder0133.py, K 4, readings every 2 rounds, alpha 0.04) gives TAKEOFF power 0.762 at
  R 32 for m 1.03 and 0.964 for m 1.05, false-positive rate <= 0.024 in every null cell. Here K 8 and readings every round, so power
  is higher; the builder must re-run that simulation with K 8, R 30, every-round readings and the t_{0.95, 7} rule and register its
  false-positive rate (must be <= 0.05 in the linear-null and linear-null + level-shift cells) and power at m 1.03 and 1.05 before
  any scored round.
- Reader check: run read0143.py on 3 synthetic datasets (linear, geometric m 1.05, staircase with 3 steps) and register its labels.

## 10. Positive control, lever checks, VOID rules
- PLANT (HIER): d50 with the oracle library >= 2.5 x FLAT-B on both HIER worlds. If PLANT fails, the searcher cannot exploit even a
  perfect library: P3 is VOID (not FAIL) and the HIER generator or searcher is redesigned before any LIB reading is scored. Also
  reported: LIB at R30 as a share of PLANT (expected >= 0.7).
- Planted single macro (smoke, before registration): NATIVE with one planted 4-op motif at rho 0.5; LIB must recover it within 3
  rounds in 3 of 3 smoke seeds.
- VOID if: the FLAT anchor misses nolearn's 44 / 300 on RULER_49100; any verify_fail; AUDIT_TOTAL != 0; a ruler sha256 mismatch;
  budget matching needs extrapolation beyond the measured B grid; the hierarchy file is opened by a searching arm (assert in code).

## 11. Kill test
- The claim "abstraction learning makes reach compound in this executor world class" is KILLED if, on HIER, the lever reached the
  system (recovery of level 1 and 2 in >= 6 of 8 seeds, PLANT passed) AND LIB d50 at R30 < 1.5 x FLAT-B in >= 6 of 8 seeds. Meaning:
  the abstractions were found but do not convert into reach at matched budget (branching cost or the heuristic dominates).
- NATIVE alone cannot kill the mechanism; a NATIVE null with a HIER pass is the predicted outcome and is reported as "library
  compounding needs nested structure the native world does not have".
- A NATIVE pass (LIB beats FLAT+ by >= 1.0 and accelerates) would contradict the audit and the law's prediction; it is reported as
  such, with the family-share and m_t markers.

## 12. Phase 2: the LLM-integrated version (gated: P3a passed and PLANT passed)
- Code: ladder0133.py and macrolib.py as registered for 0133 (hashes in BUILD_LADDER0133.md sec. 1), with one plug-in change: the
  pool generator and rulers are HIER_A (and NATIVE as the contrast). The ladder0133 PREREG sec. 4 primitive-only ruler is scored
  AND a system ruler with the current library allowed.
- Arms: MACRO_WARM (library from the policy's own verified solutions, as 0133) vs WARM (library held empty); 4 seeds per world; R 8
  rounds for the law read (the law scores alpha (1 + gamma) after 4-6 rounds); acceleration is NOT tested at R 8 (0133's sim needs
  R >= 24) and any statement about it is worded "underpowered".
- Rows: own and hindsight rows in ACTION form at every remaining action distance, targets rendered as strings (0133 fix 1 and its
  VOID_TARGET_FORMAT guard), PRIM_FRAC 0.25 primitive copies as in 0133.
- Readings: alpha by remaining ACTION distance k_a (the 0137 alpha_by_distance estimator with k counted in actions), alpha in
  primitive units from e per primitive step, gamma, alpha (1 + gamma).
- Registered predictions: Q2a alpha at k_a = 2 lies in [0.40, 0.90] in both arms (learning is per decision, as 0128's 0.637 at
  k = 2); Q2b alpha_prim(MACRO_WARM) / alpha_prim(WARM) >= 1.5 on HIER_A and <= 1.25 on NATIVE (paired, 4 seeds, one-sided t >
  2.353); Q2c MACRO_WARM alpha (1 + gamma) > 1 on HIER_A in >= 3 of 4 seeds and < 1 on NATIVE in >= 3 of 4.
- Cost: 0133's measured plan of 1.2-1.7 GPU-h per seed-round gives 2 arms x 2 worlds x 4 seeds x 8 rounds = 64 seed-rounds =
  77-109 GPU-h, about 1.5 days wall on 3 cards packed 3 per card.

## 13. Budget (symbolic phase)
- Cost per search: GATE_SUBGOAL_SEARCH_1105 measured 687 s for 900 searches of S0 at 54 actions (0.76 s each). Assume cost
  proportional to the action count: up to 182 actions (54 + 128) about 2.6 s.
- LIB, MEMO, FROZEN: 3 arms x 4 worlds (NATIVE, RHO50, HIER_A + HIER_B counted as one world of 8 seeds) x 8 seeds = 72 runs; per round
  300 wake + 300 ruler searches = 600 x at most 2.6 s = at most 26 min; 30 rounds = at most 13 h per run; total at most 940 CPU-h.
- FLAT, FLAT-B, FLAT+, PLANT: static, one scoring per ruler per beam width: about 7 widths x 16 rulers x 300 tasks x up to 8x the
  B 4 cost = about 100 CPU-h.
- Total about 1,000-1,100 CPU-h, 0 GPU-h; on Quartz CPU nodes (never the laptop, never a login node) about 13 h wall with one core per
  run. Phase 2: 77-109 GPU-h.

## 14. Builder checklist (files under /N/scratch/bsmensah/silo/library0143, mirrored in restart/library0143)
1. hier0143.py: HIER and RHO50 generators (sec. 2), motif files, ruler builder, yield and minimality smoke.
2. lib0143.py: mbeam0143 (greedy child similarity over lib.actions(), prim_exec counting), arms (sec. 4), the loop (sec. 5), ruler
   scoring (sec. 6), marker lines (sec. 7). Imports consol, opengen, macrolib unchanged; asserts their md5s.
3. read0143.py: d50 per round, law fit (imports the 0137 estimators unchanged), budget matching, P1-P6 scoring, recovery rounds.
4. sim0143.py: the power and false-positive simulation of sec. 9; reader check on synthetic data.
5. Smoke (CPU, 1 seed, 3 rounds per arm): FLAT anchor 44 / 300; empty-library mbeam0143 == nolearn beam_sim on 12 tasks field for
   field; planted single macro recovered; verify_fail 0; AUDIT_TOTAL 0; PLANT ratio printed; per-search seconds at 54 and 182 actions.
6. Freeze: ruler and motif sha256, code md5s, the TO_FIX numbers; then a verifier GO; then launch.
