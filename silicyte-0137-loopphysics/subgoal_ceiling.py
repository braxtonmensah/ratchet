#!/usr/bin/env python3
"""GATE_SUBGOAL_CEILING_1105: s_d vs s_{d/2}^2 on pooled 0128 MEAS rows, rounds 0, 5, 10. Stdlib only."""
import json, os
D = "/N/scratch/bsmensah/silo/bootseed/runs"
RUNS = ["s1", "FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"]


def cross(pts):
    """pts: list of (d, share) with d increasing; first d where share falls below 0.5, linearly interpolated."""
    for (d0, s0), (d1, s1) in zip(pts, pts[1:]):
        if s0 >= 0.5 > s1:
            return d0 + (s0 - 0.5) / (s0 - s1) * (d1 - d0)
    return None if pts[0][1] < 0.5 else float(pts[-1][0])


res = {}
for t in (0, 5, 10):
    cnt = {}
    for r in RUNS:
        for x in json.load(open(os.path.join(D, r, "round_%d.json" % t)))["fixed_rows"]:
            n, k = cnt.get(x["depth"], (0, 0)); cnt[x["depth"]] = (n + 1, k + (1 if x["v"] and x["c"] else 0))
    s = {d: (k + 0.5) / (n + 1.0) for d, (n, k) in cnt.items()}
    act = cross([(d, s[d]) for d in range(1, 11)])
    orc = cross([(d, s[d // 2] ** 2) for d in range(2, 11, 2)])
    res[t] = (act, orc)
    print("round %d | " % t + " ".join("d%d s %.3f oracle %.3f" % (d, s[d], s[d // 2] ** 2) for d in (4, 6, 8, 10))
          + " | crossing actual %s oracle %s" % (("%.2f" % act) if act else "NA", ("%.2f" % orc) if orc else "NA"))
a, o = res[10]
ratio = (o / a) if (a and o) else None
print("ROUND10 oracle/actual crossing ratio", ("%.3f" % ratio) if ratio else "NA")
print("GATE_SUBGOAL_CEILING", "WORTH_BUILDING" if ratio and ratio >= 1.5 else "SMALL")
