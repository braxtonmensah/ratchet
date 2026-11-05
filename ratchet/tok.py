"""Tokenizer wrapper (SPEC 5 builder B). Owner: builder B.

`load_tokenizer` wraps `tokenizers.Tokenizer.from_file(<model_dir>/tokenizer.json)` (the Rust tokenizer, no
transformers import). `StubTokenizer` is the deterministic rule tests use: one token per word run or per other
non-space character. Both expose `count(text) -> int` and `sha` (sha256 of tokenizer.json, or 'stub'), which
library JSON records as `tokenizer_sha` (SPEC 4.3).

Counts here are raw text counts with no special tokens; chat-template overhead is not in any block count, so a
ledger row's exact vLLM `prompt_tokens` minus the block split is the template overhead (SPEC 10 map).
"""
from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

_STUB_RE = re.compile(r'\w+|\S')


@runtime_checkable
class Tok(Protocol):
    def count(self, text: str) -> int: ...


class StubTokenizer:
    """len(re.findall(r'\\w+|\\S', text)); deterministic, no files, for tests (SPEC 5)."""

    sha = 'stub'
    name = 'stub'

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(_STUB_RE.findall(text))


class HFTokenizer:
    """`tokenizers.Tokenizer` from a model dir; count = len(ids) with add_special_tokens=False."""

    def __init__(self, path: Path):
        import tokenizers   # in the vLLM venv and the sas venv; import here so StubTokenizer needs nothing

        self.path = Path(path)
        with open(self.path, 'rb') as f:   # model dir file, not a data path (SPEC 8 static test 8 covers data paths)
            raw = f.read()
        self.sha = hashlib.sha256(raw).hexdigest()
        self.name = str(self.path)
        self._tk = tokenizers.Tokenizer.from_str(raw.decode('utf-8'))
        self._lock = threading.Lock()      # the Rust tokenizer is thread safe for encode; the lock guards the cache
        self._cache: dict[str, int] = {}
        self._cache_max = 200_000
        self._cache_text_max = 4096

    def count(self, text: str) -> int:
        if not text:
            return 0
        with self._lock:
            hit = self._cache.get(text)
        if hit is not None:
            return hit
        n = len(self._tk.encode(text, add_special_tokens=False).ids)
        if len(text) > self._cache_text_max:   # whole prompt blocks are not cached (memory)
            return n
        with self._lock:
            if len(self._cache) >= self._cache_max:
                self._cache.clear()
            self._cache[text] = n
        return n

    def encode_ids(self, text: str) -> list[int]:
        return list(self._tk.encode(text, add_special_tokens=False).ids) if text else []


def load_tokenizer(model_dir: Path) -> Tok:
    """HFTokenizer over <model_dir>/tokenizer.json. Raises FileNotFoundError or ImportError (callers in tests fall
    back to StubTokenizer; the driver must not)."""
    p = Path(model_dir) / 'tokenizer.json'
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return HFTokenizer(p)


def tokenizer_sha(tok: Tok) -> str:
    return str(getattr(tok, 'sha', None) or type(tok).__name__)
