#!/usr/bin/env python3
"""GATE_NOLEARN_MEAS_1105: similarity beam on 0128's MEAS 29000 pool (rebuilt with 0128's lib), vs 0128 trained d50_fixed."""
import sys, json, math, time, difflib
sys.path.insert(0, "/N/scratch/bsmensah/silo/bootseed/lib")
import consol as W
import bootllm as BL
D = "/N/scratch/bsmensah/silo/bootseed"
WORLD = "/N/scratch/bsmensah/arc26/fourth_law/consol_v1"
pool = BL.make_pool(WORLD, 29000, 300, 10)
ref = [r["tid"] for r in json.load(open(D + "/runs/s1/round_0.json"))["fixed_rows"]]
same = [t["tid"] for t in pool] == ref
print("LEVER pool tids equal 0128 s1 round_0 fixed_rows tids in order:", same, len(pool))
if not same:
    print("STOP"); sys.exit(3)


def sim(state, tgt):
    return sum(difflib.SequenceMatcher(None, a, b).ratio() for a, b in zip(state, tgt)) / len(tgt)


def beam_sim(t, B=4, max_steps=10):
    tgt = tuple(t["outs"][:4]); bm = [(tuple(t["ins"][:4]), [])]
    for _ in range(max_steps):
        kids, seen = [], set()
        for st, pre in bm:
            for o in W.OPN:
                nx = tuple(W.run_prog((o,), c) for c in st)
                if any(x is None for x in nx) or nx in seen:
                    continue
                seen.add(nx)
                if nx == tgt:
                    prog = pre + [o]
                    h = [W.run_prog(tuple(prog), x) for x in t["ins"][4:6]]
                    return True, h[0] == t["outs"][4] and h[1] == t["outs"][5]
                kids.append((sim(nx, tgt), nx, pre + [o]))
        if not kids:
            break
        kids.sort(key=lambda k: -k[0]); bm = [(nx, p) for s, nx, p in kids[:B]]
    return False, False


t0 = time.time(); rows = []
for t in pool:
    v, c = beam_sim(t)
    rows.append({"tid": t["tid"], "depth": t["depth"], "v": v, "c": c})
d50 = BL.logistic_d50(rows)
byd = {}
for r in rows:
    n, k = byd.get(r["depth"], (0, 0)); byd[r["depth"]] = (n + 1, k + (1 if r["c"] else 0))
print("BY_DEPTH", " ".join("%d:%d/%d" % (d, k, n) for d, (n, k) in sorted(byd.items())))
print("NOLEARN_MEAS_D50 %s correct %d of 300 s %.0f" % (("%.3f" % d50) if d50 else "None", sum(r["c"] for r in rows), time.time() - t0))
for run in ("s1", "FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"):
    ys = []
    for tt in range(11):
        sm = json.load(open("%s/runs/%s/round_%d.json" % (D, run, tt)))["summary"]
        ys.append(sm.get("d50_fixed", (sm.get("fixed_summary") or {}).get("d50")))
    print("0128 %s d50_fixed r0..r10: %s" % (run, " ".join("%.2f" % y for y in ys)))
json.dump(rows, open("nolearn_meas_rows_1105.json", "w"))
