"""Builder D: FLAT-TTC token match on a synthetic ledger (SPEC 11 test_budget)."""
from __future__ import annotations

import unittest

from ratchet import budget


def row(arm, phase, rid, n, prompt, gen, seed=None, logical=True):
    r = {'arm': arm, 'phase': phase, 'request_id': rid, 'n': n, 'prompt_tokens': prompt, 'gen_tokens': gen,
         'sealed_seed': seed}
    if logical:
        r['prompt_tokens_logical'] = prompt * n
    return r


IDS = ['t%03d' % i for i in range(400)]


class TestBudget(unittest.TestCase):
    def rows(self):
        return [
            row('STOCK', 'growth', 'STOCK|growth|r1|a|b0', 4, 7500, 4000),          # 30000 + 4000
            row('STOCK', 'growth', 'STOCK|growth|r2|a|b0', 4, 7500, 4000, logical=False),   # fallback prompt x n
            row('STOCK', 'sealed', 'STOCK|sealed|k1|a|b0', 4, 7500, 4000, seed=1),
            row('STOCK', 'sealed', 'STOCK|sealed|k2|a|b0', 4, 9999, 9999, seed=2),   # other seed: ignored
            row('STATIC', 'growth', 'STATIC|growth|r2|a|b0', 4, 7500, 4000),          # other arm: ignored
            row('FLATTTC', 'sealed', 'FLATTTC|sealed|k1|a|b0', 4, 1500, 4000, seed=1),   # 6000 + 4000 over 4
            row('FLATTTC', 'sealed', 'FLATTTC|sealed|k1|b|b0', 4, 1500, 4000, seed=1),
            row('FLATTTC', 'sealed', 'FLATTTC|sealed|k1|a|x0', 16, 1500, 9000, seed=1),  # extra: not in m_flat
            row('STOCK', 'perturbed', 'STOCK|perturbed|k1|a|b0', 4, 7500, 2000, seed=1),
            row('FLATTTC', 'perturbed', 'FLATTTC|perturbed|k1|a|b0', 2, 1000, 500, seed=1),
        ]

    def test_target_mflat_extra(self):
        fb = budget.compute(self.rows(), 1, 'sealed', IDS)
        self.assertEqual(fb.stock_growth_tokens, 68000)
        self.assertEqual(fb.stock_sealed_tokens, 34000)
        self.assertEqual(fb.target_tokens, 102000)
        self.assertEqual(fb.flat_base_samples, 8)
        self.assertEqual(fb.m_flat, 20000 / 8)                       # 2500 logical tokens per sample
        self.assertEqual(fb.n_extra, round(102000 / 2500))            # 40.8 -> 41
        self.assertEqual(fb.n_extra, 41)
        self.assertEqual(sum(fb.per_task.values()), 41)
        self.assertEqual(fb.per_task['t000'], 1)
        self.assertEqual(fb.per_task['t040'], 1)
        self.assertEqual(fb.per_task['t041'], 0)

    def test_allocation_remainder_to_first_sorted(self):
        alloc = budget.allocate(1203, list(reversed(IDS)))
        self.assertEqual(sum(alloc.values()), 1203)
        self.assertEqual(alloc['t000'], 4)
        self.assertEqual(alloc['t002'], 4)
        self.assertEqual(alloc['t003'], 3)
        self.assertEqual(alloc['t399'], 3)

    def test_half_up(self):
        self.assertEqual(budget.round_half_up(2.5), 3)
        self.assertEqual(budget.round_half_up(3.5), 4)
        self.assertEqual(budget.round_half_up(3.49), 3)

    def test_perturbed_retargets_from_perturbed_stock(self):
        fb = budget.compute(self.rows(), 1, 'perturbed', IDS)
        self.assertEqual(fb.target_tokens, 68000 + 32000)
        self.assertEqual(fb.m_flat, 2500 / 2)
        self.assertEqual(fb.n_extra, 80)

    def test_missing_rows_refuse(self):
        with self.assertRaises(budget.BudgetError):
            budget.compute(self.rows(), 3, 'sealed', IDS)
        with self.assertRaises(budget.BudgetError):
            budget.compute([r for r in self.rows() if r['arm'] != 'FLATTTC'], 1, 'sealed', IDS)

    def test_realized(self):
        real = budget.realized_tokens(self.rows(), 1, 'sealed')
        self.assertEqual(real, {'base': 20000, 'extra': 24000 + 9000, 'base_samples': 8, 'extra_samples': 16})

    def test_roundtrip(self):
        fb = budget.compute(self.rows(), 1, 'sealed', IDS)
        self.assertEqual(budget.FlatBudget.from_dict(fb.to_dict()), fb)


if __name__ == '__main__':
    unittest.main()
