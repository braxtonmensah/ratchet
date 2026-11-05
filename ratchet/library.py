"""Library merge, rank, render, save/load and sha (SPEC 4.3 and 5, builder C).

The JSON schema is ratchet.library.v1 (SPEC 4.3). `sha256` is computed over the canonical JSON (sorted keys, no spaces)
of every field except `sha256` itself, so the on-disk formatting does not change it. `save` decides `in_context` with
builder B's `prompt.library_block` (the same greedy fill the prompt uses), so the saved flags and the prompt agree.
"""
from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from ratchet.c_util import atomic_write_text, canonical_json, count_tokens, sha256_text

SCHEMA = 'ratchet.library.v1'
CALLABLE_HEADER = 'These functions are already defined; call them directly.'
_TOP_META = ('created_et', 'tokenizer_sha', 'cap_tokens', 'in_context_tokens', 'n_in_context')


class LibraryHashMismatch(ValueError):
    pass


@dataclass
class Helper:
    name: str
    hash: str
    source: str
    canonical: str
    token_len: int
    deps: list[str] = field(default_factory=list)
    first_round: int | None = None
    accepted_by: str = 'two_tasks'
    calling_tasks: list[str] = field(default_factory=list)
    n_calling_tasks: int = 0
    n_solutions: int = 0
    mdl_gain: int = 0
    rank: int | None = None
    in_context: bool = False
    verified: bool = True
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['deps'] = list(self.deps)
        d['calling_tasks'] = list(self.calling_tasks)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Helper':
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


@dataclass
class Library:
    arm: str
    round: int
    helpers: list[Helper]
    parent_sha: str | None
    meta: dict

    def names(self) -> list[str]:
        return [h.name for h in self.helpers]

    def by_name(self) -> dict[str, Helper]:
        return {h.name: h for h in self.helpers}

    def hashes(self) -> dict[str, str]:
        """name -> canonical hash; pass this as `library_names` to helpers.extract_helpers / build_solution."""
        return {h.name: h.hash for h in self.helpers}


def empty(arm: str) -> Library:
    return Library(arm=arm, round=0, helpers=[], parent_sha=None, meta={})


def rank(lib: Library) -> list[Helper]:
    """n_calling_tasks desc, token_len asc, name asc (PREREG 4, SPEC 13 I8)."""
    return sorted(lib.helpers, key=lambda h: (-int(h.n_calling_tasks), int(h.token_len), h.name))


def _assign_ranks(lib: Library) -> None:
    for i, h in enumerate(rank(lib), start=1):
        h.rank = i


def dep_closure(lib: Library, names) -> list[str]:
    """Names plus every library dep, deps before dependents, in rank order (a missing dep is skipped)."""
    by = lib.by_name()
    order = {h.name: i for i, h in enumerate(rank(lib))}
    out: list[str] = []
    seen: set[str] = set()

    def visit(n: str, stack: frozenset):
        if n in seen or n not in by or n in stack:
            return
        for d in sorted(by[n].deps, key=lambda x: (order.get(x, 1 << 30), x)):
            visit(d, stack | {n})
        seen.add(n)
        out.append(n)

    for n in sorted(names, key=lambda x: (order.get(x, 1 << 30), x)):
        visit(n, frozenset())
    return out


def _split_imports(source: str) -> tuple[list[str], str]:
    lines = source.splitlines()
    imps = []
    i = 0
    while i < len(lines) and (lines[i].startswith('import ') or lines[i].startswith('from ')):
        imps.append(lines[i].strip())
        i += 1
    return imps, '\n'.join(lines[i:]).strip('\n') + '\n'


def render_py(lib: Library, names: Sequence[str]) -> str:
    """Python module of `names` (plus dep closure) in rank order, deps first; import lines hoisted and deduped."""
    by = lib.by_name()
    order = dep_closure(lib, names)
    imports: list[str] = []
    bodies: list[str] = []
    for n in order:
        imps, body = _split_imports(by[n].source)
        for line in imps:
            if line not in imports:
                imports.append(line)
        bodies.append(body)
    head = f'# ratchet library arm={lib.arm} round={lib.round} helpers={len(order)}\n'
    parts = [head]
    if imports:
        parts.append('\n'.join(imports) + '\n')
    parts.append('\n\n'.join(bodies))
    return '\n'.join(parts)


def _fallback_block(lib: Library, cap_tokens: int, tok) -> tuple[str, tuple[str, ...], int]:
    """SPEC 5 library_block rule, used only when ratchet.prompt is not importable (tests before builder B lands)."""
    chosen: list[str] = []

    def text(names):
        if not names:
            return ''
        by = lib.by_name()
        return CALLABLE_HEADER + '\n\n' + '\n\n'.join(by[n].source.strip('\n') for n in dep_closure(lib, names)) + '\n'

    for h in rank(lib):
        if h.name in chosen:
            continue
        trial = dep_closure(lib, chosen + [h.name])
        if count_tokens(text(trial), tok) <= cap_tokens:
            chosen = trial
    t = text(chosen)
    return t, tuple(dep_closure(lib, chosen)), count_tokens(t, tok) if t else 0


def in_context(lib: Library, cap_tokens: int, tok) -> tuple[str, tuple[str, ...], int]:
    """(block text, helper names in context, block tokens) via prompt.library_block, else the SPEC fallback."""
    try:
        from ratchet import prompt as _prompt   # builder B
        fn = _prompt.library_block
    except (ImportError, AttributeError):
        fn = None
    if fn is None:
        return _fallback_block(lib, cap_tokens, tok)
    return fn(lib, cap_tokens, tok)


def to_dict(lib: Library) -> dict:
    meta = dict(lib.meta)
    d = {
        'schema': SCHEMA, 'arm': lib.arm, 'round': lib.round, 'parent_sha': lib.parent_sha,
        'created_et': meta.pop('created_et', None), 'tokenizer_sha': meta.pop('tokenizer_sha', None),
        'cap_tokens': meta.pop('cap_tokens', None), 'in_context_tokens': meta.pop('in_context_tokens', None),
        'n_helpers': len(lib.helpers), 'n_in_context': meta.pop('n_in_context', sum(1 for h in lib.helpers if h.in_context)),
        'helpers': [h.to_dict() for h in rank(lib)],
        'extra': meta,
    }
    return d


def sha(lib: Library) -> str:
    return sha256_text(canonical_json(to_dict(lib)))


def from_dict(d: dict) -> Library:
    meta = dict(d.get('extra') or {})
    for k in _TOP_META:
        if d.get(k) is not None:
            meta[k] = d[k]
    return Library(arm=d['arm'], round=int(d['round']), helpers=[Helper.from_dict(h) for h in d.get('helpers', [])],
                   parent_sha=d.get('parent_sha'), meta=meta)


def merge(prev: Library, accepted: Sequence[Helper], round: int, sols: Sequence) -> Library:
    """prev + accepted; tasks whose demo-passing growth solutions call (statically, through library deps) or redefine
    an existing helper join its calling_tasks."""
    from ratchet.helpers import _check_growth, dedup_solutions

    _check_growth(sols)
    helpers = [copy.deepcopy(h) for h in prev.helpers]
    for h in helpers:
        h.in_context = False
        h.rank = None
    by = {h.name: h for h in helpers}
    by_hash = {h.hash: h for h in helpers}
    for s in dedup_solutions([s for s in sols if getattr(s, 'demo_pass', True)]):
        called = {n for n in s.lib_calls if n in by}
        called |= {by_hash[rh.hash].name for rh in s.helpers if rh.hash in by_hash}
        stack = sorted(called)
        while stack:
            n = stack.pop()
            for d in by[n].deps:
                if d in by and d not in called:
                    called.add(d)
                    stack.append(d)
        for n in called:
            h = by[n]
            if s.task not in h.calling_tasks:
                h.calling_tasks = sorted(set(h.calling_tasks) | {s.task})
            h.n_solutions += 1
    names = set(by)
    for a in accepted:
        a = copy.deepcopy(a)
        if a.name in names or a.hash in by_hash:
            raise ValueError(f'merge: accepted helper {a.name} {a.hash[:12]} already in the library')
        if a.first_round is None:
            a.first_round = round
        a.in_context, a.rank = False, None
        helpers.append(a)
        names.add(a.name)
    for h in helpers:
        h.calling_tasks = sorted(set(h.calling_tasks))
        h.n_calling_tasks = len(h.calling_tasks)
    meta = {k: v for k, v in prev.meta.items() if k not in ('in_context_tokens', 'n_in_context', 'created_et')}
    lib = Library(arm=prev.arm, round=round, helpers=helpers,
                  parent_sha=sha(prev) if (prev.round >= 1 or prev.helpers) else None, meta=meta)
    _assign_ranks(lib)
    return lib


def save(lib: Library, dir: Path, cap_tokens: int, tok, stem: str | None = None) -> tuple[Path, Path, str]:
    """Set in_context and rank, write <stem>.json and <stem>.py (default stem L_<round>); returns (json, py, sha).

    Mutates `lib` so that sha(lib) afterwards equals the returned sha."""
    dir = Path(dir)
    stem = stem or f'L_{lib.round}'
    _assign_ranks(lib)
    _, names, ntok = in_context(lib, cap_tokens, tok)
    names = set(names)
    for h in lib.helpers:
        h.in_context = h.name in names
    lib.meta['cap_tokens'] = int(cap_tokens)
    lib.meta['in_context_tokens'] = int(ntok)
    lib.meta['n_in_context'] = len(names)
    tsha = getattr(tok, 'sha256', None) or getattr(tok, 'sha', None)
    if tsha and not lib.meta.get('tokenizer_sha'):
        lib.meta['tokenizer_sha'] = tsha
    d = to_dict(lib)
    s = sha256_text(canonical_json(d))
    d['sha256'] = s
    jp, pp = dir / f'{stem}.json', dir / f'{stem}.py'
    atomic_write_text(jp, json.dumps(d, sort_keys=True, indent=1, ensure_ascii=False) + '\n')
    atomic_write_text(pp, render_py(lib, [h.name for h in rank(lib) if h.in_context]))
    return jp, pp, s


def load(path: Path) -> Library:
    """Read a library JSON and verify its sha256 (raises LibraryHashMismatch)."""
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    want = d.pop('sha256', None)
    got = sha256_text(canonical_json(d))
    if want != got:
        raise LibraryHashMismatch(f'LIBRARY_HASH_MISMATCH {path} file={want} computed={got}')
    lib = from_dict(d)
    if sha(lib) != got:   # the round trip must be exact
        raise LibraryHashMismatch(f'LIBRARY_ROUNDTRIP_MISMATCH {path}')
    return lib
