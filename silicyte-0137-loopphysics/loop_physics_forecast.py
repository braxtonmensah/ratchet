#!/usr/bin/env python3
"""Registered forecast: fit the two-exponent law on 0128 rounds 0..10 per seed and forecast MEAS d50_fixed for rounds 11..30.
Reads ONLY round_0..round_10.json (it never opens a round > 10). Stdlib only."""
import json, math, os
D = "/N/scratch/bsmensah/silo/bootseed/runs"
RUNS = ["s1", "FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"]


def ols(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return b, my - b * mx


def mle_p(bd):
    best = None
    for i in range(999):
        p = 0.5 + 0.0005 * i
        if p >= 1: break
        ll = sum(k * math.log(p ** d) + (n - k) * math.log(1 - p ** d) for d, (n, k) in bd.items())
        if best is None or ll > best[0]: best = (ll, p)
    return best[1]


out = {}
for r in RUNS:
    N, E, R, Y = [], [], [], []
    prevN = 256
    for t in range(11):
        s = json.load(open(os.path.join(D, r, "round_%d.json" % t))); sm = s["summary"]
        bd = {}
        for x in s["fixed_rows"]:
            n, k = bd.get(x["depth"], (0, 0)); bd[x["depth"]] = (n + 1, k + (1 if x["v"] and x["c"] else 0))
        N.append(prevN); E.append(1 - mle_p(bd)); R.append(sm["own_new"] + sm["hindsight_new"])
        Y.append(sm.get("d50_fixed", (sm.get("fixed_summary") or {}).get("d50")))
        prevN = sm["train_examples"]
    Nnext = prevN   # rows P_11 is trained on = train_examples of round 10
    na, la = ols([math.log(x) for x in N], [math.log(x) for x in E]); alpha, A = -na, math.exp(la)
    g, lb = ols([math.log(x) for x in Y], [math.log(x) for x in R]); B = math.exp(lb)
    geo = lambda e: math.log(0.5) / math.log(1 - e)
    cal = sum(Y[t] / geo(E[t]) for t in range(11)) / 11.0
    n = Nnext; fc = {}
    for t in range(11, 31):
        d = cal * geo(A * n ** (-alpha)); fc[t] = round(d, 3)
        n = n + B * d ** g
    out[r] = {"alpha": round(alpha, 4), "A": round(A, 5), "gamma": round(g, 4), "B": round(B, 4), "cal": round(cal, 4),
              "N_for_P11": Nnext, "forecast_d50_fixed": fc}
    print(r, "alpha %.4f gamma %.4f cal %.3f" % (alpha, g, cal), " ".join("%d:%.2f" % (t, fc[t]) for t in (11, 12, 15, 20, 25, 30)))
json.dump(out, open("FORECAST_0128_EXT_1105.json", "w"), indent=1, sort_keys=True)
print("WROTE FORECAST_0128_EXT_1105.json")
