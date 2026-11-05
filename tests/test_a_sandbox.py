"""Builder A: sandbox (PREREG 3; SPEC 11 test_sandbox, 8 refusal test 9). Linux only (rlimits, setitimer, unshare)."""
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import ratchet  # noqa: F401
from ratchet import guard, sandbox
from ratchet.sandbox import ExecCache, ExecJob, run_batch, run_program
from ratchet.types import Pair, Task

D_IN = [((1, 2), (3, 4)), ((5, 6), (7, 8)), ((0, 1), (2, 3))]
D_OUT = [tuple(tuple((v + 1) % 10 for v in r) for r in g) for g in D_IN]
T_IN = [((9, 9), (1, 1))]
T_OUT = (((0, 0), (2, 2)),)
PLUS1 = 'def transform(grid):\n    return [[(v + 1) % 10 for v in r] for r in grid]\n'
LINUX = sys.platform.startswith('linux')


def run(code, lib='', **kw):
    return run_program(code, lib, D_IN, D_OUT, T_IN, **kw)


def task(tid='abcd0001', split='growth', outputs=True):
    return Task(id=tid, split=split, train=tuple(Pair(a, b) for a, b in zip(D_IN, D_OUT)), test_inputs=tuple(T_IN),
                test_outputs=T_OUT if outputs else None, src_sha256='sha-' + tid)


@unittest.skipUnless(LINUX, 'sandbox child needs Linux')
class TestSandboxBasics(unittest.TestCase):
    def test_ok(self):
        r = run(PLUS1)
        self.assertEqual(r.status, 'OK', r.error)
        self.assertTrue(r.demo_pass)
        self.assertEqual((r.n_demo_pass, r.n_demos), (3, 3))
        self.assertEqual(r.test_outputs, T_OUT)
        self.assertEqual(len(r.wall_s), 4)
        self.assertEqual(r.code_sha, sandbox.code_sha(PLUS1))

    def test_numpy_output_and_prints(self):
        code = ('import numpy as np\n'
                'def transform(grid):\n'
                '    print("noise " * 1000)\n'
                '    return (np.array(grid) + 1) % 10\n')
        r = run(code)
        self.assertEqual(r.status, 'OK', r.error)
        self.assertEqual(r.test_outputs, T_OUT)

    def test_demo_fail_first_fail_stop(self):
        code = ('calls = []\n'
                'def transform(grid):\n'
                '    calls.append(1)\n'
                '    if len(calls) == 2:\n'
                '        return [[0]]\n'
                '    if len(calls) >= 3:\n'
                '        while True: pass\n'
                '    return [[(v + 1) % 10 for v in r] for r in grid]\n')
        t0 = time.time()
        r = run(code)
        self.assertEqual(r.status, 'DEMO_FAIL')
        self.assertEqual(r.first_fail_demo, 1)
        self.assertEqual(r.n_demo_pass, 1)
        self.assertFalse(r.demo_pass)
        self.assertIsNone(r.test_outputs)
        self.assertEqual(len(r.wall_s), 2)          # the third demo (an infinite loop) never ran
        self.assertLess(time.time() - t0, 1.9)

    def test_timeout_per_demo(self):
        t0 = time.time()
        r = run('def transform(grid):\n    while True: pass\n')
        wall = time.time() - t0
        self.assertEqual(r.status, 'TIMEOUT', (r.error, r.wall_s, r.timeouts, r.n_demo_pass))
        self.assertEqual(r.first_fail_demo, 0)
        self.assertEqual(r.timeouts, 1)
        self.assertGreaterEqual(r.wall_s[0], 1.9)
        self.assertLess(wall, 2.0 * 4 + 2.0)
        print(f'SANDBOX_TIMEOUT_WALL {wall:.3f}s child_wall={r.wall_s[0]:.3f}s')

    def test_timeout_swallowed_by_bare_except(self):
        code = ('def transform(grid):\n'
                '    while True:\n'
                '        try:\n'
                '            while True: pass\n'
                '        except BaseException:\n'
                '            pass\n')
        t0 = time.time()
        r = run_program(code, '', D_IN[:1], D_OUT[:1], T_IN)
        self.assertEqual(r.status, 'TIMEOUT', (r.error, r.wall_s, r.timeouts, r.n_demo_pass))
        self.assertLess(time.time() - t0, 2.0 * 2 + 2.0 + 1.0)

    def test_timeout_on_test_input(self):
        code = ('def transform(grid):\n'
                '    if grid[0][0] == 9:\n'
                '        while True: pass\n'
                '    return [[(v + 1) % 10 for v in r] for r in grid]\n')
        r = run(code)
        self.assertEqual(r.status, 'TIMEOUT', (r.error, r.wall_s, r.timeouts, r.n_demo_pass))
        self.assertTrue(r.demo_pass)
        self.assertIsNone(r.test_outputs)

    def test_bad_outputs(self):
        cases = {'colour': 'return [[10]]', 'side': 'return [[1] * 31]', 'type': 'return [[1.0]]',
                 'shape': 'return [[1, 2], [3]]'}
        for reason, body in cases.items():
            r = run(f'def transform(grid):\n    {body}\n')
            self.assertEqual(r.status, 'BAD_OUTPUT', reason)
            self.assertEqual(r.error, f'BAD_OUTPUT:{reason}')
        r = run('def transform(grid):\n    return [[True]]\n')
        self.assertEqual(r.error, 'BAD_OUTPUT:type')

    def test_no_code_and_syntax(self):
        self.assertEqual(run(None).status, 'NO_CODE')
        self.assertEqual(run('   ').status, 'NO_CODE')
        self.assertEqual(run('def transform(:\n').status, 'SYNTAX')
        self.assertEqual(run('x = 1\n').status, 'ERROR')
        self.assertEqual(run('x = 1\n').error, 'NO_TRANSFORM')

    def test_exception_is_error(self):
        r = run('def transform(grid):\n    return 1 / 0\n')
        self.assertEqual(r.status, 'ERROR')
        self.assertTrue(r.error.startswith('ZeroDivisionError'))
        r = run('def transform(grid):\n    raise SystemExit(3)\n')
        self.assertEqual(r.status, 'ERROR')

    def test_fresh_copy_per_call(self):
        code = ('def transform(grid):\n'
                '    out = [[(v + 1) % 10 for v in r] for r in grid]\n'
                '    grid[0][0] = 7\n'
                '    return out\n')
        self.assertEqual(run(code).status, 'OK')

    def test_import_allowlist(self):
        r = run('import re\ndef transform(grid):\n    return grid\n')
        self.assertEqual(r.status, 'ERROR')
        self.assertIn('IMPORT_REFUSED:re', r.error)
        r = run('import math, itertools, collections, functools, copy, typing\n' + PLUS1)
        self.assertEqual(r.status, 'OK', r.error)


@unittest.skipUnless(LINUX, 'sandbox child needs Linux')
class TestSandboxRefusals(unittest.TestCase):
    """SPEC 8 refusal test 9: key file read, socket, write outside the temp dir -> ERROR and the demo fails."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='ratchet_a_sbx_'))
        cls.key = cls.tmp / 'fakekey'
        cls.key.mkdir()
        cls.k000 = cls.key / 'k000.json'
        cls.k000.write_text('{"test_outputs": [[[1]]]}')
        os.chmod(cls.k000, 0)
        cls.k644 = cls.key / 'k644.json'
        cls.k644.write_text('{"test_outputs": [[[1]]]}')
        guard.add_protected_root(cls.key)

    @classmethod
    def tearDownClass(cls):
        # the guard hook (add-only roots) refuses chmod/remove under the fake key from this process
        subprocess.run(['chmod', '-R', 'u+rwx', str(cls.tmp)], check=False)
        subprocess.run(['rm', '-rf', str(cls.tmp)], check=False)

    def assertRefused(self, body, mark='SANDBOX_REFUSED'):
        code = 'import typing\n_sys = typing.sys\n_os = _sys.modules["os"]\n_b = _sys.modules["builtins"]\n' \
               'def transform(grid):\n' + ''.join('    ' + ln + '\n' for ln in body.split('\n')) + \
               '    return [[(v + 1) % 10 for v in r] for r in grid]\n'
        r = run(code)
        self.assertEqual(r.status, 'ERROR', (body, r.status, r.error))
        self.assertFalse(r.demo_pass)
        self.assertEqual(r.first_fail_demo, 0)
        if mark:
            self.assertIn(mark, r.error or '', body)
        return r

    def test_key_file_read_refused(self):
        for p in (self.k000, self.k644):
            self.assertRefused(f'_b.open({str(p)!r}).read()')
            self.assertRefused(f'_os.open({str(p)!r}, 0)')
        self.assertRefused(f'_os.listdir({str(self.key)!r})')

    def test_other_reads_refused(self):
        self.assertRefused("_b.open('/etc/passwd').read()")
        self.assertRefused(f"_b.open({os.path.abspath(sandbox.__file__)!r}).read()")

    def test_write_outside_tmp_refused(self):
        target = f'/tmp/ratchet_a_x_{os.getpid()}'
        self.assertRefused(f"_b.open({target!r}, 'w').write('x')")
        self.assertFalse(os.path.exists(target))
        self.assertRefused(f"_os.open({target!r}, _os.O_WRONLY | _os.O_CREAT)")
        self.assertFalse(os.path.exists(target))
        self.assertRefused(f"_os.mkdir({target!r})")
        self.assertFalse(os.path.exists(target))

    def test_write_inside_tmp_allowed(self):
        code = ('def transform(grid):\n'
                '    f = open("scratch.txt", "w"); f.write("x"); f.close()\n'
                '    return [[(v + 1) % 10 for v in r] for r in grid]\n')
        r = run(code)
        self.assertEqual(r.status, 'OK', r.error)

    def test_socket_refused(self):
        self.assertRefused("_b.__import__('socket')", mark='socket')
        self.assertRefused("_sys.modules.get('_socket') or _b.__import__('_socket')", mark='socket')

    def test_process_refused(self):
        self.assertRefused("_os.system('true')")
        self.assertRefused("_b.__import__('subprocess')", mark='subprocess')
        self.assertRefused("_os.fork()")
        self.assertRefused("_os.execv('/bin/true', ['true'])")

    def test_ctypes_refused(self):
        self.assertRefused("_b.__import__('ctypes').CDLL(None)", mark='')

    def test_ctypes_via_numpy_refused(self):
        code = ('import numpy as np\n'
                'def transform(grid):\n'
                '    c = np.ctypeslib.ctypes\n'
                '    libc = c.CDLL(None)\n'
                '    return grid\n')
        r = run(code)
        self.assertEqual(r.status, 'ERROR', r.error)
        self.assertIn('SANDBOX_REFUSED', r.error)


@unittest.skipUnless(LINUX, 'sandbox child needs Linux')
class TestIsolationLayer(unittest.TestCase):
    def test_probe(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            mode = sandbox.probe_isolation(force=True)
        self.assertIn(mode, ('bwrap', 'unshare', 'audit'))
        self.assertIn(f'LEVER SANDBOX_PROBE net={sandbox.net_label(mode)} fs={sandbox.fs_label(mode)} mode={mode}',
                      buf.getvalue())
        print(f'SANDBOX_NET {mode}')

    def test_unshare_needs_setpriv_for_mode_000(self):
        if shutil.which('unshare') is None or sandbox.probe_isolation() not in ('bwrap', 'unshare'):
            self.skipTest('unshare not available')
        d = Path(tempfile.mkdtemp(prefix='ratchet_a_cap_'))
        try:
            f = d / 'f000'
            f.write_text('secret')
            os.chmod(f, 0)
            bare = subprocess.run(['unshare', '-rn', 'cat', str(f)], capture_output=True, text=True)
            ours = subprocess.run(list(sandbox.NET_PREFIX) + ['cat', str(f)], capture_output=True, text=True)
            print(f'UNSHARE_BARE_READS_000={bare.returncode == 0 and "secret" in bare.stdout} '
                  f'NET_PREFIX_READS_000={ours.returncode == 0}')
            self.assertNotEqual(ours.returncode, 0)
            self.assertNotIn('secret', ours.stdout)
            caps = subprocess.run(list(sandbox.NET_PREFIX) + ['grep', 'CapEff', '/proc/self/status'],
                                  capture_output=True, text=True)
            self.assertIn('0000000000000000', caps.stdout)
        finally:
            os.chmod(d / 'f000', 0o600)
            shutil.rmtree(d, ignore_errors=True)

    def test_unshare_has_no_network(self):
        if sandbox.probe_isolation() not in ('bwrap', 'unshare'):
            self.skipTest('unshare not available')
        prog = ('import socket\ns = socket.socket()\ns.settimeout(2)\n'
                'try:\n    s.connect(("127.0.0.1", 22)); print("CONNECTED")\nexcept OSError as e:\n    print("NONET", e)\n')
        r = subprocess.run(list(sandbox.NET_PREFIX) + [sys.executable, '-I', '-c', prog], capture_output=True,
                           text=True, timeout=30)
        self.assertIn('NONET', r.stdout, r.stdout + r.stderr)


LIB = ('def inc_grid(g):\n'
       '    return [[(v + 1) % 10 for v in r] for r in g]\n'
       '\n'
       'def unused(g):\n'
       '    return g\n')
USES_LIB = 'def transform(grid):\n    return inc_grid(grid)\n'


@unittest.skipUnless(LINUX, 'sandbox child needs Linux')
class TestLibraryModes(unittest.TestCase):
    def test_callable_counts_test_inputs_only(self):
        r = run(USES_LIB, LIB)
        self.assertEqual(r.status, 'OK', r.error)
        self.assertEqual(r.helper_calls, {'inc_grid': 1})   # 3 demos ran too, but only the test input counts
        self.assertEqual(r.static_refs, ('inc_grid',))
        self.assertEqual(r.helpers_callable, 2)
        self.assertEqual(r.exec_mode, 'callable')

    def test_trace_subset(self):
        r = run(USES_LIB, LIB, trace=['unused'])
        self.assertEqual(r.helper_calls, {})

    def test_indirect_calls_counted(self):
        lib = LIB + '\ndef wrapper(g):\n    return inc_grid(g)\n'
        code = 'def transform(grid):\n    return wrapper(grid)\n'
        r = run(code, lib)
        self.assertEqual(r.status, 'OK', r.error)
        self.assertEqual(r.helper_calls, {'inc_grid': 1, 'wrapper': 1})
        self.assertEqual(r.static_refs, ('wrapper',))

    def test_program_redefinition_not_counted(self):
        code = 'def inc_grid(g):\n    return [[(v + 1) % 10 for v in r] for r in g]\n' + USES_LIB
        r = run(code, LIB)
        self.assertEqual(r.status, 'OK')
        self.assertEqual(r.helper_calls, {})
        self.assertEqual(r.static_refs, ())

    def test_deleted_mode(self):
        lib_deleted = 'def unused(g):\n    return g\n'
        r = run(USES_LIB, lib_deleted, mode='deleted')
        self.assertEqual(r.status, 'ERROR')
        self.assertTrue(r.error.startswith('NameError'), r.error)
        self.assertEqual(r.exec_mode, 'deleted')
        self.assertEqual(r.helpers_callable, 1)

    def test_inline_mode(self):
        r = run(USES_LIB, LIB, mode='inline')
        self.assertEqual(r.status, 'ERROR')
        self.assertTrue(r.error.startswith('NameError'), r.error)
        self.assertEqual(r.helpers_callable, 0)
        self.assertEqual(r.static_refs, ('inc_grid',))
        copied = LIB + USES_LIB
        r = run(copied, LIB, mode='inline')
        self.assertEqual(r.status, 'OK')
        self.assertEqual(r.helper_calls, {})

    def test_bad_library(self):
        r = run(PLUS1, 'def broken(:\n')
        self.assertEqual(r.status, 'ERROR')
        self.assertTrue(r.error.startswith('LIBRARY_SYNTAX'))


@unittest.skipUnless(LINUX, 'sandbox child needs Linux')
class TestBatch(unittest.TestCase):
    def test_cache_hit_and_order(self):
        cache = ExecCache()
        t = task()
        jobs = [ExecJob('s0', t, PLUS1, ''), ExecJob('s1', t, PLUS1, ''), ExecJob('s2', t, 'def transform(g):\n  return g\n', ''),
                ExecJob('s3', t, PLUS1, '', mode='inline'), ExecJob('s4', task('abcd0002'), PLUS1, '')]
        buf = io.StringIO()
        with redirect_stdout(buf):
            rs = list(run_batch(jobs, workers=3, cache=cache))
        self.assertEqual([r.sample_id for r in rs], ['s0', 's1', 's2', 's3', 's4'])
        self.assertEqual([r.cache_hit for r in rs], [False, True, False, False, False])
        self.assertEqual([r.test_correct for r in rs], [True, True, False, True, True])
        self.assertEqual(rs[0].test_outputs, rs[1].test_outputs)
        rs2 = list(run_batch([ExecJob('s9', t, PLUS1, '')], workers=1, cache=cache))
        self.assertTrue(rs2[0].cache_hit)
        self.assertEqual(rs2[0].sample_id, 's9')
        self.assertRegex(buf.getvalue(), r'LEVER SANDBOX lib_sha=\w+ helpers_callable=\d+ net=(unshare|audit)')

    def test_sealed_rows_have_no_test_correct(self):
        rs = list(run_batch([ExecJob('k1', task('abcd0003', split='sealed', outputs=False), PLUS1, '')], workers=1,
                            cache=ExecCache()))
        self.assertIsNone(rs[0].test_correct)
        self.assertNotIn('test_correct', rs[0].to_row())
        self.assertEqual(rs[0].status, 'OK')

    def test_split_in_cache_key(self):
        cache = ExecCache()
        a = task('abcd0004', split='sealed', outputs=False)
        b = Task(id=a.id, split='sealed_perturbed', train=a.train, test_inputs=a.test_inputs, test_outputs=None,
                 src_sha256='other')
        rs = list(run_batch([ExecJob('a', a, PLUS1, ''), ExecJob('b', b, PLUS1, '')], workers=2, cache=cache))
        self.assertEqual([r.cache_hit for r in rs], [False, False])

    def test_row_round_trip(self):
        r = run(USES_LIB, LIB)
        from ratchet.types import ExecResult
        self.assertEqual(ExecResult.from_row(r.to_row()), r)

    def test_spawn_cost_map(self):
        """Rule 7: measure the per-program cost on this node in both spawn modes (printed, not asserted)."""
        t = task()
        n = 24
        old = os.environ.get('RATCHET_SANDBOX_SPAWN')
        try:
            for mode in ('zygote', 'spawn'):
                os.environ['RATCHET_SANDBOX_SPAWN'] = mode
                list(run_batch([ExecJob(f'w{i}', t, PLUS1 + f'# warm {mode} {i}\n', '') for i in range(4)],
                               workers=4, cache=ExecCache()))   # zygote start-up is paid once per worker
                for label, code in (('plain', PLUS1), ('numpy', 'import numpy as np\n' + PLUS1)):
                    jobs = [ExecJob(f'm{i}', t, code + f'# {mode} {i}\n', '') for i in range(n)]
                    t0 = time.time()
                    rs = list(run_batch(jobs, workers=4, cache=ExecCache()))
                    dt = time.time() - t0
                    self.assertTrue(all(r.status == 'OK' for r in rs), [r.error for r in rs])
                    print(f'SANDBOX_COST spawn={mode} {label} programs={n} workers=4 wall={dt:.3f}s '
                          f'per_program_wall={dt * 4 / n:.4f}s net={sandbox.probe_isolation()}')
        finally:
            if old is None:
                os.environ.pop('RATCHET_SANDBOX_SPAWN', None)
            else:
                os.environ['RATCHET_SANDBOX_SPAWN'] = old


@unittest.skipUnless(LINUX, 'sandbox child needs Linux')
class TestZygote(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.get('RATCHET_SANDBOX_SPAWN')
        os.environ['RATCHET_SANDBOX_SPAWN'] = 'zygote'

    def tearDown(self):
        if self.old is None:
            os.environ.pop('RATCHET_SANDBOX_SPAWN', None)
        else:
            os.environ['RATCHET_SANDBOX_SPAWN'] = self.old

    def test_programs_cannot_see_each_other(self):
        a = 'import math\nmath.LEAK = 1\nLEAKED = 1\n' + PLUS1
        b = ('import math\n'
             'def transform(grid):\n'
             '    if hasattr(math, "LEAK") or "LEAKED" in globals():\n'
             '        return [[0]]\n'
             '    return [[(v + 1) % 10 for v in r] for r in grid]\n')
        self.assertEqual(run(a).status, 'OK')
        self.assertEqual(run(b).status, 'OK')

    def test_zygote_reused_and_survives_kill(self):
        run(PLUS1)
        n0 = sandbox._ZYGOTES.started
        for _ in range(3):
            self.assertEqual(run(PLUS1 + '# again\n').status, 'OK')
        r = run_program('def transform(grid):\n    while True:\n        try:\n            while True: pass\n'
                        '        except BaseException:\n            pass\n', '', D_IN[:1], D_OUT[:1], [])
        self.assertEqual(r.status, 'TIMEOUT', (r.error, r.wall_s, r.timeouts, r.n_demo_pass))
        self.assertEqual(run(PLUS1 + '# after kill\n').status, 'OK')
        self.assertEqual(sandbox._ZYGOTES.started, n0)


class _SpawnMode:
    """Re-run a test class with one fresh `python -I -B sandbox_child.py` per program (SPEC 5 literal path)."""

    @classmethod
    def setUpClass(cls):
        cls._old_spawn = os.environ.get('RATCHET_SANDBOX_SPAWN')
        os.environ['RATCHET_SANDBOX_SPAWN'] = 'spawn'
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls._old_spawn is None:
            os.environ.pop('RATCHET_SANDBOX_SPAWN', None)
        else:
            os.environ['RATCHET_SANDBOX_SPAWN'] = cls._old_spawn


class TestSandboxBasicsSpawn(_SpawnMode, TestSandboxBasics):
    pass


class TestSandboxRefusalsSpawn(_SpawnMode, TestSandboxRefusals):
    pass


class TestLibraryModesSpawn(_SpawnMode, TestLibraryModes):
    pass


if __name__ == '__main__':
    unittest.main()
