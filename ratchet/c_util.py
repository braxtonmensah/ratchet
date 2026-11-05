"""Builder C shared utilities: constants, token counting fallback, jsonl reading, atomic writes.

Every builder C constant is read from ratchet/config.py when that module defines it (config is owned by builder D);
the values below are the defaults SPEC sections 4 and 5 register, used only until config.py carries them.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterator

try:  # builder D owns config.py; it may not exist yet while builders work in parallel
    from ratchet import config as _config  # type: ignore
except ImportError:  # pragma: no cover - depends on build order
    _config = None

_DEFAULTS = {
    'ACCEPT_MIN_TASKS': 2,            # PREREG 4: at least 2 demo-passing solutions of different tasks
    'ACCEPT_MIN_MDL': 20,             # PREREG 4: MDL gain of at least 20 tokens
    'LIBRARY_CAP_TOKENS': 6000,       # PREREG 4: library context cap
    'SANDBOX_IMPORT_ALLOW': ('math', 'itertools', 'collections', 'functools', 'copy', 'typing', 'numpy'),
    'HASH_NAME_LEN': 12,              # hex chars of a callee hash used as its name inside canonical source
    'SHAM_TOKEN_TOL': 0.05,           # SPEC 5: SHAM total tokens within 5% of the target
    'SHAM_GENRE_BIN': 25,             # SPEC 5: token_len bin width in the genre key
    'SHAM_SHUFFLE_TRIGGER': 0.95,   # SPEC 13 I5: use the shuffled pool only below 95% genre matches
    'SHAM_SWAP_ITERS': 2000,          # bound on the token-matching swap search
    'EXEMPLAR_K': 3,                  # PREREG 4: k = 3 nearest
}


def cfg(name: str):
    """Constant `name`: ratchet.config value when defined there, else the SPEC default above."""
    if _config is not None and hasattr(_config, name):
        return getattr(_config, name)
    return _DEFAULTS[name]


_TOKEN_RE = re.compile(r'\w+|\S')


def count_tokens(text: str, tok=None) -> int:
    """Token count with `tok` (anything with .count(text)); without one, the StubTokenizer rule of SPEC 5."""
    if tok is not None:
        return int(tok.count(text))
    return len(_TOKEN_RE.findall(text))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def canonical_json(obj) -> str:
    """The one JSON form every sha in builder C is computed over."""
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Rows of a jsonl file; a line that fails to parse is skipped only if it is the last one (a torn write)."""
    path = Path(path)
    if not path.exists():
        return
    lines = path.read_text(encoding='utf-8').splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            if i == len(lines) - 1:
                return
            raise


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=str(path.parent))
    try:
        data = text.encode('utf-8')
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            view = view[n:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp, path)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def parse_sample_id(sample_id: str) -> dict:
    """Split `ARM|phase|r<round>|<task>|s<i>` (sealed: `ARM|sealed|k<seed>|<task>|s<i>`) into its fields."""
    parts = sample_id.split('|')
    out = {'arm': None, 'phase': None, 'round': None, 'sealed_seed': None, 'task': None, 'slot': None}
    if len(parts) >= 1:
        out['arm'] = parts[0]
    if len(parts) >= 2:
        out['phase'] = parts[1]
    if len(parts) >= 3:
        m = re.fullmatch(r'r(\d+)', parts[2])
        k = re.fullmatch(r'k(\d+)', parts[2])
        if m:
            out['round'] = int(m.group(1))
        elif k:
            out['sealed_seed'] = int(k.group(1))
    if len(parts) >= 4:
        out['task'] = parts[3]
    if len(parts) >= 5:
        m = re.fullmatch(r's(\d+)', parts[4])
        if m:
            out['slot'] = int(m.group(1))
    return out
