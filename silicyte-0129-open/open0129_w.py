#!/usr/bin/env python3
"""open0129.py (silicyte-0129 OPEN): the silicyte-0128 FRONTIER loop with its depth ceiling removed.

  python open0129.py <D0128> <FL> <OD> loop  <k> <t_to>          the loop for seed k, rounds 0..t_to (every round trains P_{t+1})
  python open0129.py <D0128> <FL> <OD> ruler <state_dir> <k> <t,t,...>   score final policies P_t on RULER_k (measurement only)
  env DRY=1 with loop: CPU smoke (md5s, rulers, the t = 0 data and frontier pools, exclusions); no torch, no model.

D0128 = /N/scratch/bsmensah/silo/bootseed (registered lib/, inputs/, code/bootseed0128.py: read only). FL = fourth_law (consol_v1
world and Qwen3-8B, read only). OD = /N/scratch/bsmensah/silo/open0129. State dir OD/runs/OPEN_s<k>.

IMPORTED VERBATIM from bootseed0128.py (md5 c54e21d253f53ee246352f74c83e085b, asserted; the function definitions are taken from the
file's syntax tree and executed in this module, so the bytes that run are the registered bytes): fmd5, jdump, wsum, proj, beam2,
solve2, frontier_examples, f3_window, free, train, done_rounds. Kept identical: world, model, Scorer, beam (B 4), the trainer
(reachlaw.train r16 lr 2e-4 one pass over seed256 + own_0..own_t), F1 (own examples at depth >= dmin = floor(d50)), A1 1:1 hindsight
(paths of length >= dmin), F3 window [max(1, floor(d50) - 1), ceil(d50) + 3], pool sizes (300 data, 200 frontier), the A1.1 seed knob
(k = 1: pools 9000 + t / 19000 + t, no pre-shuffle, no torch seed, hindsight Random(len(rows)); k >= 2: pools 9000 + 100 k + t /
19000 + 100 k + t, pre-shuffle and torch.manual_seed 1000 k + t + 1, hindsight Random(1000003 k + len(rows)); P_0 as 0128).

DIFFERENCES from bootseed0128.py (the complete list):
  O1 generator: data and frontier pools use opengen.make_task_open (same consol_v1 family and make_task filters, any depth) in
     bootllm.make_pool's loop (same rng, tid, depth draw, held skip).
  O2 data-pool depth window 1..D_t, D_0 = 10, D_t = max(10, ceil(d50eff_{t-1}) + 6) (0128: 1..10).
  O3 search max_steps = D_t + 2 for the data-pool solve and the frontier solve (0128: 10). No upper clip on the F3 window.
  O4 d50eff = the data-pool d50 clamped to [1, D_t + 2]; if the fit returns None it is D_t when >= half the pool is correct, else 1.0
     (0128 used d50 or 1.0, which would send a model that solves everything back to depth 1). d50eff feeds dmin, the window and D_{t+1}.
  O5 measurement: MEAS 29000 is not scored in-loop. The fixed ruler RULER_k (frozen/RULER_<49000 + 100 k>.json, sha256 asserted) is
     scored by a separate process on the same GPU for every final P_t (P_0 .. P_{t_to + 1}), per-task max_steps max(12, depth + 2),
     written to ruler_t.json. It never enters training; it runs while the loop searches and trains and cannot touch the loop's RNG.
  O6 exclusions at pool build: any task with an input of any RULER_k, MEAS 29000 or MEAS_DEEP_39x00 is skipped and counted
     (0128 dropped MEAS-input data rows after the solve; here none are built). Counted per round: dp_excl_hits, front_excl_hits.
  O7 no scored-only last round: every round 0..t_to trains P_{t+1}, so a later launch with a larger t_to just continues (0128's
     scored-only round 10 needed a 3-file move to extend). The last ruler is P_{t_to + 1}.
  O8 start check: exp_n256 on the first 60 tasks of pool 9000 at max_steps 10 must equal boot_llm2 round 0's first 60 eval rows
     row for row, else exit 7 (0128 re-scored all 300 plus MEAS, about 40 min); RNG-neutral (torch CPU and CUDA states restored).
  O9 P_0 for k >= 2 is copied from 0128's runs/FRONTIER_s<k>/P_0 when present (final in 0128: never retrained; md5 recorded), so
     round 0 starts from the same policy as 0128 seed k; otherwise trained by the 0128 recipe (train(seed256, 1000 k, k)).
  O10 telemetry by depth runs over 1..D_t (0128: 1..10). Arm label OPEN (printed by train). GUIDE is not run.
"""
import ast, gc, hashlib, json, math, os, random, shutil, subprocess, sys, time

D, FL, OD, MODE = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
DRY = os.environ.get("DRY") == "1"
LIB = os.path.join(D, "lib")
SRC0128 = os.path.join(D, "code", "bootseed0128.py")
MD5_0128 = "c54e21d253f53ee246352f74c83e085b"
LIB_MD5 = {"consol.py": "002ff8e65f7b2b5ef0021c654e5ff3dd", "reachlaw.py": "4187b71d89fc61cc0fab23ec34b2cfbe",
           "ident.py": "fbac440b535c03668f91900f5c1ab2b2", "bootllm.py": "e50ef05ec7a7eb6df7dfe1c7ab5d24c0"}
INP_MD5 = {"seed256.jsonl": "617d4cc6758fa93bd32dfc7b52f73850", "boot_llm2_round_0.json": "bcb164b7e5633591d35ad09feb3eb49c",
           "exp_n256/adapter_config.json": "3db28aefa04dbdd8102d937bc08afd0d",
           "exp_n256/adapter_model.safetensors": "141a87874ee48870281173c6dad505b0"}
RULER_SEEDS = {1: 49100, 2: 49200, 3: 49300, 4: 49400}
RULER_SHA = json.load(open(os.path.join(OD, "frozen", "RULER_SHA256.json")))     # written once by build_ruler; checked below


def _md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


for sub, table, tag in ((LIB, LIB_MD5, "VOID_LIB_MD5"), (os.path.join(D, "inputs"), INP_MD5, "VOID_INPUT_MD5"),
                        (os.path.join(D, "code"), {"bootseed0128.py": MD5_0128}, "VOID_0128_MD5")):
    for f, m in table.items():
        p = os.path.join(sub, f)
        got = _md5(p) if os.path.isfile(p) else "MISSING"
        if got != m:
            print(tag, p, got, "expected", m, flush=True); sys.exit(9)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LIB); sys.path.insert(1, HERE)
import consol as W
import reachlaw as RL
import bootllm as BL
import opengen as G

# ---- import the 0128 functions verbatim (bytes asserted above) ----
IMPORTED = ["fmd5", "jdump", "wsum", "proj", "beam2", "solve2", "frontier_examples", "f3_window", "free", "train", "done_rounds"]
_tree = ast.parse(open(SRC0128).read(), SRC0128)
_nodes = [n for n in _tree.body if isinstance(n, ast.FunctionDef) and n.name in IMPORTED]
assert sorted(n.name for n in _nodes) == sorted(IMPORTED), "0128 function set changed"
exec(compile(ast.Module(body=_nodes, type_ignores=[]), SRC0128, "exec"), globals())

WORLD, MODEL = os.path.join(FL, "consol_v1"), os.path.join(FL, "models", "Qwen3-8B")
CANON_AD = os.path.join(D, "inputs", "exp_n256")
SEED_EX = os.path.join(D, "inputs", "seed256.jsonl")
BOOT2_R0 = os.path.join(D, "inputs", "boot_llm2_round_0.json")
B, MAXS = 4, 10                       # MAXS is the global beam2/solve2 read; set to D_t + 2 before every round's searches (O3)
POOL_N, FRONT_N = 300, 200
ROWK = ("tid", "depth", "v", "c", "exec")
ARM = "OPEN"
wd = json.load(open(os.path.join(WORLD, "world.json")))
ZW = [1.0 / (wd["zipf_order"].index(p) + 1) ** 1.1 for p in W.OPN]
HELD = {x for t in map(json.loads, open(os.path.join(WORLD, "held.jsonl"))) for x in t["ins"]}


def load_ruler(k):
    p = os.path.join(OD, "frozen", "RULER_%d.json" % RULER_SEEDS[k])
    sha = _sha(p)
    if sha != RULER_SHA[str(RULER_SEEDS[k])]:
        print("VOID_RULER_SHA", p, sha, flush=True); sys.exit(9)
    return json.load(open(p))["tasks"], sha


def excl_inputs():
    ex = {x for t in BL.make_pool(WORLD, 29000, 300, 10) for x in t["ins"]}
    for k in RULER_SEEDS:
        ex |= {x for t in load_ruler(k)[0] for x in t["ins"]}
    for s in (39000, 39100, 39200, 39300, 39400):
        p = os.path.join(D, "frozen", "MEAS_DEEP_%d.json" % s)
        if os.path.exists(p):
            ex |= {x for t in json.load(open(p))["tasks"] for x in t["ins"]}
    return ex


def ruler_steps(depth):
    return max(12, depth + 2)


def logp_fn(sc):                      # bootllm.solve's logp (bootllm.py:108-112), verbatim
    def logp(st, tgt):
        l = sc.logps(RL.policy_prompt(st, tgt))
        m = max(l)
        z = m + math.log(sum(math.exp(x - m) for x in l))
        return [x - z for x in l]
    return logp


# =====================================================================================================================
if MODE == "ruler":
    sd, K, TS = sys.argv[5], int(sys.argv[6]), [int(x) for x in sys.argv[7].split(",")]
    TAG = os.environ.get("RULER_TAG", "")
    import ident
    tasks, rsha = load_ruler(K)
    ads = {}
    for t in TS:
        a = (CANON_AD if K == 1 else os.path.join(sd, "P_0")) if t == 0 else os.path.join(sd, "P_%d" % t)
        if t > 0 and not os.path.exists(os.path.join(sd, "round_%d.json" % (t - 1))):
            print("RULER_REFUSE P_%d not final (no round_%d.json)" % (t, t - 1), flush=True); sys.exit(4)
        ads["P%d" % t] = a
    sc = ident.Scorer(MODEL, ads)
    for t in TS:
        out = os.path.join(sd, "ruler_%d%s.json" % (t, TAG))
        if os.path.exists(out):
            print("RULER exists", out, flush=True); continue
        a = ads["P%d" % t]
        before = {f: (_md5(os.path.join(a, f)), os.path.getmtime(os.path.join(a, f))) for f in sorted(os.listdir(a)) if os.path.isfile(os.path.join(a, f))}
        t0 = time.time()
        sc.use("P%d" % t)
        lp = logp_fn(sc)
        rows = []
        for x in tasks:
            r = BL.beam(x, B, lp, ruler_steps(x["depth"]))
            rows.append({"tid": x["tid"], "depth": x["depth"], "v": r["v"], "c": r["c"], "exec": r["exec"], "prog": r["prog"]})
        after = {f: (_md5(os.path.join(a, f)), os.path.getmtime(os.path.join(a, f))) for f in before}
        if after != before:
            print("VOID_ADAPTER_CHANGED", a, flush=True); sys.exit(6)
        s = BL.summarize(rows)
        rec = {"summary": dict(s, round=t, seed=K, ruler_seed=RULER_SEEDS[K], ruler_sha256=rsha, adapter=a,
                               adapter_md5=wsum(a), host=os.uname().nodename, job=os.environ.get("SLURM_JOB_ID"), nan=sc.nan,
                               s=round(time.time() - t0), max_steps_rule="max(12, depth + 2)"), "rows": rows}
        tmp = out + ".tmp.%d" % os.getpid()
        json.dump(rec, open(tmp, "w"))
        os.link(tmp, out); os.remove(tmp)
        print("RULER seed=%d t=%d d50=%s ci=%s correct=%d s=%d nan=%d" % (K, t, s["d50"], s["d50_ci"], s["correct"], rec["summary"]["s"], sc.nan), flush=True)
    print("RULER_DONE", flush=True)
    sys.exit(0)

# =====================================================================================================================
assert MODE == "loop"
K, T_TO = int(sys.argv[5]), int(sys.argv[6])
assert 1 <= K <= 99 and 0 <= T_TO < 1000
LEGACY = (K == 1)
sd = os.path.join(OD, "runs", "OPEN_s%d" % K)
os.makedirs(sd, exist_ok=True)
RULER, RULER_SHA_K = load_ruler(K)
EXCL = excl_inputs()


def data_seed(t):
    return 9000 + t if LEGACY else 9000 + 100 * K + t


def front_seed(t):
    return 19000 + t if LEGACY else 19000 + 100 * K + t


def d50eff(ds, Dt):
    d = ds["d50"]
    if d is None:
        d = float(Dt) if ds["correct"] >= 0.5 * ds["n"] else 1.0
    return min(max(float(d), 1.0), float(Dt + 2))


def window_D(t):
    if t == 0:
        return 10
    s = json.load(open(os.path.join(sd, "round_%d.json" % (t - 1))))["summary"]
    return max(10, int(math.ceil(s["d50_eff"])) + 6)


CODE_MD5 = fmd5(os.path.abspath(__file__))
print("META silicyte-0129 OPEN seed=%d t_to=%d sd=%s code_md5=%s opengen_md5=%s bootseed0128_md5=%s ruler=%d sha=%s excl_inputs=%d dry=%s" %
      (K, T_TO, sd, CODE_MD5, fmd5(G.__file__), MD5_0128, RULER_SEEDS[K], RULER_SHA_K[:16], len(EXCL), DRY), flush=True)

if DRY:
    t0 = time.time()
    bad = sum(not G.verify_task(x)[0] for x in RULER)
    print("DRY ruler seed=%d n=%d depths=%s verify_fail=%d" % (RULER_SEEDS[K], len(RULER), sorted({x["depth"] for x in RULER})[-3:], bad), flush=True)
    Dt = 10
    dp, dh = G.make_pool_open(ZW, HELD, data_seed(0), POOL_N, Dt, EXCL)
    vf = sum(not G.verify_task(x)[0] for x in dp)
    print("DRY data_pool k=%d t=0 seed=%d D=%d n=%d excl_hits=%d verify_fail=%d depths=%s s=%.1f" %
          (K, data_seed(0), Dt, len(dp), dh, vf, json.dumps({d: sum(1 for x in dp if x["depth"] == d) for d in range(1, Dt + 1)}), time.time() - t0), flush=True)
    ref = BL.make_pool(WORLD, data_seed(0), POOL_N, 10)
    print("DRY data_pool tid_depth_equal_to_0128_pool (same rng, same depth draws; programs differ by O1):",
          [(x["tid"], x["depth"]) for x in dp] == [(x["tid"], x["depth"]) for x in ref], flush=True)
    d50_0128 = 2.842
    r0 = "/N/scratch/bsmensah/silo/bootseed/runs/%s/round_0.json" % ("s1" if K == 1 else "FRONTIER_s%d" % K)
    if os.path.exists(r0):
        d50_0128 = json.load(open(r0))["summary"]["d50"]
    lo, hi = f3_window(d50_0128)
    t1 = time.time()
    fp, fh = G.make_pool_open(ZW, HELD, front_seed(0), FRONT_N, hi, EXCL, lo=lo)
    vf = sum(not G.verify_task(x)[0] for x in fp)
    print("DRY frontier_pool k=%d t=0 seed=%d window=%d,%d (0128 round-0 d50 %s) n=%d excl_hits=%d verify_fail=%d s=%.1f" %
          (K, front_seed(0), lo, hi, d50_0128, len(fp), fh, vf, time.time() - t1), flush=True)
    # what the pools look like when the loop is far past the 0128 ceiling
    for Dt, x50 in ((20, 14.5), (40, 34.5)):
        t1 = time.time()
        dpx, dhx = G.make_pool_open(ZW, HELD, data_seed(0), POOL_N, Dt, EXCL)
        lo, hi = f3_window(x50)
        fpx, fhx = G.make_pool_open(ZW, HELD, front_seed(0), FRONT_N, hi, EXCL, lo=lo)
        vf = sum(not G.verify_task(x)[0] for x in dpx + fpx)
        print("DRY deep D=%d n_dp=%d window=%d,%d n_fp=%d excl_hits=%d verify_fail=%d s=%.1f" % (Dt, len(dpx), lo, hi, len(fpx), dhx + fhx, vf, time.time() - t1), flush=True)
    seed_rows = [json.loads(l) for l in open(SEED_EX)]
    print("DRY seed256 states touching exclusions:", sum(any(c in EXCL for c in r["cur"]) for r in seed_rows), flush=True)
    print("DRY imported_0128_functions", ",".join(IMPORTED), flush=True)
    print("DRY_OK", flush=True)
    sys.exit(0)

import ident


def start_check():
    """O8: exp_n256 on the first 60 tasks of pool 9000 at max_steps 10 = boot_llm2 round 0's first 60 eval rows; RNG-neutral."""
    import torch
    cpu, cu = torch.get_rng_state(), torch.cuda.get_rng_state_all()
    t0 = time.time()
    sc = ident.Scorer(MODEL, {"P": CANON_AD})
    ev = BL.solve(BL.make_pool(WORLD, 9000, POOL_N, 10)[:60], sc, "P", B, 10)
    nan = sc.nan
    free(sc); del sc; gc.collect()
    torch.set_rng_state(cpu); torch.cuda.set_rng_state_all(cu)
    ok = proj(ev) == json.load(open(BOOT2_R0))["eval_rows"][:60] and nan == 0
    rec = {"host": os.uname().nodename, "job": os.environ.get("SLURM_JOB_ID"), "rows_equal_60": ok, "nan": nan, "s": round(time.time() - t0)}
    with open(os.path.join(sd, "start_checks.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    print("START_CHECK", json.dumps(rec), flush=True)
    if not ok:
        print("VOID_START_CHECK exp_n256 does not reproduce boot_llm2 round-0 rows 0..59", flush=True); sys.exit(7)


RPROC = [None]


def ruler_kick(upto, wait=False):
    """Start one ruler process for every final P_u (u <= upto) without ruler_u.json, unless one is still running (O5)."""
    p = RPROC[0]
    if p is not None:
        if wait:
            p.wait()
        if p.poll() is None:
            return
        RPROC[0] = None
    todo = [u for u in range(0, upto + 1) if not os.path.exists(os.path.join(sd, "ruler_%d.json" % u))
            and (u == 0 or os.path.exists(os.path.join(sd, "round_%d.json" % (u - 1))))]
    if not todo:
        return
    log = open(os.path.join(sd, "ruler_%s.log" % time.strftime("%m%d_%H%M%S")), "w")
    RPROC[0] = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__), D, FL, OD, "ruler", sd, str(K), ",".join(map(str, todo))],
                                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    print("RULER_SPAWN pid=%d rounds=%s" % (RPROC[0].pid, todo), flush=True)


start_check()
seed_rows = [json.loads(l) for l in open(SEED_EX)]
assert len(seed_rows) == 256
if LEGACY:
    P0 = CANON_AD
else:
    P0 = os.path.join(sd, "P_0")
    if not os.path.isfile(os.path.join(P0, "adapter_config.json")):
        if os.path.exists(os.path.join(sd, "round_0.json")):
            print("VOID_RESUME P_0 missing after round 0", flush=True); sys.exit(8)
        src = os.path.join(D, "runs", "FRONTIER_s%d" % K, "P_0")
        if os.path.isfile(os.path.join(src, "adapter_config.json")) and os.path.exists(os.path.join(D, "runs", "FRONTIER_s%d" % K, "round_0.json")):
            shutil.copytree(src, P0 + ".tmp"); os.replace(P0 + ".tmp", P0)
            print("P0_COPIED from", src, "adapter_md5", wsum(P0)[:12], "source_md5", wsum(src)[:12], flush=True)
        else:
            train(seed_rows, P0, 1000 * K, K, "P0")
for t in range(0, T_TO + 1):
    rp = os.path.join(sd, "round_%d.json" % t)
    if os.path.exists(rp):
        print("ROUND", t, "done, skip", flush=True); continue
    ad = P0 if t == 0 else os.path.join(sd, "P_%d" % t)
    if not os.path.isfile(os.path.join(ad, "adapter_config.json")):
        print("MISSING_POLICY", ad, flush=True); break
    ruler_kick(t)
    t0 = time.time()
    Dt = window_D(t)
    MAXS = Dt + 2
    spath = os.path.join(sd, "search_%d.json" % t)
    if os.path.exists(spath):
        S = json.load(open(spath)); print("SEARCH", t, "cached", flush=True)
        assert S["D"] == Dt and S["max_steps"] == MAXS
    else:
        sc = ident.Scorer(MODEL, {"P": ad})
        pool, dhit = G.make_pool_open(ZW, HELD, data_seed(t), POOL_N, Dt, EXCL)
        dp = BL.solve(pool, sc, "P", B, MAXS)
        ds = BL.summarize(dp)
        de = d50eff(ds, Dt)
        dmin = max(1, int(math.floor(de)))
        lo, hi = f3_window(de)
        fp, fhit = G.make_pool_open(ZW, HELD, front_seed(t), FRONT_N, hi, EXCL, lo=lo)
        tr = solve2(fp, sc, "P")
        print("LEVER_POOL seed=%d arm=OPEN t=%d D=%d max_steps=%d data_seed=%d front_seed=%d window=%d,%d d50=%s d50eff=%.3f n_dp=%d n_tr=%d dp_excl_hits=%d front_excl_hits=%d" %
              (K, t, Dt, MAXS, data_seed(t), front_seed(t), lo, hi, ds["d50"], de, len(dp), len(tr), dhit, fhit), flush=True)
        S = {"D": Dt, "max_steps": MAXS, "dp": dp, "dp_summary": ds, "d50_eff": de, "tr": tr, "dmin": dmin, "window": [lo, hi],
             "dp_excl_hits": dhit, "front_excl_hits": fhit, "nan": sc.nan, "search_s": round(time.time() - t0)}
        free(sc); del sc; gc.collect()
        jdump(S, spath)
    own, hs, hseed = frontier_examples(S["tr"] + [dict(r, hprog=None) for r in S["dp"]], S["dmin"])
    op = os.path.join(sd, "own_%d.jsonl" % t)
    with open(op + ".tmp", "w") as f:
        for e in own + hs:
            f.write(json.dumps(e) + "\n")
    os.replace(op + ".tmp", op)
    allown = []
    for u in range(0, t + 1):
        allown += [json.loads(l) for l in open(os.path.join(sd, "own_%d.jsonl" % u))]
    rs = None if LEGACY else 1000 * K + t + 1
    if RPROC[0] is not None:   # DEVIATION 1105-W: train only after the ruler process exits (trainer + ruler OOM fix)
        RPROC[0].wait(); print("RULER_WAIT_DONE t=%d rc=%s" % (t, RPROC[0].returncode), flush=True)
    trs, omd5, amd5 = train(seed_rows + allown, os.path.join(sd, "P_%d" % (t + 1)), rs, rs, "r%d" % t)
    Dt = S["D"]
    byd = lambda rows, key: {d: [sum(1 for r in rows if r["depth"] == d), sum(1 for r in rows if r["depth"] == d and r[key])] for d in range(1, max([Dt] + [r["depth"] for r in rows]) + 1)}
    N = len(seed_rows) + len(allown)
    tel = {"round": t, "arm": ARM, "seed": K, "D": Dt, "max_steps": S["max_steps"], "data_d50": S["dp_summary"]["d50"], "d50_eff": S["d50_eff"],
           "dmin": S["dmin"], "window": S["window"], "data_by_depth_n_correct": byd(S["dp"], "c"), "train_by_depth_n_verified": byd(S["tr"], "v"),
           "own_new": len(own), "hindsight_new": len(hs), "hindsight_seed": hseed, "train_examples": N,
           "dp_excl_hits": S["dp_excl_hits"], "front_excl_hits": S["front_excl_hits"],
           "own_depth_max": max([e["depth"] for e in own] or [0]), "hindsight_len_max": max([e["depth"] for e in hs] or [0]),
           "distinct_programs": len({tuple(r["prog"]) for r in S["dp"] + S["tr"] if r["v"]}),
           "nan": S["nan"], "search_s": S["search_s"], "train_s": trs, "order_md5": omd5, "adapter_md5": amd5}
    tel["round_s"] = round(time.time() - t0)
    summ = dict(S["dp_summary"])
    summ.update({"format": "open0129", "round": t, "arm": ARM, "seed": K, "code_md5": CODE_MD5, "D": Dt, "max_steps": S["max_steps"],
                 "d50_eff": S["d50_eff"], "dmin": S["dmin"], "train_pool_depths": S["window"], "train_solved": sum(r["v"] for r in S["tr"]),
                 "own_new": len(own), "hindsight_new": len(hs), "train_examples": N, "data_pool_seed": data_seed(t),
                 "frontier_pool_seed": front_seed(t), "adapter_md5": amd5, "ruler_seed": RULER_SEEDS[K], "round_s": tel["round_s"]})
    jdump(tel, os.path.join(sd, "tel_%d.json" % t))
    jdump({"summary": summ, "eval_rows": proj(S["dp"])}, rp)
    print("ROUND", t, json.dumps({k: tel[k] for k in tel if k not in ("data_by_depth_n_correct", "train_by_depth_n_verified")}), flush=True)
ruler_kick(T_TO + 1, wait=True)
ruler_kick(T_TO + 1, wait=True)
if RPROC[0] is not None:
    RPROC[0].wait()
print("OPEN0129_DONE", flush=True)
