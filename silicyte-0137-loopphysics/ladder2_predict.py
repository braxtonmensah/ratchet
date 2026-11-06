#!/usr/bin/env python3
"""LADDER-2 prediction from the measured two-exponent law: reach when all learning happens on verified short hops.
Inputs are measured values only (ratchet silicyte-0137): per-distance alpha k=2 0.637, k=3 0.294, k=4 0.202, near band 0.378;
pooled alpha 0.175; gamma 1.19; 0128 seed FRONTIER_s2 fit A, B for the scale. Stdlib only."""
import json, math
F = json.load(open("/N/scratch/bsmensah/silo/oneshot0136/FORECAST_0128_EXT_1105.json"))["FRONTIER_s2"]
A, B, G = F["A"], F["B"], 1.19


def run(alpha, hop, rounds=30, n0=256.0):
    """per-hop error e = A n^-alpha; a hop of length `hop` succeeds with (1-e)^hop; reach = hop * ln0.5 / ln p_hop (chain of
    verified hops); rows per round = B * reach^gamma (as measured)."""
    n, out = n0, []
    for t in range(rounds + 1):
        e = min(0.95, A * n ** (-alpha))
        p_hop = (1 - e) ** hop
        reach = hop * math.log(0.5) / math.log(p_hop)
        out.append(reach)
        n += B * reach ** G
    return out


def delta(y):
    R = len(y) - 1; h = R // 2
    def s(xs, ys):
        mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
        return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
    return s(list(range(h, R + 1)), y[h:]) - s(list(range(0, h + 1)), y[:h + 1])


rows = []
for name, alpha, hop in (("as 0128 (pooled alpha, 1-step)", 0.175, 1), ("near band k2-4", 0.378, 2), ("2-hop ladder", 0.637, 2), ("3-hop ladder", 0.294, 3)):
    y = run(alpha, hop)
    ag = alpha * G; a1 = alpha * (1 + G)
    rows.append((name, alpha, hop, ag, a1, y))
    print("%-32s alpha %.3f hop %d | alpha*gamma %.2f alpha(1+gamma) %.2f | reach r0 %.1f r10 %.1f r20 %.1f r30 %.1f | delta(30) %+.3f %s"
          % (name, alpha, hop, ag, a1, y[0], y[10], y[20], y[30], delta(y), "ACCELERATES" if delta(y) > 0 else "decelerates"))
json.dump([{"name": r[0], "alpha": r[1], "hop": r[2], "alpha_gamma": r[3], "alpha_1_gamma": r[4], "reach": [round(v, 3) for v in r[5]]} for r in rows],
          open("ladder2_predict_1105.json", "w"), indent=1)
