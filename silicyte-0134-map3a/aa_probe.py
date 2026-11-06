#!/usr/bin/env python3
"""aa_probe.py: silicyte-0134 MAP3A V0 diagnosis (2026-11-05 21:3x ET). The real-model V0 check (checks.json zero_identical False)
asked whether a c = 0 Steer hook changes sampled tokens. That check presumes bitwise-deterministic GPU sampling across generate calls,
which was verified only on CPU. This probe separates the two causes, with the registered rule in AMENDMENT_V0_1105.md:
  1. logits on one forward pass: none vs c=0 hook (bitwise), and none vs none;
  2. greedy decode, 64 tokens: none vs c=0, none vs none;
  3. sampled with MAP3A's sampler and seed: A vs A' (no hook twice), A vs Z (c=0 hook), rows differing and first divergence index.
Reads only (sets.json, sigma.pt, the model); writes aa_probe.json beside this file. No solve data is touched or produced."""
import json, os, sys, time
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
OUT = os.environ.get("AA_OUT", os.path.join(D, "aa_probe.json"))
MODEL = "/N/scratch/bsmensah/arc26/fourth_law/models/Qwen3-8B"
K, MNT, NP = 24, int(os.environ.get("AA_MNT", "400")), 2
import torch
torch.cuda.set_per_process_memory_fraction(float(os.environ.get("AA_FRAC", "0.40")), 0)
from transformers import AutoTokenizer, AutoModelForCausalLM, GenerationConfig
import map3a as M
M.need_torch()
t0 = time.time()
S = json.load(open(os.path.join(D, "out_map3a", "sets.json"))); SP = {g: [tuple(z) for z in S[g]] for g in M.GROUPS}
sigma = torch.load(os.path.join(D, "out_map3a", "sigma.pt"))["sigma"]
tok = AutoTokenizer.from_pretrained(MODEL); tok.padding_side = "left"
stop = sorted({i for i in (tok.convert_tokens_to_ids("<|im_end|>"), tok.eos_token_id, tok.pad_token_id) if isinstance(i, int)})
pad = tok.pad_token_id if tok.pad_token_id is not None else stop[0]
enc = lambda p: tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
try:
    LF, ITEMS, MAPC, HELD = M.world(); texts = [enc(M.prompt(LF, ITEMS, nm)) for nm in HELD[:NP]]; src = "held[:%d]" % NP
except Exception as ex:
    texts = [enc("Write a Python function that returns the n-th prime, then explain it."),
             enc("Explain, step by step, how to turn a 3x3 grid into its transpose, with an example.")]; src = "fallback %r" % (ex,)
print("PROMPTS %s" % src, flush=True)
hf = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa"); hf.eval()
print("LOAD %.1fs" % (time.time() - t0), flush=True)
st = M.Steer(hf); R = {"src": src, "K": K, "MNT": MNT, "torch": torch.__version__, "device": torch.cuda.get_device_name(0)}
gc = GenerationConfig(do_sample=True, temperature=1.0, top_p=0.95, top_k=20, max_new_tokens=MNT, num_return_sequences=K,
                      eos_token_id=stop, pad_token_id=pad, repetition_penalty=1.0)
e = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")


def gen(seed, cfg=gc):
    torch.manual_seed(seed)
    with torch.no_grad():
        o = hf.generate(**e, generation_config=cfg)
    return o[:, e.input_ids.shape[1]:].tolist()


def cmp(a, b):
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    first = [next((j for j in range(min(len(a[i]), len(b[i]))) if a[i][j] != b[i][j]), min(len(a[i]), len(b[i]))) for i in diff]
    return {"rows": len(a), "rows_differ": len(diff), "first_divergence": first[:48]}


V0 = st.vectors(SP["POS"], sigma, 0.0)
R["c0_vec_max_abs"] = max(float(v.abs().max()) for v in V0.values()); R["c0_vec_finite"] = all(bool(torch.isfinite(v).all()) for v in V0.values())
R["sigma_finite"] = bool(torch.isfinite(sigma).all())
# 1. logits, one forward pass, bitwise
with torch.no_grad():
    la = hf(**e, use_cache=False, logits_to_keep=8).logits
    st.on(V0); lz = hf(**e, use_cache=False, logits_to_keep=8).logits; st.off()
    la2 = hf(**e, use_cache=False, logits_to_keep=8).logits
R["logits_c0_vs_none_identical"] = bool(torch.equal(la, lz)); R["logits_c0_vs_none_maxdiff"] = float((la.float() - lz.float()).abs().max())
R["logits_none_vs_none_identical"] = bool(torch.equal(la, la2)); R["logits_none_vs_none_maxdiff"] = float((la.float() - la2.float()).abs().max())
print("LOGITS c0_vs_none identical %s maxdiff %.3g | none_vs_none identical %s maxdiff %.3g" % (
    R["logits_c0_vs_none_identical"], R["logits_c0_vs_none_maxdiff"], R["logits_none_vs_none_identical"], R["logits_none_vs_none_maxdiff"]), flush=True)
# 2. greedy, 64 tokens
gg = GenerationConfig(do_sample=False, max_new_tokens=64, num_return_sequences=1, eos_token_id=stop, pad_token_id=pad)
ga = gen(1, gg); st.on(V0); gz = gen(1, gg); st.off(); ga2 = gen(1, gg)
R["greedy_c0_vs_none"] = cmp(ga, gz); R["greedy_none_vs_none"] = cmp(ga, ga2)
print("GREEDY c0_vs_none %s | none_vs_none %s" % (R["greedy_c0_vs_none"], R["greedy_none_vs_none"]), flush=True)
# 3. sampled, MAP3A's sampler and seed: A, A' (no hook), Z (c=0 hook)
t1 = time.time(); A = gen(M.SEED_HELD * 1000); R["gen_s"] = round(time.time() - t1, 1)
A2 = gen(M.SEED_HELD * 1000); st.on(V0); Z = gen(M.SEED_HELD * 1000); st.off(); R["hook_calls_Z"] = st.calls
R["sampled_none_vs_none"] = cmp(A, A2); R["sampled_c0_vs_none"] = cmp(A, Z); R["sampled_none2_vs_c0"] = cmp(A2, Z)
R["mean_len"] = round(sum(len(x) for x in A) / len(A), 1)
print("SAMPLED none_vs_none rows_differ %d/%d | c0_vs_none %d/%d | none2_vs_c0 %d/%d | first divergence A/A' %s" % (
    R["sampled_none_vs_none"]["rows_differ"], len(A), R["sampled_c0_vs_none"]["rows_differ"], len(A), R["sampled_none2_vs_c0"]["rows_differ"], len(A),
    R["sampled_none_vs_none"]["first_divergence"][:12]), flush=True)
# the registered rule (AMENDMENT_V0_1105.md)
aa, az = R["sampled_none_vs_none"]["rows_differ"], R["sampled_c0_vs_none"]["rows_differ"]
if R["logits_c0_vs_none_identical"] and R["greedy_c0_vs_none"]["rows_differ"] == 0 and abs(aa - az) <= 4:
    R["V0"] = "PASS_LOGITS_GREEDY; sampler nondeterministic across calls; noise floor rows_differ %d/%d" % (aa, len(A))
elif (not R["logits_c0_vs_none_identical"]) or R["greedy_c0_vs_none"]["rows_differ"] > 0 or (aa == 0 and az > 0):
    R["V0"] = "FAIL; hook path changes the computation at c = 0; MAP3A arms VOID until fixed"
else:
    R["V0"] = "UNRESOLVED"
R["peak_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2); R["s"] = round(time.time() - t0)
json.dump(R, open(OUT, "w"), indent=1)
print("AA_PROBE_V0 %s" % R["V0"], flush=True)
print("AA_PROBE_JSON %s" % json.dumps(R), flush=True)
