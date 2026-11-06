#!/usr/bin/env python3
"""GATE_NOLEARN_HEURISTIC_1105: zero-learning similarity beam on RULER_49100. Stdlib + 0128's consol world (read-only)."""
import sys, json, math, time, difflib
sys.path.insert(0, "/N/scratch/bsmensah/silo/bootseed/lib")
import consol as W
R = json.load(open("/N/scratch/bsmensah/silo/open0129/frozen/RULER_49100.json"))
B = 4


def sim(state, tgt):
    return sum(difflib.SequenceMatcher(None, a, b).ratio() for a, b in zip(state, tgt)) / len(tgt)


def beam_sim(t, max_steps):
    tgt = tuple(t["outs"][:4])
    bm = [(tuple(t["ins"][:4]), [])]
    ex = 0
    for _ in range(max_steps):
        kids, seen = [], set()
        for st, pre in bm:
            for o in W.OPN:
                nx = tuple(W.run_prog((o,), c) for c in st)
                ex += 1
                if any(x is None for x in nx) or nx in seen:
                    continue
                seen.add(nx)
                if nx == tgt:
                    prog = pre + [o]
                    h = [W.run_prog(tuple(prog), x) for x in t["ins"][4:6]]
                    return True, h[0] == t["outs"][4] and h[1] == t["outs"][5], len(prog), ex
                kids.append((sim(nx, tgt), nx, pre + [o]))
        if not kids:
            break
        kids.sort(key=lambda k: -k[0])
        bm = [(nx, p) for s, nx, p in kids[:B]]
    return False, False, None, ex


def logistic_d50(rows):
    xs = [r["depth"] for r in rows]; ys = [1.0 if r["c"] else 0.0 for r in rows]
    a, b = 0.0, 0.0
    for _ in range(100):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in zip(xs, ys):
            p = 1 / (1 + math.exp(-max(-30, min(30, a - b * x))))
            g0 += y - p; g1 += -(y - p) * x
            wgt = p * (1 - p) + 1e-9
            h00 += wgt; h01 += -wgt * x; h11 += wgt * x * x
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            return None
        da = (h11 * g0 - h01 * g1) / det; db = (-h01 * g0 + h00 * g1) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-9:
            break
    return a / b if b > 1e-6 else None


t0 = time.time(); rows = []
for t in R["tasks"]:
    v, c, L, ex = beam_sim(t, max(12, t["depth"] + 2))
    rows.append({"tid": t["tid"], "depth": t["depth"], "v": v, "c": c, "L": L, "exec": ex})
byd = {}
for r in rows:
    n, k = byd.get(r["depth"], (0, 0)); byd[r["depth"]] = (n + 1, k + (1 if r["c"] else 0))
print("BY_DEPTH", " ".join("%d:%d/%d" % (d, k, n) for d, (n, k) in sorted(byd.items())))
d50 = logistic_d50(rows)
print("NOLEARN_D50 %s correct %d of %d s %.0f (P_0 LLM reference 3.059, 26 correct)" % (("%.3f" % d50) if d50 else "None", sum(r["c"] for r in rows), len(rows), time.time() - t0))
json.dump(rows, open("nolearn_rows_1105.json", "w"))
