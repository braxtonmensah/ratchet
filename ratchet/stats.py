"""Exact one-sided McNemar, Clopper-Pearson interval, Monte Carlo power (PREREG 6.1, 7.3; SPEC 5 E, 13 I19)."""
from __future__ import annotations

import math
from fractions import Fraction

from .e_util import cfg


def mcnemar_exact_one_sided(b: int, c: int) -> float:
    """P(X >= b) for X ~ Binomial(b + c, 1/2). b = discordant tasks only the first arm solves. Exact rational sum."""
    b, c = int(b), int(c)
    if b < 0 or c < 0:
        raise ValueError('b and c must be >= 0')
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(b, n + 1))
    return float(Fraction(tail, 2 ** n))


def _binom_logpmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 0.0 if k == 0 else -math.inf
    if p >= 1.0:
        return 0.0 if k == n else -math.inf
    return (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
            + k * math.log(p) + (n - k) * math.log1p(-p))


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k), X ~ Bin(n, p)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return min(1.0, sum(math.exp(_binom_logpmf(i, n, p)) for i in range(0, k + 1)))


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k)."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return min(1.0, sum(math.exp(_binom_logpmf(i, n, p)) for i in range(k, n + 1)))


def _bisect(f, lo: float, hi: float, iters: int = 200) -> float:
    """Root of an increasing f on [lo, hi]."""
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided (1 - alpha) interval for a binomial proportion k / n."""
    k, n = int(k), int(n)
    if n <= 0 or k < 0 or k > n:
        raise ValueError(f'bad k={k} n={n}')
    a2 = alpha / 2
    lo = 0.0 if k == 0 else _bisect(lambda p: binom_sf(k, n, p) - a2, 0.0, 1.0)
    hi = 1.0 if k == n else _bisect(lambda p: a2 - binom_cdf(k, n, p), 0.0, 1.0)
    return lo, hi


def critical_b(D: int, alpha: float) -> int:
    """Smallest b with mcnemar_exact_one_sided(b, D - b) < alpha; D + 1 if none."""
    if D == 0:
        return 1
    tail = 0
    denom = 2 ** D
    # walk down from b = D accumulating the tail exactly
    best = D + 1
    for b in range(D, -1, -1):
        tail += math.comb(D, b)
        if Fraction(tail, denom) < alpha:
            best = b
        else:
            break
    return best


def power_mc(d: float, n: int | None = None, gain: int | None = None, alpha: float | None = None,
             sims: int | None = None, seed: int = 0) -> float:
    """Power of the exact one-sided McNemar for a net gain of `gain` tasks of n at discordance d.

    D ~ Bin(n, d) discordant tasks; b ~ Bin(D, q), q = min(1, 0.5 + gain / (2 D)), so E[b - c] = gain when q < 1.
    Reject when mcnemar_exact_one_sided(b, D - b) < alpha. Returns the rejection fraction over `sims` draws.
    """
    n = int(cfg('N_SEALED') if n is None else n)
    gain = int(cfg('POWER_GAIN') if gain is None else gain)
    alpha = float(cfg('MCNEMAR_ALPHA') if alpha is None else alpha)
    sims = int(cfg('POWER_SIMS') if sims is None else sims)
    if not 0.0 <= d <= 1.0:
        raise ValueError(f'd={d}')
    crit = [critical_b(D, alpha) for D in range(n + 1)]
    try:
        import numpy as np
        rng = np.random.default_rng(seed)
        D = rng.binomial(n, d, size=sims)
        q = np.where(D > 0, np.minimum(1.0, 0.5 + gain / (2.0 * np.maximum(D, 1))), 0.5)
        b = rng.binomial(D, q)
        crit_arr = np.asarray(crit)
        rej = (D > 0) & (b >= crit_arr[D])
        return float(rej.mean())
    except ImportError:
        import random
        rng = random.Random(seed)
        hits = 0
        for _ in range(sims):
            D = sum(1 for _ in range(n) if rng.random() < d)
            if D == 0:
                continue
            q = min(1.0, 0.5 + gain / (2.0 * D))
            b = sum(1 for _ in range(D) if rng.random() < q)
            hits += b >= crit[D]
        return hits / sims
