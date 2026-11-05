import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from _c_support import StubTokenizer, make_task, sid
from ratchet import exemplar as E
from ratchet import helpers as H
from ratchet import library as L
from ratchet import plant as P
from ratchet import sham as S


def prog(helper_src, call):
    return helper_src + f'\n\ndef transform(grid):\n    return {call}(grid)\n'


def _variants(n):
    """n distinct dep-free helpers of a few genres and sizes."""
    out = []
    for i in range(n):
        k = i % 4
        pad = ''.join(f'    v{j} = {i} + {j}\n' for j in range(i % 7))
        if k == 0:
            src = f'def a{i}(g):\n{pad}    return [[(c + {i}) % 10 for c in r] for r in g]\n'
        elif k == 1:
            src = f'def b{i}(g):\n{pad}    return sum(1 for r in g for c in r if c == {i % 10})\n'
        elif k == 2:
            src = f'def c{i}(g, x):\n{pad}    return x > {i}\n'
        else:
            src = f'def d{i}(g):\n{pad}    return (len(g), len(g[0]) + {i})\n'
        out.append(src)
    return out


def target_library(tok):
    srcs = _variants(8)
    sols = []
    for i, s in enumerate(srcs):
        name = s.split('(')[0][4:]
        call = name if '(g, x)' not in s else f'(lambda q: [[int({name}(q, 0))]])'
        code = s + f'\n\ndef transform(grid):\n    return {call}(grid)\n' if '(g, x)' not in s else \
            s + f'\n\ndef transform(grid):\n    return [[int({name}(grid, 0))]]\n'
        sols += [H.build_solution(sid(f't{i}a'), f't{i}a', code), H.build_solution(sid(f't{i}b'), f't{i}b', code)]
    acc = H.accept(sols, L.empty('STOCK'), tok)
    lib = L.merge(L.empty('STOCK'), acc, 1, sols)
    with tempfile.TemporaryDirectory() as d:
        L.save(lib, Path(d), 6000, tok)
    return lib


def failed_helpers(n, offset=100):
    out = []
    for i, s in enumerate(_variants(n)):
        s = s.replace(f'{i}', f'{i + offset}', 1)  # rename -> distinct names
        name = s.split('(')[0][4:]
        code = s + (f'\n\ndef transform(grid):\n    return {name}(grid)\n' if '(g, x)' not in s else
                    f'\n\ndef transform(grid):\n    return [[int({name}(grid, 3))]]\n')
        hs = H.extract_helpers(code.replace(f'+ {i})', f'+ {i + 50})'), sid(f'f{i}', rnd=2), f'f{i}')
        out += hs
    return out


class TestSham(unittest.TestCase):
    def test_count_tokens_genre_and_no_accepted_hash(self):
        tok = StubTokenizer()
        tgt = target_library(tok)
        n_tgt = sum(h.in_context for h in tgt.helpers)
        self.assertEqual(n_tgt, 8)
        pool = failed_helpers(40)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            sham = S.build_sham(tgt, pool, [], tok, seed=1, exclude_hashes=[h.hash for h in tgt.helpers],
                                print_lever=True)
        self.assertRegex(buf.getvalue(), r'LEVER SHAM matched=\d+ of \d+ tokens=\d+ target=\d+ verified=0')
        self.assertEqual(len(sham.helpers), n_tgt)
        _, names, ntok = L.in_context(sham, 6000, tok)
        self.assertEqual(len(names), n_tgt)
        target_tokens = tgt.meta['in_context_tokens']
        self.assertLessEqual(abs(ntok - target_tokens), 0.05 * target_tokens)
        acc = {h.hash for h in tgt.helpers}
        self.assertFalse(acc & {h.hash for h in sham.helpers})
        self.assertTrue(all(not h.verified for h in sham.helpers))
        self.assertEqual(len({h.name for h in sham.helpers}), n_tgt)
        self.assertGreaterEqual(sham.meta['matched'], 1)
        for h in sham.helpers:
            compile(h.source, '<s>', 'exec')
        # deterministic in the seed
        with contextlib.redirect_stdout(io.StringIO()):
            again = S.build_sham(tgt, pool, [], tok, seed=1)
        self.assertEqual([h.hash for h in again.helpers], [h.hash for h in sham.helpers])

    def test_pool_too_small(self):
        tok = StubTokenizer()
        tgt = target_library(tok)
        small = failed_helpers(3)
        # below the 95% trigger with no shuffled pool: a partial library asks the caller for the shuffled pool
        part = S.build_sham(tgt, small, None, tok, seed=1)
        self.assertTrue(part.meta['partial'])
        self.assertTrue(part.meta['needs_shuffled'])
        self.assertLess(len(part.helpers), 0.95 * 8)
        # the shuffled pool given but still too small: loud failure
        with self.assertRaises(S.ShamMatchFailed):
            S.build_sham(tgt, small, [], tok, seed=1)
        # retry with a shuffled pool large enough: full count, some slots from the shuffled pool
        shuffled = failed_helpers(40, offset=300)
        full = S.build_sham(tgt, small, shuffled, tok, seed=1)
        self.assertEqual(len(full.helpers), 8)
        self.assertFalse(full.meta['partial'])
        self.assertTrue(full.meta['used_shuffled'])

    def test_genre(self):
        g = S.genre(H.extract_helpers(prog('def f(g):\n    return [list(r) for r in g]\n', 'f'), sid('t'), 't')[0],
                    StubTokenizer())
        self.assertEqual(g[:4], (1, 'grid', True, False))
        g2 = S.genre(H.extract_helpers(prog('def f(g, c):\n    return c in g[0]\n', 'f'), sid('t'), 't')[0])
        self.assertEqual(g2[:4], (2, 'bool', False, False))

    def test_failed_pool_reads_demo_fail_only(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d) / 'arms' / 'STOCK' / 'round_1'
            rd.mkdir(parents=True)
            good = prog('def ok(g):\n    return g\n', 'ok')
            bad = prog('def broken(g):\n    return g[1:]\n', 'broken')
            rows = [{'sample_id': sid('t1', 0), 'task': 't1', 'code': good},
                    {'sample_id': sid('t1', 1), 'task': 't1', 'code': bad}]
            (rd / 'samples.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n{"torn":')
            ex = [{'sample_id': sid('t1', 0), 'status': 'OK', 'demo_pass': True},
                  {'sample_id': sid('t1', 1), 'status': 'DEMO_FAIL', 'demo_pass': False}]
            (rd / 'exec.jsonl').write_text('\n'.join(json.dumps(r) for r in ex) + '\n')
            pool = S.failed_pool(Path(d))
            self.assertEqual([h.name for h in pool], ['broken'])


def tasks6():
    a = make_task('aaaa0001', [([[1, 0], [0, 1]], [[0, 1], [1, 0]])])
    b = make_task('aaaa0002', [([[1, 0], [0, 2]], [[0, 1], [2, 0]])])
    c = make_task('bbbb0001', [([[5] * 6] * 6, [[5]])])
    d = make_task('bbbb0002', [([[5] * 5] * 6, [[5]])])
    e = make_task('cccc0001', [([[3, 3, 3]], [[3], [3], [3]])])
    return {t.id: t for t in (a, b, c, d, e)}


class TestExemplar(unittest.TestCase):
    def test_features_shape(self):
        t = tasks6()['aaaa0001']
        f = E.demo_features(t)
        self.assertEqual(f.shape, (E.N_FEATURES,))
        self.assertEqual(E.N_FEATURES, 38)
        self.assertEqual(f[5], 1.0)          # same shape
        self.assertAlmostEqual(f[6] + f[7], 1.0)  # colours 0 and 1 half each

    def test_neighbours_exclude_self_and_nearest(self):
        ts = tasks6()
        pool = [E.Exemplar(task=t, sample_id=sid(t), code='def transform(g):\n    return g\n', token_len=10,
                           features=tuple(E.demo_features(ts[t]))) for t in sorted(ts)]
        sc = E.Scaler.fit(list(ts.values()))
        nb = E.neighbours(ts['aaaa0001'], pool, sc, k=3)
        self.assertNotIn('aaaa0001', [e.task for e in nb])
        self.assertEqual(nb[0].task, 'aaaa0002')
        self.assertEqual(len(nb), 3)
        nb2 = E.neighbours(ts['bbbb0001'], pool, sc, k=1, exclude_task='bbbb0002')
        self.assertNotIn(nb2[0].task, ('bbbb0001', 'bbbb0002'))

    def test_pool_from_rounds_shortest_and_shared(self):
        ts = tasks6()
        with tempfile.TemporaryDirectory() as d:
            r1 = Path(d) / 'arms' / 'STOCK' / 'round_1'
            r1.mkdir(parents=True)
            long_ = 'def transform(grid):\n    out = grid\n    return out\n'
            short = 'def transform(grid):\n    return grid\n'
            samples = [{'sample_id': sid('aaaa0001', 0), 'task': 'aaaa0001', 'phase': 'growth', 'code': long_},
                       {'sample_id': sid('aaaa0001', 1), 'task': 'aaaa0001', 'phase': 'growth', 'code': short},
                       {'sample_id': sid('bbbb0001', 0), 'task': 'bbbb0001', 'phase': 'growth', 'code': short},
                       {'sample_id': sid('cccc0001', 0), 'task': 'cccc0001', 'phase': 'growth', 'code': short}]
            execs = [{'sample_id': sid('aaaa0001', 0), 'status': 'OK', 'demo_pass': True},
                     {'sample_id': sid('aaaa0001', 1), 'status': 'OK', 'demo_pass': True},
                     {'sample_id': sid('bbbb0001', 0), 'status': 'OK', 'demo_pass': True},
                     {'sample_id': sid('cccc0001', 0), 'status': 'DEMO_FAIL', 'demo_pass': False}]
            (r1 / 'samples.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in samples))
            (r1 / 'exec.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in execs))
            ex1 = Path(d) / 'arms' / 'EXEMPLAR' / 'round_1'
            ex1.mkdir(parents=True)
            (ex1 / 'round_state.json').write_text(json.dumps({'shared_from': 'STOCK/round_1'}))
            pool = E.pool_from_rounds(Path(d), 'EXEMPLAR', 1, tasks=ts)
            self.assertEqual([e.task for e in pool], ['aaaa0001', 'bbbb0001'])
            self.assertEqual(pool[0].code, short)
            p = Path(d) / 'pool_R.json'
            s = E.save_pool(pool, p, E.Scaler.fit(list(ts.values())))
            back, sc, _ = E.load_pool(p)
            self.assertEqual([e.sample_id for e in back], [e.sample_id for e in pool])
            self.assertEqual(len(s), 64)


DSL = '''from arc_types import *


def identity(
    x: Any
) -> Any:
    """ identity function """
    return x


def add(a: Numerical, b: Numerical) -> Numerical:
    """ addition """
    return a + b


def double(a: Integer) -> Integer:
    """ twice """
    return add(a, a)


def vmirror(grid: Grid) -> Grid:
    """ mirroring along vertical """
    return tuple(row[::-1] for row in grid)


def hmirror(grid: Grid) -> Grid:
    """ mirroring along horizontal """
    return grid[::-1]


def rot180(grid: Grid) -> Grid:
    """ half rotation """
    return tuple(tuple(row[::-1]) for row in grid[::-1])


def huge(grid: Grid) -> Grid:
    """ a long unused primitive """
''' + ''.join(f'    grid = tuple(tuple((c + {i}) % 10 for c in r) for r in grid)\n' for i in range(40)) + '''    return grid
'''

CONSTS = 'F = False\nT = True\nZERO = 0\nTHREE = 3\nORIGIN = (0, 0)\n'
TYPES = 'from typing import (\n    Tuple,\n    Union,\n    Any\n)\n\nInteger = int\nIntegerTuple = Tuple[Integer, Integer]\n' \
        'Numerical = Union[Integer, IntegerTuple]\nGrid = Tuple[Tuple[Integer]]\n'
SOLVERS = '''from dsl import *
from constants import *


def solve_00000001(I):
    O = vmirror(I)
    return O


def solve_00000002(I):
    x1 = hmirror(I)
    O = vmirror(x1)
    return O


def solve_00000003(I):
    O = rot180(I)
    return O


def solve_00000004(I):
    x1 = double(THREE)
    O = hmirror(I)
    return O


def solve_00000005(I):
    O = vmirror(I)
    return O
'''


def write_dsl(d: Path):
    (d / 'dsl.py').write_text(DSL)
    (d / 'constants.py').write_text(CONSTS)
    (d / 'arc_types.py').write_text(TYPES)
    (d / 'solvers.py').write_text(SOLVERS)


class TestPlant(unittest.TestCase):
    def test_parse_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            write_dsl(Path(d))
            src = P.load_arcdsl(Path(d))
        self.assertEqual(src.solver_calls['vmirror'], {'00000001', '00000002', '00000005'})
        self.assertEqual(src.solver_calls['hmirror'], {'00000002', '00000004'})
        self.assertEqual(src.deps['double'], {'add'})
        self.assertIn("'Numerical'", src.primitives['add'])
        self.assertNotIn('THREE', src.deps.get('double', set()))
        for s in src.primitives.values():
            exec(compile(s, '<p>', 'exec'), {})    # runs without arc_types

    def test_tranches_cumulative_capped_mod_R(self):
        tok = StubTokenizer()
        with tempfile.TemporaryDirectory() as d:
            write_dsl(Path(d))
            src = P.load_arcdsl(Path(d))
        full = P._full_library(src, tok, 'PLANTDRIP')
        n_huge = full.by_name()['huge'].token_len
        _, _, n_all = L.in_context(full, 100000, tok)
        cap = n_all - n_huge // 2                      # everything but `huge` fits
        libs = P.build_tranches(src, 2, cap, tok)
        self.assertEqual(len(libs), 2)
        n1 = {h.name for h in libs[0].helpers}
        n2 = {h.name for h in libs[1].helpers}
        self.assertLess(n1, n2)                         # cumulative, strictly growing
        self.assertNotIn('huge', n2)                    # capped out
        # rank: vmirror (3 tasks), hmirror (2), add (1 via double? no: solvers name double), double (1), rot180 (1)
        order = [h.name for h in L.rank(full) if h.name in n2 and h.name in src.primitives]
        self.assertEqual(order[0], 'vmirror')
        self.assertEqual(order[1], 'hmirror')
        self.assertIn('vmirror', n1)
        self.assertNotIn('hmirror', n1)                 # rank 1 -> tranche 1 (0-based) with R = 2
        for lib in libs:
            if 'double' in {h.name for h in lib.helpers}:
                self.assertIn('add', {h.name for h in lib.helpers})   # dep closure
            _, names, ntok = L.in_context(lib, cap, tok)
            self.assertEqual(set(names), {h.name for h in lib.helpers})
            self.assertLessEqual(ntok, cap)
        self.assertEqual(libs[0].meta['tranche'], 1)

    @unittest.skipUnless(os.environ.get('RATCHET_ARCDSL_DIR'), 'set RATCHET_ARCDSL_DIR to a real arc-dsl clone')
    def test_real_arcdsl(self):
        tok = StubTokenizer()
        src = P.load_arcdsl(Path(os.environ['RATCHET_ARCDSL_DIR']))
        self.assertGreater(len(src.primitives), 100)
        n_solvers = len({t for s in src.solver_calls.values() for t in s})
        self.assertGreaterEqual(n_solvers, 390)
        libs = P.build_tranches(src, 4, 6000, tok)
        sizes = [len(l.helpers) for l in libs]
        self.assertEqual(sizes, sorted(sizes))
        for lib in libs:
            _, names, ntok = L.in_context(lib, 6000, tok)
            self.assertLessEqual(ntok, 6000)
            self.assertEqual(set(names), {h.name for h in lib.helpers})
            ns = {}
            exec(compile(L.render_py(lib, [h.name for h in lib.helpers]), '<plant>', 'exec'), ns)
        print(f'REAL_ARCDSL primitives={len(src.primitives)} solvers={n_solvers} sizes={sizes} '
              f'tokens={[L.in_context(l, 6000, tok)[2] for l in libs]} commit={src.commit}')


if __name__ == '__main__':
    unittest.main()
