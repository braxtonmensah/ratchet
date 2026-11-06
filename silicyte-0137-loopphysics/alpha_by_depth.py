#!/usr/bin/env python3
"""GATE_ALPHA_BY_DEPTH_1105: per-depth learning exponent of 0128, rounds 0..10. Stdlib only."""
import json, math, os
D = "/N/scratch/bsmensah/silo/bootseed/runs"
RUNS = ["s1", "FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"]


def ols(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


per = {d: [] for d in range(2, 9)}
for r in RUNS:
    N = []; S = {d: [] for d in range(2, 9)}
    prevN = 256
    for t in range(11):
        s = json.load(open(os.path.join(D, r, "round_%d.json" % t))); sm = s["summary"]
        cnt = {}
        for x in s["fixed_rows"]:
            n, k = cnt.get(x["depth"], (0, 0)); cnt[x["depth"]] = (n + 1, k + (1 if x["v"] and x["c"] else 0))
        N.append(prevN); prevN = sm["train_examples"]
        for d in range(2, 9):
            n, k = cnt.get(d, (0, 0)); S[d].append((k + 0.5) / (n + 1.0))
    line = []
    for d in range(2, 9):
        e = [1 - sv ** (1.0 / d) for sv in S[d]]
        a = -ols([math.log(x) for x in N], [math.log(x) for x in e])
        per[d].append(a); line.append("d%d %.3f" % (d, a))
    print(r, " ".join(line))
    print("   solve share by round, d4: %s | d6: %s" % (" ".join("%.2f" % x for x in S[4]), " ".join("%.2f" % x for x in S[6])))
pooled = {}
for d in range(2, 9):
    v = per[d]; m = sum(v) / len(v); sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1)); pooled[d] = (m, sd / 2)
    print("POOLED d%d alpha %.4f se %.4f" % (d, m, sd / 2))
ms = [m for m, se in pooled.values()]
homo = all(abs(m - 0.175) <= 2 * se for m, se in pooled.values()) or (max(ms) - min(ms) < 0.1)
best = max(pooled, key=lambda d: pooled[d][0])
print("SPREAD %.4f, largest alpha at depth %d" % (max(ms) - min(ms), best))
print("GATE_ALPHA_BY_DEPTH", "HOMOGENEOUS" if homo else "HETEROGENEOUS")
