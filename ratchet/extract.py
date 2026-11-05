"""Code extraction from model responses (SPEC 5, builder C).

Rule: strip any <think>...</think> first; take the last fenced python block that defines a top-level `transform`;
else the whole text if it compiles and defines `transform`; else None.

Resolved details (reported to the lead):
- Fences tagged python, py, python3 or untagged all count as python blocks; a fence left open at the end of the text
  (a sample cut by max_tokens) counts as a block running to the end.
- A block "defines transform" if it parses and has a top-level `def transform`. If no block parses that way, the last
  block whose text has a `def transform(` line is returned anyway, so the sandbox records SYNTAX rather than NO_CODE.
- A response with an unclosed <think> keeps only the text after the last </think> if there is one, else drops
  everything from the opening <think>.
"""
from __future__ import annotations

import ast
import re

_THINK_BLOCK = re.compile(r'<think>.*?</think>', re.S)
_FENCE = re.compile(r'```[ \t]*(python3|python|py)?[ \t]*\r?\n(.*?)(?:```|\Z)', re.S | re.I)
_DEF_TRANSFORM = re.compile(r'^def[ \t]+transform[ \t]*\(', re.M)


def strip_think(text: str) -> str:
    text = _THINK_BLOCK.sub('', text)
    if '</think>' in text:
        text = text.rsplit('</think>', 1)[1]
    if '<think>' in text:
        text = text.split('<think>', 1)[0]
    return text


def defines_transform(code: str) -> bool:
    try:
        mod = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False
    return any(isinstance(n, ast.FunctionDef) and n.name == 'transform' for n in mod.body)


def _blocks(text: str) -> list[str]:
    out = []
    for m in _FENCE.finditer(text):
        tag = (m.group(1) or '').lower()
        if tag in ('', 'python', 'python3', 'py'):
            out.append(m.group(2))
    return out


def extract_code(text: str | None) -> str | None:
    if not text:
        return None
    body = strip_think(text)
    blocks = _blocks(body)
    for b in reversed(blocks):
        if defines_transform(b):
            return b.strip('\n') + '\n'
    if defines_transform(body):
        return body.strip('\n') + '\n'
    for b in reversed(blocks):
        if _DEF_TRANSFORM.search(b):
            return b.strip('\n') + '\n'
    return None
