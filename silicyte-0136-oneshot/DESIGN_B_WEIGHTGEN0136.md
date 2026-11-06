# DESIGN (not built): 0136 (b) one-shot weight generation as a compounding loop, ranked against (d) and (a)

Written 2026-11-05 about 19:20 ET. One page. Nothing here is built or launched.

## Mechanism
A generator G (Text-to-LoRA style hypernetwork) maps a task-family description to a LoRA in one forward pass. Loop, round r:
1. G writes an adapter for each of N task families (description = 8 demo pairs of the family plus its op subset).
2. Weight-space search: from each generated adapter, a short SGD refine (about 50 steps on the family's own beam-verified programs).
3. Verifier: each candidate (generated, refined) is scored by the registered B 4 beam on 60 held tasks of its family; accepted iff
   its d50 beats the base policy's on that family.
4. G is retrained (reconstruction loss, Text-to-LoRA scheme 1) on ALL accepted adapters from rounds 0..r, generated ones included.
Compounding path: a better G starts the refine closer to good weights, so the same refine budget lands further, so G's next targets
are better. This is ExIt in weight space (the "search" is the refine; the "apprentice" is G).

## Physics floor (sizes from 0128)
- A 0128 adapter is 174,655,536 bytes (r 16, all modules, about 43.7M fp32 numbers). Generating that directly is out of scale for a
  44-adapter dataset. Shrink the output: rank 4 on q_proj and v_proj of 8 layers, about 8 x 2 x 4 x (4096 + 1024) = 0.33M numbers.
- Data floor: a hypernetwork needs hundreds of (description, adapter) pairs. 0128 gives 44 adapters, all of ONE world and differing
  only by round, so they teach "round", not "task". The world must be split into families (op subsets, zipf variants): N = 32.
- Prior signal against the cheap variant: WMOON M1 (extrapolating a weight trajectory) HURT; M6 soups passed (p 0.039). Generating
  P_{t+1} from P_0..P_t is the M1 variant and is excluded.

## What would be measured (kill test sketch, to be registered separately)
- One-shot generated-adapter d50 (no refine) on 8 HELD families never used to train G, per round, K 2 seeds.
- Matched control: the same loop with G trained on the same number of adapters from fresh SGD runs on the base (no G-start), so the
  only difference is whether G's own outputs feed G. COMPOUNDING iff the generated-adapter gain per round is convex relative to the
  control (audit sec. 1a: compounding must be relative to a matched non-self-improving control).
- Pre-test (cheapest kill, about 2 GPU-h): can G reproduce a leave-one-out family adapter within the d50 noise (0.127)? If not, stop.

## GPU cost
Per round: 32 families x (refine about 3 min + B 4 on 60 tasks about 4 min) + G training about 10 min = about 3.9 GPU-h.
8 rounds x 2 seeds x 2 arms (loop, control) = about 125 GPU-h, plus the family build and the 2 GPU-h pre-test. Wall time on 4
shared cards: about 1.5-2 days, so it cannot label before the Nov 10 deadline unless the pre-test passes by Nov 7.

## Ranking (for fundability by Nov 10)

| rank | meaning | GPU cost | what it decides | why this rank |
|---|---|---|---|---|
| 1 | (d) amortisation on 0128's saved adapters | about 5-7 GPU-h of shared-card time, no training | whether 0128's loop already converts search into weights (a channel the next loop can re-spend) | cheapest, data exist, label in about 2 h of wall time on 4 cards |
| 2 | (a) one-shot learning (update on each verified solution) | about 10-20 GPU-h for a compute-matched per-item vs per-round arm on the reach world | whether immediate updates beat batched refits at matched compute (B16 PROCX3W 534 vs 440 was NOT compute-matched) | prior signal exists; needs one new arm, not a new system |
| 3 | (b) one-shot weight generation loop | about 125 GPU-h plus a family build | whether a weight-writer compounds on its own verified adapters | highest upside, nearest precedent SEAL; misses Nov 10 unless the 2 GPU-h pre-test passes early |

(c) ROME/MEMIT is 0135 E3 and (e) Ratchet ONESHOT is a different meaning (no library formed); neither is ranked here.
