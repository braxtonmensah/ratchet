#!/usr/bin/env python3
"""aa_probe2.py: second MAP3A V0 probe (silicyte-0134), registered in AMENDMENT_V0_1105.md part 2 before it runs.
Probe 1 (aa_probe.json) found: logits at c = 0 bitwise identical to no hook; greedy c0-vs-none identical while greedy none-vs-none
already differed (1 of 2 rows, token 17); sampled rows differing 19 (none/none), 13 (none/c0), 16 (none'/c0) of 48. Its PASS bar
(counts within 4) sat below the rerun spread (sd of a difference of two such counts about 4.7), so it returned UNRESOLVED.
Part 1, deterministic kernels (CUBLAS_WORKSPACE_CONFIG :4096:8, torch.use_deterministic_algorithms, SDPA math backend): none twice
and c = 0 once, 48 rows x 400 tokens, MAP3A's sampler and seed. Part 2, default kernels, powered: 4 none runs and 4 c = 0 runs at
96 rows (4 prompts x K 24); the bar is set from the 6 none/none pairs' own spread. Reads only; writes aa_probe2.json."""
import json, os, sys, time, itertools, statistics
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
OUT = os.environ.get("AA_OUT", os.path.join(D, "aa_probe2.json"))
MODEL = "/N/scratch/bsmensah/arc26/fourth_law/models/Qwen3-8B"
K, MNT = 24, int(os.environ.get("AA_MNT", "400"))
import torch
torch.cuda.set_per_process_memory_fraction(float(os.environ.get("AA_FRAC", "0.45")), 0)
from transformers import AutoTokenizer, AutoModelForCausalLM, GenerationConfig
import map3a as M
M.need_torch(); t0 = time.time()
S = json.load(open(os.path.join(D, "out_map3a", "sets.json"))); SP = {g: [tuple(z) for z in S[g]] for g in M.GROUPS}
sigma = torch.load(os.path.join(D, "out_map3a", "sigma.pt"))["sigma"]
tok = AutoTokenizer.from_pretrained(MODEL); tok.padding_side = "left"
stop = sorted({i for i in (tok.convert_tokens_to_ids("<|im_end|>"), tok.eos_token_id, tok.pad_token_id) if isinstance(i, int)})
pad = tok.pad_token_id if tok.pad_token_id is not None else stop[0]
enc = lambda p: tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True, enable_thinking=False)
LF, ITEMS, MAPC, HELD = M.world(); texts = [enc(M.prompt(LF, ITEMS, nm)) for nm in HELD[:4]]
hf = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa"); hf.eval()
print("LOAD %.1fs" % (time.time() - t0), flush=True)
st = M.Steer(hf); V0 = st.vectors(SP["POS"], sigma, 0.0)
R = {"K": K, "MNT": MNT, "torch": torch.__version__, "cublas_ws": os.environ.get("CUBLAS_WORKSPACE_CONFIG"), "c0_vec_max_abs": max(float(v.abs().max()) for v in V0.values())}
gc = GenerationConfig(do_sample=True, temperature=1.0, top_p=0.95, top_k=20, max_new_tokens=MNT, num_return_sequences=K,
                      eos_token_id=stop, pad_token_id=pad, repetition_penalty=1.0)
SEED = M.SEED_HELD * 1000


def build(tx):
    return tok(tx, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")


def gen(e, hook):
    if hook:
        st.on(V0)
    torch.manual_seed(SEED)
    with torch.no_grad():
        o = hf.generate(**e, generation_config=gc)
    st.off(); return o[:, e.input_ids.shape[1]:].tolist()


def nd(a, b):
    return sum(1 for i in range(len(a)) if a[i] != b[i])


# Part 1: deterministic kernels
torch.use_deterministic_algorithms(True, warn_only=True)
torch.backends.cuda.enable_flash_sdp(False); torch.backends.cuda.enable_mem_efficient_sdp(False); torch.backends.cuda.enable_math_sdp(True)
e2 = build(texts[:2]); t1 = time.time()
A = gen(e2, False); A2 = gen(e2, False); Z = gen(e2, True)
R["det"] = {"rows": len(A), "none_vs_none": nd(A, A2), "c0_vs_none": nd(A, Z), "none2_vs_c0": nd(A2, Z), "s": round(time.time() - t1)}
print("DET rows %d none_vs_none %d c0_vs_none %d none2_vs_c0 %d (%ds)" % (len(A), R["det"]["none_vs_none"], R["det"]["c0_vs_none"], R["det"]["none2_vs_c0"], R["det"]["s"]), flush=True)
# Part 2: default kernels, powered
torch.use_deterministic_algorithms(False)
torch.backends.cuda.enable_flash_sdp(True); torch.backends.cuda.enable_mem_efficient_sdp(True)
e4 = build(texts); t1 = time.time()
N = [gen(e4, False) for _ in range(4)]; Zs = [gen(e4, True) for _ in range(4)]
nn = [nd(N[i], N[j]) for i, j in itertools.combinations(range(4), 2)]
zz = [nd(Zs[i], Zs[j]) for i, j in itertools.combinations(range(4), 2)]
nz = [nd(N[i], Zs[j]) for i in range(4) for j in range(4)]
sd_nn = statistics.pstdev(nn); lo, hi = min(nn) - sd_nn, max(nn) + sd_nn
R["pow"] = {"rows": len(N[0]), "nn": nn, "zz": zz, "nz": nz, "nn_sd": round(sd_nn, 2), "band": [round(lo, 2), round(hi, 2)],
            "nz_mean": round(statistics.mean(nz), 2), "zz_mean": round(statistics.mean(zz), 2), "s": round(time.time() - t1)}
print("POW rows %d | none/none %s (sd %.2f, band %.1f..%.1f) | c0/c0 %s mean %.2f | none/c0 %s mean %.2f (%ds)" % (
    len(N[0]), nn, sd_nn, lo, hi, zz, R["pow"]["zz_mean"], nz, R["pow"]["nz_mean"], R["pow"]["s"]), flush=True)
# the registered rule (AMENDMENT_V0_1105.md part 2)
d = R["det"]; p = R["pow"]
if d["none_vs_none"] == 0 and d["c0_vs_none"] == 0:
    R["V0"] = "PASS_DETERMINISTIC: with deterministic kernels the c = 0 hook reproduces no-hook sampling bitwise"
elif d["none_vs_none"] == 0 and d["c0_vs_none"] > 0:
    R["V0"] = "FAIL: deterministic kernels make none/none identical but the c = 0 hook changes %d rows" % d["c0_vs_none"]
elif lo <= p["nz_mean"] <= hi and lo <= p["zz_mean"] <= hi:
    R["V0"] = "PASS_POWERED: none/c0 mean %.2f and c0/c0 mean %.2f lie inside the none/none rerun band %.1f..%.1f" % (p["nz_mean"], p["zz_mean"], lo, hi)
elif p["nz_mean"] > hi:
    R["V0"] = "FAIL: none/c0 mean %.2f exceeds the none/none rerun band (max + sd = %.1f)" % (p["nz_mean"], hi)
else:
    R["V0"] = "UNRESOLVED"
R["peak_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2); R["s"] = round(time.time() - t0)
json.dump(R, open(OUT, "w"), indent=1)
print("AA_PROBE2_V0 %s" % R["V0"], flush=True); print("AA_PROBE2_JSON %s" % json.dumps(R), flush=True)
