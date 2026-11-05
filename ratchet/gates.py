"""PREREG 6 gates, computed on score outputs only (solved id sets, winning sample ids and their exec rows).

No function here sees a grid or a key file.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Mapping, Sequence

from .e_util import cfg, get
from .stats import mcnemar_exact_one_sided


def compare(solved: Mapping[str, frozenset], a: str, b: str, alpha: float | None = None) -> dict:
    """Exact one-sided McNemar of arm a over arm b. b_ = tasks only a solves, c_ = tasks only b solves."""
    alpha = float(cfg('MCNEMAR_ALPHA') if alpha is None else alpha)
    A, B = frozenset(solved[a]), frozenset(solved[b])
    bb, cc = len(A - B), len(B - A)
    p = mcnemar_exact_one_sided(bb, cc)
    return {'a': a, 'b': b, 'solved_a': len(A), 'solved_b': len(B), 'b_only_a': bb, 'c_only_b': cc,
            'net': bb - cc, 'p': p, 'alpha': alpha, 'pass': p < alpha}


def calls_accepted(row, accepted: frozenset) -> bool:
    """True iff the exec row shows a runtime call (count > 0, test inputs) of an accepted helper (SPEC 13 I10)."""
    calls = get(row, 'helper_calls', None) or {}
    return any(int(v) > 0 and k in accepted for k, v in dict(calls).items())


def reuse_gate(W: frozenset, winners: Mapping[str, Sequence], accepted: frozenset,
               min_fraction: float | None = None) -> dict:
    """PREREG 6.2: at least half of the winning programs on W call an accepted helper.

    winners[task] = exec rows of STOCK's winning samples for that task (pooled over the seeds where it was correct).
    A program is a distinct (task, code_sha); a code_sha counts as calling if any of its rows shows a call.
    Decisive fraction: distinct programs. Also reported: per-sample and per-task fractions.
    """
    min_fraction = float(cfg('REUSE_MIN_FRAC') if min_fraction is None else min_fraction)
    accepted = frozenset(accepted)
    progs: dict[tuple[str, str], bool] = {}
    n_rows = n_rows_call = 0
    tasks_any = 0
    missing = []
    for t in sorted(W):
        rows = list(winners.get(t, []) or [])
        if not rows:
            missing.append(t)
        task_call = False
        for r in rows:
            sha = get(r, 'code_sha', None) or get(r, 'sample_id', '')
            c = calls_accepted(r, accepted)
            key = (t, str(sha))
            progs[key] = progs.get(key, False) or c
            n_rows += 1
            n_rows_call += c
            task_call = task_call or c
        tasks_any += task_call
    n_prog = len(progs)
    n_call = sum(progs.values())
    frac = (n_call / n_prog) if n_prog else 0.0
    if min_fraction == 0.5:
        ok = n_prog > 0 and 2 * n_call >= n_prog          # exact integer form of fraction >= 0.5
    else:
        ok = n_prog > 0 and frac >= min_fraction
    return {'W': len(W), 'programs': n_prog, 'programs_calling': n_call, 'fraction': frac,
            'samples': n_rows, 'samples_calling': n_rows_call,
            'tasks_with_a_calling_winner': tasks_any, 'tasks_without_winner_rows': missing,
            'min_fraction': min_fraction, 'pass': bool(ok),
            'reason': 'EMPTY_W' if not W else ('NO_WINNER_ROWS' if n_prog == 0 else '')}


def knockout_gate(W: frozenset, solved_delete: frozenset, solved_inline: frozenset,
                  max_kept_fraction: float | None = None) -> dict:
    """PREREG 6.3: each knockout mode removes at least half of W's solves: kept = |W & solved| <= floor(KNOCKOUT_MAX_FRAC
    x |W|), in exact rational arithmetic (0.5 gives |W| // 2)."""
    frac = Fraction(str(cfg('KNOCKOUT_MAX_FRAC') if max_kept_fraction is None else max_kept_fraction))
    W = frozenset(W)
    kd = len(W & frozenset(solved_delete))
    ki = len(W & frozenset(solved_inline))
    lim = math.floor(frac * len(W))
    return {'W': len(W), 'kept_delete': kd, 'kept_inline': ki, 'removed_delete': len(W) - kd,
            'removed_inline': len(W) - ki, 'max_kept': lim,
            'pass_delete': bool(W) and kd <= lim, 'pass_inline': bool(W) and ki <= lim,
            'pass': bool(W) and kd <= lim and ki <= lim, 'reason': 'EMPTY_W' if not W else ''}


def contamination_gate(net_primary: int, net_perturbed: int, min_fraction: float | None = None) -> dict:
    """PREREG 6.4: STOCK's net gain over FLAT-TTC on the perturbed copy is at least half the unperturbed net gain."""
    min_fraction = float(cfg('CONTAM_MIN_FRAC') if min_fraction is None else min_fraction)
    if min_fraction == 0.5:
        ok = 2 * int(net_perturbed) >= int(net_primary)
    else:
        ok = net_perturbed >= min_fraction * net_primary
    return {'net_primary': int(net_primary), 'net_perturbed': int(net_perturbed), 'min_fraction': min_fraction,
            'ratio': (net_perturbed / net_primary) if net_primary else None,
            'pass': bool(ok and net_primary > 0), 'reason': '' if net_primary > 0 else 'NO_PRIMARY_GAIN'}


def aa_pairs(per_seed_solved: Mapping[int, frozenset]) -> list[dict]:
    """A/A noise: every pair of seeds of one arm, as McNemar (b, c, net, p)."""
    seeds = sorted(per_seed_solved)
    out = []
    for i, s in enumerate(seeds):
        for t in seeds[i + 1:]:
            A, B = frozenset(per_seed_solved[s]), frozenset(per_seed_solved[t])
            bb, cc = len(A - B), len(B - A)
            out.append({'seed_a': s, 'seed_b': t, 'b': bb, 'c': cc, 'net': bb - cc,
                        'p': mcnemar_exact_one_sided(bb, cc), 'discordant': bb + cc})
    return out
