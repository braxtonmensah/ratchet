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
