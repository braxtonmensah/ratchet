"""Sandbox parent side (PREREG 3; SPEC 1.6 item 3, 5 builder A, 8 layer 5). Owner: builder A.

One subprocess per program: `<isolation prefix> python -I -B sandbox_child.py`, JSON request on stdin, JSON lines back
on stdout, cwd = a fresh tempfile.mkdtemp() in $TMPDIR (removed afterwards).

Isolation (review fix 2026-11-04; PEP 578: an audit hook is not a sandbox). Three modes, probed once per process:
- 'bwrap' (required in production): bubblewrap with new user, net, ipc and uts namespaces and a private mount view.
  `/` is bound read-only, then a tmpfs is mounted over every data-bearing root (config.SANDBOX_HIDE_ROOTS: /N/scratch,
  /N/slate, /N/project, the geode3 home, project and log trees, /tmp, /var/tmp, /dev/shm, /run, /proc, ...), and only
  the Python install (prefixes, LIBDIR, site-packages), sandbox_child.py itself and the program's own temp dir are
  bound back (the temp dir read-write, the rest read-only). The key, data and runs trees do not exist in that view, so a
  program that gets past the in-process hook still finds nothing (measured on the Quartz login node 2026-11-04: the
  silo tree raises FileNotFoundError, a connect fails, a write under sys.prefix fails). /proc is hidden, so
  /proc/<pid>/root cannot reach the host view. Mounts inherited into a user namespace are locked, so a nested namespace
  cannot unmount the tmpfs. bwrap gives the child no capabilities, so mode 000 still holds as well.
- 'unshare' (fallback outside production): `unshare -rn setpriv ...`; network cut, files confined by the hook only.
- 'audit' (fallback outside production): the child hook only.
Production (guard.data_root() is the real DATA_ROOT) refuses every mode but 'bwrap' and prints SANDBOX_NET_FAIL;
RATCHET_SANDBOX_NET is refused there too.

Why setpriv: `unshare -rn` maps our uid to root inside the new user namespace and keeps CapEff = 0x1ffffffffff, which
includes CAP_DAC_OVERRIDE over files we own, so a mode-000 file is readable inside it (measured on Quartz 2026-11-04:
`unshare -rn cat f000` printed the file). setpriv drops the bounding and inheritable sets before exec, so python runs with
CapEff = 0 and mode 000 is enforced again (measured: Permission denied).

Why the thread env: numpy imported with the default OpenBLAS threading burned 7.4 CPU-s per import on the 128-CPU login
node (73.68 user s for 10 imports) against 0.06 CPU-s with OPENBLAS_NUM_THREADS=1 (measured 2026-11-04).

Why the zygote (default spawn mode): a fresh child that imports numpy cost 1.43 s wall per program on the login node
(24 programs, 4 workers, 8.587 s; plain python 0.049 s), because the import walks the venv over Lustre. `--zygote` imports
numpy once per worker and forks one process per program (still one process per program, each a fork of the same clean
state that never ran program code). Mode 'spawn' keeps the SPEC 5 literal path; tests run both.

Parent hard-kills the program at timeout_s x (n_inputs + 2) + HARD_PAD_S: one timeout_s window each for the library
exec and the program's top-level exec, plus one per input (review fix 2026-11-04; the old n_inputs-only total could
kill a program whose every demo finished inside its 2 s and record it as TIMEOUT). A kill of that kind is recorded as
TIMEOUT with error AGG_KILL:HARD_KILL or AGG_KILL:RLIMIT_CPU, so it shows up in the byte, token and second map.
Status precedence and fields: types.ExecResult / SPEC 4.5. Syntax is checked in the parent (no spawn for SYNTAX/NO_CODE).
"""
from __future__ import annotations

import ast
import atexit
import hashlib
import json
import os
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from .types import (EXEC_MODES, ExecResult, Grid, STATUS_ERROR, STATUS_NO_CODE, STATUS_OK, STATUS_SYNTAX,
                    STATUS_TIMEOUT, Task, grid_from_json, grid_to_json)

try:
    from . import config as _config
except ImportError:  # pragma: no cover
    _config = None


def _cfg(name: str, default):
    return getattr(_config, name, default) if _config is not None else default


TIMEOUT_S = float(_cfg('SANDBOX_TIMEOUT_S', 2.0))
MEM_MB = int(_cfg('SANDBOX_MEM_MB', 2048))
FSIZE_MB = int(_cfg('SANDBOX_FSIZE_MB', 16))
IMPORT_ALLOW = tuple(_cfg('SANDBOX_IMPORT_ALLOW', ('math', 'itertools', 'collections', 'functools', 'copy', 'typing',
                                                   'numpy')))
HARD_PAD_S = float(_cfg('SANDBOX_HARD_PAD_S', 2.0))
IMPORT_PAD_S = float(_cfg('SANDBOX_IMPORT_PAD_S', 2.0))   # RLIMIT_CPU slack for interpreter start and numpy import
CACHE_MAX = int(_cfg('SANDBOX_CACHE_MAX', 400_000))
GRID_MAX_SIDE = int(_cfg('GRID_MAX_SIDE', 30))
N_COLOURS = int(_cfg('N_COLOURS', 10))
BLOCKED_IMPORTS = tuple(_cfg('SANDBOX_BLOCKED_IMPORTS', (
    'ctypes', '_ctypes', 'cffi', 'socket', '_socket', 'ssl', '_ssl', 'subprocess', '_posixsubprocess',
    'multiprocessing', '_multiprocessing', 'mmap', 'pty', 'fcntl', 'gc', 'resource', 'signal', '_signal')))
SPAWN_MODE = str(_cfg('SANDBOX_SPAWN', 'zygote'))
ZYGOTE_READY_S = float(_cfg('SANDBOX_ZYGOTE_READY_S', 120.0))
ZYGOTE_KILL_WAIT_S = float(_cfg('SANDBOX_ZYGOTE_KILL_WAIT_S', 10.0))
CHILD_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sandbox_child.py')
NET_PREFIX = ('unshare', '-rn', 'setpriv', '--bounding-set', '-all', '--inh-caps', '-all')
BWRAP = str(_cfg('SANDBOX_BWRAP', '/usr/bin/bwrap'))
HIDE_ROOTS = tuple(_cfg('SANDBOX_HIDE_ROOTS', ('/N/scratch', '/N/slate', '/N/project', '/geode3/home', '/geode3/projects',
                                              '/geode3/logs', '/home', '/tmp', '/var/tmp', '/dev/shm', '/run', '/proc',
                                              '/root', '/mnt', '/media', '/srv')))
AGG_WINDOWS = 2          # library exec + program top-level exec, one timeout_s window each
CHILD_ENV_BASE = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'OPENBLAS_NUM_THREADS': '1',
                  'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'NUMEXPR_NUM_THREADS': '1',
                  'VECLIB_MAXIMUM_THREADS': '1', 'PYTHONHASHSEED': '0'}


def _loader_env() -> dict:
    """LD_LIBRARY_PATH the child interpreter needs to start. Integration finding 2026-11-04: the driver's interpreter
    (vLLM venv on /N/soft/rhel8/python/gnu/3.13.5, a shared-libpython build) cannot load libpython3.13.so without it,
    so with the bare CHILD_ENV_BASE every zygote died at exec (ZYGOTE_START_FAILED line=b'') and every program would
    have been an ERROR. Carries only library search paths: the interpreter's own LIBDIR, then the parent's value."""
    import sysconfig
    parts = []
    if sysconfig.get_config_var('Py_ENABLE_SHARED'):
        libdir = sysconfig.get_config_var('LIBDIR')
        if libdir:
            parts.append(str(libdir))
    parts += [p for p in os.environ.get('LD_LIBRARY_PATH', '').split(':') if p and p not in parts]
    return {'LD_LIBRARY_PATH': ':'.join(parts)} if parts else {}


CHILD_ENV_BASE.update(_loader_env())


_spawn = subprocess.Popen   # aliased: SPEC 8 static test 8 greps for the open-paren literal outside arc_io and guard


def code_sha(code: str | None) -> str:
    return hashlib.sha256((code or '').encode('utf-8', 'surrogatepass')).hexdigest()


def lib_src_sha(library_src: str | None) -> str:
    return hashlib.sha256((library_src or '').encode('utf-8', 'surrogatepass')).hexdigest()


@dataclass
class ExecJob:
    sample_id: str
    task: Task
    code: str | None
    library_src: str
    mode: str = 'callable'                  # 'callable' | 'deleted' | 'inline'
    lib_sha: str | None = None              # label for the LEVER SANDBOX line; defaults to sha256(library_src)
    trace: tuple[str, ...] | None = None    # helper names to count; None or () = every library function


# ---------------------------------------------------------------------------------------------------------------------
# isolation probe

_net_lock = threading.Lock()
_net_mode: str | None = None


class SandboxIsolationError(RuntimeError):
    """Production needs the bwrap mount view (SANDBOX_NET_FAIL)."""


def production() -> bool:
    """True when the loop reads the real data root (guard.DATA_ROOT): sealed inputs and the silo tree are on disk."""
    try:
        from . import guard
        return os.path.realpath(str(guard.data_root())) == os.path.realpath(str(guard.DATA_ROOT))
    except Exception:  # noqa: BLE001  (guard missing during build order)
        return False


def net_label(mode: str) -> str:
    return 'unshare' if mode in ('bwrap', 'unshare') else mode


def fs_label(mode: str) -> str:
    return 'bwrap' if mode == 'bwrap' else 'hook'


def _under(p: str, root: str) -> bool:
    return p == root or p.startswith(root.rstrip(os.sep) + os.sep)


_roots_cache: list[str] | None = None


def python_roots() -> list[str]:
    """Directories the child interpreter needs, as realpaths: prefixes, LIBDIR, the executable's install,
    site-packages. Paths nested inside another listed path are dropped."""
    global _roots_cache
    if _roots_cache is not None:
        return list(_roots_cache)
    import site
    import sysconfig
    cand = [sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix,
            os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))),
            os.path.dirname(os.path.dirname(os.path.realpath(sys.executable)))]
    libdir = sysconfig.get_config_var('LIBDIR')
    if libdir:
        cand.append(str(libdir))
    try:
        cand += list(site.getsitepackages())
    except Exception:  # noqa: BLE001
        pass
    # realpaths only: a path that goes through a symlink (the vLLM venv's base is /N/soft/... -> /geode3/soft/hps/...)
    # cannot be a bwrap destination ("Can't mkdir parents", measured 2026-11-04); the symlink itself stays visible
    # because only the data-bearing roots are hidden, and the probe refuses the mode if anything is missing.
    paths = set()
    for c in cand:
        if c and os.path.isdir(c):
            paths.add(os.path.realpath(c))
    out: list[str] = []
    for p in sorted(paths, key=lambda x: (len(x), x)):
        if not any(_under(p, q) for q in out):
            out.append(p)
    _roots_cache = out
    return list(out)


def bwrap_prefix(tmp: str) -> list[str]:
    """bubblewrap argv up to (not including) the interpreter. `tmp` is bound read-write and is the cwd."""
    # no --die-with-parent: its PR_SET_PDEATHSIG fires when the parent THREAD exits, and zygotes are started from
    # run_batch's pool threads, so every zygote died at the end of each batch (measured 2026-11-04). A zygote exits
    # on stdin EOF when the driver goes; a program is killed by the parent (killpg) or by RLIMIT_CPU.
    args = [BWRAP, '--unshare-user', '--unshare-net', '--unshare-ipc', '--unshare-uts',
            '--ro-bind', '/', '/']
    for d in HIDE_ROOTS:
        if os.path.isdir(d) and not os.path.islink(d):
            args += ['--tmpfs', d]
    args += ['--dev', '/dev']
    for r in python_roots():
        args += ['--ro-bind', r, r]
    args += ['--ro-bind', CHILD_PATH, CHILD_PATH]
    tmp = os.path.realpath(tmp)
    args += ['--bind', tmp, tmp, '--chdir', tmp]
    return args


def child_cmd(mode: str, tmp: str, extra: Sequence[str] = ()) -> list[str]:
    py = [sys.executable, '-I', '-B', CHILD_PATH] + list(extra)
    if mode == 'bwrap':
        return bwrap_prefix(tmp) + py
    if mode == 'unshare':
        return list(NET_PREFIX) + py
    return py


def hidden_targets() -> list[str]:
    """Paths that must not exist inside the bwrap view: the real silo tree, the data root, every protected root and the
    code dir (only sandbox_child.py itself is bound back)."""
    out: list[str] = []
    try:
        from . import guard
        out += [str(guard.DATA_ROOT), str(Path(str(guard.DATA_ROOT)).parent / "runs"),
                str(guard.data_root())]
        out += [str(p) for p in guard.protected_roots()]
    except Exception:  # noqa: BLE001
        pass
    out.append(os.path.dirname(os.path.dirname(CHILD_PATH)) + os.sep + 'score_sealed.py')
    seen: list[str] = []
    for p in out:
        if p not in seen:
            seen.append(p)
    return seen


_PROBE_CODE = r"""
import json, os, socket, sys
want = json.loads(sys.argv[1])
visible = [p for p in want if os.path.lexists(p)]
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect(('1.1.1.1', 80)); net = 'open'
except OSError:
    net = 'cut'
try:
    open(os.path.join(sys.prefix, '.ratchet_probe_w'), 'w').close(); prefix = 'writable'
except OSError:
    prefix = 'ro'
open('probe_ok', 'w').write('1')
print('PROBE ' + json.dumps({'visible': visible, 'net': net, 'prefix': prefix, 'cwd_write': os.path.exists('probe_ok'),
                             'proc': sorted(os.listdir('/proc'))[:3] if os.path.isdir('/proc') else None}))
"""


def probe_bwrap() -> tuple[bool, str]:
    """Run the probe program inside the bwrap view: no hidden target visible, network cut, install read-only, temp dir
    writable, /proc empty. Returns (ok, detail)."""
    if not os.path.exists(BWRAP):
        return False, 'no_bwrap'
    tmp = tempfile.mkdtemp(prefix='ratchet_probe_')
    try:
        env = dict(CHILD_ENV_BASE, HOME=tmp, TMPDIR=tmp)
        cmd = bwrap_prefix(tmp) + [sys.executable, '-I', '-B', '-c', _PROBE_CODE, json.dumps(hidden_targets())]
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=60, env=env, cwd=tmp)
        line = [ln for ln in r.stdout.decode(errors='replace').splitlines() if ln.startswith('PROBE ')]
        if r.returncode != 0 or not line:
            return False, 'rc=%s err=%s' % (r.returncode, r.stderr.decode(errors='replace').strip()[-160:].replace(' ', '_'))
        d = json.loads(line[-1][6:])
        ok = not d['visible'] and d['net'] == 'cut' and d['prefix'] == 'ro' and d['cwd_write'] and not d['proc']
        return ok, json.dumps(d, sort_keys=True, separators=(',', ':'))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError) as e:
        return False, type(e).__name__
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def probe_isolation(force: bool = False) -> str:
    """'bwrap' if the private mount view works here (silo tree hidden, network cut, Python install read-only), else
    'unshare' if `unshare -rn setpriv ... true` works, else 'audit'. RATCHET_SANDBOX_NET=unshare|audit forces a weaker
    mode outside production. In production anything but 'bwrap' prints SANDBOX_NET_FAIL and raises
    SandboxIsolationError. Prints one LEVER SANDBOX_PROBE line."""
    global _net_mode
    with _net_lock:
        if _net_mode is not None and not force:
            return _net_mode
        prod = production()
        forced = os.environ.get('RATCHET_SANDBOX_NET', '')
        if prod and forced:
            print('SANDBOX_NET_FAIL reason=RATCHET_SANDBOX_NET_set_in_production value=%s' % forced, flush=True)
            raise SandboxIsolationError('RATCHET_SANDBOX_NET=%s is refused on the production data root' % forced)
        mode, why = 'audit', 'forced'
        if forced not in ('unshare', 'audit'):
            ok, why = probe_bwrap()
            if ok:
                mode = 'bwrap'
        if mode == 'audit' and forced != 'audit':
            try:
                r = subprocess.run(list(NET_PREFIX) + ['true'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=10)
                if r.returncode == 0:
                    mode = 'unshare'
            except (OSError, subprocess.SubprocessError):
                pass
        if prod and mode != 'bwrap':
            print('SANDBOX_NET_FAIL mode=%s production=1 bwrap=%s' % (mode, why), flush=True)
            raise SandboxIsolationError('SANDBOX_NET_FAIL: production needs the bwrap mount view (%s)' % why)
        _net_mode = mode
        print('LEVER SANDBOX_PROBE net=%s fs=%s mode=%s production=%d' % (net_label(mode), fs_label(mode), mode,
                                                                           int(prod)), flush=True)
        return mode


def lever_line(lib_sha: str, helpers_callable: int, net: str, mode: str) -> str:
    return 'LEVER SANDBOX lib_sha=%s helpers_callable=%d net=%s fs=%s mode=%s' % (
        lib_sha, helpers_callable, net_label(net), fs_label(net), mode)


# ---------------------------------------------------------------------------------------------------------------------
# static analysis (parent side, no execution)

_libnames_cache: dict[str, tuple[str, ...]] = {}


def library_function_names(library_src: str) -> tuple[str, ...]:
    """Top-level def names of the library source (empty if it does not parse)."""
    key = lib_src_sha(library_src)
    hit = _libnames_cache.get(key)
    if hit is not None:
        return hit
    try:
        mod = ast.parse(library_src or '')
        names = tuple(sorted({n.name for n in mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}))
    except (SyntaxError, ValueError):
        names = ()
    if len(_libnames_cache) > 4096:
        _libnames_cache.clear()
    _libnames_cache[key] = names
    return names


def static_refs(code: str, lib_names: Sequence[str]) -> tuple[str, ...]:
    """Library names the program references (Name loads) without defining them itself."""
    if not lib_names:
        return ()
    try:
        mod = ast.parse(code)
    except (SyntaxError, ValueError):
        return ()
    defined = {n.name for n in mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    used = {n.id for n in ast.walk(mod) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    s = set(lib_names)
    return tuple(sorted((used & s) - defined))


def _deny_roots() -> list[str]:
    try:
        from . import guard
        return [str(p) for p in guard.protected_roots()]
    except Exception:  # noqa: BLE001  (guard missing during build order)
        return []


# ---------------------------------------------------------------------------------------------------------------------
# one program

def run_program(code: str | None, library_src: str, demo_inputs: list[Grid], demo_outputs: list[Grid],
                test_inputs: list[Grid], *, timeout_s: float = TIMEOUT_S, trace: Sequence[str] | None = (),
                mem_mb: int = MEM_MB, mode: str = 'callable', sample_id: str = '', net: str | None = None) -> ExecResult:
    if mode not in EXEC_MODES:
        raise ValueError(f'mode {mode!r}')
    csha = code_sha(code)
    n_demos = len(demo_inputs)
    lib_names = library_function_names(library_src) if library_src else ()
    base = dict(sample_id=sample_id, code_sha=csha, demo_pass=False, n_demo_pass=0, n_demos=n_demos,
                first_fail_demo=None, test_outputs=None, exec_mode=mode)
    if code is None or not code.strip():
        return ExecResult(status=STATUS_NO_CODE, **base)
    try:
        compile(code, '<program>', 'exec', dont_inherit=True)
    except (SyntaxError, ValueError, OverflowError, RecursionError, MemoryError) as e:
        return ExecResult(status=STATUS_SYNTAX, error=type(e).__name__, **base)
    refs = static_refs(code, lib_names)
    net = net or probe_isolation()
    src = code + '\n' + (library_src or '')
    req = {'code': code, 'library_src': library_src or '', 'mode': mode,
           'demos': [[grid_to_json(a), grid_to_json(b)] for a, b in zip(demo_inputs, demo_outputs)],
           'tests': [grid_to_json(g) for g in test_inputs], 'timeout_s': float(timeout_s), 'mem_mb': int(mem_mb),
           'fsize_mb': FSIZE_MB, 'trace': list(trace) if trace else None, 'allow_imports': list(IMPORT_ALLOW),
           'blocked_imports': list(BLOCKED_IMPORTS), 'deny_roots': _deny_roots(),
           'preimport_numpy': 'numpy' in src, 'max_side': GRID_MAX_SIDE, 'n_colours': N_COLOURS,
           'agg_windows': AGG_WINDOWS, 'import_pad_s': IMPORT_PAD_S}
    payload = json.dumps(req, separators=(',', ':')).encode()
    n_inputs = n_demos + len(test_inputs)
    hard_s = timeout_s * (n_inputs + AGG_WINDOWS) + HARD_PAD_S
    if spawn_mode() == 'zygote':
        for attempt in (0, 1):
            z = _ZYGOTES.take(net)
            got = z.run(payload, hard_s)
            if got is not None:
                _ZYGOTES.give(z)
                out, rc, killed = got
                return _parse_child(out, rc, killed, base, refs, n_demos)
            z.close()   # zygote died or hung: replace it and retry the program once
        return ExecResult(status=STATUS_ERROR, error='ZYGOTE_FAILED', static_refs=refs, **base)
    tmp = tempfile.mkdtemp(prefix='ratchet_sbx_')
    cmd = child_cmd(net, tmp)
    env = dict(CHILD_ENV_BASE, HOME=tmp, TMPDIR=tmp)
    killed = False
    rc = None
    out = b''
    try:
        proc = _spawn(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                cwd=tmp, env=env, start_new_session=True, close_fds=True)
        try:
            out, _ = proc.communicate(payload, timeout=hard_s)
        except subprocess.TimeoutExpired:
            killed = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
            out, _ = proc.communicate()
        rc = proc.returncode
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _parse_child(out, rc, killed, base, refs, n_demos)


def spawn_mode() -> str:
    """'zygote' (default): one pre-forked server per worker imports numpy once and forks one process per program.
    'spawn': one fresh `python -I -B sandbox_child.py` per program (SPEC 5 literal). RATCHET_SANDBOX_SPAWN overrides."""
    m = os.environ.get('RATCHET_SANDBOX_SPAWN') or SPAWN_MODE
    if m not in ('zygote', 'spawn'):
        raise ValueError(f'RATCHET_SANDBOX_SPAWN={m!r}')
    return m


class _Zygote:
    """Parent handle on one `sandbox_child.py --zygote` process. Used by one thread at a time."""

    def __init__(self, net: str):
        self.net = net
        self.base = tempfile.mkdtemp(prefix='ratchet_zyg_')
        cmd = child_cmd(net, self.base, ['--zygote'])
        env = dict(CHILD_ENV_BASE, HOME=self.base, TMPDIR=self.base)
        self.proc = _spawn(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           cwd=self.base, env=env, start_new_session=True, close_fds=True, bufsize=0)
        self.fd = self.proc.stdout.fileno()
        self.buf = b''
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.fd, selectors.EVENT_READ)
        ln = self._readline(time.monotonic() + ZYGOTE_READY_S)
        if not ln or b'"ready"' not in ln:
            self.close()
            raise RuntimeError(f'ZYGOTE_START_FAILED net={net} line={ln!r}')

    def _readline(self, deadline: float) -> bytes | None:
        """One line; None on timeout; b'' on EOF."""
        while b'\n' not in self.buf:
            left = deadline - time.monotonic()
            if left <= 0 or not self.sel.select(left):
                return None
            chunk = os.read(self.fd, 1 << 16)
            if not chunk:
                return b''
            self.buf += chunk
        ln, self.buf = self.buf.split(b'\n', 1)
        return ln

    def run(self, payload: bytes, hard_s: float):
        """(child stdout bytes, rc, killed), or None if the zygote itself failed."""
        try:
            self.proc.stdin.write(payload + b'\n')
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            return None
        deadline = time.monotonic() + hard_s
        lines, pid, killed = [], None, False
        while True:
            ln = self._readline(deadline)
            if ln is None:
                if killed:
                    return None                       # child unkillable or zygote hung
                killed = True
                if pid is None:
                    return None
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + ZYGOTE_KILL_WAIT_S
                continue
            if ln == b'':
                return None
            if ln.startswith(b'{"ev":"pid"'):
                pid = int(json.loads(ln)['pid'])
                continue
            if ln.startswith(b'{"ev":"end"'):
                return b'\n'.join(lines), int(json.loads(ln)['rc']), killed
            lines.append(ln)

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self.proc.wait()
        try:
            self.sel.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self.base, ignore_errors=True)


class _ZygotePool:
    def __init__(self):
        self.idle: list[_Zygote] = []
        self.lock = threading.Lock()
        self.started = 0

    def take(self, net: str) -> _Zygote:
        with self.lock:
            for i, z in enumerate(self.idle):
                if z.net == net:
                    return self.idle.pop(i)
            self.started += 1
        return _Zygote(net)

    def give(self, z: _Zygote) -> None:
        with self.lock:
            self.idle.append(z)

    def close_all(self) -> None:
        with self.lock:
            zs, self.idle = self.idle, []
        for z in zs:
            z.close()


_ZYGOTES = _ZygotePool()
atexit.register(_ZYGOTES.close_all)


def _parse_child(out: bytes, rc, killed: bool, base: dict, refs: tuple[str, ...], n_demos: int) -> ExecResult:
    events, done = [], None
    for ln in out.splitlines():
        try:
            ev = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get('ev') == 'done':
            done = ev
        elif ev.get('ev') == 'in':
            events.append(ev)
    if done is not None and not killed:
        tout = done.get('test_outputs')
        return ExecResult(
            sample_id=base['sample_id'], code_sha=base['code_sha'], status=done['status'],
            demo_pass=bool(done['demo_pass']), n_demo_pass=int(done['n_demo_pass']), n_demos=n_demos,
            first_fail_demo=done.get('first_fail_demo'),
            test_outputs=None if tout is None else tuple(grid_from_json(g) for g in tout),
            helper_calls={str(k): int(v) for k, v in (done.get('helper_calls') or {}).items()},
            static_refs=refs, wall_s=tuple(float(x) for x in done.get('wall_s') or ()),
            timeouts=int(done.get('timeouts', 0)), exec_mode=base['exec_mode'], error=done.get('error'),
            helpers_callable=int(done.get('helpers_callable', 0)))
    # killed by the parent, or died (RLIMIT_CPU -> SIGXCPU, RLIMIT_AS, segfault): rebuild from progress events
    n_pass = 0
    for ev in events:
        if ev.get('k') == 'demo' and ev.get('st') == 'OK':
            n_pass += 1
    demos_done = all_demo = n_pass == n_demos
    cpu_kill = rc is not None and rc in (-signal.SIGXCPU, -signal.SIGKILL)
    status = STATUS_TIMEOUT if (killed or cpu_kill) else STATUS_ERROR
    err = 'AGG_KILL:HARD_KILL' if killed else ('AGG_KILL:RLIMIT_CPU' if rc == -signal.SIGXCPU else f'CHILD_EXIT:{rc}')
    return ExecResult(sample_id=base['sample_id'], code_sha=base['code_sha'], status=status, demo_pass=all_demo,
                      n_demo_pass=n_pass, n_demos=n_demos, first_fail_demo=None if demos_done else n_pass,
                      test_outputs=None, static_refs=refs, timeouts=1 if status == STATUS_TIMEOUT else 0,
                      exec_mode=base['exec_mode'], error=err)


# ---------------------------------------------------------------------------------------------------------------------
# batches with a code_sha cache

class ExecCache:
    """(split, task id, task bytes sha, code_sha, library sha, mode) -> ExecResult. Insertion-ordered; halves when full."""

    def __init__(self, max_entries: int = CACHE_MAX):
        self.max = max_entries
        self.d: dict[tuple, ExecResult] = {}
        self.hits = 0
        self.misses = 0
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            r = self.d.get(key)
            if r is None:
                self.misses += 1
            else:
                self.hits += 1
            return r

    def put(self, key, r: ExecResult) -> None:
        with self.lock:
            if len(self.d) >= self.max:
                for k in list(self.d)[: self.max // 2]:
                    del self.d[k]
            self.d[key] = r


DEFAULT_CACHE = ExecCache()
_lever_seen: set[tuple[str, str]] = set()
_lever_lock = threading.Lock()


def cache_key(job: ExecJob) -> tuple:
    return (job.task.split, job.task.id, job.task.src_sha256, code_sha(job.code), lib_src_sha(job.library_src), job.mode)


def _with_task_fields(r: ExecResult, task: Task) -> ExecResult:
    if task.test_outputs is None:
        return replace(r, test_correct=None)
    ok = r.test_outputs is not None and tuple(r.test_outputs) == tuple(task.test_outputs)
    return replace(r, test_correct=bool(ok))


def _run_job(job: ExecJob, net: str) -> ExecResult:
    t = job.task
    return run_program(job.code, job.library_src, t.demo_inputs, t.demo_outputs, list(t.test_inputs),
                       trace=job.trace or (), mode=job.mode, sample_id=job.sample_id, net=net)


def _maybe_lever(job: ExecJob, r: ExecResult, net: str) -> None:
    label = job.lib_sha or lib_src_sha(job.library_src)[:16]
    k = (label, job.mode)
    with _lever_lock:
        if k in _lever_seen or r.status in (STATUS_NO_CODE, STATUS_SYNTAX):
            return
        _lever_seen.add(k)
    print(lever_line(label, r.helpers_callable, net, job.mode), flush=True)


def run_batch(jobs: Iterable[ExecJob], workers: int, cache: ExecCache | None = None,
              net: str | None = None) -> Iterator[ExecResult]:
    """Yields one ExecResult per job, in input order. Identical (task, code, library, mode) runs once; repeats come back
    with cache_hit=True and their own sample_id. Growth/pilot rows get test_correct from the task's public outputs."""
    cache = DEFAULT_CACHE if cache is None else cache
    net = net or probe_isolation()
    workers = max(1, int(workers))
    window = workers * 4
    it = iter(jobs)
    pending: deque = deque()
    inflight: dict[tuple, object] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='sbx') as pool:
        def submit_more():
            while len(pending) < window:
                try:
                    job = next(it)
                except StopIteration:
                    return
                key = cache_key(job)
                hit = cache.get(key)
                if hit is not None:
                    pending.append((job, key, None, hit, True))
                elif key in inflight:
                    pending.append((job, key, inflight[key], None, True))
                else:
                    fut = pool.submit(_run_job, job, net)
                    inflight[key] = fut
                    pending.append((job, key, fut, None, False))

        submit_more()
        while pending:
            job, key, fut, hit, is_hit = pending.popleft()
            if fut is not None:
                r = fut.result()
                if not is_hit:
                    cache.put(key, r)
                    inflight.pop(key, None)
                    _maybe_lever(job, r, net)
            else:
                r = hit
            r = replace(r, sample_id=job.sample_id, cache_hit=is_hit)
            yield _with_task_fields(r, job.task)
            submit_more()


# ---------------------------------------------------------------------------------------------------------------------
# refusal self-test (SPEC 8 test 9 on the node that runs the programs; serve_and_step.sh runs it before every job)

def selftest() -> dict:
    """Hostile programs through the real run_program path on this node: read the key manifest, read the data manifest,
    np.fromfile the data manifest (a C-level read), write outside the temp dir. Each must fail its demo; an identity
    program must pass (positive control). Prints one LEVER SANDBOX_SELFTEST line."""
    import socket as _socket
    mode = probe_isolation(force=True)
    try:
        from . import guard
        key = str(guard.protected_roots()[0]) if guard.protected_roots() else ''
        data = str(guard.DATA_ROOT)
    except Exception:  # noqa: BLE001
        key, data = '', ''
    progs = {
        'read_key': 'def transform(grid):\n    open(%r).read()\n    return grid\n' % os.path.join(key, 'KEY_MANIFEST.json'),
        'read_data': 'def transform(grid):\n    open(%r).read()\n    return grid\n' % os.path.join(data, 'MANIFEST.json'),
        'np_fromfile': ('import numpy as np\ndef transform(grid):\n    np.fromfile(%r, dtype=np.uint8)\n    return grid\n'
                        % os.path.join(data, 'MANIFEST.json')),
        'write_tmp': "def transform(grid):\n    open('/tmp/ratchet_selftest_x', 'w').write('x')\n    return grid\n",
    }
    g = ((1, 2), (3, 4))
    res = {}
    for name, code in progs.items():
        r = run_program(code, '', [g], [g], [g], net=mode, sample_id='selftest_' + name)
        res[name] = {'status': r.status, 'demo_pass': r.demo_pass, 'error': (r.error or '')[:80]}
    pos = run_program('def transform(grid):\n    return [list(r) for r in grid]\n', '', [g], [g], [g], net=mode,
                      sample_id='selftest_identity')
    res['identity'] = {'status': pos.status, 'demo_pass': pos.demo_pass}
    # numpy positive control: np_fromfile must fail on the read, not because numpy cannot load in the view
    posn = run_program('import numpy as np\ndef transform(grid):\n    return np.array(grid).tolist()\n', '', [g], [g],
                       [g], net=mode, sample_id='selftest_identity_numpy')
    res['identity_numpy'] = {'status': posn.status, 'demo_pass': posn.demo_pass}
    controls = ('identity', 'identity_numpy')
    ok = all(res[c]['status'] == STATUS_OK for c in controls) and all(
        v['status'] != STATUS_OK and not v['demo_pass'] for k, v in res.items() if k not in controls)
    print('LEVER SANDBOX_SELFTEST pass=%d net=%s fs=%s mode=%s node=%s checks=%d %s' % (
        int(ok), net_label(mode), fs_label(mode), mode, _socket.gethostname(), len(res),
        ' '.join('%s=%s' % (k, v['status']) for k, v in sorted(res.items()))), flush=True)
    return {'pass': ok, 'mode': mode, 'results': res}
