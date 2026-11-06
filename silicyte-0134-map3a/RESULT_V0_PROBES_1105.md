# RESULT: MAP3A V0 probes. V0 PASS (powered): the hook is inert at c = 0; H100 sampling is not reproducible across calls

Silicyte lead, 2026-11-05 21:58 ET (PowerShell clock). Rule: AMENDMENT_V0_1105.md (parts 1 and 2, both registered before their probe ran).
Data: aa_probe.json, aa_probe2.json (this folder; produced on R2 12699476, Qwen3-8B bf16, torch 2.13.0+cu130).

## Probe 1 (21:38 to 21:40, 2.1 min)
- Logits, one forward pass, 2 held prompts, last 8 positions: c = 0 hook vs none bitwise identical (max diff 0); none vs none identical.
- Greedy 64 tokens: c = 0 vs none 0 of 2 rows differ; none vs none 1 of 2 rows differ, from token 17.
- Sampled, MAP3A's sampler and seed, 48 rows x 400 tokens: rows differing none/none 19, none/c0 13, none'/c0 16.
- Verdict by its registered rule: UNRESOLVED (|19 - 13| = 6 > 4). The bar sat below the rerun spread (count sd about 3.3, difference sd about 4.7).

## Probe 2 (21:44 to 21:51, 7.0 min)
- Deterministic kernels (CUBLAS_WORKSPACE_CONFIG :4096:8, torch.use_deterministic_algorithms(True, warn_only), SDPA math backend),
  48 rows x 400 tokens: none/none 17, c0/none 15, none'/c0 15 rows differ. Still not reproducible, so rule steps 1 and 2 do not apply.
- Powered, default kernels, 96 rows x 400 tokens, 4 no-hook and 4 c = 0 runs with the same seed:
  none/none pairs 39, 36, 38, 32, 39, 39 (mean 37.2, sd 2.54; band 29.5 to 41.5);
  c0/c0 pairs 39, 41, 44, 38, 41, 37 (mean 40.00);
  none/c0 pairs (16) 33, 39, 35, 34, 41, 40, 37, 42, 33, 39, 36, 37, 34, 35, 35, 35 (mean 36.56).
- Verdict by rule step 3: PASS_POWERED (both means inside the none/none band).

## Conclusion
V0 is satisfied by the bitwise logits identity plus the powered sampled comparison. The registered V0 check presumed reproducible GPU
sampling across generate calls and so measured the sampler, not the hook; the c = 0 vector is exactly zero (max abs 0.0, finite).
Noise floor recorded for the differ_from_base diagnostic: 37.2 of 96 rows (38.7%) differ between two identical no-hook calls at 400 new
tokens; at MAP3A's 1,500 new tokens the fraction is higher (not measured), so differ_from_base is read only as near 1 (an active edit)
against near the floor (a weak one), never as a solve surrogate. The registered reads (paired per-concept solve fractions over the 40
held-out concepts, Holm within family) never assumed bitwise reproducibility and proceed unchanged. MAP3A's BASE arm was still
generating on I1 at 21:58 (no HELD line yet); I1 ends about 22:33 and the run resumes per arm on H8 through the lane's autopilot.

Lesson, already compiled in memory: an equivalence bar must sit above the same-condition rerun spread; probe 1's did not.
