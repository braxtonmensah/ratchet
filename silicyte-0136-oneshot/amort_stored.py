#!/usr/bin/env python3
"""GATE_STORED_AMORT_1105: decode beam2 exec into (L, j) and read Q1/Q2/Q3 on 0128 MEAS rows, rounds 0..10. Stdlib only."""
import json, math, os, sys
D = "/N/scratch/bsmensah/silo/bootseed/runs"
RUNS = ["s1", "FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"]
NOPS, B = 54, 4


def dec(ex):
    if ex <= NOPS:
        return 1, None
    L = 2 + (ex - NOPS - 1) // (NOPS * B)
    j = (ex - NOPS - 1 - NOPS * B * (L - 2)) // NOPS
    return L, j


# lever check on dp / tr rows that store prog
tot = bad = 0
for r in RUNS[1:]:
    for t in range(11):
        s = json.load(open(os.path.join(D, r, "search_%d.json" % t)))
        for key in ("dp", "tr"):
            for x in s.get(key) or []:
                if x.get("v") and x.get("prog"):
                    tot += 1
                    L, j = dec(x["exec"])
                    if L != len(x["prog"]) or (j is not None and not 0 <= j < B):
                        bad += 1
print("LEVER decoder solved rows %d mismatches %d" % (tot, bad))
if tot == 0 or bad > 0:
    print("STOP decoder invalid"); sys.exit(3)

rows = {}   # (run, t) -> list of (tid, depth, L, j, exec)
for r in RUNS:
    for t in range(11):
        s = json.load(open(os.path.join(D, r, "round_%d.json" % t)))
        out = []
        for x in s["fixed_rows"]:
            if x["v"]:
                L, j = dec(x["exec"])
                out.append((x["tid"], x["depth"], L, j, x["exec"]))
        rows[(r, t)] = out

# fixed L weights: pooled distribution of L>=2 solves over all runs and rounds
from collections import Counter
cL = Counter(L for v in rows.values() for (_, _, L, j, _) in v if L >= 2)
W = {L: n / float(sum(cL.values())) for L, n in cL.items()}
print("L_WEIGHTS", json.dumps({str(k): round(v, 4) for k, v in sorted(W.items())}))


def q1(v):
    num = den = 0.0
    for L, w in W.items():
        sub = [j for (_, _, LL, j, _) in v if LL == L]
        if sub:
            num += w * sum(1 for j in sub if j == 0) / float(len(sub)); den += w
    return num / den if den else None


def ols(xs, ys):
    n = len(xs); mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx


slopes = []
for r in RUNS:
    q = [q1(rows[(r, t)]) for t in range(11)]
    sh = [sum(1 for (_, d, L, _, _) in rows[(r, t)] if L < d) / float(len(rows[(r, t)])) if rows[(r, t)] else None for t in range(11)]
    ts = [t for t in range(11) if q[t] is not None]
    b = ols(ts, [q[t] for t in ts])
    slopes.append(b)
    print("Q1 %s slope %+.5f per round | %s" % (r, b, " ".join("%.3f" % x if x is not None else "NA" for x in q)))
    print("Q3 %s shortcut share | %s" % (r, " ".join("%.3f" % x if x is not None else "NA" for x in sh)))
    print("N  %s solves | %s" % (r, " ".join(str(len(rows[(r, t)])) for t in range(11))))
m = sum(slopes) / len(slopes)
sd = math.sqrt(sum((b - m) ** 2 for b in slopes) / (len(slopes) - 1))
tq = m / (sd / math.sqrt(len(slopes))) if sd > 0 else float("inf")
print("Q1_SUMMARY mean slope %+.5f sd %.5f t %.3f (crit 2.353) all_positive %s" % (m, sd, tq, all(b > 0 for b in slopes)))

# Q2: paired early vs late exec at the same L
dn = up = eq = 0
per = {}
for r in RUNS:
    early, late = {}, {}
    for t in (0, 1, 2):
        for (tid, d, L, j, ex) in rows[(r, t)]:
            early.setdefault(tid, (L, ex))
    for t in (8, 9, 10):
        for (tid, d, L, j, ex) in rows[(r, t)]:
            late[tid] = (L, ex)
    a = b2 = c = 0
    for tid in early:
        if tid in late and late[tid][0] == early[tid][0]:
            if late[tid][1] < early[tid][1]: a += 1
            elif late[tid][1] > early[tid][1]: b2 += 1
            else: c += 1
    per[r] = (a, b2, c); dn += a; up += b2; eq += c
n = dn + up
# one-sided binomial p for >= dn successes of n at 0.5
p = sum(math.factorial(n) / (math.factorial(k) * math.factorial(n - k)) for k in range(dn, n + 1)) / 2.0 ** n if n else 1.0
print("Q2 per run (late<early, late>early, equal)", json.dumps(per))
print("Q2_SUMMARY late_lower %d late_higher %d equal %d one-sided p %.4g" % (dn, up, eq, p))
sig = all(b > 0 for b in slopes) and tq > 2.353 and p < 0.05
print("GATE_STORED_AMORT", "SIGNAL" if sig else "NO_SIGNAL")
