import json
import tempfile
import unittest
from pathlib import Path

from _c_support import StubTokenizer, sid
from ratchet import helpers as H
from ratchet import library as L


def prog(helper_src, call):
    return helper_src + f'\n\ndef transform(grid):\n    return {call}(grid)\n'


FLIP = 'def flip(g):\n    return [r[::-1] for r in g]\n'
UPS = 'def upside(g):\n    return [list(r) for r in g[::-1]]\n'
BIG = 'def big(g):\n' + ''.join(f'    g = [[(c + {i}) % 10 for c in r] for r in g]\n' for i in range(12)) + '    return g\n'


def sol(code, task, slot=0, rnd=1, lib=frozenset()):
    return H.build_solution(sid(task, slot, rnd), task, code, lib)


def round1():
    tok = StubTokenizer()
    sols = [sol(prog(FLIP, 'flip'), 't1'), sol(prog(FLIP, 'flip'), 't2'), sol(prog(FLIP, 'flip'), 't3'),
            sol(prog(UPS, 'upside'), 't1'), sol(prog(UPS, 'upside'), 't4'),
            sol(prog(BIG, 'big'), 't5'), sol(prog(BIG, 'big'), 't6')]
    acc = H.accept(sols, L.empty('STOCK'), tok)
    return L.merge(L.empty('STOCK'), acc, 1, sols), tok


class TestLibrary(unittest.TestCase):
    def test_rank_order(self):
        lib, _ = round1()
        r = L.rank(lib)
        self.assertEqual(r[0].name, 'flip')            # 3 tasks
        self.assertEqual([h.n_calling_tasks for h in r], [3, 2, 2])
        self.assertLess(r[1].token_len, r[2].token_len)  # tie on tasks -> shorter first
        self.assertEqual([h.rank for h in r], [1, 2, 3])
        self.assertIsNone(lib.parent_sha)

    def test_save_load_sha_and_determinism(self):
        lib, tok = round1()
        with tempfile.TemporaryDirectory() as d:
            jp, pp, s = L.save(lib, Path(d), 6000, tok)
            self.assertEqual(jp.name, 'L_1.json')
            self.assertEqual(L.sha(lib), s)
            back = L.load(jp)
            self.assertEqual(L.sha(back), s)
            self.assertEqual(json.loads(jp.read_text())['sha256'], s)
            b1 = jp.read_bytes()
            L.save(back, Path(d) / 'again', 6000, tok)
            self.assertEqual((Path(d) / 'again' / 'L_1.json').read_bytes(), b1)
            # tamper
            dd = json.loads(b1)
            dd['helpers'][0]['source'] = dd['helpers'][0]['source'].replace('[::-1]', '[::1]')
            jp.write_text(json.dumps(dd))
            with self.assertRaises(L.LibraryHashMismatch):
                L.load(jp)

    def test_py_render_executes(self):
        lib, tok = round1()
        with tempfile.TemporaryDirectory() as d:
            _, pp, _ = L.save(lib, Path(d), 6000, tok)
            ns = {}
            exec(compile(pp.read_text(), str(pp), 'exec'), ns)
            self.assertEqual(ns['flip']([[1, 2]]), [[2, 1]])
            self.assertEqual(ns['upside']([[1], [2]]), [[2], [1]])

    def test_cap_limits_in_context(self):
        lib, tok = round1()
        _, names_all, n_all = L.in_context(lib, 6000, tok)
        self.assertEqual(set(names_all), {'flip', 'upside', 'big'})
        cap = n_all - 5
        with tempfile.TemporaryDirectory() as d:
            L.save(lib, Path(d), cap, tok)
        inside = {h.name for h in lib.helpers if h.in_context}
        self.assertNotIn('big', inside)                  # biggest and lowest rank is dropped
        self.assertIn('flip', inside)
        self.assertLessEqual(lib.meta['in_context_tokens'], cap)

    def test_merge_reuse_and_parent(self):
        lib1, tok = round1()
        with tempfile.TemporaryDirectory() as d:
            L.save(lib1, Path(d), 6000, tok)
        s1 = L.sha(lib1)
        names = lib1.hashes()
        calls = sol('def transform(grid):\n    return flip(upside(grid))\n', 't9', rnd=2, lib=names)
        redefine = sol(prog(FLIP, 'flip'), 't8', rnd=2, lib=names)   # redefines flip under the same hash
        self.assertEqual(calls.lib_calls, frozenset({'flip', 'upside'}))
        acc = H.accept([calls, redefine], lib1, tok)
        self.assertEqual(acc, [])
        lib2 = L.merge(lib1, acc, 2, [calls, redefine])
        by = lib2.by_name()
        self.assertEqual(by['flip'].calling_tasks, ['t1', 't2', 't3', 't8', 't9'])
        self.assertEqual(by['upside'].calling_tasks, ['t1', 't4', 't9'])
        self.assertEqual(by['big'].n_calling_tasks, 2)
        self.assertEqual(lib2.parent_sha, s1)
        self.assertEqual(lib2.round, 2)
        self.assertEqual(lib1.by_name()['flip'].n_calling_tasks, 3)   # prev untouched

    def test_library_dep_reuse_transitive(self):
        tok = StubTokenizer()
        A = 'def inc(v):\n    return v + 1\n\ndef inc_all(g):\n    return [[inc(c) for c in r] for r in g]\n'
        sols = [sol(prog(A, 'inc_all'), 't1'), sol(prog(A, 'inc_all'), 't2')]
        lib1 = L.merge(L.empty('STOCK'), H.accept(sols, L.empty('STOCK'), tok), 1, sols)
        self.assertEqual(lib1.by_name()['inc_all'].deps, ['inc'])
        s = sol('def transform(grid):\n    return inc_all(grid)\n', 't3', rnd=2, lib=lib1.hashes())
        lib2 = L.merge(lib1, [], 2, [s])
        self.assertIn('t3', lib2.by_name()['inc'].calling_tasks)
        py = L.render_py(lib2, ['inc_all'])
        self.assertLess(py.index('def inc('), py.index('def inc_all('))

    def test_merge_refuses_sealed(self):
        lib1, tok = round1()
        bad = H.build_solution('STOCK|sealed|k1|e1|s0', 'e1', 'def transform(grid):\n    return flip(grid)\n',
                               lib1.hashes())
        with self.assertRaises(H.SealedHelperRefused):
            L.merge(lib1, [], 2, [bad])


if __name__ == '__main__':
    unittest.main()
