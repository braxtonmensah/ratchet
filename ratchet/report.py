"""Byte, token and second map (SPEC 10, rule 7) and the per-arm per-round demo-pass / test-correct tables (PREREG 5).

Reads only loop data (ledger, samples, exec rows, libraries, job STATUS) and scores/ booleans. Growth test-correct comes
from exec rows' test_correct (public growth outputs); sealed test-correct comes only from scores/ (score_sealed.py).
"""
from __future__ import annotations

import ast
import glob
import os
from collections import defaultdict
from pathlib import Path

from .e_util import cfg, iter_jsonl, read_json, task_of_sample
from .pilot import ledger_rows

STATUSES = ('OK', 'NO_CODE', 'SYNTAX', 'DEMO_FAIL', 'TIMEOUT', 'ERROR', 'BAD_OUTPUT')


def _where(run_dir: Path, p: str) -> tuple[str, str, str]:
    """(arm, phase, slot) of an exec/samples file from its directory (SPEC 7)."""
    parts = Path(p).relative_to(run_dir).parts
    if parts[0] == 'arms':
        return parts[1], 'growth', parts[2]
    if parts[0] == 'pilot':
        return parts[1], 'pilot', ''
    if parts[0] == 'sealed':
        return parts[2], parts[1], parts[3]
    if parts[0] == 'knockout':
        return 'STOCK', 'knockout_' + parts[1], parts[2]
    return '?', parts[0], ''


def _files(run_dir: Path, name: str) -> list[str]:
    pats = [f'arms/*/round_*/{name}', f'pilot/*/{name}', f'sealed/*/*/seed_*/{name}', f'knockout/*/seed_*/{name}']
    out = []
    for p in pats:
        out += sorted(glob.glob(os.path.join(str(run_dir), p)))
    return out


def _defs(code: str) -> set[str]:
    try:
        mod = ast.parse(code or '')
    except (SyntaxError, ValueError):
        return set()
    return {n.name for n in mod.body if isinstance(n, ast.FunctionDef) and n.name != 'transform'}


def _library_index(run_dir: Path) -> dict[str, dict]:
    """lib sha -> {'names': in-context helper names, 'all': every helper, 'arm', 'round'}."""
    idx = {}
    for p in sorted(glob.glob(os.path.join(str(run_dir), 'arms', '**', 'L_*.json'), recursive=True)):
        d = read_json(p, {}) or {}
        s = d.get('sha256')
        if not s:
            continue
        hs = d.get('helpers', [])
        idx[s] = {'names': {h['name'] for h in hs if h.get('in_context')}, 'all': hs,
                  'arm': d.get('arm'), 'round': d.get('round'), 'path': p}
    return idx


def byte_map(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    tok = defaultdict(lambda: defaultdict(float))
    for r in ledger_rows(run_dir, None):
        k = (r.get('arm', '?'), r.get('phase', '?'))
        t = tok[k]
        n = int(r.get('n') or 1)
        t['requests'] += 1
        t['samples'] += n
        t['prompt'] += r.get('prompt_tokens') or 0
        t['prompt_logical'] += r.get('prompt_tokens_logical') or (r.get('prompt_tokens') or 0) * n
        t['cached'] += r.get('cached_prompt_tokens') or 0
        for f in ('instruction_tokens', 'task_tokens', 'library_tokens', 'exemplar_tokens'):
            t[f] += (r.get(f) or 0) * n
        t['gen'] += r.get('gen_tokens') or 0
        t['truncated'] += sum(1 for x in (r.get('finish_reasons') or []) if x == 'length')
        t['latency_s'] += r.get('latency_s') or 0
    ex = defaultdict(lambda: defaultdict(float))
    libidx = _library_index(run_dir)
    sample_lib: dict[str, tuple[str | None, str]] = {}
    for p in _files(run_dir, 'samples.jsonl'):
        for r in iter_jsonl(p):
            sample_lib[r.get('sample_id', '')] = (r.get('lib_sha'), r.get('code') or '')
    later_calls: dict[str, int] = defaultdict(int)
    for p in _files(run_dir, 'exec.jsonl'):
        arm, phase, slot = _where(run_dir, p)
        e = ex[(arm, phase)]
        for r in iter_jsonl(p):
            e['rows'] += 1
            st = r.get('status', '?')
            e['status_' + st] += 1
            e['demo_pass'] += bool(r.get('demo_pass'))
            e['timeouts'] += int(r.get('timeouts') or 0)
            e['cpu_s'] += sum(float(x) for x in (r.get('wall_s') or []))
            e['cache_hit'] += bool(r.get('cache_hit'))
            if r.get('test_correct'):
                e['test_correct_samples'] += 1
            err = str(r.get('error') or '')
            if st == 'BAD_OUTPUT' or err.startswith('BAD_OUTPUT'):
                e['out_of_domain'] += 1
            if err.startswith('AGG_KILL'):          # whole-program hard kill or RLIMIT_CPU (sandbox review fix)
                e['agg_kill'] += 1
            if err == 'LIB_TIMEOUT':
                e['lib_timeout'] += 1
            lib_sha, code = sample_lib.get(r.get('sample_id', ''), (None, ''))
            if lib_sha and lib_sha in libidx and (_defs(code) & libidx[lib_sha]['names']):
                e['redefines_library_helper'] += 1
            if arm == 'STOCK':
                rnd = int(slot.split('_')[1]) if slot.startswith('round_') else 10 ** 6
                for k, v in (r.get('helper_calls') or {}).items():
                    if int(v) > 0:
                        later_calls[f'{k}@{rnd}'] += 1
    # rule 3: accepted STOCK helpers never called by any later program (later growth round or any sealed STOCK run)
    never = []
    stock_libs = [v for v in libidx.values() if v['arm'] == 'STOCK']
    if stock_libs:
        last = max(stock_libs, key=lambda v: v['round'] or 0)
        for h in last['all']:
            fr = h.get('first_round') or 0
            called = any(int(key.rsplit('@', 1)[1]) > fr and key.rsplit('@', 1)[0] == h['name'] for key in later_calls)
            if not called:
                never.append(h['name'])
    jobs = {}
    for p in sorted(glob.glob(os.path.join(str(run_dir), 'jobs', '*', 'STATUS.json'))):
        st = read_json(p, {}) or {}
        jobs[Path(p).parent.name] = {'state': st.get('state'), 'meta': st.get('meta'),
                                     'seconds': st.get('seconds') or {}, 'gen_tok_per_s': st.get('gen_tok_per_s'),
                                     'prefix_cache_hit_rate': st.get('prefix_cache_hit_rate')}
    keys = sorted(set(tok) | set(ex))
    rows = []
    for k in keys:
        t, e = tok.get(k, {}), ex.get(k, {})
        rows.append({'arm': k[0], 'phase': k[1], **{f'tok_{a}': b for a, b in t.items()},
                     **{f'exec_{a}': b for a, b in e.items()}})
    return {'rows': rows, 'jobs': jobs, 'helpers_never_called_later': never,
            'n_stock_final_helpers': len(max(stock_libs, key=lambda v: v['round'] or 0)['all']) if stock_libs else 0}


def growth_table(run_dir: Path) -> list[dict]:
    """Per growth arm and round: samples, demo-pass samples, demo-pass tasks, tasks with any test-correct sample, and
    pass@2 test-correct tasks when builder A's select is importable."""
    run_dir = Path(run_dir)
    out = []
    for p in sorted(glob.glob(os.path.join(str(run_dir), 'arms', '*', 'round_*', 'exec.jsonl'))):
        arm, _, slot = _where(run_dir, p)
        rows = list(iter_jsonl(p))
        tasks = {r.get('task') or task_of_sample(r.get('sample_id', '')) for r in rows}
        dp = {r.get('task') or task_of_sample(r['sample_id']) for r in rows if r.get('demo_pass')}
        tc = {r.get('task') or task_of_sample(r['sample_id']) for r in rows if r.get('test_correct')}
        out.append({'arm': arm, 'round': int(slot.split('_')[1]), 'samples': len(rows),
                    'demo_pass_samples': sum(bool(r.get('demo_pass')) for r in rows), 'tasks': len(tasks),
                    'demo_pass_tasks': len(dp), 'any_test_correct_tasks': len(tc),
                    'pass2_test_correct_tasks': _pass2_count(Path(p).parent, rows)})
    return sorted(out, key=lambda r: (r['arm'], r['round']))


def _pass2_count(d: Path, rows: list[dict]) -> int | None:
    try:
        from .select import pass2, candidate_from_exec
        from .types import ExecResult
        from . import arc_io
    except Exception:
        return None
    code_len = {r['sample_id']: len(r.get('code') or '') for r in iter_jsonl(d / 'samples.jsonl')}
    by = defaultdict(list)
    for r in rows:
        er = ExecResult.from_row(r)
        by[r.get('task') or task_of_sample(r['sample_id'])].append(candidate_from_exec(er, code_len.get(er.sample_id, 0)))
    n = 0
    try:
        for t, cands in by.items():
            sub = pass2(t, cands)
            task = arc_io.load_task(t, 'growth')
            n += any(tuple(a.outputs) == tuple(task.test_outputs) for a in sub.attempts)
    except Exception:
        return None
    return n


def sealed_demo_pass(run_dir: Path, cond: str, arm: str) -> dict[str, int]:
    """Seed -> sealed tasks with at least one demo-passing sample, from the loop's own sealed exec rows (no key; PREREG 5
    reports demo-pass and test-correct separately; review fix 2026-11-04)."""
    if cond.startswith('knockout_'):
        pat = os.path.join(str(run_dir), 'knockout', cond[len('knockout_'):], 'seed_*')
    else:
        pat = os.path.join(str(run_dir), 'sealed', cond, arm, 'seed_*')
    out = {}
    for d in sorted(glob.glob(pat)):
        k = Path(d).name.split('_', 1)[1]
        task = {r.get('sample_id'): r.get('task') for r in iter_jsonl(Path(d) / 'samples.jsonl')}
        out[k] = len({task.get(r.get('sample_id')) or task_of_sample(r.get('sample_id', ''))
                      for r in iter_jsonl(Path(d) / 'exec.jsonl') if r.get('demo_pass')})
    return out


def sealed_table(run_dir: Path) -> list[dict]:
    """Per condition and arm: solved (2 of 3 seeds) and per-seed correct counts, from scores/solved_*.json only; per-seed
    demo-pass tasks from the loop's sealed exec rows."""
    out = []
    for name in ('primary', 'knockout', 'arcagi2'):
        d = read_json(Path(run_dir) / 'scores' / f'solved_{name}.json', None)
        if not d:
            continue
        per = d.get('per_seed', {})
        if name == 'arcagi2':
            per = {'arcagi2': per}
        for cond, arms in per.items():
            for arm, seeds in arms.items():
                solved = len((d.get('solved', {}).get(cond, {}) or {}).get(arm, []))
                out.append({'condition': cond, 'arm': arm, 'solved_2of3': solved,
                            'per_seed_correct': {k: sum(bool(v) for v in m.values()) for k, m in seeds.items()},
                            'per_seed_demo_pass': sealed_demo_pass(run_dir, cond, arm),
                            'n_tasks': max((len(m) for m in seeds.values()), default=0)})
    return out


def _n(x) -> str:
    if isinstance(x, float):
        return f'{x:,.0f}' if x == int(x) else f'{x:,.2f}'
    return f'{x:,}' if isinstance(x, int) else str(x)


def render_map(run_dir: Path) -> str:
    m = byte_map(run_dir)
    L = ['## Byte, token and second map', '',
         '| arm | phase | requests | samples | prompt | logical prompt | instr | task | library | exemplar | cached share '
         '| gen | truncated share | exec rows | no code | syntax | demo-pass | timeouts | exec cpu s | out of domain '
         '| redefines lib helper | agg kills | lib timeouts |',
         '|' + '---|' * 23]
    for r in m['rows']:
        pr = r.get('tok_prompt', 0) or 0
        smp = r.get('tok_samples', 0) or 0
        rows = r.get('exec_rows', 0) or 0
        L.append('| ' + ' | '.join(_n(x) for x in [
            r['arm'], r['phase'], r.get('tok_requests', 0), smp, pr, r.get('tok_prompt_logical', 0),
            r.get('tok_instruction_tokens', 0), r.get('tok_task_tokens', 0), r.get('tok_library_tokens', 0),
            r.get('tok_exemplar_tokens', 0), f'{(r.get("tok_cached", 0) / pr):.4f}' if pr else 'n/a',
            r.get('tok_gen', 0), f'{(r.get("tok_truncated", 0) / smp):.4f}' if smp else 'n/a', rows,
            r.get('exec_status_NO_CODE', 0), r.get('exec_status_SYNTAX', 0), r.get('exec_demo_pass', 0),
            r.get('exec_timeouts', 0), f'{r.get("exec_cpu_s", 0):.1f}', r.get('exec_out_of_domain', 0),
            r.get('exec_redefines_library_helper', 0), r.get('exec_agg_kill', 0), r.get('exec_lib_timeout', 0)]) + ' |')
    L += ['', f'Rule 3 counters: accepted STOCK helpers never called by a later program: '
              f'{len(m["helpers_never_called_later"])} of {m["n_stock_final_helpers"]}.', '',
          '| job | state | vLLM startup s | sampling s | exec only s | drain s | idle s | gen tok/s | prefix hit |',
          '|---|---|---|---|---|---|---|---|---|']
    for j, s in sorted(m['jobs'].items()):
        sec = s['seconds']
        L.append(f'| {j} | {s["state"]} | {sec.get("vllm_startup", "")} | {sec.get("sampling", "")} | '
                 f'{sec.get("exec_only", "")} | {sec.get("drain", "")} | {sec.get("idle", "")} | '
                 f'{s.get("gen_tok_per_s")} | {s.get("prefix_cache_hit_rate")} |')
    return '\n'.join(L) + '\n'


def render_tables(run_dir: Path) -> str:
    L = ['## Growth: demo-pass and test-correct by arm and round', '',
         '| arm | round | samples | demo-pass samples | tasks | demo-pass tasks | any test-correct tasks | pass@2 test-correct tasks |',
         '|---|---|---|---|---|---|---|---|']
    for r in growth_table(run_dir):
        L.append(f'| {r["arm"]} | {r["round"]} | {r["samples"]} | {r["demo_pass_samples"]} | {r["tasks"]} | '
                 f'{r["demo_pass_tasks"]} | {r["any_test_correct_tasks"]} | '
                 f'{"n/a" if r["pass2_test_correct_tasks"] is None else r["pass2_test_correct_tasks"]} |')
    L += ['', '## Sealed: solved (2 of 3 seeds) and per-seed correct', '',
          '| condition | arm | solved | per-seed correct | per-seed demo-pass tasks | tasks |', '|---|---|---|---|---|---|']
    for r in sealed_table(run_dir):
        ps = ', '.join(f'seed {k}: {v}' for k, v in sorted(r['per_seed_correct'].items()))
        dp = ', '.join(f'seed {k}: {v}' for k, v in sorted(r.get('per_seed_demo_pass', {}).items())) or 'n/a'
        L.append(f'| {r["condition"]} | {r["arm"]} | {r["solved_2of3"]} | {ps} | {dp} | {r["n_tasks"]} |')
    return '\n'.join(L) + '\n'
