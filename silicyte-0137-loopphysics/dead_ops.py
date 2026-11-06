#!/usr/bin/env python3
"""GATE_DEAD_OPS_1105: op frequencies in 0129 ruler reference programs vs 0128 verified programs. Stdlib only."""
import json, glob, os
from collections import Counter
W = json.load(open("/N/scratch/bsmensah/arc26/fourth_law/consol_v1/world.json"))
OPS = list(W["zipf_order"]); assert len(OPS) == 54


def progs_in(obj, out):
    """collect every list-of-op-name sequence stored under a key named prog / ref / program"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("prog", "ref", "program", "ref_prog") and isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                out.append(v)
            else:
                progs_in(v, out)
    elif isinstance(obj, list):
        for v in obj:
            progs_in(v, out)


ref = []
for f in sorted(glob.glob("/N/scratch/bsmensah/silo/open0129/frozen/RULER_49[1-4]00.json")):
    progs_in(json.load(open(f)), ref)
cref = Counter(o for p in ref for o in p)
sol = []
for r in ("FRONTIER_s2", "FRONTIER_s3", "FRONTIER_s4"):
    for t in range(11):
        s = json.load(open("/N/scratch/bsmensah/silo/bootseed/runs/%s/search_%d.json" % (r, t)))
        for k in ("dp", "tr"):
            for x in s.get(k) or []:
                if x.get("v") and x.get("prog"):
                    sol.append(x["prog"])
csol = Counter(o for p in sol for o in p)
print("ruler reference programs", len(ref), "ops", sum(cref.values()), "| verified 0128 programs", len(sol), "ops", sum(csol.values()))
unk = sorted(set(cref) | set(csol) - set(OPS))
print("names not in world ops:", unk[:10])
dead = [o for o in OPS if cref[o] == 0 and csol[o] == 0]
hard = [o for o in OPS if cref[o] > 0 and csol[o] == 0]
never_ref = [o for o in OPS if cref[o] == 0]
print("DEAD (in neither):", len(dead), dead)
print("HARD (in references, never solved with):", len(hard), [(o, cref[o]) for o in hard])
print("never in any ruler reference:", len(never_ref), never_ref)
print("in solutions but never in references:", [(o, csol[o]) for o in OPS if cref[o] == 0 and csol[o] > 0])
print("share of a beam step's 54 executions spent on DEAD ops: %.3f" % (len(dead) / 54.0))
print("GATE_DEAD_OPS", "DEAD_OPS" if dead else ("HARD_OPS_ONLY" if hard else "NONE"))
