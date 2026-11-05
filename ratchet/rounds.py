"""Round state machine, idempotent work units, atomic writes and the PLAN order (SPEC 4.6, 7.1). Owner: builder D.

Every piece of work is keyed by an id (request_id for sampling, sample_id for execution). A restart re-reads the jsonl
files, drops a torn trailing line, and skips every id that is already done. State files are written atomically
(temp file in the same directory, fsync, os.replace), so a kill at any point leaves either the old or the new state.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import config

ROUND_STATES = ('PENDING', 'SAMPLING', 'EXECUTING', 'EXTRACTING', 'FROZEN')
GPU_KINDS = frozenset({'pilot', 'grow', 'sealed', 'flat_extra', 'knockout'})
MANUAL_KINDS = frozenset({'lead_gate', 'score_gate', 'blocked'})


@dataclass(frozen=True)
class WorkUnit:
    kind: str
    arm: str | None = None
    phase: str | None = None
    round: int | None = None
    sealed_seed: int | None = None
    condition: str | None = None

    def key(self) -> str:
        return '|'.join('' if v is None else str(v) for v in
                        (self.kind, self.arm, self.phase, self.round, self.sealed_seed, self.condition))

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def gpu(self) -> bool:
        # A growth round whose rows are shared from STOCK round 1 needs no model call.
        return self.kind in GPU_KINDS and not (self.kind == 'grow' and self.round == 1
                                               and self.arm in config.SHARED_ROUND1_ARMS)

    @property
    def manual(self) -> bool:
        return self.kind in MANUAL_KINDS


# ---------------------------------------------------------------------------------------------------------------------
# Time

class TestSwitchRefused(RuntimeError):
    pass


def _under(p: str, root: str) -> bool:
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


def production_run(run) -> bool:
    """A run on the real runs tree (config.REAL_RUNS_DIR, not redirectable by RATCHET_ROOT) or inside a SLURM job."""
    d = os.path.realpath(str(run.dir if hasattr(run, 'dir') else run))
    return _under(d, os.path.realpath(str(config.REAL_RUNS_DIR))) or bool(os.environ.get('SLURM_JOB_ID'))


def check_test_switches(run) -> None:
    """skip_pilot and auto_ack exist for CPU tests only (review fix 2026-11-04): PREREG 7 fixes S and R by the pilot
    rule, and the lead gates are the lead's commits. Refused on the real runs tree and inside any SLURM job."""
    on = [k for k in ('skip_pilot', 'auto_ack') if run.cfg.get(k)]
    if on and production_run(run):
        raise TestSwitchRefused('TEST_SWITCH_REFUSED %s on a production run (%s)' % (','.join(on), run.dir))


def retired(run_dir) -> list[str]:
    """VOID runs listed in <runs>/ATTEMPTS.json when the harness is retired (PREREG 9), else []."""
    a = read_json(Path(run_dir).parent / 'ATTEMPTS.json', {}) or {}
    v = list(a.get('void_runs', []))
    return v if (a.get('retired') or len(v) >= int(config.VOID_MAX_ATTEMPTS)) else []


def now_et() -> str:
    """Eastern time stamp (fixed UTC-5 for EST after Nov 1; DST is not needed for this run's dates)."""
    try:
        from zoneinfo import ZoneInfo
        t = _dt.datetime.now(ZoneInfo('America/New_York'))
    except Exception:  # noqa: BLE001 - tzdata may be absent on the login node
        t = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=-5)))
    return t.strftime('%Y-%m-%d %H:%M:%S ET')


# ---------------------------------------------------------------------------------------------------------------------
# Atomic files

def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def dumps(obj: Any) -> str:
    """Canonical JSON used for every state file: sorted keys, no NaN, LF."""
    return json.dumps(obj, sort_keys=True, indent=1, allow_nan=False, default=_json_default) + '\n'


def _json_default(o: Any):
    if hasattr(o, '__dataclass_fields__'):
        return asdict(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, Path):
        return str(o)
    if hasattr(o, 'tolist'):
        return o.tolist()
    raise TypeError('not JSON serializable: %r' % type(o))


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, dumps(obj).encode('utf-8'))


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def load_state(dir: Path) -> dict:
    """round_state.json of a round (or unit_state.json style dir); {} if absent."""
    return read_json(Path(dir) / 'round_state.json', {}) or {}


def save_state(dir: Path, state: dict) -> None:
    state = dict(state)
    state.setdefault('schema', config.ROUND_SCHEMA)
    state['updated_et'] = now_et()
    atomic_write_json(Path(dir) / 'round_state.json', state)


# ---------------------------------------------------------------------------------------------------------------------
# JSONL: append-only, torn-tail tolerant

def repair_jsonl(path: Path) -> int:
    """Truncate a torn or unparsable trailing line so later appends start on a clean line. Returns bytes dropped."""
    path = Path(path)
    if not path.exists():
        return 0
    data = path.read_bytes()
    if not data:
        return 0
    keep = len(data)
    if not data.endswith(b'\n'):
        keep = data.rfind(b'\n') + 1
    else:
        # the last full line must parse; a crash can leave a complete-looking but cut line only without '\n',
        # but check anyway (a partial write that happened to end on a newline byte inside a string).
        start = data.rfind(b'\n', 0, len(data) - 1) + 1
        try:
            json.loads(data[start:].decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            keep = start
    dropped = len(data) - keep
    if dropped:
        with path.open('r+b') as f:
            f.truncate(keep)
            f.flush()
            os.fsync(f.fileno())
    return dropped


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Rows of a jsonl file; a line that fails to parse is skipped only if it is the last one (torn write)."""
    path = Path(path)
    if not path.exists():
        return
    lines = path.read_bytes().split(b'\n')
    if lines and lines[-1] == b'':
        lines.pop()
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        try:
            yield json.loads(ln.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            if i == len(lines) - 1:
                return
            raise ValueError('corrupt line %d in %s (not the last line)' % (i + 1, path))


def read_rows(path: Path, key: str) -> dict[str, dict]:
    """Rows keyed by `key`, last row wins (a re-issued request after a kill overwrites its earlier copy)."""
    out: dict[str, dict] = {}
    for row in iter_jsonl(path):
        k = row.get(key)
        if k is not None:
            out[k] = row
    return out


def done_ids(jsonl: Path, key: str) -> set[str]:
    return set(read_rows(jsonl, key))


def append_jsonl(path: Path, rows: Iterable[dict]) -> None:
    """One write call for all rows (so a request's samples land together), then flush and fsync."""
    rows = list(rows)
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = ''.join(json.dumps(r, sort_keys=True, allow_nan=False, default=_json_default) + '\n' for r in rows)
    with path.open('ab') as f:
        f.write(blob.encode('utf-8'))
        f.flush()
        os.fsync(f.fileno())


# ---------------------------------------------------------------------------------------------------------------------
# Run directory layout (SPEC 7)

def round_dir(run, arm: str, r: int) -> Path:
    return Path(run.dir) / 'arms' / arm / ('round_%d' % r)


def arm_dir(run, arm: str) -> Path:
    return Path(run.dir) / 'arms' / arm


def pilot_dir(run, which: str) -> Path:
    return Path(run.dir) / 'pilot' / which


def sealed_dir(run, condition: str, arm: str, seed: int) -> Path:
    return Path(run.dir) / 'sealed' / condition / arm / ('seed_%d' % seed)


def knockout_dir(run, mode: str, seed: int) -> Path:
    return Path(run.dir) / 'knockout' / mode / ('seed_%d' % seed)


def freeze_dir(run) -> Path:
    return Path(run.dir) / 'freeze'


def scores_dir(run) -> Path:
    return Path(run.dir) / 'scores'


def logs_dir(run) -> Path:
    return Path(run.dir) / 'logs'


def jobs_dir(run) -> Path:
    return Path(run.dir) / 'jobs'


def ledger_dir(run) -> Path:
    return Path(run.dir) / 'ledger'


def unit_state_path(run, unit: WorkUnit) -> Path | None:
    if unit.kind in ('grow',):
        return round_dir(run, unit.arm, unit.round) / 'round_state.json'
    if unit.kind == 'pilot':
        return pilot_dir(run, unit.condition) / 'round_state.json'
    if unit.kind in ('sealed', 'flat_extra'):
        return sealed_dir(run, unit.condition, unit.arm, unit.sealed_seed) / 'round_state.json'
    if unit.kind == 'knockout':
        return knockout_dir(run, unit.condition, unit.sealed_seed) / 'round_state.json'
    if unit.kind == 'build_sham':
        return arm_dir(run, 'SHAM') / 'round_state.json'
    if unit.kind == 'build_plant':
        return arm_dir(run, 'PLANTDRIP') / 'round_state.json'
    return None


# ---------------------------------------------------------------------------------------------------------------------
# PLAN (SPEC 7.1)

def sealed_seeds(run) -> tuple[int, ...]:
    return tuple(run.cfg.get('sealed_seeds', config.SEALED_SEEDS))


def plan(run) -> list[WorkUnit]:
    """Deterministic order of every unit of the run. Units past a missing S/R are not planned yet."""
    check_test_switches(run)
    u: list[WorkUnit] = []
    if not run.cfg.get('skip_pilot'):
        for which in config.PILOT_WHICH:
            u.append(WorkUnit('pilot', which, 'pilot', None, None, which))
        u.append(WorkUnit('pilot_choose'))
    if run.S is None or run.R is None:
        return u
    R = run.R
    # 2. Growth
    u.append(WorkUnit('grow', 'STOCK', 'growth', 1))
    for arm in config.SHARED_ROUND1_ARMS:
        u.append(WorkUnit('grow', arm, 'growth', 1))           # shared from STOCK round 1, no model call
    for r in range(2, R + 1):
        u.append(WorkUnit('grow', 'STOCK', 'growth', r))
    for r in range(2, R + 1):
        u.append(WorkUnit('grow', 'EXEMPLAR', 'growth', r))
    u.append(WorkUnit('grow', 'ONESHOT', 'growth', 1))
    u.append(WorkUnit('build_sham', 'SHAM'))
    u.append(WorkUnit('build_plant', 'PLANTDRIP'))
    for r in range(2, R + 1):
        u.append(WorkUnit('grow', 'STATIC', 'growth', r))
    # 3. Library freeze, then the lead commits it
    u.append(WorkUnit('freeze_libraries'))
    u.append(WorkUnit('lead_gate', condition='FREEZE'))
    # 4. Sealed sampling
    for k in sealed_seeds(run):
        for arm in config.LIBRARY_ARMS:
            u.append(WorkUnit('sealed', arm, 'sealed', None, k, 'sealed'))
        u.append(WorkUnit('sealed', config.FLAT_ARM, 'sealed', None, k, 'sealed'))
        u.append(WorkUnit('flat_extra', config.FLAT_ARM, 'sealed', None, k, 'sealed'))
    u.append(WorkUnit('perturb_build'))
    for k in sealed_seeds(run):
        u.append(WorkUnit('sealed', 'STOCK', 'perturbed', None, k, 'perturbed'))
        u.append(WorkUnit('sealed', config.FLAT_ARM, 'perturbed', None, k, 'perturbed'))
        u.append(WorkUnit('flat_extra', config.FLAT_ARM, 'perturbed', None, k, 'perturbed'))
    # 5, 6. Submission freeze, lead commit, first key read (lead runs `ratchet score`)
    u.append(WorkUnit('freeze_submissions'))
    u.append(WorkUnit('lead_gate', condition='SUBMIT_FREEZE'))
    u.append(WorkUnit('score_gate', condition='primary'))
    # 7. Knockout
    u.append(WorkUnit('knockout_build'))
    for mode, phase in (('delete', 'knockout_delete'), ('inline', 'knockout_inline')):
        for k in sealed_seeds(run):
            u.append(WorkUnit('knockout', 'STOCK', phase, None, k, mode))
    u.append(WorkUnit('freeze_knockout'))
    u.append(WorkUnit('lead_gate', condition='KO_FREEZE'))
    u.append(WorkUnit('score_gate', condition='knockout'))
    # 8. Verdict
    u.append(WorkUnit('verdict'))
    # 9. ARC-AGI-2 secondary read (PREREG 2; SPEC 13 I16): planned only once RESULT.md exists and the ARC-AGI-2 key
    # was added (`score_sealed.py seal-arcagi2`), so a run without it ends at the verdict.
    if (Path(run.dir) / 'RESULT.md').exists() and _arcagi2_sealed():
        for k in sealed_seeds(run):
            for arm in config.LIBRARY_ARMS + (config.FLAT_ARM,):
                u.append(WorkUnit('sealed', arm, 'arcagi2', None, k, 'arcagi2'))
        u.append(WorkUnit('freeze_arcagi2'))
        u.append(WorkUnit('lead_gate', condition='A2_SUBMIT_FREEZE'))
        u.append(WorkUnit('score_gate', condition='arcagi2'))
    return u


def _arcagi2_sealed() -> bool:
    try:
        from . import guard
        return (Path(guard.data_root()) / 'arcagi2_sealed').is_dir()
    except Exception:  # noqa: BLE001
        return False


def _state_of(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    return (read_json(path, {}) or {}).get('state')


def gate_acked(run, name: str) -> bool:
    """A lead gate passes when <name>.ack holds the sha256 in <name>.sha256 (written by `ratchet freeze --ack`)."""
    fd = freeze_dir(run)
    sha_file, ack_file = fd / (name + '.sha256'), fd / (name + '.ack')
    if not sha_file.exists():
        return False
    if run.cfg.get('auto_ack'):
        check_test_switches(run)
        return True
    return ack_file.exists() and ack_file.read_text().split()[:1] == sha_file.read_text().split()[:1]


def unit_done(run, unit: WorkUnit) -> bool:
    d = Path(run.dir)
    k = unit.kind
    if k in ('grow', 'pilot', 'build_sham', 'build_plant', 'knockout'):
        return _state_of(unit_state_path(run, unit)) in ('FROZEN', 'DONE')
    if k == 'sealed':
        st = _state_of(unit_state_path(run, unit))
        if unit.arm == config.FLAT_ARM and unit.condition in ('sealed', 'perturbed'):
            return st in ('BASE_DONE', 'EXTRA_SAMPLING', 'EXTRA_EXECUTING', 'DONE')
        return st == 'DONE'
    if k == 'flat_extra':
        return _state_of(unit_state_path(run, unit)) == 'DONE'
    if k == 'pilot_choose':
        return (d / 'pilot' / 'PILOT_CHOICE.json').exists()
    if k == 'freeze_libraries':
        return (freeze_dir(run) / 'FREEZE.json').exists()
    if k == 'freeze_submissions':
        return (freeze_dir(run) / 'SUBMIT_FREEZE.json').exists()
    if k == 'freeze_knockout':
        return (freeze_dir(run) / 'KO_FREEZE.json').exists()
    if k == 'freeze_arcagi2':
        return (freeze_dir(run) / 'A2_SUBMIT_FREEZE.json').exists()
    if k == 'lead_gate':
        return gate_acked(run, unit.condition)
    if k == 'perturb_build':
        return (d / 'PERTURB_DONE.json').exists()
    if k == 'score_gate':
        return (scores_dir(run) / ('solved_%s.json' % unit.condition)).exists()
    if k == 'knockout_build':
        return (d / 'knockout' / 'KO_LIBS.json').exists()
    if k == 'verdict':
        return (d / 'RESULT.md').exists()
    raise ValueError('unknown unit kind %r' % k)


def next_unit(run) -> WorkUnit | None:
    stop = Path(run.dir) / 'pilot' / 'PILOT_STOP.json'
    if stop.exists():
        return WorkUnit('blocked', condition=(read_json(stop, {}) or {}).get('reason', 'PILOT_STOP'))
    for unit in plan(run):
        if not unit_done(run, unit):
            return unit
    return None
