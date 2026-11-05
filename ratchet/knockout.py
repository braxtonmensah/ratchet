"""PREREG 6.3 knockout libraries (SPEC 5 E, 13 I11).

For each task in W (sealed tasks STOCK solves and FLAT-TTC does not), with K = the helpers STOCK's winning programs
called at runtime on that task plus every helper whose dependency closure reaches one of them (it would raise NameError
if called):
- delete mode: exactly the helpers L_R puts in context, minus K. Helpers L_R left out of context stay out, so the
  freed tokens are not refilled by lower-ranked helpers (review fix 2026-11-04). Sandbox mode 'deleted'.
- inline mode (PREREG 6.3b, "with the helpers inlined as non-callable text"): the same callable set as delete mode,
  plus K shown as non-callable reference text (inline_text_library). Every helper outside K stays callable; the
  sandbox executes only the callable set (mode 'deleted'). Review fix 2026-11-04: inline mode used to show the whole
  L_R as non-callable and execute no library at all, which knocked out every helper, not only the called ones, and
  made "removes at least half of those solves" easier to pass. K's own dependencies outside K stay callable, so the
  inlined text runs if copied.

Inputs come from score outputs only: scores/W.json (ids), scores/winners.json (sample ids) and the loop's own sealed
exec rows (helper_calls). No grid is read here. Builder D (arms.build_knockout, freeze.freeze_knockout) saves the
libraries, samples both modes and writes KO_FREEZE.json; score_sealed.py verifies it before the knockout read.
"""
from __future__ import annotations

import copy
import glob
import os
from pathlib import Path
from typing import Mapping, Sequence

from .e_util import get, iter_jsonl, read_json

MODES = ('delete', 'inline')


def called_helpers(winners: Sequence) -> frozenset[str]:
    """Names with a runtime call count > 0 in any winning exec row."""
    out: set[str] = set()
    for r in winners:
        for k, v in dict(get(r, 'helper_calls', None) or {}).items():
            if int(v) > 0:
                out.add(str(k))
    return frozenset(out)


def _helpers(lib) -> list:
    return list(get(lib, 'helpers', []) or [])


def _deps(h) -> list[str]:
    return list(get(h, 'deps', []) or [])


def delete_closure(lib, removed: frozenset[str]) -> frozenset[str]:
    """`removed` plus every helper whose dependency closure reaches a removed name."""
    by = {get(h, 'name'): h for h in _helpers(lib)}
    gone = set(n for n in removed if n in by)
    changed = True
    while changed:
        changed = False
        for n, h in by.items():
            if n not in gone and any(d in gone for d in _deps(h)):
                gone.add(n)
                changed = True
    return frozenset(gone)


def _set(obj, name, value):
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


def _in_ctx(h) -> bool:
    return bool(get(h, 'in_context', False))


def build_knockout_libraries(L_R, W: frozenset[str], winners: Mapping[str, Sequence]) -> dict[str, object]:
    """Per task in W: the delete-mode library = L_R's in-context helpers without the task's called helpers and their
    dependents (a deep copy; out-of-context helpers are dropped so nothing refills the freed tokens).

    Tasks whose winners called no library helper keep every in-context helper (removed set empty), so the knockout
    cannot remove that solve. The inline-mode text for the same task comes from inline_text_library.
    """
    out: dict[str, object] = {}
    for t in sorted(W):
        called = called_helpers(list(winners.get(t, []) or []))
        gone = delete_closure(L_R, called)
        lib = copy.deepcopy(L_R)
        _set(lib, 'helpers', [h for h in _helpers(lib) if _in_ctx(h) and get(h, 'name') not in gone])
        meta = dict(get(lib, 'meta', {}) or {})
        meta.update({'knockout_mode': 'delete', 'knockout_task': t, 'knockout_called': sorted(called),
                     'knockout_removed': sorted(gone), 'parent_lib_sha': _lib_sha(L_R)})
        _set(lib, 'meta', meta)
        _set(lib, 'arm', 'KO_DELETE')
        out[t] = lib
    return out


def inline_text_library(L_R, gone: frozenset[str], task: str):
    """The helpers of `gone` that L_R puts in context, as a library rendered under the NON-callable header
    (prompt.build_messages inline_library); never executed."""
    lib = copy.deepcopy(L_R)
    _set(lib, 'helpers', [h for h in _helpers(lib) if _in_ctx(h) and get(h, 'name') in gone])
    meta = dict(get(lib, 'meta', {}) or {})
    meta.update({'knockout_mode': 'inline', 'knockout_task': task, 'knockout_inlined': sorted(gone),
                 'parent_lib_sha': _lib_sha(L_R)})
    _set(lib, 'meta', meta)
    _set(lib, 'arm', 'KO_INLINE')
    return lib


def inline_library(L_R):
    """Whole L_R as one non-callable text block (the pre-fix reading of PREREG 6.3b; kept for reference, unused)."""
    lib = copy.deepcopy(L_R)
    meta = dict(get(lib, 'meta', {}) or {})
    meta.update({'knockout_mode': 'inline', 'parent_lib_sha': _lib_sha(L_R)})
    _set(lib, 'meta', meta)
    _set(lib, 'arm', 'KO_INLINE')
    return lib


def _lib_sha(lib) -> str | None:
    try:
        from . import library
        return library.sha(lib)
    except Exception:
        return None


def ko_marker(mode: str, task: str, removed: Sequence[str] = ()) -> str:
    """Rule 6 marker (SPEC 9). The sampler prints it once per task when the sandbox namespace is built."""
    if mode == 'delete':
        return f'LEVER KO_DELETE task={task} removed={",".join(sorted(removed)) or "none"}'
    return f'LEVER KO_INLINE task={task} callable=0 inlined={",".join(sorted(removed)) or "none"}'


# ---------------------------------------------------------------------------------------------------------------------
# run-directory side

def ko_library_dir(run_dir: Path, mode: str, task: str) -> Path:
    return Path(run_dir) / 'knockout' / mode / 'libraries' / task


def load_W_and_winners(run_dir: Path) -> tuple[frozenset[str], dict[str, list[str]]]:
    s = Path(run_dir) / 'scores'
    W = frozenset((read_json(s / 'W.json', {}) or {}).get('W', []))
    win = (read_json(s / 'winners.json', {}) or {}).get('winners', {})
    return W, {t: list(v) for t, v in win.items()}


def winner_exec_rows(run_dir: Path, winners_ids: Mapping[str, Sequence[str]], arm: str = 'STOCK',
                     condition: str = 'sealed') -> dict[str, list[dict]]:
    """Exec rows (loop data) of the winning sample ids, grouped by task."""
    want = {sid for v in winners_ids.values() for sid in v}
    rows: dict[str, dict] = {}
    for p in sorted(glob.glob(os.path.join(str(run_dir), 'sealed', condition, arm, 'seed_*', 'exec.jsonl'))):
        for r in iter_jsonl(p):
            sid = r.get('sample_id')
            if sid in want:
                rows[sid] = r
    out: dict[str, list[dict]] = {}
    for t, sids in winners_ids.items():
        out[t] = [rows[s] for s in sids if s in rows]
    return out


def stock_final_library_path(run_dir: Path) -> Path:
    fz = read_json(Path(run_dir) / 'freeze' / 'FREEZE.json', {}) or {}
    ent = (fz.get('libraries') or {}).get('STOCK') or {}
    p = ent.get('json')
    if not p:
        raise FileNotFoundError('FREEZE.json has no libraries.STOCK.json')
    p = Path(p)
    return p if p.is_absolute() else Path(run_dir) / p

