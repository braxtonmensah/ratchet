"""Builder E: PREREG 6 gates and knockout libraries (on score outputs only)."""
import unittest
from dataclasses import dataclass, field

import ratchet  # noqa: F401
from ratchet import gates, knockout

try:
    from ratchet.library import Helper, Library  # builder C
except Exception:  # pragma: no cover
    @dataclass
    class Helper:
        name: str
        deps: list = field(default_factory=list)

    @dataclass
    class Library:
        arm: str
        round: int
        helpers: list
        parent_sha: object
        meta: dict


def H(name, deps=()):
    try:
        return Helper(name=name, hash='h_' + name, source=f'def {name}(g):\n    return g\n', canonical='',
                      token_len=5, deps=list(deps))
    except TypeError:
        return Helper(name=name, deps=list(deps))


def row(sid, code_sha, calls):
    return {'sample_id': sid, 'code_sha': code_sha, 'helper_calls': calls, 'demo_pass': True}


class TestCompare(unittest.TestCase):
    def test_compare(self):
        s = {'STOCK': frozenset(map(str, range(12))), 'FLATTTC': frozenset(['0', '1', 'x', 'y'])}
        c = gates.compare(s, 'STOCK', 'FLATTTC')
        self.assertEqual((c['b_only_a'], c['c_only_b'], c['net']), (10, 2, 8))
        self.assertAlmostEqual(c['p'], 79 / 4096)
        self.assertTrue(c['pass'])
        c2 = gates.compare(s, 'FLATTTC', 'STOCK')
        self.assertFalse(c2['pass'])

    def test_aa_pairs(self):
        aa = gates.aa_pairs({1: frozenset('ab'), 2: frozenset('bc'), 3: frozenset('abc')})
        self.assertEqual(len(aa), 3)
        self.assertEqual((aa[0]['b'], aa[0]['c']), (1, 1))


class TestReuse(unittest.TestCase):
    def test_programs_dedup_and_half(self):
        W = frozenset(['t1', 't2'])
        win = {'t1': [row('a', 'c1', {'h': 2}), row('b', 'c1', {}), row('c', 'c2', {})],
               't2': [row('d', 'c3', {'h': 1})]}
        g = gates.reuse_gate(W, win, frozenset(['h']))
        # programs: (t1,c1) calls (one of its rows calls), (t1,c2) no, (t2,c3) calls -> 2 of 3
        self.assertEqual((g['programs'], g['programs_calling']), (3, 2))
        self.assertTrue(g['pass'])
        self.assertEqual((g['samples'], g['samples_calling']), (4, 2))

    def test_exactly_half_passes_below_fails(self):
        W = frozenset(['t'])
        g = gates.reuse_gate(W, {'t': [row('a', 'c1', {'h': 1}), row('b', 'c2', {})]}, frozenset(['h']))
        self.assertTrue(g['pass'])
        g = gates.reuse_gate(W, {'t': [row('a', 'c1', {'h': 1}), row('b', 'c2', {}), row('c', 'c3', {})]},
                             frozenset(['h']))
        self.assertFalse(g['pass'])

    def test_unaccepted_or_zero_calls_do_not_count(self):
        W = frozenset(['t'])
        g = gates.reuse_gate(W, {'t': [row('a', 'c1', {'other': 3, 'h': 0})]}, frozenset(['h']))
        self.assertFalse(g['pass'])

    def test_empty(self):
        self.assertFalse(gates.reuse_gate(frozenset(), {}, frozenset(['h']))['pass'])
        self.assertEqual(gates.reuse_gate(frozenset(['t']), {}, frozenset())['reason'], 'NO_WINNER_ROWS')


class TestKnockoutGate(unittest.TestCase):
    def test_half_rule(self):
        W = frozenset('abcde')            # |W| = 5: at most 2 may survive each knockout
        self.assertTrue(gates.knockout_gate(W, frozenset('ab'), frozenset('a'))['pass'])
        g = gates.knockout_gate(W, frozenset('abc'), frozenset())
        self.assertFalse(g['pass'])
        self.assertFalse(g['pass_delete'])
        self.assertTrue(g['pass_inline'])
        W4 = frozenset('abcd')            # removing exactly half passes
        self.assertTrue(gates.knockout_gate(W4, frozenset('ab'), frozenset('cd'))['pass'])
        self.assertFalse(gates.knockout_gate(frozenset(), frozenset(), frozenset())['pass'])

    def test_solves_outside_W_ignored(self):
        self.assertTrue(gates.knockout_gate(frozenset('ab'), frozenset('xyz'), frozenset('a'))['pass'])


class TestContamination(unittest.TestCase):
    def test_rule(self):
        self.assertTrue(gates.contamination_gate(20, 10)['pass'])
        self.assertFalse(gates.contamination_gate(20, 9)['pass'])
        self.assertTrue(gates.contamination_gate(21, 11)['pass'])
        self.assertFalse(gates.contamination_gate(21, 10)['pass'])   # 10 < 10.5
        self.assertFalse(gates.contamination_gate(0, 5)['pass'])


class TestKnockoutLibraries(unittest.TestCase):
    def setUp(self):
        self.L = Library(arm='STOCK', round=4, helpers=[H('a'), H('b', ['a']), H('c'), H('d', ['b']), H('e')],
                         parent_sha=None, meta={})
        for h in self.L.helpers:
            h.in_context = h.name != 'e'     # 'e' was left out of context by the cap: never refilled by a knockout

    def test_called_and_closure(self):
        rows = [row('s1', 'x', {'a': 1, 'c': 0}), row('s2', 'y', {})]
        self.assertEqual(knockout.called_helpers(rows), frozenset(['a']))
        self.assertEqual(knockout.delete_closure(self.L, frozenset(['a'])), frozenset(['a', 'b', 'd']))

    def test_build_per_task(self):
        W = frozenset(['t1', 't2', 't3'])
        win = {'t1': [row('s1', 'x', {'c': 2})], 't2': [row('s2', 'y', {'b': 1})], 't3': []}
        libs = knockout.build_knockout_libraries(self.L, W, win)
        self.assertEqual(sorted(libs), ['t1', 't2', 't3'])
        names = {t: sorted(h.name for h in lib.helpers) for t, lib in libs.items()}
        self.assertEqual(names['t1'], ['a', 'b', 'd'])
        self.assertEqual(names['t2'], ['a', 'c'])
        self.assertEqual(names['t3'], ['a', 'b', 'c', 'd'])
        self.assertEqual(libs['t2'].meta['knockout_removed'], ['b', 'd'])
        self.assertEqual(len(self.L.helpers), 5)          # the source library is not mutated
        self.assertEqual(knockout.ko_marker('delete', 't2', ['b', 'd']), 'LEVER KO_DELETE task=t2 removed=b,d')
        self.assertEqual(knockout.ko_marker('inline', 't2', ['b', 'd']), 'LEVER KO_INLINE task=t2 callable=0 inlined=b,d')

    def test_inline_text_is_only_the_knocked_out_helpers(self):
        # PREREG 6.3b (review fix 2026-11-04): the called helpers and their dependents become non-callable text; the
        # rest of L_R stays callable (the delete-mode set)
        gone = knockout.delete_closure(self.L, frozenset(['b']))
        txt = knockout.inline_text_library(self.L, gone, 't2')
        self.assertEqual(sorted(h.name for h in txt.helpers), ['b', 'd'])
        self.assertEqual(txt.meta['knockout_mode'], 'inline')

    def test_inline_keeps_all(self):
        il = knockout.inline_library(self.L)
        self.assertEqual([h.name for h in il.helpers], ['a', 'b', 'c', 'd', 'e'])
        self.assertEqual(il.meta['knockout_mode'], 'inline')


if __name__ == '__main__':
    unittest.main()
