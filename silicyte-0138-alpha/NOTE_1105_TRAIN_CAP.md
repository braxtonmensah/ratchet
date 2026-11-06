# NOTE (2026-11-05 20:26 ET, Silicyte lead): 0138 training memory cap raised from 0.65 to 0.85 on a dedicated card

- The verifier's launch line set ALPHA_TRAIN_FRAC=0.65 (55.3 GB). SMOKE on H5 (g83, card alone, 84.5 GB free) measured:
  string-target fit SMOKE_S peak_allocated 36.51 GB; as-run 0128-format fit SMOKE_H needed about 57 GB and hit VOID_OOM at the 0.65 cap
  (peak 44.13 GB plus a 12.63 GiB request). Rerun at ALPHA_TRAIN_FRAC=0.85 (72.3 GB): SMOKE_H peak_allocated 64.26 GB, reserved 72.27 GB.
- The cap is a memory limit only; no training or scoring computation changes. All 0138 cards run alone on their card.
- Finding: the 0128 hindsight-format defect costs 76% more training memory on the same rows (64.26 vs 36.51 GB), consistent with its
  prompts being 970 vs 434 tokens.
