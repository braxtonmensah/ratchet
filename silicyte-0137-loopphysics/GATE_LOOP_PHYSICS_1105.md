# GATE (exploratory, stored rows): the loop's two exponents, and the law they imply for compounding

Written 2026-11-05 18:51 ET (PowerShell clock) by the Silicyte lead, BEFORE any quantity below was computed.
Data: silicyte-0128 round_t.json, rounds 0..10, s1 and FRONTIER_s2..s4. Stdlib, login node, no GPU.

## Model (stated before data)
- Capability is per-step accuracy p: a depth-d task is solved with probability about p^d, so d50 = ln 0.5 / ln p, and the per-step
  error is e = 1 - p.
- Learning law: e = A N^(-alpha), N = rows the policy was trained on (P_0: 256; P_t: train_examples of round t-1).
- Feedback law: rows added per round r_t = own_new + hindsight_new = B d50_t^gamma (longer solutions carry more step rows).
- Then dN/dt is proportional to N^(alpha gamma), and for alpha gamma < 1: d50 grows like t^(alpha / (1 - alpha gamma)).
  - Reach ACCELERATES in rounds iff alpha (1 + gamma) > 1.
  - The loop COMPOUNDS in the strong sense (exponential or faster) iff alpha gamma >= 1.
- Prediction (from the audit's model-free deceleration): alpha (1 + gamma) < 1 in every seed.

## Quantities
- p_t two ways: (i) from the registered logistic d50_fixed, p = 0.5^(1 / d50); (ii) the geometric MLE of p from the per-depth MEAS
  solve counts (by_depth, depths 1..10), grid 0.500..0.999 step 0.0005.
- alpha_k = -(OLS slope of ln e_t on ln N_t), t = 0..10. gamma_k = OLS slope of ln r_t on ln d50_t, t = 0..10.
- Report alpha, gamma, alpha gamma and alpha (1 + gamma) per seed, mean and sd across seeds, for both p estimates.
- The multiplier: how many times larger alpha gamma would have to be to reach 1, and alpha (1 + gamma) to reach 1.

## Rule
- CONSISTENT iff alpha (1 + gamma) < 1 in all 4 seeds under estimate (ii); then the law explains 0128's deceleration and names the
  lever (raise alpha: learn more per row; raise gamma: rows per round that grow faster with capability, the reinvestment channel).
- INCONSISTENT otherwise (the law predicts acceleration that 0128 does not show, so the model is wrong and must not guide design).
