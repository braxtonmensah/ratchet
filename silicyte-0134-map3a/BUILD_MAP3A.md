# BUILD MAP3A (silicyte-0134): additive neuron edits, act += c*sigma. STATE for a cold verifier

Builder 2, 2026-11-05 19:3x ET. Nothing was submitted, cancelled, held or released; no srun into any holder; no fourth_law file
written (fourth_law is read and imported only). Quartz dir: /N/scratch/bsmensah/silo/map3a0134/. Laptop mirror:
C:/Users/bmens/NQ_local/silicyte-funding/rsi_sprint/restart/map3a0134/. Pre-fix copies: scratchpad map3a_bd966c7e.py (old map3a.py).

## Files (sha256; laptop == Quartz, checked with sha256sum on both)
| file | sha256 | what |
|---|---|---|
| map3a.py | 39f40041b62148c54d750ad37be83761d7f301c97fffca692b6c7e741d89028d | modes: sets / smoke / power / run / read |
| map3a.sh | 5effd02a4e7cf7d02c692d5ca4598743a9a154ba2ad7a2b2c365dfa852d083de | GPU step: tiny GPU smoke, full run, read (all capped, see Packing) |
| PREREG_MAP3A_DRAFT.md | 362e074125873cf6598a45e94f2e633bb95ee23bc6a147900ea50362ad978f11 | rules fixed before data |
| out_map3a/sets.json (Quartz only) | 0546eb88e7263f2be682c9c7af93f6a4bba55e568e3a0652783ad5354175ecc4 | verified sets, verified_against_map2 true |

Outputs on Quartz: power.out (sha 24047d02 run), sets.out (sha 2869824 run; sets code byte-identical in 39f40041), smoke_cpu.out
(sha 39f40041 run). Earlier failed outputs kept: sets_1804_run.out, power_tbug.out.

## 1. The 19:02 blocker: NEG and ORDER mismatch. Cause and fix
- Cause: map2.py:135-136 ranks the fp32 T; map2.py:150 saves `T.half()` into map_full.pt. The fp32 T is on no disk (map2.py ==
  map2_12695509.py, the run snapshot, sha bd8e06dc). fp16 spacing at |t| 4-8 is 0.0039, so exact ties are common.
- NEG: 254 neurons lie strictly below T16 -4.37891, and 3 sit exactly on it for 2 slots. MAP2 (fp32) took L15.N4885; a plain fp16
  argsort took L26.N1570. That was the only membership difference.
- ORDER: 47 of the 200 map.json positions differed, all inside exact fp16 tie groups (0 with unequal T16).
- Fix (reproduce_sets): rank by T16; inside an exact T16 tie, use MAP2's own record: map.json position first, then adapter_<G>_x0.0
  members before non-members, then (layer, lora_A row). lora_A rows list each layer's neurons in MAP2's fp32 order (map2.py:172 sorts
  by -|s-1|, equal across a group; Python's sort is stable).
- The check is not weakened: strict equality with all three adapters and with the ordered map.json list stays. Two strict checks were
  added: TIES_ONLY (the T16 value sequence of the 256 equals the plain fp16 argsort's, so the rule decides only among exactly equal
  values) and "adapter rows monotone in T16 within every layer".
- Plain statement: membership of 1 NEG neuron (2 of 3 tied at T16 -4.37891) cannot be derived from map_full.pt alone; it comes from
  MAP2's NEG adapter, which is what MAP2 applied.

sets.out (19:19-19:31, h1):
```
TIES_ONLY POS ... True | members changed by the tie rule [] | order positions changed 99 | adapter rows monotone ...: True | max |map.json t - T16| 0.0059
TIES_ONLY NEG ... True | members changed ['L15.N4885 T16 -4.37891', 'L26.N1570 T16 -4.37891'] | order positions changed 110 | monotone True | 0.0055
SET POS == MAP2 adapter_POS_x0.0 (256 neurons): True
SET NEG == MAP2 adapter_NEG_x0.0 (256 neurons): True
SET RAND == MAP2 adapter_RAND_x0.0 (256 neurons): True
ORDER top-100 POS + top-100 NEG == MAP2 map.json top_neurons (ordered): True
SPLIT == MAP2 split.json: True | map 60 held 40
PROMPT tokens held: min 320 median 505 max 795 | map: total 34080 max 794
SETS_OK True
```
("order positions changed" counts all 256 positions vs the plain argsort, including the cascade after a swap; the 47 is over the
200 map.json positions.)

## 2. Why `sets` hung, and the fix (physics floor)
- The first sets process (pid 1515820, h1) sat in state D with fd 4 = .../site-packages/transformers/models and fd 5 walking model
  files. `from transformers import AutoTokenizer` in transformers 5.18.0 reads its ~2,713 .py files to build its import table.
- Measured on h1/h2 login nodes: stat of 521 files on slate 28.5 s (55 ms each); stat of 61 files on scratch 8.1 s; `du` of the
  transformers package did not finish in 9 min; `import torch` 203.6 s at 19:0x and 567.1 s at 19:2x (load average 18-24, 39 users).
- So on a login node a cold transformers import costs tens of minutes. It was filesystem latency, not a code deadlock. Fix:
  - `sets` no longer imports transformers: chat_tokenizer() renders tokenizer_config.json's chat_template with jinja2 3.1.6 (sandboxed,
    trim_blocks, lstrip_blocks, loopcontrols, as transformers does) and encodes with tokenizers 0.23.2; 17.9 s.
  - `power` no longer imports torch (need_torch() is lazy); it now finishes in 3 s.
  - Every phase prints its own duration with flush (IMPORT, LOADED, SPLIT, PROMPT), so a slow phase is visible.
  - smoke() checks the transformers-free tokenizer against AutoTokenizer + apply_chat_template on all 100 prompts (strings and ids).
- Second bug found on the way: `power` crashed at t = 0 inside lc_b18.t_upper (log(1 - x) with x = 1; no symmetry switch). map3a.py
  now has its own t_upper (incomplete beta with the symmetry switch). TCHECK: df 39 quantiles 1.684875 / 2.022691 / 2.425841 give
  0.050000 / 0.025000 / 0.010000, t 0 gives 0.5, and t 2.816 gives 0.00379 (lc_b18 0.00379, RESULT_MAP2 p 0.0038).
- Killed on h1 after the hostname and cmdline check (authorised by the lead): 1515797 (bash chain), then 1515820 (python sets).

## 3. CPU smoke (hook plumbing, tiny random Qwen3, plus tokenizer equality)
smoke_cpu.out (19:31-20:1x, h1, map3a.py sha 39f40041): **HOOK_SMOKE PASS**.
```
IMPORT torch 596.7s | IMPORT transformers 5.18.0 1524.2s
template_string_equal_of_100 100 | token_ids_equal_of_100 100   (transformers-free tokenizer == AutoTokenizer)
c0_identical_fp32 True | bf16_c0_logits_identical True | bf16_c0_generate_identical True
prehook_vs_constvec_maxdiff 2.1e-07 (act += c*sigma == constant vector) | edit_vs_base_maxdiff 0.582
hand_lastlayer_maxdiff 1.2e-07 (delta size 0.361) | hand_midlayer_residual_maxdiff 2.4e-07
c30_generate_tokens_changed 100 | hook_calls_c0_generate 60 == expected 60 | qwen3_8b_down_proj [4096, 12288], 36 layers, silu
```
RISK for GPU time: the 25-min transformers import was on a login node. If a compute node's slate is as slow, map3a.sh pays it twice
(GPU smoke, full run) while holding 38 GB of a card. The lead should read the IMPORT lines at the top of smoke_gpu.out.

## 4. Power and K (power.out, from MAP2 held.json, 11 arms, 55 arm pairs)
- Paired-diff sd at K=8: median 0.1019, max 0.1662. NEG_x0.0 - POS_x0.0: +0.0406, sd 0.0912, t 2.816, p 0.0038.
- Model sd is binomial, 0.1156 at K=8, between-concept part 0 (the observed sd is below binomial), so the table is conservative.
- 18 of 40 held concepts are 0/8 and 3 are 8/8 in every MAP2 arm.

| K | MDE alpha 0.05 | MDE alpha 0.0125 (Holm step 1) | power at 13/320, alpha 0.0125 |
|---|---|---|---|
| 8 | 4.64 pts (14.8/320) | 5.82 pts (18.6/320) | 0.46 |
| 16 | 3.28 (10.5) | 4.11 (13.2) | 0.79 |
| 24 | 2.68 (8.6) | 3.36 (10.7) | 0.93 |
| 32 | 2.32 (7.4) | 2.91 (9.3) | 0.98 |

**K = 24**: the smallest K with Holm MDE <= 13/320 = 4.06 points (the PREREG rule). Written into the PREREG and the code default.

## 5. Packing, memory and GPU-hours
- Rows per generate call = (BS // K) * K. **MAP3A_BS = 48** (2 prompts x 24), 20 generate calls per arm. The code default is
  still BS 80 (72 rows at K 24, about 44 GB); the launch line sets MAP3A_BS=48 and MAP3A_CAP_GB=38 explicitly. The code was left
  unchanged so the smoke ran on the final sha.
- Memory model from sets.out (prompt max 795 + 1500 new, 147,456 B KV per token): rows 24: 27.5 GB; rows 48: 35.6 GB; rows 72 would
  be about 44 GB. At BS 48 the default cap is ceil(35.6 + 2.0) = **38 GB**.
- gpu_setup() in map3a.py, run by both the GPU smoke and the full run: torch.cuda.init(), then
  torch.cuda.set_per_process_memory_fraction(38e9 / total) at once (0.48 of an 80 GB H100); REFUSE (exit 4) if card free < cap + 1 GB;
  REFUSE if any process on the card is bootseed0128.py (the uncapped 0128 trainer, grows to 71 GB) or has an unreadable cmdline.
  max_memory_allocated and max_memory_reserved are logged after load, after sigma/KL and after every arm (held.json "mem").
- Arms: BASE, PC, 12 edit arms = 14 x 960 = 13,440 samples, plus the c=0 identity check (2 prompts x 24 twice) and the GPU smoke.
- Time (ESTIMATE, not measured): HF decode at 48 rows on an H100 is about 25-35 ms per step (the floor is 16.4 GB of weights + up to
  13 GB of KV per step / 3.35 TB/s = about 9 ms; HF's per-layer Python overhead dominates). A call lasts until its longest row stops,
  at most 1500 steps = 38-53 s. 20 calls x 14 arms = 280 calls = 3.0-4.1 h at worst-case length; scoring runs on 7 CPU cores. Alone
  about 3-4 h; beside another job assume x1.3-1.5, so **about 4-6 GPU-hours of one shared H100 (0.48 of its memory)**. The first
  BASE arm's tok/s and steps in held.json replace this estimate. The import of torch + transformers on a compute node is not
  measured here (MAP2's whole job, including vLLM, took 27:20, so it was not tens of minutes there).
- Resumable: sets.json, sigma.pt, kl.json, checks.json, held.json persist; a restart skips finished arms and refuses a different K.
  MAP3A_DEADLINE (epoch s) stops cleanly between arms.

## 6. Launch (for the lead, after a verifier GO; not run by any builder)
Check the card first; it must show no bootseed0128.py process and at least 39 GB free (the script refuses otherwise):
```
srun --jobid=<holder> --overlap -n1 -c 8 --cpu-bind=none nvidia-smi --query-compute-apps=pid,used_memory --format=csv < /dev/null
cd /N/scratch/bsmensah/silo/map3a0134
nohup srun --jobid=<holder> --overlap -n1 -c 8 --cpu-bind=none env MAP3A_K=24 MAP3A_BS=48 MAP3A_CAP_GB=38 LC_NCORES=7 \
  bash /N/scratch/bsmensah/silo/map3a0134/map3a.sh > /N/scratch/bsmensah/silo/map3a0134/map3a_run.log 2>&1 < /dev/null &
```
Lever lines to check in map3a_run.log / smoke_gpu.out: MEM_CAP, NEIGHBOURS, CHECK hook at c=0 ... True, KL RAND+..., VEC ...,
HELD <arm> ... differ from BASE (must be > 0 for every edited arm), MEM <arm>.

## Remaining checklist
- [x] sets: SETS_OK True, POS/NEG/RAND True, ORDER True.
- [x] power: K = 24 written into the PREREG.
- [x] CPU smoke HOOK_SMOKE PASS.
- [ ] Verifier reads this file, the PREREG and map3a.py cold; GO or NO-GO.
- [ ] Lead launches (section 6). GPU smoke must print GPU_SMOKE_PASS first; then read the first BASE arm's tok/s.
