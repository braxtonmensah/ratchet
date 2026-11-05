# RESULT silicyte-0128 (BOOTSEED_V1), registered A1 read at R = 10: LINEAR-GROWTH within 10 rounds

Read 2026-11-05 16:4x ET with the registered reader, ext/read_0128_ext.py (md5 953d97be). Per A4, the A1 read uses rounds 0..10 only.

## What was tested

Qwen3-8B with a LoRA, in the consol_v1 depth-knob world. Every round it searches for verified solutions to its own data and frontier
pools, then retrains its LoRA on them; the improver's own weights change. K = 4 independent seeds, each with its own pools, seeds and
round 0 (A1). The quantity is d50_fixed: the depth at which P_r solves 50% of a fixed measurement pool (29000, 300 tasks) that is never
trained on.
- SHAPE: per-seed OLS quadratic coefficient c over rounds 0..10, then a seed-level one-sided t (alpha 0.04, df 3, critical value 2.605).
- LEVEL: mean per-round gain, 95% lower bound > 0.
The registration and amendments are in silicyte-0128/PREREG_BOOTSEED_V1.md in this repo (A1 to A4; A4 registered 13:44 ET, before any
round-11 reading).

## Result

| seed | d50_fixed, rounds 0 -> 10 | curvature c | mean gain per round |
|---|---|---|---|
| 1 | 2.863 -> 4.682 | +0.0010 | 0.182 |
| 2 | 2.860 -> 4.900 | -0.0187 | 0.204 |
| 3 | 2.778 -> 4.305 | -0.0121 | 0.153 |
| 4 | 2.635 -> 4.473 | -0.0053 | 0.184 |

- SHAPE: mean c = -0.0088, sd 0.0085, t = -2.07 against crit 2.605: FAIL. The sign leans slightly toward deceleration.
- LEVEL: mean gain 0.181 d50 per round, sd 0.021, lower 95% bound 0.156: PASS.
- **Label: LINEAR-GROWTH, within 10 rounds.**
  - VOID gate: seed 1's round 0 reproduced boot_llm2's (66 correct, d50 2.842).
  - UNDERPOWERED gate: all 4 seeds reached round 10, and power at the measured noise is above 0.6 (below).
- Prediction (registered before any seed ran): point c 0.00, 80% band [-0.03, +0.03], P(COMPOUNDS) 0.08, most likely label
  LINEAR-GROWTH. The observed mean c (-0.0088) is inside the band, and the label is the predicted one.

## How sensitive the test was (r10/resim_a1.js, measured noise, xorshift128+, 4,000 runs)

Noise measured from the four seeds' gains:
- per-round random walk tau 0.158;
- transient measurement noise s_e 0.127;
- between-seed gain sd 0.021.

With those values and the registered rule:

| true growth | the rule calls it accelerating |
|---|---|
| linear (m = 1.0) | 4.0% |
| each round's gain 10% larger than the last (m = 1.1) | 56% |
| m = 1.2 | 99.9% |

So acceleration of 20% per round or more is ruled out over these 10 rounds; 10% per round is not.

## What it means, and what it does not

- The loop reliably improves itself: +0.18 depth per round on a never-trained ruler, consistent across 4 seeds. It does not speed up
  within 10 rounds.
- Two measured facts bound the reading:
  - The weights reset every round: each round fits a fresh LoRA (lib/reachlaw.py:125); consecutive rounds' weight changes have cosine
    0.05 to 0.09 (weightmap/RESULT_LORA_ANATOMY_S1.md). What accumulates is the self-made dataset, not the weights.
  - The loop has a ceiling: training search is capped at 10 steps, and data pools stop at depth 10 (ext/VERDICT_A4_0128.md).
- A later takeoff is tested separately:
  - A4 (rounds to 30 on per-seed deep rulers) can see one that starts near round 10.
  - silicyte-0129 (no depth ceiling) and silicyte-0130 (the loop adjusts its own recipe) are built for the rest.
- Seeds 2 to 4's round-10 readings come from their scored-only round 10, archived by the A4 continuation
  (ext/archive/FRONTIER_sk/round_10.scored_only.json, md5 prefixes 6dc7d7b4 / a944b63b / 2c0e59fc). Those seeds are re-running
  round 10 as a trained round. A4 requires the redone MEAS rows to equal these exactly (extend_0128.py post), and that check is
  pending; if it fails, this note will say so.
