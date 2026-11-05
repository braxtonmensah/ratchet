"""Helper extraction, canonicalization, MDL and the STOCK acceptance rule (PREREG 4, SPEC 5, builder C).

A helper is a top-level `def` of a demo-passing growth program other than `transform`. Its canonical form strips
docstrings, comments and annotations, renames the function to `h`, its parameters to a0.., every other local to v0..
(order of first appearance), and every callee helper to `h_<first 12 hex of its canonical sha256>`, then ast.unparse.
Alpha-equivalent helpers therefore share one hash.

Acceptance (PREREG 4, SPEC 13 I7): a helper not already in the previous library is accepted iff it is defined in deduped
demo-passing growth solutions of at least ACCEPT_MIN_TASKS distinct tasks, or mdl_gain >= ACCEPT_MIN_MDL, where
mdl_gain = (k - 1) x token_len(canonical) and k = number of deduped solutions defining it. Deps of an accepted helper
are accepted with it. Any non-growth sample raises SealedHelperRefused.
"""
from __future__ import annotations

import ast
import builtins
import copy
import symtable
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from ratchet.c_util import cfg, count_tokens, parse_sample_id, sha256_text


class SealedHelperRefused(ValueError):
    """A solution from a phase other than growth reached the acceptance rule (PREREG 4: sealed never contributes)."""


_BUILTINS = frozenset(dir(builtins))


@dataclass
class RawHelper:
    name: str
    source: str
    canonical: str
    hash: str
    deps: tuple[str, ...]
    free_names: tuple[str, ...]
    sample_id: str
    task: str
    genre: tuple


@dataclass
class Solution:
    sample_id: str
    task: str
    code: str
    code_sha: str
    helpers: tuple[RawHelper, ...]
    lib_calls: frozenset[str]
    prog_hash: str = ''          # canonical program hash used by dedup_solutions
    demo_pass: bool = True       # accept() ignores solutions with demo_pass False


# ----------------------------------------------------------------------------------------------------------------------
# parsing and free names

def parse_program(code: str) -> ast.Module | None:
    if not isinstance(code, str) or not code.strip():
        return None
    try:
        return ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError, OverflowError):
        return None


def _segment(code: str, node: ast.AST) -> str:
    lines = code.splitlines()
    start = min([node.lineno] + [d.lineno for d in getattr(node, 'decorator_list', [])])
    seg = '\n'.join(lines[start - 1:node.end_lineno])
    return seg.rstrip() + '\n'


def free_names_of(fn_src: str) -> set[str]:
    """Names a top-level def (plus decorators) reads from module scope or builtins, via symtable."""
    try:
        st = symtable.symtable(fn_src, '<helper>', 'exec')
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return set()
    out: set[str] = set()
    for sym in st.get_symbols():
        if sym.is_referenced() and not sym.is_assigned() and not sym.is_imported():
            out.add(sym.get_name())

    def walk(t):
        for sym in t.get_symbols():
            if sym.is_global():
                out.add(sym.get_name())
        for c in t.get_children():
            walk(c)

    for c in st.get_children():
        walk(c)
    return out


def _allowed_roots() -> frozenset[str]:
    return frozenset(cfg('SANDBOX_IMPORT_ALLOW'))


def _module_imports(mod: ast.Module) -> tuple[dict[str, str], set[str]]:
    """(bound name -> one-line import that binds it, for allowed modules; names bound by disallowed imports)."""
    allowed = _allowed_roots()
    good: dict[str, str] = {}
    bad: set[str] = set()
    for node in mod.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                bound = a.asname or a.name.split('.')[0]
                if a.name.split('.')[0] in allowed:
                    good[bound] = ast.unparse(ast.Import(names=[ast.alias(name=a.name, asname=a.asname)]))
                else:
                    bad.add(bound)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or '').split('.')[0]
            for a in node.names:
                bound = a.asname or a.name
                if node.level == 0 and root in allowed and a.name != '*':
                    good[bound] = ast.unparse(ast.ImportFrom(module=node.module, names=[ast.alias(name=a.name, asname=a.asname)], level=0))
                else:
                    bad.add(bound)
    return good, bad


def _module_other_bound(mod: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in mod.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.AsyncFunctionDef):
                out.add(node.name)
            continue
        if isinstance(node, ast.ClassDef):
            out.add(node.name)
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
                out.add(sub.id)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# canonicalization

def _strip(node: ast.AST) -> ast.AST:
    """Remove docstrings and annotations in place (recursively)."""
    for sub in ast.walk(node):
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = sub.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant) \
                    and isinstance(body[0].value.value, str):
                body = body[1:]
            sub.body = body or [ast.Pass()]
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sub.returns = None
                a = sub.args
                for arg in a.posonlyargs + a.args + a.kwonlyargs + ([a.vararg] if a.vararg else []) + ([a.kwarg] if a.kwarg else []):
                    arg.annotation = None
        if isinstance(sub, ast.Lambda):
            pass
        for fld in ('body', 'orelse', 'finalbody'):
            stmts = getattr(sub, fld, None)
            if isinstance(stmts, list) and stmts and isinstance(stmts[0], ast.stmt):
                new = []
                for s in stmts:
                    if isinstance(s, ast.AnnAssign):
                        if s.value is None:
                            continue
                        s = ast.Assign(targets=[s.target], value=s.value, lineno=s.lineno, col_offset=s.col_offset)
                    new.append(s)
                setattr(sub, fld, new or [ast.Pass()])
    return node


def _bound_name_events(node: ast.AST):
    """Yield every identifier occurrence that could be a local, in DFS field order."""
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, ast.arg):
        yield node.arg
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name
    elif isinstance(node, ast.ExceptHandler) and node.name:
        yield node.name
    elif isinstance(node, ast.alias):
        yield node.asname or node.name.split('.')[0]
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        yield from node.names
    for child in ast.iter_child_nodes(node):
        yield from _bound_name_events(child)


class _Renamer(ast.NodeTransformer):
    def __init__(self, mapping: Mapping[str, str]):
        self.m = mapping

    def visit_Name(self, node):
        if node.id in self.m:
            node.id = self.m[node.id]
        return node

    def visit_arg(self, node):
        if node.arg in self.m:
            node.arg = self.m[node.arg]
        self.generic_visit(node)
        return node

    def _named(self, node):
        if node.name in self.m:
            node.name = self.m[node.name]
        self.generic_visit(node)
        return node

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _named

    def visit_ExceptHandler(self, node):
        if node.name and node.name in self.m:
            node.name = self.m[node.name]
        self.generic_visit(node)
        return node

    def visit_alias(self, node):
        bound = node.asname or node.name.split('.')[0]
        if bound in self.m:
            node.asname = self.m[bound]
        return node

    def visit_Global(self, node):
        node.names = [self.m.get(n, n) for n in node.names]
        return node

    visit_Nonlocal = visit_Global


def hash_name(h: str) -> str:
    return 'h_' + h[:int(cfg('HASH_NAME_LEN'))]


def _last_def(mod: ast.Module) -> ast.FunctionDef:
    defs = [n for n in mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not defs:
        raise ValueError('canonicalize: no function definition in source')
    return defs[-1]


def canonicalize(fn_src: str, callee_hashes: Mapping[str, str] | None = None) -> tuple[str, str]:
    """(canonical source, sha256 hex). `callee_hashes` maps callee helper names to their canonical hashes."""
    mod = ast.parse(fn_src)
    fn = copy.deepcopy(_last_def(mod))
    own = fn.name
    _strip(fn)
    fn.lineno = getattr(fn, 'lineno', 1)
    globals_ = free_names_of(ast.unparse(ast.Module(body=[fn], type_ignores=[])))
    mapping: dict[str, str] = {own: 'h'}
    a = fn.args
    params = [x.arg for x in a.posonlyargs + a.args] + ([a.vararg.arg] if a.vararg else []) + \
             [x.arg for x in a.kwonlyargs] + ([a.kwarg.arg] if a.kwarg else [])
    for i, p in enumerate(params):
        mapping.setdefault(p, f'a{i}')
    n_local = 0
    for body_node in fn.body + fn.decorator_list:
        for ident in _bound_name_events(body_node):
            if ident in mapping or ident in globals_:
                continue
            mapping[ident] = f'v{n_local}'
            n_local += 1
    for g in globals_:
        if g == own:
            continue
        if callee_hashes and g in callee_hashes:
            mapping[g] = hash_name(callee_hashes[g])
        else:
            mapping.pop(g, None)
    fn = _Renamer(mapping).visit(fn)
    canonical = ast.unparse(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])))
    return canonical, sha256_text(canonical)


def program_hash(code: str, helper_hashes: Mapping[str, str]) -> str | None:
    """Canonical program hash: canonical transform (callees by hash) plus every top-level statement that is not a def."""
    mod = parse_program(code)
    if mod is None:
        return None
    tr = [n for n in mod.body if isinstance(n, ast.FunctionDef) and n.name == 'transform']
    if not tr:
        return None
    seg = _segment(code, tr[-1])
    try:
        canon, _ = canonicalize(seg, helper_hashes)
    except (SyntaxError, ValueError):
        canon = ast.unparse(tr[-1])
    rest = [ast.unparse(_strip(copy.deepcopy(n))) for n in mod.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not (isinstance(n, ast.Expr) and isinstance(getattr(n, 'value', None), ast.Constant) and isinstance(n.value.value, str))]
    return sha256_text(canon + '\n#--\n' + '\n'.join(rest))


# ----------------------------------------------------------------------------------------------------------------------
# genre (structural part; sham.genre adds the token-length bin)

def _return_kind(expr: ast.AST | None, assigns: Mapping[str, ast.AST], depth: int = 0) -> str:
    if expr is None:
        return 'none'
    if isinstance(expr, ast.Constant):
        if expr.value is None:
            return 'none'
        if isinstance(expr.value, bool):
            return 'bool'
        if isinstance(expr.value, (int, float)):
            return 'int'
        return 'list'
    if isinstance(expr, (ast.Compare, ast.BoolOp)) or (isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not)):
        return 'bool'
    if isinstance(expr, ast.Tuple):
        return 'tuple'
    if isinstance(expr, (ast.List, ast.ListComp)):
        elt = expr.elts[0] if isinstance(expr, ast.List) and expr.elts else getattr(expr, 'elt', None)
        if isinstance(elt, (ast.List, ast.ListComp)) or (isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name)
                                                       and elt.func.id in ('list', 'tuple')) \
                or (isinstance(elt, ast.Subscript) and isinstance(elt.slice, ast.Slice)):
            return 'grid'
        return 'list'
    if isinstance(expr, (ast.Set, ast.SetComp, ast.Dict, ast.DictComp, ast.GeneratorExp)):
        return 'list'
    if isinstance(expr, ast.BinOp):
        l = _return_kind(expr.left, assigns, depth + 1)
        return l if l in ('grid', 'list', 'tuple') else 'int'
    if isinstance(expr, ast.Call):
        f = expr.func
        fname = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else '')
        if fname in ('len', 'sum', 'max', 'min', 'abs', 'int', 'round', 'count', 'index'):
            return 'int'
        if fname in ('bool', 'all', 'any', 'isinstance'):
            return 'bool'
        if fname == 'tuple':
            return 'tuple'
        if fname in ('deepcopy', 'tolist', 'zeros', 'array', 'full', 'rot90', 'flip', 'transpose', 'copy'):
            return 'grid'
        if fname in ('list', 'sorted', 'set', 'frozenset', 'dict', 'Counter', 'defaultdict'):
            return 'list'
        return 'list'
    if isinstance(expr, ast.Name) and depth < 3 and expr.id in assigns:
        return _return_kind(assigns[expr.id], assigns, depth + 1)
    if isinstance(expr, ast.Name):
        return 'grid'
    return 'list'


def genre_parts(fn_src: str) -> tuple:
    """(arity, return kind, has_loop, uses_numpy) of the last def in fn_src."""
    try:
        fn = _last_def(ast.parse(fn_src))
    except (SyntaxError, ValueError):
        return (0, 'none', False, False)
    a = fn.args
    arity = len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs) + (1 if a.vararg else 0) + (1 if a.kwarg else 0)
    assigns: dict[str, ast.AST] = {}
    kinds: list[str] = []
    has_loop = False
    uses_np = False

    def visit(node, top):
        nonlocal has_loop, uses_np
        for child in ast.iter_child_nodes(node):
            nested = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef))
            if isinstance(child, (ast.For, ast.While, ast.AsyncFor, ast.comprehension)):
                has_loop = True
            if isinstance(child, ast.Name) and child.id in ('np', 'numpy'):
                uses_np = True
            if top and not nested:
                if isinstance(child, ast.Assign):
                    for t in child.targets:
                        if isinstance(t, ast.Name) and t.id not in assigns:
                            assigns[t.id] = child.value
                if isinstance(child, ast.Return):
                    kinds.append(child)
            visit(child, top and not nested)

    visit(fn, True)
    ks = [_return_kind(r.value, assigns) for r in kinds]
    if not ks:
        kind = 'none'
    else:
        counts: dict[str, int] = {}
        for k in ks:
            counts[k] = counts.get(k, 0) + 1
        kind = max(counts, key=lambda k: (counts[k], -ks.index(k)))
    return (arity, kind, has_loop, uses_np)


# ----------------------------------------------------------------------------------------------------------------------
# extraction

UNBOUND_LOG: list[dict] = []   # (sample_id, helper, names) of helpers dropped for unbound free names; caller may flush


def _analyze(code: str, library_names) -> dict | None:
    mod = parse_program(code)
    if mod is None:
        return None
    imports, bad_imports = _module_imports(mod)
    other = _module_other_bound(mod) | bad_imports
    funcs: dict[str, ast.FunctionDef] = {}
    for node in mod.body:
        if isinstance(node, ast.FunctionDef):
            funcs[node.name] = node
    for n in list(funcs):
        if n in other:
            del funcs[n]
    has_transform = 'transform' in funcs
    lib_hashes = dict(library_names) if isinstance(library_names, Mapping) else {}
    lib_set = frozenset(library_names or ())
    allowed = _allowed_roots()
    info: dict[str, dict] = {}
    for name, node in funcs.items():
        seg = _segment(code, node)
        free = free_names_of(seg) - {name}
        local, libd, imps, unbound = set(), set(), [], set()
        for f in sorted(free):
            if f in funcs and f != 'transform':
                local.add(f)
            elif f == 'transform':
                unbound.add(f)
            elif f in imports:
                imps.append(imports[f])
            elif f in other:
                unbound.add(f)
            elif f in lib_set:
                libd.add(f)
            elif f in allowed:
                imps.append(f'import {f}')
            elif f in _BUILTINS:
                pass
            else:
                unbound.add(f)
        info[name] = {'node': node, 'seg': seg, 'free': free, 'local': local, 'lib': libd, 'imports': imps,
                      'unbound': unbound}
    # canonical hashes in dependency order (a cycle falls back to the raw callee name)
    hashes: dict[str, str] = {}
    canon: dict[str, str] = {}
    visiting: set[str] = set()

    def h_of(n: str) -> str | None:
        if n in hashes:
            return hashes[n]
        if n in visiting:
            return None
        visiting.add(n)
        ch = {}
        for d in info[n]['local']:
            hd = h_of(d)
            if hd is not None:
                ch[d] = hd
        for d in info[n]['lib']:
            if d in lib_hashes:
                ch[d] = lib_hashes[d]
        try:
            c, hs = canonicalize(info[n]['seg'], ch)
        except (SyntaxError, ValueError, RecursionError):
            c, hs = info[n]['seg'], sha256_text(info[n]['seg'])
        visiting.discard(n)
        hashes[n], canon[n] = hs, c
        return hs

    for n in sorted(info):
        h_of(n)
    # validity fixpoint: unbound names, or a dep that is itself invalid
    valid = {n for n in info if not info[n]['unbound'] and n != 'transform'}
    changed = True
    while changed:
        changed = False
        for n in sorted(valid):
            if not info[n]['local'] <= valid:
                valid.discard(n)
                changed = True
    # reachability from transform
    reach: set[str] = set()
    if has_transform:
        stack = sorted(info['transform']['local'])
        while stack:
            n = stack.pop()
            if n in reach:
                continue
            reach.add(n)
            stack.extend(sorted(info[n]['local']))
    lib_reach = set(info['transform']['lib']) if has_transform else set()
    for n in reach:
        lib_reach |= info[n]['lib']
    return {'mod': mod, 'info': info, 'hashes': hashes, 'canon': canon, 'valid': valid, 'reach': reach,
            'lib_reach': lib_reach, 'has_transform': has_transform}


def _raw(name: str, a: dict, sample_id: str, task: str) -> RawHelper:
    inf = a['info'][name]
    imports = list(dict.fromkeys(inf['imports']))
    source = ('\n'.join(imports) + '\n' if imports else '') + inf['seg']
    return RawHelper(name=name, source=source, canonical=a['canon'][name], hash=a['hashes'][name],
                     deps=tuple(sorted(inf['local'] | inf['lib'])), free_names=tuple(sorted(inf['free'])),
                     sample_id=sample_id, task=task, genre=genre_parts(inf['seg']))


def extract_helpers(code: str, sample_id: str, task: str, library_names=frozenset(), *,
                    reachable_only: bool = True) -> list[RawHelper]:
    """Top-level defs other than transform; unbound helpers (and helpers depending on them) are dropped and logged.

    `library_names` is a frozenset of names, or a Mapping name -> canonical hash (then library callees enter the
    canonical form by hash). With reachable_only (default) only helpers reachable from transform are returned.
    """
    a = _analyze(code, library_names)
    if a is None:
        return []
    out = []
    for name in sorted(a['info']):
        if name == 'transform':
            continue
        if reachable_only and name not in a['reach']:
            continue
        if name not in a['valid']:
            UNBOUND_LOG.append({'sample_id': sample_id, 'helper': name, 'unbound': sorted(a['info'][name]['unbound'])})
            continue
        out.append(_raw(name, a, sample_id, task))
    return out


def build_solution(sample_id: str, task: str, code: str, library_names=frozenset(), *, demo_pass: bool = True,
                   code_sha: str | None = None) -> Solution | None:
    """Solution record for one program (None when the code does not parse or has no transform)."""
    a = _analyze(code, library_names)
    if a is None or not a['has_transform']:
        return None
    helpers = tuple(_raw(n, a, sample_id, task) for n in sorted(a['reach']) if n in a['valid'])
    hh = {n: a['hashes'][n] for n in a['info'] if n != 'transform'}
    if isinstance(library_names, Mapping):
        for k, v in library_names.items():
            hh.setdefault(k, v)
    return Solution(sample_id=sample_id, task=task, code=code, code_sha=code_sha or sha256_text(code), helpers=helpers,
                    lib_calls=frozenset(a['lib_reach']), prog_hash=program_hash(code, hh) or sha256_text(code),
                    demo_pass=demo_pass)


def dedup_solutions(sols: Sequence[Solution]) -> list[Solution]:
    """One solution per (task, canonical program hash): the one with the smallest sample_id."""
    best: dict[tuple[str, str], Solution] = {}
    for s in sols:
        key = (s.task, s.prog_hash or s.code_sha)
        if key not in best or s.sample_id < best[key].sample_id:
            best[key] = s
    return sorted(best.values(), key=lambda s: (s.task, s.sample_id))


def mdl_gain(h: RawHelper, sols: Sequence[Solution], tok) -> int:
    k = sum(1 for s in dedup_solutions(sols) if any(x.hash == h.hash for x in s.helpers))
    return max(0, k - 1) * count_tokens(h.canonical, tok)


# ----------------------------------------------------------------------------------------------------------------------
# acceptance

def _check_growth(sols: Iterable[Solution]) -> None:
    for s in sols:
        phase = parse_sample_id(s.sample_id)['phase']
        if phase != 'growth':
            raise SealedHelperRefused(f'SEALED_HELPER_REFUSED sample_id={s.sample_id} phase={phase}')


def rename_source(source: str, mapping: Mapping[str, str]) -> str:
    """Rewrite the def name and global references per `mapping` (import prefix lines are kept)."""
    if not mapping or all(k == v for k, v in mapping.items()):
        return source
    mod = ast.parse(source)
    fn = _last_def(mod)
    globals_ = free_names_of(ast.unparse(ast.Module(body=[fn], type_ignores=[]))) | {fn.name}
    m = {k: v for k, v in mapping.items() if k in globals_ and k != v}
    if not m:
        return source
    _Renamer(m).visit(fn)
    return ast.unparse(ast.fix_missing_locations(mod)) + '\n'


def accept(round_sols: Sequence[Solution], prev, tok) -> list:
    """New library helpers from this round's demo-passing growth solutions (see module docstring)."""
    from ratchet.library import Helper   # local import: library imports helpers

    _check_growth(round_sols)
    sols = dedup_solutions([s for s in round_sols if s.demo_pass])
    prev_by_hash = {h.hash: h for h in prev.helpers}
    taken = {h.name for h in prev.helpers}
    defs: dict[str, list[tuple[Solution, RawHelper]]] = {}
    for s in sols:
        seen = set()
        for rh in s.helpers:
            if rh.hash in seen:
                continue
            seen.add(rh.hash)
            defs.setdefault(rh.hash, []).append((s, rh))
    min_tasks, min_mdl = int(cfg('ACCEPT_MIN_TASKS')), int(cfg('ACCEPT_MIN_MDL'))
    stats: dict[str, dict] = {}
    for hs, lst in defs.items():
        lst.sort(key=lambda p: p[0].sample_id)
        tasks = sorted({p[0].task for p in lst})
        rep_sol, rep = lst[0]
        gain = max(0, len(lst) - 1) * count_tokens(rep.canonical, tok)
        by2, bym = len(tasks) >= min_tasks, gain >= min_mdl
        stats[hs] = {'tasks': tasks, 'k': len(lst), 'gain': gain, 'rep': rep, 'rep_sol': rep_sol,
                     'by': 'both' if by2 and bym else ('two_tasks' if by2 else ('mdl' if bym else None))}
    acc = {hs for hs, st in stats.items() if st['by'] and hs not in prev_by_hash}
    # dependency closure (deps resolved inside the representative solution)
    queue = sorted(acc)
    dep_hash: dict[str, dict[str, str]] = {}
    while queue:
        hs = queue.pop()
        st = stats[hs]
        local = {rh.name: rh.hash for rh in st['rep_sol'].helpers}
        dep_hash[hs] = {}
        for d in st['rep'].deps:
            if d in local:
                dh = local[d]
                dep_hash[hs][d] = dh
                if dh not in prev_by_hash and dh not in acc:
                    acc.add(dh)
                    stats[dh]['by'] = stats[dh]['by'] or 'dep'
                    queue.append(dh)
    # unique names
    final: dict[str, str] = {}
    for hs in sorted(acc, key=lambda x: (stats[x]['rep'].name, x)):
        n = stats[hs]['rep'].name
        if n in taken:
            n = f'{n}_{hs[:6]}'
        taken.add(n)
        final[hs] = n
    out = []
    for hs in sorted(acc, key=lambda x: final[x]):
        st = stats[hs]
        rep: RawHelper = st['rep']
        mapping = {rep.name: final[hs]}
        deps_final = []
        for d in rep.deps:
            dh = dep_hash.get(hs, {}).get(d)
            if dh is None:                       # library dep, keeps its name
                deps_final.append(d)
                continue
            target = final.get(dh) or prev_by_hash[dh].name
            mapping[d] = target
            deps_final.append(target)
        source = rename_source(rep.source, mapping)
        sid = parse_sample_id(rep.sample_id)
        out.append(Helper(
            name=final[hs], hash=hs, source=source, canonical=rep.canonical,
            token_len=count_tokens(source, tok), deps=sorted(set(deps_final)), first_round=sid['round'],
            accepted_by=st['by'], calling_tasks=list(st['tasks']), n_calling_tasks=len(st['tasks']),
            n_solutions=st['k'], mdl_gain=st['gain'], rank=None, in_context=False, verified=True,
            provenance={'sample_ids': sorted(p[0].sample_id for p in defs[hs]), 'source_task': rep.task}))
    return out
