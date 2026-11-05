"""PLANT positive control: Hodel arc-dsl primitives released in R tranches (PREREG 4, SPEC 5 and 13 I6, builder C).

load_arcdsl parses dsl.py, constants.py, arc_types.py and solvers.py statically (no arc-dsl code is executed here).
Each primitive's annotations are rewritten as string literals (`a: 'Numerical'`), so a primitive runs without the
arc_types aliases being defined; the rewritten def is rendered by ast.unparse (docstring kept, signature on one line).
Constants and type aliases a primitive body actually reads become dependency entries.

build_tranches: rank primitives by distinct Hodel solver tasks referencing them (desc), token_len asc, name asc; fit the
capped set with the prompt's greedy fill; the primitive at position i of the capped set (rank order) goes to tranche
i mod R; L_plant_r = tranches 0..r-1 plus their dep closure (cumulative, so L_plant_R is the whole capped set).
"""
from __future__ import annotations

import ast
import builtins
import re
from dataclasses import dataclass, field
from pathlib import Path

from ratchet.c_util import count_tokens, sha256_text
from ratchet.helpers import canonicalize, free_names_of
from ratchet.library import Helper, Library, dep_closure, in_context, rank

_BUILTINS = frozenset(dir(builtins))
_SOLVER = re.compile(r'solve_([0-9a-f]{8})$')


class ArcDslParseError(ValueError):
    pass


@dataclass
class PlantSource:
    primitives: dict[str, str]
    constants_src: str
    types_src: str
    deps: dict[str, set[str]]
    solver_calls: dict[str, set[str]]
    entries: dict[str, str] = field(default_factory=dict)   # constant / type alias name -> one-definition source
    commit: str | None = None


def _string_annotations(fn: ast.FunctionDef) -> ast.FunctionDef:
    a = fn.args
    for arg in a.posonlyargs + a.args + a.kwonlyargs + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else []):
        if arg.annotation is not None:
            arg.annotation = ast.Constant(ast.unparse(arg.annotation))
    if fn.returns is not None:
        fn.returns = ast.Constant(ast.unparse(fn.returns))
    return fn


def _git_commit(d: Path) -> str | None:
    head = d / '.git' / 'HEAD'
    if not head.exists():
        return None
    h = head.read_text().strip()
    if not h.startswith('ref:'):
        return h
    ref = h.split(None, 1)[1]
    p = d / '.git' / ref
    if p.exists():
        return p.read_text().strip()
    packed = d / '.git' / 'packed-refs'
    if packed.exists():
        for line in packed.read_text().splitlines():
            if line.endswith(' ' + ref):
                return line.split()[0]
    return None


def _assign_entries(src: str, typing_ok: bool) -> tuple[dict[str, str], dict[str, str]]:
    """(name -> definition source, typing name -> import line) for single-name top-level assignments."""
    mod = ast.parse(src)
    imports: dict[str, str] = {}
    out: dict[str, str] = {}
    for node in mod.body:
        if isinstance(node, ast.ImportFrom) and typing_ok and node.module == 'typing':
            for a in node.names:
                imports[a.asname or a.name] = f'from typing import {a.name}' + (f' as {a.asname}' if a.asname else '')
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            out[node.targets[0].id] = ast.unparse(node) + '\n'
    return out, imports


def load_arcdsl(dir: Path) -> PlantSource:
    d = Path(dir)
    files = {n: d / n for n in ('dsl.py', 'constants.py', 'arc_types.py', 'solvers.py')}
    missing = [n for n, p in files.items() if not p.exists()]
    if missing:
        raise ArcDslParseError(f'arc-dsl files missing in {d}: {missing}')
    dsl_src = files['dsl.py'].read_text(encoding='utf-8')
    const_src = files['constants.py'].read_text(encoding='utf-8')
    types_src = files['arc_types.py'].read_text(encoding='utf-8')
    solv_src = files['solvers.py'].read_text(encoding='utf-8')
    const_entries, _ = _assign_entries(const_src, False)
    type_entries, typing_imports = _assign_entries(types_src, True)
    prims: dict[str, str] = {}
    for node in ast.parse(dsl_src).body:
        if isinstance(node, ast.FunctionDef):
            prims[node.name] = ast.unparse(_string_annotations(node)) + '\n'
    entries: dict[str, str] = {}
    deps: dict[str, set[str]] = {}

    def entry_deps(name: str, src: str) -> set[str]:
        node = ast.parse(src).body[0]
        names = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
        return names

    pending = []
    for name, src in prims.items():
        free = free_names_of(src) - {name}
        dd = set()
        for f in free:
            if f in prims:
                dd.add(f)
            elif f in const_entries or f in type_entries:
                dd.add(f)
                pending.append(f)
            elif f in _BUILTINS:
                continue
            else:
                raise ArcDslParseError(f'primitive {name} reads unknown name {f}')
        deps[name] = dd
    while pending:
        f = pending.pop()
        if f in entries:
            continue
        src = const_entries.get(f) or type_entries[f]
        imps = []
        dd = set()
        for n in sorted(entry_deps(f, src)):
            if n in typing_imports:
                imps.append(typing_imports[n])
            elif n in const_entries or n in type_entries:
                dd.add(n)
                pending.append(n)
        entries[f] = ('\n'.join(imps) + '\n' if imps else '') + src
        deps[f] = dd
    calls: dict[str, set[str]] = {n: set() for n in prims}
    for node in ast.parse(solv_src).body:
        if isinstance(node, ast.FunctionDef):
            m = _SOLVER.match(node.name)
            if not m:
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and sub.id in prims:
                    calls[sub.id].add(m.group(1))
    return PlantSource(primitives=prims, constants_src=const_src, types_src=types_src, deps=deps, solver_calls=calls,
                       entries=entries, commit=_git_commit(d))


def _full_library(src: PlantSource, tok, arm: str) -> Library:
    helpers = []
    for name, s in src.primitives.items():
        try:
            canon, h = canonicalize(s, None)
        except (SyntaxError, ValueError):
            canon, h = s, sha256_text(s)
        tasks = sorted(src.solver_calls.get(name, ()))
        helpers.append(Helper(name=name, hash=h, source=s, canonical=canon, token_len=count_tokens(s, tok),
                              deps=sorted(src.deps.get(name, ())), first_round=None, accepted_by='plant',
                              calling_tasks=tasks, n_calling_tasks=len(tasks), n_solutions=len(tasks), mdl_gain=0,
                              verified=True, provenance={'source': 'arc-dsl', 'kind': 'primitive', 'commit': src.commit}))
    for name, s in src.entries.items():
        helpers.append(Helper(name=name, hash=sha256_text(s), source=s, canonical=s, token_len=count_tokens(s, tok),
                              deps=sorted(src.deps.get(name, ())), first_round=None, accepted_by='plant',
                              calling_tasks=[], n_calling_tasks=0, n_solutions=0, mdl_gain=0, verified=True,
                              provenance={'source': 'arc-dsl', 'kind': 'definition', 'commit': src.commit}))
    return Library(arm=arm, round=0, helpers=helpers, parent_sha=None, meta={'arcdsl_commit': src.commit})


def build_tranches(src: PlantSource, R: int, cap_tokens: int, tok, arm: str = 'PLANTDRIP') -> list[Library]:
    """Cumulative libraries L_plant_1..L_plant_R (each a Library with round = r)."""
    import copy

    if R < 1:
        raise ValueError('R must be >= 1')
    full = _full_library(src, tok, arm)
    _, names, _ = in_context(full, cap_tokens, tok)
    capped = set(names)
    prim_order = [h.name for h in rank(full) if h.name in capped and h.name in src.primitives]
    tranche = {n: i % R for i, n in enumerate(prim_order)}
    by = full.by_name()
    libs = []
    for r in range(1, R + 1):
        chosen = [n for n in prim_order if tranche[n] < r]
        closure = dep_closure(full, chosen)
        helpers = []
        for n in closure:
            h = copy.deepcopy(by[n])
            h.first_round = (tranche[n] + 1) if n in tranche else min(
                [tranche[m] + 1 for m in chosen if n in dep_closure(full, [m])] or [r])
            helpers.append(h)
        lib = Library(arm=arm, round=r, helpers=helpers, parent_sha=None,
                      meta={'arcdsl_commit': src.commit, 'tranche': r, 'of': R,
                            'primitives': sum(1 for n in closure if n in src.primitives),
                            'capped_primitives': len(prim_order), 'n_primitives_total': len(src.primitives)})
        libs.append(lib)
    return libs
