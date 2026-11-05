"""Integration end-to-end (lead's integration pass, 2026-11-04): a 5-task GROWTH-only dry run, CPU only, stub LLM.

Drives the real job entry `arms.step` (every builder's real module: arc_io, guard, prompt, StubLLM, ledger, sandbox
subprocesses, extract, helpers, library) over a plan restricted to
  FLAT round 1 = pilot FLAT_A, FLAT round 2 = pilot FLAT_B (no library, the PREREG 7.1 A/A on growth tasks),
  STOCK growth round 1 and round 2 (round 2 sees L_1 in context, callable),
with S = 2 samples per task per round. FLAT-TTC does no growth sampling in the registered design (SPEC 13 I5); its only
growth-task rounds are the two pilot FLAT rounds, so those are the FLAT rounds here.

Checks:
  1. token ledger totals equal an independent recount within 5%: gen tokens re-counted from every sample text, logical
     prompt tokens re-counted by rebuilding every prompt from the frozen library files on disk; job STATUS.json token
     counters and the top-level STATUS.json ledger totals agree with the ledger;
  2. STATUS.json (job and top level) and the META line (stdout first line, first line of every server log) appear;
  3. no code path opens the key: an audit spy records every open/listdir/scandir path in this process during the run
     (positive control: it does see the growth task reads), none lies under the fake key or the real KEY_ROOT, and the
     guard refuses open, listdir and the loader on the fake key;
  4. the library JSON round-trips: load verifies sha256, a re-save writes byte-identical JSON and .py, L_2 parents L_1,
     and L_1 is non-empty (an empty library would make the round trip vacuous);
  5. a second job re-issues nothing and changes no frozen file.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ratchet import arms, guard, rounds
from ratchet.arms import Deadline
from ratchet.rounds import WorkUnit

# ---------------------------------------------------------------------------------------------------------------------
# audit spy (Python cannot remove a hook, so it is gated by a flag and installed once per process)

_SPY = {'on': False, 'paths': []}
_SPY_EVENTS = ('open', 'os.listdir', 'os.scandir')


def _spy(event, args):
    if not _SPY['on'] or event not in _SPY_EVENTS or not args:
        return
    a = args[0]
    if isinstance(a, (str, bytes, os.PathLike)):
        _SPY['paths'].append(a)


sys.addaudithook(_spy)

# ---------------------------------------------------------------------------------------------------------------------
# fixtures: 3 identity tasks, 2 flip tasks; copy_grid is used by 2 or more tasks so STOCK round 1 accepts it

IDENT = 'Program:\n```python\ndef copy_grid(g):\n    return [list(r) for r in g]\n\n\ndef transform(grid):\n' \
        '    return copy_grid(grid)\n```\n'
FLIP = '```python\ndef flip_rows(g):\n    return [list(reversed(r)) for r in g]\n\n\ndef transform(grid):\n' \
       '    return flip_rows(grid)\n```\n'
USE_LIB = '```python\ndef transform(grid):\n    return copy_grid(grid)\n```\n'
BAD = '```python\ndef paint(g):\n    return [[0 for _ in r] for r in g]\n\n\ndef transform(grid):\n' \
      '    return paint(grid)\n```\n'
NONE = 'I am not sure about this one.'
FIXTURES = [IDENT, FLIP, USE_LIB, BAD, NONE, IDENT, FLIP]
GRIDS = [[[1, 2], [3, 4]], [[5, 0, 1], [2, 2, 3]], [[7, 8, 9]], [[1], [2]]]
TASKS = {'e2e0': 'ident', 'e2e1': 'ident', 'e2e2': 'ident', 'e2e3': 'flip', 'e2e4': 'flip'}
S = 2
STUB_PLAN = [WorkUnit('pilot', 'FLAT_A', 'pilot', None, None, 'FLAT_A'),
             WorkUnit('pilot', 'FLAT_B', 'pilot', None, None, 'FLAT_B'),
             WorkUnit('grow', 'STOCK', 'growth', 1),
             WorkUnit('grow', 'STOCK', 'growth', 2)]


def _fn(kind):
    if kind == 'ident':
        return lambda g: [list(r) for r in g]
    return lambda g: [list(reversed(r)) for r in g]


def _within(a: float, b: float, frac: float = 0.05) -> bool:
    return abs(a - b) <= frac * max(abs(a), abs(b), 1)


class TestE2EGrowthDryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='ratchet_e2e_'))
        data = cls.tmp / 'data'
        (data / 'growth').mkdir(parents=True)
        for i, (tid, kind) in enumerate(sorted(TASKS.items())):
            f = _fn(kind)
            grids = GRIDS[i % 2:] + GRIDS[:i % 2]
            body = {'train': [{'input': g, 'output': f(g)} for g in grids[:3]],
                    'test': [{'input': grids[3], 'output': f(grids[3])}]}
            (data / 'growth' / ('%s.json' % tid)).write_text(json.dumps(body))
        # fake key: files written and set to mode 000 BEFORE the root is protected (the hook refuses chmod after)
        cls.key = cls.tmp / 'key'
        (cls.key / 'arcagi1').mkdir(parents=True)
        cls.key_file = cls.key / 'arcagi1' / 'e2e0.json'
        cls.key_file.write_text('{"id": "e2e0", "test_outputs": [[[1]]]}')
        os.chmod(cls.key_file, 0)
        os.chmod(cls.key, 0o700)
        guard.add_protected_root(cls.key)
        cls.old_env = os.environ.get('RATCHET_DATA_ROOT')
        os.environ['RATCHET_DATA_ROOT'] = str(data)
        guard.add_data_root(data)
        cls.data = data
        cls.run_dir = cls.tmp / 'runs' / 'e2e'
        arms.init_run(cls.run_dir, S=S, R=2, skip_pilot=True, model=str(cls.tmp / 'nomodel'), exec_workers=2,
                      pilot_n=len(TASKS), s_pilot=S)
        from ratchet import tok as tokmod
        cls.tok = tokmod.StubTokenizer()
        cls.out1, cls.client1 = cls._step('e2e_j1')
        cls.paths1 = list(_SPY['paths'])
        cls.frozen1 = cls._frozen_bytes()
        cls.ledger_rows1 = cls._ledger_line_count()
        cls.out2, cls.client2 = cls._step('e2e_j2')

    @classmethod
    def tearDownClass(cls):
        if cls.old_env is None:
            os.environ.pop('RATCHET_DATA_ROOT', None)
        else:
            os.environ['RATCHET_DATA_ROOT'] = cls.old_env
        keep = os.environ.get('RATCHET_E2E_KEEP')   # copy the run dir out (for lever_check.py) before cleanup
        if keep:
            shutil.rmtree(keep, ignore_errors=True)
            shutil.copytree(cls.run_dir, keep)
        # the guard refuses chmod/remove under the protected fake key from this process
        subprocess.run(['chmod', '-R', 'u+rwx', str(cls.tmp)], check=False)
        subprocess.run(['rm', '-rf', str(cls.tmp)], check=False)

    @classmethod
    def _step(cls, job: str):
        from ratchet import ledger, llm
        run = arms.load_run(cls.run_dir, kit=arms.LazyKit(tok=cls.tok))
        run.job_id = job
        led = ledger.Ledger(rounds.ledger_dir(run) / ('ledger_%s.jsonl' % job))
        client = llm.StubLLM(FIXTURES, led, cls.tok, gen_tokens=None)
        buf = io.StringIO()
        _SPY['paths'].clear()
        _SPY['on'] = True
        try:
            with mock.patch.object(rounds, 'plan', lambda r: list(STUB_PLAN)), contextlib.redirect_stdout(buf):
                arms.step(run, client, Deadline(time.time()))
        finally:
            _SPY['on'] = False
            if hasattr(led, 'close'):
                led.close()
        return buf.getvalue(), client

    @classmethod
    def _frozen_bytes(cls) -> dict:
        out = {}
        for p in sorted(cls.run_dir.rglob('*')):
            if p.is_file() and p.suffix in ('.json', '.py', '.jsonl') and 'jobs' not in p.parts \
                    and p.name not in ('STATUS.json',) and 'ledger' not in p.parts:
                out[str(p.relative_to(cls.run_dir))] = p.read_bytes()
        return out

    @classmethod
    def _ledger_line_count(cls) -> int:
        return sum(len(p.read_text().splitlines()) for p in (cls.run_dir / 'ledger').glob('*.jsonl'))

    def _sample_rows(self) -> list[dict]:
        rows = []
        for p in sorted(self.run_dir.rglob('samples.jsonl')):
            rows.extend(rounds.iter_jsonl(p))
        return rows

    # -----------------------------------------------------------------------------------------------------------------
    def test_0_every_unit_ran(self):
        for which in ('FLAT_A', 'FLAT_B'):
            self.assertEqual(rounds.load_state(self.run_dir / 'pilot' / which)['state'], 'DONE', which)
        for r in (1, 2):
            self.assertEqual(rounds.load_state(self.run_dir / 'arms' / 'STOCK' / ('round_%d' % r))['state'], 'FROZEN')
        self.assertEqual(len(self._sample_rows()), len(TASKS) * S * 4)
        # sandbox rows for every sample, and the library did reach round 2: a program that only calls copy_grid
        # passes its demos in round 2 (it would raise NameError without the callable library)
        d2 = self.run_dir / 'arms' / 'STOCK' / 'round_2'
        s2 = rounds.read_rows(d2 / 'samples.jsonl', 'sample_id')
        e2 = rounds.read_rows(d2 / 'exec.jsonl', 'sample_id')
        self.assertEqual(set(s2), set(e2))
        uses = [sid for sid, row in s2.items() if row['code'] and 'def copy_grid' not in row['code']
                and 'copy_grid' in row['code'] and TASKS[row['task']] == 'ident']
        for sid in uses:
            self.assertTrue(e2[sid]['demo_pass'], sid)
        print('E2E samples=%d stock_r2_lib_only_programs=%d' % (len(self._sample_rows()), len(uses)))

    def test_1_ledger_totals_match_recount(self):
        from ratchet import ledger, library, prompt, arc_io
        rows = list(ledger.iter_rows(self.run_dir))
        tot = ledger.totals(self.run_dir)
        samples = self._sample_rows()
        self.assertEqual(tot['samples'], len(samples))
        self.assertEqual(tot['requests'], len(TASKS) * 4)
        # gen: re-count every sample text
        gen_recount = sum(self.tok.count(r['text']) for r in samples)
        self.assertTrue(_within(tot['gen'], gen_recount), (tot['gen'], gen_recount))
        # logical prompt: rebuild every prompt from the task file and the frozen library file on disk
        L1 = library.load(self.run_dir / 'arms' / 'STOCK' / 'round_1' / 'L_1.json')
        recount = 0
        for row in rows:
            lib = L1 if (row['arm'] == 'STOCK' and row['round'] == 2) else None
            task = arc_io.load_task(row['task'], 'growth')
            pb = prompt.build_messages(task, self.tok, library=lib, cap_tokens=6000)
            p = sum(self.tok.count(str(m.get('content', ''))) for m in pb.messages)
            recount += p * int(row['n'])
            if lib is not None:
                self.assertEqual(row['library_tokens'], pb.library_tokens)
                self.assertGreater(row['library_tokens'], 0)
            split = row['library_tokens'] + row['exemplar_tokens'] + row['task_tokens'] + row['instruction_tokens']
            self.assertLessEqual(split, row['prompt_tokens'], row['request_id'])
        self.assertTrue(_within(tot['prompt_logical'], recount), (tot['prompt_logical'], recount))
        split_total = (tot['library_logical'] + tot['exemplar_logical'] + tot['task_logical']
                       + tot['instruction_logical'])
        self.assertTrue(_within(tot['prompt_logical'], split_total), (tot['prompt_logical'], split_total))
        # job STATUS.json counters and the top-level STATUS.json agree with the ledger
        js = json.loads((self.run_dir / 'jobs' / 'e2e_j1' / 'STATUS.json').read_text())
        self.assertTrue(_within(js['tokens']['prompt_logical'], tot['prompt_logical']))
        self.assertTrue(_within(js['tokens']['gen'], tot['gen']))
        self.assertEqual(js['tokens']['requests'], tot['requests'])
        top = json.loads((self.run_dir / 'STATUS.json').read_text())
        self.assertEqual(top['ledger_totals']['logical_total'], tot['logical_total'])
        by = {k: ledger.totals(self.run_dir, arm=a, phase=ph) for k, a, ph in (
            ('STOCK', 'STOCK', 'growth'), ('FLAT_A', 'FLAT_A', 'pilot'), ('FLAT_B', 'FLAT_B', 'pilot'))}
        self.assertEqual(sum(v['logical_total'] for v in by.values()), tot['logical_total'])
        print('E2E ledger prompt_logical=%d recount=%d split=%d gen=%d recount=%d samples=%d requests=%d '
              'STOCK=%d FLAT_A=%d FLAT_B=%d' % (tot['prompt_logical'], recount, split_total, tot['gen'], gen_recount,
                                                tot['samples'], tot['requests'], by['STOCK']['logical_total'],
                                                by['FLAT_A']['logical_total'], by['FLAT_B']['logical_total']))

    def test_2_status_and_meta(self):
        first = self.out1.splitlines()[0]
        self.assertTrue(first.startswith('META arm='), first)
        for field in ('model=', 'temperature=0.8', 'top_p=0.95', 'max_tokens=4096', 'enable_thinking=0',
                      'S=2', 'R=2', 'job=e2e_j1', 'code_sha='):
            self.assertIn(field, first)
        js = json.loads((self.run_dir / 'jobs' / 'e2e_j1' / 'STATUS.json').read_text())
        self.assertEqual((js['state'], js['exit_reason']), ('DONE', 'PLAN_DONE'))
        self.assertEqual(js['meta'], first)
        self.assertEqual(len(js['units_done']), len(STUB_PLAN))
        for k in ('started_et', 'updated_et', 'deadline_et', 'seconds', 'tokens', 'exec', 'job_id'):
            self.assertIn(k, js)
        top = json.loads((self.run_dir / 'STATUS.json').read_text())
        self.assertIsNone(top['next_unit'])
        self.assertEqual(top['arms']['STOCK'], {'round_1': 'FROZEN', 'round_2': 'FROZEN'})
        logs = sorted((self.run_dir / 'logs').glob('server_*_e2e_j1.log'))
        names = {p.name for p in logs}
        self.assertIn('server_STOCK_growth_e2e_j1.log', names)
        self.assertIn('server_FLAT_A_pilot_e2e_j1.log', names)
        self.assertIn('server_FLAT_B_pilot_e2e_j1.log', names)
        text = ''
        for p in logs:
            body = p.read_text()
            self.assertTrue(body.startswith('META arm='), p.name)
            # lever_check.py reads each server_<ARM>_* log on its own: every arm's log needs its own markers
            for marker in ('LEVER SANDBOX lib_sha=', 'LEVER NOTHINK first_response_has_think=0', 'LEVER PREFIX hit_rate='):
                self.assertIn(marker, body, p.name)
            text += body
        for marker in ('LEVER STOCK library r=2 ', 'LEVER SANDBOX lib_sha=', 'LEVER NOTHINK first_response_has_think=0',
                       'LEVER PREFIX hit_rate='):
            self.assertIn(marker, text)

    def test_3_no_code_path_opens_the_key(self):
        from ratchet import arc_io
        real = [os.path.realpath(os.fspath(p)) for p in self.paths1]
        roots = [os.path.realpath(str(self.key)), os.path.realpath(str(guard.KEY_ROOT))]
        under = [p for p in real if any(p == r or p.startswith(r + os.sep) for r in roots)]
        self.assertEqual(under, [])
        # positive control: the spy saw the growth task reads of this very run
        g = os.path.realpath(str(self.data / 'growth'))
        self.assertTrue(any(p.startswith(g + os.sep) for p in real), 'spy recorded no growth read')
        # the guard refuses every route to the fake key and protects the real KEY_ROOT
        with self.assertRaises(guard.SealedReadRefused):
            open(self.key_file, 'rb')
        with self.assertRaises(guard.SealedReadRefused):
            os.listdir(self.key)
        with self.assertRaises(guard.SealedReadRefused):
            arc_io._read_json(self.key_file)
        with self.assertRaises(guard.SealedReadRefused):
            guard.check_data_read(guard.KEY_ROOT / 'arcagi1' / 'e2e0.json')
        self.assertTrue(guard.is_protected(guard.KEY_ROOT))
        self.assertTrue(guard.hook_installed())
        self.assertFalse(guard.is_unlocked())
        self.assertEqual(os.stat(self.key_file).st_mode & 0o777, 0)
        print('E2E spy_paths=%d key_paths=0' % len(real))

    def test_4_library_json_round_trip(self):
        from ratchet import library
        out = self.tmp / 'roundtrip'
        out.mkdir(exist_ok=True)
        shas = {}
        for r in (1, 2):
            d = self.run_dir / 'arms' / 'STOCK' / ('round_%d' % r)
            jp, pp = d / ('L_%d.json' % r), d / ('L_%d.py' % r)
            body = json.loads(jp.read_text())
            lib = library.load(jp)
            self.assertEqual(library.sha(lib), body['sha256'])
            self.assertEqual(body['schema'], 'ratchet.library.v1')
            j2, p2, s2 = library.save(lib, out, 6000, self.tok, stem='L_%d' % r)
            self.assertEqual(s2, body['sha256'])
            self.assertEqual(j2.read_bytes(), jp.read_bytes())
            self.assertEqual(p2.read_bytes(), pp.read_bytes())
            self.assertEqual(library.to_dict(library.from_dict(library.to_dict(lib))), library.to_dict(lib))
            st = rounds.load_state(d)
            self.assertEqual(st['library_out'], body['sha256'])
            shas[r] = body
        self.assertIn('copy_grid', {h['name'] for h in shas[1]['helpers']})
        self.assertEqual(shas[2]['parent_sha'], shas[1]['sha256'])
        for h in shas[1]['helpers']:
            self.assertTrue(set(h['calling_tasks']) <= set(TASKS), h['name'])

    def test_6_child_env_finds_libpython(self):
        # the driver's vLLM-venv python is a shared-libpython build; without its LIBDIR on LD_LIBRARY_PATH every
        # sandbox child died at exec (found by running this suite under that interpreter, 2026-11-04)
        import sysconfig
        from ratchet import sandbox
        if sysconfig.get_config_var('Py_ENABLE_SHARED'):
            self.assertIn(str(sysconfig.get_config_var('LIBDIR')),
                          sandbox.CHILD_ENV_BASE.get('LD_LIBRARY_PATH', '').split(':'))
        r = subprocess.run([sys.executable, '-I', '-c', 'print(1)'], env=dict(sandbox.CHILD_ENV_BASE),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, '1'), r.stderr[-300:])

    def test_5_second_job_reissues_nothing(self):
        self.assertEqual(self.client2.bodies, [])
        self.assertEqual(self._ledger_line_count(), self.ledger_rows1)
        self.assertEqual(self._frozen_bytes(), self.frozen1)
        self.assertIn('STEP_EXIT state=DONE reason=PLAN_DONE', self.out2)


if __name__ == '__main__':
    unittest.main()
