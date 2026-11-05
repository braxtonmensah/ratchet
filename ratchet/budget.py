"""FLAT-TTC token match (PREREG 4 FLAT-TTC row; SPEC 5 builder D, 13 I2, I12). Owner: builder D.

target   = logical tokens of STOCK growth (all rounds, round 1 included) + STOCK sealed (this seed and condition)
m_flat   = logical tokens per sample over FLAT's base sealed pass (requests '|b<k>') of this seed and condition
n_extra  = round-half-up(target / m_flat)
per_task = n_extra // N each, remainder +1 to the first (n_extra mod N) ids in sorted order

Logical tokens of a ledger row = prompt_tokens_logical (prompt x n, library tokens included) + gen_tokens.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Iterable, Sequence

from . import config

CONDITION_PHASE = {'sealed': 'sealed', 'perturbed': 'perturbed', 'arcagi2': 'arcagi2'}


class BudgetError(RuntimeError):
    pass


@dataclass
class FlatBudget:
    sealed_seed: int
    target_tokens: int
    m_flat: float
    n_extra: int
    per_task: dict[str, int]
    condition: str = 'sealed'
    stock_growth_tokens: int = 0
    stock_sealed_tokens: int = 0
    flat_base_tokens: int = 0
    flat_base_samples: int = 0
    n_tasks: int = 0
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'FlatBudget':
        d = dict(d)
        d['per_task'] = {str(k): int(v) for k, v in d['per_task'].items()}
        return cls(**d)


def logical_tokens(row: dict) -> int:
    n = int(row.get('n', 1) or 1)
    pl = row.get('prompt_tokens_logical')
    if pl is None:
        pl = int(row.get('prompt_tokens', 0)) * n
    return int(pl) + int(row.get('gen_tokens', 0))


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def is_base_request(request_id: str) -> bool:
    """FLAT base requests end in '|b<k>'; extra requests end in '|x<k>'."""
    return request_id.rsplit('|', 1)[-1].startswith('b')


def allocate(n_extra: int, task_ids: Sequence[str]) -> dict[str, int]:
    ids = sorted(task_ids)
    if not ids:
        raise BudgetError('no tasks to allocate FLAT extra samples to')
    q, rem = divmod(int(n_extra), len(ids))
    return {t: q + (1 if i < rem else 0) for i, t in enumerate(ids)}


def compute(rows: Iterable[dict], sealed_seed: int, condition: str, task_ids: Sequence[str]) -> FlatBudget:
    """Pure function of ledger rows (already deduped by request_id) and the sealed task ids."""
    phase = CONDITION_PHASE[condition]
    g = s = fb = 0
    fn = 0
    n_g = n_s = n_fb = 0
    for row in rows:
        arm, ph, k = row.get('arm'), row.get('phase'), row.get('sealed_seed')
        if arm == 'STOCK' and ph == 'growth':
            g += logical_tokens(row)
            n_g += 1
        elif arm == 'STOCK' and ph == phase and k == sealed_seed:
            s += logical_tokens(row)
            n_s += 1
        elif arm == config.FLAT_ARM and ph == phase and k == sealed_seed and is_base_request(row['request_id']):
            fb += logical_tokens(row)
            fn += int(row.get('n', 1) or 1)
            n_fb += 1
    if n_g == 0:
        raise BudgetError('no STOCK growth ledger rows')
    if n_s == 0:
        raise BudgetError('no STOCK %s ledger rows for seed %d' % (phase, sealed_seed))
    if fn == 0:
        raise BudgetError('no FLAT base %s ledger rows for seed %d' % (phase, sealed_seed))
    target = g + s
    m_flat = fb / fn
    n_extra = round_half_up(target / m_flat)
    per_task = allocate(n_extra, task_ids)
    return FlatBudget(sealed_seed=sealed_seed, target_tokens=target, m_flat=m_flat, n_extra=n_extra, per_task=per_task,
                      condition=condition, stock_growth_tokens=g, stock_sealed_tokens=s, flat_base_tokens=fb,
                      flat_base_samples=fn, n_tasks=len(per_task),
                      detail={'stock_growth_requests': n_g, 'stock_sealed_requests': n_s, 'flat_base_requests': n_fb})


def flat_budget(run, sealed_seed: int, condition: str = 'sealed') -> FlatBudget:
    from . import arms
    kit = arms.kit_of(run)
    split = arms.CONDITION_SPLIT[condition]
    return compute(kit.ledger.iter_rows(run.dir), sealed_seed, condition, arms.split_ids(run, split))


def realized_tokens(rows: Iterable[dict], sealed_seed: int, condition: str) -> dict:
    """FLAT logical tokens actually spent this seed: base, extra (requests '|x<k>'), and samples of each."""
    phase = CONDITION_PHASE[condition]
    out = {'base': 0, 'extra': 0, 'base_samples': 0, 'extra_samples': 0}
    for row in rows:
        if row.get('arm') == config.FLAT_ARM and row.get('phase') == phase and row.get('sealed_seed') == sealed_seed:
            part = 'base' if is_base_request(row['request_id']) else 'extra'
            out[part] += logical_tokens(row)
            out[part + '_samples'] += int(row.get('n', 1) or 1)
    return out
