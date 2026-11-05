"""Builder E: exact McNemar, Clopper-Pearson, power Monte Carlo (SPEC 11 test_stats)."""
import math
import unittest

import ratchet  # noqa: F401
from ratchet.stats import binom_cdf, clopper_pearson, critical_b, mcnemar_exact_one_sided, power_mc


class TestMcNemar(unittest.TestCase):
    def test_spec_value(self):
        self.assertEqual(mcnemar_exact_one_sided(10, 2), 79 / 4096)
        self.assertAlmostEqual(mcnemar_exact_one_sided(10, 2), 0.019287, places=6)

    def test_equal_counts_not_significant(self):
        for b in range(0, 40):
            self.assertGreaterEqual(mcnemar_exact_one_sided(b, b), 0.5)

    def test_edges(self):
        self.assertEqual(mcnemar_exact_one_sided(0, 0), 1.0)
        self.assertEqual(mcnemar_exact_one_sided(5, 0), 1 / 32)
        self.assertEqual(mcnemar_exact_one_sided(0, 5), 1.0)
        with self.assertRaises(ValueError):
            mcnemar_exact_one_sided(-1, 2)

    def test_one_sided_direction(self):
        self.assertLess(mcnemar_exact_one_sided(12, 3), 0.05)
        self.assertGreater(mcnemar_exact_one_sided(3, 12), 0.95)

    def test_critical_b(self):
        for D in (1, 5, 12, 30, 100):
            cb = critical_b(D, 0.05)
            if cb <= D:
                self.assertLess(mcnemar_exact_one_sided(cb, D - cb), 0.05)
            if cb - 1 >= 0:
                self.assertGreaterEqual(mcnemar_exact_one_sided(cb - 1, D - cb + 1), 0.05)
        self.assertEqual(critical_b(4, 0.05), 5)   # 4 of 4 gives p = 1/16 = 0.0625: never significant
        self.assertEqual(critical_b(5, 0.05), 5)   # 5 of 5 gives 1/32


class TestClopperPearson(unittest.TestCase):
    def test_known_values(self):
        lo, hi = clopper_pearson(5, 10)
        self.assertAlmostEqual(lo, 0.187086, places=5)
        self.assertAlmostEqual(hi, 0.812914, places=5)
        lo, hi = clopper_pearson(0, 50)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 1 - 0.025 ** (1 / 50), places=6)
        lo, hi = clopper_pearson(50, 50)
        self.assertEqual(hi, 1.0)
        self.assertAlmostEqual(lo, 0.025 ** (1 / 50), places=6)

    def test_tail_masses(self):
        k, n = 17, 50
        lo, hi = clopper_pearson(k, n)
        self.assertAlmostEqual(1 - binom_cdf(k - 1, n, lo), 0.025, places=6)
        self.assertAlmostEqual(binom_cdf(k, n, hi), 0.025, places=6)
        self.assertLess(lo, k / n)
        self.assertGreater(hi, k / n)

    def test_bad_args(self):
        with self.assertRaises(ValueError):
            clopper_pearson(6, 5)


class TestPower(unittest.TestCase):
    def test_monotone_decreasing_in_d(self):
        # fixed net gain of +20: more discordance is more noise, so power falls as d grows
        ps = [power_mc(d, sims=20000, seed=1) for d in (0.06, 0.12, 0.25, 0.5)]
        for a, b in zip(ps, ps[1:]):
            self.assertGreater(a, b)

    def test_bounds_and_reproducible(self):
        p1 = power_mc(0.2, sims=5000, seed=3)
        p2 = power_mc(0.2, sims=5000, seed=3)
        self.assertEqual(p1, p2)
        self.assertTrue(0.0 <= p1 <= 1.0)
        self.assertEqual(power_mc(0.0, sims=1000), 0.0)

    def test_power_matches_exact_when_d_fixed(self):
        # d = 0.05 of 400 is about 20 discordant tasks, so q is near 1 and power is near 1
        self.assertGreater(power_mc(0.05, sims=5000), 0.95)

    def test_zero_gain_is_size(self):
        size = power_mc(0.2, gain=0, sims=40000, seed=5)
        self.assertLess(size, 0.05)
        self.assertGreater(size, 0.01)


if __name__ == '__main__':
    unittest.main()
