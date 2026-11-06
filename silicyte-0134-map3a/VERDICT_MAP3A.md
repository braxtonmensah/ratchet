VERDICT: GO

# VERDICT MAP3A (silicyte-0134), independent verifier, 2026-11-05 20:23 ET

Read in full: BUILD_MAP3A.md, PREREG_MAP3A_DRAFT.md, map3a.py, map3a.sh (laptop), sets.out, smoke_cpu.out, power.out, sets.json
(Quartz), map2.py (sha bd8e06dc..., 299 lines), out_map2 listing, held.json, split.json, map.json, AUDIT PART2 sec. 5.
My own checks ran on Quartz login h1 with stdlib python3 -I, nice 19, in /N/scratch/bsmensah/verify_map3a/ (vsets.py 7.5 s,
vpow.py; outputs vsets.out, vpow.out). No torch, no srun, nothing submitted or cancelled, nothing written outside verify_map3a and
this file.

GO, with two conditions that do not block the launch: (C1) the floor/ceiling report registered in item 4 below is produced at read
time; (C2) the wording fix in item 1. Neither changes code, data or a registered test.

## 1. Sets equal the neurons MAP2 applied: CONFIRMED (independent, no torch)
vsets.py parsed map_full.pt (zip pickle, restricted unpickler) and the three adapter_*_x0.0 safetensors directly:
- T is HalfStorage [36, 12288]; sha256 of the fp16 bytes 4d6d3bfe9bd63ec3... equals sets.json sha256_T16. Confirms map2.py:151
  saves T.half() while map2.py:135-136 rank the fp32 T.
- lora_A is F32; every nonzero is exactly 1.0, one per row, rows contiguous from 0. Max rows per layer: POS 17, NEG 17, RAND 13, all
  below RMAX 64, so MAP2's cap at map2.py:173-174 never fired (held.json: applied 256, capped 0 for all x0.0 arms).
- Adapter set == sets.json set: POS True, NEG True, RAND True (256 unique each). RAND also equals Random(77) reproduced in stdlib.
- The tie rule cannot change membership beyond exact fp16 ties: every neuron strictly beyond the boundary is in the adapter, and
  every adapter member is at least as extreme as the boundary (POS True, NEG True). So only exact-tie neurons are decided by MAP2's
  record. Within-layer adapter rows are monotone in T16 (True), and map.json top-100 is non-increasing in T16, all in the adapter,
  equal to sets.json's first 100 in order (POS and NEG True; max |map.json t - T16| 0.0059 / 0.0055).
- NEG boundary: 254 strictly below -4.37891, 3 at it (L26.N1570, L22.N4863, L15.N4885) for 2 slots; adapter holds L22.N4863 and
  L15.N4885. Matches the builder.
- C2 wording fix: POS ALSO has an exact tie at its last slot that the builder does not mention. 255 strictly above +4.39453, 3 at it
  (L23.N7413, L19.N1393, L5.N1047) for 1 slot; the adapter holds L19.N1393. A plain argsort happened to pick the same one, so
  "members changed []" is true, but the sentence "membership of 1 NEG neuron cannot be derived from map_full.pt alone" should read:
  "3 boundary decisions (POS 1 of 3 tied, NEG 2 of 3 tied) come only from MAP2's adapters; only the NEG one differs from a plain fp16
  argsort." Not a blocker: the run takes membership from the adapter-verified sets.json, and the GPU smoke re-runs sets().
- Order inside sets only matters for the map.json report; the edit uses the set (Steer sums over it), so the order tie-break is
  harmless.

## 2. HOOK_SMOKE: PASS, and the code tests the production path
smoke_cpu.out (map3a.py sha 39f40041): c0_identical_fp32 True; prehook (literal act += c*sigma on down_proj input) vs Steer constant
vector maxdiff 2.1e-07 with edit-vs-base 0.582; hand last layer 1.2e-07 (delta 0.361); hand mid-layer residual 2.4e-07; bf16
c=0 logits and generate identical True; c=30 changed 100 tokens; hook calls 60 == 3 layers x 20 steps; real down_proj [4096, 12288],
36 layers, silu; tokenizer strings 100/100 and ids 100/100 equal to AutoTokenizer. smoke() uses the same Steer class as run().
Qwen3 down_proj has no bias, so W(x + d) = Wx + Wd and the forward-hook constant is exactly the additive edit (up to bf16 rounding).
Left-pad positions also get v, but they are masked as keys, so no leak.

## 3. Power: CONFIRMED against an independent t (Simpson integration of the pdf, not incomplete beta)
- df 39 quantiles: 0.85094 (upper 0.20), 1.68488 (0.05), 2.02269 (0.025), 2.42584 (0.01), 2.70791 (0.005); textbook 0.851,
  1.6849, 2.0227, 2.4258, 2.7079. Upper 0.0125: 2.33126. P(T > 2.816) = 0.00379 (MAP2 0.0038).
- map3a t_upper vs Simpson over t in [-4, 4]: max diff 7.1e-15. The t = 0 crash of lc_b18 is fixed (t_upper(0) = 0.5).
- Recomputed table from MAP2 held.json (11 arms, binomial sd 0.1156 at K 8): Holm-step MDE 5.82 / 4.11 / 3.36 / 2.91 points at K
  8 / 16 / 24 / 32; power at 13/320 0.457 / 0.789 / 0.931 / 0.979. Matches power.out. K 24 is the smallest K with MDE <= 4.06.
- 18 concepts 0/8 and 3 at 8/8 in every MAP2 arm: confirmed. Power uses the central-t shift approximation; fine at this power.

## 4. PREREG: CONFIRMED, one reporting gap (C1)
- PRIMARY (Holm over 4): POS+c > NEG+c and NEG-c > POS-c at c 1 and 3. read() builds exactly these 4 rows for DOSES [1, 3] and
  Holm-corrects them at 0.05 step-down; SECONDARY 8 rows match too.
- PC: RAND at the smallest c in {10, 30, 100, 300} with mean KL >= 0.5 nat on 20 map prompts (no solve data); V2 = BASE > PC
  one-sided p < 0.05. V0: c=0 hook identity on the real model (checks.json). V1: HF BASE (K 24) vs MAP2 vLLM BASE (K 8) per concept,
  paired, two-sided, PASS if p > 0.05; read() implements it. MDE stated (3.36 points at K 24).
- MAP2 held per-concept order equals HELD order (map2.py:195 samples HELD), so V1 pairs the right concepts.
- C1 GAP: the PREREG reports MAP2's floor/ceiling (18 at 0/8, 3 at 8/8 in every arm), but read() reports nothing about MAP3A's own
  floor/ceiling or the audit's constant-output concepts. MAP2 BASE has 5 concepts at 8/8 (c047, c052, c091, c092, c048) and 25 at
  0/8; audit sec. 5 constant-output set c042 6, c047 8, c091 8, c041 6, c092 8 = 36 of 82. A PRIMARY pass could come from an edit
  that breaks trivial constant-output concepts. Registered here, before any MAP3A data, as a REQUIRED DESCRIPTIVE report (not a gate,
  not a test), computed from held.json "per":
  (a) per arm: number of concepts at 0/24 and at 24/24, and concepts at 0 in every arm / 24 in every arm;
  (b) per arm: solves on the 5 audit constant-output concepts (c042, c047, c091, c041, c092) and on c052, c048;
  (c) the 4 PRIMARY contrasts recomputed with those 7 concepts removed (n 33), with mean difference and p, labelled descriptive.
  Any ADDITIVE CAUSAL PASS whose effect vanishes or reverses in (c) must be stated as "carried by trivial concepts".
  This needs no map3a.py change (held.json keeps per-concept counts); do not edit map3a.py while the run executes.

## 5. Memory: CONFIRMED in code
gpu_setup(): torch.cuda.init(), mem_get_info, then set_per_process_memory_fraction(38e9 / total) before the model loads (no CUDA use
earlier: sets() loads on CPU). REFUSE exit 4 if free < cap + 1 GB (39 GB), if nvidia-smi fails, if any other GPU process's cmdline is
unreadable, or if it contains "bootseed0128". All refusals are on the safe side. Note: frac on an 80 GB H100 (about 85.0e9 B total)
is about 0.447, not 0.48 as BUILD says; cosmetic. Memory model at 48 rows: 16.4 + 16.2 KV + 3.0 = 35.6 GB, 2.4 GB margin under the
cap; an OOM inside the cap kills only MAP3A and the run resumes per arm.

## 6. sha256 laptop == Quartz: CONFIRMED
map3a.py 39f40041b62148c5..., map3a.sh 5effd02a4e7cf7d0..., PREREG_MAP3A_DRAFT.md 362e074125873cf6..., BUILD_MAP3A.md 8706b9be4088d222...
equal on both; sets.json 0546eb88e7263f2b... on Quartz.

## Launch (lead only; not run by the verifier)
map3a.sh is a bash step with its own memory gate, so it does not fit qrun.sh (which runs a .py). Do qrun's two checks by hand:
1. `squeue -h -j <holder> -o %T` must print RUNNING.
2. `srun --jobid=<holder> --overlap -n1 -c 8 --cpu-bind=none nvidia-smi --query-compute-apps=pid,used_memory --format=csv < /dev/null`
   shows no bootseed0128.py and at least 39 GB free.
3. Exact launch line:
```
cd /N/scratch/bsmensah/silo/map3a0134
nohup srun --jobid=<holder> --overlap -n1 -c 8 --cpu-bind=none env MAP3A_K=24 MAP3A_BS=48 MAP3A_CAP_GB=38 LC_NCORES=7 \
  bash /N/scratch/bsmensah/silo/map3a0134/map3a.sh > /N/scratch/bsmensah/silo/map3a0134/map3a_run.log 2>&1 < /dev/null &
```
4. Prove the launch with the MAP3A_STEP_START line in map3a_run.log within 45 s, then GPU_SMOKE_PASS, then MEM_CAP / NEIGHBOURS,
   CHECK hook at c=0 True, KL RAND+..., and the first BASE tok/s. Do not edit map3a.py or map3a.sh while the step runs.
