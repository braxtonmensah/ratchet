# PREDICTION (registered before any 0129 round-1 result is read): what the two-exponent law says 0129's primary will show

Written 2026-11-05 19:09 ET (PowerShell clock) by the Silicyte lead. Uses ONLY 0128 rounds 0..10 (FORECAST_0128_EXT_1105.json fits) and
no 0129 data. 0129 (PREREG_OPEN0129.md, registered 18:15 ET) keeps 0128's loop and P_0 per seed and removes the depth ceiling.

## Rule (fixed now)
- For 0129 seed k use 0128's fitted law for the matching seed (k = 1 -> s1, k >= 2 -> FRONTIER_sk): e_t = A N_t^(-alpha),
  N_{t+1} = N_t + B d_t^gamma, d_t = ln 0.5 / ln(1 - e_t) (geometric d50; any positive rescaling to the 0129 ruler leaves the SIGN of
  delta unchanged and scales its size).
- Simulate t = 0..R for R = 20, 25, 30, 35 from N_0 = 256; compute 0129's registered statistic delta = OLS slope of d over rounds
  h..R minus OLS slope over 0..h, h = floor(R / 2); also the ratio delta / (mean per-round gain) as a unitless size.
- PREDICTION: delta < 0 for every seed and every R (the law decelerates), so the law predicts 0129 will NOT read TAKEOFF.
- How it is scored at 0129's registered read: the sign of each seed's observed delta on the nominal axis against this prediction, and
  the observed unitless size against the predicted one. A positive observed delta in 3 or more of 4 seeds FALSIFIES the law for
  ceiling-free worlds (the ceiling was then binding the exponents).
