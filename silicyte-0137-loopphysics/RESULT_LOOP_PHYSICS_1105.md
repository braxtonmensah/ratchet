# RESULT (exploratory): a two-exponent law of the 0128 self-training loop. It explains the deceleration, it forecasts, and it names the lever

Silicyte lead, 2026-11-05 18:52 ET (PowerShell clock). Gates written before each computation: GATE_LOOP_PHYSICS_1105.md (18:51 ET),
GATE_LOOP_PHYSICS_OOS_1105.md (18:52 ET). Code loop_physics.py (cf0a4fcc), loop_physics_oos.py (a65c1e9d), loop_physics_forecast.py
(2c00a9cd). Data: 0128 round_0..round_10.json of s1, FRONTIER_s2..s4 (registered MEAS pool 29000). Stdlib on the Quartz login node.

## The law
- Per-step accuracy p: a depth-d task is solved with probability about p^d, so d50 = ln 0.5 / ln p and the per-step error is e = 1 - p.
- Learning: e = A N^(-alpha), N = rows the policy was trained on.
- Feedback: rows added per round r = B d50^gamma (longer solutions carry more step rows).
- So dN/dt is proportional to N^(alpha gamma). Reach accelerates in rounds iff alpha (1 + gamma) > 1; the loop compounds in the
  strong sense (exponential or faster) iff alpha gamma >= 1.

## Measured (rounds 0..10; e from the geometric MLE of per-depth MEAS solves)
| seed | alpha (se) | gamma (se) | alpha gamma | alpha (1 + gamma) |
|---|---|---|---|---|
| s1 | 0.1626 (0.0236) | 1.047 (0.376) | 0.170 | 0.333 |
| FRONTIER_s2 | 0.1923 (0.0210) | 0.782 (0.225) | 0.150 | 0.343 |
| FRONTIER_s3 | 0.1425 (0.0168) | 1.470 (0.286) | 0.209 | 0.352 |
| FRONTIER_s4 | 0.2030 (0.0194) | 1.446 (0.248) | 0.294 | 0.497 |
| mean +/- sd | 0.175 +/- 0.028 | 1.19 +/- 0.33 | 0.206 +/- 0.063 | 0.381 +/- 0.077 |

From the registered logistic d50: alpha 0.142 +/- 0.016, alpha (1 + gamma) 0.310 +/- 0.050. **GATE: CONSISTENT** (alpha (1 + gamma) < 1
in all 4 seeds, matching the audit's model-free deceleration).

## It forecasts (fit rounds 0..5, predict rounds 6..10, vs a straight line through rounds 0..5)
| seed | MAE law | MAE linear |
|---|---|---|
| s1 | 0.307 | 0.082 |
| FRONTIER_s2 | 0.155 | 0.623 |
| FRONTIER_s3 | 0.087 | 0.410 |
| FRONTIER_s4 | 0.230 | 0.281 |
| pooled | 0.195 | 0.349 |
**GATE_OOS: PREDICTS** (law better in 3 of 4 seeds and pooled).

## What it says
- 0128 does feed back (gamma about 1.2: rows per round grow with reach), but it learns too little per row: doubling the training rows
  cuts per-step error by only about 11% (alpha 0.175). Acceleration needs alpha (1 + gamma) above 1: a factor 2.6 from here.
  Strong compounding needs alpha gamma >= 1: a factor 4.9.
- The lever is mostly alpha, learning per row. Raising gamma alone would need rows per round to grow as d50^4.7.
- Removing the depth ceiling (0129) does not change alpha or gamma, so the law predicts 0129 will not take off unless its exponents
  differ from 0128's. That is a falsifiable prediction for 0129's registered read.
- Any new loop can be scored on alpha (1 + gamma) after a few rounds, long before a curvature test has power.
- Known way to beat a power law in data: data pruning toward hard, informative rows (Sorscher et al. 2022, "Beyond neural scaling laws:
  beating power law scaling via data pruning"). 0128 trains on replay-all, most of it easy rows. That is the next experiment to price.

## Registered forecast (locked before any extension round > 10 is read for scoring)
FORECAST_0128_EXT_1105.json (sha256 bab5cac8...): per seed, the law fitted on rounds 0..10 forecasts MEAS d50_fixed at rounds 11..30.
| seed | 11 | 12 | 15 | 20 | 25 | 30 |
|---|---|---|---|---|---|---|
| s1 | 4.66 | 4.75 | 4.98 | 5.30 | 5.57 | 5.79 |
| FRONTIER_s2 | 5.14 | 5.25 | 5.55 | 5.96 | 6.30 | 6.59 |
| FRONTIER_s3 | 4.50 | 4.58 | 4.79 | 5.08 | 5.31 | 5.51 |
| FRONTIER_s4 | 4.97 | 5.11 | 5.48 | 6.01 | 6.46 | 6.85 |
- Disclosure: one extension reading was seen incidentally at 18:3x ET (FRONTIER_s2 round 11, d50 4.766), before this forecast was
  made. That point is excluded from scoring. Score: MAE over every other extension round that exists at Nov 10, against a straight line
  through rounds 0..10 as the baseline.

## Limits
Exploratory. The model is phenomenological (geometric per-step success, power laws in N and d50) and fitted on 11 rounds. The
calibration factor between the geometric and logistic d50 scales (1.49-1.61) is fitted, not derived. MEAS depths stop at 10, so a
forecast above about 8 would hit the ruler's ceiling.

## Addendum 18:59 ET: reinvesting saved search does not cross the line (GATE_REINVEST_1105.md, written before the read; reinvest.py 9c5c8913)
Cost per verified solve c_t = total exec / solves, per pool, vs d50; beta = -(slope of ln c on ln d50); under a fixed execution budget,
rows per round would scale as d50^(gamma + beta).
| seed | frontier beta (se) | data-pool beta (se) | alpha (1 + gamma + beta_dp) |
|---|---|---|---|
| FRONTIER_s2 | -0.402 (0.396) | +1.182 (0.202) | 0.570 |
| FRONTIER_s3 | -0.300 (0.394) | +0.949 (0.208) | 0.487 |
| FRONTIER_s4 | +0.284 (0.464) | +1.288 (0.235) | 0.758 |
**GATE_REINVEST: NO_HELP.** At the frontier, cost per solve does not fall (the window moves with the model, so its tasks stay equally
hard). Below the frontier it falls (amortisation), but even spending all of that saving on more rows leaves alpha (1 + gamma + beta)
at 0.49-0.76, under 1. Reinvestment alone cannot make this loop accelerate; alpha (learning per row) has to rise.

## Addendum 19:01 ET: GUIDE's learning-progress curriculum is not a clear alpha lever (GATE_GUIDE_ALPHA_1105.md, before the read)
Same rounds per pair (GUIDE's registered label is not read): pair s2 (rounds 0..5) alpha GUIDE 0.149 (se 0.033) vs FRONTIER 0.178
(se 0.040), ratio 0.84; pair s3 (rounds 0..4) 0.107 (se 0.024) vs 0.085 (se 0.020), ratio 1.25. **UNCLEAR** (needs >= 1.5 in both
pairs for a lever candidate). Curriculum selection by learning progress does not obviously raise learning per row at this length.

## Addendum 19:12 ET: the learning exponent falls as 1/depth (GATE_ALPHA_BY_DEPTH_1105.md before the read: HETEROGENEOUS)
Per-depth per-step error e_d = 1 - s_d^(1/d) on MEAS (30 tasks per depth), alpha_d pooled over 4 seeds (se = sd / 2):
| depth d | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|
| alpha_d | 0.569 (0.070) | 0.397 (0.030) | 0.299 (0.024) | 0.241 (0.023) | 0.205 (0.044) | 0.178 (0.031) | 0.130 (0.028) |
| d x alpha_d | 1.14 | 1.19 | 1.20 | 1.21 | 1.23 | 1.25 | 1.04 |
- Post hoc (the 1/d form was not in the gate): alpha_d is close to 1.2 / d for depths 2-7. The error at depth d falls like N^(-1.2/d),
  the curse-of-dimensionality rate of a learner covering a d-dimensional space, not the depth-independent rate a learner of reusable
  steps would show.
- Consequence: setting e_d = 0.693 / d (the 50% point) gives a reach that grows only about logarithmically in training rows, so each
  extra depth costs a roughly constant FACTOR more data. This is a sharper statement of why 0128 decelerates than the pooled
  alpha 0.175.
- Lever this points to: COMPOSITIONALITY, making a deep step as learnable as a shallow one. Candidates: subgoal decomposition (the
  model proposes intermediate states, so every search hop is short), and hindsight relabelling at every intermediate distance.
  Hard-first data pruning would feed mostly the slowest-learning rows and is not supported by this read.
