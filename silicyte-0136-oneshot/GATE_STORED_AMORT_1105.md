# GATE (exploratory, stored rows only): does 0128's policy need less search for the same task as it trains? (one-shot meaning (d), proxy)

Registered 2026-11-05 18:46 ET (PowerShell clock) by the Silicyte lead, BEFORE any of the quantities below were computed.
Data: silicyte-0128 search_t.json, rounds 0..10 only (the registered A1 rounds), runs s1, FRONTIER_s2, FRONTIER_s3, FRONTIER_s4. No GPU.
Amendment 18:48 ET, before any quantity was computed (the first run crashed opening runs/s1/search_0.json: the legacy seed 1 keeps no
search files): MEAS rows are read from round_t.json fixed_rows (the registered MEAS rows, same fields tid/depth/v/c/exec, all 4 seeds);
the decoder lever check uses dp/tr rows of the FRONTIER_s2..s4 search files.
Status: EXPLORATORY. It cannot confirm meaning (d); the full test (beam 1 vs beam 4 scoring of saved adapters) is the 0136 builder's.

## Decoder (bootseed0128.beam2, B 4, 54 ops, fixed op order, last step exhaustive)
exec counts op executions. A solve of length L: L = 1 if exec <= 54; else L = 2 + floor((exec - 55) / 216) and the final-step parent's
beam rank j = floor((exec - 55 - 216 (L - 2)) / 54), in 0..3. Valid only when every expanded beam holds 4 states.
**Lever check first:** on dp and tr rows (which store prog), decoded L must equal len(prog) on 100% of solved rows; else STOP, the
decoder is wrong and nothing below is read.

## Quantities (MEAS pool 29000, the same 300 tasks every round and seed)
- Q1(k, t): among MEAS solves with L >= 2, the share with j = 0, stratified by L (per-L share, averaged with weights fixed as the
  pooled L distribution over all seeds and rounds), so a deeper solve mix cannot move it.
- Q2: tasks solved in both an early round (0..2, first solve) and a late round (8..10, last solve) at the same L: sign test of
  late exec < early exec vs late exec > early exec, per seed and pooled.
- Q3(k, t): share of MEAS solves with L < nominal depth (shortcuts). Telemetry only.

## Rule (fixed now)
- SIGNAL iff the OLS slope of Q1 over rounds 0..10 is > 0 in all 4 seeds AND the one-sided t of the mean slope across seeds
  exceeds t_{0.95,3} = 2.353 AND the pooled Q2 sign test has one-sided p < 0.05.
- Otherwise NO SIGNAL in stored rows. A NO SIGNAL does not kill meaning (d): j shows only the last step's ranking, not greedy reach.
- Either way, the result is reported with every per-seed slope and the Q2 counts.
