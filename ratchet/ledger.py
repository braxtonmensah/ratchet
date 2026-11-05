"""Token ledger (SPEC 4.4, 5 builder B; PREREG 3 and 10). Owner: builder B.

One file per job, `runs/<run>/ledger/ledger_<jobid>.jsonl`, one row per vLLM request. `prompt_tokens` and
`gen_tokens` are vLLM `usage` values (exact); `prompt_tokens_logical` = `prompt_tokens` x n is what every token match
uses (SPEC 13 I2). Rows are appended under a lock, flushed every row and fsynced every LEDGER_FSYNC_EVERY rows and at
close. Readers dedup by request_id (last wins: a request re-issued after an abandoned job replaces the old row) and
drop a torn last line.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Iterable, Iterator

try:   # builder D owns config.py
    from ratchet import config as _config
except ImportError:   # pragma: no cover
    _config = None

_DEFAULTS = {
    'LEDGER_FSYNC_EVERY': 32,
    'LEDGER_PHASES': ('growth', 'sealed', 'perturbed', 'knockout_delete', 'knockout_inline', 'pilot', 'arcagi2'),
}


def _cfg(name: str):
    if _config is not None and hasattr(_config, name):
        return getattr(_config, name)
    return _DEFAULTS[name]


SCHEMA = 'ratchet.ledger.v1'

# field -> allowed types (SPEC 4.4). None in a tuple means the value may be null.
_INT = (int,)
_FIELDS: dict[str, tuple] = {
    'ts_et': (str,), 'run': (str,), 'job_id': (str,), 'arm': (str,), 'phase': (str,),
    'round': (int, type(None)), 'sealed_seed': (int, type(None)), 'task': (str,), 'request_id': (str,),
    'n': _INT, 'seed': _INT,
    'prompt_tokens': _INT, 'prompt_tokens_logical': _INT,
    'cached_prompt_tokens': (int, type(None)),     # null when the server does not report prompt_tokens_details
    'library_tokens': _INT, 'exemplar_tokens': _INT, 'task_tokens': _INT, 'instruction_tokens': _INT,
    'gen_tokens': _INT, 'gen_tokens_per_sample': (list,), 'finish_reasons': (list,),
    'latency_s': (int, float), 'lib_sha': (str, type(None)), 'model_sha': (str, type(None)),
    'sampling': (dict,),
}
REQUIRED = tuple(_FIELDS)
SAMPLING_KEYS = ('temperature', 'top_p', 'max_tokens', 'enable_thinking')


class LedgerSchemaError(ValueError):
    pass


def validate(row: dict) -> None:
    """Raise LedgerSchemaError unless `row` has every SPEC 4.4 field with the right type and consistent counts."""
    missing = [k for k in REQUIRED if k not in row]
    if missing:
        raise LedgerSchemaError(f'missing fields {missing}')
    for k, types in _FIELDS.items():
        v = row[k]
        if isinstance(v, bool) and bool not in types:
            raise LedgerSchemaError(f'{k} is bool')
        if not isinstance(v, types):
            raise LedgerSchemaError(f'{k}={v!r} has type {type(v).__name__}')
    if row['phase'] not in _cfg('LEDGER_PHASES'):
        raise LedgerSchemaError(f'phase {row["phase"]!r}')
    n = row['n']
    if n < 1:
        raise LedgerSchemaError(f'n={n}')
    if len(row['finish_reasons']) != n or len(row['gen_tokens_per_sample']) != n:
        raise LedgerSchemaError(f'n={n} but {len(row["finish_reasons"])} finish_reasons, '
                                f'{len(row["gen_tokens_per_sample"])} gen_tokens_per_sample')
    if row['prompt_tokens_logical'] != row['prompt_tokens'] * n:
        raise LedgerSchemaError('prompt_tokens_logical != prompt_tokens x n')
    for k in ('prompt_tokens', 'gen_tokens', 'library_tokens', 'exemplar_tokens', 'task_tokens', 'instruction_tokens'):
        if row[k] < 0:
            raise LedgerSchemaError(f'{k} < 0')
    if row['cached_prompt_tokens'] is not None and not 0 <= row['cached_prompt_tokens'] <= row['prompt_tokens']:
        raise LedgerSchemaError('cached_prompt_tokens outside [0, prompt_tokens]')
    miss = [k for k in SAMPLING_KEYS if k not in row['sampling']]
    if miss:
        raise LedgerSchemaError(f'sampling lacks {miss}')


def tokdiff(row: dict) -> int:
    """|sum(local per-sample counts) - usage gen_tokens|; SPEC 4.4 tolerates up to n."""
    return abs(sum(int(x) for x in row['gen_tokens_per_sample']) - int(row['gen_tokens']))


class Ledger:
    """Append-only writer for one job's ledger file. Thread safe."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _repair_torn_tail(self.path)
        self._f = open(self.path, 'a', encoding='utf-8')
        self._lock = threading.Lock()
        self._since_sync = 0
        self.rows_written = 0
        self.tokdiff_rows = 0
        self.closed = False

    def append(self, row: dict) -> None:
        validate(row)
        d = tokdiff(row)
        if d > row['n']:
            self.tokdiff_rows += 1
            print(f'LEDGER_TOKDIFF request_id={row["request_id"]} local={sum(row["gen_tokens_per_sample"])} '
                  f'usage={row["gen_tokens"]} n={row["n"]}', flush=True)
        line = json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n'
        with self._lock:
            if self.closed:
                raise ValueError('ledger closed')
            self._f.write(line)
            self._f.flush()
            self.rows_written += 1
            self._since_sync += 1
            if self._since_sync >= int(_cfg('LEDGER_FSYNC_EVERY')):
                os.fsync(self._f.fileno())
                self._since_sync = 0

    def sync(self) -> None:
        with self._lock:
            if not self.closed:
                self._f.flush()
                os.fsync(self._f.fileno())
                self._since_sync = 0

    def close(self) -> None:
        with self._lock:
            if self.closed:
                return
            self._f.flush()
            os.fsync(self._f.fileno())
            self._f.close()
            self.closed = True

    def __enter__(self) -> 'Ledger':
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class NullLedger:
    """Ledger that validates and keeps rows in memory (tests and dry runs)."""

    def __init__(self):
        self.rows: list[dict] = []
        self._lock = threading.Lock()

    def append(self, row: dict) -> None:
        validate(row)
        with self._lock:
            self.rows.append(row)

    def sync(self) -> None:
        pass

    def close(self) -> None:
        pass


def _repair_torn_tail(path: Path) -> int:
    """Truncate a last line with no newline that does not parse (a job killed mid-write). Returns bytes dropped."""
    if not path.is_file():
        return 0
    size = path.stat().st_size
    if size == 0:
        return 0
    with open(path, 'rb+') as f:
        f.seek(max(0, size - 1))
        if f.read(1) == b'\n':
            return 0
        # find the start of the last line
        pos = size - 1
        chunk = 4096
        start = 0
        while pos > 0:
            lo = max(0, pos - chunk)
            f.seek(lo)
            buf = f.read(pos - lo)
            i = buf.rfind(b'\n')
            if i >= 0:
                start = lo + i + 1
                break
            pos = lo
        f.seek(start)
        tail = f.read()
        try:
            json.loads(tail)
            f.seek(size)
            f.write(b'\n')       # a complete row that only lacked its newline
            return 0
        except ValueError:
            f.truncate(start)
            print(f'LEDGER_TORN_TAIL path={path} dropped_bytes={size - start}', file=sys.stderr, flush=True)
            return size - start


def _iter_file(path: Path) -> Iterator[dict]:
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')
    last = len(lines) - 1
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        try:
            yield json.loads(ln)
        except ValueError:
            if i >= last - 1:   # torn last line (with or without a trailing empty string)
                continue
            raise


_JOB_RE = re.compile(r'ledger_(.+)\.jsonl$')


def _file_order(p: Path):
    m = _JOB_RE.search(p.name)
    j = m.group(1) if m else p.name
    return (0, int(j), '') if j.isdigit() else (1, 0, j)


def ledger_files(run_dir: Path) -> list[Path]:
    d = Path(run_dir) / 'ledger'
    if not d.is_dir():
        return []
    return sorted(d.glob('ledger_*.jsonl'), key=_file_order)


def iter_rows(run_dir: Path) -> Iterator[dict]:
    """Every ledger row of the run, deduped by request_id (last wins; files in job-id order, rows in file order)."""
    last: dict[str, dict] = {}
    for p in ledger_files(run_dir):
        for row in _iter_file(p):
            rid = row.get('request_id')
            if rid is None:
                continue
            last.pop(rid, None)   # re-insert so iteration order is the order of the winning row
            last[rid] = row
    yield from last.values()


def _match(row: dict, arm, phase, sealed_seed) -> bool:
    def ok(val, want):
        if want is None:
            return True
        if isinstance(want, (tuple, list, set, frozenset)):
            return val in want
        return val == want
    return ok(row.get('arm'), arm) and ok(row.get('phase'), phase) and ok(row.get('sealed_seed'), sealed_seed)


def totals_of(rows: Iterable[dict], arm=None, phase=None, sealed_seed=None) -> dict:
    """Sum over rows matching the filters (None = no filter; a tuple = any of)."""
    t = {'prompt': 0, 'prompt_logical': 0, 'cached': 0, 'cached_known_rows': 0, 'library': 0, 'library_logical': 0,
         'exemplar_logical': 0, 'task_logical': 0, 'instruction_logical': 0, 'gen': 0, 'logical_total': 0,
         'samples': 0, 'requests': 0, 'truncated': 0}
    for row in rows:
        if not _match(row, arm, phase, sealed_seed):
            continue
        n = int(row.get('n', 1) or 1)
        p = int(row.get('prompt_tokens', 0))
        pl = row.get('prompt_tokens_logical')
        pl = p * n if pl is None else int(pl)
        g = int(row.get('gen_tokens', 0))
        t['prompt'] += p
        t['prompt_logical'] += pl
        c = row.get('cached_prompt_tokens')
        if c is not None:
            t['cached'] += int(c)
            t['cached_known_rows'] += 1
        lib = int(row.get('library_tokens', 0))
        t['library'] += lib
        t['library_logical'] += lib * n
        t['exemplar_logical'] += int(row.get('exemplar_tokens', 0)) * n
        t['task_logical'] += int(row.get('task_tokens', 0)) * n
        t['instruction_logical'] += int(row.get('instruction_tokens', 0)) * n
        t['gen'] += g
        t['logical_total'] += pl + g
        t['samples'] += n
        t['requests'] += 1
        t['truncated'] += sum(1 for fr in row.get('finish_reasons', ()) if fr == 'length')
    return t


def totals(run_dir: Path, arm: str | None = None, phase: str | None = None, sealed_seed: int | None = None) -> dict:
    """SPEC 5 totals: {'prompt', 'prompt_logical', 'cached', 'library', 'gen', 'logical_total', 'samples',
    'requests', 'truncated'} plus the logical block split. 'library' is the per-request library block tokens summed
    over requests; 'library_logical' multiplies by n. 'truncated' counts samples with finish_reason 'length'."""
    return totals_of(iter_rows(run_dir), arm=arm, phase=phase, sealed_seed=sealed_seed)
