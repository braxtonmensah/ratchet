"""Arm registry and drivers (PREREG 4, 6.3, 6.4, 7; SPEC 5 builder D, 7, 9, 13 I1 to I5, I10 to I12, I17). Owner: D.

Every driver is resumable: sampling is keyed by request_id (a request is done when all n of its sample_ids are in
samples.jsonl), execution by sample_id (exec.jsonl), and EXTRACTING -> FROZEN is a pure function of a round's rows,
re-run from scratch after a kill. Seeds exclude the arm name, so arms with identical prompts get identical draws
(common random numbers, SPEC 13 I3).

Other builders' modules are reached through a kit (`run.kit`, default: the real ratchet modules, imported lazily), so the
drivers can be tested on CPU with fakes that keep the SPEC 5 signatures.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from . import config, rounds
from .rounds import (WorkUnit, append_jsonl, atomic_write_json, load_state, now_et, read_json, read_rows, repair_jsonl,
                     save_state)

ARMS = config.ARMS
CONDITION_SPLIT = {'sealed': 'sealed', 'perturbed': 'sealed_perturbed', 'arcagi2': 'arcagi2_sealed',
                   'knockout_delete': 'sealed', 'knockout_inline': 'sealed'}
CONDITION_PHASE = {'sealed': 'sealed', 'perturbed': 'perturbed', 'arcagi2': 'arcagi2',
                   'knockout_delete': 'knockout_delete', 'knockout_inline': 'knockout_inline'}
# Knockout re-samples with the seeds of STOCK's own sealed pass (paired with the run being knocked out).
CONDITION_SEED_PHASE = {'sealed': 'sealed', 'perturbed': 'perturbed', 'arcagi2': 'arcagi2',
                        'knockout_delete': 'sealed', 'knockout_inline': 'sealed'}
# Both knockout modes execute only the helpers that stay callable (sandbox mode 'deleted'); inline mode also shows the
# knocked-out helpers as non-callable text (PREREG 6.3b; review fix 2026-11-04).
KO_MODES = {'delete': ('knockout_delete', 'deleted'), 'inline': ('knockout_inline', 'deleted')}


class ArmError(RuntimeError):
    pass


class FreezeMissing(ArmError):
    pass


class SealedHelperRefused(ArmError):
    """A non-growth sample reached a library build (PREREG 4: sealed tasks never contribute helpers)."""


# ---------------------------------------------------------------------------------------------------------------------
# Kit: the other builders' modules

_KIT_MODULES = ('arc_io', 'sandbox', 'select', 'perturb', 'types', 'tok', 'llm', 'ledger', 'prompt', 'extract',
                'helpers', 'library', 'sham', 'exemplar', 'plant', 'pilot', 'knockout', 'verdict', 'report', 'stats')


class LazyKit:
    """Attribute access imports ratchet.<name> on first use. `tok` is the tokenizer (set by the caller)."""

    def __init__(self, tok=None, **overrides):
        self.tok = tok
        self.__dict__.update(overrides)

    def __getattr__(self, name):
        if name in _KIT_MODULES:
            mod = importlib.import_module('ratchet.' + name)
            self.__dict__[name] = mod
            return mod
        raise AttributeError(name)


def kit_of(run) -> Any:
    if run.kit is None:
        run.kit = LazyKit()
    if getattr(run.kit, 'tok', None) is None:
        run.kit.tok = default_tokenizer(run.kit, run)
    return run.kit


def default_tokenizer(kit, run=None):
    """The model's tokenizer. Inside a job (RATCHET_REQUIRE_REAL_TOKENIZER=1, set by serve_and_step.sh) and for any run
    on the real runs tree (login-node `grow --finalize`, SHAM and PLANT builds included; review fix 2026-11-04) a
    failure is fatal: the 6,000-token library cap, the MDL 20 threshold and the SHAM 5% match would otherwise be measured
    in stub tokens. Elsewhere (tests) it falls back to StubTokenizer and says so."""
    tokmod = importlib.import_module('ratchet.tok')
    model_dir = Path(os.environ.get('RATCHET_MODEL_DIR', str(config.MODEL_DIR)))
    required = os.environ.get('RATCHET_REQUIRE_REAL_TOKENIZER') == '1' or (run is not None and rounds.production_run(run))
    try:
        tok = tokmod.load_tokenizer(model_dir)
        print('LEVER TOKENIZER kind=hf path=%s sha=%s' % (model_dir / 'tokenizer.json', tokmod.tokenizer_sha(tok)),
              flush=True)
        return tok
    except Exception as e:  # noqa: BLE001 - tokenizers missing on the login node
        if required:
            raise ArmError('TOKENIZER_REQUIRED %s: %s: %s' % (model_dir, type(e).__name__, e))
        print('LEVER TOKENIZER kind=stub reason=%s' % type(e).__name__, flush=True)
        return tokmod.StubTokenizer()


# ---------------------------------------------------------------------------------------------------------------------
# Run

@dataclass
class Run:
    dir: Path
    S: int | None
    R: int | None
    seed_base: int
    cfg: dict
    kit: Any = field(default=None, repr=False, compare=False)
    job_id: str = field(default_factory=lambda: os.environ.get('SLURM_JOB_ID', 'local'))
    cache: dict = field(default_factory=dict, repr=False, compare=False)

    @property
    def name(self) -> str:
        return self.cfg.get('name') or Path(self.dir).name

    @property
    def cap(self) -> int:
        return int(self.cfg.get('cap_tokens', config.LIBRARY_CAP_TOKENS))


def init_run(dir: Path, S: int | None = None, R: int | None = None, seed_base: int = config.SEED_BASE,
             **cfg) -> 'Run':
    dir = Path(dir)
    p = dir / 'RUN.json'
    if p.exists():
        raise ArmError('RUN.json already exists in %s' % dir)
    ret = rounds.retired(dir)
    if ret:
        raise ArmError('HARNESS_RETIRED after VOID runs %s (PREREG 9); no new run' % ','.join(ret))
    if (S is not None or R is not None) and not cfg.get('skip_pilot'):
        raise ArmError('S and R come from the pilot rule (PREREG 7); pass them only with skip_pilot (tests)')
    probe = Run(dir=dir, S=S, R=R, seed_base=seed_base, cfg=dict(cfg))
    rounds.check_test_switches(probe)
    instr = cfg.pop('instruction', config.INSTRUCTION_DEFAULT_RUN)
    cfg.pop('instruction_sha', None)
    if instr not in config.INSTRUCTIONS:
        raise ArmError('INSTRUCTION_REFUSED unknown instruction %r' % (instr,))
    if instr != config.INSTRUCTION_DEFAULT_RUN and not cfg.get('skip_pilot'):
        raise ArmError('INSTRUCTION_REFUSED a piloted run starts at %s; only the pilot screen may change it'
                       % config.INSTRUCTION_DEFAULT_RUN)
    d = {'schema': config.RUN_SCHEMA, 'name': dir.name, 'S': S, 'R': R, 'seed_base': seed_base,
         'sealed_seeds': list(config.SEALED_SEEDS), 'perturb_seed': config.PERTURB_SEED,
         'model': str(config.MODEL_DIR), 'cap_tokens': config.LIBRARY_CAP_TOKENS, 'created_et': now_et(),
         'code_git_sha': code_git_sha(), 'harness': 'v2', 'max_tokens': config.MAX_TOKENS,
         'instruction': instr, 'instruction_sha': config.INSTRUCTION_SHAS[instr],
         'instruction_history': [{'instruction': instr, 'sha': config.INSTRUCTION_SHAS[instr], 'et': now_et(),
                                  'why': 'init'}]}
    d.update(cfg)
    atomic_write_json(p, d)
    return load_run(dir)


def load_run(dir: Path, kit=None) -> 'Run':
    dir = Path(dir)
    d = read_json(dir / 'RUN.json')
    if d is None:
        raise ArmError('no RUN.json in %s (run `ratchet init`)' % dir)
    run = Run(dir=dir, S=d.get('S'), R=d.get('R'), seed_base=int(d.get('seed_base', config.SEED_BASE)), cfg=d, kit=kit)
    rounds.check_test_switches(run)
    return run


def update_run(run: Run, **kv) -> Run:
    d = read_json(Path(run.dir) / 'RUN.json', {})
    d.update(kv)
    atomic_write_json(Path(run.dir) / 'RUN.json', d)
    new = load_run(run.dir, kit=run.kit)
    new.job_id, new.cache = run.job_id, run.cache
    return new


class InstructionRefused(ArmError):
    pass


def instruction_sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def run_instruction(run: Run) -> tuple[str, str, str]:
    """(name, text, sha256) of the instruction recorded for this run (RUN.json `instruction`, `instruction_sha`).
    Refuses (InstructionRefused) when the run records none (a pre-v2 run), an unknown name, or a sha that is not the
    sha of the text this code would send (AMENDMENT 2: the run refuses a hash other than the registered text's)."""
    name = run.cfg.get('instruction')
    rec = run.cfg.get('instruction_sha')
    if name not in config.INSTRUCTIONS:
        raise InstructionRefused('INSTRUCTION_REFUSED run %s records no known instruction (%r)' % (run.name, name))
    text = config.INSTRUCTIONS[name]
    got = instruction_sha(text)
    if got != config.INSTRUCTION_SHAS[name] or rec != got:
        raise InstructionRefused('INSTRUCTION_SHA_REFUSED run=%s instruction=%s in_use=%s recorded=%s registered=%s' % (
            run.name, name, got, rec, config.INSTRUCTION_SHAS[name]))
    return name, text, got


def lever_instruction_line(run: Run) -> str:
    name, _text, sha = run_instruction(run)
    return 'LEVER INSTRUCTION sha=%s name=%s max_tokens=%d' % (sha, name, int(config.SAMPLING['max_tokens']))


def model_sha(run: Run) -> str | None:
    """sha256 over the per-file sha256 of every weight and config file (RUN.json model_files_sha256, written by
    `ratchet modelcheck` in the first GPU job; review fix 2026-11-04), else the old config.json +
    model.safetensors.index.json hash (SPEC 4.4); None if neither exists."""
    if 'model_sha' not in run.cache and run.cfg.get('model_files_sha256'):
        files = run.cfg['model_files_sha256']
        blob = ''.join('%s %s\n' % (k, files[k]['sha256']) for k in sorted(files))
        run.cache['model_sha'] = hashlib.sha256(blob.encode()).hexdigest()
    if 'model_sha' not in run.cache:
        d = Path(run.cfg.get('model') or config.MODEL_DIR)
        h, seen = hashlib.sha256(), False
        for name in ('config.json', 'model.safetensors.index.json'):
            p = d / name
            if p.exists():
                h.update(p.read_bytes())
                seen = True
        run.cache['model_sha'] = h.hexdigest() if seen else None
    return run.cache['model_sha']


MODEL_FILE_GLOBS = ('*.safetensors', '*.json', '*.jinja', '*.model', '*.txt', '*.py')


def model_files(model_dir: Path) -> list[Path]:
    out = set()
    for g in MODEL_FILE_GLOBS:
        out.update(p for p in Path(model_dir).glob(g) if p.is_file())
    return sorted(out)


def model_check(run: Run) -> dict:
    """PREREG 3: the weights are fixed for the whole run. First call: sha256, size and mtime of every weight, config and
    tokenizer file into RUN.json model_files_sha256. Later calls: size and mtime of every file must match (a file whose
    size or mtime changed is re-hashed, and must hash the same), and no file may appear or disappear. Raises ArmError
    MODEL_CHANGED; returns a summary for the META line."""
    d = Path(run.cfg.get('model') or config.MODEL_DIR)
    files = model_files(d)
    if not files:
        raise ArmError('MODEL_MISSING no weight or config files in %s' % d)

    def sha(p):
        h = hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda: f.read(1 << 24), b''):
                h.update(b)
        return h.hexdigest()

    have = run.cfg.get('model_files_sha256')
    if not have:
        rec = {}
        for p in files:
            st = p.stat()
            rec[p.name] = {'sha256': sha(p), 'size': st.st_size, 'mtime_ns': st.st_mtime_ns}
        update_run(run, model_files_sha256=rec, model_files_recorded_et=now_et())
        return {'state': 'RECORDED', 'files': len(rec), 'bytes': sum(v['size'] for v in rec.values())}
    names = {p.name for p in files}
    if names != set(have):
        raise ArmError('MODEL_CHANGED file set differs: added %s removed %s' % (
            sorted(names - set(have)), sorted(set(have) - names)))
    rehashed = 0
    for p in files:
        st, want = p.stat(), have[p.name]
        if st.st_size != want['size'] or st.st_mtime_ns != want['mtime_ns']:
            rehashed += 1
            if st.st_size != want['size'] or sha(p) != want['sha256']:
                raise ArmError('MODEL_CHANGED %s (size %d vs %d)' % (p.name, st.st_size, want['size']))
    return {'state': 'MATCH', 'files': len(files), 'rehashed': rehashed}


def code_git_sha() -> str:
    """RATCHET_CODE_SHA, else the CODE_SHA file beside the code (written at sync time: the Quartz code dir is an rsync
    copy whose own .git is stale), else the repo's .git HEAD."""
    sha = os.environ.get('RATCHET_CODE_SHA')
    if sha:
        return sha
    try:
        f = (config.REPO_DIR / 'CODE_SHA').read_text().split()
        if f:
            return f[0]
    except OSError:
        pass
    git = config.REPO_DIR / '.git'
    try:
        head = (git / 'HEAD').read_text().strip()
        if head.startswith('ref: '):
            ref = head[5:]
            p = git / ref
            if p.exists():
                return p.read_text().strip()
            packed = git / 'packed-refs'
            if packed.exists():
                for ln in packed.read_text().splitlines():
                    if ln.endswith(' ' + ref):
                        return ln.split()[0]
            return 'unknown'
        return head
    except OSError:
        return 'nogit'


# ---------------------------------------------------------------------------------------------------------------------
# Seeds (common random numbers)

def seed_for(run: Run, phase: str, round: int | None, task: str, slot: int, sealed_seed: int | None) -> int:
    key = json.dumps([run.seed_base, phase, round, task, slot, sealed_seed], separators=(',', ':'))
    return int.from_bytes(hashlib.sha256(key.encode('utf-8')).digest()[:config.SEED_BYTES], 'big')


# ---------------------------------------------------------------------------------------------------------------------
# Deadline

class Deadline:
    def __init__(self, start_ts: float, stop_issue_s: int = config.STOP_ISSUE_S, hard_s: int = config.HARD_STOP_S,
                 clock: Callable[[], float] = time.time):
        self.start_ts = float(start_ts)
        self.stop_issue_ts = self.start_ts + stop_issue_s
        self.hard_ts = self.start_ts + hard_s
        self.clock = clock

    def issue_ok(self) -> bool:
        return self.clock() < self.stop_issue_ts

    def hard(self) -> bool:
        return self.clock() >= self.hard_ts

    def elapsed(self) -> float:
        return self.clock() - self.start_ts


# ---------------------------------------------------------------------------------------------------------------------
# Logs and lever markers (SPEC 9): logs/server_<ARM>_<phase>_<jobid>.log, META first

def meta_line(run: Run, arm: str, phase: str, round: int | None) -> str:
    s = config.SAMPLING
    return ('META arm=%s phase=%s round=%s model=%s temperature=%s top_p=%s max_tokens=%d enable_thinking=%d '
            'seed_base=%d S=%s R=%s code_sha=%s job=%s' % (
                arm, phase, '-' if round is None else round, run.cfg.get('model', str(config.MODEL_DIR)),
                s['temperature'], s['top_p'], s['max_tokens'], int(bool(s['enable_thinking'])), run.seed_base,
                run.S, run.R, run.cfg.get('code_git_sha_live') or code_git_sha(), run.job_id))


_log_lock = threading.Lock()


def emit(run: Run, arm: str, phase: str, line: str, round: int | None = None) -> None:
    path = rounds.logs_dir(run) / ('server_%s_%s_%s.log' % (arm, phase, run.job_id))
    with _log_lock:
        new = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a', encoding='utf-8') as f:
            if new:
                f.write(meta_line(run, arm, phase, round) + '\n')
            f.write(line.rstrip('\n') + '\n')
        print(line, flush=True)


def lever_sandbox(run: Run, arm: str, phase: str, lib_sha: str | None, helpers_callable: int, round=None) -> None:
    mode = run.cache.get('net')
    if mode is None:
        try:
            mode = kit_of(run).sandbox.probe_isolation()
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ == 'SandboxIsolationError':
                raise                   # production without the bwrap view: stop, never run programs
            mode = 'probe_failed_' + type(e).__name__
        run.cache['net'] = mode
    net = 'unshare' if mode in ('bwrap', 'unshare') else mode
    fs = 'bwrap' if mode == 'bwrap' else 'hook'
    emit(run, arm, phase, 'LEVER SANDBOX lib_sha=%s helpers_callable=%d net=%s fs=%s' % (
        lib_sha or 'none', helpers_callable, net, fs), round)


def lever_prefix(run: Run, arm: str, phase: str, client, round=None) -> None:
    try:
        m = client.server_metrics() or {}
        rate = m.get('prefix_cache_hit_rate')
    except Exception:  # noqa: BLE001
        rate = None
    emit(run, arm, phase, 'LEVER PREFIX hit_rate=%s' % ('unavailable' if rate is None else '%.4f' % float(rate)), round)


# ---------------------------------------------------------------------------------------------------------------------
# Tasks

def split_ids(run: Run, split: str) -> list[str]:
    key = ('ids', split)
    if key not in run.cache:
        run.cache[key] = sorted(kit_of(run).arc_io.task_ids(split))
    return run.cache[key]


def tasks_of(run: Run, split: str, ids: Sequence[str] | None = None) -> list:
    kit = kit_of(run)
    store = run.cache.setdefault(('tasks', split), {})
    out = []
    for i in (split_ids(run, split) if ids is None else ids):
        if i not in store:
            store[i] = kit.arc_io.load_task(i, split)
        out.append(store[i])
    return out


def growth_ids(run: Run) -> list[str]:
    return split_ids(run, 'growth')


# ---------------------------------------------------------------------------------------------------------------------
# Sampling core

@dataclass
class ReqSpec:
    request_id: str
    task: Any
    arm: str
    phase: str
    round: int | None
    sealed_seed: int | None
    slots: list[int]
    sample_ids: list[str]
    seed: int
    library: Any = None
    exemplars: Any = None
    inline: bool = False
    inline_library: Any = None          # knockout inline: these helpers shown as NON-callable text (PREREG 6.3b)
    meta_extra: dict = field(default_factory=dict)


@dataclass
class JobCounters:
    sampling_s: float = 0.0
    exec_s: float = 0.0
    requests: int = 0
    prompt: int = 0
    prompt_logical: int = 0
    cached: int = 0
    gen: int = 0
    exec_runs: int = 0
    exec_timeouts: int = 0
    first_text_checked: bool = False
    # (arm, phase) logs that already carry the NOTHINK marker. lever_check.py reads markers per server_<ARM>_* log, so a
    # once-per-job marker left every later arm of the same job LEVER_VOID (integration finding, 2026-11-04).
    think_checked: set = field(default_factory=set)
    # (arm, phase) logs that already carry the LEVER INSTRUCTION marker (same per-log rule as NOTHINK)
    instruction_logged: set = field(default_factory=set)


def counters(run: Run) -> JobCounters:
    return run.cache.setdefault('counters', JobCounters())


def _usage_int(usage: dict, *path) -> int:
    v: Any = usage or {}
    for p in path:
        if not isinstance(v, dict):
            return 0
        v = v.get(p)
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def build_prompt(run: Run, spec: ReqSpec):
    kit = kit_of(run)
    _name, text, _sha = run_instruction(run)
    if spec.inline_library is not None:
        return kit.prompt.build_messages(spec.task, kit.tok, library=spec.library, inline_library=spec.inline_library,
                                         cap_tokens=run.cap, instruction=text)
    return kit.prompt.build_messages(spec.task, kit.tok, library=spec.library, exemplars=spec.exemplars,
                                     inline_noncallable=spec.inline, cap_tokens=run.cap, instruction=text)


def _check_pilot_only(run: Run, spec: ReqSpec) -> None:
    """A PLANT_SOLVE (pilot-only) library may only reach a pilot-phase prompt on a pilot (growth) task."""
    from .library import is_pilot_only
    for lib in (spec.library, spec.inline_library):
        if lib is not None and is_pilot_only(lib):
            split = getattr(spec.task, 'split', None)
            if spec.phase != 'pilot' or split not in ('pilot', 'growth'):
                raise ArmError('PILOT_ONLY_LIBRARY_REFUSED %s in phase %s on split %s (%s)' % (
                    getattr(lib, 'arm', '?'), spec.phase, split, spec.request_id))
    if spec.exemplars:
        for e in spec.exemplars:
            sid = str(getattr(e, 'sample_id', '') or (e.get('sample_id') if isinstance(e, dict) else ''))
            if sid.split('|')[0] == config.PLANT_SOLVE_ARM or '|pilot|' in sid:
                raise ArmError('PILOT_ONLY_EXEMPLAR_REFUSED %s (%s)' % (sid, spec.request_id))


def lever_adapter(run: Run, pending: Sequence[ReqSpec], builds: dict, log_arm: str, log_phase: str,
                  log_round=None) -> None:
    """PLANT_FAIL_DIAGNOSIS 4.3: before any model call, every callable library going into context is checked through
    the sandbox's type adapter on one list-of-lists demo grid of the job's own split (the spec task's first demo input).
    Prints one LEVER ADAPTER line per distinct library source per job and refuses (ArmError) if any grid-typed helper
    raises on the list grid where its tuple call does not, or returns a different value."""
    from . import adapter as _ad
    kit = kit_of(run)
    checked = run.cache.setdefault('adapter_checked', {})
    for s in pending:
        if s.library is None or s.inline:
            continue
        names = list(getattr(builds[s.request_id], 'helpers_in_context', ()) or ())
        if not names:
            continue
        src = library_src(run, s.library, names)
        key = (hashlib.sha256(src.encode('utf-8')).hexdigest(), log_arm, log_phase)
        if key in checked:
            continue
        n_grid = len(_ad.grid_helpers(src))
        if n_grid == 0:
            res = {'grid_helpers': 0, 'list_smoke_ok': 0, 'ok': True, 'refused': [], 'status': 'NO_GRID_HELPERS'}
        else:
            fn = getattr(kit.sandbox, 'adapter_smoke', None)
            if fn is None:
                raise ArmError('LEVER_ADAPTER_REFUSED the sandbox has no adapter_smoke but the library has %d '
                               'grid-typed helpers' % n_grid)
            grid = s.task.train[0].input
            res = fn(src, grid)
        checked[key] = res
        emit(run, log_arm, log_phase, _ad.lever_line(int(res['grid_helpers']), int(res['list_smoke_ok']),
                                                     lib=key[0][:16], task=s.task.id, ok=int(bool(res['ok']))),
             log_round)
        if not res['ok']:
            raise ArmError('LEVER_ADAPTER_REFUSED lib=%s task=%s status=%s error=%s refused=%s' % (
                key[0][:16], s.task.id, res.get('status'), res.get('error'), ','.join(res.get('refused') or [])[:400]))


def sample(run: Run, specs: Sequence[ReqSpec], samples_path: Path, client, deadline: Deadline,
           log_arm: str, log_phase: str, log_round=None) -> bool:
    """Issue every spec whose samples are not all present. True when every spec is done."""
    kit = kit_of(run)
    repair_jsonl(samples_path)
    have = set(read_rows(samples_path, 'sample_id'))
    pending = [s for s in specs if not all(i in have for i in s.sample_ids)]
    if not pending:
        return True
    if client is None or not deadline.issue_ok():
        return False
    _iname, _itext, isha = run_instruction(run)   # refuses before any model call
    by_id = {s.request_id: s for s in pending}
    builds: dict[str, Any] = {}
    reqs = []
    for s in pending:
        _check_pilot_only(run, s)
        builds[s.request_id] = build_prompt(run, s)
    c0 = counters(run)
    if (log_arm, log_phase) not in c0.instruction_logged:
        c0.instruction_logged.add((log_arm, log_phase))
        emit(run, log_arm, log_phase, lever_instruction_line(run), log_round)
    lever_adapter(run, pending, builds, log_arm, log_phase, log_round)
    for s in pending:
        pb = builds[s.request_id]
        meta = {'run': run.name, 'job_id': run.job_id, 'arm': s.arm, 'phase': s.phase, 'round': s.round,
                'sealed_seed': s.sealed_seed, 'task': s.task.id, 'n': len(s.slots), 'seed': s.seed,
                'library_tokens': int(getattr(pb, 'library_tokens', 0)),
                'exemplar_tokens': int(getattr(pb, 'exemplar_tokens', 0)),
                'task_tokens': int(getattr(pb, 'task_tokens', 0)),
                'instruction_tokens': int(getattr(pb, 'instruction_tokens', 0)),
                'lib_sha': getattr(pb, 'lib_sha', None), 'model_sha': model_sha(run),
                'sampling': dict(config.SAMPLING)}
        meta.update(s.meta_extra)
        reqs.append(kit.llm.GenRequest(request_id=s.request_id, messages=pb.messages, n=len(s.slots), seed=s.seed,
                                       meta=meta))
    lock = threading.Lock()
    c = counters(run)

    def on_result(res) -> None:
        s = by_id[res.request_id]
        pb = builds[res.request_id]
        texts = list(res.texts)
        if len(texts) != len(s.slots):
            raise ArmError('request %s returned %d texts for n=%d' % (res.request_id, len(texts), len(s.slots)))
        rows = []
        for i, (slot, sid, text) in enumerate(zip(s.slots, s.sample_ids, texts)):
            code = kit.extract.extract_code(text)
            fr = res.finish_reasons[i] if i < len(res.finish_reasons) else None
            rows.append({'sample_id': sid, 'request_id': s.request_id, 'arm': s.arm, 'phase': s.phase,
                         'round': s.round, 'sealed_seed': s.sealed_seed, 'task': s.task.id, 'seed_idx': slot,
                         'text': text, 'code': code,
                         'code_sha': hashlib.sha256(code.encode('utf-8')).hexdigest() if code is not None else None,
                         'finish_reason': fr, 'gen_tokens': int(kit.tok.count(text)),
                         'lib_sha': getattr(pb, 'lib_sha', None),
                         'helpers_in_context': list(getattr(pb, 'helpers_in_context', ()) or ()),
                         'helpers_inline': list(getattr(pb, 'helpers_inline', ()) or ()),
                         'exemplar_ids': list(getattr(pb, 'exemplar_ids', ()) or ()),
                         'inline': bool(s.inline), 'job_id': run.job_id, 'instruction_sha': isha})
        with lock:
            append_jsonl(samples_path, rows)
            u = res.usage or {}
            c.requests += 1
            c.prompt += _usage_int(u, 'prompt_tokens')
            c.prompt_logical += _usage_int(u, 'prompt_tokens') * len(s.slots)
            c.cached += _usage_int(u, 'prompt_tokens_details', 'cached_tokens')
            c.gen += _usage_int(u, 'completion_tokens')
            if (log_arm, log_phase) not in c.think_checked and texts:
                c.think_checked.add((log_arm, log_phase))
                c.first_text_checked = True
                emit(run, log_arm, log_phase, 'LEVER NOTHINK first_response_has_think=%d' % int('<think>' in texts[0]),
                     log_round)

    t0 = time.time()
    try:
        out = client.run(reqs, on_result, deadline.stop_issue_ts, deadline.hard_ts)
    finally:
        c.sampling_s += time.time() - t0
    have = set(read_rows(samples_path, 'sample_id'))
    complete = all(all(i in have for i in s.sample_ids) for s in specs)
    if not complete:
        summary = {k: v for k, v in (out or {}).items() if k != 'error_ids'} if isinstance(out, dict) else out
        errs = (out or {}).get('error_ids', []) if isinstance(out, dict) else []
        print('SAMPLE_INCOMPLETE %s run=%s errors=%s' % (samples_path, summary, errs[:5]), flush=True)
    return complete


# ---------------------------------------------------------------------------------------------------------------------
# Execution core

def _row_of(res) -> dict:
    if hasattr(res, 'to_row'):
        return res.to_row()
    if is_dataclass(res):
        return asdict(res)
    return dict(res)


def _grid(g) -> tuple:
    return tuple(tuple(int(v) for v in r) for r in g)


def _outputs_equal(got, want) -> bool:
    if got is None or want is None or len(got) != len(want):
        return False
    return all(_grid(a) == _grid(b) for a, b in zip(got, want))


def library_src(run: Run, lib, names: Sequence[str]) -> str:
    if lib is None or not names:
        return ''
    key = ('libsrc', id(lib), tuple(names))
    hit = run.cache.get(key)
    if hit is None or hit[0] is not lib:       # hold the object so its id cannot be reused by another library
        hit = (lib, kit_of(run).library.render_py(lib, list(names)))
        run.cache[key] = hit
    return hit[1]


def execute(run: Run, samples_path: Path, exec_path: Path, task_by_id: dict, lib_for: Callable[[dict], Any],
            mode: str, deadline: Deadline, public_outputs: bool) -> bool:
    """Execute every sample without an exec row. lib_for(sample_row) -> Library or None (callable helpers).
    public_outputs: the tasks' test outputs are public (growth, pilot): add test_correct."""
    kit = kit_of(run)
    repair_jsonl(exec_path)
    samples = read_rows(samples_path, 'sample_id')
    done = set(read_rows(exec_path, 'sample_id'))
    pending = [samples[k] for k in sorted(samples) if k not in done]
    if not pending:
        return True
    c = counters(run)
    batch = int(run.cfg.get('exec_batch', config.EXEC_BATCH))
    workers = int(run.cfg.get('exec_workers', config.EXEC_WORKERS))
    for i in range(0, len(pending), batch):
        if deadline.hard():
            return False
        chunk = pending[i:i + batch]
        rows_out: list[dict] = []
        jobs, job_rows = [], []
        for srow in chunk:
            if not srow.get('code'):
                rows_out.append({'sample_id': srow['sample_id'], 'code_sha': None, 'status': 'NO_CODE',
                                 'demo_pass': False, 'n_demo_pass': 0, 'n_demos': len(task_by_id[srow['task']].train),
                                 'first_fail_demo': None, 'test_outputs': None, 'helper_calls': {}, 'static_refs': [],
                                 'wall_s': [], 'timeouts': 0, 'exec_mode': mode, 'cache_hit': False})
                continue
            lib = None if mode == 'inline' else lib_for(srow)
            src = library_src(run, lib, srow.get('helpers_in_context') or [])
            jobs.append(kit.sandbox.ExecJob(sample_id=srow['sample_id'], task=task_by_id[srow['task']],
                                            code=srow['code'], library_src=src, mode=mode))
            job_rows.append(srow)
        t0 = time.time()
        if jobs:
            results = list(kit.sandbox.run_batch(jobs, workers))
            by_sid = {}
            for j, res in zip(jobs, results):
                row = _row_of(res)
                row.setdefault('sample_id', j.sample_id)
                by_sid[row['sample_id']] = row
            for srow in job_rows:
                row = by_sid.get(srow['sample_id'])
                if row is None:
                    raise ArmError('sandbox returned no result for %s' % srow['sample_id'])
                rows_out.append(row)
        c.exec_s += time.time() - t0
        for row in rows_out:
            row['exec_mode'] = row.get('exec_mode') or mode
            c.exec_runs += 1
            c.exec_timeouts += int(row.get('timeouts') or 0)
            if public_outputs:
                t = task_by_id[samples[row['sample_id']]['task']]
                row['test_correct'] = bool(row.get('demo_pass')) and _outputs_equal(row.get('test_outputs'),
                                                                                    t.test_outputs)
            else:
                row.pop('test_correct', None)
        rows_out.sort(key=lambda r: r['sample_id'])
        append_jsonl(exec_path, rows_out)
    return True


def round_counts(samples_path: Path, exec_path: Path) -> dict:
    samples = read_rows(samples_path, 'sample_id')
    ex = read_rows(exec_path, 'sample_id')
    demo_tasks, test_tasks = set(), set()
    for sid, row in ex.items():
        t = samples.get(sid, {}).get('task')
        if row.get('demo_pass'):
            demo_tasks.add(t)
        if row.get('test_correct'):
            test_tasks.add(t)
    return {'samples_done': len(samples), 'exec_done': len(ex), 'demo_pass_tasks': len(demo_tasks),
            'test_correct_tasks': len(test_tasks)}


# ---------------------------------------------------------------------------------------------------------------------
# Libraries

def load_library(run: Run, path: Path):
    path = Path(path)
    if not path.is_absolute():
        path = Path(run.dir) / path
    key = ('lib', str(path))
    if key not in run.cache:
        run.cache[key] = kit_of(run).library.load(path)
    return run.cache[key]


def rel(run: Run, p: Path) -> str:
    return Path(p).resolve().relative_to(Path(run.dir).resolve()).as_posix()


def round_library(run: Run, arm: str, r: int):
    """Library out of a FROZEN round (STOCK r, ONESHOT 1); STATIC r -> STOCK L_1."""
    if arm == 'STATIC':
        arm, r = 'STOCK', 1
    st = load_state(rounds.round_dir(run, arm, r))
    if st.get('state') != 'FROZEN' or not st.get('library_json'):
        raise ArmError('%s round %d has no frozen library' % (arm, r))
    return load_library(run, st['library_json'])


def round_library_sha(run: Run, arm: str, r: int) -> str | None:
    if arm == 'STATIC':
        arm, r = 'STOCK', 1
    return load_state(rounds.round_dir(run, arm, r)).get('library_out')


def _in_context(lib) -> list:
    return [h for h in lib.helpers if getattr(h, 'in_context', False)]


def ctx_hashes(lib) -> frozenset:
    """Canonical hashes of the helpers a library puts in context (what the prompt actually shows)."""
    return frozenset(getattr(h, 'hash', None) or h.name for h in _in_context(lib)) if lib is not None else frozenset()


def stock_updated(run: Run, lib) -> int:
    """1 iff `lib` puts in context a helper set that differs from L_1's and is non-empty (SPEC 9 STOCK marker).
    Review fix 2026-11-04: the marker compared library sha values, which always differ between rounds (the round number
    is part of the sha), so updated=1 printed even when no round after 1 accepted anything."""
    try:
        l1 = round_library(run, 'STOCK', 1)
    except ArmError:
        return 0
    h = ctx_hashes(lib)
    return int(bool(h) and h != ctx_hashes(l1))


def _deterministic_meta(lib, created_et: str | None) -> None:
    if created_et:
        lib.meta['created_et'] = created_et


# ---------------------------------------------------------------------------------------------------------------------
# Growth

def _require_frozen(run: Run, arm: str, r: int) -> dict:
    st = load_state(rounds.round_dir(run, arm, r))
    if st.get('state') != 'FROZEN':
        raise ArmError('%s round %d is not FROZEN (state %s)' % (arm, r, st.get('state')))
    return st


def _growth_specs(run: Run, arm: str, r: int, tasks: Sequence, library=None, exemplars_for=None) -> list[ReqSpec]:
    S, R = run.S, run.R
    out = []
    for t in tasks:
        batches = range(1, R) if arm == 'ONESHOT' else [0]
        for b in batches:
            first = b * S
            slots = list(range(first, first + S))
            seed = seed_for(run, 'growth', r, t.id, first, None)
            out.append(ReqSpec(request_id='%s|growth|r%d|%s|b%d' % (arm, r, t.id, b), task=t, arm=arm, phase='growth',
                               round=r, sealed_seed=None, slots=slots,
                               sample_ids=['%s|growth|r%d|%s|s%d' % (arm, r, t.id, i) for i in slots], seed=seed,
                               library=library, exemplars=exemplars_for(t) if exemplars_for else None))
    return out


def _copy_rows(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in ('samples.jsonl', 'exec.jsonl'):
        src = src_dir / name
        if src.exists():
            rounds.atomic_write_bytes(dst_dir / name, src.read_bytes())


def _share_round1(run: Run, arm: str) -> str:
    """STATIC and EXEMPLAR round 1 = STOCK round 1 (SPEC 13 I3): copy the rows, point at STOCK's L_1."""
    src = _require_frozen(run, 'STOCK', 1)
    d = rounds.round_dir(run, arm, 1)
    _copy_rows(rounds.round_dir(run, 'STOCK', 1), d)
    st = {k: src.get(k) for k in ('requests_total', 'requests_done', 'samples_done', 'exec_done', 'demo_pass_tasks',
                                  'test_correct_tasks', 'library_json', 'library_py', 'library_out')}
    if arm == 'EXEMPLAR':
        st['library_json'] = st['library_py'] = st['library_out'] = None
    st.update({'arm': arm, 'round': 1, 'state': 'FROZEN', 'library_in': None, 'shared_from': 'STOCK:1',
               'started_et': src.get('started_et'), 'jobs': [run.job_id]})
    save_state(d, st)
    return 'FROZEN'


def exemplar_pool(run: Run, upto_round: int) -> list:
    kit = kit_of(run)
    tasks = {t.id: t for t in tasks_of(run, 'growth')}
    pool = kit.exemplar.pool_from_rounds(Path(run.dir), 'EXEMPLAR', upto_round, tasks=tasks, tok=kit.tok)
    return sorted(pool, key=lambda e: (e.task, e.sample_id))


def exemplar_scaler(run: Run):
    if 'scaler' not in run.cache:
        kit = kit_of(run)
        run.cache['scaler'] = kit.exemplar.Scaler.fit(tasks_of(run, 'growth'))
    return run.cache['scaler']


def grow_round(run: Run, arm: str, r: int, client, deadline: Deadline) -> str:
    if arm not in config.GROWTH_SAMPLING_ARMS:
        raise ArmError('%s does no growth sampling (SPEC 13 I5)' % arm)
    if arm == 'ONESHOT' and r != 1:
        raise ArmError('ONESHOT has one round')
    if r < 1 or r > run.R:
        raise ArmError('round %d outside 1..%d' % (r, run.R))
    d = rounds.round_dir(run, arm, r)
    st = load_state(d)
    if st.get('state') == 'FROZEN':
        return 'FROZEN'
    if r == 1 and arm in config.SHARED_ROUND1_ARMS:
        return _share_round1(run, arm)
    tasks = tasks_of(run, 'growth')
    library, exemplars_for, lib_in = None, None, None
    if arm == 'STOCK' and r >= 2:
        _require_frozen(run, 'STOCK', r - 1)
        library, lib_in = round_library(run, 'STOCK', r - 1), round_library_sha(run, 'STOCK', r - 1)
    elif arm == 'STATIC':
        _require_frozen(run, 'STATIC', r - 1)
        library, lib_in = round_library(run, 'STOCK', 1), round_library_sha(run, 'STOCK', 1)
    elif arm == 'EXEMPLAR':
        _require_frozen(run, 'EXEMPLAR', r - 1)
        pool = exemplar_pool(run, r - 1)
        scaler = exemplar_scaler(run)
        kit = kit_of(run)

        def exemplars_for(t):  # SPEC 13 I17: a task never sees its own programs
            return kit.exemplar.neighbours(t, pool, scaler, k=config.EXEMPLAR_K, exclude_task=t.id)
    elif arm == 'ONESHOT':
        _require_frozen(run, 'STOCK', 1)
    specs = _growth_specs(run, arm, r, tasks, library, exemplars_for)
    if not st:
        st = {'arm': arm, 'round': r, 'state': 'PENDING', 'library_in': lib_in, 'library_out': None,
              'requests_total': len(specs), 'requests_done': 0, 'samples_done': 0, 'exec_done': 0,
              'demo_pass_tasks': 0, 'test_correct_tasks': 0, 'shared_from': None, 'started_et': now_et(), 'jobs': []}
    if arm == 'ONESHOT' and not st.get('shared_copied'):
        _copy_rows(rounds.round_dir(run, 'STOCK', 1), d)      # slots 0..S-1 come from STOCK round 1
        st['shared_from'] = 'STOCK:1 slots 0..%d' % (run.S - 1)
        st['shared_copied'] = True
    if run.job_id not in st['jobs']:
        st['jobs'].append(run.job_id)
    samples_path, exec_path = d / 'samples.jsonl', d / 'exec.jsonl'
    if st['state'] in ('PENDING', 'SAMPLING'):
        st['state'] = 'SAMPLING'
        save_state(d, st)
        n_ctx = len(_in_context(library)) if library is not None else 0
        if arm == 'STOCK' and r >= 2:
            # r = 2 always prints updated=0: L_{r-1} = L_1 there by construction (SPEC 9 note)
            emit(run, arm, 'growth', 'LEVER STOCK library r=%d sha=%s updated=%d helpers_in_context=%d' % (
                r, lib_in, stock_updated(run, library), n_ctx), r)
        elif arm == 'STATIC':
            emit(run, arm, 'growth', 'LEVER STATIC library r=%d sha=%s frozen=1' % (r, lib_in), r)
        elif arm == 'ONESHOT':
            emit(run, arm, 'growth', 'LEVER ONESHOT round=1 slots_per_task=%d' % (run.R * run.S), r)
        elif arm == 'EXEMPLAR':
            for s in specs:
                ex = s.exemplars or []
                pb = build_prompt(run, s)
                emit(run, arm, 'growth', 'LEVER EXEMPLAR task=%s k=%d exemplar_tokens=%d' % (
                    s.task.id, len(ex), int(getattr(pb, 'exemplar_tokens', 0))), r)
        lever_sandbox(run, arm, 'growth', lib_in, n_ctx, r)
        ok = sample(run, specs, samples_path, client, deadline, arm, 'growth', r)
        st.update(round_counts(samples_path, exec_path))
        have = set(read_rows(samples_path, 'sample_id'))
        st['requests_done'] = sum(1 for s in specs if all(i in have for i in s.sample_ids))
        if client is not None and ok:
            lever_prefix(run, arm, 'growth', client, r)
        if not ok:
            save_state(d, st)
            return 'SAMPLING'
        st['state'] = 'EXECUTING'
        save_state(d, st)
    if st['state'] == 'EXECUTING':
        lib_for = (lambda row: library) if library is not None else (lambda row: None)
        ok = execute(run, samples_path, exec_path, {t.id: t for t in tasks}, lib_for, 'callable', deadline, True)
        st.update(round_counts(samples_path, exec_path))
        if not ok:
            save_state(d, st)
            return 'EXECUTING'
        st['state'] = 'EXTRACTING'
        save_state(d, st)
    if deadline.hard():
        return st['state']
    finalize_round(run, arm, r, kit_of(run).tok)
    return 'FROZEN'


def _check_growth_rows(run: Run, samples: dict) -> None:
    gids = set(growth_ids(run))
    for sid, row in samples.items():
        if row.get('phase') != 'growth' or row.get('task') not in gids or row.get('sealed_seed') is not None:
            raise SealedHelperRefused('non-growth sample %s (phase %s task %s) reached a library build' % (
                sid, row.get('phase'), row.get('task')))


def round_solutions(run: Run, d: Path, library) -> list:
    """Demo-passing growth solutions of a round, sorted by sample_id (order-independent of how rows were written)."""
    kit = kit_of(run)
    samples = read_rows(d / 'samples.jsonl', 'sample_id')
    _check_growth_rows(run, samples)
    ex = read_rows(d / 'exec.jsonl', 'sample_id')
    if library is not None and hasattr(library, 'hashes'):
        names = library.hashes()
    else:
        names = frozenset(h.name for h in getattr(library, 'helpers', []) or [])
    sols = []
    for sid in sorted(ex):
        row = ex[sid]
        # PREREG 4: helpers come from demo-passing programs; how a program fares on the growth test input does not
        # matter for acceptance (review fix 2026-11-04: status OK was also required, which dropped demo-passing
        # programs that errored or timed out on a test input)
        if not row.get('demo_pass'):
            continue
        srow = samples[sid]
        sol = kit.helpers.build_solution(sid, srow['task'], srow['code'], names, demo_pass=True,
                                         code_sha=srow.get('code_sha'))
        if sol is not None:
            sols.append(sol)
    return sols


def finalize_round(run: Run, arm: str, r: int, tok) -> str:
    """EXTRACTING -> FROZEN, a pure function of the round's rows. Returns the library (or pool) sha."""
    kit = kit_of(run)
    d = rounds.round_dir(run, arm, r)
    st = load_state(d)
    if st.get('state') == 'FROZEN':
        return st.get('library_out')
    if st.get('state') != 'EXTRACTING':
        raise ArmError('%s round %d is %s, not EXTRACTING' % (arm, r, st.get('state')))
    samples = read_rows(d / 'samples.jsonl', 'sample_id')
    _check_growth_rows(run, samples)
    out_sha = None
    if arm in ('STOCK', 'ONESHOT'):
        prev = round_library(run, 'STOCK', r - 1) if (arm == 'STOCK' and r >= 2) else kit.library.empty(arm)
        sols = kit.helpers.dedup_solutions(round_solutions(run, d, prev))
        accepted = kit.helpers.accept(sols, prev, tok)
        lib = kit.library.merge(prev, accepted, r, sols)
        _deterministic_meta(lib, st.get('started_et'))
        stem = 'L_one' if arm == 'ONESHOT' else 'L_%d' % r
        jp, pp, out_sha = kit.library.save(lib, d, run.cap, tok, stem=stem)
        st.update({'library_json': rel(run, jp), 'library_py': rel(run, pp), 'library_out': out_sha,
                   'n_helpers': len(lib.helpers), 'n_accepted': len(accepted), 'n_solutions': len(sols),
                   'n_in_context': len(_in_context(lib))})
    elif arm == 'STATIC':
        out_sha = round_library_sha(run, 'STOCK', 1)
        st.update({'library_json': load_state(rounds.round_dir(run, 'STOCK', 1)).get('library_json'),
                   'library_out': out_sha})
    elif arm == 'EXEMPLAR':
        if r == run.R:
            pool = exemplar_pool(run, r)
            p = rounds.arm_dir(run, 'EXEMPLAR') / 'pool_R.json'
            body = {'schema': 'ratchet.exemplar_pool.v1', 'round': r, 'n': len(pool),
                    'exemplars': [asdict(e) for e in pool]}
            atomic_write_json(p, body)
            out_sha = hashlib.sha256(p.read_bytes()).hexdigest()
            st.update({'library_json': rel(run, p), 'library_out': out_sha, 'n_exemplars': len(pool)})
    else:
        raise ArmError('no growth finalize for %s' % arm)
    st.update(round_counts(d / 'samples.jsonl', d / 'exec.jsonl'))
    st['state'] = 'FROZEN'
    save_state(d, st)
    return out_sha


# ---------------------------------------------------------------------------------------------------------------------
# SHAM and PLANT builds (no sampling, SPEC 13 I5, I6)

SHAM_FALLBACK_ARMS = ('EXEMPLAR', 'ONESHOT', 'STATIC')


def _shuffled_pool(run: Run) -> list:
    """Fallback SHAM pool when STOCK's failed pool matches < 95% of slots: helpers of the OTHER growth arms' programs
    that FAILED their demos (EXEMPLAR, ONESHOT, and STATIC rounds already sampled), still never a helper any accepted
    library holds. Review fix 2026-11-04: the old fallback took helpers of STOCK's demo-PASSING programs, which is
    verified code, while PREREG 4 defines SHAM as code "that failed its demos or came from shuffled tasks". Every
    program here failed its demos; no extra sampling. Deterministic at its PLAN position (STATIC rounds 2..R run after
    the SHAM build, so they are not on disk yet)."""
    kit = kit_of(run)
    out = []
    for arm in SHAM_FALLBACK_ARMS:
        out.extend(kit.sham.failed_pool(Path(run.dir), arm))
    return out


def build_sham_arm(run: Run) -> str:
    kit = kit_of(run)
    d = rounds.arm_dir(run, 'SHAM')
    st = load_state(d)
    if st.get('state') == 'DONE':
        return st['library_out']
    target = round_library(run, 'STOCK', run.R)
    tgt_ctx = _in_context(target)
    tgt_tokens = int(target.meta.get('in_context_tokens') or sum(int(h.token_len) for h in tgt_ctx))
    seed = int(run.cfg.get('sham_seed', config.SHAM_SEED))
    failed = kit.sham.failed_pool(Path(run.dir))
    # no SHAM helper may be a helper any accepted library of the run holds
    exclude = set()
    for r in range(1, run.R + 1):
        exclude |= {h.hash for h in round_library(run, 'STOCK', r).helpers}
    exclude |= {h.hash for h in round_library(run, 'ONESHOT', 1).helpers}
    used_shuffled = False
    try:
        lib = kit.sham.build_sham(target, failed, None, kit.tok, seed, cap_tokens=run.cap,
                                  exclude_hashes=sorted(exclude))
        need = bool(lib.meta.get('needs_shuffled')) or len(lib.helpers) < config.SHAM_SHUFFLE_TRIGGER * len(tgt_ctx)
    except Exception as e:  # noqa: BLE001 - sham.ShamMatchFailed: the failed pool alone cannot match
        print('SHAM failed pool alone: %s: %s' % (type(e).__name__, e), flush=True)
        need = True
    if need:
        try:
            lib = kit.sham.build_sham(target, failed, _shuffled_pool(run), kit.tok, seed, cap_tokens=run.cap,
                                      exclude_hashes=sorted(exclude))
        except Exception as e:  # noqa: BLE001 - no registered SHAM fallback: stop loudly for the lead
            save_state(d, {'arm': 'SHAM', 'round': None, 'state': 'FAILED', 'error': '%s: %s' % (type(e).__name__, e),
                           'target_n': len(tgt_ctx), 'target_tokens': tgt_tokens, 'failed_pool': len(failed),
                           'jobs': [run.job_id]})
            emit(run, 'SHAM', 'build', 'SHAM_BUILD_FAILED %s: %s' % (type(e).__name__, e))
            raise
        used_shuffled = True
    _deterministic_meta(lib, load_state(rounds.round_dir(run, 'STOCK', run.R)).get('started_et'))
    jp, pp, s = kit.library.save(lib, d, run.cap, kit.tok, stem='L_sham')
    saved = kit.library.load(jp)
    ctx = _in_context(saved)
    toks = int(saved.meta.get('in_context_tokens') or sum(int(h.token_len) for h in ctx))
    matched = int(saved.meta.get('matched', len(ctx)))      # sham.py: slots filled by an exact-genre helper
    tiers = {}
    for h in saved.helpers:
        t = int((getattr(h, 'provenance', None) or {}).get('genre_tier') or 0)
        tiers[t] = tiers.get(t, 0) + 1
    emit(run, 'SHAM', 'build', 'LEVER SHAM matched=%d of %d tokens=%d target=%d verified=%d in_context=%d '
         'tier2=%d fallback_pool=%d' % (
             matched, len(tgt_ctx), toks, tgt_tokens, int(any(getattr(h, 'verified', False) for h in saved.helpers)),
             len(ctx), tiers.get(2, 0), int(used_shuffled)))
    save_state(d, {'arm': 'SHAM', 'round': None, 'state': 'DONE', 'library_json': rel(run, jp),
                   'library_py': rel(run, pp), 'library_out': s, 'matched': len(ctx), 'target_n': len(tgt_ctx),
                   'tokens': toks, 'target_tokens': tgt_tokens, 'used_shuffled_pool': used_shuffled,
                   'started_et': now_et(), 'jobs': [run.job_id]})
    return s


def arcdsl_dir(run: Run) -> Path:
    return Path(run.cfg.get('arcdsl_dir') or (config.DATA_DIR / 'raw' / 'arc-dsl'))


def _plant_tranches(run: Run, R: int) -> list:
    kit = kit_of(run)
    src = kit.plant.load_arcdsl(arcdsl_dir(run))
    return kit.plant.build_tranches(src, R, run.cap, kit.tok)


def build_plant_arm(run: Run) -> str:
    kit = kit_of(run)
    d = rounds.arm_dir(run, 'PLANTDRIP')
    st = load_state(d)
    if st.get('state') == 'DONE':
        return st['library_out']
    libs = _plant_tranches(run, run.R)
    if len(libs) != run.R:
        raise ArmError('build_tranches returned %d libraries for R=%d' % (len(libs), run.R))
    created = read_json(Path(run.dir) / 'RUN.json', {}).get('created_et')
    tranches = []
    for r, lib in enumerate(libs, 1):
        _deterministic_meta(lib, created)
        jp, pp, s = kit.library.save(lib, d, run.cap, kit.tok, stem='L_plant_%d' % r)
        n = len(_in_context(kit.library.load(jp)))
        tranches.append({'tranche': r, 'library_json': rel(run, jp), 'library_py': rel(run, pp), 'sha': s,
                         'primitives': n})
        emit(run, 'PLANTDRIP', 'build', 'LEVER PLANTDRIP tranche=%d of %d primitives=%d' % (r, run.R, n))
    d1 = rounds.arm_dir(run, 'PLANTL1')
    lib1 = kit.library.load(Path(run.dir) / tranches[0]['library_json'])
    jp1, pp1, s1 = kit.library.save(lib1, d1, run.cap, kit.tok, stem='L_plant_1')
    emit(run, 'PLANTL1', 'build', 'LEVER PLANTL1 tranche=1 primitives=%d' % tranches[0]['primitives'])
    save_state(d1, {'arm': 'PLANTL1', 'round': None, 'state': 'DONE', 'library_json': rel(run, jp1),
                    'library_py': rel(run, pp1), 'library_out': s1, 'jobs': [run.job_id]})
    last = tranches[-1]
    save_state(d, {'arm': 'PLANTDRIP', 'round': None, 'state': 'DONE', 'library_json': last['library_json'],
                   'library_py': last['library_py'], 'library_out': last['sha'], 'tranches': tranches,
                   'jobs': [run.job_id]})
    return last['sha']


# ---------------------------------------------------------------------------------------------------------------------
# Pilot (PREREG 7; growth tasks only)

def pilot_base(which: str) -> str:
    """Logical arm of a physical pilot dir: V1_FLAT_A -> FLAT_A."""
    return which[len(config.PILOT_V1_PREFIX):] if which.startswith(config.PILOT_V1_PREFIX) else which


def pilot_expected_instruction(which: str) -> str:
    return 'V1' if which.startswith(config.PILOT_V1_PREFIX) else config.INSTRUCTION_DEFAULT_RUN


def flat_a_mean_gen(run: Run) -> dict:
    """g = mean generated tokens per sample of the F3 FLAT_A pilot round (samples.jsonl gen_tokens, the model's own
    tokenizer count; the same definition that gives v1 FLAT_A 1,451,835 tokens over 400 samples)."""
    d = rounds.pilot_dir(run, 'FLAT_A')
    if (load_state(d) or {}).get('state') != 'DONE':
        raise ArmError('SCREEN_NEEDS_FLAT_A: pilot/FLAT_A is not DONE')
    rows = list(read_rows(d / 'samples.jsonl', 'sample_id').values())
    if not rows:
        raise ArmError('SCREEN_NEEDS_FLAT_A: pilot/FLAT_A has no samples')
    tot = sum(int(r.get('gen_tokens') or 0) for r in rows)
    return {'g': tot / len(rows), 'gen_tokens': tot, 'samples': len(rows)}


def screen_S(run: Run, n_tasks: int) -> dict:
    """S_screen = round(SCREEN_GEN_BUDGET / (n_tasks x g)), g = F3 FLAT_A mean gen tokens per sample (VERDICT 3.5)."""
    m = flat_a_mean_gen(run)
    budget = int(config.SCREEN_GEN_BUDGET)
    g = float(m['g'])
    S = int(round(budget / (n_tasks * g))) if g > 0 else 0
    return {'S_screen': max(1, S), 'g_flat_a': g, 'budget': budget, 'n_tasks': n_tasks,
            'flat_a_gen_tokens': m['gen_tokens'], 'flat_a_samples': m['samples']}


def plant_solve_libraries(run: Run, d: Path, tasks: Sequence) -> dict:
    """Per pilot task: L_solve_<task>.json under pilot/<which>/libs (built once, then loaded and hash-checked). Refuses
    (ArmError) if any closure's rendered callable block exceeds the cap or is not wholly in context."""
    kit = kit_of(run)
    ld = d / 'libs'
    src = None
    out, info = {}, {}
    for t in tasks:
        jp = ld / ('L_solve_%s.json' % t.id)
        if not jp.exists():
            if src is None:
                src = kit.plant.load_arcdsl(arcdsl_dir(run))
            lib = kit.plant.solver_library(src, t.id, kit.tok)
            _deterministic_meta(lib, read_json(Path(run.dir) / 'RUN.json', {}).get('created_et'))
            _text, _names, full_tok = kit.prompt.library_block(lib, 10 ** 9, kit.tok)
            if full_tok > run.cap:
                raise ArmError('PLANT_SOLVE_CAP_REFUSED task=%s closure=%d helpers block_tokens=%d cap=%d' % (
                    t.id, len(lib.helpers), full_tok, run.cap))
            kit.library.save(lib, ld, run.cap, kit.tok, stem='L_solve_%s' % t.id)
        lib = load_library(run, jp)
        names = [h.name for h in lib.helpers if h.in_context]
        if set(names) != {h.name for h in lib.helpers} or config.PLANT_SOLVE_NAME not in names:
            raise ArmError('PLANT_SOLVE_CAP_REFUSED task=%s in_context=%d of %d helpers' % (
                t.id, len(names), len(lib.helpers)))
        out[t.id] = lib
        info[t.id] = {'helpers': len(lib.helpers), 'tokens': int(lib.meta.get('in_context_tokens') or 0),
                      'sha': kit.library.sha(lib)}
    return {'libs': out, 'info': info}


def run_pilot_round(run: Run, which: str, client, deadline: Deadline) -> None:
    """One pilot round (PREREG 7 as amended; harness v2). `which` is a physical pilot dir (config.PILOT_PHYSICAL):
    FLAT_A, FLAT_B, PLANT1, PLANT_SOLVE (S = 8), the screen FLAT_S (S = S_screen, F3 only) and the V1_* fallback
    re-runs. Every round runs under the run's recorded instruction and refuses one recorded for another instruction."""
    if which not in config.PILOT_PHYSICAL:
        raise ArmError('pilot round %r not in %s' % (which, config.PILOT_PHYSICAL))
    kit = kit_of(run)
    d = rounds.pilot_dir(run, which)
    st = load_state(d)
    if st.get('state') == 'DONE':
        return
    iname, _itext, isha = run_instruction(run)
    want = pilot_expected_instruction(which)
    if run.cfg.get('skip_pilot') and not which.startswith(config.PILOT_V1_PREFIX):
        rounds.check_test_switches(run)   # a test run (refused in production) may drive FLAT_A / FLAT_B under V1
        want = iname
    if iname != want:
        raise InstructionRefused('PILOT_INSTRUCTION_REFUSED %s runs under %s but the run records %s' % (
            which, want, iname))
    if st and st.get('instruction_sha') not in (None, isha):
        raise InstructionRefused('PILOT_INSTRUCTION_REFUSED %s was started under sha %s, run now records %s' % (
            which, st.get('instruction_sha'), isha))
    base = pilot_base(which)
    ids = sorted(kit.arc_io.pilot_ids(int(run.cfg.get('pilot_n', config.PILOT_N))))
    tasks = tasks_of(run, 'pilot', ids)
    S = int(run.cfg.get('s_pilot', config.S_PILOT))
    screen = None
    if base == config.PILOT_SCREEN:
        screen = st.get('screen') or screen_S(run, len(tasks))
        S = int(screen['S_screen'])
    library, lib_sha, per_task, ps = None, None, None, None
    if base == 'PLANT1':
        lp = d / 'L_plant_1.json'
        if not lp.exists():
            lib = _plant_tranches(run, int(run.cfg.get('pilot_r', config.PILOT_R)))[0]
            _deterministic_meta(lib, read_json(Path(run.dir) / 'RUN.json', {}).get('created_et'))
            kit.library.save(lib, d, run.cap, kit.tok, stem='L_plant_1')
        library = load_library(run, lp)
        lib_sha = kit.library.sha(library)
    elif base == config.PLANT_SOLVE_ARM:
        ps = plant_solve_libraries(run, d, tasks)
        per_task = ps['libs']
        lib_sha = 'per_task'
    seed_phase = {'FLAT_B': 'pilot:FLAT_B', config.PILOT_SCREEN: 'pilot:FLAT_S'}.get(base, 'pilot:FLAT_A')
    nmax = int(config.SCREEN_MAX_N_PER_REQUEST) if base == config.PILOT_SCREEN else S
    specs = []
    for t in tasks:
        lib_t = per_task[t.id] if per_task is not None else library
        for b, lo in enumerate(range(0, S, nmax)):
            slots = list(range(lo, min(S, lo + nmax)))
            specs.append(ReqSpec(request_id='%s|pilot|r1|%s|b%d' % (which, t.id, b), task=t, arm=which,
                                 phase='pilot', round=1, sealed_seed=None, slots=slots,
                                 sample_ids=['%s|pilot|r1|%s|s%d' % (which, t.id, i) for i in slots],
                                 seed=seed_for(run, seed_phase, 1, t.id, lo, None), library=lib_t))
    if not st:
        st = {'arm': which, 'round': 1, 'state': 'SAMPLING', 'requests_total': len(specs), 'library_out': lib_sha,
              'started_et': now_et(), 'jobs': [], 'S_pilot': S, 'instruction': iname, 'instruction_sha': isha}
        if screen is not None:
            st['screen'] = screen
        if ps is not None:
            st['plant_solve'] = ps['info']
    if run.job_id not in st['jobs']:
        st['jobs'].append(run.job_id)
    save_state(d, st)
    sp, ep = d / 'samples.jsonl', d / 'exec.jsonl'
    if base == 'PLANT1':
        emit(run, which, 'pilot', 'LEVER PLANTL1 tranche=1 primitives=%d' % len(_in_context(library)), 1)
    if ps is not None:
        toks = [v['tokens'] for v in ps['info'].values()]
        emit(run, which, 'pilot', 'LEVER PLANT_SOLVE libraries=%d max_block_tokens=%d cap=%d solver=%s' % (
            len(per_task), max(toks) if toks else 0, run.cap, config.PLANT_SOLVE_NAME), 1)
    if screen is not None:
        emit(run, which, 'pilot', 'LEVER SCREEN S_screen=%d g_flat_a=%.1f budget=%d' % (
            S, float(screen['g_flat_a']), int(screen['budget'])), 1)
    n_ctx = len(_in_context(library)) if library is not None else (
        max(len(_in_context(v)) for v in per_task.values()) if per_task else 0)
    lever_sandbox(run, which, 'pilot', lib_sha, n_ctx, 1)
    if not sample(run, specs, sp, client, deadline, which, 'pilot', 1):
        st.update(round_counts(sp, ep))
        save_state(d, st)
        return
    if client is not None:
        lever_prefix(run, which, 'pilot', client, 1)
    st['state'] = 'EXECUTING'
    save_state(d, st)
    if per_task is not None:
        def lib_for(row):
            return per_task[row['task']]
    else:
        def lib_for(row):
            return library
    ok = execute(run, sp, ep, {t.id: t for t in tasks}, lib_for, 'callable', deadline, True)
    st.update(round_counts(sp, ep))
    st['state'] = 'DONE' if ok else 'EXECUTING'
    save_state(d, st)


def pilot_screen(run: Run) -> Run:
    """VERDICT_AMENDMENT_2 3.4, 3.5: F3 stands iff FLAT_S has >= 23 demo-pass tasks AND >= 22 pass@2 test-correct
    tasks. Writes pilot/SCREEN.json once (never rewritten). On a failed screen the run's instruction becomes V1 at
    max_tokens 4,096 (RUN.json instruction, instruction_sha, instruction_history); the F3 FLAT_A stays on disk."""
    kit = kit_of(run)
    p = Path(run.dir) / 'pilot' / 'SCREEN.json'
    if p.exists():
        return run
    iname, _t, isha = run_instruction(run)
    if iname != config.INSTRUCTION_DEFAULT_RUN:
        raise InstructionRefused('SCREEN_REFUSED the screen runs under %s, run records %s' % (
            config.INSTRUCTION_DEFAULT_RUN, iname))
    res = kit.pilot.screen_decision(Path(run.dir))
    res.update({'created_et': now_et(), 'instruction_screened': iname, 'instruction_screened_sha': isha})
    atomic_write_json(p, res)
    print('PILOT_SCREEN decision=%s demo_pass_tasks=%s pass2_tasks=%s S_screen=%s' % (
        res['decision'], res['demo_pass_tasks'], res['pass2_tasks'], res.get('S_screen')), flush=True)
    if res['decision'] == 'V1':
        hist = list(run.cfg.get('instruction_history') or [])
        hist.append({'instruction': 'V1', 'sha': config.INSTRUCTION_SHAS['V1'], 'et': now_et(),
                     'why': 'F3 screen failed (pilot/SCREEN.json); fallback to the v1 instruction at max_tokens %d'
                            % int(config.MAX_TOKENS)})
        run = update_run(run, instruction='V1', instruction_sha=config.INSTRUCTION_SHAS['V1'],
                         instruction_history=hist)
    print(lever_instruction_line(run), flush=True)
    return run


def pilot_choose(run: Run) -> Run:
    """PREREG 7.1 to 7.3 via pilot.py (E). Writes pilot/PILOT_CHOICE.json, and S, R into RUN.json when feasible;
    otherwise pilot/PILOT_STOP.json (the run stops for an amendment)."""
    kit = kit_of(run)
    pdir = Path(run.dir) / 'pilot'
    if hasattr(kit.pilot, 'run_pilot_rules'):
        rules = kit.pilot.run_pilot_rules(Path(run.dir))
        smoke, plant, choice = rules.get('smoke') or {}, rules.get('plant') or {}, rules.get('choice') or {}
        status = rules.get('status')
    else:
        smoke = kit.pilot.step1_smoke(Path(run.dir))
        plant = kit.pilot.step2_plant(Path(run.dir))
        choice = kit.pilot.choose_SR(kit.pilot.step3_rates(Path(run.dir)))
        status = None
    report = kit.pilot.write_pilot_report(Path(run.dir))
    out = {'smoke': smoke, 'plant': plant, 'choice': choice, 'status': status, 'report': str(report),
           'created_et': now_et()}
    atomic_write_json(pdir / 'PILOT_CHOICE.json', out)
    reason = None
    if not smoke.get('pass'):
        reason = 'PILOT_SMOKE_FAIL'
    elif not plant.get('pass'):
        reason = 'PILOT_PLANT_FAIL'
    elif not (choice.get('S') and choice.get('R')):
        reason = status if status not in (None, 'OK') else (choice.get('status') or 'PILOT_NO_FEASIBLE_SR')
    if reason:
        atomic_write_json(pdir / 'PILOT_STOP.json', {'reason': reason, 'created_et': now_et()})
        print('PILOT_STOP %s' % reason, flush=True)
        return run
    print('PILOT_CHOICE S=%d R=%d' % (int(choice['S']), int(choice['R'])), flush=True)
    return update_run(run, S=int(choice['S']), R=int(choice['R']), pilot_choice=choice)


# ---------------------------------------------------------------------------------------------------------------------
# Sealed sampling (frozen libraries only)

def freeze_entry(run: Run, arm: str) -> dict | None:
    fp = rounds.freeze_dir(run) / 'FREEZE.json'
    fr = read_json(fp)
    if fr is None:
        raise FreezeMissing('FREEZE.json missing: sealed sampling needs frozen libraries')
    return fr['libraries'].get(arm)


def frozen_library(run: Run, arm: str):
    """The arm's frozen library, its file sha checked against FREEZE.json. EXEMPLAR -> list of exemplars."""
    e = freeze_entry(run, arm)
    if e is None:
        return None
    p = Path(run.dir) / e['json']
    got = hashlib.sha256(p.read_bytes()).hexdigest()
    if got != e['sha256_json']:
        raise ArmError('FROZEN_LIBRARY_CHANGED %s %s != %s' % (p, got, e['sha256_json']))
    if arm == 'EXEMPLAR':
        key = ('pool', str(p))
        if key not in run.cache:
            Ex = kit_of(run).exemplar.Exemplar
            body = json.loads(p.read_text(encoding='utf-8'))
            run.cache[key] = [Ex(**{**x, 'features': tuple(x['features'])}) for x in body['exemplars']]
        return run.cache[key]
    return load_library(run, p)


def sealed_out_dir(run: Run, arm: str, sealed_seed: int, condition: str) -> Path:
    if condition.startswith('knockout_'):
        return rounds.knockout_dir(run, condition[len('knockout_'):], sealed_seed)
    return rounds.sealed_dir(run, condition, arm, sealed_seed)


def _sealed_specs(run: Run, arm: str, k: int, condition: str, tasks: Sequence, lib_for_task, ex_for_task,
                  inline: bool, slots_for_task, tag: str, batch_n: int) -> list[ReqSpec]:
    phase, seed_phase = CONDITION_PHASE[condition], CONDITION_SEED_PHASE[condition]
    out = []
    for t in tasks:
        slots_all = slots_for_task(t)
        for b in range(0, len(slots_all), batch_n):
            slots = slots_all[b:b + batch_n]
            if not slots:
                continue
            out.append(ReqSpec(request_id='%s|%s|k%d|%s|%s%d' % (arm, phase, k, t.id, tag, b // batch_n),
                               task=t, arm=arm, phase=phase, round=None, sealed_seed=k, slots=slots,
                               sample_ids=['%s|%s|k%d|%s|s%d' % (arm, phase, k, t.id, i) for i in slots],
                               seed=seed_for(run, seed_phase, None, t.id, slots[0], k),
                               library=lib_for_task(t), exemplars=ex_for_task(t), inline=inline))
    return out


def sample_sealed(run: Run, arm: str, sealed_seed: int, condition: str, client, deadline: Deadline,
                  library_override=None, task_ids: Sequence[str] | None = None, mode: str = 'callable',
                  inline_override: dict | None = None) -> None:
    """S samples per sealed task (SPEC 13 I1) with the arm's frozen library; then execution and submissions.
    library_override: a Library, or a dict task -> Library (knockout delete). mode: callable | deleted | inline."""
    if arm not in ARMS:
        raise ArmError('unknown arm %s' % arm)
    if condition not in CONDITION_SPLIT:
        raise ArmError('unknown condition %s' % condition)
    kit = kit_of(run)
    d = sealed_out_dir(run, arm, sealed_seed, condition)
    st = load_state(d)
    if st.get('state') in ('DONE', 'BASE_DONE'):
        return
    split, phase = CONDITION_SPLIT[condition], CONDITION_PHASE[condition]
    tasks = tasks_of(run, split, task_ids)
    exemplars = None
    if library_override is not None:
        lib_any = library_override
    elif arm == config.FLAT_ARM:
        lib_any = None
    elif arm == 'EXEMPLAR':
        lib_any, exemplars = None, frozen_library(run, 'EXEMPLAR')
    else:
        lib_any = frozen_library(run, arm)
    if isinstance(lib_any, dict):
        lib_for_task = lambda t: lib_any[t.id]  # noqa: E731
    else:
        lib_for_task = lambda t: lib_any  # noqa: E731
    if exemplars is not None:
        scaler = exemplar_scaler(run)
        ex_for_task = lambda t: kit.exemplar.neighbours(t, exemplars, scaler, k=config.EXEMPLAR_K)  # noqa: E731
    else:
        ex_for_task = lambda t: None  # noqa: E731
    inline = mode == 'inline'
    S = run.S
    specs = _sealed_specs(run, arm, sealed_seed, condition, tasks, lib_for_task, ex_for_task, inline,
                          lambda t: list(range(S)), 'b', S)
    if inline_override is not None:
        for sp_ in specs:
            sp_.inline_library = inline_override[sp_.task.id]
            sp_.inline = True
    if not st:
        st = {'arm': arm, 'round': None, 'sealed_seed': sealed_seed, 'condition': condition, 'state': 'SAMPLING',
              'requests_total': len(specs), 'mode': mode, 'started_et': now_et(), 'jobs': []}
    if run.job_id not in st['jobs']:
        st['jobs'].append(run.job_id)
    save_state(d, st)
    sp, ep = d / 'samples.jsonl', d / 'exec.jsonl'
    if st['state'] == 'SAMPLING':
        _sealed_levers(run, arm, phase, sealed_seed, condition, lib_any, specs, mode, inline_override)
        if not sample(run, specs, sp, client, deadline, arm, phase):
            st.update(round_counts(sp, ep))
            save_state(d, st)
            return
        if client is not None:
            lever_prefix(run, arm, phase, client)
        st['state'] = 'EXECUTING'
        save_state(d, st)
    by_task = {t.id: lib_for_task(t) for t in tasks}
    ok = execute(run, sp, ep, {t.id: t for t in tasks}, lambda row: by_task.get(row['task']),
                 mode, deadline, False)
    st.update(round_counts(sp, ep))
    if not ok:
        save_state(d, st)
        return
    if arm == config.FLAT_ARM and condition in ('sealed', 'perturbed'):
        st['state'] = 'BASE_DONE'          # submissions after the FLAT extra samples (flat_extra unit)
    else:
        write_submissions(run, arm, sealed_seed, condition, task_ids=[t.id for t in tasks])
        st['state'] = 'DONE'
    save_state(d, st)


def _sealed_levers(run: Run, arm: str, phase: str, k: int, condition: str, lib_any, specs, mode: str,
                   inline_override: dict | None = None) -> None:
    if isinstance(lib_any, dict):
        full = frozen_library(run, 'STOCK')
        full_names = {h.name for h in _in_context(full)}
        for t in sorted(lib_any):
            kept = sorted(h.name for h in _in_context(lib_any[t]))
            removed = sorted(full_names - set(kept))
            if inline_override is not None:
                shown = sorted(h.name for h in (inline_override.get(t).helpers if inline_override.get(t) else []))
                emit(run, arm, phase, 'LEVER KO_INLINE task=%s callable=0 inlined=%s kept_callable=%s' % (
                    t, ','.join(shown) or 'none', ','.join(kept) or 'none'))
            else:
                emit(run, arm, phase, 'LEVER KO_DELETE task=%s removed=%s kept=%s' % (
                    t, ','.join(removed) or 'none', ','.join(kept) or 'none'))
        lever_sandbox(run, arm, phase, 'pertask', max([len(_in_context(v)) for v in lib_any.values()] or [0]))
        return
    if mode == 'inline':
        for s in specs:
            if s.slots[0] == 0:
                emit(run, arm, phase, 'LEVER KO_INLINE task=%s callable=0' % s.task.id)
        lever_sandbox(run, arm, phase, kit_of(run).library.sha(lib_any) if lib_any is not None else None, 0)
        return
    n_ctx = len(_in_context(lib_any)) if lib_any is not None and hasattr(lib_any, 'helpers') else 0
    sha = kit_of(run).library.sha(lib_any) if lib_any is not None and hasattr(lib_any, 'helpers') else None
    if arm == 'STOCK':
        emit(run, arm, phase, 'LEVER STOCK library r=%d sha=%s updated=%d helpers_in_context=%d' % (
            run.R, sha, stock_updated(run, lib_any), n_ctx))
    elif arm == 'STATIC':
        emit(run, arm, phase, 'LEVER STATIC library r=%d sha=%s frozen=1' % (run.R, sha))
    elif arm == 'PLANTDRIP':
        emit(run, arm, phase, 'LEVER PLANTDRIP tranche=%d of %d primitives=%d' % (run.R, run.R, n_ctx))
    elif arm == 'PLANTL1':
        emit(run, arm, phase, 'LEVER PLANTL1 tranche=1 primitives=%d' % n_ctx)
    elif arm == 'SHAM':
        emit(run, arm, phase, 'LEVER SHAM library sha=%s helpers_in_context=%d verified=0' % (sha, n_ctx))
    elif arm == 'ONESHOT':
        emit(run, arm, phase, 'LEVER ONESHOT library sha=%s helpers_in_context=%d' % (sha, n_ctx))
    elif arm == 'EXEMPLAR':
        for s in specs:
            pb = build_prompt(run, s)
            emit(run, arm, phase, 'LEVER EXEMPLAR task=%s k=%d exemplar_tokens=%d' % (
                s.task.id, len(s.exemplars or []), int(getattr(pb, 'exemplar_tokens', 0))))
    if phase == 'perturbed':
        emit(run, arm, phase, 'LEVER PERTURB seed=%d tasks=%d' % (
            int(run.cfg.get('perturb_seed', config.PERTURB_SEED)), len({s.task.id for s in specs})))
    lever_sandbox(run, arm, phase, sha, n_ctx)


def sample_flat_extra(run: Run, sealed_seed: int, condition: str, client, deadline: Deadline) -> None:
    from . import budget as _budget
    arm = config.FLAT_ARM
    d = sealed_out_dir(run, arm, sealed_seed, condition)
    st = load_state(d)
    if st.get('state') == 'DONE':
        return
    if st.get('state') not in ('BASE_DONE', 'EXTRA_SAMPLING', 'EXTRA_EXECUTING'):
        raise ArmError('FLAT base pass seed %d %s not done (state %s)' % (sealed_seed, condition, st.get('state')))
    stock = load_state(sealed_out_dir(run, 'STOCK', sealed_seed, condition))
    if stock.get('state') != 'DONE':
        raise ArmError('STOCK %s seed %d not done: the FLAT target needs its tokens' % (condition, sealed_seed))
    if 'budget' not in st:     # computed once, then frozen in the state (a restart never re-targets)
        fb = _budget.flat_budget(run, sealed_seed, condition)
        st['budget'] = fb.to_dict()
        atomic_write_json(d / 'flat_budget.json', fb.to_dict())
    fb = _budget.FlatBudget.from_dict(st['budget'])
    phase = CONDITION_PHASE[condition]
    tasks = tasks_of(run, CONDITION_SPLIT[condition])
    S = run.S
    batch_n = int(run.cfg.get('flat_extra_n', max(S, config.FLAT_EXTRA_BATCH_N)))
    specs = _sealed_specs(run, arm, sealed_seed, condition, tasks, lambda t: None, lambda t: None, False,
                          lambda t: list(range(S, S + fb.per_task.get(t.id, 0))), 'x', batch_n)
    sp, ep = d / 'samples.jsonl', d / 'exec.jsonl'
    if st['state'] in ('BASE_DONE', 'EXTRA_SAMPLING'):
        st['state'] = 'EXTRA_SAMPLING'
        st['extra_requests_total'] = len(specs)
        save_state(d, st)
        if not sample(run, specs, sp, client, deadline, arm, phase):
            st.update(round_counts(sp, ep))
            save_state(d, st)
            return
        st['state'] = 'EXTRA_EXECUTING'
        save_state(d, st)
    ok = execute(run, sp, ep, {t.id: t for t in tasks}, lambda row: None, 'callable', deadline, False)
    st.update(round_counts(sp, ep))
    if not ok:
        save_state(d, st)
        return
    real = _budget.realized_tokens(kit_of(run).ledger.iter_rows(run.dir), sealed_seed, condition)
    st['realized'] = real
    emit(run, arm, phase, 'LEVER FLATTTC seed=%d extra=%d target_tokens=%d realized_tokens=%d' % (
        sealed_seed, fb.n_extra, fb.target_tokens, real['extra']))
    lever_sandbox(run, arm, phase, None, 0)
    if client is not None:
        lever_prefix(run, arm, phase, client)
    write_submissions(run, arm, sealed_seed, condition, task_ids=[t.id for t in tasks])
    st['state'] = 'DONE'
    save_state(d, st)


def write_submissions(run: Run, arm: str, sealed_seed: int, condition: str,
                      task_ids: Sequence[str] | None = None) -> Path:
    """select.pass2 per task over every executed sample of this arm, seed and condition. Written before any key read."""
    kit = kit_of(run)
    d = sealed_out_dir(run, arm, sealed_seed, condition)
    samples = read_rows(d / 'samples.jsonl', 'sample_id')
    ex = read_rows(d / 'exec.jsonl', 'sample_id')
    missing = sorted(set(samples) - set(ex))
    if missing:
        raise ArmError('%d samples without exec rows in %s (first %s)' % (len(missing), d, missing[0]))
    ids = sorted(task_ids) if task_ids is not None else split_ids(run, CONDITION_SPLIT[condition])
    by_task: dict[str, list] = {t: [] for t in ids}
    for sid in sorted(ex):
        srow, row = samples[sid], ex[sid]
        if srow['task'] not in by_task:
            continue
        outs = row.get('test_outputs') if row.get('demo_pass') else None
        by_task[srow['task']].append(kit.types.Candidate(
            sample_id=sid, code_len=len(srow.get('code') or ''), demo_pass=bool(row.get('demo_pass')),
            test_outputs=None if outs is None else tuple(_grid(g) for g in outs)))
    subs = []
    for t in ids:
        sub = kit.select.pass2(t, by_task[t])
        subs.append(sub.to_json() if hasattr(sub, 'to_json') else asdict(sub))
    p = d / 'submissions.json'
    atomic_write_json(p, {'schema': 'ratchet.submissions.v1', 'run': run.name, 'arm': arm, 'condition': condition,
                          'sealed_seed': sealed_seed, 'n_tasks': len(subs), 'n_samples': len(samples),
                          'submissions': subs})
    return p


# ---------------------------------------------------------------------------------------------------------------------
# Perturbed split, knockout

def build_perturbed(run: Run) -> None:
    kit = kit_of(run)
    seed = int(run.cfg.get('perturb_seed', config.PERTURB_SEED))
    out = kit.perturb.build_perturbed_split(seed, 'sealed')
    run.cache.pop(('ids', 'sealed_perturbed'), None)
    n = len(split_ids(run, 'sealed_perturbed'))
    emit(run, 'PERTURB', 'build', 'LEVER PERTURB seed=%d tasks=%d' % (seed, n))
    atomic_write_json(Path(run.dir) / 'PERTURB_DONE.json', {'seed': seed, 'tasks': n, 'out': str(out),
                                                            'created_et': now_et()})


def _scores_W(run: Run) -> list[str]:
    w = read_json(rounds.scores_dir(run) / 'W.json')
    if w is None:
        raise ArmError('scores/W.json missing (the primary score has not run)')
    if isinstance(w, dict):
        w = w.get('W', w.get('tasks', []))
    return sorted(w)


def _winners(run: Run) -> dict[str, list]:
    """winners.json (task -> winning sample ids) resolved to STOCK sealed exec rows across seeds."""
    kit = kit_of(run)
    w = read_json(rounds.scores_dir(run) / 'winners.json') or {}
    if 'winners' in w and isinstance(w['winners'], dict):
        w = w['winners']
    rows: dict[str, dict] = {}
    for k in rounds.sealed_seeds(run):
        rows.update(read_rows(rounds.sealed_dir(run, 'sealed', 'STOCK', k) / 'exec.jsonl', 'sample_id'))
    ER = getattr(kit.types, 'ExecResult', None)
    out = {}
    for task, sids in sorted(w.items()):
        res = []
        for sid in sids:
            if sid not in rows:
                raise ArmError('winner %s has no STOCK sealed exec row' % sid)
            res.append(ER.from_row(rows[sid]) if ER is not None and hasattr(ER, 'from_row') else rows[sid])
        out[task] = res
    return out


def build_knockout(run: Run) -> None:
    """PREREG 6.3 knockout libraries, per task in W (review fix 2026-11-04):
    - delete: exactly STOCK's in-context L_R helpers minus the helpers that task's winners called and their dependents.
      Nothing out of context is refilled into the freed tokens (the saved in-context set is checked against that list).
    - inline: the same callable set, plus the knocked-out helpers shown as NON-callable reference text; every other
      helper stays callable. The sandbox executes only the callable set in both modes."""
    kit = kit_of(run)
    W = _scores_W(run)
    L_R = frozen_library(run, 'STOCK')
    winners = _winners(run)
    libs = kit.knockout.build_knockout_libraries(L_R, frozenset(W), winners)
    full = {h.name for h in _in_context(L_R)}
    index, inline = {}, {}
    created = read_json(rounds.freeze_dir(run) / 'FREEZE.json', {}).get('created_et')
    for task in sorted(libs):
        lib = libs[task]
        gone = set((lib.meta or {}).get('knockout_removed') or [])
        want_kept = sorted(full - gone)
        _deterministic_meta(lib, created)
        jp, pp, s = kit.library.save(lib, ko_library_dir(run, 'delete', task), run.cap, kit.tok,
                                     stem='L_ko_%s' % task)
        kept = sorted(h.name for h in _in_context(kit.library.load(jp)))
        if kept != want_kept:
            raise ArmError('KO_CONTEXT_REFILL task %s: saved in-context %s != L_R in-context minus removed %s' % (
                task, kept, want_kept))
        index[task] = {'json': rel(run, jp), 'py': rel(run, pp), 'sha256': s, 'removed': sorted(full - set(kept)),
                       'kept': kept}
        txt = kit.knockout.inline_text_library(L_R, frozenset(gone), task)
        _deterministic_meta(txt, created)
        jp2, pp2, s2 = kit.library.save(txt, ko_library_dir(run, 'inline', task), run.cap, kit.tok,
                                        stem='L_ko_inline_%s' % task)
        inline[task] = {'json': rel(run, jp2), 'py': rel(run, pp2), 'sha256': s2,
                        'inlined': sorted(h.name for h in txt.helpers), 'callable_json': rel(run, jp)}
    atomic_write_json(Path(run.dir) / 'knockout' / 'KO_LIBS.json', {
        'W': W, 'libraries': index, 'inline': inline, 'created_et': now_et()})


def ko_library_dir(run: Run, mode: str, task: str) -> Path:
    return Path(run.dir) / 'knockout' / mode / 'libraries' / task


def sample_knockout(run: Run, mode: str, sealed_seed: int, client, deadline: Deadline) -> None:
    condition, exec_mode = KO_MODES[mode]
    idx = read_json(Path(run.dir) / 'knockout' / 'KO_LIBS.json')
    if idx is None:
        raise ArmError('knockout libraries not built')
    W = sorted(idx['W'])
    override = {t: load_library(run, idx['libraries'][t]['json']) for t in W}
    inline = None
    if mode == 'inline':
        inline = {t: load_library(run, idx['inline'][t]['json']) for t in W}
    sample_sealed(run, 'STOCK', sealed_seed, condition, client, deadline, library_override=override, task_ids=W,
                  mode=exec_mode, inline_override=inline)


# ---------------------------------------------------------------------------------------------------------------------
# Job STATUS (SPEC 4.7) and the step loop

class JobStatus:
    def __init__(self, run: Run, deadline: Deadline):
        self.run, self.deadline = run, deadline
        self.path = rounds.jobs_dir(run) / str(run.job_id) / 'STATUS.json'
        prev = read_json(self.path, {}) or {}
        self.d = {'job_id': str(run.job_id), 'job_name': os.environ.get('SLURM_JOB_NAME', ''),
                  'node': os.environ.get('SLURMD_NODENAME', os.environ.get('HOSTNAME', '')),
                  'gpu': os.environ.get('RATCHET_GPU_NAME', ''), 'state': 'RUNNING', 'meta': None,
                  'started_et': prev.get('started_et') or now_et(), 'updated_et': None,
                  'deadline_et': None, 'units_done': prev.get('units_done', []),
                  'seconds': {'vllm_startup': float(os.environ.get('RATCHET_VLLM_STARTUP_S', 0) or 0),
                              'sampling': 0.0, 'exec_only': 0.0, 'drain': 0.0, 'idle': 0.0},
                  'units': {}, 'tokens': {}, 'gen_tok_per_s': 0.0, 'prefix_cache_hit_rate': None,
                  'exec': {}, 'exit_reason': None, 'last_error': None}

    def write(self, **kw) -> None:
        c = counters(self.run)
        self.d.update(kw)
        self.d['updated_et'] = now_et()
        self.d['seconds']['sampling'] = round(c.sampling_s, 3)
        self.d['seconds']['exec_only'] = round(c.exec_s, 3)
        self.d['seconds']['elapsed'] = round(self.deadline.elapsed(), 3)
        self.d['tokens'] = {'prompt': c.prompt, 'prompt_logical': c.prompt_logical, 'cached': c.cached, 'gen': c.gen,
                            'requests': c.requests}
        self.d['gen_tok_per_s'] = round(c.gen / c.sampling_s, 3) if c.sampling_s > 0 else 0.0
        self.d['exec'] = {'runs': c.exec_runs, 'timeouts': c.exec_timeouts, 'cpu_s': round(c.exec_s, 3)}
        atomic_write_json(self.path, self.d)


def write_run_status(run: Run, job_state: dict | None = None) -> None:
    nu = rounds.next_unit(run)
    arms_progress: dict[str, dict] = {}
    base = Path(run.dir) / 'arms'
    if base.exists():
        for arm_d in sorted(base.iterdir()):
            if arm_d.is_dir():
                prog = {}
                for rd in sorted(arm_d.glob('round_*')):
                    prog[rd.name] = load_state(rd).get('state')
                if (arm_d / 'round_state.json').exists():
                    prog['build'] = load_state(arm_d).get('state')
                arms_progress[arm_d.name] = prog
    try:
        totals = kit_of(run).ledger.totals(Path(run.dir))
    except Exception as e:  # noqa: BLE001
        totals = {'error': type(e).__name__}
    p = Path(run.dir) / 'STATUS.json'
    prev = read_json(p, {}) or {}
    jobs = prev.get('jobs', [])
    if job_state:
        jobs = [j for j in jobs if j.get('job_id') != job_state.get('job_id')] + [job_state]
    atomic_write_json(p, {'run': run.name, 'S': run.S, 'R': run.R, 'next_unit': nu.to_dict() if nu else None,
                          'next_unit_gpu': bool(nu and nu.gpu), 'arms': arms_progress, 'ledger_totals': totals,
                          'jobs': jobs[-20:], 'updated_et': now_et()})


def run_unit(run: Run, u: WorkUnit, client, deadline: Deadline) -> Run:
    from . import freeze as _freeze
    k = u.kind
    if k == 'pilot':
        run_pilot_round(run, u.condition, client, deadline)
    elif k == 'pilot_screen':
        run = pilot_screen(run)
    elif k == 'pilot_choose':
        run = pilot_choose(run)
    elif k == 'grow':
        grow_round(run, u.arm, u.round, client, deadline)
    elif k == 'build_sham':
        build_sham_arm(run)
    elif k == 'build_plant':
        build_plant_arm(run)
    elif k == 'freeze_libraries':
        _path, sha = _freeze.freeze_libraries(run)
        print('FREEZE sha256=%s (lead: commit freeze/FREEZE.json, then `ratchet freeze --ack %s`)' % (sha, sha),
              flush=True)
    elif k == 'sealed':
        sample_sealed(run, u.arm, u.sealed_seed, u.condition, client, deadline)
    elif k == 'flat_extra':
        sample_flat_extra(run, u.sealed_seed, u.condition, client, deadline)
    elif k == 'perturb_build':
        build_perturbed(run)
    elif k == 'freeze_submissions':
        _path, sha = _freeze.freeze_submissions(run)
        print('SUBMIT_FREEZE sha256=%s' % sha, flush=True)
    elif k == 'knockout_build':
        build_knockout(run)
    elif k == 'knockout':
        sample_knockout(run, u.condition, u.sealed_seed, client, deadline)
    elif k == 'freeze_knockout':
        _path, sha = _freeze.freeze_knockout(run)
        print('KO_FREEZE sha256=%s' % sha, flush=True)
    elif k == 'freeze_arcagi2':
        _path, sha = _freeze.freeze_arcagi2(run)
        print('A2_SUBMIT_FREEZE sha256=%s (lead: commit, then `ratchet freeze --ack %s --name A2_SUBMIT_FREEZE`)' % (
            sha, sha), flush=True)
    elif k == 'verdict':
        kit_of(run).verdict.write_result(Path(run.dir), config.REPO_DIR)
    else:
        raise ArmError('unit kind %s is not runnable by step' % k)
    return run


def step(run: Run, client, deadline: Deadline) -> None:
    """Job entry: work PLAN units until the deadline, a manual gate, or the end. client None = CPU-only job."""
    ret = rounds.retired(run.dir)
    if ret:
        raise ArmError('HARNESS_RETIRED after VOID runs %s (PREREG 9): step refused' % ','.join(ret))
    status = JobStatus(run, deadline)
    first = rounds.next_unit(run)
    meta = meta_line(run, (first.arm if first else None) or '-', (first.phase if first else None) or '-',
                     first.round if first else None)
    print(meta, flush=True)
    status.write(meta=meta, state='RUNNING',
                 deadline_et=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(deadline.stop_issue_ts)))
    exit_reason, state = None, 'RUNNING'
    stalls: dict[str, int] = {}
    try:
        if first is not None and first.gpu:
            # Truncation amendment: every job prints the instruction sha once and refuses a sha other than the run's.
            print(lever_instruction_line(run), flush=True)
        while True:
            u = rounds.next_unit(run)
            if u is None:
                exit_reason, state = 'PLAN_DONE', 'DONE'
                break
            if u.manual:
                exit_reason, state = 'WAITING_%s_%s' % (u.kind.upper(), u.condition), 'DONE'
                print('STEP_WAIT %s' % u.key(), flush=True)
                break
            if u.gpu and (client is None or not deadline.issue_ok()):
                exit_reason = 'NEEDS_GPU' if client is None else 'DEADLINE_ISSUE'
                state = 'DONE' if client is None else 'STOPPED_GRACEFUL'
                break
            if deadline.hard():
                exit_reason, state = 'DEADLINE_HARD', 'STOPPED_GRACEFUL'
                break
            print('UNIT start %s' % u.key(), flush=True)
            status.write(units=u.to_dict())
            run = run_unit(run, u, client, deadline)
            done = rounds.unit_done(run, u)
            print('UNIT %s %s' % ('done' if done else 'partial', u.key()), flush=True)
            if done:
                status.d['units_done'].append(u.key())
            status.write()
            write_run_status(run)
            if not done:
                if deadline.issue_ok() and not deadline.hard():
                    # time left but the unit did not finish (for example failed requests): retry once in this job
                    stalls[u.key()] = stalls.get(u.key(), 0) + 1
                    if stalls[u.key()] <= int(run.cfg.get('max_stalls', 1)):
                        continue
                    raise ArmError('unit %s did not complete with time left (stalled)' % u.key())
                exit_reason, state = 'DEADLINE', 'STOPPED_GRACEFUL'
                break
    except BaseException as e:
        status.write(state='FAILED', exit_reason=type(e).__name__, last_error=''.join(
            traceback.format_exception_only(type(e), e)).strip()[:2000])
        write_run_status(run, {'job_id': str(run.job_id), 'state': 'FAILED', 'exit_reason': type(e).__name__,
                               'updated_et': now_et()})
        raise
    status.write(state=state, exit_reason=exit_reason)
    write_run_status(run, {'job_id': str(run.job_id), 'state': state, 'exit_reason': exit_reason,
                           'updated_et': now_et()})
    print('STEP_EXIT state=%s reason=%s' % (state, exit_reason), flush=True)
