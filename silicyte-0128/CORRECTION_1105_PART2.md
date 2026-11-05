# CORRECTION (2026-11-05 18:54 ET, Silicyte lead): claims in r10/RESULT_0128_A1R10.md still overstated after 745b4a9

Source: AUDIT_RSI_CONCLUSIONS_1105_PART2.md (independent read-only auditor, recomputed on Quartz). The registered result file is not
edited; this note supersedes the sentences below. Each line: the claim, then the corrected sentence.

1. "The weights reset every round ... cosine 0.05 to 0.09 ... What accumulates is the self-made dataset, not the weights."
   Corrected: Each round fits a fresh LoRA from the base model (lib/reachlaw.py:125); this is true by code. The 0.05-0.09 cosine between
   consecutive weight changes is not evidence for it: fits from different seeds, sharing only about 5% of their rows, give 0.033-0.050,
   while consecutive fits share 80-88% of their rows.
2. "The loop reliably improves itself: +0.18 depth per round on a never-trained ruler ... It does not speed up within 10 rounds."
   Corrected: Refitting a fresh LoRA each round on the growing self-made dataset raises d50 on a never-trained ruler by 0.18 per round
   (0.127 model-free), with no detectable speed-up; the test cannot see a speed-up of 10% per round (power 0.30) or one starting after
   round 5, and there is no fixed-teacher control, so this is not evidence that self-generated data does better than other data of the
   same volume.
3. "So acceleration of 20% per round or more is ruled out over these 10 rounds; 10% per round is not."
   WITHDRAWN (18:12 ET): endpoint-matched power is 0.67 at m 1.2 and 0.30 at m 1.1.
4. "UNDERPOWERED gate: ... power at the measured noise is above 0.6."
   Corrected: Power above 0.6 holds only for m >= 1.2 with the endpoint matched (0.67); at m 1.1 it is 0.30.
5. "that check is pending; if it fails, this note will say so."
   Corrected: The check passed for all three seeds: 300 of 300 redone round-10 MEAS rows equal the archive (POST OK,
   post_1105_postfix.log, e3157e7).
6. Appendix: "So the linear d50 is not hiding an acceleration at the frontier."
   Corrected: No depth band shows detectable acceleration; at d7-10 the seed spread (c sd 0.0172, t -1.00) is too wide to rule one out.
   "The hardest tasks improve 5 to 10x" -> d7-10 solve rates rise from 0.00-0.02 to 0.07-0.12.
7. "The search-space caveat used 42 ops; the world has 54."
   Corrected: The world and the policy have 54 ops; 42 is the number of distinct ops in the loop's verified programs (the 12 cut ops
   never appear). In 54-op search units the logistic gain is 54^0.181 = 2.06x per round (54^0.127 = 1.66x model-free).

Also checked by the auditor: 0 overlap between all 41,836 trained rows (44 rounds) and MEAS 29000 / MEAS_DEEP (SUPPORTED); the 0133
macro premise is OVERSTATED (61.8% of top-20 bigram uses are same-family compositions; 13.2% saving with families completed; the
i.i.d. generator alone gives 16.3%; same reach with and without macros at 2.07x executions).
