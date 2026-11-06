# RESEARCH: where self-improvement provably compounds, why, and the strongest test for this week

Researcher for the Silicyte RSI lane, 2026-11-05, written from 22:16 ET (PowerShell clock). Desk research plus local reads; no jobs
run. Builds on generalist0140/RESEARCH_SELFPLAY_1105.md, RESEARCH_DISTILL_1105.md and RESEARCH_FRONTIER_1105.md (not redone: LLM
self-play curves, OPD, provers and 2026 items are taken from there and cited as [SELFPLAY], [DISTILL], [FRONTIER]). Local evidence:
ratchet/silicyte-0137-loopphysics (the law, [LAW]; SYNTHESIS_LADDER2_1105.md, [SYNTHESIS]), AUDIT_RSI_CONCLUSIONS_1105_PART2.md
([AUDIT2]), ladder0133/ ([0133]), the world's consol.py ([WORLD]).

Source tags: [P] primary text read today (arXiv abstract or HTML, or the PDF text). [M] from my memory of a well-known paper, not
re-fetched today; treat the number as unverified until checked. "Not found" means I looked and the text I read does not give it.
"[my est.]" marks my own estimate or arithmetic.

The law in one line ([LAW]): per-step error e = A N^(-alpha) in verified rows N; rows per round grow as d50^gamma; reach accelerates
iff alpha (1 + gamma) > 1. 0128: alpha 0.175, gamma 1.19, alpha (1 + gamma) 0.38; alpha_d about 1.2 / d by depth; a zero-learning
similarity beam (d50 4.871 on MEAS) matches the trained 8B (round 10 mean 4.59).

---

## 1. Where self-improvement compounds, with evidence

Bottom line first. I found NO published loop whose reach accelerates per unit compute, in the law's sense alpha (1 + gamma) > 1.
What does exist, with numbers, is a smaller and still important class: loops that do NOT saturate. They keep a constant exponent (or a
constant gain per round) over tens to hundreds of iterations, where every LLM self-training loop in [SELFPLAY] sec. 2 has its largest
gain at iteration 1 and then shrinks, flattens or collapses. The useful contrast for us is therefore "constant exponent" versus
"exponent that decays with depth", and 0128 is in the second group (alpha_d about 1.2 / d).

### 1.1 Table of cases

| case | learner | verifier | frontier source | iterations | published curve | numbers |
|---|---|---|---|---|---|---|
| AlphaZero / AlphaGo Zero | policy + value net, search as teacher | exact (game result) | opponent = current self | 700k steps (chess) | rises over the whole run; Elo grows about linearly in log compute | chess: Stockfish level at about 300k of 700k steps, 4 h of 9 h [P, secondary summaries of the Science 2018 figure]. AlphaGo Zero: beat AlphaGo Lee 100-0 after 3 days, 5,185 Elo after 40 days [M] |
| AlphaZero scaling, Hex (Jones 2021, arXiv 2104.03113) | same | exact | self | many runs | compute frontier is a straight line in log compute until a perfect-play plateau | "500 Elo per order of magnitude increase in compute"; twice the compute wins "roughly 2/3"; each board-size step needs 7x the compute for perfect play; 10x train compute replaces about 15x test compute [P] |
| AlphaZero scaling, Connect Four and Pentago (Neumann and Gros, arXiv 2210.00849) | same | exact | self | many runs | power laws with one exponent across the fitted range | strength exponent in parameters alpha_N 0.88 / 0.87; in compute alpha_C 0.55 / 0.55; optimal size vs compute 0.62 / 0.63 (expected score 1 / (1 + (N_j / N_i)^alpha)) [P] |
| Self-Improving Transformers (Lee et al., ICML 2025, arXiv 2502.01612) | 14M from-scratch transformer, 6 layers, 384 dim, no positional embedding | majority vote or length filter (maze: an oracle verifier did about as well) | its own outputs one length beyond the last round | up to about 100 rounds | reach grows +1 per round by schedule, no saturation seen | reverse addition 16 -> 100 digits at +1 digit per round, 50,000 new rows per round, 1,500 steps; copy/reverse past 120 after about 100 rounds; forward addition above 98% to length 70 over 60 rounds; maze 9 -> 30 hops; multiplication 6x6 only 13.7% after 7 rounds without filtering, near perfect with majority vote (data accuracy 31% -> 93.3%); a wider difficulty schedule reaches 10x10 in 19 rounds instead of 41 [P] |
| STP, self-play theorem prover (Dong and Ma, arXiv 2502.00212) | LLM prover + conjecturer | Lean | conjectures the prover proves with pass rate in (0, 1/4] | 48 Lean iterations | "significantly better scaling than expert iteration", which plateaus | LeanWorkbook 28.5% vs 13.2% for expert iteration; 3.6M conjectures, 241M proofs, 51.3B tokens; at 11.4% cumulative, expert iteration found "only 131 out of 2.5M" correct proofs, so retraining "has almost no effect"; at least 47% of conjectures get proved [P] |
| Goedel-Prover V1 expert iteration (arXiv 2502.07640) | LLM prover | Lean | fixed 140K statements, new formalized sets added at iterations 4 and 7 | 9 | shrinking gains on fixed data; jumps only when new statements are added | LeanWorkbook solved 20.6K -> 23.0K -> 24.4K -> 25.4K -> 27.0K -> 27.8K -> 28.8K -> 29.7K -> 30.3K: increments +2.4K, +1.4K, +1.0K, +1.6K, +0.8K, +1.0K, +0.9K, +0.6K (Table 8 as extracted; headers garbled, mapping inferred) [P] |
| rStar-Math (arXiv 2501.04519) | 7B policy + process reward model, MCTS as teacher | answer check + PPM | 747k problems, more rollouts for unsolved | 4 rounds | MATH increments shrink; AIME increments did not shrink | MATH 58.8 -> 69.6 -> 73.6 -> 75.8 -> 78.4; AIME24 0 -> 3.3 -> 10.0 -> 16.7 -> 26.7 (30 items, 1 item = 3.3 points) [DISTILL] |
| DreamCoder (Ellis et al., PLDI 2021, arXiv 2006.08381) | library (abstraction sleep) + recognition net (dream sleep) + enumeration | exact (program execution) | fixed task sets (LOGO 160, towers 107, text 128) | 20 wake/sleep cycles | rises, then converges on the finite set | text editing 3.7% -> 79.6% solved (mean search 235 s -> 40 s); LOGO and towers "nearly 100%" while "no alternative model ever solves more than 60%"; library depth vs solves r = 0.79; about a day on 20-100 CPUs [P, PDF text] |
| LILO (Grand et al., ICLR 2024, arXiv 2310.19791) | LLM synthesis + enumeration + Stitch compression + auto-documentation | exact | fixed sets | DreamCoder 10-16 iterations | library adds a lot in one domain, nothing in another | mean solve, LLM solver + search vs LILO: REGEX 76.60 vs 77.07 (+0.47); CLEVR 96.44 vs 96.76; LOGO 37.84 vs 48.95 (+11.11, but LILO sd 22.15 over 3 seeds); DreamCoder REGEX 43.93 "still increasing at iteration 10"; one LLM round equals about 48 CPU-hours of DreamCoder search [P] |
| Stitch (Bowers et al., POPL 2023, arXiv 2211.16605) | compression only | n/a | n/a | n/a | n/a | "3-4 orders of magnitude faster", "2 orders of magnitude less memory" than DreamCoder's compressor, comparable compressivity [P]. The tool, not a loop. |
| "Library Learning Doesn't" (Berlot-Attwell et al., arXiv 2410.20274) | LEGO-Prover, TroVE | Lean / execution | fixed | n/a | gains real, but not from the library | "function reuse is extremely infrequent on miniF2F and MATH"; "self-correction and self-consistency are the primary drivers" [P] |
| Peano tactic induction (Poesia and Goodman, arXiv 2211.15864) | RL policy + induced tactics | exact (formal system) | 5 Khan Academy algebra sections | curriculum | without tactics it "stagnates in the equation solving sections"; with tactics it "eventually solve[s] all problems" | an example solution has random-action probability 10^-12 from axioms vs 1.28 x 10^-6 as 3 steps over 18 induced tactics [P] |
| Voyager (arXiv 2305.16291) | frozen GPT-4 + skill library | self-verification | automatic curriculum | 160 prompting iterations | without the library, "a tendency to plateau in the later stages" | 3.3x more unique items, 15.3x faster tech-tree milestones than prior SOTA; random curriculum -93% items; no self-verification -73% [P] |
| Darwin Goedel Machine (arXiv 2505.22954) | frozen Claude 3.5 Sonnet, self-edited scaffold | benchmark tests | open-ended archive of agents | 80 | step-wise rises with dips at iterations 4 and 56 | SWE-bench Verified 20.0 -> 50.0; without open-ended exploration 23.0; without self-improvement 39.0; Polyglot 14.2 -> 30.7; about USD 22,000 per run [P] |
| Hyperagents (Zhang et al., arXiv 2603.19461, Mar 2026) | DGM whose meta agent edits itself too | task scores | archive | not read | improvements "accumulate across runs" (abstract; no numbers there) | not found in the abstract; appears to edit code, not weights [P abstract only] |
| FunSearch / AlphaEvolve | frozen LLM + evolutionary program database | exact evaluator | the database | about 10^6 samples per problem [M] | best score improves with samples; no weight learning | cap set in dimension 8: 512 vs previous 496 [M] |
| Test-time training on ARC (arXiv 2411.07279) | 8B, per-task LoRA | demos | none (one shot per task) | 1 | not a loop | up to 6x vs fine-tuned baseline; 53.0% ARC public validation; 61.9% with program synthesis [P] |
| Absolute Zero, R-Zero, R-Diverse, Agent0, SPIN, ReST-EM | LLM, RL or SFT on own data | executor / majority vote | self-proposed | 3-5 | largest gain at iteration 1, then flat, linear small or collapse | R-Zero 4B +5.49, +0.38, +0.68, -2.60; R-Diverse 8B +5.00, +0.52, +0.70, +0.55, +0.51 [SELFPLAY sec. 2] |
| Explorer-Zero (arXiv 2610.19868) | LLM proposer that probes the checker, subtask rewards | environment | interactive proposer | 4 outer loops | full method "keeps improving"; the no-subtask variant levels off after about 60 steps | AppWorld 29.5 -> 45.8 -> 59.7 [FRONTIER] |

### 1.2 Each case in the law's terms

The law's quantities are: alpha (learning per verified row, and whether it decays with depth), gamma (how the frontier's row supply
grows with reach), and the curve shape. Where a paper reports no per-row exponent, I give the closest measured quantity.

1. AlphaZero family. Alpha: strength is a power law in compute with ONE exponent across the fitted range (alpha_C 0.55 in two games;
   Hex 500 Elo per decade until the perfect-play plateau). The exponent does not decay as the agent gets stronger. Gamma: the
   frontier is the agent itself, so every game is played at about a 50% win rate against the current policy: the supply of
   frontier rows never runs out and does not need to grow with strength. Shape: Elo linear in log compute, so in absolute terms the
   gain per FLOP decelerates (a power law with exponent below 1), but it never saturates before the game's ceiling. The training
   target is MCTS output, which is always one improvement-operator step ahead of the raw policy, so the teacher's lead regenerates
   every iteration.
2. Self-Improving Transformers. Alpha: at trained lengths the per-digit error is tiny and does not grow with length: above 98%
   exact at length 70 means per-digit error at most 1 - 0.98^(1/70) = 2.9e-4 [my est., from the paper's number]. 0128's per-step
   error at round 10 is about 1 - 0.5^(1/4.59) = 0.14. The learner represents the rule (the carry procedure), so a deeper instance
   costs no more rows than a shallow one: alpha_d does not fall like 1 / d. Gamma: 50,000 rows per round at every length, so gamma
   is 0 in rows and 1 in tokens. Shape: reach +1 per round by schedule over 60-100+ rounds; the schedule, not the learner, sets the
   rate (19 rounds instead of 41 when the schedule is widened). "Exponential improvements" in the abstract refers to
   out-of-distribution accuracy across rounds, not reach per FLOP.
3. STP vs expert iteration. Same prover; what differs is gamma. Expert iteration on a fixed statement set exhausts its frontier:
   131 correct proofs in 2.5M samples at 11.4%, so new rows per round go to about zero (gamma effectively negative: rows fall as reach
   rises) and it plateaus. The conjecturer keeps manufacturing statements at pass rate (0, 1/4], so at least 47% of conjectures yield
   rows and the loop runs 48 iterations to double the expert-iteration result. Alpha is not reported.
4. Goedel-Prover V1. Fixed statements: increments shrink from +2.4K to +0.6K. Each injection of new statements (iterations 4 and 7)
   gives a jump. Pure gamma story: saturation when the frontier supply is fixed.
5. rStar-Math. Search as teacher (MCTS + PPM) and more rollouts for unsolved problems: the hardest slice (AIME) has non-shrinking
   increments over 4 rounds, the closest LLM case to compounding [DISTILL]; MATH increments shrink (+10.8, +4.0, +2.2, +2.6).
6. DreamCoder, LILO, Peano. Here the mechanism is depth reduction. Peano's example: 3 tactic steps carry random-action probability
   1.28e-6 versus 1e-12 from axioms, so in log-probability the effective search depth falls by ln(1e-12) / ln(1.28e-6) = 2.04x [my
   est.]. In the law, alpha_d about 1.2 / d means a learner that faces depth d / m instead of d learns m times faster per row, so a
   compression factor m multiplies alpha. DreamCoder's library depth correlates with solves (r 0.79), the ablations stay below 60%
   where the full system nears 100%, and the curves converge because the task sets are finite (107 to 160 tasks), which says
   nothing about acceleration. LILO shows the domain dependence: +11.11 on LOGO, +0.47 on REGEX. "Library Learning Doesn't" shows LLM
   libraries in math are rarely reused at all.
7. Voyager, DGM, Hyperagents, FunSearch. Frozen weights. What carries the gain is an archive or library outside the weights plus a
   frontier that the archive itself opens (DGM: 23.0 without open-ended exploration vs 50.0 with it; Voyager: -93% items with a random
   curriculum). These fail his "weights must change" rule and are useful only as frontier designs.
8. LLM self-play (R-Zero and kin). Largest gain at iteration 1, then small constant or collapsing gains [SELFPLAY]. Pseudo-label
   accuracy decays (R-Zero 79% -> 63% over iterations 1-3), so the verifier gets worse as the frontier moves. Explorer-Zero's
   checker-probing proposer is the exception that keeps rising.

### 1.3 What none of them shows
- Acceleration per FLOP. Even the strongest cases are concave in compute (Elo linear in log compute; Lee et al.'s cost per round
  grows with sequence length while reach grows +1 per round).
- A curve over many iterations for a library-learning LLM loop on an unbounded task supply.
So the strongest public statement available is "non-saturating with a stable exponent", and our registered bar ("accelerates") is
stricter than anything published. A verdict should register both readings (sec. 8 of the prereg draft does).

---

## 2. The mechanism question: what separates compounding from saturating loops

The hypothesis: compounding needs (a) per-row efficiency that does not fall with depth (rules, abstractions, value functions rather
than instance memory), (b) a frontier the learner's own improvement expands, (c) exact verification.

| case | (a) depth-stable efficiency | (b) self-expanding frontier | (c) exact or reliable check | outcome |
|---|---|---|---|---|
| AlphaZero | NOT via rules: generic net; stable exponent comes from search as teacher | yes (opponent = self) | yes | non-saturating, concave in compute |
| Self-Improving Transformers | yes (rule learned; per-digit error 2.9e-4 at length 70) | yes (+1 length per round) | majority vote, reliable only with filtering (6x6: 13.7% without) | non-saturating, linear per round |
| STP | not measured | yes (conjecturer) | yes (Lean) | keeps scaling; expert iteration plateaus |
| Goedel V1, ReST-EM, expert iteration | not measured | no (fixed set) | yes | shrinking gains |
| DreamCoder, Peano | yes (library cuts depth: Peano 2.04x in log-probability) | partly (fixed task sets) | yes | converges to near 100% of a finite set |
| LILO REGEX, LEGO-Prover, TroVE | no reuse (REGEX +0.47; reuse "extremely infrequent") | fixed | yes | no library effect |
| R-Zero | no | yes | no (labels decay 79% -> 63%) | collapse after iteration 3 |
| 0128 | no (alpha_d about 1.2 / d) | yes (gamma 1.19) | yes (executor) | decelerates, alpha (1 + gamma) 0.38 |
| 0133 macros (audit) | library fills op-set gaps (sec. 2.2) | yes | yes | no reach gain in smoke, 2.07x execution cost |

### 2.1 Verdict on the hypothesis
- (b) holds in every non-saturating case and its absence explains every plateau with a fixed set (STP vs expert iteration, Goedel V1
  increments, Voyager -93%, DGM 23.0 vs 50.0). In the law it is the condition gamma >= 0; a fixed set drives gamma below 0.
- (c) holds, with a correction: what matters is that label accuracy stays high as the frontier moves, not that the checker is
  formally exact. Lee et al.'s majority vote worked (31% -> 93.3% data accuracy); R-Zero's majority vote decayed and collapsed. Our
  executor is exact, so (c) is not our bottleneck.
- (a) is right in substance but too narrow in form. AlphaZero is the counterexample to "rules or abstractions are needed": its net
  memorises patterns like any net, and it still keeps a constant exponent because its training target is search output whose lead
  over the policy regenerates at every strength. The general condition is: THE EXPONENT MUST NOT DECAY AS THE FRONTIER DEEPENS. Two
  known routes give it: (a1) a learner that represents the rule or an abstraction, so a deeper task is not a new instance; (a2) a
  teacher (search) that is always one improvement step ahead of the policy on frontier states. 0128 has neither: it trains on its
  own successful paths (no lead) and memorises instances (alpha_d about 1.2 / d).
- Missing from the hypothesis, (d): reusable structure in the task distribution. Abstraction compounds only when deep tasks are
  built from parts that recur. LOGO and towers were designed by people with polygons and arches inside; Khan Academy algebra has
  tactics; REGEX in LILO and miniF2F did not reward a library. Our world has, by construction, none: the generator draws ops i.i.d.
  Zipf(1.1) over a fixed order, "NOT a designed hierarchy" ([WORLD] docstring), and the audit measured that the world's own gold
  programs, with no learner, already compress 16.3% under top-20 bigrams [AUDIT2].
- Missing (e): a stated acceleration bar is beyond the evidence. No case accelerates per FLOP (sec. 1.3).

### 2.2 What this says about our world, numerically
- 0133's macro library is mostly op-set completion: 11 of the top 20 bigrams (61.8% of their uses) equal a single would-be op
  (drop3 drop3 = drop6, sub chains = base maps); merging the op families alone shortens programs 22.0% (E1) to 34.2% (E2); what the
  library adds beyond that is 13.2-13.6%, below the generator's own 16.3% [AUDIT2].
- Per-round MDL compression rises over rounds 1-5 and then "sits at 24-34% through round 10 in every seed: a plateau" [AUDIT2]. As a
  depth factor m = 1 / (1 - c): 1.32 to 1.52, and it stops growing.
- The law then gives, for an LLM learner whose per-row efficiency scales as 1 / (depth in decisions): alpha_eff = 0.175 x m, so
  alpha (1 + gamma) = 0.38 x m = 0.50 to 0.58 at m 1.32 to 1.52 [my est.]. Crossing 1 needs m >= 2.63 (the "factor 2.6" in [LAW]),
  and keeping the frontier at the k = 2 value (alpha 0.637, alpha (1 + gamma) 1.40) needs m to grow with reach so that frontier tasks
  stay about 2 actions long: m_t about d50_t / 2. In an i.i.d. world m plateaus, so the law predicts LIBRARY does NOT cross in the
  native world. It can cross only where abstractions nest (macros of macros that keep appearing at larger scales).
- The search side agrees: with b = 54 primitives and L = 64 macros of mean length m = 2, exhaustive reach at a fixed execution budget
  E scales as m ln E / ln(b + L) instead of ln E / ln b, a factor 2 x ln 54 / ln 118 = 1.67 [my est.], a one-time level shift unless m
  keeps growing; and the beam smoke measured equal reach at 2.07x action executions [AUDIT2].

### 2.3 The corrected mechanism, in the law's terms
Compounding (here: non-saturating, and accelerating if strong enough) needs all of:
1. gamma >= 0 from a self-generated frontier (conjecturer, self as opponent, own outputs at the next length).
2. an exponent that does not decay with frontier depth: either abstraction or rule learning that keeps the frontier short in the
   learner's own units (m_t growing with reach), or a search teacher whose lead regenerates.
3. labels that stay correct as the frontier moves.
4. a task distribution with recurring, nested parts (for route 2a only).
5. for acceleration specifically: alpha_eff (1 + gamma) > 1, with gamma measured per FLOP if the claim is per FLOP (cost per row
   rises with depth: the 0137 reinvest addendum's beta).

---

## 3. silicyte-0143 LIBRARY

Full draft: PREREG_LIBRARY0143_DRAFT.md beside this file. Summary of the design choices and why:
- Symbolic first, on CPU, no LLM: the similarity beam that matched the 8B (nolearn.py rule) plus a library from MDL compression of
  its own verified solutions (ladder0133/macrolib.py: extract, parse, mbeam, verify_solution, already built and smoke-tested:
  empty-library mbeam == beam2 on 12 of 12 tasks). The searcher has no weights, so any reach growth is the library's.
- Three worlds, because sec. 2 says the outcome depends on structure: NATIVE (opengen consol_v1, i.i.d. Zipf: predicted null),
  RHO50 (consol.world_rho with 10 planted 2-op motifs at rho 0.5: one level, predicted level shift without acceleration), HIER (new:
  three nested motif levels: the only world where the law predicts a crossing). HIER with the oracle library is the positive control.
- Controls the audit demanded: FLAT-B (same primitive-execution budget spent on a wider beam), FLAT+ (op families completed once:
  drop/trim/rot 6-15 and the 2-sub base maps), MEMO (whole solved programs as macros, DreamCoder's Memorize baseline), FROZEN (library
  frozen after round 2: separates growth from level).
- Readings in the law's units (e per primitive step by geometric MLE on frozen rulers, N, gamma, alpha (1 + gamma)) plus the lever
  markers that say whether the abstraction channel reached the system (compression m_t, nesting depth used, planted-motif recovery,
  family share of macros).
- The LLM-integrated version reuses ladder0133.py (MACRO_WARM vs WARM) on HIER and NATIVE and reads alpha by remaining ACTION
  distance; it is gated on the symbolic HIER result.

---

## 4. A test with a better chance of showing compounding in 4 days on about 10 H100s

### 4.1 Recommendation: silicyte-0144 HORIZON, a law-instrumented replication of Self-Improving Transformers with a self-paced frontier
What: train the paper's 14M from-scratch transformer (6 layers, 6 heads, 384 dim, no positional embedding) on reverse addition
(primary) and maze hops (secondary), then run the self-improvement loop: each round generate 50,000 problems at the next lengths,
label them with the model's own majority vote over 5 seeds (keep >= 4 of 5 agreeing; maze: all 3 agree), fine-tune, repeat.
Arms (4 seeds each):
- SCHED1: the paper's schedule, +1 length per round (replication; expected linear reach).
- SELFPACE: each round extends to the longest length where the model's own 5-seed agreement on 512 unlabelled probes is >= 0.9
  (no test labels; the paper's accelerated schedule used test accuracy, which it calls unavailable in practice). If the model trained
  to length L generalises to L (1 + c), this schedule grows geometrically: the acceleration test.
- NOSELF (compute matched): the same GPU-seconds spent training on the initial lengths only (the control that has no
  self-improvement channel).
- ORACLE (compute matched to SELFPACE): true labels at SELFPACE's lengths; SELFPACE / ORACLE is the cost of self-labelling.
- BRIDGE (one seed first, then 4): the same 14M recipe as a step policy in OUR world (0128's (state, target) -> op rows, loop and
  ruler), from scratch. It asks whether the 8B's memorisation (alpha_d about 1.2 / d) is a property of the world or of the learner.
Readings: reach_t = longest length with >= 0.95 exact accuracy on a frozen, true-labelled ruler (lengths 1 to 200, 100 problems per
length); per-digit error by geometric MLE per length; alpha_d by length; increments reach_t - reach_{t-1}; reach against cumulative
GPU-seconds (the per-FLOP reading); the law's alpha (1 + gamma) in rows and in tokens.
Registered predictions (to be fixed in a prereg before any data):
- H1 non-saturation: SCHED1 increments over rounds 20-60 have a mean of at least 0.9 of rounds 1-20 in >= 3 of 4 seeds. [my est.
  P 0.85, from the paper's 60-100+ round curves]
- H2 depth-stable learning: d x alpha_d grows with d (not constant as in 0128) in the SCHED1 rows. [my est. P 0.7]
- H3 acceleration per round: SELFPACE increments in the second half exceed the first half, one-sided t across 4 seeds > 2.353
  (t_0.95, 3). [my est. P 0.5]
- H4 acceleration per GPU-second: reach vs cumulative GPU-seconds has fitted exponent b >= 1. [my est. P 0.15: tokens per row grow
  with length, so this probably fails; registering it keeps the per-FLOP claim honest]
- H5 BRIDGE: the 14M step policy in our world shows d x alpha_d constant (memorises) [my est. P 0.6]; if instead it grows, the 8B
  LoRA, not the world, was the bottleneck.
Price [my est.]: 14M parameters, batch 1,024, about 100-300 tokens per row: 6 x 1.4e7 x 3e5 = 2.5e13 FLOP per step, about 0.2-0.3 s
on an H100 at a modest 100 TFLOP/s; 1,500-5,000 steps plus 50,000 x 5 generations per round: about 6-15 min per round. SCHED1 60
rounds about 6-15 GPU-h per run; SELFPACE fewer rounds. 2 tasks x 4 arms x 4 seeds = 32 runs, about 60-190 GPU-h before packing;
the runs are tiny in memory, so 4 per card under MPS (x1.68 measured on Quartz, 11/04 note) brings wall time to about 1 day on 10
H100s. Code: no official repository found by today's search; a nanoGPT-style re-implementation from the paper's appendix settings
(lr 5e-4, batch 1,024, 10,000 initial steps for reverse addition; per-task steps per round as listed in the paper) is about a day of
building.
Why it beats LADDER-2 and LIBRARY for "can we show compounding this week":
- It sits in the only published class with a long non-saturating curve on a weight-updating learner, so the prior for H1 is high.
- It tests the law's decisive variable directly: whether the exponent decays with depth (H2), in a learner known to learn the rule.
- SELFPACE is the cleanest acceleration test available: it removes the hand-set +1 schedule that caps reach at linear.
- It is cheap and does not compete with 0140 for the 8B cards.
- The BRIDGE arm connects it to our world, which the paper alone does not.
Where it is weaker: a toy algorithmic domain with one rule; a positive result shows the law's boundary, not general self-improvement.

### 4.2 Ranking of the candidates for this week (all probabilities are my estimates)
| test | what a pass shows | P(non-saturation) | P(acceleration per round) | P(per GPU-h) | cost | days |
|---|---|---|---|---|---|---|
| HORIZON SELFPACE (sec. 4.1) | the law's boundary in a rule learner | 0.85 | 0.5 | 0.15 | 60-190 GPU-h | 1 build + 1-2 run |
| LADDER-2 (0139) | short verified hops cross the boundary in our world | 0.5 | 0.3 (sits near 1: lower 90% bounds give 0.99 [SYNTHESIS]) | 0.15 | 0139 budget | 2-4 |
| LIBRARY HIER symbolic (0143) | nested abstractions make a zero-learning searcher compound | 0.75 | 0.6 (planted structure) | 0.4 | about 600-1,000 CPU-h, 0 GPU | 1 build + 0.5 run |
| LIBRARY NATIVE (0143) | library compounds in the i.i.d. world | 0.1 | 0.05 | 0.05 | included above | same |
| STP-style conjecturer in our world | frontier supply (gamma) | covered by 0140 SELF vs FROZEN_CHALLENGER | | | | |

The strongest single package for a public verdict this week is HORIZON (GPU, about 1 day of cards) run in parallel with 0143
symbolic (CPU only), because between them they separate the three causes: learner (HORIZON BRIDGE), world structure (0143 NATIVE vs
HIER), and frontier supply (already in 0140).

---

## Sources (read today unless tagged [M])
- arXiv 2502.01612 (Lee, Cai, Schwarzschild, Lee, Papailiopoulos; ICML 2025, PMLR 267: 32930-32964): abstract and HTML.
- arXiv 2502.00212 (STP): abstract and HTML.
- arXiv 2104.03113 v2 (Jones, Scaling scaling laws with board games): HTML.
- arXiv 2210.00849 (Neumann and Gros): HTML Table 1.
- arXiv 2006.08381 (DreamCoder): PDF text (pypdf), pages with "Quantitative analyses" and Fig. 6.
- arXiv 2310.19791 (LILO): HTML Table 1 and text.
- arXiv 2211.16605 (Stitch): abstract.
- arXiv 2410.20274 (Library Learning Doesn't): abstract.
- arXiv 2211.15864 (Peano): abstract and HTML.
- arXiv 2305.16291 (Voyager): abstract and HTML.
- arXiv 2505.22954 (Darwin Goedel Machine): HTML incl. Table 1 and App. E.1.
- arXiv 2603.19461 (Hyperagents): abstract only.
- arXiv 2502.07640 (Goedel-Prover V1): HTML Table 8.
- arXiv 2411.07279 (TTT on ARC): abstract.
- AlphaZero chess timing: Wikipedia AlphaZero page and chess24 / Cadence summaries of Silver et al., Science 362: 1140 (2018).
- [M] Silver et al., Nature 550: 354 (2017), AlphaGo Zero; Romera-Paredes et al., Nature 625: 468 (2024), FunSearch.
- Local: ratchet/silicyte-0137-loopphysics/*.md and *.out; restart/AUDIT_RSI_CONCLUSIONS_1105_PART2.md; restart/ladder0133/
  BUILD_LADDER0133.md, PREREG_LADDER0133_DRAFT.md, macrolib.py; rsi_campaign/rig/boot_llm/consol.py (md5 002ff8e6, the world);
  restart/open0129/opengen.py; restart/bootseed/bootseed0128.py.
