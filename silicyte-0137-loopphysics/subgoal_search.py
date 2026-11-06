#!/usr/bin/env python3
"""GATE_SUBGOAL_SEARCH_1105: similarity beam with oracle intermediate states on RULER_49100. Stdlib + 0128's consol world."""
import sys, json, math, time, difflib
sys.path.insert(0, "/N/scratch/bsmensah/silo/bootseed/lib")
import consol as W
sys.path.insert(0, "/N/scratch/bsmensah/silo/bootseed/lib")
import bootllm as BL
R = json.load(open("/N/scratch/bsmensah/silo/open0129/frozen/RULER_49100.json"))
B = 4


def sim(state, tgt):
    return sum(difflib.SequenceMatcher(None, a, b).ratio() for a, b in zip(state, tgt)) / len(tgt)


def hop(start, tgt, max_steps):
    """similarity beam from start rows to tgt rows; returns the op list or None"""
    start, tgt = tuple(start), tuple(tgt)
    if start == tgt:
        return []
    bm = [(start, [])]
    for _ in range(max_steps):
        kids, seen = [], set()
        for st, pre in bm:
            for o in W.OPN:
                nx = tuple(W.run_prog((o,), c) for c in st)
                if any(x is None for x in nx) or nx in seen:
                    continue
                seen.add(nx)
                if nx == tgt:
                    return pre + [o]
                kids.append((sim(nx, tgt), nx, pre + [o]))
        if not kids:
            return None
        kids.sort(key=lambda k: -k[0]); bm = [(nx, p) for s, nx, p in kids[:B]]
    return None


def run_arm(t, cuts):
    """cuts: list of reference-step indices where an oracle state is given (exclusive of 0 and d)"""
    ins = t["ins"][:4]; prog = t["prog"]; d = t["depth"]
    points = [0] + cuts + [d]
    states = [[W.run_prog(tuple(prog[:k]), x) for x in ins] for k in points[:-1]] + [t["outs"][:4]]
    full = []
    for i in range(len(points) - 1):
        L = points[i + 1] - points[i]
        ms = max(12, d + 2) if len(points) == 2 else max(6, L + 2)
        h = hop(states[i], states[i + 1], ms)
        if h is None:
            return False
        full += h
    test = [W.run_prog(tuple(full), x) for x in t["ins"][4:6]]
    return test[0] == t["outs"][4] and test[1] == t["outs"][5]


t0 = time.time()
res = {"PLAIN": [], "MID": [], "HOP4": []}
for t in R["tasks"]:
    d = t["depth"]
    res["PLAIN"].append({"depth": d, "c": run_arm(t, [])})
    res["MID"].append({"depth": d, "c": run_arm(t, [d // 2] if d >= 2 else [])})
    res["HOP4"].append({"depth": d, "c": run_arm(t, list(range(4, d, 4)))})
for arm, rows in res.items():
    d50 = BL.logistic_d50(rows)
    deep = sum(1 for r in rows if r["c"] and r["depth"] >= 20)
    print("%s d50 %s solved %d of 300 deep(>=20) %d" % (arm, ("%.3f" % d50) if d50 else "None", sum(r["c"] for r in rows), deep))
byd = {}
for arm, rows in res.items():
    for r in rows:
        byd.setdefault(r["depth"], {}).setdefault(arm, 0)
        byd[r["depth"]][arm] += 1 if r["c"] else 0
print("BY_DEPTH (PLAIN/MID/HOP4 of 10):", " ".join("%d:%d/%d/%d" % (d, v.get("PLAIN", 0), v.get("MID", 0), v.get("HOP4", 0)) for d, v in sorted(byd.items())))
p = BL.logistic_d50(res["PLAIN"]); h = BL.logistic_d50(res["HOP4"])
print("GATE_SUBGOAL_SEARCH", "SUBGOALS_BUY_DEPTH" if (p and h and h >= 2 * p) or (p and h is None and sum(r["c"] for r in res["HOP4"]) > 250) else "LIMITED", "s %.0f" % (time.time() - t0))
