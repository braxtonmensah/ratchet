"""pass@2 selection without test outputs (PREREG 5; SPEC 5 builder A, 13 I9). Owner: builder A.

Only demo-passing candidates that produced an output for every test input vote. The vote key is the joint tuple of test
outputs (a multi-test task is one key). Order: votes desc, then the shortest code_len among the programs giving that
tuple, then repr of the tuple (deterministic). Up to k distinct tuples are submitted.

No parameter of pass2 can carry a test output from the key: Candidate holds only a program's own sampled outputs.
"""
from __future__ import annotations

from typing import Sequence

from .types import Attempt, Candidate, ExecResult, Submission

try:
    from . import config as _config
except ImportError:  # pragma: no cover
    _config = None

PASS_AT = int(getattr(_config, 'PASS_AT', 2)) if _config is not None else 2


def candidate_from_exec(r: ExecResult, code_len: int) -> Candidate:
    """code_len = characters of the extracted code (SPEC 13 I9)."""
    return Candidate(sample_id=r.sample_id, code_len=int(code_len), demo_pass=bool(r.demo_pass),
                     test_outputs=r.test_outputs if r.demo_pass else None)


def pass2(task_id: str, candidates: Sequence[Candidate], k: int = PASS_AT) -> Submission:
    groups: dict[tuple, list[Candidate]] = {}
    n_demo_pass = 0
    for c in candidates:
        if not c.demo_pass:
            continue
        n_demo_pass += 1
        if c.test_outputs is None or len(c.test_outputs) == 0:
            continue
        groups.setdefault(tuple(c.test_outputs), []).append(c)
    ranked = []
    for key, cs in groups.items():
        ranked.append((-len(cs), min(c.code_len for c in cs), repr(key), key, cs))
    ranked.sort(key=lambda x: (x[0], x[1], x[2]))
    attempts = []
    for negv, min_len, _r, key, cs in ranked[:k]:
        ids = tuple(c.sample_id for c in sorted(cs, key=lambda c: (c.code_len, c.sample_id)))
        attempts.append(Attempt(outputs=key, votes=-negv, min_len=min_len, sample_ids=ids))
    return Submission(task=task_id, attempts=tuple(attempts), n_candidates=len(candidates), n_demo_pass=n_demo_pass)
