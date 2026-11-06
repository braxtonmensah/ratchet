#!/usr/bin/env python3
"""GATE_GUIDE_ALPHA_1105: alpha and gamma of GUIDE_sk vs FRONTIER_sk on the same rounds 0..T. Stdlib only."""
import json, math, os
D = "/N/scratch/bsmensah/silo/bootseed/runs"


def ols(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    res = [y - my - b * (x - mx) for x, y in zip(xs, ys)]
    return b, math.sqrt(sum(r * r for r in res) / max(1, n - 2) / sxx)


def mle_p(bd):
    best = None
    for i in range(999):
        p = 0.5 + 0.0005 * i
        if p >= 1: break
        ll = sum(k * math.log(p ** d) + (n - k) * math.log(1 - p ** d) for d, (n, k) in bd.items())
        if best is None or ll > best[0]: best = (ll, p)
    return best[1]


def series(run, T):
    N, E, R, Y = [], [], [], []
    prevN = 256
    for t in range(T + 1):
        s = json.load(open(os.path.join(D, run, "round_%d.json" % t))); sm = s["summary"]
        bd = {}
        for x in s["fixed_rows"]:
            n, k = bd.get(x["depth"], (0, 0)); bd[x["depth"]] = (n + 1, k + (1 if x["v"] and x["c"] else 0))
        N.append(prevN); E.append(1 - mle_p(bd)); R.append(sm["own_new"] + sm["hindsight_new"])
        Y.append(sm.get("d50_fixed", (sm.get("fixed_summary") or {}).get("d50")))
        prevN = sm["train_examples"]
    a, ase = ols([math.log(x) for x in N], [math.log(x) for x in E])
    g, gse = ols([math.log(x) for x in Y], [math.log(x) for x in R])
    return -a, ase, g, gse, N, Y


ratios = []
for k in (2, 3):
    G = "GUIDE_s%d" % k; F = "FRONTIER_s%d" % k
    T = max(int(f[6:-5]) for f in os.listdir(os.path.join(D, G)) if f.startswith("round_") and f.endswith(".json"))
    ag, ages, gg, ggse, NG, YG = series(G, T)
    af, afse, gf, gfse, NF, YF = series(F, T)
    ratios.append(ag / af)
    print("pair s%d T=%d | GUIDE alpha %.4f (se %.4f) gamma %.3f (se %.3f) | FRONTIER alpha %.4f (se %.4f) gamma %.3f (se %.3f) | ratio %.3f"
          % (k, T, ag, ages, gg, ggse, af, afse, gf, gfse, ag / af))
    print("  GUIDE N %s d50 %s" % (NG, " ".join("%.2f" % y for y in YG)))
    print("  FRONT N %s d50 %s" % (NF, " ".join("%.2f" % y for y in YF)))
lab = "LEVER_CANDIDATE" if all(r >= 1.5 for r in ratios) else ("NO_LEVER" if all(r <= 1.1 for r in ratios) else "UNCLEAR")
print("GATE_GUIDE_ALPHA", lab)
