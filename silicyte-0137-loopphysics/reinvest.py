#!/usr/bin/env python3
"""GATE_REINVEST_1105: cost per verified solve vs d50 on 0128 frontier and data pools, rounds 0..10. Stdlib only."""
import json, math, os
D = "/N/scratch/bsmensah/silo/bootseed/runs"
RUNS = ["FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"]
ALPHA = {"FRONTIER_s2": 0.1923, "FRONTIER_s3": 0.1425, "FRONTIER_s4": 0.2030}   # RESULT_LOOP_PHYSICS_1105 estimate (ii)
GAMMA = {"FRONTIER_s2": 0.7818, "FRONTIER_s3": 1.4696, "FRONTIER_s4": 1.4460}


def ols(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    res = [y - my - b * (x - mx) for x, y in zip(xs, ys)]
    return b, math.sqrt(sum(r * r for r in res) / (n - 2) / sxx)


helps = crosses = True
for r in RUNS:
    Y, C = [], {"tr": [], "dp": []}
    for t in range(11):
        sm = json.load(open(os.path.join(D, r, "round_%d.json" % t)))["summary"]
        Y.append(sm.get("d50_fixed", (sm.get("fixed_summary") or {}).get("d50")))
        s = json.load(open(os.path.join(D, r, "search_%d.json" % t)))
        for k in ("tr", "dp"):
            rows = s.get(k) or []
            ex = sum(x["exec"] for x in rows); nv = sum(1 for x in rows if x["v"])
            C[k].append((ex, nv, len(rows)))
    for k in ("tr", "dp"):
        c = [ex / float(nv) for ex, nv, n in C[k]]
        b, se = ols([math.log(y) for y in Y], [math.log(x) for x in c]); beta = -b
        a, g = ALPHA[r], GAMMA[r]
        print("%s %s beta %+.3f (se %.3f) alpha(1+gamma+beta) %.3f | cost/solve %s | solved %s"
              % (r, k, beta, se, a * (1 + g + beta), " ".join("%.0f" % x for x in c), " ".join("%d/%d" % (nv, n) for ex, nv, n in C[k])))
        if k == "tr":
            helps = helps and beta > 0
            crosses = crosses and a * (1 + g + beta) > 1
print("GATE_REINVEST", "REINVEST_CROSSES" if crosses else ("REINVEST_HELPS" if helps else "NO_HELP"))
