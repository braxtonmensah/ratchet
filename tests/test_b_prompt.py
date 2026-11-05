"""Builder B: prompt.py and tok.py (SPEC 11 test_prompt.py row). CPU only, no model calls."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratchet import prompt                                    # noqa: E402
from ratchet.tok import StubTokenizer, load_tokenizer         # noqa: E402
from ratchet.types import Pair, Task                          # noqa: E402

try:
    from ratchet.library import Helper, Library                # builder C
except ImportError:                                           # pragma: no cover
    Helper = Library = None

TOK = StubTokenizer()


def G(*rows):
    return tuple(tuple(int(c) for c in r) for r in rows)


def make_task(tid='t0001', test_out=G('77', '77')):
    return Task(id=tid, split='growth', train=(Pair(G('12', '34'), G('21', '43')), Pair(G('56'), G('65'))),
                test_inputs=(G('89', '98'),), test_outputs=(test_out,), src_sha256='0' * 64)


def H(name, source=None, n_calling=2, deps=(), token_len=None):
    src = source if source is not None else f'def {name}(g):\n    return [list(r) for r in g]\n'
    tl = TOK.count(src) if token_len is None else token_len
    if Helper is None:
        from types import SimpleNamespace
        return SimpleNamespace(name=name, source=src, deps=list(deps), n_calling_tasks=n_calling, token_len=tl)
    return Helper(name=name, hash=name + '_h', source=src, canonical=src, token_len=tl, deps=list(deps),
                  calling_tasks=[f'c{i}' for i in range(n_calling)], n_calling_tasks=n_calling)


def L(helpers, arm='STOCK', round=1):
    if Library is None:
        from types import SimpleNamespace
        return SimpleNamespace(arm=arm, round=round, helpers=list(helpers), parent_sha=None, meta={})
    return Library(arm=arm, round=round, helpers=list(helpers), parent_sha=None, meta={})


def body(size, name):
    lines = [f'def {name}(g):', '    out = []']
    lines += [f'    x{i} = len(g) + {i}' for i in range(size)]
    lines.append('    return g')
    return '\n'.join(lines) + '\n'


class TestTaskBlock(unittest.TestCase):
    def test_format_and_no_test_output(self):
        t = make_task()
        tb = prompt.task_block(t)
        self.assertTrue(tb.startswith('Example 1\nInput:\n12\n34\nOutput:\n21\n43'))
        self.assertIn('Example 2\nInput:\n56\nOutput:\n65', tb)
        self.assertTrue(tb.endswith('Test input:\n89\n98'))
        pb = prompt.build_messages(t, TOK)
        for m in pb.messages:
            self.assertNotIn('77\n77', m['content'])
            self.assertNotIn('7', m['content'].split('Test input:')[-1].split('Write')[0])

    def test_multi_test_labels(self):
        t = Task(id='x', split='growth', train=(Pair(G('1'), G('2')),), test_inputs=(G('3'), G('4')),
                 test_outputs=None, src_sha256='0' * 64)
        tb = prompt.task_block(t)
        self.assertIn('Test input 1:\n3', tb)
        self.assertIn('Test input 2:\n4', tb)


class TestLibraryBlock(unittest.TestCase):
    def test_empty_library_identical_to_none(self):
        t = make_task()
        a = prompt.build_messages(t, TOK)
        b = prompt.build_messages(t, TOK, library=L([]))
        c = prompt.build_messages(t, TOK, exemplars=[])
        self.assertEqual(a.messages, b.messages)
        self.assertEqual(a.messages, c.messages)
        self.assertEqual((b.library_tokens, b.helpers_in_context, b.block_kind), (0, (), 'none'))

    def test_rank_order_and_block_first(self):
        lib = L([H('aa_low', n_calling=1), H('bb_high', n_calling=5), H('cc_mid', n_calling=3)])
        text, names, ntok = prompt.library_block(lib, 6000, TOK)
        self.assertEqual(names, ('bb_high', 'cc_mid', 'aa_low'))
        self.assertTrue(text.startswith(prompt.CALLABLE_HEADER))
        self.assertLess(text.index('def bb_high'), text.index('def cc_mid'))
        self.assertEqual(ntok, TOK.count(text))
        pb = prompt.build_messages(make_task(), TOK, library=lib)
        self.assertTrue(pb.messages[1]['content'].startswith(prompt.CALLABLE_HEADER))
        self.assertEqual(pb.messages[0]['content'], prompt.SYSTEM)
        self.assertEqual(pb.block_kind, 'callable')
        self.assertEqual(pb.library_tokens, ntok)
        self.assertIsNotNone(pb.lib_sha)

    def test_dep_closure_deps_first(self):
        base = H('base_fn', n_calling=0)
        top = H('top_fn', source='def top_fn(g):\n    return base_fn(g)\n', n_calling=9, deps=['base_fn'])
        text, names, _ = prompt.library_block(L([top, base]), 6000, TOK)
        self.assertEqual(names, ('base_fn', 'top_fn'))
        self.assertLess(text.index('def base_fn'), text.index('def top_fn'))

    def test_closure_must_fit_whole(self):
        big_dep = H('big_dep', source=body(200, 'big_dep'), n_calling=0)
        top = H('top_fn', source='def top_fn(g):\n    return big_dep(g)\n', n_calling=9, deps=['big_dep'])
        small = H('small_fn', n_calling=1)
        cap = TOK.count(prompt._render_library(prompt.CALLABLE_HEADER, [top.source, small.source])) + 5
        text, names, ntok = prompt.library_block(L([top, big_dep, small]), cap, TOK)
        self.assertEqual(names, ('small_fn',))   # top cannot come without big_dep; skip and continue
        self.assertLessEqual(ntok, cap)

    def test_cap_greedy_continue(self):
        hs = [H('huge', source=body(3000, 'huge'), n_calling=50)]
        hs += [H(f'h{i:03d}', source=body(i % 37 + 1, f'h{i:03d}'), n_calling=10 - i % 10) for i in range(400)]
        lib = L(hs)
        text, names, ntok = prompt.library_block(lib, 6000, TOK)
        self.assertLessEqual(ntok, 6000)
        self.assertEqual(ntok, TOK.count(text))
        self.assertNotIn('huge', names)
        self.assertGreater(len(names), 20)
        # nothing left out would still fit
        chosen = set(names)
        for h in hs:
            if h.name in chosen:
                continue
            srcs = [x.source for x in prompt._rank(lib) if x.name in chosen or x.name == h.name]
            trial = prompt._render_library(prompt.CALLABLE_HEADER, srcs)
            self.assertGreater(TOK.count(trial), 6000, h.name)

    def test_drop_and_missing_dep(self):
        a = H('a_fn', n_calling=5)
        b = H('b_fn', source='def b_fn(g):\n    return a_fn(g)\n', n_calling=4, deps=['a_fn'])
        c = H('c_fn', source='def c_fn(g):\n    return ghost(g)\n', n_calling=3, deps=['ghost'])
        d = H('d_fn', n_calling=1)
        _, names, _ = prompt.library_block(L([a, b, c, d]), 6000, TOK)
        self.assertEqual(names, ('a_fn', 'b_fn', 'd_fn'))   # c_fn needs a missing helper
        _, names, _ = prompt.library_block(L([a, b, c, d]), 6000, TOK, drop=frozenset({'a_fn'}))
        self.assertEqual(names, ('d_fn',))                  # b_fn depends on the dropped a_fn

    def test_inline_header(self):
        lib = L([H('a_fn')])
        text, names, _ = prompt.library_block(lib, 6000, TOK, inline_noncallable=True)
        self.assertTrue(text.startswith(prompt.INLINE_HEADER))
        pb = prompt.build_messages(make_task(), TOK, library=lib, inline_noncallable=True)
        self.assertEqual(pb.block_kind, 'inline')
        self.assertNotIn(prompt.CALLABLE_HEADER, pb.messages[1]['content'])

    def test_cache_returns_same(self):
        lib = L([H('a_fn'), H('b_fn', n_calling=1)])
        r1 = prompt.library_block(lib, 6000, TOK)
        r2 = prompt.library_block(lib, 6000, TOK)
        self.assertEqual(r1, r2)


class TestExemplarBlock(unittest.TestCase):
    def _ex(self, task, sid, code):
        from types import SimpleNamespace
        return SimpleNamespace(task=task, sample_id=sid, code=code, token_len=TOK.count(code), features=())

    def test_exemplar_cap_and_ids(self):
        e1 = self._ex('n1', 'STOCK|growth|r1|n1|s0', 'def transform(grid):\n    return grid\n')
        e2 = self._ex('n2', 'STOCK|growth|r1|n2|s3', body(3000, 'transform'))
        e3 = self._ex('n3', 'STOCK|growth|r1|n3|s1', 'def transform(grid):\n    return grid[::-1]\n')
        pb = prompt.build_messages(make_task(), TOK, exemplars=[e1, e2, e3])
        self.assertEqual(pb.exemplar_ids, ('STOCK|growth|r1|n1|s0', 'STOCK|growth|r1|n3|s1'))
        self.assertEqual(pb.exemplar_tasks, ('n1', 'n3'))
        self.assertLessEqual(pb.exemplar_tokens, 6000)
        self.assertEqual(pb.block_kind, 'exemplar')
        self.assertTrue(pb.messages[1]['content'].startswith('Verified programs'))

    def test_own_task_refused_and_both_refused(self):
        own = self._ex('t0001', 's', 'def transform(grid):\n    return grid\n')
        with self.assertRaises(ValueError):
            prompt.build_messages(make_task('t0001'), TOK, exemplars=[own])
        other = self._ex('zz', 's', 'def transform(grid):\n    return grid\n')
        with self.assertRaises(ValueError):
            prompt.build_messages(make_task(), TOK, library=L([H('a')]), exemplars=[other])


def _real_tokenizer():
    if os.environ.get('RATCHET_NO_REAL_TOK'):
        return None
    try:
        from ratchet import config
        d = Path(getattr(config, 'MODEL_DIR'))
    except Exception:
        return None
    try:
        return load_tokenizer(d)
    except (ImportError, OSError):
        return None


class TestRealTokenizer(unittest.TestCase):
    def setUp(self):
        self.tok = _real_tokenizer()
        if self.tok is None:
            self.skipTest('tokenizers or model tokenizer.json not available')

    def test_counts_digits(self):
        n = self.tok.count('0123456789')
        self.assertEqual(n, 10, 'grid digits are expected to be one token each (SPEC 1.2)')

    def test_block_under_cap_and_estimate_is_exact(self):
        hs = [H(f'helper_{i:03d}', source=body(i % 23 + 1, f'helper_{i:03d}'), n_calling=8 - i % 8,
                token_len=i % 23 + 10) for i in range(500)]
        lib = L(hs)
        text, names, ntok = prompt.library_block(lib, 6000, self.tok)
        self.assertLessEqual(ntok, 6000)
        self.assertEqual(ntok, self.tok.count(text))
        # the additive pre-filter must not change the choice versus exact-only greedy
        old = dict(prompt._DEFAULTS)
        # config.py now defines PROMPT_EST_MARGIN_BASE (integration pass) and config wins over _DEFAULTS: patch both,
        # or the "exact-only" run silently reuses the default margin and the comparison is vacuous
        from unittest import mock
        _pc = mock.patch.object(prompt._config, 'PROMPT_EST_MARGIN_BASE', 10 ** 9, create=True)
        _pc.start()
        try:
            prompt._DEFAULTS['PROMPT_EST_MARGIN_BASE'] = 10 ** 9
            prompt._CACHE.clear()
            self.assertEqual(prompt._cfg('PROMPT_EST_MARGIN_BASE'), 10 ** 9)
            _, names_exact, _ = prompt.library_block(lib, 6000, self.tok)
        finally:
            _pc.stop()
            prompt._DEFAULTS.clear()
            prompt._DEFAULTS.update(old)
            prompt._CACHE.clear()
        self.assertEqual(names, names_exact)


if __name__ == '__main__':
    unittest.main()
