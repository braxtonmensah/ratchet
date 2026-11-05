"""The single data loader (SPEC 4.1, 5 builder A, 8 layer 2). Owner: builder A.

Every task-data read goes through _read_json, which calls guard.check_data_read(path) first (realpath under
<data root>/<split>, never under a protected root). Writes into the data tree (perturbed split) go through _write_json.
No other module opens data files.

Data root: guard.data_root() (DATA_ROOT, or RATCHET_DATA_ROOT for CPU tests; tests must also guard.add_data_root it).
Split directories: growth -> growth/, pilot -> growth/ (pilot ids are a subset of growth, SPEC 7 has no data/pilot dir),
sealed -> sealed/, sealed_perturbed -> sealed_perturbed/, arcagi2_sealed -> arcagi2_sealed/.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .types import Grid, Pair, Task, grid_to_json as _g2j

try:
    from . import config as _config
except ImportError:  # pragma: no cover - build order
    _config = None


def _cfg(name: str, default):
    return getattr(_config, name, default) if _config is not None else default


SPLITS = ('growth', 'pilot', 'sealed', 'sealed_perturbed', 'arcagi2_sealed')
SEALED_SPLITS = ('sealed', 'sealed_perturbed', 'arcagi2_sealed')
OUTPUT_SPLITS = ('growth', 'pilot')
SPLIT_DIR = {'growth': 'growth', 'pilot': 'growth', 'sealed': 'sealed', 'sealed_perturbed': 'sealed_perturbed',
             'arcagi2_sealed': 'arcagi2_sealed'}

GROWTH_IDS_SHA256 = _cfg('GROWTH_IDS_SHA256', 'c4e1b145daad71b4f02ac3482be215f1ab07863b67f13fc1bde1572f501ff75a')
SEALED_IDS_SHA256 = _cfg('SEALED_IDS_SHA256', '911bf838d8843606d5fc1ba0550a0c23670027bf8f6e32e4e4fbf93854957ddd')
_REPO = Path(__file__).resolve().parent.parent
GROWTH_IDS_FILE = Path(_cfg('GROWTH_IDS_FILE', _REPO / 'splits' / 'growth_ids_arcagi1_train.txt'))
SEALED_IDS_FILE = Path(_cfg('SEALED_IDS_FILE', _REPO / 'splits' / 'sealed_ids_arcagi1_eval.txt'))
GRID_MAX_SIDE = int(_cfg('GRID_MAX_SIDE', 30))
N_COLOURS = int(_cfg('N_COLOURS', 10))
PILOT_N = int(_cfg('PILOT_N', 50))
PILOT_SALT = 'ratchet-pilot|'
TASK_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


class IdListMismatch(ValueError):
    pass


class SealedLeak(RuntimeError):
    pass


class BadGrid(ValueError):
    pass


class BadTask(ValueError):
    pass


def _guard():
    from . import guard   # lazy: guard may import from this module's siblings
    return guard


def data_root() -> Path:
    return Path(_guard().data_root())


def _is_production_root() -> bool:
    g = _guard()
    return os.path.realpath(str(data_root())) == os.path.realpath(str(g.DATA_ROOT))


# ---------------------------------------------------------------------------------------------------------------------
# id lists (PREREG 2)

def _canonical_id_bytes(ids) -> bytes:
    return ''.join(i + '\n' for i in sorted(ids)).encode('ascii')


def id_list_sha256(ids) -> str:
    """sha256 of the sorted id list, one id per line, LF line ends, trailing LF (equals the committed files' bytes)."""
    return hashlib.sha256(_canonical_id_bytes(ids)).hexdigest()


def verify_id_list(path: Path, expected_sha256: str) -> list[str]:
    """Parse an id-list file and check its sorted, LF-normalized form hashes to the PREREG value."""
    with open(path, 'rb') as f:   # repo file, not task data
        raw = f.read()
    ids = [ln.strip() for ln in raw.decode('ascii').splitlines() if ln.strip()]
    if len(set(ids)) != len(ids):
        raise IdListMismatch(f'ID_LIST_DUPLICATES {path}')
    got = id_list_sha256(ids)
    if got != expected_sha256:
        raise IdListMismatch(f'ID_LIST_SHA_MISMATCH {path} got={got} want={expected_sha256}')
    return sorted(ids)


def growth_id_list() -> list[str]:
    return verify_id_list(GROWTH_IDS_FILE, GROWTH_IDS_SHA256)


def sealed_id_list() -> list[str]:
    return verify_id_list(SEALED_IDS_FILE, SEALED_IDS_SHA256)


def pilot_ids(n: int = PILOT_N, growth_ids: list[str] | None = None) -> list[str]:
    """The n growth ids with the smallest sha256('ratchet-pilot|' + id), returned sorted by id.
    Default id pool: the committed PREREG growth list on the production root; on a test data root (RATCHET_DATA_ROOT),
    the growth ids on disk, so a pilot round on a small fake growth split loads tasks that exist (integration fix)."""
    if growth_ids is None:
        ids = growth_id_list() if _is_production_root() else task_ids('growth')
    else:
        ids = list(growth_ids)
    ranked = sorted(ids, key=lambda i: (hashlib.sha256((PILOT_SALT + i).encode()).hexdigest(), i))
    return sorted(ranked[:n])


def _split_dir(split: str) -> Path:
    if split not in SPLITS:
        raise ValueError(f'unknown split {split!r}; one of {SPLITS}')
    return data_root() / SPLIT_DIR[split]


def task_ids(split: str) -> list[str]:
    """Sorted ids of the split as present on disk. On the production data root, growth and the ARC-AGI-1 sealed splits
    must equal the PREREG-hashed id lists exactly (IdListMismatch otherwise); pilot = pilot_ids()."""
    if split == 'pilot':
        ids = pilot_ids()
        if _is_production_root():
            have = set(task_ids('growth'))
            missing = [i for i in ids if i not in have]
            if missing:
                raise IdListMismatch(f'PILOT_IDS_MISSING {missing[:5]}')
        return ids
    d = _split_dir(split)
    ids = sorted(fn[:-5] for fn in os.listdir(d) if fn.endswith('.json') and TASK_ID_RE.match(fn[:-5]))
    if _is_production_root():
        want = {'growth': GROWTH_IDS_SHA256, 'sealed': SEALED_IDS_SHA256, 'sealed_perturbed': SEALED_IDS_SHA256}.get(split)
        if want is not None and id_list_sha256(ids) != want:
            raise IdListMismatch(f'SPLIT_ON_DISK_MISMATCH split={split} n={len(ids)} sha={id_list_sha256(ids)} want={want}')
    return ids


# ---------------------------------------------------------------------------------------------------------------------
# grids

def validate_grid(obj) -> Grid:
    """1..30 rows by 1..30 columns, rectangular, ints 0..9 (bool refused). Returns the immutable Grid."""
    if not isinstance(obj, (list, tuple)) or not (1 <= len(obj) <= GRID_MAX_SIDE):
        raise BadGrid(f'rows: {type(obj).__name__} len={len(obj) if isinstance(obj, (list, tuple)) else "-"}')
    width = None
    out = []
    for row in obj:
        if not isinstance(row, (list, tuple)) or not (1 <= len(row) <= GRID_MAX_SIDE):
            raise BadGrid('row shape')
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise BadGrid('ragged')
        r = []
        for v in row:
            if type(v) is not int or not (0 <= v < N_COLOURS):
                raise BadGrid(f'cell {v!r}')
            r.append(v)
        out.append(tuple(r))
    return tuple(out)


def grid_to_json(g: Grid) -> list[list[int]]:
    return _g2j(g)


def render_grid(g: Grid) -> str:
    """Rows of digits, no spaces, '\\n' between rows (no trailing newline)."""
    return '\n'.join(''.join(str(v) for v in row) for row in g)


def parse_rendered(s: str) -> Grid:
    """Inverse of render_grid."""
    return validate_grid([[int(ch) for ch in ln] for ln in s.split('\n')])


# ---------------------------------------------------------------------------------------------------------------------
# reads and writes (the only open() calls on data paths)

def _read_bytes(path: Path) -> bytes:
    safe = _guard().check_data_read(path)
    with open(safe, 'rb') as f:
        return f.read()


def _read_json(path: Path) -> dict:
    return json.loads(_read_bytes(path))


def _write_json(path: Path, obj, *, sort_keys: bool = False) -> str:
    """Atomic write of a JSON file inside the data root (temp file + os.replace). Returns sha256 of the bytes written.
    Refuses any path outside the data root or under a protected root."""
    g = _guard()
    path = Path(path)
    parent_real = os.path.realpath(str(path.parent))
    root_real = os.path.realpath(str(data_root()))
    if not (parent_real == root_real or parent_real.startswith(root_real.rstrip(os.sep) + os.sep)):
        raise PermissionError(f'DATA_WRITE_REFUSED outside data root: {parent_real}')
    if g.is_protected(parent_real):
        raise g.SealedReadRefused(f'DATA_WRITE_REFUSED under protected root: {parent_real}')
    data = json.dumps(obj, separators=(',', ':'), sort_keys=sort_keys).encode()
    tmp = Path(parent_real) / f'.{path.name}.tmp{os.getpid()}'
    with open(tmp, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, Path(parent_real) / path.name)
    return hashlib.sha256(data).hexdigest()


def task_path(task_id: str, split: str) -> Path:
    if not TASK_ID_RE.match(task_id or ''):
        raise ValueError(f'bad task id {task_id!r}')
    return _split_dir(split) / f'{task_id}.json'


def parse_task(obj: dict, task_id: str, split: str, src_sha256: str) -> Task:
    """Build a Task from a parsed ARC JSON object. Sealed splits: SealedLeak if any test item carries 'output'."""
    if not isinstance(obj, dict) or not isinstance(obj.get('train'), list) or not isinstance(obj.get('test'), list):
        raise BadTask(f'{split}/{task_id}: missing train/test lists')
    if not obj['train'] or not obj['test']:
        raise BadTask(f'{split}/{task_id}: empty train or test')
    if split in SEALED_SPLITS:
        for item in obj['test']:
            if isinstance(item, dict) and 'output' in item:
                raise SealedLeak(f'SEALED_LEAK {split}/{task_id}: a test item carries an output')
    train = tuple(Pair(validate_grid(p['input']), validate_grid(p['output'])) for p in obj['train'])
    test_inputs = tuple(validate_grid(p['input']) for p in obj['test'])
    test_outputs = None
    if split in OUTPUT_SPLITS:
        if not all(isinstance(p, dict) and 'output' in p for p in obj['test']):
            raise BadTask(f'{split}/{task_id}: growth test item without output')
        test_outputs = tuple(validate_grid(p['output']) for p in obj['test'])
    return Task(id=task_id, split=split, train=train, test_inputs=test_inputs, test_outputs=test_outputs,
                src_sha256=src_sha256)


def load_task(task_id: str, split: str) -> Task:
    raw = _read_bytes(task_path(task_id, split))
    return parse_task(json.loads(raw), task_id, split, hashlib.sha256(raw).hexdigest())


def load_split(split: str) -> list[Task]:
    return [load_task(i, split) for i in task_ids(split)]


def task_to_json(t: Task, include_test_outputs: bool) -> dict:
    """ARC JSON for a Task. include_test_outputs=False gives the sealed (inputs-only) shape."""
    test = []
    for i, g in enumerate(t.test_inputs):
        item = {'input': grid_to_json(g)}
        if include_test_outputs and t.test_outputs is not None:
            item['output'] = grid_to_json(t.test_outputs[i])
        test.append(item)
    return {'train': [{'input': grid_to_json(p.input), 'output': grid_to_json(p.output)} for p in t.train], 'test': test}
