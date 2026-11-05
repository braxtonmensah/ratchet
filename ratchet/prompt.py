"""Prompt builder (SPEC 5 builder B; PREREG 4 library cap). Owner: builder B.

Message order: system, then one user message = [library block or exemplar block] + task block + instruction. The
block comes first so the vLLM prefix cache shares it across the tasks of a round (SPEC 1.6 item 4). With no library
helpers in context and no exemplars, the user message is exactly task block + instruction, so round 1 of STOCK, STATIC
and EXEMPLAR (all empty context) builds byte-identical messages (SPEC 13 I3).

Library block (PREREG 4: cap 6,000 tokens, helpers ranked by distinct calling tasks, then length; SPEC 13 I8):
greedy over library.rank(lib); a helper goes in only with its whole dependency closure; a candidate that would cross
the cap is skipped and the loop continues (smaller helpers may still fit). A helper whose closure names a helper that
is missing from the library or is in `drop` is skipped (it could not run). The cap is checked on the exact token count
of the rendered block (header and fences included). A cheap additive estimate first rejects candidates that exceed
the cap by more than a margin; the exact count then decides.

The task block never reads Task.test_outputs (PREREG 5: test outputs are never shown or used).

Harness v2 (PLANT_FAIL_DIAGNOSIS 4.2; AMENDMENT 2 F3 with VERDICT_AMENDMENT_2):
- build_messages takes `instruction` (default: config.INSTRUCTION, the v1 text, so callers that pass nothing, selfft
  included, get v1 bytes). The Ratchet driver passes the run's recorded instruction (arms.run_instruction).
- A library or exemplar note goes immediately BEFORE the instruction's tail (config.INSTRUCTION_TAILS: v1's
  "Return one ..." sentence; for F3 the whole appended F3 text), so the last thing the model reads is the instruction's
  own last sentence. A FLAT prompt (no block) carries the instruction verbatim.
- The callable header carries the grid-contract sentence, and a rule-generated type legend (adapter.legend: only the
  arc-dsl aliases named by the rendered helpers' annotations) opens the library code block. Both are inside the block
  whose exact token count is held to the 6,000 cap. Unannotated (grown) libraries get an empty legend; the inline
  (non-callable reference) block gets none, because inline text is copied by the model, not adapted.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Sequence

try:   # builder D owns config.py
    from ratchet import config as _config
except ImportError:   # pragma: no cover
    _config = None

_DEFAULTS = {
    'LIBRARY_CAP_TOKENS': 6000,
    'SYSTEM_PROMPT': ('You solve ARC puzzles by writing Python. Each puzzle shows input and output grids of digits 0 to '
                      '9. Find the rule that maps every input to its output and write it as a function.'),
    'INSTRUCTION': ('Write a Python function `def transform(grid):` that takes the input grid as a list of lists of '
                    'ints and returns the output grid as a list of lists of ints (values 0 to 9, at most 30 by 30). It '
                    'must produce the correct output for every example above and for the test input. You may import '
                    'math, itertools, collections, functools, copy, typing and numpy. Return one ```python fenced '
                    'block containing the complete program.'),
    'LIB_HEADER_CALLABLE': ('These functions are already defined; call them directly. Pass grids exactly as transform '
                            'receives them; these functions accept and return grids as lists of lists of ints.'),
    'LIB_HEADER_INLINE': 'Reference code. These functions are NOT defined in your environment; copy any code you need.',
    'LIB_NOTE_CALLABLE': 'The library functions above are already defined in your environment; you may call them.',
    'LIB_NOTE_INLINE': 'The reference code above is not defined in your environment; copy any part you use.',
    'EXEMPLAR_HEADER': 'Verified programs that solve other, similar puzzles (each passes every example of its own puzzle):',
    'EXEMPLAR_NOTE': 'The programs above solve other puzzles; they are shown for reference only.',
    'PROMPT_EST_MARGIN_PER_PIECE': 2,   # additive-estimate slack per helper before the exact count is skipped
    'PROMPT_EST_MARGIN_BASE': 4,
}


def _cfg(name: str):
    if _config is not None and hasattr(_config, name):
        return getattr(_config, name)
    return _DEFAULTS[name]


SYSTEM: str = _cfg('SYSTEM_PROMPT')
INSTRUCTION: str = _cfg('INSTRUCTION')
CALLABLE_HEADER: str = _cfg('LIB_HEADER_CALLABLE')
INLINE_HEADER: str = _cfg('LIB_HEADER_INLINE')
FENCE_OPEN = '```python\n'
FENCE_CLOSE = '\n```'


@dataclass
class PromptBuild:
    messages: list[dict]
    library_tokens: int
    exemplar_tokens: int
    task_tokens: int
    instruction_tokens: int          # system text + instruction text (+ the library or exemplar note)
    helpers_in_context: tuple[str, ...]
    lib_sha: str | None
    exemplar_ids: tuple[str, ...]
    block_kind: str = 'none'         # none | callable | inline | exemplar | callable+inline
    exemplar_tasks: tuple[str, ...] = field(default_factory=tuple)
    helpers_inline: tuple[str, ...] = field(default_factory=tuple)   # knockout inline: shown as non-callable text

    def ledger_meta(self) -> dict:
        """The prompt fields of a ledger row (SPEC 4.4); D adds run, job, arm, phase, round, seed, task, model_sha."""
        return {'library_tokens': self.library_tokens, 'exemplar_tokens': self.exemplar_tokens,
                'task_tokens': self.task_tokens, 'instruction_tokens': self.instruction_tokens, 'lib_sha': self.lib_sha}


# ---------------------------------------------------------------------------------------------------------------------
# helpers for C's Library / Helper (attribute access with a dict fallback)

def _g(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _rank(lib) -> list:
    try:
        from ratchet.library import rank as _lib_rank   # builder C
    except ImportError:   # pragma: no cover
        _lib_rank = None
    if _lib_rank is not None and not isinstance(lib, dict):
        return list(_lib_rank(lib))
    hs = list(_g(lib, 'helpers', []) or [])
    return sorted(hs, key=lambda h: (-int(_g(h, 'n_calling_tasks', 0) or 0), int(_g(h, 'token_len', 0) or 0),
                                     str(_g(h, 'name'))))


def _lib_sha(lib) -> str | None:
    if lib is None:
        return None
    try:
        from ratchet.library import sha as _sha   # builder C
        return _sha(lib)
    except (ImportError, AttributeError, TypeError, KeyError):
        v = _g(lib, 'sha256')
        return v if isinstance(v, str) else None


def _render_grid(g) -> str:
    try:
        from ratchet.arc_io import render_grid   # builder A
    except ImportError:   # pragma: no cover
        render_grid = None
    if render_grid is not None:
        return render_grid(g)
    return '\n'.join(''.join(str(int(v)) for v in row) for row in g)


# ---------------------------------------------------------------------------------------------------------------------
# blocks

def task_block(task) -> str:
    """Demos as 'Example k\\nInput:\\n<grid>\\nOutput:\\n<grid>', then the test inputs. Never reads test_outputs."""
    parts = []
    for i, p in enumerate(task.train, start=1):
        parts.append(f'Example {i}\nInput:\n{_render_grid(p.input)}\nOutput:\n{_render_grid(p.output)}')
    tests = list(task.test_inputs)
    for j, g in enumerate(tests, start=1):
        label = 'Test input:' if len(tests) == 1 else f'Test input {j}:'
        parts.append(f'{label}\n{_render_grid(g)}')
    return '\n\n'.join(parts)


def _render_library(header: str, sources: Sequence[str], legend: bool = False) -> str:
    """header, then one python fence: [type legend,] the helper sources. legend=True only for the callable block."""
    body = [s.strip('\n') for s in sources]
    if legend:
        from ratchet.adapter import legend as _legend
        lg = _legend(body)
        if lg:
            body = [lg] + body
    return header + '\n' + FENCE_OPEN + '\n\n'.join(body) + FENCE_CLOSE


def _tails() -> tuple[str, ...]:
    t = getattr(_config, 'INSTRUCTION_TAILS', {}) if _config is not None else {}
    return tuple(sorted(set(t.values()), key=len, reverse=True))


def with_notes(instruction: str, notes: Sequence[str]) -> str:
    """The instruction with the notes placed immediately before its tail (its closing sentence or sentences). An
    instruction with no known tail gets the notes appended at the end (the v1 rule)."""
    notes = [str(n) for n in notes if n]
    if not notes:
        return instruction
    for tail in _tails():
        if tail and instruction.endswith(tail) and len(instruction) > len(tail):
            head = instruction[: len(instruction) - len(tail)].rstrip(' ')
            return ' '.join([head] + notes + [tail])
    return ' '.join([instruction] + notes)


def _ordered(names: Sequence[str], by: dict, order: dict) -> list[str]:
    """Deps before dependents; roots and deps visited in rank order (same rule as library.dep_closure)."""
    out: list[str] = []
    seen: set[str] = set()

    def visit(n: str, stack: frozenset) -> None:
        if n in seen or n in stack or n not in by:
            return
        for d in sorted(_g(by[n], 'deps', ()) or (), key=lambda x: (order.get(x, 1 << 30), x)):
            visit(d, stack | {n})
        seen.add(n)
        out.append(n)

    for n in sorted(names, key=lambda x: (order.get(x, 1 << 30), x)):
        visit(n, frozenset())
    return out


def _closure(name: str, by: dict, drop: frozenset) -> list[str] | None:
    """Every name `name` needs (itself included), or None if one is missing from the library or dropped."""
    need: list[str] = []
    seen: set[str] = set()
    stack = [name]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        if n not in by or n in drop:
            return None
        seen.add(n)
        need.append(n)
        stack.extend(sorted(_g(by[n], 'deps', ()) or ()))
    return need


_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 4096


def library_block(lib, cap_tokens: int, tok, inline_noncallable: bool = False,
                  drop: frozenset = frozenset()) -> tuple[str, tuple[str, ...], int]:
    """(block text, helper names in render order, exact block tokens). Empty library or nothing fits: ('', (), 0)."""
    if lib is None:
        return '', (), 0
    helpers = list(_g(lib, 'helpers', []) or [])
    if not helpers:
        return '', (), 0
    drop = frozenset(drop)
    sha = _lib_sha(lib)
    key = None
    if sha is not None:
        key = (sha, int(cap_tokens), bool(inline_noncallable), tuple(sorted(drop)), str(getattr(tok, 'sha', id(tok))))
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
        if hit is not None:
            return hit
    ranked = _rank(lib)
    by: dict = {}
    for h in ranked:                      # a duplicate name keeps its best-ranked helper
        by.setdefault(str(_g(h, 'name')), h)
    order = {n: i for i, n in enumerate(by)}
    header = INLINE_HEADER if inline_noncallable else CALLABLE_HEADER
    legend = not inline_noncallable
    piece: dict[str, int] = {}

    def piece_tokens(n: str) -> int:
        if n not in piece:
            piece[n] = tok.count(str(_g(by[n], 'source', '')).strip('\n'))
        return piece[n]

    chosen: list[str] = []
    chosen_set: set[str] = set()
    cur = tok.count(_render_library(header, []))   # header and fences alone
    m_piece = int(_cfg('PROMPT_EST_MARGIN_PER_PIECE'))
    m_base = int(_cfg('PROMPT_EST_MARGIN_BASE'))
    skipped_unrunnable = 0
    for h in ranked:
        name = str(_g(h, 'name'))
        if name in chosen_set or by.get(name) is not h or name in drop:
            continue
        cl = _closure(name, by, drop)
        if cl is None:
            skipped_unrunnable += 1
            continue
        new = [n for n in cl if n not in chosen_set]
        est = cur + sum(piece_tokens(n) for n in new)
        if est > cap_tokens + m_base + m_piece * len(new):
            continue
        trial = _ordered(chosen + new, by, order)
        c = tok.count(_render_library(header, [str(_g(by[n], 'source', '')) for n in trial], legend))
        if c <= cap_tokens:
            chosen = trial
            chosen_set.update(new)
            cur = c
    if not chosen:
        res = ('', (), 0)
    else:
        text = _render_library(header, [str(_g(by[n], 'source', '')) for n in chosen], legend)
        res = (text, tuple(chosen), tok.count(text))
    if key is not None:
        with _CACHE_LOCK:
            if len(_CACHE) >= _CACHE_MAX:
                _CACHE.clear()
            _CACHE[key] = res
    return res


def inline_text_block(lib, tok) -> tuple[str, tuple[str, ...], int]:
    """Every helper of `lib` under the NON-callable header, in rank order with dependencies first; no cap and no
    closure rule (the text is reference only; it is never executed). Used for the knockout inline mode: these are the
    knocked-out helpers, and the callable block beside it holds the rest (PREREG 6.3b)."""
    helpers = list(_g(lib, 'helpers', []) or []) if lib is not None else []
    if not helpers:
        return '', (), 0
    by: dict = {}
    for h in _rank(lib):
        by.setdefault(str(_g(h, 'name')), h)
    order = {n: i for i, n in enumerate(by)}
    names = _ordered(list(by), by, order)
    text = _render_library(INLINE_HEADER, [str(_g(by[n], 'source', '')) for n in names])
    return text, tuple(names), tok.count(text)


def _exemplar_piece(code: str) -> str:
    return FENCE_OPEN + code.strip('\n') + FENCE_CLOSE


def exemplar_block(exemplars: Sequence, cap_tokens: int, tok) -> tuple[str, tuple[str, ...], int]:
    """Greedy in the given (nearest-first) order: an exemplar goes in whole if the block stays under the cap.
    Returns (text, sample ids included, exact tokens)."""
    header = str(_cfg('EXEMPLAR_HEADER'))
    chosen: list = []
    cur = 0
    for ex in exemplars or ():
        trial = chosen + [ex]
        text = header + '\n\n' + '\n\n'.join(_exemplar_piece(str(_g(e, 'code', ''))) for e in trial)
        c = tok.count(text)
        if c <= cap_tokens:
            chosen = trial
            cur = c
    if not chosen:
        return '', (), 0
    text = header + '\n\n' + '\n\n'.join(_exemplar_piece(str(_g(e, 'code', ''))) for e in chosen)
    return text, tuple(str(_g(e, 'sample_id', '')) for e in chosen), tok.count(text)


def build_messages(task, tok, *, library=None, exemplars: Sequence | None = None, inline_noncallable: bool = False,
                   drop: frozenset = frozenset(), cap_tokens: int | None = None, inline_library=None,
                   instruction: str | None = None) -> PromptBuild:
    if library is not None and exemplars:
        raise ValueError('a prompt carries a library block or an exemplar block, not both')
    base = INSTRUCTION if instruction is None else str(instruction)
    if inline_library is not None:
        return _build_knockout_inline(task, tok, library, inline_library, cap_tokens, base)
    cap = int(_cfg('LIBRARY_CAP_TOKENS') if cap_tokens is None else cap_tokens)
    block, names, lib_tokens = ('', (), 0)
    ex_block, ex_ids, ex_tokens = ('', (), 0)
    ex_tasks: tuple[str, ...] = ()
    kind = 'none'
    instr = base
    if library is not None:
        block, names, lib_tokens = library_block(library, cap, tok, inline_noncallable=inline_noncallable, drop=drop)
        if block:
            kind = 'inline' if inline_noncallable else 'callable'
            instr = with_notes(base, [str(_cfg('LIB_NOTE_INLINE' if inline_noncallable else 'LIB_NOTE_CALLABLE'))])
    elif exemplars:
        own = getattr(task, 'id', None)
        if any(str(_g(e, 'task', '')) == own for e in exemplars):
            raise ValueError(f'exemplar of task {own} shown to itself (SPEC 13 I17)')
        ex_block, ex_ids, ex_tokens = exemplar_block(exemplars, cap, tok)
        if ex_block:
            kind = 'exemplar'
            instr = with_notes(base, [str(_cfg('EXEMPLAR_NOTE'))])
            idset = set(ex_ids)
            ex_tasks = tuple(str(_g(e, 'task', '')) for e in exemplars if str(_g(e, 'sample_id', '')) in idset)
    tb = task_block(task)
    user = '\n\n'.join(x for x in (block or ex_block, tb, instr) if x)
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]
    return PromptBuild(messages=messages, library_tokens=lib_tokens, exemplar_tokens=ex_tokens,
                       task_tokens=tok.count(tb), instruction_tokens=tok.count(SYSTEM) + tok.count(instr),
                       helpers_in_context=tuple(names), lib_sha=_lib_sha(library) if library is not None else None,
                       exemplar_ids=tuple(ex_ids), block_kind=kind, exemplar_tasks=ex_tasks)


def _build_knockout_inline(task, tok, library, inline_library, cap_tokens, base: str | None = None) -> PromptBuild:
    """Knockout inline prompt: [callable block of `library`] + [non-callable text block of `inline_library`] + task +
    instruction with both notes. library_tokens counts both blocks; helpers_in_context lists only the callable ones."""
    cap = int(_cfg('LIBRARY_CAP_TOKENS') if cap_tokens is None else cap_tokens)
    block, names, lib_tokens = ('', (), 0)
    if library is not None:
        block, names, lib_tokens = library_block(library, cap, tok)
    tblock, tnames, t_tokens = inline_text_block(inline_library, tok)
    notes = []
    if block:
        notes.append(str(_cfg('LIB_NOTE_CALLABLE')))
    if tblock:
        notes.append(str(_cfg('LIB_NOTE_INLINE')))
    instr = with_notes(INSTRUCTION if base is None else base, notes)
    tb = task_block(task)
    user = '\n\n'.join(x for x in (block, tblock, tb, instr) if x)
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]
    kind = '+'.join(k for k, b in (('callable', block), ('inline', tblock)) if b) or 'none'
    return PromptBuild(messages=messages, library_tokens=lib_tokens + t_tokens, exemplar_tokens=0,
                       task_tokens=tok.count(tb), instruction_tokens=tok.count(SYSTEM) + tok.count(instr),
                       helpers_in_context=tuple(names), lib_sha=_lib_sha(library) if library is not None else None,
                       exemplar_ids=(), block_kind=kind, helpers_inline=tuple(tnames))
