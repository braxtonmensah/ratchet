# AMENDMENT 1 (DRAFT): a weight-training arm for silicyte-0119 (Ratchet), as a Qwen3-8B sub-study

Drafted: 2026-11-04 20:00 ET (PowerShell Get-Date); revised the same evening with the coordinator's design input from
RESEARCH_ARC_WINNERS_1104.md (SOAR-style hindsight relabelling as the primary arm, CORRECT-ONLY as a registered control).
Status: DRAFT. Not appended to PREREG.md, not registered in the loop ledger, not committed. The lead appends it under PREREG
`## AMENDMENTS` (the line must begin `AMENDMENT 1 ` exactly; see sec. 8) and registers the sec. 14 block. Nothing in this draft has
run: no GPU job, no CPU job, no training, no code edit under `ratchet/`. Read-only checks only: the files in sec. 1 and Quartz
login-node reads on 2026-11-04 between 19:45 and 20:00 ET (`sbatch --test-only` with `-A students`; no job was created).

Why: the founder, on learning that Ratchet keeps weights fixed: "we haven't even trained or edited the weights". Ratchet as
registered grows only an in-context library of Python helpers with frozen weights (PREREG sec. 3, 4). This amendment adds the
question it leaves open: does a model that trains on its own verified outputs improve round after round, at equal compute?

Labels: SOURCE = a file, command or log line read for this draft; ESTIMATE = my number, not measured; RULE = registered by this
amendment once appended. Every ESTIMATE is replaced by a J1 measurement before any main job (sec. 10).

Deadlines used below (plan values, not events): D_GROWTH = 2026-11-10 22:00 ET, the latest start of any growth job.
D_SEAL = 2026-11-11 00:00 ET, the earliest moment the sealed key may be opened (the founder's note to the outside reviewer promises
no sealed scoring before that day).

## Method rules

1. Physics floor first. Compute the hard limit from measured sizes and hardware specs before any fix; the gap is where the bugs are.
2. Read the shipped artifact's own logs against its own name.
3. Hunt the constraint nobody uses.
4. Register the kill test before the data, and accept the null.
5. Read the code of what "obviously" happens.
6. Prove the lever reached the system before reading any effect. Every lever prints a marker line. Measure the noise (an A/A) before trusting a gain.
7. Map every byte, token and second before ranking anything.

## 1. Inputs read, and what they fix

| fact | value | SOURCE |
|---|---|---|
| Ratchet proposer | Qwen3.6-35B-A3B fp8, weights fixed, temp 0.8, top_p 0.95, max 4,096 gen tokens | PREREG sec. 3 |
| fp8 copy on disk | 37,454,789,472 B of tensors (routed experts 32,216,186,880; embed+lm_head 2,034,237,440; GDN 1,016,597,760; mtp 853,668,480; visual 893,142,496); `quant_method fp8`, e4m3, dynamic activations, block scales (`weight_scale_inv`) | safetensors headers and config.json of `tufa/models/qwen36_35b_a3b_fp8` |
| bf16 copy on disk | YES: `/N/scratch/bsmensah/arc26/tufa/models/qwen36_35b_a3b`, 26 shards, `quantization_config` null, 71,903,645,408 B of tensors; text model without visual (893,142,496) and mtp (1,689,281,536) = 69,321,221,376 B (64.56 GiB), of which routed experts 64,424,509,440 B (93%) | safetensors headers; index `total_size` 71903645408 |
| architecture | `Qwen3_5MoeForConditionalGeneration`, 40 layers (30 Gated DeltaNet, 10 full attention), 256 experts, 8 active, vocab 248,320, experts stored as 3D tensors | config.json; transformers 5.18.0 `modeling_qwen3_5_moe.py` lines 844 to 869 |
| h100-debug QOS | `cpu=24, gres/gpu=1, mem=380000M` per job, 1 job per user, 1:00:00 | `sacctmgr show qos h100-debug`; `scontrol show partition h100-debug` |
| 2, 3 or 4 GPUs per h100-debug job | REFUSED: `QOSMaxGRESPerNode` for gpu:h100:2, :3 and :4; gpu:h100:1 test-only start estimate 2026-11-04 23:52 on g38 | `sbatch --test-only -p h100-debug -A students` |
| h100-debug occupancy now | own `sa_debug` 12676791 RUNNING (holds the 1-job slot) | `squeue -u bsmensah -p h100-debug` |
| Qwen3-8B | bf16, 16,381,516,776 B, 36 layers, 8 KV heads, head_dim 128, hidden 4,096, vocab 151,936, max_position 40,960 | `fourth_law/models/Qwen3-8B/config.json`, `du -cb` |
| 8B LoRA stack on record | consol.py `train()`: peft LoraConfig r 16, alpha 32, dropout 0, q,k,v,o,gate,up,down; AdamW lr 1e-4; bs 4; 2 epochs; peft 0.21.2 + accelerate 1.15.0 in `fourth_law/pylib`; adapters hot-loaded into a running vLLM server via `POST /v1/load_lora_adapter` | consol.py lines 507, 526 to 583; `ls pylib` |
| silent tail clipping | consol.py builds `ids = (pi + ti)[:3072]`, `lab = ([-100]*len(pi) + ti)[:3072]`: a row over 3,072 tokens loses its completion with no warning | consol.py lines 554 to 555 (rule 5) |
| consol.py train speed | TRAIN_DONE n 397 s 52 ... n 1004 s 116 (2 epochs) | `fourth_law/boot_llm/rounds.log` |
| vLLM env | vLLM 0.30.0, torch 2.13.0, transformers 5.18.0, flashinfer 0.6.18.post1; NO peft, NO fla, NO causal_conv1d in `lightning/venv_vllm` | `ls site-packages` |
| ARC row lengths | growth tasks (391 of 400 in the local ARC-AGI-2 training copy), demos + test inputs at 1 token per digit and per row newline: mean 1,000, p50 764, p90 2,041, max 6,510 tokens. Rows of task + 400 instruction + 1,000 gen tokens over 3,072: 70 of 391 (17.9%); over 4,096: 23; over 6,144: 5; over 8,192: 0 | node over `arc-prize-2026/data/ARC-AGI-2/data/training` and `splits/growth_ids_arcagi1_train.txt` |
| arc-dsl for PLANT | `silo/ratchet/data/raw/arc-dsl`: 400 `def solve_` in solvers.py (6,576 lines), dsl.py 1,524 lines | Quartz `grep -c`, `wc -l` |
| score_sealed.py | arm list from `config.ARMS` (8 library arms; hard-coded `STOCK` minus `FLAT_ARM` for W and gates); a second key access for a condition needs `--amendment <id>`, the id must appear as `AMENDMENT <id> ` under PREREG `## AMENDMENTS`, and each amendment id serves ONE key access across all conditions | score_sealed.py lines 502 to 541, 621 to 640; config.py lines 74 to 80 |
| SOAR (direct precedent) | arXiv 2507.14172 (Pourcel, Colas, Oudeyer, ICML 2025): Python programs on ARC-AGI-1; hindsight relabelling ("any sampled program is correct for the outputs it produces"); at most 50 rows per task (25 top + 25 bottom ranked, deduped); LoRA r256, alpha 32, 3 epochs, lr 5e-5, RS-LoRA; every iteration restarts from the Instruct weights on pooled data; 6k candidates per task per iteration; ARC-AGI-1 test 7B 14.25% to 36.25%; ablation (14B, ARC-train) no FT 29.29, correct-only 34.67, greedy-diverse 36.46; pooled data 7B 33.0 vs own-data 19.9; fine-tuning about 5% of total FLOPs | RESEARCH_ARC_WINNERS_1104.md sec. 4.1 (coordinator's read of the paper) |
| CodeIt | arXiv 2402.04858: CodeT5+ 220M, Hodel DSL; policy-only / cumulative ARC eval: CodeIt 49 / 59; no relabelling 24 / 42; no prioritised replay 38 / 58 | RESEARCH_ARC_WINNERS_1104.md sec. 4.2 |
| our weight-training record | 15 weight-update rows on Flash-Next, 0 PASS (GRPO r1 -0.0253, r2 -0.0678, r3 -0.057; LRFT1 +0.0063 BETWEEN; LRFT1F 87/158 vs 93/158; LRFT3+ACTDIR -0.038; HS-AONLY 12/158 vs 93/158; CEGIS 4/18 vs 11/18; ...) | RESULT_PORL_CRL_AUDIT_1031 sec. 0 line 11, sec. 2 |
| update noise | RLF1p vs RLF1b on the same 864 rows: pooled cosine 0.269, norm ratio 0.942; at 16-row Adam batches about 27% signal, 73% noise; rows, not steps, buy signal | memory arc-rl-update-is-mostly-noise-at-rlf1-scale... |
| credit and clipping | RLF1p/RLF1b/wide1 at max_len 20,480: 62 to 71% of rows credited 0 check and 0 submit tokens; rule: VOID an RL round with more than 5% clipped rows | memory arc-rl-rows-credit-wrong-tokens-tail-clipped |
| fourth-law weight findings | rho_match 0.981 [0.843, 1.118] (weights give head starts at par, never faster rates); CONT minus ORIG +0.014 TIE (self-generated rows carry about 0 new capability); ROLLCTX continuous + 1:1 replay = retraining at 17% of the examples; second-seed noise 0.2 to 0.5 d50 | memory fourth-law-lane-reuse-exponent-and-h100-rig |

Rule 2 read of consol.py's speed against its own comment: the comment says "glossary prompts (~2k tokens)", the log says 1,004 rows
x 2 epochs in 116 s = 0.058 s per row pass. At 6N = 6 x 8.19e9 = 4.9e10 FLOP per trained token and 989 TFLOP/s (H100 SXM dense bf16,
NVIDIA datasheet) a 0.058 s row pass holds at most 1,170 tokens even at 100% utilization. Those rows were much shorter than 2k tokens,
so the measured speed does not transfer to ARC rows. Training seconds below are ESTIMATES from FLOPs.

## 2. Feasibility: can the 35B-A3B be LoRA-trained and served with LoRA? (rules 1, 3, 5)

### 2a. Training the 35B-A3B on one 80 GB H100 inside a 1 h slot

- fp8 weights cannot be trained directly here: transformers' `integrations/finegrained_fp8.py` has `FP8Linear` for the forward path
  (grep found no `autograd.Function` or `backward`), and no fp8 trainer exists on our record. ESTIMATE: not usable.
- A bf16 copy exists: 69,321,221,376 B text-only = 64.56 GiB. One H100 80 GB holds about 79.6 GiB (ESTIMATE, typical 81,559 MiB),
  leaving about 15.0 GiB. fp32 logits alone at T = 8,192 are 248,320 x 8,192 x 4 B = 8.14 GB (7.58 GiB), so a step fits only with a
  chunked loss, gradient checkpointing and bs 1 (ESTIMATE). Alternative on record: pin the 64.4 GB of routed experts in host RAM (the
  FN trainer's `--pin all` layout; this QOS gives 380,000 MB host RAM, enough), measured on Flash-Next at 850 to 925 tok/s with a 583
  to 617 s load (RESULT_LEAN_RFT sec. 2, 4).
- No trainer for this architecture on record: consol.py is the dense Qwen3 path; the FN k5 trainer (`fn_trainer/k5_train/train_v2.py`)
  is bespoke to Flash-Next's INT4 experts (`int4_experts_v2c`) and QSA indexer (`qsa_vec_v3`) per `k5_env_v2.sh`. The HF reference
  forward loops over hit experts in Python (`Qwen3_5MoeExperts`, lines 856 to 869) and, without fla (absent from the vLLM venv; an fla
  overlay exists only in the FN k3 env), Gated DeltaNet falls back to `torch_chunk_gated_delta_rule` (lines 301 to 302). ESTIMATE: a
  working trainer is a multi-day build, not a config change.
- Co-residency fails: vLLM fp8 weights 37.45 GB plus a bf16 trainer 69.3 GB exceed 80 GB, and QOS refuses a second GPU. Every round
  pays a vLLM stop, a trainer load and a vLLM restart: ESTIMATE 300 s x 2 (SPEC 1.5, ASSUMED) + 240 to 620 s = 840 to 1,220 s, 23 to 34%
  of a slot before any token; or 2 jobs per round (sample job, train job), 12 jobs for the primary arm alone at R = 6.

### 2b. vLLM 0.30.0 serving a LoRA adapter on the 35B-A3B fp8

- The class supports LoRA: `Qwen3_5MoeForConditionalGeneration` inherits `SupportsLoRA` through `Qwen3VLForConditionalGeneration`
  (qwen3_vl.py lines 1791 to 1795), sets `is_3d_moe_weight = True` "For MoE LoRA weights loading" (qwen3_5.py line 703), and maps the
  packed GDN projections `in_proj_qkvz`, `in_proj_ba` (lines 301 to 311).
- MoE LoRA needs a LoRA-capable experts kernel: `lora/layers/fused_moe.py` line 77 asserts `moe_kernel.supports_lora()`; only experts
  classes that mix in `LoRAExpertsMixin` pass (TritonExperts, Marlin, TRT-LLM bf16, gpt-oss). The fp8 MoE oracle (`oracle/fp8.py`) has
  no LoRA-aware backend choice (the only LoRA routing is in `oracle/unquantized.py` lines 183 to 233), and its priority list puts
  FLASHINFER_TRTLLM, FLASHINFER_CUTLASS and DEEPGEMM ahead of TRITON. So `--enable-lora` with expert targets on the fp8 model is expected
  to trip that assert unless the backend is forced to TRITON (ESTIMATE, not run).
- The constraint nobody uses (rule 3): `--lora-target-modules` (LoRAConfig.target_modules; `model_manager.py` lines 430 to 437 skip any
  module not matched) can restrict LoRA to dense modules (attention, GDN projections, shared expert), so the fused MoE layer is never
  wrapped. That is the target set the FN LRFT arm trained ("GDN, QSA, shared experts; routed experts frozen", RESULT_LEAN_RFT sec. 1).
  UNVERIFIED at runtime; our record has a runtime LoRA that silently applied nothing on the 27B (memory
  arc-runtime-lora-silently-ignored), so it would need the sec. 7c probe even if it boots.

### 2c. Verdict

35B-A3B: NOT FEASIBLE as a registered arm in this window. Possible in principle (bf16 copy present; class supports LoRA; a dense-only
target set plausibly serves), but it needs (1) a new trainer for Qwen3.5-MoE with GDN kernels, (2) two model loads per round on a
1-GPU, 1-job QOS, (3) an unverified fp8 LoRA serve path. Qwen3-8B: FEASIBLE on the stack on record (consol.py trainer, peft 0.21.2,
vLLM hot-load of adapters), with vLLM and trainer co-resident on one card (16.38 GB weights each; ESTIMATE peak under 70 GB with the
r256 adapter, checked in J1). RULE: the weight arms run on Qwen3-8B as a self-contained sub-study with its own controls on the same
model, scored on the same 400 sealed tasks by the same `score_sealed.py`. Its result answers "does self-training compound for an 8B
proposer on ARC", not "would Ratchet's 35B compound"; RESULT.md says so in its first paragraph. SOAR's 7B is the nearest published
model size, which is a second reason for the 8B.

## 3. The prior, stated before the data (rule 4)

Our record has two hindsight-flavoured weight failures (RESULT_PORL_CRL_AUDIT_1031 sec. 0 line 11 and sec. 2): HS-AONLY, SFT on
hindsight-relabelled rows, 12/158 vs 93/158, and LRFT3 (LRFT round 3 on improved-model self-generated lives plus RSI hindsight rows,
then ACTDIR), -0.038 [-0.1024, +0.0301]. Both ran on the ARC lane's Flash-Next tool loop: multi-turn thinking lives with tool calls,
10k-token rows, the reward measured through stochastic box lives. HS-AONLY was 239 short tool-call rows that cut thinking 2.6x in 12
steps, i.e. off-format rows that collapsed the policy's format, not a test of SOAR-style relabelling (RESEARCH_ARC_WINNERS_1104 sec. 0
item 3). Rejection-sampling SFT is also null on our record (LRFT1 BETWEEN, LRFT1F FAIL, SFT-A1 40/63 vs 43/63).

What differs here, each a RULE: (1) single-turn program synthesis, non-thinking, completion = the program only; (2) every training
row's prompt is produced by the same `prompt.py` render the sampler uses, for the (possibly relabelled) task, and the completion is a
response the model itself emitted, so rows are byte-for-byte inference format (FT_FORMAT marker, sec. 7c); (3) the label is exact:
the sandbox executes the program, so a relabelled row is correct for its relabelled task by construction; (4) base-weight restart each
round on pooled rows (SOAR) instead of continuing one adapter; (5) a different base model (Qwen3-8B). The prior stays negative: none
of these differences has been tested on our record, and SOAR's gains came at a search budget 750x ours (sec. 12).

## 4. Design (RULES)

### 4a. Model, prompts, slices

- RULE: Qwen3-8B bf16 (sha256 of config.json + index in META), vLLM 0.30.0, `enable_thinking` False, temperature 0.8, top_p 0.95, max
  4,096 generated tokens, `max_model_len` 20,480 (Ratchet's value; covers the 6,000-token library arms), `max_lora_rank` 256. Prompt =
  Ratchet's FLAT prompt (`prompt.py`, no library block) for no-library arms, STOCK prompt for library arms. Same sandbox, same pass@2
  selection (PREREG sec. 5), same program contract (SPEC 4.2).
- RULE: before any model call the 400 growth ids are split by a seeded draw (seed 20261104, `random.Random(seed).sample` over the sorted
  id list) into TRAIN (320) and HELD (80); the HELD list and its sha256 are written beside the PREREG split hashes. HELD tasks are
  sampled every round for measurement and never contribute a training row to any arm except the PC-0 diagnostic adapter (sec. 7a),
  which is discarded. Sealed tasks never contribute training rows to any arm.

### 4b. Row modes

- RELABEL (primary; SOAR hindsight relabelling): every sampled program for a TRAIN task that runs on all demo inputs without error or
  timeout and returns valid grids (rectangular, 1 to 30 per side, colours 0 to 9) defines a relabelled task: the original demo inputs
  with the program's own outputs as demo outputs, and the original test input. Row = (render of the relabelled task, the model's
  response that contains the program). A demo-passing program's relabelled task is the original task, so correct programs are
  included. Degenerate programs are excluded (our filter, not SOAR's): output equal to input on every demo, or the same output grid
  on every demo. Per TRAIN task, pooled over all rounds so far, keep at most 16 rows: the 8 best by accuracy on the ORIGINAL demos
  (fraction of demos exact, then mean pixel accuracy) and the 8 most different among the rest (greedy max-min Hamming distance over
  the program's output grids), deduped by canonical code sha. SOAR keeps 50 (25 top + 25 bottom); 16 is the stated deviation that fits
  training into one job per round (sec. 10). SOAR's refinement pairs are NOT included (budget; deviation stated).
- CORRECT-ONLY (registered control; CodeIt A2, SOAR correct-only): rows only from programs that pass every original demo of a TRAIN
  task, original task render, same 16-row cap (8 best by length-independent seeded draw + dedupe; all such rows are equally correct).
- Rows never use public growth test outputs for selection; the share of kept rows whose program is test-wrong on the original task is
  reported (BARC's about 9% false positives, RESEARCH_ARC_WINNERS sec. 5.3 item 7).

### 4c. Arms

R rounds (R = 6, R_min = 4), S_g samples per growth task per round (S_g = 8 unless J1's rule in sec. 10 raises it), S_seal = 8 sealed
samples per task per seed (base), 3 sealed seeds (PREREG sec. 6).

| arm | growth | weights | sealed |
|---|---|---|---|
| SELFFT (primary, RELABEL) | each round r = 1..R: sample S_g on all 400 growth tasks from A_{r-1} (A_0 = zero adapter); add this round's RELABEL rows to the pool; train A_r FROM BASE on the pooled rows; serve A_r. After the last update one HELD-only pass (80 x S_g) under A_R | R trainings, each from base | A_R |
| SELFFT_S2 (A/A) | as SELFFT, round 1 only, sampling and row-order seeds disjoint from seed 1; then one HELD pass under its A_1 | 1 training | none |
| CORRECTONLY (registered control) | the SELFFT loop with CORRECT-ONLY rows, its own sampling chain (round r samples from its own A_{r-1}) | R trainings from base | its A_R |
| ONESHOT | one round of R x S_g base samples per growth task (its first S_g slots are SELFFT round 1's samples, as SPEC 13 I3); RELABEL the union under the same caps; one training from base | 1 training | A_one |
| FROZEN8B | none | zero r256 adapter, same code path (B = 0) | S_seal + extra per seed (sec. 5) |
| SELFFT_LIB (if it fits) | as SELFFT with Ratchet's frozen STOCK library L_R (35B-grown, sha from Ratchet FREEZE.json) in context and callable | R trainings | A_R^LIB with L_R |
| LIBFROZEN8B (if it fits) | none | zero adapter | L_R in context, S_seal + extra matched to SELFFT_LIB |

The library arms are the frozen-library control on the same model: SELFFT vs FROZEN8B isolates weights, LIBFROZEN8B vs FROZEN8B
isolates the library on the 8B, SELFFT_LIB asks whether they add. They are secondary and descriptive; L_R contains helpers from HELD
tasks, so HELD slopes of library arms are not read.

### 4d. Training recipe (RULE; SOAR D.4 where it fits a 1 h slot)

LoRA r 256, alpha 32, RS-LoRA scaling (`use_rslora=True`, peft 0.21.2), dropout 0, on q,k,v,o,gate,up,down; AdamW lr 5e-5, 10-step
warmup, constant after; 1 epoch per training (SOAR 3; cut for time, deviation stated); bs by a 32,768-token budget per optimizer step;
loss on completion tokens only; chunked cross entropy. Trainer = a copy of consol.py `train()` with: (a) no slicing: `max_len` 12,288
(no-library rows; worst measured prompt 6,510 + 400 + 4,096 = 11,006) and 20,480 for library rows; a row over `max_len` is CLIPPED,
dropped and counted, never cut; (b) labels cover exactly the completion tokens; (c) restart from base weights every training (fresh
adapter init, seed logged); (d) FT_UPDATE marker (sec. 7c). Trainer and vLLM share the card (vLLM `gpu_memory_utilization` 0.45,
ESTIMATE; set from the J1 peak).

## 5. Matched compute (RULE)

- Unit: one logical token at 2N FLOP. Sampling tokens (logical prompt tokens per SPEC 13 I2, plus generated tokens) count 1 unit each.
  Trained tokens (every token of every row, every epoch, every round's from-base retraining) count 3 units each: training costs 6N per
  token (forward 2N, recomputed forward 2N under checkpointing, input-gradient backward 2N; LoRA weight gradients are small) against 2N
  per inference token. Source of 2N and 6N: Kaplan et al. 2020, arXiv 2001.08361, sec. 2.1. Ratio 3 is fixed now; J1 also measures
  the seconds ratio rho_s = (H100 s per trained token) / (H100 s per generated token at the operating batch).
- H100 seconds: every job logs GPU-busy seconds per arm (sampling wall while that arm's requests are in flight, trainer wall, adapter
  load and probe). Ledger rows follow SPEC 4.4 plus `adapter_sha` and `train_tokens`.
- SELFFT total U_SFT = growth units + 3 x all trained tokens + its sealed units.
- ONESHOT: same growth samples by construction; its single training runs epochs over its union until its trained tokens equal
  SELFFT's total trained tokens (fractional last epoch by seeded row subset, cap 6 epochs; any shortfall becomes extra ONESHOT sealed
  samples so units match).
- FROZEN8B per seed: S_seal + extra samples per sealed task, extra = ceil((U_SFT,growth + 3 x T_SFT,train) / (400 x m_F)), m_F its
  measured mean logical tokens per sealed sample (the FLAT-TTC rule of PREREG sec. 4, applied per seed as SPEC 1.3), AND its realized
  H100 seconds per seed at least SELFFT's growth + training + per-seed sealed H100 seconds; the larger of the two budgets wins. The
  control always gets the larger budget. Marker FT_MATCH.
- CORRECTONLY is matched to SELFFT in sampling only (same S_g, R, S_seal); it trains on far fewer tokens. Its comparison with SELFFT
  is the relabelling ablation at equal sampling, as in CodeIt A2 and SOAR Table 2, and is not a compute-matched test.
- ESTIMATE at S_g 8, R 6, m = 1,400 prompt + 600 gen = 2,000: growth 6 x 3,200 x 2,000 = 38.4M units. RELABEL rows per round about
  320 TRAIN tasks x 8 x 0.8 x 0.6 executable / 320 x 320 = about 1,536 new rows (ESTIMATE: 60% of programs execute on all demos);
  pooled and capped at 16 per task: 1,536, 3,072, 4,608, 5,120, 5,120, 5,120 rows, 24,576 row-trainings x 2,000 tokens = 49.2M trained
  tokens, x 3 = 147.5M units. FROZEN8B extra = (38.4M + 147.5M + 1.3M) / 800,000 = 234, so about 242 samples per sealed task per seed.
  Rule 7 finding: at matched compute the from-base retraining makes the frozen control's budget 30 times the trained arm's sealed
  budget, and FROZEN8B's sealed sampling is the single largest line of the plan (sec. 10).

## 6. Primary quantity, tests, labels (RULE)

- Primary quantity Q: sealed solves of SELFFT (RELABEL) at round R minus sealed solves of ONESHOT, both of 400, pass@2 per PREREG
  sec. 5, a task SOLVED iff correct in at least 2 of 3 sealed seeds (PREREG sec. 6).
- Sealed tests: SELFFT vs ONESHOT and SELFFT vs FROZEN8B, each an exact one-sided McNemar test on the paired solved sets (Ratchet's
  `stats.py`), p < 0.05 each, intersection-union, no multiplicity correction. SELFFT vs CORRECTONLY: the same test, reported, not part
  of the gate.
- HELD slope (required): h_r = mean over the 80 HELD tasks of the per-task demo-pass fraction among S_g samples from A_r, r = 0..R (h_0
  from SELFFT round 1, h_R from the final HELD pass). Slope b = OLS of h_r on r; 95% one-sided lower bound by task-cluster bootstrap
  (10,000 resamples over the 80 tasks, seed 20261104). Reported with it: per-round gains h_r - h_{r-1} and their OLS trend (whether the
  gain per round rises), the same slope for CORRECTONLY, and HELD pass@2 test-correct per round from public growth outputs.
- Contamination gate: perturbed sealed copy (Ratchet's `perturb.py`, the main run's PERTURB.json and seed): SELFFT's net solves over
  ONESHOT on the perturbed copy must be at least half its unperturbed net. Only SELFFT and ONESHOT are sampled perturbed (FROZEN8B at
  about 242 samples per task would add about 46,000 s more).

Labels, applied in this order:

1. VOID: PC-0 or PC-1 fails (sec. 7a); any lever proof fails (sec. 7c); clipped rows over 5% of any training's rows, or any credit or
   format check fails (sec. 7d); any HELD or sealed task in a SELFFT, SELFFT_S2, CORRECTONLY or ONESHOT training row (FT_UPDATE
   n_rows_held or n_rows_sealed non-zero). A VOID run is retired after two attempts (PREREG sec. 9).
2. UNDERPOWERED (declared before the key is opened, printed as the headline whatever the gates give, gates still reported): fewer than
   R_min = 4 SELFFT trainings exist when D_GROWTH passes; or projected power below 60% (sec. 7b); or |Q| not larger than the sec. 7b
   A/A difference scaled to 400 tasks.
3. COMPOUNDS-WEIGHTS iff SELFFT beats ONESHOT and FROZEN8B (both p < 0.05), AND the HELD slope lower bound is > 0, AND the
   contamination gate holds.
4. ITERATED-GAIN: beats ONESHOT and FROZEN8B, slope lower bound <= 0.
5. RETRIEVAL: beats both, slope passes, contamination gate fails.
6. HEAD-START: beats FROZEN8B, not ONESHOT. One training on the same base samples buys the gain; iterating adds nothing (the fourth-law
   reading, rho_match 0.981).
7. NULL: none of the above. Published as NULL.
Descriptive tag, any label: RELABEL-CARRIES iff SELFFT beats CORRECTONLY at p < 0.05 (replicates CodeIt A2 / SOAR Table 2 direction).

## 7. Positive control, noise, lever markers, credit and format checks (RULES)

### 7a. Positive controls (any failure = VOID)

Rows: each of the 400 Hodel solvers (arc-dsl commit pinned in `data/MANIFEST.json`) is rendered as one self-contained
`def transform(grid)` with its dependency-closed dsl.py primitives and constants inlined and list/tuple grid conversion; each rendered
program must pass all demos and the test of its own growth task in Ratchet's sandbox, else it is dropped and counted (FT_PC_ROWS
built=.. passed=..). Prompt = the SELFFT render of that task. Each PC adapter is trained from base with the sec. 4d recipe, 2 epochs.

- PC-1 (binding, the requested control): train on the rendered rows of the 320 TRAIN tasks. Sample the 80 HELD tasks at S_g under the
  PC-1 adapter; compare per task (at least one demo-passing sample, yes/no) with the base HELD samples of SELFFT round 1 (same sampling
  seeds). PASS iff net gain >= +5 of 80 AND exact one-sided McNemar p < 0.05 AND the gain exceeds the base A/A difference of sec. 7b.
  Margin basis: +5 with 0 losses is the smallest count that can reach p < 0.05 (0.5^5 = 0.031).
- PC-0 (binding lever check, also diagnostic): train on the rendered rows of the 80 HELD tasks themselves; that adapter serves this one
  measurement and is then removed from the serving path (its sha is logged; any later FT_ADAPTER_LIVE with it = VOID). PASS iff HELD
  demo-pass rises by net >= +20 of 80. PC-0 fail: the update does not reach sampling. PC-0 pass with PC-1 fail: supervised cross-task
  transfer is absent at this scale; VOID, not NULL.

### 7b. Noise and power

- A/A (requested): SELFFT seed 1 vs SELFFT_S2 after round 1: HELD demo-pass task counts under the two A_1 adapters, and per-task
  discordance d_A. The base A/A is free: HELD round-1 samples of seed 1 and seed 2 both come from A_0.
- Power: after J2, the PREREG sec. 7.3 projection with the measured base discordance on HELD pass@2 (two base samplings at S_seal):
  projected power for Q = +8 of 400 at one-sided 0.05. Below 60% = UNDERPOWERED, written to RESULT.md before the key is opened. Stated
  now: HELD tasks are easier than sealed ones, so this discordance is a stand-in of unknown direction.

### 7c. Lever markers (rule 6; each a VOID condition if absent or wrong)

```
FT_UPDATE round=<r> arm=<SELFFT|SELFFT_S2|CORRECTONLY|ONESHOT|PC0|PC1|SELFFT_LIB> mode=<relabel|correct|plant> n_rows=<trained> n_new=<this round> n_relabelled=<rows whose task != original> clipped=<rows over max_len> n_rows_held=<..> n_rows_sealed=<..> train_tokens=<..> label_tokens=<..> steps=<..> train_s=<..> init=base loss_first=<..> loss_last=<..> prev_adapter_sha=<sha256[:16]> adapter_sha=<sha256[:16]>
FT_ADAPTER_LIVE adapter_sha=<..> arm=<..> phase=<growth|held|sealed|perturbed> round=<r> vllm_name=<..> probe_lp_base=<..> probe_lp_adapter=<..> probe_lp_hf=<..>
FT_FROZEN_LIVE adapter_sha=<zero-adapter sha> probe_lp_base=<..> probe_lp_adapter=<..>
FT_MATCH arm=<FROZEN8B|ONESHOT|LIBFROZEN8B> seed=<k> extra=<..> target_units=<..> realized_units=<..> target_h100_s=<..> realized_h100_s=<..>
FT_FORMAT arm=<..> round=<r> rows=<..> prompt_render_identical=<..> completion_is_own_response=<..> code_sha_roundtrip=<..> think_tokens=0
FT_ROWLEN arm=<..> round=<r> p50=<..> p99=<..> max=<..> over_max_len=<..> tokenizer_sha=<..>
FT_PC kind=<PC0|PC1> held=80 base_pass=<..> pc_pass=<..> wins=<..> losses=<..> p=<..>
```

Proofs: adapter_sha differs from prev_adapter_sha at every training; the next sampling job's FT_ADAPTER_LIVE prints exactly the newest
adapter_sha (it must change after each update); |probe_lp_adapter - probe_lp_base| > 1e-3 nats on a fixed probe completion AND
|probe_lp_adapter - probe_lp_hf| < 0.05 nats (vLLM serves the bytes the trainer wrote); FROZEN8B's sha is constant and its |adapter -
base| < 1e-3. For SELFFT, n_relabelled must be > 0 from round 1 (else the arm is CORRECT-ONLY in disguise); for CORRECTONLY it must be
0. Rule 2 read before any label: a SELFFT log whose sha never changes is FROZEN in disguise; a FROZEN8B log with a changing sha is not
FROZEN; a sealed SELFFT log naming any sha other than A_R is not A_R; each = VOID. No effect is read before `lever_check.py` prints
LEVER_OK for these regexes (SPEC sec. 9 procedure).

### 7d. Credit, clipping, format (the three our record got wrong)

- Credit: every kept row's label tokens = its completion tokens exactly, and the code block the sandbox ran lies inside the labelled
  span. Any failing row in J1 = fix before main; any in a main training = dropped and counted.
- Clipping: rows over max_len are dropped and counted; VOID if clipped / rows > 5% in any training (the record's threshold). Responses
  with finish_reason=length are failed samples and never rows. At consol.py's 3,072 cap 17.9% of growth tasks would have lost their
  completions (sec. 1), which is why the cap moves to 12,288 and slicing is removed.
- Format (from HS-AONLY's collapse): FT_FORMAT must show prompt_render_identical = completion_is_own_response = code_sha_roundtrip =
  rows and think_tokens = 0 in every training; any shortfall = that training VOID. In J1, FROZEN8B and A_1 must have the same share of
  responses with an extractable program within 2 points on 50 TRAIN tasks (a format-collapse alarm).

## 8. Seal and scoring path

- Sealed sampling may run once FREEZE_FT.json (adapter safetensors for every sealed arm and the zero adapter, and for library arms L_R,
  each with sha256 in a `{"path", "sha256"}` shape that `freeze_entries` already parses) and SUBMIT_FREEZE are committed and acked by
  the lead. The key is opened once, not before D_SEAL.
- Read the code of what "obviously" happens (rule 5): `score_sealed.py` cannot score this sub-study as it stands. (1) `_score_primary`
  takes its arms from `config.ARMS` and refuses with MISSING_SUBMISSION unless all 8 library arms are present; W is hard-coded as
  `S['STOCK'] - S[FLAT_ARM]`, and the reuse and knockout gates read the STOCK library. (2) The main run will already have a `primary`
  row in the key-root KEY_READS.jsonl, so this access needs `--amendment 1`, which passes only if PREREG `## AMENDMENTS` contains the
  text `AMENDMENT 1 `, and that id is then spent: one key access for this sub-study, sealed and perturbed together (both are in the
  `primary` globs). An ARC-AGI-2 secondary for the 8B would need another amendment id; it is not planned.
- Required before J1 (builders, after the lead appends this amendment; not done in this draft): a run profile `runs/ft8b` with ARMS =
  (SELFFT, CORRECTONLY, ONESHOT, FROZEN8B[, SELFFT_LIB, LIBFROZEN8B]), FLAT_ARM = FROZEN8B, PERTURBED_ARMS = (SELFFT, ONESHOT), the role
  `STOCK` in `_score_primary` mapped to SELFFT, library gates skipped for adapter arms; a test that the profile scores a stub run end to
  end with one amendment access; the trainer copy of sec. 4d; both row modes of sec. 4b (the coordinator reports the builder is adding
  them to the runner); the HELD split file; the Hodel renderer of sec. 7a.

## 9. Physics floor of the effect (rule 1)

CORRECT-ONLY rows are set by what the 8B already solves: at most 16 per demo-passed TRAIN task, ESTIMATE under 200 new rows per round,
inside the regime where our record measured mostly noise (864-row GRPO update 27% signal; self-generated rows add about 0 new
capability, CONT minus ORIG +0.014). RELABEL lifts the row count about 8x (every executable program, ESTIMATE about 1,536 per round)
without new samples, which is the mechanism SOAR and CodeIt credit; it does not lift the search budget, which is the binding gap:
SOAR searched 6k candidates per task per iteration, this plan 8 (750x less; 190x at S_g 32).

## 10. Compute plan (RULE: hard cap 38 h100-debug jobs of 1 h, 1 H100 each)

Per-job ESTIMATES (J1 replaces them): vLLM 8B start 150 s, 300 s stop margin, about 3,000 s of work per job; decode about 3,000
generated tok/s (the TTRL amendment's 2,000 to 6,000 range; bandwidth ceiling at util 0.45 about 11,000 tok/s); 8B training 4.9e10
FLOP per token at 30% of 989 TFLOP/s = 6,060 trained tok/s. One SELFFT round r: 3,200 samples x 600 = 1.92M gen tokens = 640 s;
sandbox about 30 s on 24 cores; training (pooled rows x 2,000) / 6,060 = 507 s at r = 1 rising to 1,690 s from r = 4; adapter save,
hot-load, probe about 20 s.

J1 rule for S_g: choose the largest S_g in {8, 16, 32} whose projected job count at the measured rates fits the cap; else S_g = 8.

| job | order | content |
|---|---|---|
| J1 | first free slot after the Ratchet main pilot | full-path smoke on 50 TRAIN tasks: 2 SELFFT rounds in both row modes, ONESHOT path, zero adapter, from-base retrain, adapter save, hot-load, probe, resume in a fresh process; measures decode tok/s, trained tok/s (rho_s), co-resident peak memory with r256, FT_ROWLEN with the real tokenizer, FT_CREDIT, FT_FORMAT, executable-program share; Hodel renderer pass count |
| J2 | after J1 passes | PC-0 and PC-1 (2 trainings, 3 HELD passes of 640 samples incl. base); SELFFT_S2 round 1 + its HELD pass; power projection |
| J3 to J7 | after J2 passes | SELFFT rounds 1 to 6 (about 3,840 s sampling + 8,100 s training), resumable at any round boundary |
| J8, J9 | after J3 | CORRECTONLY rounds 1 to 6 (3,840 s sampling, small trainings) |
| J10 to J13 | after J7 | ONESHOT: 16,000 more base samples (3,200 s), RELABEL union, one from-base training at about 49M tokens (about 8,100 s) |
| J14 | reserve | one rerun of any growth job that died or failed a check |
| L1 to L4 | if slots remain, after Ratchet's L_R is frozen | SELFFT_LIB (2 jobs), LIB sealed for both library arms (2 jobs) |
| S1 to S19 | after FREEZE_FT is acked | sealed sampling: SELFFT, CORRECTONLY, ONESHOT 3 seeds (5,760 s); perturbed SELFFT and ONESHOT (3,840 s); FROZEN8B 3 seeds at about 242 per task (290,400 samples, about 58,000 s): about 67,600 s of decode |
| S20 | reserve | one sealed rerun |

Calendar: growth jobs J1 to J14 start no later than D_GROWTH; the SELFFT rounds that exist when D_GROWTH passes are the run (fewer than
4 = UNDERPOWERED). The key is opened once, not before D_SEAL; sealed sampling may continue past D_SEAL. The h100-debug slot is one job
per user for every lane: Ratchet main (12 H100-hours) has priority, then this sub-study; it never cancels another lane's job.

Cut order when slots run short (first cut first): (1) L1 to L4 (library arms); (2) J14 and S20 reserves; (3) S_g back to 8 if J1 raised
it; (4) R from 6 to R_min 4 (ONESHOT and FROZEN8B budgets follow, since they are matched from the ledger); (5) CORRECTONLY (the
relabelling ablation, not in the gate). Never cut: J1, J2 (both positive controls and the A/A), SELFFT to R_min, ONESHOT, FROZEN8B at
its full matched budget, the perturbed copy, the 3 sealed seeds.

Cross-lane finding (rule 3): AMENDMENT_TTRL_V1 sec. 3 and 6 lay out 4 arms on 4 H100s inside one h100-debug job; this QOS refuses any
job with more than 1 GPU (QOSMaxGRESPerNode for 2, 3 and 4, test-only on 2026-11-04 at 19:5x ET). Its own fallback (1) applies at once:
arms rotate one per job, its job count quadruples, its cuts trigger. Both amendments and Ratchet main draw on the same single slot.

## 11. Byte, token and second map (rule 7, ESTIMATES until J1)

| item | bytes / tokens / seconds | basis |
|---|---|---|
| 8B weights, vLLM + trainer co-resident | 2 x 16.38 GB | config, du |
| r256 LoRA on 7 projections x 36 layers | about 0.70B parameters: 1.4 GB bf16 + 5.6 GB fp32 Adam states | arithmetic: per layer 256 x (2 x 8,192 + 2 x 5,120 + 3 x 16,384) |
| 8B KV per token | 36 x 8 x 128 x 2 x 2 B = 147,456 B | config.json |
| KV pool at util 0.45 | about 36 GB - 16.4 - 2 = 17.6 GB = about 119k tokens | arithmetic |
| prompt per sample | mean 1,000 + 400 = 1,400 logical tokens (p90 2,441, max 6,910) | node measure, sec. 1 |
| RELABEL rows | about 1,536 new per round; pool capped at 5,120 (16 x 320) | ESTIMATE, sec. 5 |
| SELFFT growth | 19,200 samples, 11.5M gen tokens (3,840 s) + 49.2M trained tokens (8,100 s) | sec. 5, 10 |
| ONESHOT | 16,000 extra samples (3,200 s) + 49M trained tokens (8,100 s) | sec. 10 |
| sealed | about 67,600 s decode, 86% of it FROZEN8B | sec. 10 |
| total | 14 growth + 20 sealed = 34 jobs (+4 optional) | sec. 10 |

## 12. Weakest points of this design

1. Search budget and power. SOAR's gains came at 6k candidates per task per iteration; this plan affords 8 to 32 (190x to 750x less),
   and the coordinator's research notes Barbadillo's gain shrinking below 512. An 8B's sealed solves are likely small (no measurement:
   the base 8B has never been sampled on these prompts), exact McNemar needs at least 5 net discordant tasks, and FROZEN8B at about
   242 samples per task is a strong comparator. UNDERPOWERED or HEAD-START are the likely reads.
2. The model is not Ratchet's. The 8B answers a narrower question than the founder asked, and the library arms import a 35B-grown L_R
   into an 8B, so weights vs library is compared on a library the 8B did not grow.
3. Build and queue risk. The trainer copy with from-base restart, both row modes, the Hodel renderer, the `runs/ft8b` scoring profile
   and the one-shot amendment access do not exist yet; 34 jobs share one h100-debug slot with Ratchet main and the TTRL amendment.
   PC-1 adds a separate risk: if supervised cross-task transfer is absent at 320 rows, the run is VOID even with a working lever.

## 13. What a stranger reruns

Every adapter (safetensors + sha), every row file (prompt render sha, code sha, mode, round), the HELD split, the token and seconds
ledger, `score_sealed.py` under the `ft8b` profile, the perturbation seed. Rescoring one adapter on the 400 sealed tasks needs one GPU,
Qwen3-8B and the public ARC-AGI-1 data.

## 14. Registration line

```
Quantity:          In the Qwen3-8B sub-study of silicyte-0119, sealed ARC-AGI-1 solves (of 400; pass@2, solved in >= 2 of 3 seeds)
                   of SELFFT (SOAR-style hindsight relabelling, from-base retraining on pooled rows each round) after R = 6 rounds
                   minus SELFFT-ONESHOT (one training on the relabelled union of the same number of base samples) at matched
                   compute.
Point prediction:  +1 task. Expected label: UNDERPOWERED or NULL (HEAD-START next).
80% band:          [-5, +8] (ESTIMATE; to be replaced by the ledger's calibrated band at registration, as AMENDMENT 0 did).
Gate:              COMPOUNDS-WEIGHTS iff SELFFT beats ONESHOT and FROZEN8B by exact one-sided McNemar p < 0.05 each, AND the HELD
                   (80 growth tasks never trained on) demo-pass slope over rounds 0..R has a 95% task-bootstrap lower bound > 0,
                   AND on the perturbed sealed copy SELFFT keeps at least half its net gain over ONESHOT, with PC-0, PC-1, every
                   lever proof and every credit, clipping and format check passed.
Threshold basis:   alpha 0.05 one-sided per comparison under intersection-union (both must pass, no correction); noise floor = the
                   SELFFT seed-1 vs seed-2 round-1 A/A on HELD plus the 2-of-3-seed rule; UNDERPOWERED if projected power for +8 of
                   400 at the measured HELD discordance is below 60% (PREREG 7.3 rule); +5 net with 0 losses is the smallest count
                   exact McNemar can pass (0.5^5 = 0.031), which also sets the PC-1 margin; prior measurement: SOAR 7B 14.25% to
                   36.25% at 6k candidates per task per iteration, CodeIt relabelling 59 vs 42 of 400.
Kill clause:       VOID if PC-0 (+20 of 80 on trained HELD tasks) or PC-1 (+5 of 80 on HELD after training on 320 TRAIN Hodel
                   programs, p < 0.05) fails, if any FT_UPDATE or FT_ADAPTER_LIVE line is missing or adapter_sha does not change
                   after a training, if SELFFT shows n_relabelled = 0, if clipped rows exceed 5% of any training, if FT_FORMAT
                   falls short of all rows, or if any HELD or sealed task enters a training row. Two VOIDs retire the harness.
                   Stop at 38 h100-debug jobs or at D_GROWTH for growth; one key access under --amendment 1, not before D_SEAL.
                   NULL is published as NULL.
Pass probability:  0.07 (ESTIMATE). Against: 0 PASS among the 15 weight-update rows of RESULT_PORL_CRL_AUDIT_1031 sec. 2, including
                   two hindsight-flavoured arms (HS-AONLY 12/158 vs 93/158, a format collapse; LRFT3 -0.038); fourth-law rho_match
                   0.981 (weights give head starts, not rates) and CONT = ORIG; a search budget 190x to 750x below SOAR's; a
                   matched frozen control with about 242 samples per task. For: SOAR is the direct precedent in this exact setting
                   (Python programs, ARC-AGI-1, a 7B improving over iterations), relabelling is the ablated load-bearing part
                   (CodeIt 59 vs 42), rows here are exact inference format with an exact executor, unlike every Flash-Next arm.
```
