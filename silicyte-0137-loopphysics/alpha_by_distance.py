#!/usr/bin/env python3
"""GATE_ALPHA_BY_DISTANCE_1105: per-distance step success q_k = s_k / s_{k-1} and its learning exponent, pooled over 4 seeds."""
import json, math, os, random
D = "/N/scratch/bsmensah/silo/bootseed/runs"
RUNS = ["s1", "FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"]


def ols(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


rows = {t: {d: [] for d in range(1, 11)} for t in range(11)}   # outcomes per round and depth, pooled over seeds
Nm = []
for t in range(11):
    ns = []
    for r in RUNS:
        s = json.load(open(os.path.join(D, r, "round_%d.json" % t)))
        for x in s["fixed_rows"]:
            rows[t][x["depth"]].append(1 if x["v"] and x["c"] else 0)
        ns.append(256 if t == 0 else json.load(open(os.path.join(D, r, "round_%d.json" % (t - 1))))["summary"]["train_examples"])
    Nm.append(sum(ns) / float(len(ns)))


def alphas(R):
    out = {}
    for k in range(1, 9):
        es = []
        for t in range(11):
            sk = (sum(R[t][k]) + 0.5) / (len(R[t][k]) + 1.0)
            sp = 1.0 if k == 1 else (sum(R[t][k - 1]) + 0.5) / (len(R[t][k - 1]) + 1.0)
            q = min(sk / sp, 0.999)
            es.append(max(1 - q, 1e-3))
        out[k] = -ols([math.log(x) for x in Nm], [math.log(x) for x in es])
    return out


base = alphas(rows)
rng = random.Random(7)
boots = []
for b in range(500):
    R = {t: {d: [rng.choice(v) for _ in v] for d, v in rows[t].items()} for t in rows}
    boots.append(alphas(R))
for k in range(1, 9):
    v = sorted(x[k] for x in boots)
    print("k=%d alpha %.4f  90%% [%.4f, %.4f]" % (k, base[k], v[25], v[474]))
near = [sum(x[k] for k in (2, 3, 4)) / 3 for x in boots]; far = [sum(x[k] for k in (5, 6, 7, 8)) / 4 for x in boots]
bn = sum(base[k] for k in (2, 3, 4)) / 3; bf = sum(base[k] for k in (5, 6, 7, 8)) / 4
near.sort(); far.sort()
print("BAND near(2-4) %.4f [%.4f, %.4f] | far(5-8) %.4f [%.4f, %.4f]" % (bn, near[25], near[474], bf, far[25], far[474]))
lab = "FAR_SLOW" if far[474] < near[25] else ("NEAR_EQUAL" if abs(bn - bf) < 0.05 else "MIXED")
print("GATE_ALPHA_BY_DISTANCE", lab)
