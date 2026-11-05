import unittest

from _c_support import FixedTok, StubTokenizer, sid
from ratchet import helpers as H
from ratchet.library import empty

FLIP_A = '''
def flip_rows(grid):
    """reverse each row"""
    out = []
    for row in grid:  # walk rows
        out.append(row[::-1])
    return out

def transform(grid):
    return flip_rows(grid)
'''

FLIP_B = '''
def mirror(g: list) -> list:
    res = []
    for r in g:
        res.append(r[::-1])
    return res

def transform(x):
    y = mirror(x)
    return y
'''

FLIP_C = '''
def flip_rows(grid):
    out = []
    for row in grid:
        out.append(row[::-2])
    return out

def transform(grid):
    return flip_rows(grid)
'''


def prog(helper_src, call):
    return helper_src + f'\n\ndef transform(grid):\n    return {call}(grid)\n'


class TestCanonical(unittest.TestCase):
    def test_alpha_equivalent_share_hash(self):
        a = H.extract_helpers(FLIP_A, sid('t1'), 't1')
        b = H.extract_helpers(FLIP_B, sid('t2'), 't2')
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertEqual(a[0].hash, b[0].hash)
        self.assertEqual(a[0].canonical, b[0].canonical)
        self.assertIn('def h(a0):', a[0].canonical)
        self.assertNotIn('reverse', a[0].canonical)

    def test_different_code_differs(self):
        a = H.extract_helpers(FLIP_A, sid('t1'), 't1')[0]
        c = H.extract_helpers(FLIP_C, sid('t3'), 't3')[0]
        self.assertNotEqual(a.hash, c.hash)

    def test_callee_by_hash(self):
        p1 = '''
def inc(v):
    return v + 1

def inc_all(grid):
    return [[inc(c) for c in row] for row in grid]

def transform(grid):
    return inc_all(grid)
'''
        p2 = '''
def bump(q):
    return q + 1

def apply_bump(m):
    return [[bump(z) for z in r] for r in m]

def transform(grid):
    return apply_bump(grid)
'''
        p3 = p2.replace('q + 1', 'q + 2')
        h1 = {h.name: h for h in H.extract_helpers(p1, sid('a'), 'a')}
        h2 = {h.name: h for h in H.extract_helpers(p2, sid('b'), 'b')}
        h3 = {h.name: h for h in H.extract_helpers(p3, sid('c'), 'c')}
        self.assertEqual(h1['inc_all'].hash, h2['apply_bump'].hash)
        self.assertNotEqual(h1['inc_all'].hash, h3['apply_bump'].hash)   # callee body differs
        self.assertEqual(h1['inc_all'].deps, ('inc',))

    def test_keyword_and_attribute_names_kept(self):
        c, _ = H.canonicalize('def f(g):\n    return sorted(g, key=len).copy()\n')
        self.assertIn('key=len', c)
        self.assertIn('.copy()', c)


class TestExtraction(unittest.TestCase):
    def test_unbound_dropped_with_dependents(self):
        code = '''
K = 3

def uses_const(grid):
    return [r * K for r in grid]

def wraps(grid):
    return uses_const(grid)

def ok(grid):
    return [list(r) for r in grid]

def transform(grid):
    return ok(wraps(grid))
'''
        hs = H.extract_helpers(code, sid('t'), 't')
        self.assertEqual([h.name for h in hs], ['ok'])

    def test_undefined_name_dropped(self):
        code = prog('def f(g):\n    return mystery(g)\n', 'f')
        self.assertEqual(H.extract_helpers(code, sid('t'), 't'), [])

    def test_library_names_allowed(self):
        code = prog('def f(g):\n    return lib_rot(g)\n', 'f')
        self.assertEqual(H.extract_helpers(code, sid('t'), 't'), [])
        hs = H.extract_helpers(code, sid('t'), 't', frozenset({'lib_rot'}))
        self.assertEqual(hs[0].deps, ('lib_rot',))

    def test_allowed_import_attached(self):
        code = 'import numpy as np\nfrom collections import Counter\n' + prog(
            'def f(g):\n    c = Counter(x for r in g for x in r)\n    return np.array(g).tolist()\n', 'f')
        h = H.extract_helpers(code, sid('t'), 't')[0]
        self.assertTrue(h.source.startswith('import numpy as np\n') or h.source.startswith('from collections'))
        self.assertIn('import numpy as np', h.source)
        self.assertIn('from collections import Counter', h.source)

    def test_disallowed_import_dropped(self):
        code = 'import os\n' + prog('def f(g):\n    os.getcwd()\n    return g\n', 'f')
        self.assertEqual(H.extract_helpers(code, sid('t'), 't'), [])

    def test_dead_helper_not_extracted(self):
        code = 'def unused(g):\n    return g\n\n' + prog('def f(g):\n    return g[::-1]\n', 'f')
        self.assertEqual([h.name for h in H.extract_helpers(code, sid('t'), 't')], ['f'])
        self.assertEqual(len(H.extract_helpers(code, sid('t'), 't', reachable_only=False)), 2)

    def test_transform_not_a_helper_and_bad_code(self):
        self.assertEqual(H.extract_helpers('def transform(g):\n    return g\n', sid('t'), 't'), [])
        self.assertEqual(H.extract_helpers('def f(:', sid('t'), 't'), [])
        self.assertIsNone(H.build_solution(sid('t'), 't', 'def f(g):\n    return g\n'))


def sol(code, task, slot=0, rnd=1, phase='growth', lib=frozenset(), demo_pass=True):
    s = H.build_solution(sid(task, slot, rnd, phase=phase), task, code, lib, demo_pass=demo_pass)
    assert s is not None
    return s


HELP = 'def f(g):\n    return [r[::-1] for r in g]\n'


class TestAccept(unittest.TestCase):
    def test_two_task_rule(self):
        tok = StubTokenizer()
        one = H.accept([sol(prog(HELP, 'f'), 't1')], empty('STOCK'), tok)
        self.assertEqual(one, [])
        two = H.accept([sol(prog(HELP, 'f'), 't1'), sol(prog(HELP.replace('f(g)', 'g2(q)').replace('in g', 'in q'),
                                                             'g2'), 't2')], empty('STOCK'), tok)
        self.assertEqual(len(two), 1)
        self.assertEqual(two[0].accepted_by, 'both')   # k = 2 also gives MDL (2 - 1) x len >= 20
        two_only = H.accept([sol(prog(HELP, 'f'), 't1'), sol(prog(HELP, 'f'), 't2')], empty('STOCK'), FixedTok(5))
        self.assertEqual(two_only[0].accepted_by, 'two_tasks')   # MDL 5 < 20, so the task rule alone
        self.assertEqual(two[0].calling_tasks, ['t1', 't2'])
        self.assertTrue(two[0].verified)

    def test_demo_fail_ignored(self):
        tok = StubTokenizer()
        out = H.accept([sol(prog(HELP, 'f'), 't1'), sol(prog(HELP, 'f'), 't2', demo_pass=False)], empty('STOCK'), tok)
        self.assertEqual(out, [])

    def _two_solutions_one_task(self):
        p1 = prog(HELP, 'f')
        p2 = HELP + '\n\ndef transform(grid):\n    out = f(grid)\n    return out\n'
        s1, s2 = sol(p1, 't1', 0), sol(p2, 't1', 1)
        self.assertNotEqual(s1.prog_hash, s2.prog_hash)
        return [s1, s2]

    def test_mdl_19_rejects_20_accepts(self):
        sols = self._two_solutions_one_task()
        self.assertEqual(H.mdl_gain(sols[0].helpers[0], sols, FixedTok(19)), 19)
        self.assertEqual(H.accept(sols, empty('STOCK'), FixedTok(19)), [])
        acc = H.accept(sols, empty('STOCK'), FixedTok(20))
        self.assertEqual(len(acc), 1)
        self.assertEqual(acc[0].accepted_by, 'mdl')
        self.assertEqual(acc[0].mdl_gain, 20)

    def test_dedup_identical_programs(self):
        p = prog(HELP, 'f')
        sols = [sol(p, 't1', 0), sol(p + '\n# same program\n', 't1', 1)]
        self.assertEqual(len(H.dedup_solutions(sols)), 1)
        self.assertEqual(H.mdl_gain(sols[0].helpers[0], sols, FixedTok(100)), 0)
        self.assertEqual(H.accept(sols, empty('STOCK'), FixedTok(100)), [])

    def test_sealed_rows_refused(self):
        for phase in ('sealed', 'perturbed', 'knockout_delete', 'pilot', 'arcagi2'):
            s = H.build_solution(f'STOCK|{phase}|k1|t1|s0', 't1', prog(HELP, 'f'))
            with self.assertRaises(H.SealedHelperRefused):
                H.accept([s], empty('STOCK'), StubTokenizer())

    def test_deps_accepted_with_parent_and_renamed(self):
        p1 = '''
def inc(v):
    return v + 1

def inc_all(grid):
    return [[inc(c) for c in row] for row in grid]

def transform(grid):
    return inc_all(grid)
'''
        p2 = '''
def bump(q):
    return q + 1

def apply_bump(m):
    return [[bump(z) for z in r] for r in m]

def transform(grid):
    return apply_bump(grid)
'''
        # inc and bump share a hash, and so do inc_all and apply_bump: each is in 2 tasks
        acc = H.accept([sol(p1, 'a'), sol(p2, 'b')], empty('STOCK'), FixedTok(5))
        self.assertEqual({h.accepted_by for h in acc}, {'two_tasks'})
        acc = H.accept([sol(p1, 'a'), sol(p2, 'b')], empty('STOCK'), StubTokenizer())
        names = sorted(h.name for h in acc)
        self.assertEqual(names, ['inc', 'inc_all'])
        parent = [h for h in acc if h.name == 'inc_all'][0]
        self.assertEqual(parent.deps, ['inc'])
        # a dep used by one task only is accepted with its parent
        p3 = '''
def only_here(v):
    return v * 7

def par(grid):
    return [[only_here(c) for c in row] for row in grid]

def transform(grid):
    return par(grid)
'''
        # two distinct solutions of ONE task: par passes MDL (23 stub tokens), only_here alone would not (10 tokens)
        p4 = p3.replace('    return par(grid)', '    out = par(grid)\n    return out')
        tok = StubTokenizer()
        acc = {h.name: h for h in H.accept([sol(p3, 'x', 0), sol(p4, 'x', 1)], empty('STOCK'), tok)}
        self.assertEqual(set(acc), {'only_here', 'par'})
        self.assertEqual(acc['par'].accepted_by, 'mdl')
        self.assertEqual(acc['only_here'].accepted_by, 'dep')
        self.assertEqual(acc['par'].mdl_gain, 23)

    def test_name_collision_made_unique(self):
        f1 = 'def f(g):\n    return [r[::-1] for r in g]\n'
        f2 = 'def f(g):\n    return g[::-1]\n'
        acc = H.accept([sol(prog(f1, 'f'), 't1'), sol(prog(f1, 'f'), 't2'), sol(prog(f2, 'f'), 't3'),
                        sol(prog(f2, 'f'), 't4')], empty('STOCK'), StubTokenizer())
        names = sorted(h.name for h in acc)
        self.assertEqual(len(names), 2)
        self.assertEqual(len(set(names)), 2)
        for h in acc:
            self.assertIn(f'def {h.name}(', h.source)
            compile(h.source, '<t>', 'exec')

    def test_existing_hash_not_reaccepted(self):
        from ratchet.library import merge
        tok = StubTokenizer()
        sols = [sol(prog(HELP, 'f'), 't1'), sol(prog(HELP, 'f'), 't2')]
        acc = H.accept(sols, empty('STOCK'), tok)
        L1 = merge(empty('STOCK'), acc, 1, sols)
        sols2 = [sol(prog(HELP, 'f'), 't3', rnd=2), sol(prog(HELP, 'f'), 't4', rnd=2)]
        self.assertEqual(H.accept(sols2, L1, tok), [])


if __name__ == '__main__':
    unittest.main()
