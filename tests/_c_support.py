"""Shared fixtures for builder C tests (stub tokenizer, tiny tasks, solution builders). CPU only, no model."""
from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from ratchet.tok import StubTokenizer  # builder B
except Exception:  # pragma: no cover - before builder B lands
    class StubTokenizer:
        def count(self, text: str) -> int:
            return len(re.findall(r'\w+|\S', text))

try:
    from ratchet.types import Pair, Task  # builder A
except Exception:  # pragma: no cover - before builder A lands
    @dataclass(frozen=True)
    class Pair:
        input: tuple
        output: tuple

    @dataclass(frozen=True)
    class Task:
        id: str
        split: str
        train: tuple
        test_inputs: tuple
        test_outputs: tuple | None
        src_sha256: str


class FixedTok:
    """Every text counts as `n` tokens (pins the MDL threshold exactly)."""

    def __init__(self, n: int):
        self.n = n

    def count(self, text: str) -> int:
        return self.n


def grid(rows):
    return tuple(tuple(r) for r in rows)


def make_task(tid: str, pairs, split: str = 'growth') -> Task:
    train = tuple(Pair(grid(i), grid(o)) for i, o in pairs)
    return Task(id=tid, split=split, train=train, test_inputs=(grid(pairs[0][0]),), test_outputs=None,
                src_sha256='0' * 64)


def sid(task: str, slot: int = 0, rnd: int = 1, arm: str = 'STOCK', phase: str = 'growth') -> str:
    return f'{arm}|{phase}|r{rnd}|{task}|s{slot}'
