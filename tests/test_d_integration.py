"""Builder D integration: D's drivers on the REAL A, B and C modules (arc_io on a temp data root, prompt, StubLLM,
ledger, sandbox subprocesses, extract, helpers, library, exemplar, sham, plant, select, perturb), CPU only.

Runs the PLAN from growth through library freeze, sealed and perturbed sampling, FLAT token match and the
submission freeze, and stops at the first key read (score gate). Then re-runs step and checks nothing is re-issued.
Skips if a module of another builder is missing.
"""
from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import tempfile
import time
import unittest
from pathlib import Path

NEEDED = ('arc_io', 'sandbox', 'select', 'perturb', 'types', 'tok', 'llm', 'ledger', 'prompt', 'extract', 'helpers',
          'library', 'sham', 'exemplar', 'plant')
MISSING = []
for _m in NEEDED:
    try:
        importlib.import_module('ratchet.' + _m)
    except Exception as e:  # noqa: BLE001
        MISSING.append('%s (%s)' % (_m, type(e).__name__))

from ratchet import arms, guard, rounds  # noqa: E402
from ratchet.arms import Deadline  # noqa: E402

IDENT = '''Here is the program.
```python
def copy_grid(g):
    return [list(r) for r in g]


def transform(grid):
    return copy_grid(grid)
```
'''
FLIP = '''```python
def flip_rows(g):
    return [list(reversed(r)) for r in g]


def transform(grid):
    return flip_rows(grid)
```
'''
USE_LIB = '''```python
def transform(grid):
    return copy_grid(grid)
```
'''
BAD = '''```python
def paint(g):
    return [[0 for _ in r] for r in g]


def transform(grid):
    return paint(grid)
```
'''
BAD2 = '''```python
def upend_rows(g):
    return [list(r) for r in reversed(g)]


def transform(grid):
    return upend_rows(grid)
```
'''
BAD3 = '''```python
def tup_grid(g):
    return [tuple(r) for r in g]


def transform(grid):
    return tup_grid(grid)[::-1]
```
'''
NONE = 'I am not sure about this one.'
FIXTURES = [IDENT, FLIP, USE_LIB, BAD, NONE, IDENT, BAD2, BAD3, FLIP]


def _task(inp, out_fn):
    pairs = [{'input': g, 'output': out_fn(g)} for g in inp]
    return pairs


def _ident(g):
    return [list(r) for r in g]


def _flip(g):
    return [list(reversed(r)) for r in g]


GRIDS = [[[1, 2], [3, 4]], [[5, 0, 1], [2, 2, 3]], [[7, 8, 9]], [[1], [2]]]


@unittest.skipIf(MISSING, 'modules missing: %s' % MISSING)
class TestIntegrationReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='ratchet_di_'))
        data = cls.tmp / 'data'
        for split, ids in (('growth', ['a0', 'a1', 'a2', 'b0', 'b1', 'b2']), ('sealed', ['s0', 's1', 's2', 's3'])):
            (data / split).mkdir(parents=True)
            for i, tid in enumerate(ids):
                fn = _ident if (tid[0] in 'a' or tid in ('s0', 's1')) else _flip
                grids = GRIDS[i % 2:] + GRIDS[:i % 2]
                train = _task(grids[:3], fn)
                test = [{'input': grids[3], 'output': fn(grids[3])}]
                if split == 'sealed':
                    test = [{'input': grids[3]}]
                (data / split / ('%s.json' % tid)).write_text(json.dumps({'train': train, 'test': test}))
        cls.old_env = os.environ.get('RATCHET_DATA_ROOT')
        os.environ['RATCHET_DATA_ROOT'] = str(data)
        guard.add_data_root(data)
        dsl = cls.tmp / 'arc-dsl'
        dsl.mkdir()
        from test_c_sham_exemplar_plant import write_dsl
        write_dsl(dsl)
        cls.run_dir = cls.tmp / 'runs' / 'v1'
        arms.init_run(cls.run_dir, S=2, R=2, skip_pilot=True, auto_ack=True, model=str(cls.tmp / 'nomodel'),
                      arcdsl_dir=str(dsl), exec_workers=4)
        from ratchet import tok as tokmod
        cls.tok = tokmod.StubTokenizer()

    @classmethod
    def tearDownClass(cls):
        if cls.old_env is None:
            os.environ.pop('RATCHET_DATA_ROOT', None)
        else:
            os.environ['RATCHET_DATA_ROOT'] = cls.old_env
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _step(self, job: str):
        from ratchet import ledger, llm
        run = arms.load_run(self.run_dir, kit=arms.LazyKit(tok=self.tok))
        run.job_id = job
        led = ledger.Ledger(rounds.ledger_dir(run) / ('ledger_%s.jsonl' % job))
        client = llm.StubLLM(FIXTURES, led, self.tok, gen_tokens=None)
        try:
            arms.step(run, client, Deadline(time.time()))   # the real client compares with wall-clock time
        finally:
            if hasattr(led, 'close'):
                led.close()
        return run, client

    def test_plan_to_first_key_read(self):
        run, client = self._step('i1')
        u = rounds.next_unit(arms.load_run(self.run_dir))
        self.assertEqual((u.kind, u.condition), ('score_gate', 'primary'))
        d = self.run_dir
        st1 = rounds.load_state(d / 'arms' / 'STOCK' / 'round_1')
        st2 = rounds.load_state(d / 'arms' / 'STOCK' / 'round_2')
        self.assertEqual(st1['state'], 'FROZEN')
        self.assertGreater(st1['demo_pass_tasks'], 0)
        L1 = json.loads((d / st1['library_json']).read_text())
        names = {h['name'] for h in L1['helpers']}
        self.assertIn('copy_grid', names, 'a helper used by 2 or more growth tasks must be accepted in round 1')
        self.assertEqual(st2['library_in'], st1['library_out'])
        # sandbox rows for every sample, and growth rows carry test_correct
        for r in (1, 2):
            rd = d / 'arms' / 'STOCK' / ('round_%d' % r)
            s = rounds.read_rows(rd / 'samples.jsonl', 'sample_id')
            e = rounds.read_rows(rd / 'exec.jsonl', 'sample_id')
            self.assertEqual(set(s), set(e))
            self.assertEqual(len(s), 6 * 2)
            self.assertTrue(all('test_correct' in x for x in e.values()))
        # a program that calls the library helper passes only when the helper is callable (round 2 has L_1)
        e2 = rounds.read_rows(d / 'arms' / 'STOCK' / 'round_2' / 'exec.jsonl', 'sample_id')
        s2 = rounds.read_rows(d / 'arms' / 'STOCK' / 'round_2' / 'samples.jsonl', 'sample_id')
        uses = [sid for sid, row in s2.items() if row['code'] and 'def copy_grid' not in row['code']
                and 'copy_grid' in row['code'] and row['task'].startswith('a')]
        for sid in uses:
            self.assertTrue(e2[sid]['demo_pass'], sid)
        # sealed submissions for every arm and seed, FLAT extra matched to STOCK's tokens
        fz = json.loads((d / 'freeze' / 'SUBMIT_FREEZE.json').read_text())
        self.assertEqual(len(fz['submissions']), 3 * 8 + 3 * 2)
        for k in (1, 2, 3):
            fb = json.loads((d / 'sealed' / 'sealed' / 'FLATTTC' / ('seed_%d' % k) / 'flat_budget.json').read_text())
            self.assertGreater(fb['n_extra'], 0)
            st = rounds.load_state(d / 'sealed' / 'sealed' / 'FLATTTC' / ('seed_%d' % k))
            self.assertGreaterEqual(st['realized']['extra'], fb['target_tokens'] * 0.5)
            subs = json.loads((d / 'sealed' / 'sealed' / 'STOCK' / ('seed_%d' % k) / 'submissions.json').read_text())
            self.assertEqual(subs['n_tasks'], 4)
        # sealed exec rows never carry test_correct; sealed samples never reach a library
        for p in (d / 'sealed').rglob('exec.jsonl'):
            self.assertFalse([r for r in rounds.iter_jsonl(p) if 'test_correct' in r], str(p))
        # ledger rows: one per request, schema-valid (B validates on append), library tokens counted
        from ratchet import ledger
        rows = list(ledger.iter_rows(d))
        self.assertTrue(rows)
        self.assertTrue(any(r['library_tokens'] > 0 for r in rows if r['arm'] == 'STOCK' and r['phase'] == 'sealed'))
        # lever markers in per-arm server logs
        logs = '\n'.join(p.read_text() for p in (d / 'logs').glob('server_*.log'))
        # STOCK marker (review fix 2026-11-04): updated=1 only if L_R's in-context helper set differs from L_1's (it
        # compared shas, which always differ between rounds); the growth r = 2 line is 0 by construction (L_1 = L_1)
        fz = json.loads((d / 'freeze' / 'FREEZE.json').read_text())

        def ctx(rel):
            return {h['hash'] for h in json.loads((d / rel).read_text())['helpers'] if h.get('in_context')}
        lr, l1 = ctx(fz['libraries']['STOCK']['json']), ctx(fz['libraries']['STATIC']['json'])
        want = int(bool(lr) and lr != l1)
        self.assertRegex(logs, r'LEVER STOCK library r=2 sha=\w+ updated=%d helpers_in_context=\d+' % want)
        self.assertRegex(logs, r'LEVER STOCK library r=2 sha=\w+ updated=0 ')
        print('D_INTEGRATION stock_updated=%d L_R_ctx=%d L_1_ctx=%d' % (want, len(lr), len(l1)))
        for rx in (r'LEVER STATIC library r=\d+ sha=\w+ frozen=1',
                   r'LEVER ONESHOT round=1 slots_per_task=4', r'LEVER PLANTDRIP tranche=\d+ of \d+ primitives=\d+',
                   r'LEVER PLANTL1 tranche=1 primitives=\d+', r'LEVER SHAM matched=\d+ of \d+ tokens=\d+ target=\d+',
                   r'LEVER FLATTTC seed=\d extra=\d+ target_tokens=\d+ realized_tokens=\d+',
                   r'LEVER PERTURB seed=\d+ tasks=4', r'LEVER SANDBOX lib_sha=\w+ helpers_callable=\d+ net=(unshare|audit)',
                   r'LEVER NOTHINK first_response_has_think=0'):
            self.assertRegex(logs, rx)
        # idempotent: a second job re-issues nothing and changes no frozen file
        before = {p: p.read_bytes() for p in d.rglob('*') if p.is_file() and p.suffix in ('.json', '.py')
                  and 'jobs' not in p.parts and p.name not in ('STATUS.json', 'round_state.json')}
        n_rows = len(rows)
        run2, client2 = self._step('i2')
        self.assertEqual(len(list(ledger.iter_rows(d))), n_rows)
        after = {p: p.read_bytes() for p in before}
        self.assertEqual([str(p) for p in before if before[p] != after[p]], [])


if __name__ == '__main__':
    unittest.main()
