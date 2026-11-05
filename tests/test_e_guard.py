"""Builder E: sealed-read guard refusal tests (SPEC 8 tests 1 to 6, 8 and 9; tests 7 and 10 are in
test_e_score_verdict.py). Hook tests run in subprocesses so this process never holds an unremovable protected root."""
import json
import os
import re
import tempfile
import textwrap
import unittest
from pathlib import Path

import ratchet  # noqa: F401
from ratchet import guard

from _e_support import REPO, run_py

PRELUDE = textwrap.dedent('''
    import os, sys, json
    from pathlib import Path
    import ratchet
    from ratchet import guard
    KEY = Path(os.environ['T_KEY']); DATA = Path(os.environ['T_DATA'])
    guard.add_protected_root(KEY)
    guard.add_data_root(DATA)
    def refused(fn):
        try:
            fn()
        except guard.SealedReadRefused as e:
            return 'REFUSED'
        except Exception as e:
            return 'OTHER:' + type(e).__name__ + ':' + str(e)[:200]
        return 'ALLOWED'
''')


class GuardCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.key = root / 'key'
        self.data = root / 'data'
        (self.key / 'arcagi1').mkdir(parents=True)
        self.kf = self.key / 'arcagi1' / 'e0.json'
        self.kf.write_text(json.dumps({'id': 'e0', 'test_outputs': [[[1]]]}))
        for s in ('growth', 'sealed'):
            (self.data / s).mkdir(parents=True)
        task = {'train': [{'input': [[1]], 'output': [[2]]}], 'test': [{'input': [[1]]}]}
        (self.data / 'sealed' / 'e0.json').write_text(json.dumps(task))
        (self.data / 'growth' / 'g0.json').write_text(json.dumps(
            {'train': task['train'], 'test': [{'input': [[1]], 'output': [[2]]}]}))
        self.env = {'T_KEY': str(self.key), 'T_DATA': str(self.data), 'RATCHET_DATA_ROOT': str(self.data)}

    def tearDown(self):
        self.tmp.cleanup()

    def py(self, body: str) -> list[str]:
        r = run_py(PRELUDE + textwrap.dedent(body), self.env)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        return r.stdout.split()


class TestGuardRefusals(GuardCase):
    def test1_loader_refuses_key_file(self):
        out = self.py(f'''
            try:
                from ratchet import arc_io
            except Exception:
                print('SKIP'); sys.exit(0)
            print(refused(lambda: arc_io._read_json(Path({str(self.kf)!r}))))
        ''')
        if out == ['SKIP']:
            self.skipTest('arc_io (builder A) not importable')
        self.assertEqual(out, ['REFUSED'])

    def test2_open_and_listdir_refused_after_import(self):
        out = self.py(f'''
            kf = {str(self.kf)!r}
            print(refused(lambda: open(kf).read()))
            print(refused(lambda: open(kf, 'rb')))
            print(refused(lambda: open(kf, 'w')))
            print(refused(lambda: os.listdir(KEY)))
            print(refused(lambda: os.listdir(KEY / 'arcagi1')))
            print(refused(lambda: list(os.scandir(KEY))))
            print(refused(lambda: os.chmod(kf, 0o644)))
            print(refused(lambda: __import__('shutil').copyfile(kf, str(DATA / 'x.json'))))
            print(refused(lambda: Path(kf).read_text()))
            print(refused(lambda: open(str(DATA / 'growth' / 'g0.json')).read()))
        ''')
        self.assertEqual(out, ['REFUSED'] * 9 + ['ALLOWED'])

    def test3_symlink_into_key_refused(self):
        link = self.data / 'sealed' / 'e1.json'
        os.symlink(self.kf, link)
        os.symlink(self.key / 'arcagi1', self.data / 'sealed_perturbed')     # made outside the guarded process
        out = self.py(f'''
            print(refused(lambda: guard.check_data_read(Path({str(link)!r}))))
            print(refused(lambda: open({str(link)!r}).read()))
            try:
                from ratchet import arc_io
                print(refused(lambda: arc_io.load_task('e1', 'sealed')))
            except ImportError:
                print('REFUSED')
            dlink = DATA / 'sealed_perturbed'
            print(refused(lambda: guard.check_data_read(dlink / 'e0.json')))
            print(refused(lambda: os.symlink(KEY / 'arcagi1' / 'e0.json', str(DATA / 'growth' / 'z.json'))))
        ''')
        self.assertEqual(out, ['REFUSED'] * 5)

    def test4_dotdot_and_outside_paths_refused(self):
        out = self.py(f'''
            print(refused(lambda: guard.check_data_read(DATA / 'sealed' / '..' / '..' / 'key' / 'arcagi1' / 'e0.json')))
            print(refused(lambda: guard.check_data_read(DATA / 'sealed' / '..' / 'growth' / '..' / '..' / 'x.json')))
            print(refused(lambda: guard.check_data_read(Path({str(REPO / 'splits' / 'growth_ids_arcagi1_train.txt')!r}))))
            print(refused(lambda: guard.check_data_read(Path('C:/Users/bmens/NQ_local/arc-prize-2026/data/ARC-AGI-2/data/training/x.json'))))
            print(refused(lambda: guard.check_data_read(DATA / 'raw' / 'ARC-AGI' / 'x.json')))
            print(refused(lambda: guard.check_data_read(DATA / 'sealed')))
            print(refused(lambda: guard.check_data_read(DATA / 'sealed' / 'e0.json')))
            print(refused(lambda: guard.check_data_read(DATA / 'growth' / '..' / 'sealed' / 'e0.json')))
        ''')
        self.assertEqual(out, ['REFUSED'] * 6 + ['ALLOWED'] * 2)

    def test5_sealed_file_with_output_is_a_leak(self):
        leak = {'train': [{'input': [[1]], 'output': [[2]]}], 'test': [{'input': [[1]], 'output': [[2]]}]}
        (self.data / 'sealed' / 'e2.json').write_text(json.dumps(leak))
        out = self.py('''
            try:
                from ratchet import arc_io
            except Exception:
                print('SKIP'); sys.exit(0)
            try:
                arc_io.load_task('e2', 'sealed'); print('LOADED')
            except arc_io.SealedLeak:
                print('LEAK')
            t = arc_io.load_task('e0', 'sealed')
            print('OK' if t.test_outputs is None else 'HAS_OUTPUTS')
        ''')
        if out == ['SKIP']:
            self.skipTest('arc_io (builder A) not importable')
        self.assertEqual(out, ['LEAK', 'OK'])

    def test6_unlock_only_from_code_score_sealed(self):
        other = Path(self.tmp.name) / 'elsewhere'
        other.mkdir()
        (other / 'score_sealed.py').write_text(textwrap.dedent(f'''
            import sys
            sys.path.insert(0, {str(REPO)!r})
            import ratchet
            from ratchet import guard
            try:
                p = guard._issue_proof('score'); guard._unlock(p); print('UNLOCKED')
            except guard.SealedReadRefused:
                print('REFUSED')
        '''))
        r = run_py(f'import runpy; runpy.run_path({str(other / "score_sealed.py")!r}, run_name="__main__")', self.env)
        self.assertEqual(r.stdout.split(), ['REFUSED'], r.stderr)
        import subprocess, sys
        r2 = subprocess.run([sys.executable, str(other / 'score_sealed.py')], capture_output=True, text=True)
        self.assertEqual(r2.stdout.split(), ['REFUSED'], r2.stderr)
        out = self.py('''
            print(refused(lambda: guard._unlock(object())))
            print(refused(lambda: guard._unlock(guard._Proof('score'))))
            print(refused(lambda: guard._issue_proof('score')))
            import score_sealed
            print(refused(lambda: score_sealed._read_outputs('primary', [], {'run_dir': DATA}, 'x', 'y')))
            print('LOCKED' if not guard.is_unlocked() else 'UNLOCKED')
            print(refused(lambda: open(str(KEY / 'arcagi1' / 'e0.json')).read()))
        ''')
        self.assertEqual(out, ['REFUSED', 'REFUSED', 'REFUSED', 'REFUSED', 'LOCKED', 'REFUSED'])

    def test_protected_roots_are_add_only(self):
        self.assertFalse(hasattr(guard, 'remove_protected_root'))
        self.assertIn(Path(os.path.realpath(str(guard.KEY_ROOT))), [Path(p) for p in guard.protected_roots()])
        self.assertTrue(guard.hook_installed())


class TestStatic(unittest.TestCase):
    """SPEC 8 test 8: only guard.py and arc_io.py open data paths; only guard.py and score_sealed.py name the key."""

    def test8_static(self):
        pkg = REPO / 'ratchet'
        key_bad, open_bad = [], []
        data_tok = re.compile(r"DATA_ROOT|data_root\(|['\"/]data/|DATA_DIR|['\"](growth|sealed|sealed_perturbed|"
                              r"arcagi2_sealed)['\"]")
        for p in sorted(pkg.glob('*.py')):
            text = p.read_text(encoding='utf-8')
            if p.name != 'guard.py' and ('key/' in text or 'KEY_ROOT' in text):
                key_bad.append(p.name)
            if p.name in ('guard.py', 'arc_io.py'):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if 'open(' in line and data_tok.search(line):
                    open_bad.append(f'{p.name}:{i}')
        self.assertEqual(key_bad, [], 'files naming the key location')
        self.assertEqual(open_bad, [], 'open( on a data path outside guard.py and arc_io.py')
        self.assertIn('KEY_ROOT', (REPO / 'score_sealed.py').read_text() + (pkg / 'guard.py').read_text())


class TestSandboxRefusals(GuardCase):
    """SPEC 8 test 9: a generated program that reads the key, opens a socket or writes outside its temp dir fails."""

    def test9_sandbox(self):
        try:
            from ratchet import sandbox
        except Exception as e:  # pragma: no cover
            self.skipTest(f'sandbox (builder A) not importable: {e}')
        os.chmod(self.kf, 0o644)                       # prove the child's hook refuses, not only the file mode
        outside = Path(self.tmp.name) / 'outside_x'
        progs = {
            'key': f'def transform(grid):\n    open({str(self.kf)!r}).read()\n    return grid\n',
            'socket': 'import socket\ndef transform(grid):\n    socket.socket().connect(("1.1.1.1", 80))\n    return grid\n',
            'socket2': 'def transform(grid):\n    __import__("socket").create_connection(("1.1.1.1", 80), 1)\n    return grid\n',
            'write': f'def transform(grid):\n    open({str(outside)!r}, "w").write("x")\n    return grid\n',
            'tmpx': 'def transform(grid):\n    open("/tmp/ratchet_e_test_x", "w").write("x")\n    return grid\n',
        }
        g = ((1,),)
        for name, code in progs.items():
            r = sandbox.run_program(code, '', [g], [g], [g], timeout_s=2.0)
            self.assertFalse(r.demo_pass, name)
            self.assertIn(r.status, ('ERROR', 'DEMO_FAIL', 'TIMEOUT'), (name, r.status, r.error))
        self.assertFalse(outside.exists())
        ok = sandbox.run_program('def transform(grid):\n    return grid\n', '', [g], [g], [g], timeout_s=2.0)
        self.assertTrue(ok.demo_pass, ok.error)


if __name__ == '__main__':
    unittest.main()
