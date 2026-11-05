#!/usr/bin/env python3
"""GATE_LOOP_PHYSICS_1105: alpha (learning exponent) and gamma (feedback exponent) of the 0128 loop, rounds 0..10. Stdlib only."""
import json, math, os
D = "/N/scratch/bsmensah/silo/bootseed/runs"
RUNS = ["s1", "FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"]


def ols(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    res = [y - my - b * (x - mx) for x, y in zip(xs, ys)]
    se = math.sqrt(sum(r * r for r in res) / (n - 2) / sxx)
    return b, se


def mle_p(by_depth):
    best = None
    for i in range(999):
        p = 0.5 + 0.0005 * i
        if p >= 1: break
        ll = 0.0
        for d, (n, k) in by_depth.items():
            q = p ** d
            ll += k * math.log(q) + (n - k) * math.log(1 - q)
        if best is None or ll > best[0]:
            best = (ll, p)
    return best[1]


res = {"i": [], "ii": []}
for r in RUNS:
    N, E1, E2, RR, DD = [], [], [], [], []
    prevN = 256
    for t in range(11):
        s = json.load(open(os.path.join(D, r, "round_%d.json" % t)))
        sm = s["summary"]
        fs = sm.get("fixed_summary") or {}
        d50 = sm.get("d50_fixed", fs.get("d50"))
        rows = s["fixed_rows"]
        bd = {}
        for x in rows:
            n, k = bd.get(x["depth"], (0, 0)); bd[x["depth"]] = (n + 1, k + (1 if x["v"] and x["c"] else 0))
        p2 = mle_p(bd)
        p1 = 0.5 ** (1.0 / d50)
        N.append(prevN); E1.append(1 - p1); E2.append(1 - p2); DD.append(d50)
        RR.append(sm["own_new"] + sm["hindsight_new"])
        prevN = sm["train_examples"]
    print("%s N %s" % (r, N))
    print("%s d50 %s" % (r, " ".join("%.3f" % x for x in DD)))
    print("%s rows/round %s" % (r, RR))
    print("%s e(i) %s" % (r, " ".join("%.4f" % x for x in E1)))
    print("%s e(ii) %s" % (r, " ".join("%.4f" % x for x in E2)))
    g, gse = ols([math.log(x) for x in DD], [math.log(x) for x in RR])
    for tag, E in (("i", E1), ("ii", E2)):
        a, ase = ols([math.log(x) for x in N], [math.log(x) for x in E]); a = -a
        res[tag].append((a, g))
        print("%s [%s] alpha %.4f (se %.4f) gamma %.4f (se %.4f) alpha*gamma %.4f alpha*(1+gamma) %.4f" % (r, tag, a, ase, g, gse, a * g, a * (1 + g)))

for tag in ("i", "ii"):
    A = [a for a, g in res[tag]]; G = [g for a, g in res[tag]]
    AG = [a * g for a, g in res[tag]]; A1 = [a * (1 + g) for a, g in res[tag]]
    def ms(v):
        m = sum(v) / len(v); sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1)); return m, sd
    print("SUMMARY[%s] alpha %.4f +/- %.4f | gamma %.4f +/- %.4f | alpha*gamma %.4f +/- %.4f (x%.1f to reach 1) | alpha*(1+gamma) %.4f +/- %.4f (x%.2f to reach 1)"
          % ((tag,) + ms(A) + ms(G) + ms(AG) + (1 / ms(AG)[0],) + ms(A1) + (1 / ms(A1)[0],)))
ok = all(a * (1 + g) < 1 for a, g in res["ii"])
print("GATE_LOOP_PHYSICS", "CONSISTENT" if ok else "INCONSISTENT")
