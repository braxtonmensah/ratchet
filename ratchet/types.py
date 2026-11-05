"""Shared data types for ratchet_v1 (SPEC 4.1, 4.5, 5 builder A). Owner: builder A.

Grid is an immutable tuple of tuples of ints so grids can be dict keys and vote keys (select.pass2). Every loader and the
sandbox normalize to this form; JSON rows carry lists (grid_to_json / grid_from_json).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

Grid = tuple[tuple[int, ...], ...]

# exec.jsonl status values (SPEC 4.5)
STATUS_OK = 'OK'
STATUS_NO_CODE = 'NO_CODE'
STATUS_SYNTAX = 'SYNTAX'
STATUS_DEMO_FAIL = 'DEMO_FAIL'
STATUS_TIMEOUT = 'TIMEOUT'
STATUS_ERROR = 'ERROR'
STATUS_BAD_OUTPUT = 'BAD_OUTPUT'
STATUSES = (STATUS_OK, STATUS_NO_CODE, STATUS_SYNTAX, STATUS_DEMO_FAIL, STATUS_TIMEOUT, STATUS_ERROR, STATUS_BAD_OUTPUT)

EXEC_MODES = ('callable', 'deleted', 'inline')


def grid_to_json(g: Grid) -> list[list[int]]:
    return [list(r) for r in g]


def grid_from_json(obj: Any) -> Grid:
    """Plain conversion (no domain check; arc_io.validate_grid does the check)."""
    return tuple(tuple(int(v) for v in r) for r in obj)


@dataclass(frozen=True)
class Pair:
    input: Grid
    output: Grid


@dataclass(frozen=True)
class Task:
    id: str
    split: str
    train: tuple[Pair, ...]
    test_inputs: tuple[Grid, ...]
    test_outputs: tuple[Grid, ...] | None    # not None only for split 'growth' and 'pilot'
    src_sha256: str                          # sha256 of the bytes this Task was loaded from

    @property
    def demo_inputs(self) -> list[Grid]:
        return [p.input for p in self.train]

    @property
    def demo_outputs(self) -> list[Grid]:
        return [p.output for p in self.train]


@dataclass(frozen=True)
class Candidate:
    """One sampled program as pass@2 sees it. test_outputs are the program's own outputs on the test inputs, never the key."""
    sample_id: str
    code_len: int
    demo_pass: bool
    test_outputs: tuple[Grid, ...] | None


@dataclass(frozen=True)
class Attempt:
    outputs: tuple[Grid, ...]
    votes: int
    min_len: int
    sample_ids: tuple[str, ...]


@dataclass(frozen=True)
class Submission:
    task: str
    attempts: tuple[Attempt, ...]
    n_candidates: int
    n_demo_pass: int

    def to_json(self) -> dict:
        return {'task': self.task, 'n_candidates': self.n_candidates, 'n_demo_pass': self.n_demo_pass,
                'attempts': [{'outputs': [grid_to_json(g) for g in a.outputs], 'votes': a.votes, 'min_len': a.min_len,
                              'sample_ids': list(a.sample_ids)} for a in self.attempts]}

    @classmethod
    def from_json(cls, d: dict) -> 'Submission':
        atts = tuple(Attempt(outputs=tuple(grid_from_json(g) for g in a['outputs']), votes=int(a['votes']),
                             min_len=int(a['min_len']), sample_ids=tuple(a['sample_ids'])) for a in d['attempts'])
        return cls(task=d['task'], attempts=atts, n_candidates=int(d['n_candidates']), n_demo_pass=int(d['n_demo_pass']))


@dataclass
class ExecResult:
    """One exec.jsonl row (SPEC 4.5). test_correct is set only for tasks whose public outputs are known (growth, pilot)."""
    sample_id: str
    code_sha: str
    status: str
    demo_pass: bool
    n_demo_pass: int
    n_demos: int
    first_fail_demo: int | None
    test_outputs: tuple[Grid, ...] | None
    helper_calls: dict[str, int] = field(default_factory=dict)
    static_refs: tuple[str, ...] = ()
    wall_s: tuple[float, ...] = ()
    timeouts: int = 0
    exec_mode: str = 'callable'
    cache_hit: bool = False
    test_correct: bool | None = None
    error: str | None = None                 # short reason, e.g. 'BAD_OUTPUT:colour', 'IMPORT_REFUSED:re', exception class
    helpers_callable: int = 0                # library functions defined in the child namespace before the program ran

    def to_row(self) -> dict:
        row: dict[str, Any] = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if f.name == 'test_outputs':
                v = None if v is None else [grid_to_json(g) for g in v]
            elif f.name in ('static_refs', 'wall_s'):
                v = list(v)
            elif f.name == 'helper_calls':
                v = dict(sorted(v.items()))
            if f.name == 'test_correct' and v is None:
                continue
            row[f.name] = v
        return row

    @classmethod
    def from_row(cls, row: dict) -> 'ExecResult':
        kw = {f.name: row[f.name] for f in fields(cls) if f.name in row}
        if kw.get('test_outputs') is not None:
            kw['test_outputs'] = tuple(grid_from_json(g) for g in kw['test_outputs'])
        kw['static_refs'] = tuple(kw.get('static_refs', ()))
        kw['wall_s'] = tuple(float(x) for x in kw.get('wall_s', ()))
        kw['helper_calls'] = {str(k): int(v) for k, v in (kw.get('helper_calls') or {}).items()}
        return cls(**kw)
