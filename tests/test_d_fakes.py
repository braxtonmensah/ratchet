"""Deterministic fakes of the A, B, C, E interfaces (SPEC 5 signatures) for builder D's CPU tests. No TestCase here.

Programs are short fenced texts whose comment tags fix their behaviour in the fake sandbox:
    # demo=<0|1> out=<int> calls=<lib helper names>
plus top-level `def <helper>(g)` lines that the fake helper extractor reads.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
import re
import types as _types
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ratchet import rounds
from ratchet.types import Pair, Task


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


class SimulatedKill(Exception):
    pass


class KillSwitch:
    def __init__(self):
        self.left = None
        self.kills = 0
        self.ticks = 0

    def arm(self, n: int | None):
        self.left = n

    def tick(self, where: str = ''):
        self.ticks += 1
        if self.left is None:
            return
        self.left -= 1
        if self.left <= 0:
            self.left = None
            self.kills += 1
            raise SimulatedKill(where)


KS = KillSwitch()


# ---------------------------------------------------------------------------------------------------------------------
# arc_io

def _grid(v):
    return ((v,),)


class FakeArcIO:
    def __init__(self, n_growth=6, n_sealed=6):
        self.growth = ['g%02d' % i for i in range(n_growth)]
        self.sealed = ['e%02d' % i for i in range(n_sealed)]
        self.perturbed_built = False

    def task_ids(self, split):
        if split in ('growth', 'pilot'):
            return list(self.growth)
        if split == 'sealed':
            return list(self.sealed)
        if split == 'sealed_perturbed':
            return list(self.sealed) if self.perturbed_built else []
        if split == 'arcagi2_sealed':
            return []
        raise ValueError(split)

    def pilot_ids(self, n=50):
        return sorted(self.growth)[:n]

    def load_task(self, tid, split):
        train = (Pair(_grid(1), _grid(1)), Pair(_grid(2), _grid(2)))
        outs = (_grid(1),) if split in ('growth', 'pilot') else None
        if split == 'sealed_perturbed' and not self.perturbed_built:
            raise FileNotFoundError(tid)
        return Task(id=tid, split=split, train=train, test_inputs=(_grid(3),), test_outputs=outs, src_sha256=_sha(tid))


class FakePerturb:
    def __init__(self, arc):
        self.arc = arc

    def build_perturbed_split(self, seed, src_split='sealed', out_dir=None):
        self.arc.perturbed_built = True
        return Path('/fake/sealed_perturbed')


# ---------------------------------------------------------------------------------------------------------------------
# tok, prompt, extract

class FakeTok:
    def count(self, text):
        return len(re.findall(r'\w+|\S', text or ''))


@dataclass
class PromptBuild:
    messages: list
    library_tokens: int
    exemplar_tokens: int
    task_tokens: int
    instruction_tokens: int
    helpers_in_context: tuple
    lib_sha: str | None
    exemplar_ids: tuple
    helpers_inline: tuple = ()


class FakePrompt:
    def __init__(self, library_mod):
        self.lib = library_mod

    def build_messages(self, task, tok, *, library=None, exemplars=None, inline_noncallable=False, drop=frozenset(),
                       cap_tokens=6000, inline_library=None):
        names, ltok, lsha = (), 0, None
        inl = tuple(sorted(h.name for h in inline_library.helpers)) if inline_library is not None else ()
        if library is not None:
            ctx = sorted((h for h in library.helpers if h.in_context), key=lambda h: h.name)
            names = tuple(h.name for h in ctx)
            ltok = sum(h.token_len for h in ctx)
            lsha = self.lib.sha(library)
        ex_ids, etok = (), 0
        if exemplars:
            ex_ids = tuple(e.sample_id for e in exemplars)
            etok = sum(e.token_len for e in exemplars)
        user = 'LIB %s INLINE %d EX %s TASK %s' % (','.join(names), int(inline_noncallable or bool(inl)),
                                                  ','.join(ex_ids) + ('|TEXT ' + ','.join(inl) if inl else ''), task.id)
        return PromptBuild(messages=[{'role': 'system', 'content': 'SYS'}, {'role': 'user', 'content': user}],
                           library_tokens=ltok, exemplar_tokens=etok, task_tokens=10, instruction_tokens=5,
                           helpers_in_context=names, lib_sha=lsha, exemplar_ids=ex_ids, helpers_inline=inl)


class FakeExtract:
    @staticmethod
    def extract_code(text):
        m = re.findall(r'```python\n(.*?)```', text or '', re.S)
        return m[-1] if m else None


# ---------------------------------------------------------------------------------------------------------------------
# llm and ledger

@dataclass
class GenRequest:
    request_id: str
    messages: list
    n: int
    seed: int
    meta: dict


@dataclass
class GenResult:
    request_id: str
    texts: list
    finish_reasons: list
    usage: dict
    latency_s: float


def program_text(task: str, seed: int, i: int, user: str) -> str:
    libnames = user.split()[1] if user.startswith('LIB ') else ''
    libnames = '' if libnames == 'INLINE' else libnames
    h = int(_sha('%s|%d|%d|%s' % (task, seed, i, user)), 16)
    k = h % 7
    if k == 0:
        return 'I could not find a rule.'
    if k == 1:
        body, tag = 'def hA(g):\n    return g\n', 'demo=1 out=1 calls='
    elif k == 2:
        body, tag = 'def hA(g):\n    return g\ndef hB(g):\n    return g\n', 'demo=1 out=2 calls='
    elif k == 3:
        body, tag = 'def hC(g):\n    return g\n', 'demo=0 out=0 calls='
    elif k == 4:
        first = libnames.split(',')[0] if libnames else ''
        body, tag = '', 'demo=1 out=1 calls=%s' % first
    elif k == 5:
        body, tag = 'def hD_%s(g):\n    return g\n' % task, 'demo=1 out=3 calls='
    else:
        body, tag = 'def hE(g):\n    return g\ndef hF(g):\n    return g\n', 'demo=1 out=1 calls='
    return 'Here.\n```python\n# %s\n%sdef transform(grid):\n    return grid\n```\n' % (tag, body)


class FakeLedgerMod:
    class Ledger:
        def __init__(self, path):
            self.path = Path(path)

        def append(self, row):
            rounds.repair_jsonl(self.path)
            rounds.append_jsonl(self.path, [row])

    @staticmethod
    def iter_rows(run_dir):
        out = {}
        for p in sorted((Path(run_dir) / 'ledger').glob('ledger_*.jsonl')):
            for row in rounds.iter_jsonl(p):
                out[row['request_id']] = row
        return iter(out[k] for k in sorted(out))

    @staticmethod
    def totals(run_dir, arm=None, phase=None, sealed_seed=None):
        rows = list(FakeLedgerMod.iter_rows(run_dir))
        return {'requests': len(rows), 'gen': sum(r['gen_tokens'] for r in rows)}


class FakeClient:
    """Issues requests in a shuffled order (as a thread pool would), writes one ledger row per request, honours the
    stop-issue time with the run's clock, and ticks the kill switch."""

    def __init__(self, run_dir: Path, job_id: str, clock=lambda: 0.0, order_seed: int = 0, fail_ids=()):
        self.ledger = FakeLedgerMod.Ledger(Path(run_dir) / 'ledger' / ('ledger_%s.jsonl' % job_id))
        self.job_id = job_id
        self.clock = clock
        self.rng = random.Random(order_seed)
        self.fail_ids = set(fail_ids)
        self.issued = []

    def server_metrics(self):
        return {'prefix_cache_hit_rate': 0.5}

    def run(self, reqs, on_result, stop_issue_ts, hard_stop_ts):
        reqs = list(reqs)
        self.rng.shuffle(reqs)
        done = 0
        for req in reqs:
            if self.clock() >= stop_issue_ts:
                break
            if req.request_id in self.fail_ids:
                continue
            KS.tick('client:' + req.request_id)
            user = req.messages[-1]['content']
            texts = [program_text(req.meta['task'], req.seed, i, user) for i in range(req.n)]
            gen = [FakeTok().count(t) for t in texts]
            prompt = 100 + int(req.meta.get('library_tokens', 0)) + int(req.meta.get('exemplar_tokens', 0))
            row = dict(req.meta)
            row.update({'request_id': req.request_id, 'job_id': self.job_id, 'prompt_tokens': prompt,
                        'prompt_tokens_logical': prompt * req.n, 'gen_tokens': sum(gen),
                        'gen_tokens_per_sample': gen, 'finish_reasons': ['stop'] * req.n})
            self.ledger.append(row)
            self.issued.append(req.request_id)
            on_result(GenResult(req.request_id, texts, ['stop'] * req.n,
                                {'prompt_tokens': prompt, 'completion_tokens': sum(gen)}, 0.01))
            KS.tick('client_after:' + req.request_id)
            done += 1
        return {'done': done}


# ---------------------------------------------------------------------------------------------------------------------
# sandbox

@dataclass
class ExecJob:
    sample_id: str
    task: object
    code: str
    library_src: str
    mode: str


def _tags(code):
    m = re.search(r'# demo=(\d) out=(\d+) calls=(\S*)', code or '')
    if not m:
        return 0, 0, []
    return int(m.group(1)), int(m.group(2)), [c for c in m.group(3).split(',') if c]


class FakeSandbox:
    def __init__(self):
        self.jobs = []

    @staticmethod
    def probe_isolation():
        return 'audit'

    def run_batch(self, jobs, workers):
        for j in jobs:
            KS.tick('exec:' + j.sample_id)
            self.jobs.append(j)
            demo, out, calls = _tags(j.code)
            defined = set(re.findall(r'^def (\w+)\(', j.library_src or '', re.M))
            if any(c not in defined for c in calls) and j.mode != 'inline':
                demo = 0
            if j.mode == 'inline' and calls:
                demo = 0
            ok = bool(demo) and int(_sha(j.task.id + j.code), 16) % 4 != 0
            yield {'sample_id': j.sample_id, 'code_sha': _sha(j.code), 'status': 'OK' if ok else 'DEMO_FAIL',
                   'demo_pass': ok, 'n_demo_pass': 2 if ok else 0, 'n_demos': 2, 'first_fail_demo': None if ok else 0,
                   'test_outputs': [[[out]]] if ok else None, 'helper_calls': {c: 1 for c in calls if ok},
                   'static_refs': calls, 'wall_s': [0.01], 'timeouts': 0, 'exec_mode': j.mode, 'cache_hit': False}


# ---------------------------------------------------------------------------------------------------------------------
# helpers and library

@dataclass
class RawH:
    name: str
    hash: str
    token_len: int
    task: str
    sample_id: str


@dataclass
class Sol:
    sample_id: str
    task: str
    code: str
    code_sha: str
    helpers: tuple
    lib_calls: frozenset
    demo_pass: bool = True


@dataclass
class Helper:
    name: str
    hash: str
    token_len: int
    calling_tasks: list = field(default_factory=list)
    in_context: bool = False
    verified: bool = True
    first_round: int | None = None


@dataclass
class Library:
    arm: str
    round: int
    helpers: list
    parent_sha: str | None
    meta: dict

    def hashes(self):
        return {h.name: h.hash for h in self.helpers}


class FakeHelpers:
    @staticmethod
    def build_solution(sample_id, task, code, library_names=frozenset(), *, demo_pass=True, code_sha=None):
        if code is None or 'def transform' not in code:
            return None
        hs = tuple(RawH(n, _sha('h:' + n), 3 * len(n), task, sample_id)
                   for n in re.findall(r'^def (\w+)\(', code, re.M) if n != 'transform')
        _, _, calls = _tags(code)
        return Sol(sample_id, task, code, code_sha or _sha(code), hs,
                   frozenset(c for c in calls if c in set(library_names)), demo_pass)

    @staticmethod
    def extract_helpers(code, sample_id, task, library_names=frozenset()):
        s = FakeHelpers.build_solution(sample_id, task, code, library_names)
        return list(s.helpers) if s else []

    @staticmethod
    def dedup_solutions(sols):
        best = {}
        for s in sols:
            k = (s.task, s.code_sha)
            if k not in best or s.sample_id < best[k].sample_id:
                best[k] = s
        return sorted(best.values(), key=lambda s: (s.task, s.sample_id))

    @staticmethod
    def accept(sols, prev, tok):
        prevh = {h.hash for h in prev.helpers}
        tasks, first = defaultdict(set), {}
        for s in sols:
            if not s.sample_id.split('|')[1] == 'growth':
                raise ValueError('sealed solution reached accept')
            for h in s.helpers:
                if h.hash not in prevh:
                    tasks[h.hash].add(s.task)
                    first.setdefault(h.hash, h)
        return [Helper(first[k].name, k, first[k].token_len, sorted(tasks[k])) for k in sorted(tasks)
                if len(tasks[k]) >= 2]


class FakeLibraryMod:
    Library = Library
    Helper = Helper

    @staticmethod
    def empty(arm):
        return Library(arm, 0, [], None, {})

    @staticmethod
    def _dict(lib):
        return {'arm': lib.arm, 'round': lib.round, 'parent_sha': lib.parent_sha,
                'meta': {k: lib.meta[k] for k in sorted(lib.meta)},
                'helpers': [asdict(h) for h in sorted(lib.helpers, key=lambda h: h.name)]}

    @staticmethod
    def sha(lib):
        return _sha(json.dumps(FakeLibraryMod._dict(lib), sort_keys=True))

    @staticmethod
    def merge(prev, accepted, round, sols):
        helpers = copy.deepcopy(prev.helpers)
        by = {h.name: h for h in helpers}
        for s in sols:
            for n in s.lib_calls:
                if n in by and s.task not in by[n].calling_tasks:
                    by[n].calling_tasks = sorted(set(by[n].calling_tasks) | {s.task})
        for a in accepted:
            a = copy.deepcopy(a)
            a.first_round = round
            helpers.append(a)
        meta = {k: v for k, v in prev.meta.items() if k not in ('created_et', 'in_context_tokens')}
        return Library(prev.arm, round, helpers, FakeLibraryMod.sha(prev) if (prev.helpers or prev.round) else None,
                       meta)

    @staticmethod
    def render_py(lib, names):
        return ''.join('def %s(g):\n    return g\n' % n for n in names)

    @staticmethod
    def save(lib, dir, cap_tokens, tok, stem=None):
        KS.tick('save')
        stem = stem or 'L_%d' % lib.round
        order = sorted(lib.helpers, key=lambda h: (-len(h.calling_tasks), h.token_len, h.name))
        used = 0
        for h in order:
            h.in_context = used + h.token_len <= cap_tokens
            if h.in_context:
                used += h.token_len
        lib.meta['in_context_tokens'] = used
        d = FakeLibraryMod._dict(lib)
        s = _sha(json.dumps(d, sort_keys=True))
        d['sha256'] = s
        dir = Path(dir)
        jp, pp = dir / (stem + '.json'), dir / (stem + '.py')
        rounds.atomic_write_bytes(jp, (json.dumps(d, sort_keys=True, indent=1) + '\n').encode())
        rounds.atomic_write_bytes(pp, FakeLibraryMod.render_py(lib, [h.name for h in order if h.in_context]).encode())
        return jp, pp, s

    @staticmethod
    def load(path):
        d = json.loads(Path(path).read_text())
        want = d.pop('sha256')
        if _sha(json.dumps(d, sort_keys=True)) != want:
            raise ValueError('LIBRARY_HASH_MISMATCH')
        return Library(d['arm'], d['round'], [Helper(**h) for h in d['helpers']], d['parent_sha'], d['meta'])


# ---------------------------------------------------------------------------------------------------------------------
# exemplar, sham, plant

@dataclass(frozen=True)
class Exemplar:
    task: str
    sample_id: str
    code: str
    token_len: int
    features: tuple


class FakeExemplar:
    Exemplar = Exemplar

    class Scaler:
        @staticmethod
        def fit(tasks):
            return FakeExemplar.Scaler()

    @staticmethod
    def pool_from_rounds(run_dir, arm, upto_round, **kw):
        best = {}
        for r in range(1, upto_round + 1):
            d = Path(run_dir) / 'arms' / arm / ('round_%d' % r)
            samples = rounds.read_rows(d / 'samples.jsonl', 'sample_id')
            for sid, row in sorted(rounds.read_rows(d / 'exec.jsonl', 'sample_id').items()):
                if row.get('demo_pass'):
                    s = samples[sid]
                    cand = (len(s['code']), sid)
                    if s['task'] not in best or cand < best[s['task']][0]:
                        best[s['task']] = (cand, Exemplar(s['task'], sid, s['code'], len(s['code']) // 4, (1.0,)))
        return [best[t][1] for t in sorted(best)]

    @staticmethod
    def neighbours(task, pool, scaler, k=3, exclude_task=None):
        cands = [e for e in pool if e.task != exclude_task]
        return sorted(cands, key=lambda e: _sha(task.id + e.task))[:k]


class FakeSham:
    @staticmethod
    def failed_pool(run_dir, arm='STOCK'):
        out = []
        for d in sorted((Path(run_dir) / 'arms' / arm).glob('round_*')):
            samples = rounds.read_rows(d / 'samples.jsonl', 'sample_id')
            for sid, row in sorted(rounds.read_rows(d / 'exec.jsonl', 'sample_id').items()):
                if row['status'] == 'DEMO_FAIL' and samples[sid].get('code'):
                    out.extend(FakeHelpers.extract_helpers(samples[sid]['code'], sid, samples[sid]['task']))
        return out

    @staticmethod
    def build_sham(target, failed_pool, shuffled_pool, tok, seed, cap_tokens=6000, exclude_hashes=()):
        n = sum(1 for h in target.helpers if h.in_context)
        seen, hs = set(), []
        for h in list(failed_pool) + list(shuffled_pool or []):
            if h.hash in seen or h.hash in {x.hash for x in target.helpers}:
                continue
            seen.add(h.hash)
            hs.append(Helper('sham_' + h.name, _sha('sham' + h.hash), h.token_len, [h.task], verified=False))
            if len(hs) >= n:
                break
        return Library('SHAM', 0, hs, None, {})


class FakePlant:
    @staticmethod
    def load_arcdsl(dir):
        return {'dir': str(dir)}

    @staticmethod
    def build_tranches(src, R, cap_tokens, tok):
        prims = ['p%d' % i for i in range(2 * R)]
        out = []
        for r in range(1, R + 1):
            hs = [Helper(p, _sha(p), 4, ['solver']) for i, p in enumerate(prims) if i % R < r]
            out.append(Library('PLANTDRIP', r, hs, None, {}))
        return out


# ---------------------------------------------------------------------------------------------------------------------
# select, types, pilot, knockout, verdict

@dataclass(frozen=True)
class Candidate:
    sample_id: str
    code_len: int
    demo_pass: bool
    test_outputs: tuple | None


class FakeSelect:
    @staticmethod
    def pass2(task_id, candidates, k=2):
        votes, best_len = defaultdict(int), {}
        for c in candidates:
            if c.demo_pass and c.test_outputs is not None:
                votes[c.test_outputs] += 1
                best_len[c.test_outputs] = min(best_len.get(c.test_outputs, 10**9), c.code_len)
        order = sorted(votes, key=lambda o: (-votes[o], best_len[o], repr(o)))[:k]
        sub = {'task': task_id, 'attempts': [{'outputs': [list(map(list, g)) for g in o], 'votes': votes[o]}
                                             for o in order],
               'n_candidates': len(candidates), 'n_demo_pass': sum(1 for c in candidates if c.demo_pass)}
        return _types.SimpleNamespace(to_json=lambda: sub)


class FakePilot:
    def __init__(self, S=2, R=2, smoke=True):
        self.S, self.R, self.smoke = S, R, smoke

    def step1_smoke(self, run_dir):
        return {'pass': self.smoke}

    def step2_plant(self, run_dir):
        return {'pass': True}

    def step3_rates(self, run_dir):
        return {'gen_tok_per_s': 1.0}

    def choose_SR(self, rates):
        return {'S': self.S, 'R': self.R}

    def write_pilot_report(self, run_dir):
        p = Path(run_dir) / 'PILOT.md'
        p.write_text('pilot\n')
        return p


class FakeKnockout:
    @staticmethod
    def build_knockout_libraries(L_R, W, winners):
        out = {}
        for t in sorted(W):
            called = set()
            for r in winners.get(t, []):
                called |= set((r['helper_calls'] if isinstance(r, dict) else r.helper_calls).keys())
            lib = copy.deepcopy(L_R)
            lib.helpers = [h for h in lib.helpers if h.in_context and h.name not in called]
            lib.meta = dict(lib.meta, knockout_removed=sorted(called & {h.name for h in L_R.helpers if h.in_context}))
            out[t] = lib
        return out

    @staticmethod
    def inline_text_library(L_R, gone, task):
        lib = copy.deepcopy(L_R)
        lib.helpers = [h for h in lib.helpers if h.in_context and h.name in gone]
        lib.meta = dict(lib.meta, knockout_mode='inline', knockout_task=task)
        return lib


class FakeVerdict:
    @staticmethod
    def write_result(run_dir, repo_dir):
        p = Path(run_dir) / 'RESULT.md'
        p.write_text('NULL\n')
        return p


def make_kit(n_growth=6, n_sealed=6, pilot=None):
    arc = FakeArcIO(n_growth, n_sealed)
    lib = FakeLibraryMod
    kit = _types.SimpleNamespace(
        tok=FakeTok(), arc_io=arc, perturb=FakePerturb(arc), prompt=FakePrompt(lib), extract=FakeExtract,
        llm=_types.SimpleNamespace(GenRequest=GenRequest), ledger=FakeLedgerMod,
        sandbox=_types.SimpleNamespace(ExecJob=ExecJob, run_batch=FakeSandbox().run_batch,
                                       probe_isolation=FakeSandbox.probe_isolation),
        helpers=FakeHelpers, library=lib, exemplar=FakeExemplar, sham=FakeSham, plant=FakePlant,
        select=FakeSelect, types=_types.SimpleNamespace(Candidate=Candidate), pilot=pilot or FakePilot(),
        knockout=FakeKnockout, verdict=FakeVerdict)
    return kit
