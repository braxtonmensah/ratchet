"""SHAM library (PREREG 4, SPEC 5 and 13 I5, builder C).

One candidate per in-context helper of the target library: same genre (arity, return kind, has_loop, uses_numpy,
token_len bin), nearest token_len, canonical hash in no accepted library, compiles, no dependency on other helpers.
Same count; total block tokens within SHAM_TOKEN_TOL (5%) of the target's in_context_tokens; verified = false.

Pools: helpers of STOCK growth programs that failed their demos (failed_pool: every growth sample with demo_pass false
and parseable code, whatever the failing status). The fallback pool (the `shuffled_pool` argument; arms passes the
failed pools of the other growth arms, never demo-passing code) is used only if fewer than SHAM_SHUFFLE_TRIGGER (95%)
of the slots find a same-genre candidate in the failed pool. Slots still empty may drop the token-length bin (tier 2,
the genre parts arity, return kind, loop and numpy still match; the library-level token total is matched separately);
any-genre filling (the old tier 3) is refused (review fix 2026-11-04: PREREG 4 registers a genre-matched SHAM), so an
unfillable slot raises ShamMatchFailed and the arm driver stops with SHAM_BUILD_FAILED for the lead.
`matched` counts exact-genre slots.
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Iterable, Sequence

from ratchet.c_util import cfg, count_tokens, iter_jsonl, parse_sample_id
from ratchet.helpers import RawHelper, extract_helpers, genre_parts
from ratchet.library import Helper, Library, in_context, rank, sha


class ShamMatchFailed(RuntimeError):
    pass


def genre(h, tok=None) -> tuple:
    """(arity, return kind grid|list|int|bool|tuple|none, has_loop, uses_numpy, token_len bin of SHAM_GENRE_BIN)."""
    src = h.source
    tl = h.token_len if isinstance(h, Helper) and tok is None else count_tokens(src, tok)
    return tuple(genre_parts(src)) + (int(tl) // int(cfg('SHAM_GENRE_BIN')),)


def _compiles(src: str) -> bool:
    try:
        compile(src, '<sham>', 'exec')
        return True
    except (SyntaxError, ValueError, RecursionError, MemoryError, OverflowError):
        return False


def _eligible(pool: Iterable[RawHelper], exclude: set[str]) -> list[RawHelper]:
    seen: set[str] = set()
    out = []
    for h in sorted(pool, key=lambda x: (x.hash, x.sample_id)):
        if h.hash in exclude or h.hash in seen or h.deps or not _compiles(h.source):
            continue
        seen.add(h.hash)
        out.append(h)
    return out


def build_sham(target: Library, failed_pool: Sequence[RawHelper], shuffled_pool: Sequence[RawHelper] | None,
               tok, seed: int, cap_tokens: int = 6000, *, exclude_hashes: Iterable[str] = (),
               print_lever: bool = False) -> Library:
    """SHAM library matched to `target`'s in-context helpers. `exclude_hashes`: canonical hashes of every accepted
    library of the run (the target's own hashes are always excluded).

    With shuffled_pool None and fewer than SHAM_SHUFFLE_TRIGGER of slots matched by genre in the failed pool, returns a
    PARTIAL library (exact matches only, meta partial=True, needs_shuffled=True) so the caller retries with the shuffled
    pool. Otherwise the result has exactly one helper per slot, or ShamMatchFailed is raised (pool too small, or the
    block tokens miss the 5% band). The LEVER SHAM line is printed only with print_lever (the arm driver prints its own);
    meta['matched'] is the count of exact-genre slots."""
    rng = random.Random(f'sham|{seed}')
    tgt = [h for h in rank(target) if h.in_context]
    if not tgt and target.helpers:
        _, names, _ = in_context(target, cap_tokens, tok)
        tgt = [h for h in rank(target) if h.name in set(names)]
    target_tokens = target.meta.get('in_context_tokens')
    if target_tokens is None:
        target_tokens = in_context(target, cap_tokens, tok)[2]
    exclude = set(exclude_hashes) | {h.hash for h in target.helpers}
    pools = {'failed': _eligible(failed_pool, exclude), 'shuffled': _eligible(shuffled_pool or [], exclude)}
    g = {}
    for p in pools.values():
        for h in p:
            g[h.hash] = (genre(h, tok), count_tokens(h.source, tok))
    tg = [(genre(h, tok), count_tokens(h.source, tok)) for h in tgt]
    jitter = {h.hash: rng.random() for p in ('failed', 'shuffled') for h in pools[p]}

    used: set[str] = set()
    slots: list[RawHelper | None] = [None] * len(tgt)
    tier: list[int] = [0] * len(tgt)

    def fill(pool_name: str, key_len: int, tier_no: int):
        for i, (tgen, tlen) in enumerate(tg):
            if slots[i] is not None:
                continue
            cands = [h for h in pools[pool_name] if h.hash not in used and g[h.hash][0][:key_len] == tgen[:key_len]]
            if not cands:
                continue
            best = min(cands, key=lambda h: (abs(g[h.hash][1] - tlen), jitter[h.hash], h.hash))
            slots[i] = best
            tier[i] = tier_no
            used.add(best.hash)

    fill('failed', 5, 1)
    exact_failed = sum(1 for s in slots if s is not None)
    if tgt and exact_failed < float(cfg('SHAM_SHUFFLE_TRIGGER')) * len(tgt):
        if shuffled_pool is None:
            # SPEC 13 I5: below the trigger the shuffled pool is required. Return only the exact matches (fewer
            # helpers than slots) so the caller samples / builds the shuffled pool and calls again with it.
            lib = _assemble(target, tgt, slots, tier, pools, tok, seed, int(target_tokens), cap_tokens)
            lib.meta.update({'matched': exact_failed, 'n_slots': len(tgt), 'partial': True, 'within_tol': False,
                             'needs_shuffled': True})
            return lib
        fill('shuffled', 5, 1)
    for key_len, tier_no in ((4, 2),):          # no any-genre tier (PREREG 4: genre-matched)
        for p in ('failed', 'shuffled'):
            fill(p, key_len, tier_no)
    if any(s is None for s in slots):
        raise ShamMatchFailed(f'SHAM_POOL_TOO_SMALL slots={len(tgt)} filled={sum(s is not None for s in slots)}')

    # swap search: bring the summed source tokens to the target's summed source tokens (same tier constraint)
    tgt_sum = sum(t[1] for t in tg)
    tol = float(cfg('SHAM_TOKEN_TOL'))
    ceiling = tgt_sum + max(0, int(cap_tokens) - int(target_tokens))   # summed tokens above this cannot fit the cap

    def dist(x):
        return abs(x - tgt_sum) + (10 * (x - ceiling) + 10 ** 6 if x > ceiling else 0)

    def total():
        return sum(g[s.hash][1] for s in slots)

    for _ in range(int(cfg('SHAM_SWAP_ITERS'))):
        cur = total()
        if dist(cur) <= tol * 0.4 * max(tgt_sum, 1):
            break
        best = None
        for i, s in enumerate(slots):
            key_len = {1: 5, 2: 4, 3: 0}[tier[i]]
            for p in ('failed', 'shuffled'):
                for c in pools[p]:
                    if c.hash in used or g[c.hash][0][:key_len] != tg[i][0][:key_len]:
                        continue
                    new = cur - g[s.hash][1] + g[c.hash][1]
                    gain = dist(cur) - dist(new)
                    if gain > 0 and (best is None or gain > best[0]):
                        best = (gain, i, c)
        if best is None:
            break
        _, i, c = best
        used.discard(slots[i].hash)
        slots[i] = c
        used.add(c.hash)

    lib = _assemble(target, tgt, slots, tier, pools, tok, seed, int(target_tokens), cap_tokens)
    _, in_names, ntok = in_context(lib, cap_tokens, tok)
    matched = sum(1 for t in tier if t == 1)
    within = abs(ntok - target_tokens) <= tol * max(target_tokens, 1) and len(in_names) == len(tgt)
    lib.meta.update({'matched': matched, 'n_slots': len(tgt), 'sham_tokens': int(ntok),
                     'within_tol': bool(within), 'n_in_block': len(in_names), 'partial': False,
                     'used_shuffled': any(h.provenance.get('pool') == 'fallback_failed' for h in lib.helpers),
                     'tier2': sum(1 for t in tier if t == 2)})
    if print_lever:
        print(f'LEVER SHAM matched={matched} of {len(tgt)} tokens={ntok} target={target_tokens} verified=0', flush=True)
    if not within:
        raise ShamMatchFailed(f'SHAM_TOKEN_MATCH_FAILED tokens={ntok} target={target_tokens} '
                              f'in_block={len(in_names)} of {len(tgt)}')
    return lib


def _assemble(target, tgt, slots, tier, pools, tok, seed, target_tokens, cap_tokens) -> Library:
    failed_hashes = {h.hash for h in pools['failed']}
    helpers = []
    names: set[str] = set()
    for i, s in enumerate(slots):
        if s is None:
            continue
        name = s.name
        k = 2
        while name in names:
            name = f'{s.name}_{k}'
            k += 1
        names.add(name)
        source = s.source
        if name != s.name:
            from ratchet.helpers import rename_source
            source = rename_source(s.source, {s.name: name})
        helpers.append(Helper(
            name=name, hash=s.hash, source=source, canonical=s.canonical, token_len=count_tokens(source, tok), deps=[],
            first_round=target.round, accepted_by='sham', calling_tasks=[s.task], n_calling_tasks=1, n_solutions=0,
            mdl_gain=0, rank=None, in_context=False, verified=False,
            provenance={'sample_ids': [s.sample_id], 'source_task': s.task,
                        'pool': 'failed' if s.hash in failed_hashes else 'fallback_failed', 'genre_tier': tier[i],
                        'matched_to': tgt[i].name}))
    return Library(arm='SHAM', round=target.round, helpers=helpers, parent_sha=None,
                   meta={'target_sha': sha(target), 'target_in_context_tokens': int(target_tokens), 'seed': seed,
                         'cap_tokens_target': int(cap_tokens)})


def _round_dirs(arm_dir: Path) -> list[Path]:
    out = []
    for p in arm_dir.glob('round_*'):
        try:
            out.append((int(p.name.split('_', 1)[1]), p))
        except ValueError:
            continue
    return [p for _, p in sorted(out)]


def failed_pool(run_dir: Path, arm: str = 'STOCK') -> list[RawHelper]:
    """Helpers of `arm` growth programs that did not pass their demos (demo_pass false: DEMO_FAIL, or an ERROR, TIMEOUT
    or BAD_OUTPUT on a demo; review fix 2026-11-04, it took DEMO_FAIL only), all rounds, deduped by hash."""
    run_dir = Path(run_dir)
    out: dict[str, RawHelper] = {}
    for rd in _round_dirs(run_dir / 'arms' / arm):
        failed = {r['sample_id'] for r in iter_jsonl(rd / 'exec.jsonl')
                  if not r.get('demo_pass') and r.get('status') not in ('NO_CODE', 'SYNTAX')}
        if not failed:
            continue
        for s in iter_jsonl(rd / 'samples.jsonl'):
            sid = s.get('sample_id')
            if sid not in failed or not s.get('code'):
                continue
            if parse_sample_id(sid)['phase'] != 'growth':
                continue
            for h in extract_helpers(s['code'], sid, s.get('task') or parse_sample_id(sid)['task'], frozenset()):
                if h.hash not in out or h.sample_id < out[h.hash].sample_id:
                    out[h.hash] = h
    return [out[k] for k in sorted(out)]
