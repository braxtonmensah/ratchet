# NOTE (2026-11-05 20:45 ET, Silicyte lead): AMENDMENT A1 was probed and NOT switched on; the registered loop continues from round 4

- Why A1 was drafted: rounds 1-3 had 0 strict climbs in all 3 TRAINED seeds, so training was skipped every round (TRAINED = FROZEN).
  The builder found 0 of 648 round 1-2 rollouts were new matrices: the base model pastes the shown program (line overlap 0.983-0.986).
- A1 (AMENDMENT_A1_DRAFT.md, sha256 f2bca6e2; armt_a1.py 5d7db6b8): sampling T 1.0 / top_p 1.0 / top_k 20 for both arms plus
  copy-safe near-miss rows, switched on ONLY if a pre-registered probe on untrained streams yields >= 3 rows in >= 2 of 3 streams with
  template validity >= 0.42 in all three. Independent verifier: VERDICT_ARMT_A1.md (GO for gpucheck and probe only).
- a1gpucheck PASS (20:13 ET): weighted-loss path norms 0.0 / 0.462 / 0.863 for weights 0 / 1 / 0.25.
- a1probe (20:13-20:43 ET, step 12693135.5): **A1_PROBE_FAIL rows [3, 1, 2], validity [0.787, 0.787, 0.787]**. Only one stream
  reached 3 rows.
- Per the verdict's fallback: STOP removed and the REGISTERED armt.py (8fce8dad) relaunched from round 4 at 20:44 ET (step
  12693135.6). No AMENDMENT_A1.json exists; A1 is not active. The registered expectation stands: NO_UPDATE at round 6 is likely.
