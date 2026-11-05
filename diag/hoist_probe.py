"""Diagnostic (read-only, no model call, no sealed file): why did STOCK accept 0 helpers in run v2?

For each STOCK growth round, counts demo-passing solutions with top-level helpers vs helpers nested inside transform, and
measures what the registered acceptance rule (>= 2 distinct tasks, or (k - 1) x token_len >= 20) would accept if
closure-free nested defs were hoisted to top level. Uses ratchet.helpers unchanged for canonical hashing and the unbound
check, so a nested def that reads transform's locals is dropped exactly as an unbound top-level helper would be.

Usage (Quartz, venv python, PYTHONPATH=<ratchet code>): python -I diag/hoist_probe.py <run_dir> [model_dir]
"""
import ast
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ratchet import helpers as H          # noqa: E402
from ratchet.c_util import count_tokens   # noqa: E402

run = Path(sys.argv[1])
tok = None
if len(sys.argv) > 2:
    from ratchet import tok as tokmod
    tok = tokmod.load_tokenizer(Path(sys.argv[2]))


def hoisted_module(code):
    mod = H.parse_program(code)
    if mod is None:
        return None, 0
    top = [n for n in mod.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    top_names = {n.name for n in mod.body if isinstance(n, ast.FunctionDef)}
    tr = next((n for n in mod.body if isinstance(n, ast.FunctionDef) and n.name == 'transform'), None)
    nested = []
    if tr is not None:
        for node in ast.walk(tr):
            if isinstance(node, ast.FunctionDef) and node is not tr:
                nested.append(node)
    keep = [n for n in mod.body if isinstance(n, ast.FunctionDef) and n.name != 'transform']
    seen = set(top_names)
    for n in nested:
        if n.name in seen:
            continue
        seen.add(n.name)
        keep.append(n)
    src = '\n'.join(ast.unparse(x) for x in top) + '\n\n' + '\n\n'.join(ast.unparse(x) for x in keep) + '\n'
    return src, len(nested)


out = {}
for r in range(1, 9):
    d = run / 'arms' / 'STOCK' / f'round_{r}'
    if not (d / 'samples.jsonl').exists():
        break
    ex = {}
    for line in open(d / 'exec.jsonl'):
        j = json.loads(line)
        ex[j['sample_id']] = j
    c = collections.Counter()
    sols_top, sols_hoist = [], []
    for line in open(d / 'samples.jsonl'):
        j = json.loads(line)
        sid = j['sample_id']
        e = ex.get(sid, {})
        if not e.get('demo_pass'):
            continue
        task = H.parse_sample_id(sid)['task'] if hasattr(H, 'parse_sample_id') else sid.split('|')[3]
        code = j.get('code') or ''
        c['demo_pass'] += 1
        s1 = H.build_solution(sid, task, code)
        if s1 is not None:
            sols_top.append(s1)
            c['with_top_helper'] += bool(s1.helpers)
        src, n_nested = hoisted_module(code)
        c['with_nested_def'] += bool(n_nested)
        c['nested_defs'] += n_nested
        if src is None:
            continue
        raws = H.extract_helpers(src, sid, task, reachable_only=False)
        c['hoisted_valid_helpers'] += len(raws)
        sols_hoist.append((task, s1.code_sha if s1 else sid, raws))
    # registered acceptance on hoisted helpers, deduped one solution per (task, code_sha)
    best = {}
    for task, key, raws in sols_hoist:
        best.setdefault((task, key), raws)
    defs = collections.defaultdict(list)
    for (task, _), raws in best.items():
        for h in {x.hash: x for x in raws}.values():
            defs[h.hash].append((task, h))
    acc = []
    for hs, lst in defs.items():
        tasks = sorted({t for t, _ in lst})
        tl = count_tokens(lst[0][1].canonical, tok)
        gain = max(0, len(lst) - 1) * tl
        if len(tasks) >= 2 or gain >= 20:
            acc.append({'name': lst[0][1].name, 'tasks': len(tasks), 'k': len(lst), 'tokens': tl, 'gain': gain,
                        'by': 'two_tasks' if len(tasks) >= 2 else 'mdl'})
    acc.sort(key=lambda a: (-a['tasks'], -a['k']))
    c['distinct_hoisted_hashes'] = len(defs)
    c['would_accept'] = len(acc)
    c['would_accept_two_tasks'] = sum(a['by'] == 'two_tasks' for a in acc)
    out[r] = {'counts': dict(c), 'top': acc[:12]}
    print(f'ROUND {r}', json.dumps(dict(c)))
    for a in acc[:12]:
        print('   ', json.dumps(a))
dst = Path(__file__).resolve().parent / f'hoist_probe_{run.name}.json'   # never inside the registered run dir
dst.write_text(json.dumps(out, indent=1))
print('WROTE', dst)
