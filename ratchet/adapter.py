"""Type adapter, parent side (harness v2; PLANT_FAIL_DIAGNOSIS 4.1 to 4.3). Static analysis only: nothing here executes
library code. The adapter itself runs in sandbox_child.py (which never imports this package and carries its own copy of
the rule; tests/test_v2_adapter.py checks the two agree).

Rule (read only from a helper's own annotations, string literals as plant.py renders them):
- an argument at a parameter annotated Grid, Element or Piece (positional or keyword) that is a non-empty list whose items
  are lists or tuples goes in as a tuple of tuples;
- a non-empty tuple-of-tuples result of a function whose return annotation is Grid, Element or Piece comes back as a list
  of lists;
- everything else, and every helper with no such annotation, is identity (the same function object).

Also here: the type legend (F2), the list of grid-typed helpers for the lever check, and the lever-check program
(F3 of the diagnosis): for each helper whose first positional parameter is grid-typed, the program calls it through the
adapter on a list-of-lists demo grid and on the same grid as a tuple of tuples, with defaults for the other parameters,
and encodes per helper one code in a returned grid (it runs through the normal sandbox path as a test input).
"""
from __future__ import annotations

import ast
from typing import Sequence

from . import config

GRID_TYPES = frozenset(config.ADAPTER_GRID_TYPES)
LEGEND = tuple(config.TYPE_LEGEND)
_LEGEND_NAMES = frozenset(n for n, _ in LEGEND)

# Lever-check result codes (one per grid-typed helper, in order; 0 pads the returned grid)
SMOKE_BOTH_OK = 1
SMOKE_LIST_RAISES = 2        # raises on the list grid where the tuple call does not: refuse
SMOKE_BOTH_RAISE = 3         # the default arguments do not fit this helper; not the adapter's fault
SMOKE_TUPLE_RAISES = 4       # list call fine, tuple call raises
SMOKE_RESULTS_DIFFER = 5     # both run but return different values: refuse (a silent wrong answer)
SMOKE_REFUSE = frozenset({SMOKE_LIST_RAISES, SMOKE_RESULTS_DIFFER})
SMOKE_WIDTH = 30

# default argument kinds for the lever check (PLANT_FAIL_DIAGNOSIS 4.3: True for Boolean, a cell colour for Integer, a
# 1-cell frozenset for Patch; the other arc-dsl aliases get the analogous one-element value)
_KIND = {'Grid': 'G', 'Element': 'G', 'Piece': 'G', 'Boolean': 'B', 'Integer': 'I', 'Numerical': 'I',
         'IntegerTuple': 'T', 'Patch': 'P', 'Indices': 'P', 'Object': 'O', 'Objects': 'S', 'IndicesSet': 'Q',
         'IntegerSet': 'Z', 'Callable': 'F', 'Container': 'P', 'FrozenSet': 'P', 'Tuple': 'T', 'Any': 'I',
         'Cell': 'C', 'TupleTuple': 'G', 'ContainerContainer': 'Q'}


_QUOTES = '\'"'


def _ann_str(node, future: bool = False) -> str | None:
    """The annotation as the child sees it at run time, when that is a string: a string literal always; any other
    expression only under `from __future__ import annotations` (then every annotation is its source text). Quotes are
    stripped the same way sandbox_child._is_grid_ann strips them."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.strip().strip(_QUOTES).strip()
    if future:
        return ast.unparse(node).strip().strip(_QUOTES).strip()
    return None


def _parse(src: str):
    try:
        mod = ast.parse(src or '')
    except (SyntaxError, ValueError):
        return [], False
    future = any(isinstance(n, ast.ImportFrom) and n.module == '__future__' and
                 any(a.name == 'annotations' for a in n.names) for n in mod.body)
    return [n for n in mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))], future


def _top_defs(src: str) -> list[ast.FunctionDef]:
    return _parse(src)[0]


def signature(fn: ast.FunctionDef, future: bool = False) -> dict:
    """{'pos': [(name, annotation or None)], 'kw': [...], 'ret': annotation or None} (string annotations only)."""
    a = fn.args
    return {'pos': [(x.arg, _ann_str(x.annotation, future)) for x in a.posonlyargs + a.args],
            'kw': [(x.arg, _ann_str(x.annotation, future)) for x in a.kwonlyargs],
            'ret': _ann_str(fn.returns, future), 'n_defaults': len(a.defaults), 'vararg': a.vararg is not None}


def signatures(src: str) -> dict[str, dict]:
    defs, future = _parse(src)
    return {f.name: signature(f, future) for f in defs}


def adapted(sig: dict) -> bool:
    """True iff the child wraps this helper (some parameter or the return is grid-typed)."""
    return (any(t in GRID_TYPES for _, t in sig['pos'] + sig['kw']) or sig['ret'] in GRID_TYPES)


def grid_first(sig: dict) -> bool:
    return bool(sig['pos']) and sig['pos'][0][1] in GRID_TYPES


def grid_helpers(src: str) -> list[str]:
    """Library functions whose first positional parameter is grid-typed (the lever-check set), in source order."""
    return [n for n, s in signatures(src).items() if grid_first(s)]


def annotation_names(src: str) -> set[str]:
    """Every Name inside every string annotation of every top-level def (e.g. 'Tuple[Grid, Grid]' -> Tuple, Grid)."""
    out: set[str] = set()
    for f in _top_defs(src):
        a = f.args
        anns = [x.annotation for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg] if x is not None]
        anns.append(f.returns)
        for node in anns:
            s = _ann_str(node)
            if not s:
                continue
            try:
                expr = ast.parse(s, mode='eval')
            except SyntaxError:
                continue
            out.update(n.id for n in ast.walk(expr) if isinstance(n, ast.Name))
    return out


def legend(sources: Sequence[str]) -> str:
    """Comment block naming only the arc-dsl aliases that appear in the given helpers' annotations ('' if none)."""
    names: set[str] = set()
    for s in sources:
        names |= annotation_names(str(s))
    names &= _LEGEND_NAMES
    if not names:
        return ''
    return '\n'.join('# %s: %s' % (n, t) for n, t in LEGEND if n in names)


# ---------------------------------------------------------------------------------------------------------------------
# lever-check program

def _arg_expr(kind: str, grid_var: str) -> str:
    return {'G': '_rt_mk(%s)' % grid_var, 'B': 'True', 'I': '_rt_c', 'T': '(0, 0)', 'P': 'frozenset({(0, 0)})',
            'O': 'frozenset({(_rt_c, (0, 0))})', 'S': 'frozenset({frozenset({(_rt_c, (0, 0))})})',
            'Q': 'frozenset({frozenset({(0, 0)})})', 'Z': 'frozenset({_rt_c})', 'F': '(lambda x: x)',
            'C': '(_rt_c, (0, 0))'}.get(kind, 'None')


def smoke_program(src: str) -> tuple[str, list[str]]:
    """(program source, helper names checked). The program's transform(grid) returns the codes as a grid."""
    sigs = signatures(src)
    names = [n for n, s in sigs.items() if grid_first(s)]
    if len(names) > SMOKE_WIDTH * config.GRID_MAX_SIDE:
        raise ValueError('too many grid-typed helpers for one smoke grid: %d' % len(names))
    lines = ['def transform(grid):',
             '    _rt_c = grid[0][0]',
             '    def _rt_mk(g):',
             '        return [list(r) for r in g] if isinstance(g, list) else tuple(tuple(r) for r in g)',
             '    _rt_tg = tuple(tuple(r) for r in grid)',
             '    _rt_codes = []']
    for n in names:
        s = sigs[n]
        req = s['pos'][: len(s['pos']) - s['n_defaults']] if s['n_defaults'] else s['pos']
        kinds = [_KIND.get(t or '', 'X') for _, t in req]
        kw_req = [(k, _KIND.get(t or '', 'X')) for k, t in s['kw']]
        for j, gv in enumerate(('grid', '_rt_tg')):
            args = ', '.join([_arg_expr(k, gv) for k in kinds] + ['%s=%s' % (k, _arg_expr(kd, gv)) for k, kd in kw_req])
            lines += ['    try:', '        _rt_r%d = %s(%s)' % (j, n, args), '        _rt_e%d = False' % j,
                      '    except Exception:', '        _rt_r%d = None' % j, '        _rt_e%d = True' % j]
        lines += ['    if _rt_e0 and not _rt_e1:', '        _rt_codes.append(%d)' % SMOKE_LIST_RAISES,
                  '    elif _rt_e0 and _rt_e1:', '        _rt_codes.append(%d)' % SMOKE_BOTH_RAISE,
                  '    elif _rt_e1:', '        _rt_codes.append(%d)' % SMOKE_TUPLE_RAISES,
                  '    else:', '        try:', '            _rt_same = _rt_r0 == _rt_r1', '        except Exception:',
                  '            _rt_same = False',
                  '        _rt_codes.append(%d if _rt_same else %d)' % (SMOKE_BOTH_OK, SMOKE_RESULTS_DIFFER)]
    lines += ['    _rt_codes = _rt_codes or [0]',
              '    _rt_rows = [_rt_codes[i:i + %d] for i in range(0, len(_rt_codes), %d)]' % (SMOKE_WIDTH, SMOKE_WIDTH),
              '    return [r + [0] * (%d - len(r)) for r in _rt_rows]' % SMOKE_WIDTH]
    return '\n'.join(lines) + '\n', names


def decode_smoke(names: Sequence[str], out_grid) -> dict[str, int]:
    flat = [int(v) for row in (out_grid or ()) for v in row]
    return {n: (flat[i] if i < len(flat) else 0) for i, n in enumerate(names)}


def lever_line(n_grid: int, n_list_ok: int, **extra) -> str:
    tail = ''.join(' %s=%s' % (k, v) for k, v in extra.items())
    return 'LEVER ADAPTER grid_helpers=%d list_smoke_ok=%d%s' % (n_grid, n_list_ok, tail)
