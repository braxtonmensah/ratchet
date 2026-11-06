#!/usr/bin/env python3
"""PREDICT_0129_FROM_LAW_1105: simulate the 0128 law (per-seed fits) and compute 0129's delta statistic. Uses no 0129 data."""
import json, math
F = json.load(open("FORECAST_0128_EXT_1105.json"))
MAP = {1: "s1", 2: "FRONTIER_s2", 3: "FRONTIER_s3", 4: "FRONTIER_s4"}


def ols_slope(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


out = {}
allneg = True
for k, r in MAP.items():
    p = F[r]; a, A, g, B = p["alpha"], p["A"], p["gamma"], p["B"]
    n = 256.0; d = []
    for t in range(36):
        e = A * n ** (-a); dt = math.log(0.5) / math.log(1 - e); d.append(dt); n += B * dt ** g
    row = {}
    for R in (20, 25, 30, 35):
        h = R // 2
        delta = ols_slope(list(range(h, R + 1)), d[h:R + 1]) - ols_slope(list(range(0, h + 1)), d[0:h + 1])
        gain = (d[R] - d[0]) / R
        row[R] = {"delta": round(delta, 5), "mean_gain": round(gain, 5), "delta_over_gain": round(delta / gain, 3)}
        allneg = allneg and delta < 0
    out["seed%d" % k] = {"law_from": r, "d_geo": [round(x, 3) for x in d], "by_R": row}
    print("seed %d (%s): " % (k, r) + " | ".join("R%d delta %+.4f gain %.4f ratio %+.3f" % (R, v["delta"], v["mean_gain"], v["delta_over_gain"]) for R, v in row.items()))
json.dump(out, open("PREDICT_0129_FROM_LAW_1105.json", "w"), indent=1, sort_keys=True)
print("PREDICTION delta<0 for every seed and R:", allneg)
