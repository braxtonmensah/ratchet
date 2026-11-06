# PREREG MAP3A (DRAFT): additive edits on Qwen3-8B's map neurons (silicyte-0134)

Drafted 2026-11-05 18:0x ET, before any MAP3A data. Updated 19:3x ET (tie rule for the sets, K = 24, BS 48, memory cap), still before
any MAP3A GPU data. Code: map3a.py / map3a.sh (sha256 in BUILD_MAP3A.md). The rule below is fixed before any GPU run. Changing it
after data makes the read post hoc. It stays DRAFT until a verifier GO.

## Why
MAP2 (fourth_law phi1, RESULT_MAP2.md) tested only MULTIPLICATIVE scaling. It applied an exact LoRA on down_proj with
B[:, q] = W[:, ni] * (s - 1) at s = 0, 0.5, 2 and 3. Every arm landed at 75-88 of 320. A scale is zero wherever the neuron is quiet, so
that null may come from the shape of the dose. The user's objection: "add 1, subtract 1, stop multiplying". MAP3A tests the
additive edit act_ni += c * sigma_ni.

**An additive offset on map neurons is a steering vector.** At layer L it equals adding the constant
v_L = c * sum_{i in S_L} sigma_i * W_L[:, i] to the residual stream, at every position and whatever the input.

## Fixed inputs (identical to MAP2)
- Neuron sets:
  - POS: the 256 highest t;
  - NEG: the 256 lowest t;
  - RAND: 256 random neurons, from Random(77).
  These come from fourth_law out_map2/map_full.pt. They are checked equal to the neurons in MAP2's own adapter_POS_x0.0, adapter_NEG_x0.0 and adapter_RAND_x0.0, and the run refuses if they differ.
  map_full.pt holds T in fp16 (map2.py:150 saves T.half()), while MAP2 ranked the fp32 T. Inside a group of exactly equal fp16 values
  the order and membership therefore come from MAP2's own record: map.json top_neurons order first, then adapter membership, then
  the adapter's per-layer row order. This decides exactly one NEG neuron (L15.N4885 in, L26.N1570 out; both sit at fp16 -4.37891
  with a third neuron, for 2 slots) and 47 order positions, all inside exact fp16 ties. `sets` proves the rule touches only exact ties
  (TIES_ONLY) and then checks equality with all three adapters and with the ordered map.json list.
- Split, prompts and scorer: the same 40 held-out concepts as out_map2/split.json, with the PROCX3 prompt, chat template and no thinking. Scoring uses LF.code_of / run_cand / judge, and a solve is exact on all 22 hidden pairs.
- Sampling: T 1.0, top_p 0.95, top_k 20, 1500 new tokens, K = 24 samples per concept (see Power and K). The generator is HF transformers, MAP3A_BS 48 (2 prompts x 24 samples per generate call), and every arm uses the same seed for each chunk (23*1000 + first prompt index), which gives common random numbers across arms.
- sigma_ni: the sd of the down_proj input over every prompt token of the 60 map concepts, from one forward pass with no sampling. It is stored in sigma.pt.

## Arms (held-out, 40 concepts x K)
| arm | what it is |
|---|---|
| BASE | no edit |
| PC | positive control: RAND at +c_pc sigma |
| POS+c, POS-c, NEG+c, NEG-c, RAND+c, RAND-c | c = 1, then c = 3 |

c_pc is the smallest c in {10, 30, 100, 300} for which RAND+c reaches a mean next-token KL from BASE of at least 0.5 nat. The KL is measured on the last 64 prompt positions of 20 map prompts, so no solve data is used. The KL of every arm is logged as a dose-strength diagnostic.

## Validity gates (a FAIL on any gate means no edit read is interpreted)
- **V0, plumbing:** on the real model, the hook installed at c = 0 gives tokens identical to having no hook. Every edited arm also reports what fraction of its samples differ from BASE.
- **V1, comparability:** HF BASE vs MAP2's vLLM BASE (82/320), paired over concepts and two-sided. It passes if p > 0.05.
- **V2, positive control:** BASE > PC, one-sided paired p < 0.05. This shows the hook path changes behaviour.

## Registered reads
All tests are one-sided paired t-tests on per-concept solve fractions over the 40 concepts, Holm-corrected within each family.

**PRIMARY:** POS vs NEG at a matched dose. This is the additive version of MAP2's post hoc lead, NEG x0 88 vs POS x0 75, a gap of 13/320 (p 0.0038). The family has 4 tests:
- POS+c > NEG+c, at c = 1 and 3;
- NEG-c > POS-c, at c = 1 and 3.

**SECONDARY:** each map set vs RAND at a matched dose. The family has 8 tests:
- helpful directions: POS+c > RAND+c and NEG-c > RAND-c;
- harmful directions: RAND-c > POS-c and RAND+c > NEG+c.

## Power and K (fixed 2026-11-05 19:2x ET, before any MAP3A GPU data)
The minimum detectable effect is computed by map3a.py power from MAP2's per-concept counts (power.out, numbers in BUILD_MAP3A.md). K is
the smallest of 8, 16, 24 and 32 for which the Holm first-step MDE (alpha 0.0125, one-sided, power 0.8) is at most 13/320 = 4.06 points.

| K | MDE at alpha 0.0125 | power at 13/320 (alpha 0.0125) |
|---|---|---|
| 8 | 5.82 points (18.6 of 320) | 0.46 |
| 16 | 4.11 points (13.2 of 320) | 0.79 |
| 24 | 3.36 points (10.7 of 320) | 0.93 |
| 32 | 2.91 points (9.3 of 320) | 0.98 |

**K = 24** (960 samples per arm). The sd model is binomial, sd 0.1156 at K = 8, which is above the observed median over MAP2's 55
arm pairs (0.1019), so it is conservative; CRN sampling makes the realized MDE smaller still. 18 of the 40 held-out concepts are 0/8
and 3 are 8/8 in every MAP2 arm, so most of the signal must come from about 19 movable concepts.

## Verdicts
- **ADDITIVE CAUSAL PASS:** at least one PRIMARY test passes after Holm, with V0, V1 and V2 all passing.
- **ADDITIVE NULL:** V0, V1 and V2 pass and every PRIMARY and SECONDARY test fails. The steering vectors built from the map do not move held-out solves beyond the MDE, and MAP2's null is then not a dose-shape artifact at these doses.
- **INSTRUMENT FAIL:** V2 fails. The read is "the hook path or the dose is too weak", not "the neurons do not matter".

## Predictions (before data)
- V2 PC PASS: 0.85.
- At least one PRIMARY test passes: 0.30.
- POS+3 < BASE (any large push hurts): 0.5.

## REGISTRATION

Registered 2026-11-05 20:25 ET (Quartz clock) by the Silicyte lead. Text above is PREREG_MAP3A_DRAFT.md byte for byte (sha256 362e074125873cf6598a45e94f2e633bb95ee23bc6a147900ea50362ad978f11). Verifier: VERDICT_MAP3A.md (GO, sha b8492621), including its registered addition: the read reports per-concept floor (0 of K) and ceiling (K of K) counts at BASE and per arm. Code: map3a.py 39f40041, map3a.sh 5effd02a; launch K 24, BS 48, cap 38 GB. No held.json existed at registration. (An earlier registration line at 20:24 ET printed a literal date format instead of the time; it was replaced before any data.)
