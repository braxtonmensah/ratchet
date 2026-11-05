"""Review fixes 2026-11-04: one or more refusal or behaviour tests per applied finding (CPU, login node, no GPU)."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import ratchet  # noqa: F401
from ratchet import arms, config, freeze, gates, guard, knockout, pilot, prompt, report, rounds, sandbox, verdict
from ratchet.arms import Run
from ratchet.library import Helper, Library
from ratchet.tok import StubTokenizer
from ratchet.types import Pair, Task

import _e_support as S

LINUX = sys.platform.startswith('linux')
G = ((1, 2), (3, 4))


def busy(sec: float, indent: str = '') -> str:
    return (f'{indent}_t0 = time.perf_counter()\n'
            f'{indent}while time.perf_counter() - _t0 < {sec}:\n'
            f'{indent}    pass\n')


# ---------------------------------------------------------------------------------------------------------------------
# finding 1, 3, 27: OS-level sandbox view; production refuses weaker modes; namespace audit events refused

@unittest.skipUnless(LINUX, 'sandbox needs Linux')
class TestSandboxIsolation(unittest.TestCase):
    def test_bwrap_view_hides_tmp_and_silo_without_the_hook(self):
        if sandbox.probe_isolation() != 'bwrap':
            self.skipTest('bwrap view not available here')
        d = Path(tempfile.mkdtemp(prefix='ratchet_g_secret_'))
        tmp = Path(tempfile.mkdtemp(prefix='ratchet_g_box_'))
        try:
            secret = d / 'answer.json'
            secret.write_text('{"test_outputs": [[[7]]]}')
            # a raw interpreter (no audit hook at all) inside the view: the OS view alone must hide these paths
            code = ('import json, os, sys\n'
                    'print(json.dumps({p: os.path.exists(p) for p in sys.argv[1:]}))\n')
            paths = [str(secret), str(guard.DATA_ROOT), str(config.REAL_RUNS_DIR), sandbox.CHILD_PATH]
            r = subprocess.run(sandbox.bwrap_prefix(str(tmp)) + [sys.executable, '-I', '-c', code] + paths,
                               capture_output=True, text=True, timeout=60, env=dict(sandbox.CHILD_ENV_BASE))
            seen = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertFalse(seen[str(secret)], seen)
            self.assertFalse(seen[str(guard.DATA_ROOT)], seen)
            self.assertFalse(seen[str(config.REAL_RUNS_DIR)], seen)
            self.assertTrue(seen[sandbox.CHILD_PATH], seen)          # positive control: the bound child file
            # and a generated program reading it through the real path fails its demo
            prog = 'def transform(grid):\n    open(%r).read()\n    return grid\n' % str(secret)
            res = sandbox.run_program(prog, '', [G], [G], [G])
            self.assertNotEqual(res.status, 'OK')
            self.assertFalse(res.demo_pass)
            print('G_BWRAP_VIEW hidden=%s child_visible=%s' % (not seen[str(secret)], seen[sandbox.CHILD_PATH]))
        finally:
            shutil.rmtree(d, ignore_errors=True)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_selftest_passes_here(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            res = sandbox.selftest()
        self.assertTrue(res['pass'], res)
        self.assertRegex(buf.getvalue(), r'LEVER SANDBOX_SELFTEST pass=1 net=\w+ fs=\w+')
        print(buf.getvalue().strip().splitlines()[-1])

    def test_production_refuses_weak_modes(self):
        old = sandbox._net_mode
        try:
            with mock.patch.object(sandbox, 'production', return_value=True), \
                    mock.patch.dict(os.environ, {'RATCHET_SANDBOX_NET': 'audit'}):
                with redirect_stdout(io.StringIO()) as buf:
                    with self.assertRaises(sandbox.SandboxIsolationError):
                        sandbox.probe_isolation(force=True)
                self.assertIn('SANDBOX_NET_FAIL', buf.getvalue())
            env = {k: v for k, v in os.environ.items() if k != 'RATCHET_SANDBOX_NET'}
            with mock.patch.object(sandbox, 'production', return_value=True), \
                    mock.patch.object(sandbox, 'BWRAP', '/nonexistent/bwrap'), mock.patch.dict(os.environ, env, clear=True):
                with redirect_stdout(io.StringIO()) as buf:
                    with self.assertRaises(sandbox.SandboxIsolationError):
                        sandbox.probe_isolation(force=True)
                self.assertIn('SANDBOX_NET_FAIL mode=', buf.getvalue())
        finally:
            sandbox._net_mode = old

    def test_child_hook_refuses_namespace_events(self):
        spec = importlib.util.spec_from_file_location('ratchet_child_under_test', sandbox.CHILD_PATH)
        child = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(child)
        hook = child._make_hook(tempfile.gettempdir(), [], [], [])
        for ev in ('os.unshare', 'os.setns', 'sys.addaudithook', 'os.fork', 'socket.connect'):
            with self.assertRaises(PermissionError, msg=ev):
                hook(ev, (0,))
        with self.assertRaises(PermissionError):
            hook('os.fwalk', ('/etc',))
        hook('os.listdir', (tempfile.gettempdir(),))     # inside the temp dir: allowed


# ---------------------------------------------------------------------------------------------------------------------
# finding 5: the aggregate budget covers library exec and top-level program exec

@unittest.skipUnless(LINUX, 'sandbox needs Linux')
class TestAggregateBudget(unittest.TestCase):
    def test_slow_library_and_toplevel_with_every_demo_under_2s_is_ok(self):
        # 1 demo + 1 test, each 1.7 s; library exec 1.7 s; program top-level exec 1.7 s: about 6.8 s in total. The old
        # parent kill (2 x 2 inputs + 2 = 6 s) and RLIMIT_CPU (2 x 2 + 1 = 5 s) killed this program although every
        # timed window was under its 2 s.
        lib = 'import time\n' + busy(1.7) + 'def helper(g):\n    return [list(r) for r in g]\n'
        code = 'import time\n' + busy(1.7) + 'def transform(grid):\n' + busy(1.7, '    ') + '    return helper(grid)\n'
        allow = tuple(sandbox.IMPORT_ALLOW) + ('time',)
        with mock.patch.object(sandbox, 'IMPORT_ALLOW', allow):
            t0 = time.time()
            r = sandbox.run_program(code, lib, [G], [G], [G])
            dt = time.time() - t0
        print('G_AGG status=%s error=%s wall=%.2f hard_s=%.1f' % (r.status, r.error, dt,
                                                                 2.0 * (2 + sandbox.AGG_WINDOWS) + sandbox.HARD_PAD_S))
        self.assertEqual(r.status, 'OK', r.error)
        self.assertTrue(r.demo_pass)

    def test_library_timeout_is_labelled(self):
        lib = 'while True:\n    pass\n'
        r = sandbox.run_program('def transform(grid):\n    return grid\n', lib, [G], [G], [G])
        self.assertEqual(r.status, 'TIMEOUT')
        self.assertEqual(r.error, 'LIB_TIMEOUT')


# ---------------------------------------------------------------------------------------------------------------------
# findings 2, 4, 6, 22, 23: key-root read log, --test, perturb binding, retirement, acks

class TestScoreGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.key, self.data = S.make_key(self.root)
        f = S.make_run(self.root)
        self.run, self.fsha, self.ssha = f['run'], f['freeze_sha'], f['submit_sha']

    def tearDown(self):
        subprocess.run(['chmod', '-R', 'u+rwx', self.tmp.name], check=False)
        self.tmp.cleanup()

    def score(self, run=None, extra=(), test_flag=True, ssha=None):
        return S.run_score(['score', '--run', str(run or self.run), '--condition', 'primary', '--freeze-sha', self.fsha,
                            '--submit-sha', ssha or self.ssha] + list(extra), self.key, test_flag=test_flag)

    def test_fresh_run_dir_or_deleted_log_gets_no_second_read(self):
        r = self.score()
        self.assertEqual(r.returncode, 0, r.stderr)
        # copy the run (same freezes, same submissions) to a new dir and drop its run-local log: still refused
        v1b = self.run.parent / 'v1b'
        shutil.copytree(self.run, v1b)
        shutil.rmtree(v1b / 'scores')
        r2 = self.score(run=v1b)
        self.assertEqual(r2.returncode, 2, r2.stdout + r2.stderr)
        self.assertIn('REPEATED_CONDITION_KEY', r2.stderr)
        (self.run / 'scores' / 'KEY_READS.jsonl').unlink()
        r3 = self.score()
        self.assertIn('REPEATED_CONDITION_KEY', r3.stderr)
        self.assertEqual(S.key_modes(self.key), [0] * len(S.key_modes(self.key)))   # the key log is mode 000 too
        print('G_KEYLOG second_run=%s deleted_log=%s' % (r2.returncode, r3.returncode))

    def test_amendment_must_be_registered_and_unused(self):
        self.assertEqual(self.score().returncode, 0)
        v1b = self.run.parent / 'v1b'
        shutil.copytree(self.run, v1b)
        shutil.rmtree(v1b / 'scores')
        r = self.score(run=v1b, extra=['--amendment', '99'])
        self.assertIn('AMENDMENT_NOT_IN_PREREG', r.stderr)
        r = self.score(run=v1b, extra=['--amendment', '0'])     # PREREG.md carries "AMENDMENT 0 "
        self.assertEqual(r.returncode, 0, r.stderr)
        v1c = self.run.parent / 'v1c'
        shutil.copytree(self.run, v1c)
        shutil.rmtree(v1c / 'scores')
        self.assertIn('AMENDMENT_ALREADY_USED', self.score(run=v1c, extra=['--amendment', '0']).stderr)

    def test_key_override_needs_test_flag(self):
        r = self.score(test_flag=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn('ROOT_OVERRIDE_REFUSED', r.stderr)

    def test_not_acked(self):
        (self.run / 'freeze' / 'FREEZE.ack').unlink()
        r = self.score()
        self.assertIn('NOT_ACKED FREEZE.ack', r.stderr)

    def test_retired_harness(self):
        (self.run.parent / 'ATTEMPTS.json').write_text(json.dumps({'void_runs': ['a', 'b']}))
        self.assertIn('HARNESS_RETIRED', self.score().stderr)

    def test_perturb_seed_bound_to_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            key, _ = S.make_key(root)
            f = S.make_run(root, manifest_seed=7)
            r = S.run_score(['score', '--run', str(f['run']), '--condition', 'primary', '--freeze-sha', f['freeze_sha'],
                             '--submit-sha', f['submit_sha']], key)
            self.assertIn('PERTURB_SEED_MISMATCH', r.stderr)
            subprocess.run(['chmod', '-R', 'u+rwx', d], check=False)

    def test_perturbed_file_edit_refused(self):
        p = self.root / 'data' / 'sealed_perturbed' / 'e3.json'
        p.write_text(p.read_text() + ' ')
        self.assertIn('PERTURBED_FILE_CHANGED', self.score().stderr)


# ---------------------------------------------------------------------------------------------------------------------
# findings 14, 15, 17: verdict refuses a registered label without power or with a VOID lever

class TestVerdictBlocks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.key, self.data = S.make_key(self.root)
        f = S.make_run(self.root)
        self.run = f['run']
        r = S.run_score(['score', '--run', str(self.run), '--condition', 'primary', '--freeze-sha', f['freeze_sha'],
                         '--submit-sha', f['submit_sha']], self.key)
        assert r.returncode == 0, r.stderr
        ko = S.make_knockout(self.run, f['freeze_sha'], f['submit_sha'])
        r = S.run_score(['score', '--run', str(self.run), '--condition', 'knockout', '--freeze-sha', f['freeze_sha'],
                         '--submit-sha', ko], self.key)
        assert r.returncode == 0, r.stderr

    def tearDown(self):
        subprocess.run(['chmod', '-R', 'u+rwx', self.tmp.name], check=False)
        self.tmp.cleanup()

    def test_all_levers_ok_is_registered(self):
        v = verdict.verdict(self.run)
        self.assertEqual(v['blocks'], [])
        out = verdict.write_result(self.run, None)
        self.assertEqual(out.name, 'RESULT.md')

    def test_missing_marker_is_lever_void_draft(self):
        (self.run / 'logs' / 'server_SHAM_sealed_fixture.log').unlink()
        out = verdict.write_result(self.run, None)
        self.assertEqual(out.name, 'RESULT_DRAFT.md')
        self.assertFalse((self.run / 'RESULT.md').exists())
        self.assertIn('LEVER_VOID: SHAM no_logs', out.read_text())

    def test_nothink_one_is_void(self):
        p = self.run / 'logs' / 'server_STATIC_sealed_fixture.log'
        p.write_text(p.read_text() + 'LEVER NOTHINK first_response_has_think=1\n')
        self.assertIn('STATIC NOTHINK=1', '; '.join(verdict.verdict(self.run)['blocks']))

    def test_stock_l_r_equal_to_l_1_is_void(self):
        fz = json.loads((self.run / 'freeze' / 'FREEZE.json').read_text())
        lib = json.loads((self.run / fz['libraries']['STOCK']['json']).read_text())
        (self.run / fz['libraries']['STATIC']['json']).write_text(json.dumps(lib))
        self.assertIn('STOCK L_R_in_context_equals_L_1', verdict.lever_status(self.run)['void'])

    def test_pilot_missing_and_power_missing(self):
        (self.run / 'PILOT.json').unlink()
        self.assertIn('PILOT_MISSING', verdict.verdict(self.run)['blocks'])
        (self.run / 'PILOT.json').write_text(json.dumps({'status': 'OK', 'choice': {'power': None}}))
        self.assertIn('POWER_MISSING', verdict.verdict(self.run)['blocks'])
        self.assertEqual(verdict.write_result(self.run, None).name, 'RESULT_DRAFT.md')


class TestPilotRule(unittest.TestCase):
    RATES = {'g': 1000.0, 'P_task': 1500.0, 'L': 6000, 'a': 1e9, 'b': 0.0, 'startup_s': 0.0, 'u_flat_req': 0.0,
             'u_lib_req': 0.0}

    def test_no_d_is_power_missing_not_ok(self):
        c = pilot.choose_SR(dict(self.RATES, d=None), power_sims=500)
        self.assertEqual(c['status'], 'POWER_MISSING')
        self.assertIsNone(c['S'])
        self.assertEqual(c['would_choose'], {'S': 16, 'R': 8})

    def test_flat_extra_counts_round1_at_m_F(self):
        u = pilot.units(4, 3.4)
        self.assertAlmostEqual(u['flat_extra'], 2 * 3 * (1 + 4 * 3.4))

    def test_no_cached_counts_is_rates_missing(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            import datetime as dt
            t0 = dt.datetime(2026, 11, 5, 10, 0, 0)
            rows = [{'request_id': f'r{i}', 'phase': 'pilot', 'latency_s': 30.0, 'gen_tokens': 8000, 'n': 8,
                     'prompt_tokens': 1500, 'cached_prompt_tokens': None, 'task_tokens': 1100, 'instruction_tokens': 400,
                     'ts_et': (t0 + dt.timedelta(seconds=5 * i)).strftime('%Y-%m-%d %H:%M:%S')} for i in range(40)]
            (run / 'ledger').mkdir()
            (run / 'ledger' / 'ledger_1.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            for w, k in (('FLAT_A', 20), ('FLAT_B', 20), ('PLANT1', 25)):
                (run / 'pilot' / w).mkdir(parents=True)
                (run / 'pilot' / w / 'exec.jsonl').write_text(''.join(
                    json.dumps({'sample_id': f'{w}|pilot|r1|t{i:02d}|s0', 'demo_pass': i < k}) + '\n' for i in range(50)))
            res = pilot.run_pilot_rules(run, correct_fn=lambda d_, w: {'t00': True, 't01': w == 'FLAT_A'},
                                        power_sims=500)
            self.assertEqual(res['status'], 'RATES_MISSING')
            self.assertEqual(res['rates']['cached_known_rows'], 0)


# ---------------------------------------------------------------------------------------------------------------------
# findings 7, 17, 22: test switches, S/R only from the pilot, retirement at init

class TestRunSwitches(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_g_run_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_auto_ack_and_skip_pilot_refused_in_production(self):
        prod = Run(dir=config.REAL_RUNS_DIR / 'any', S=4, R=4, seed_base=1000, cfg={'auto_ack': True})
        with self.assertRaises(rounds.TestSwitchRefused):
            rounds.check_test_switches(prod)
        with self.assertRaises(rounds.TestSwitchRefused):
            rounds.plan(Run(dir=config.REAL_RUNS_DIR / 'any', S=4, R=4, seed_base=1000, cfg={'skip_pilot': True}))
        local = Run(dir=self.tmp, S=4, R=4, seed_base=1000, cfg={'auto_ack': True})
        rounds.check_test_switches(local)                        # a temp test run: allowed
        with mock.patch.dict(os.environ, {'SLURM_JOB_ID': '123'}):
            with self.assertRaises(rounds.TestSwitchRefused):
                rounds.check_test_switches(local)                # inside any SLURM job: refused

    def test_init_refuses_S_R_without_pilot_and_after_retirement(self):
        with self.assertRaises(arms.ArmError):
            arms.init_run(self.tmp / 'a', S=4, R=4, model='/fake/model')
        (self.tmp / 'ATTEMPTS.json').write_text(json.dumps({'void_runs': ['x', 'y'], 'retired': True}))
        with self.assertRaises(arms.ArmError) as cm:
            arms.init_run(self.tmp / 'b', model='/fake/model')
        self.assertIn('HARNESS_RETIRED', str(cm.exception))

    def test_freeze_needs_pilot_with_power(self):
        arms.init_run(self.tmp / 'c', model='/fake/model')
        run = arms.update_run(arms.load_run(self.tmp / 'c'), S=4, R=4)
        with self.assertRaises(freeze.FreezeRefused) as cm:
            freeze.check_pilot(run)
        self.assertIn('PILOT_MISSING', str(cm.exception))
        (self.tmp / 'c' / 'PILOT.json').write_text(json.dumps({'status': 'OK', 'S': 4, 'R': 4,
                                                               'choice': {'power': None}}))
        with self.assertRaises(freeze.FreezeRefused):
            freeze.check_pilot(run)
        (self.tmp / 'c' / 'PILOT.json').write_text(json.dumps({'status': 'OK', 'S': 4, 'R': 4,
                                                               'choice': {'power': 0.7}}))
        self.assertEqual(freeze.check_pilot(run)['status'], 'OK')

    def test_model_check_records_then_detects_a_change(self):
        m = self.tmp / 'model'
        m.mkdir()
        (m / 'config.json').write_text('{"a": 1}')
        (m / 'layers-0.safetensors').write_bytes(b'w' * 1000)
        arms.init_run(self.tmp / 'r', model=str(m))
        run = arms.load_run(self.tmp / 'r')
        self.assertEqual(arms.model_check(run)['state'], 'RECORDED')
        run = arms.load_run(self.tmp / 'r')
        self.assertEqual(arms.model_check(run)['state'], 'MATCH')
        self.assertIsNotNone(arms.model_sha(run))
        (m / 'layers-0.safetensors').write_bytes(b'x' * 1001)
        with self.assertRaises(arms.ArmError) as cm:
            arms.model_check(run)
        self.assertIn('MODEL_CHANGED', str(cm.exception))


# ---------------------------------------------------------------------------------------------------------------------
# findings 10, 12: knockout prompt shows the callable rest plus the knocked-out helpers as text; no refill

def _h(name, deps=(), in_ctx=True, tasks=2):
    src = f'def {name}(g):\n' + (f'    return {deps[0]}(g)\n' if deps else '    return g\n')
    return Helper(name=name, hash='h_' + name, source=src, canonical=src, token_len=8, deps=list(deps),
                  calling_tasks=[f't{i}' for i in range(tasks)], n_calling_tasks=tasks, in_context=in_ctx)


class TestKnockoutPrompt(unittest.TestCase):
    def test_inline_prompt_blocks(self):
        tok = StubTokenizer()
        callable_lib = Library(arm='KO', round=2, helpers=[_h('d')], parent_sha=None, meta={})
        text_lib = Library(arm='KO_INLINE', round=2, helpers=[_h('a'), _h('b', ['a'])], parent_sha=None, meta={})
        task = Task(id='t9', split='sealed', train=(Pair(G, G),), test_inputs=(G,), test_outputs=None, src_sha256='x')
        pb = prompt.build_messages(task, tok, library=callable_lib, inline_library=text_lib, cap_tokens=6000)
        user = pb.messages[1]['content']
        self.assertIn(prompt.CALLABLE_HEADER, user)
        self.assertIn(prompt.INLINE_HEADER, user)
        self.assertLess(user.index(prompt.CALLABLE_HEADER), user.index(prompt.INLINE_HEADER))
        self.assertEqual(pb.helpers_in_context, ('d',))
        self.assertEqual(pb.helpers_inline, ('a', 'b'))
        self.assertEqual(pb.block_kind, 'callable+inline')
        self.assertEqual(pb.library_tokens, tok.count(user[:user.index('Example 1')].strip()))

    def test_delete_library_never_refills(self):
        L = Library(arm='STOCK', round=3, helpers=[_h('a'), _h('b', ['a']), _h('c'), _h('z', in_ctx=False, tasks=9)],
                    parent_sha=None, meta={})
        libs = knockout.build_knockout_libraries(L, frozenset(['t']), {'t': [{'helper_calls': {'a': 1}}]})
        self.assertEqual([h.name for h in libs['t'].helpers], ['c'])      # b depends on a; z was out of context
        self.assertEqual(libs['t'].meta['knockout_removed'], ['a', 'b'])


# ---------------------------------------------------------------------------------------------------------------------
# findings 9, 11, 18, 19, 24, 26

class TestPoolsAndCounts(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_g_pool_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _round(self, arm, rows):
        d = self.tmp / 'arms' / arm / 'round_1'
        d.mkdir(parents=True)
        # distinct constants: helpers that differ only by name share a canonical hash and would dedup to one
        code = 'def grow_%d(g):\n    return [r + [%d] for r in g]\n\ndef transform(grid):\n    return grow_%d(grid)\n'
        sam, ex = [], []
        for i, (status, dp) in enumerate(rows):
            sid = f'{arm}|growth|r1|t{i}|s0'
            sam.append({'sample_id': sid, 'task': f't{i}', 'phase': 'growth', 'code': code % (i, i, i)})
            ex.append({'sample_id': sid, 'status': status, 'demo_pass': dp})
        (d / 'samples.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in sam))
        (d / 'exec.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in ex))

    def test_failed_pool_takes_every_demo_failure(self):
        from ratchet import sham
        self._round('STOCK', [('DEMO_FAIL', False), ('ERROR', False), ('TIMEOUT', False), ('OK', True),
                              ('ERROR', True), ('SYNTAX', False)])
        names = sorted(h.name for h in sham.failed_pool(self.tmp))
        self.assertEqual(names, ['grow_0', 'grow_1', 'grow_2'])     # demo-passing ones never; SYNTAX has no code
        self._round('EXEMPLAR', [('DEMO_FAIL', False), ('OK', True)])
        self.assertEqual(sorted(h.name for h in sham.failed_pool(self.tmp, 'EXEMPLAR')), ['grow_0'])

    def test_round_solutions_accept_demo_pass_whatever_the_test_status(self):
        self._round('STOCK', [('OK', True), ('ERROR', True), ('TIMEOUT', True), ('DEMO_FAIL', False)])
        run = Run(dir=self.tmp, S=1, R=1, seed_base=1000, cfg={}, kit=arms.LazyKit(tok=StubTokenizer()))
        with mock.patch.object(arms, 'growth_ids', return_value=['t0', 't1', 't2', 't3']):
            sols = arms.round_solutions(run, self.tmp / 'arms' / 'STOCK' / 'round_1', None)
        self.assertEqual(sorted(s.task for s in sols), ['t0', 't1', 't2'])

    def test_knockout_threshold_from_config(self):
        self.assertEqual(gates.knockout_gate(frozenset('abcde'), frozenset('ab'), frozenset('a'))['max_kept'], 2)
        self.assertEqual(gates.knockout_gate(frozenset('abcd'), frozenset(), frozenset(), 0.5)['max_kept'], 2)
        self.assertEqual(gates.knockout_gate(frozenset('abcdefghij'), frozenset(), frozenset(), 0.3)['max_kept'], 3)

    def test_sealed_demo_pass_counts(self):
        d = self.tmp / 'sealed' / 'sealed' / 'STOCK' / 'seed_1'
        d.mkdir(parents=True)
        (d / 'samples.jsonl').write_text(''.join(json.dumps({'sample_id': f's{i}', 'task': f't{i % 2}'}) + '\n'
                                                 for i in range(4)))
        (d / 'exec.jsonl').write_text(''.join(json.dumps({'sample_id': f's{i}', 'demo_pass': i == 1}) + '\n'
                                              for i in range(4)))
        self.assertEqual(report.sealed_demo_pass(self.tmp, 'sealed', 'STOCK'), {'1': 1})

    def test_perturb_entry_seed_check(self):
        man = self.tmp / 'PERTURB.json'
        man.write_text(json.dumps({'seed': 5, 'n_tasks': 0, 'tasks': {}}))
        (self.tmp / 'PERTURB_DONE.json').write_text(json.dumps({'out': str(man)}))
        run = Run(dir=self.tmp, S=1, R=1, seed_base=1000, cfg={'perturb_seed': 5})
        e = freeze.perturb_entry(run)
        self.assertEqual(e['seed'], 5)
        self.assertEqual(e['sha256'], S.sha(man))
        run.cfg['perturb_seed'] = 6
        with self.assertRaises(freeze.FreezeRefused):
            freeze.perturb_entry(run)


if __name__ == '__main__':
    unittest.main()
