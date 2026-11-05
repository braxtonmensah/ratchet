"""Builder E shared helpers: config lookup with defaults, tolerant JSONL reading, hashing, ET clock.

Every constant builder E uses is listed in E_DEFAULTS. If `ratchet/config.py` (builder D) defines the same name, the
config value wins, so config.py stays the single place a number is changed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator

E_DEFAULTS: dict[str, Any] = {
    # names match ratchet/config.py (builder D) where D defines them
    'MCNEMAR_ALPHA': 0.05,
    'SOLVED_MIN_SEEDS': 2,
    'SEALED_SEEDS': (1, 2, 3),
    'REUSE_MIN_FRAC': 0.5,
    'KNOCKOUT_MAX_FRAC': 0.5,
    'CONTAM_MIN_FRAC': 0.5,
    'POWER_GAIN': 20,
    'POWER_MIN': 0.60,
    'POWER_SIMS': 100_000,
    'N_SEALED': 400,
    'N_GROWTH': 400,
    'PILOT_N': 50,
    'S_GRID': (4, 8, 16),
    'R_GRID': (4, 6, 8),
    'H100_HOURS_BUDGET': 12,
    'PILOT_RATE_INTERVAL_S': 30,
    'LIBRARY_CAP_TOKENS': 6000,
    'ARMS': ('STOCK', 'STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'FLATTTC', 'PLANTDRIP', 'PLANTL1'),
    'LIBRARY_ARMS': ('STOCK', 'STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'PLANTDRIP', 'PLANTL1'),
    'PERTURBED_ARMS': ('STOCK', 'FLATTTC'),
    'FLAT_ARM': 'FLATTTC',
    'JOB_WALL_S': 3600,
    'STOP_ISSUE_S': 3120,
    'PRED_POINT': 2,
    'PRED_BAND': (-8, 14),
    'PRED_BAND_CALIBRATED': (-10.68, 17.216),
    'P_COMPOUNDS': 0.15,
    'PERTURB_SEED': 20261104,
    'VOID_MAX_ATTEMPTS': 2,
    'ARCAGI1_COMMIT': '399030444e0ab0cc8b4e199870fb20b863846f34',
    'GROWTH_IDS_SHA256': 'c4e1b145daad71b4f02ac3482be215f1ab07863b67f13fc1bde1572f501ff75a',
    'SEALED_IDS_SHA256': '911bf838d8843606d5fc1ba0550a0c23670027bf8f6e32e4e4fbf93854957ddd',
    # builder E only (not in config.py yet)
    'PASS_AT': 2,
    'PILOT_PLANT_MIN_GAIN': 1,          # PREREG 7.2: raise demo-pass count by at least 1 task
    'COMPARATORS': ('STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'FLATTTC'),   # PREREG 6.1
}


def cfg(name: str):
    """Value from ratchet.config if it defines `name`, else the builder E default."""
    try:
        from . import config  # type: ignore
        if hasattr(config, name):
            return getattr(config, name)
    except Exception:
        pass
    return E_DEFAULTS[name]


def now_et(fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo('America/New_York')).strftime(fmt) + ' ET'
    except Exception:
        return _dt.datetime.now().strftime(fmt) + ' local'


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path | str) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def read_json(p: Path | str, default=None):
    p = Path(p)
    if not p.exists():
        return default
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json_atomic(p: Path | str, obj, indent: int | None = 1) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f'.tmp{os.getpid()}')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, indent=indent, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return p


def write_text_atomic(p: Path | str, text: str) -> Path:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f'.tmp{os.getpid()}')
    with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    return p


def iter_jsonl(p: Path | str) -> Iterator[dict]:
    """Rows of a JSONL file; a line that fails to parse is skipped only if it is the last line (torn write)."""
    p = Path(p)
    if not p.exists():
        return
    with open(p, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')
    while lines and lines[-1].strip() == '':
        lines.pop()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                return
            raise


def get(obj, name: str, default=None):
    """Field of a dataclass-like object or a dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def task_of_sample(sample_id: str) -> str:
    """Task id from a sample_id `ARM|phase|r<round>|<task>|s<i>` (SPEC 4.5)."""
    parts = str(sample_id).split('|')
    return parts[3] if len(parts) >= 5 else ''


def as_grid(g) -> tuple:
    return tuple(tuple(int(v) for v in row) for row in g)
