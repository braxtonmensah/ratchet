"""Contamination-gate perturbation (PREREG 6.4; SPEC 5 builder A, 13 I12). Owner: builder A.

Per task: one random colour permutation that fixes 0, plus one of rot90 / rot180 / rot270 / transpose, applied to every
demo grid and every test grid together. The draw is random.Random(f'{seed}|{task_id}'): shuffle colours 1..9, then choose
the geometry. Rotations are clockwise: rot90(g)[i][j] = g[H-1-j][i].
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from . import arc_io
from .types import Grid, Pair, Task

try:
    from . import config as _config
except ImportError:  # pragma: no cover
    _config = None


def _cfg(name: str, default):
    return getattr(_config, name, default) if _config is not None else default


GEOMS = tuple(_cfg('PERTURB_GEOMS', ('rot90', 'rot180', 'rot270', 'transpose')))
PERTURB_SEED = int(_cfg('PERTURB_SEED', 20261104))
PERTURB_SCHEMA = 'ratchet.perturb.v1'


@dataclass(frozen=True)
class Perturbation:
    perm: tuple[int, ...]   # perm[c] = new colour of c; perm[0] == 0
    geom: str

    def to_json(self) -> dict:
        return {'perm': list(self.perm), 'geom': self.geom}


def draw(task_id: str, seed: int) -> Perturbation:
    rng = random.Random(f'{seed}|{task_id}')
    rest = list(range(1, 10))
    rng.shuffle(rest)
    geom = rng.choice(GEOMS)
    return Perturbation(perm=(0, *rest), geom=geom)


def _geom(g: Grid, geom: str) -> Grid:
    h, w = len(g), len(g[0])
    if geom == 'rot90':
        return tuple(tuple(g[h - 1 - j][i] for j in range(h)) for i in range(w))
    if geom == 'rot180':
        return tuple(tuple(reversed(r)) for r in reversed(g))
    if geom == 'rot270':
        return tuple(tuple(g[j][w - 1 - i] for j in range(h)) for i in range(w))
    if geom == 'transpose':
        return tuple(tuple(g[j][i] for j in range(h)) for i in range(w))
    raise ValueError(f'unknown geom {geom!r}')


def apply_grid(g: Grid, p: Perturbation) -> Grid:
    if p.perm[0] != 0 or sorted(p.perm) != list(range(10)):
        raise ValueError(f'bad perm {p.perm}')
    return _geom(tuple(tuple(p.perm[v] for v in r) for r in g), p.geom)


def apply_task(t: Task, p: Perturbation, split: str | None = None) -> Task:
    """Train inputs and outputs, test inputs, and test outputs if present, all with the same transform."""
    return Task(id=t.id, split=split or t.split,
                train=tuple(Pair(apply_grid(x.input, p), apply_grid(x.output, p)) for x in t.train),
                test_inputs=tuple(apply_grid(g, p) for g in t.test_inputs),
                test_outputs=None if t.test_outputs is None else tuple(apply_grid(g, p) for g in t.test_outputs),
                src_sha256=t.src_sha256)


def build_perturbed_split(seed: int = PERTURB_SEED, src_split: str = 'sealed', out_dir: Path | None = None,
                          task_ids: list[str] | None = None) -> Path:
    """Write <data>/sealed_perturbed/<id>.json (inputs-only shape, never a test output) and <data>/PERTURB.json.
    Prints the PERTURB lever marker. Returns the PERTURB.json path."""
    out_dir = Path(out_dir) if out_dir is not None else arc_io.data_root() / 'sealed_perturbed'
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = list(task_ids) if task_ids is not None else arc_io.task_ids(src_split)
    rows = {}
    geoms = {g: 0 for g in GEOMS}
    for tid in ids:
        t = arc_io.load_task(tid, src_split)
        p = draw(tid, seed)
        geoms[p.geom] += 1
        pt = apply_task(t, p, split='sealed_perturbed')
        out_sha = arc_io._write_json(out_dir / f'{tid}.json', arc_io.task_to_json(pt, include_test_outputs=False))
        rows[tid] = {**p.to_json(), 'src_sha256': t.src_sha256, 'out_sha256': out_sha}
    manifest = {'schema': PERTURB_SCHEMA, 'seed': seed, 'src_split': src_split, 'n_tasks': len(ids),
                'geom_counts': geoms, 'draw': "random.Random(f'{seed}|{task_id}'): shuffle 1..9, then choice(GEOMS)",
                'tasks': rows}
    mpath = out_dir.parent / 'PERTURB.json'
    arc_io._write_json(mpath, manifest, sort_keys=True)
    print(f'LEVER PERTURB seed={seed} tasks={len(ids)} geoms=' + ','.join(f'{k}:{v}' for k, v in geoms.items()), flush=True)
    return mpath
