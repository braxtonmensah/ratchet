#!/usr/bin/env python3
"""GATE_LOOP_PHYSICS_OOS_1105: fit the two-exponent law on rounds 0..5, forecast d50 at rounds 6..10, vs linear extrapolation."""
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


tot_law = tot_lin = 0.0; wins = 0
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
    fit = range(6)
    na, la = ols([math.log(N[t]) for t in fit], [math.log(E[t]) for t in fit]); alpha, A = -na, math.exp(la)
    g, lb = ols([math.log(Y[t]) for t in fit], [math.log(R[t]) for t in fit]); B = math.exp(lb)
    # e(ii) -> d50 on the registered logistic scale: calibrate by the fit-window mean ratio of logistic d50 to geometric d50
    geo = lambda e: math.log(0.5) / math.log(1 - e)
    cal = sum(Y[t] / geo(E[t]) for t in fit) / 6.0
    n = N[5]; pred = {}
    for t in range(5, 11):
        d = cal * geo(A * n ** (-alpha))
        pred[t] = d
        n = n + B * d ** g
    lb_, la_ = ols(list(fit), [Y[t] for t in fit])
    lin = {t: la_ + lb_ * t for t in range(6, 11)}
    mae_law = sum(abs(pred[t] - Y[t]) for t in range(6, 11)) / 5.0
    mae_lin = sum(abs(lin[t] - Y[t]) for t in range(6, 11)) / 5.0
    tot_law += mae_law; tot_lin += mae_lin; wins += mae_law < mae_lin
    print("%s fit alpha %.4f gamma %.4f cal %.3f | actual %s | law %s | linear %s | MAE law %.3f linear %.3f"
          % (r, alpha, g, cal, " ".join("%.2f" % Y[t] for t in range(6, 11)), " ".join("%.2f" % pred[t] for t in range(6, 11)),
             " ".join("%.2f" % lin[t] for t in range(6, 11)), mae_law, mae_lin))
print("OOS_SUMMARY pooled MAE law %.3f linear %.3f, law wins %d of 4" % (tot_law / 4, tot_lin / 4, wins))
print("GATE_LOOP_PHYSICS_OOS", "PREDICTS" if wins >= 3 and tot_law < tot_lin else "DESCRIBES_ONLY")
