"""EXEMPLAR arm: demo features, z-score scaler, k = 3 nearest verified programs (PREREG 4, SPEC 5, builder C).

Feature vector (38 values, mean over demo pairs): input h, input w, output h, output w, output/input area ratio,
same-shape flag, input colour histogram (10, cell fractions), output colour histogram (10), number of input colours,
number of output colours, input background colour one-hot (10; background = most frequent input colour, ties to the
smaller colour). The scaler is fit on growth tasks only. A task never sees its own programs (SPEC 13 I17).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from ratchet.c_util import atomic_write_text, canonical_json, count_tokens, iter_jsonl, sha256_text

FEATURE_NAMES = (['in_h', 'in_w', 'out_h', 'out_w', 'area_ratio', 'same_shape']
                 + [f'in_c{i}' for i in range(10)] + [f'out_c{i}' for i in range(10)]
                 + ['in_ncol', 'out_ncol'] + [f'bg{i}' for i in range(10)])
N_FEATURES = len(FEATURE_NAMES)


@dataclass
class Exemplar:
    task: str
    sample_id: str
    code: str
    token_len: int
    features: tuple[float, ...]


def _pair_features(inp, out) -> np.ndarray:
    a = np.asarray(inp, dtype=np.int64)
    b = np.asarray(out, dtype=np.int64)
    ih, iw = a.shape
    oh, ow = b.shape
    hin = np.bincount(a.ravel(), minlength=10)[:10].astype(float) / a.size
    hout = np.bincount(b.ravel(), minlength=10)[:10].astype(float) / b.size
    counts = np.bincount(a.ravel(), minlength=10)[:10]
    bg = np.zeros(10)
    bg[int(np.argmax(counts))] = 1.0
    return np.concatenate([[ih, iw, oh, ow, (oh * ow) / (ih * iw), float((ih, iw) == (oh, ow))], hin, hout,
                           [float((hin > 0).sum()), float((hout > 0).sum())], bg])


def demo_features(task) -> np.ndarray:
    rows = [_pair_features(p.input, p.output) for p in task.train]
    if not rows:
        return np.zeros(N_FEATURES)
    return np.mean(np.stack(rows), axis=0)


class Scaler:
    def __init__(self, mean: np.ndarray | None = None, std: np.ndarray | None = None):
        self.mean = np.zeros(N_FEATURES) if mean is None else np.asarray(mean, dtype=float)
        self.std = np.ones(N_FEATURES) if std is None else np.asarray(std, dtype=float)

    @classmethod
    def fit(cls, tasks: Sequence) -> 'Scaler':
        x = np.stack([demo_features(t) for t in tasks]) if tasks else np.zeros((1, N_FEATURES))
        mean = x.mean(axis=0)
        std = x.std(axis=0)
        std = np.where(std > 1e-12, std, 1.0)
        return cls(mean, std)

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (np.asarray(x, dtype=float) - self.mean) / self.std

    def to_dict(self) -> dict:
        return {'mean': [float(v) for v in self.mean], 'std': [float(v) for v in self.std]}

    @classmethod
    def from_dict(cls, d: dict) -> 'Scaler':
        return cls(np.asarray(d['mean']), np.asarray(d['std']))


def neighbours(task, pool: Sequence[Exemplar], scaler: Scaler, k: int = 3,
               exclude_task: str | None = None) -> list[Exemplar]:
    """k nearest exemplars by Euclidean distance on z-scored features; the task itself is always excluded."""
    excl = {task.id} | ({exclude_task} if exclude_task else set())
    cands = [e for e in pool if e.task not in excl]
    if not cands:
        return []
    q = scaler.transform(demo_features(task))
    m = scaler.transform(np.asarray([e.features for e in cands], dtype=float))
    d = np.sqrt(((m - q) ** 2).sum(axis=1))
    order = sorted(range(len(cands)), key=lambda i: (round(float(d[i]), 9), cands[i].task, cands[i].sample_id))
    return [cands[i] for i in order[:k]]


def _parse_shared(s) -> tuple[str, int] | None:
    if isinstance(s, dict):
        return str(s.get('arm')), int(s.get('round'))
    if isinstance(s, str):
        m = re.search(r'([A-Z][A-Z_]*)\W*(?:round_?|r)?(\d+)', s)
        if m:
            return m.group(1), int(m.group(2))
    return None


def _round_rows(run_dir: Path, arm: str, r: int, depth: int = 0) -> tuple[Path, list[dict], list[dict]]:
    rd = run_dir / 'arms' / arm / f'round_{r}'
    samples = list(iter_jsonl(rd / 'samples.jsonl'))
    if not samples and depth < 3 and (rd / 'round_state.json').exists():
        st = json.loads((rd / 'round_state.json').read_text(encoding='utf-8'))
        shared = _parse_shared(st.get('shared_from'))
        if shared:
            return _round_rows(run_dir, shared[0], shared[1], depth + 1)
    return rd, samples, list(iter_jsonl(rd / 'exec.jsonl'))


def pool_from_rounds(run_dir: Path, arm: str, upto_round: int, *, tasks: Mapping | None = None, tok=None,
                     split: str = 'growth') -> list[Exemplar]:
    """Shortest (characters) demo-passing growth program per task over rounds 1..upto_round; ties by sample_id.

    `tasks` maps task id -> Task for features (default: arc_io.load_task(id, split))."""
    run_dir = Path(run_dir)
    best: dict[str, dict] = {}
    for r in range(1, int(upto_round) + 1):
        _, samples, execs = _round_rows(run_dir, arm, r)
        ok = {e['sample_id'] for e in execs if e.get('demo_pass')}   # demo-passing = verified (same rule as STOCK, PREREG 4)
        for s in samples:
            sid, code = s.get('sample_id'), s.get('code')
            if sid not in ok or not code or s.get('phase', 'growth') != 'growth':
                continue
            t = s['task']
            if t not in best or (len(code), sid) < (len(best[t]['code']), best[t]['sample_id']):
                best[t] = s
    if not best:
        return []
    if tasks is None:
        from ratchet import arc_io   # builder A, the single data loader
        tasks = {t: arc_io.load_task(t, split) for t in best}
    out = []
    for t in sorted(best):
        s = best[t]
        out.append(Exemplar(task=t, sample_id=s['sample_id'], code=s['code'], token_len=count_tokens(s['code'], tok),
                            features=tuple(float(v) for v in demo_features(tasks[t]))))
    return out


def save_pool(pool: Sequence[Exemplar], path: Path, scaler: Scaler | None = None, meta: dict | None = None) -> str:
    """Write pool_R.json; returns its sha256 (computed like library sha: canonical JSON without the sha field)."""
    d = {'schema': 'ratchet.exemplar_pool.v1', 'meta': meta or {}, 'scaler': scaler.to_dict() if scaler else None,
         'exemplars': [asdict(e) for e in pool]}
    s = sha256_text(canonical_json(d))
    d['sha256'] = s
    atomic_write_text(Path(path), json.dumps(d, sort_keys=True, indent=1) + '\n')
    return s


def load_pool(path: Path) -> tuple[list[Exemplar], Scaler | None, dict]:
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    want = d.pop('sha256', None)
    if sha256_text(canonical_json(d)) != want:
        from ratchet.library import LibraryHashMismatch
        raise LibraryHashMismatch(f'POOL_HASH_MISMATCH {path}')
    pool = [Exemplar(task=e['task'], sample_id=e['sample_id'], code=e['code'], token_len=int(e['token_len']),
                     features=tuple(e['features'])) for e in d['exemplars']]
    sc = Scaler.from_dict(d['scaler']) if d.get('scaler') else None
    return pool, sc, d.get('meta', {})
