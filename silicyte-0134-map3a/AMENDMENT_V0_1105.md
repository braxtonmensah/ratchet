# AMENDMENT, before any arm is read: V0 on the real model returned False. The diagnosis and the decision rule

Silicyte lead, 2026-11-05 21:33 ET (PowerShell clock).

## What has been seen
map3a_run.log up to its last line, written 20:34:34 ET: "CHECK hook at c=0 gives identical tokens to no hook on the real model
(48 samples): False", and out_map3a/checks.json {"zero_identical": false, "zero_n": 48}. No HELD line exists (the BASE arm is still
generating; the I1 card read 100% utilization with the MAP3A process at 35,966 MiB at 21:29). No solve count of any arm has been read.

## What V0 assumed
V0 compares two HF generate calls with the same torch seed, one without the hook and one with the Steer hook at c = 0, and requires
identical tokens. That presumes bitwise-deterministic GPU sampling across calls. The premise was verified only on CPU (smoke:
bf16_c0_generate_identical True on a tiny random model) and never on the H100 with the real model. The c = 0 vector is exactly zero
(c times sigma with c = 0; the same POS vectors at c = 1 give a finite KL of 0.0028 nat), and `out + 0` cannot change a value, so the
remaining candidate is sampling that is not reproducible across calls on the GPU. Either way, the gate as written cannot tell the
hook from the sampler, so it is replaced by the probe below, and the rule is fixed here before the probe runs.

## The probe (aa_probe.py, sha256 in this folder's .sha256 file; runs on the empty renewal card R2 12699476; reads no solve data)
1. Logits on one forward pass over the 2 held prompts: none vs c = 0 hook (bitwise), and none vs none.
2. Greedy decode of 64 tokens: none vs c = 0, none vs none.
3. Sampled with MAP3A's sampler and seed (T 1.0, top_p 0.95, top_k 20, K 24, 2 prompts = 48 rows, 400 new tokens): A vs A' (no hook
   twice), A vs Z (c = 0 hook), with the number of rows that differ and the first divergence index per row.

## The rule
- PASS: logits none-vs-c0 bitwise identical, greedy none-vs-c0 identical, and the sampled A/A' differs about as much as A/Z (rows that
  differ within 4 of each other, out of 48). Then the hook is inert at c = 0 and the sampler is nondeterministic across calls. V0 passes
  on the logits and greedy tests; the A/A' rows-differ fraction is recorded as the noise floor for every arm's differ_from_base
  diagnostic; the registered reads proceed unchanged (paired solve-fraction tests over concepts, which never assumed bitwise
  reproducibility of samples).
- FAIL: logits none-vs-c0 differ, or greedy none-vs-c0 differs, or A/A' is identical while A/Z is not. Then the hook path changes the
  computation at c = 0; no MAP3A arm is interpreted (VOID) until the cause is found, fixed, and the fix registered.
- Anything else: UNRESOLVED; no arm is interpreted; a second probe is designed and registered.

The MAP3A arms keep running meanwhile (map3a.py does not stop on V0). Their solve counts stay unread until this rule has been applied
and its outcome published beside this file.

## Part 2 (21:46 ET): probe 1 returned UNRESOLVED by its own rule; the second probe and its rule, registered before it runs
Probe 1 (aa_probe.json, 21:40:26 ET, R2): logits with the c = 0 hook bitwise identical to no hook (maxdiff 0); greedy c0-vs-none
identical (0 of 2 rows) while greedy none-vs-none already differed (1 of 2 rows, from token 17); sampled rows differing 19 (none/none),
13 (none/c0), 16 (none'/c0) of 48; first divergences at tokens 15 to 364. By the rule above this is UNRESOLVED: not PASS because
|19 - 13| = 6 > 4, not FAIL because no condition fired. The bar was the mistake: with about a third of rows differing, a count's sd is
about 3.3 and the difference of two counts has sd about 4.7, so the tolerance of 4 sat below the rerun spread (the 11/04 rule: an
equivalence bar must sit above the same-seed rerun spread). The evidence so far says the computation, not the hook, varies from call to
call on the H100: no-hook greedy decoding is not reproducible across two calls.

Probe 2 (aa_probe2.py, sha256 in AMENDMENT_V0_1105.sha256; R2; reads no solve data):
- Part 1, deterministic kernels (CUBLAS_WORKSPACE_CONFIG :4096:8, torch.use_deterministic_algorithms(True), SDPA math backend):
  none twice and c = 0 once, MAP3A's sampler and seed, 48 rows x 400 tokens.
- Part 2, default kernels, powered: 4 no-hook runs and 4 c = 0 runs at 96 rows (4 held prompts x K 24), same seed. Pairwise counts of
  rows that differ: 6 none/none pairs, 6 c0/c0 pairs, 16 none/c0 pairs. The band is [min(none/none) - sd, max(none/none) + sd].
Rule, in order:
1. PASS_DETERMINISTIC if, with deterministic kernels, none/none differ in 0 rows and c0/none differ in 0 rows.
2. FAIL if deterministic kernels make none/none identical but c0/none differs.
3. Otherwise (deterministic kernels still not reproducible): PASS_POWERED if the mean none/c0 count and the mean c0/c0 count both lie
   inside the none/none band; FAIL if the mean none/c0 count exceeds the band's top; UNRESOLVED otherwise.
On PASS, V0 is satisfied by the logits identity plus this probe; the none/none mean differ fraction is the recorded noise floor for the
differ_from_base diagnostic; the registered reads proceed unchanged. On FAIL, every MAP3A arm is VOID until the hook path is fixed and
re-registered. On a second UNRESOLVED, MAP3A is set aside (it is the lowest-priority test on the cards) and no arm is interpreted.
