"""Sealed-read guard (SPEC section 8, layers 2 to 4).

- protected roots: KEY_ROOT plus any root added with add_protected_root or the RATCHET_KEY_ROOT env var. Add-only.
- install_audit_hook(): a sys.addaudithook hook (Python has no API to remove one) that refuses filesystem events whose
  path resolves (os.path.realpath: symlinks and '..' resolved) under a protected root, unless the process is unlocked.
- check_data_read(path): the allowlist the single loader (arc_io._read_json) calls before every data read.
- unlock: only score_sealed.py, run as __main__ from <code>/score_sealed.py, can obtain a proof (_issue_proof) and pass it
  to _unlock. guard._unlock(object()) raises.

This guards against accidents and against generated programs (which also run in a sandbox subprocess with its own hook and
see mode-000 key files). It is not a defence against loop code written to defeat it.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

KEY_ROOT = Path('/N/scratch/bsmensah/silo/ratchet/key')
DATA_ROOT = Path('/N/scratch/bsmensah/silo/ratchet/data')
SPLITS = ('growth', 'pilot', 'sealed', 'sealed_perturbed', 'arcagi2_sealed')

ENV_KEY_ROOT = 'RATCHET_KEY_ROOT'     # adds a protected root (tests, fake key); can never remove KEY_ROOT
ENV_DATA_ROOT = 'RATCHET_DATA_ROOT'   # adds an allowed data root (tests); protected roots still win

# Events refused under a protected root while locked. Path-like args of each event are all checked.
GUARDED_EVENTS = frozenset({
    'open', 'os.listdir', 'os.scandir', 'os.chmod', 'os.chown', 'os.rename', 'os.remove', 'os.rmdir', 'os.mkdir',
    'os.symlink', 'os.link', 'os.truncate', 'os.utime', 'os.chdir', 'os.chflags', 'os.lchflags',
    'shutil.copyfile', 'shutil.copymode', 'shutil.copystat', 'shutil.copytree', 'shutil.move', 'shutil.rmtree',
    'shutil.chown', 'shutil.make_archive', 'shutil.unpack_archive', 'glob.glob', 'glob.glob/2', 'os.walk',
    'pathlib.Path.glob', 'pathlib.Path.rglob',
})


class SealedReadRefused(PermissionError):
    pass


def _real(p) -> str:
    if isinstance(p, bytes):
        p = os.fsdecode(p)
    return os.path.normcase(os.path.realpath(os.fspath(p)))


_lock = threading.Lock()
_protected: list[str] = []
_data_roots: list[str] = []
_hook_installed = False
_unlocked = False
_proofs: set[int] = set()
_proof_objs: list[object] = []
_tls = threading.local()


def _under(path_real: str, root_real: str) -> bool:
    return path_real == root_real or path_real.startswith(root_real.rstrip(os.sep) + os.sep)


def protected_roots() -> tuple[Path, ...]:
    return tuple(Path(r) for r in _protected)


def add_protected_root(p) -> None:
    r = _real(p)
    with _lock:
        if r not in _protected:
            _protected.append(r)


def data_roots() -> tuple[Path, ...]:
    return tuple(Path(r) for r in _data_roots)


def add_data_root(p) -> None:
    """Allow reads under <p>/<split>. Add-only; a protected root inside it stays refused."""
    r = _real(p)
    with _lock:
        if r not in _data_roots:
            _data_roots.append(r)


def key_root() -> Path:
    """The key directory score_sealed.py uses: RATCHET_KEY_ROOT if set (always also protected), else KEY_ROOT."""
    env = os.environ.get(ENV_KEY_ROOT)
    return Path(_real(env)) if env else KEY_ROOT


def data_root() -> Path:
    env = os.environ.get(ENV_DATA_ROOT)
    return Path(_real(env)) if env else DATA_ROOT


def is_protected(path) -> bool:
    r = _real(path)
    return any(_under(r, root) for root in _protected)


def is_unlocked() -> bool:
    return _unlocked


def _path_args(event: str, args) -> list:
    out = []
    for a in args:
        if isinstance(a, (str, bytes, os.PathLike)):
            out.append(a)
    if event in ('os.listdir', 'os.scandir') and (not args or args[0] is None):
        out.append('.')
    return out


def _hook(event: str, args) -> None:
    if event not in GUARDED_EVENTS or _unlocked or not _protected:
        return
    if getattr(_tls, 'busy', False):
        return
    _tls.busy = True
    try:
        for a in _path_args(event, args):
            try:
                r = _real(a)
            except (TypeError, ValueError, OSError):
                continue
            for root in _protected:
                if _under(r, root):
                    raise SealedReadRefused(f'SEALED_READ_REFUSED event={event} path={r}')
    finally:
        _tls.busy = False


def install_audit_hook() -> None:
    """Idempotent. Registers KEY_ROOT and the env roots, then adds the audit hook once per process."""
    global _hook_installed
    add_protected_root(KEY_ROOT)
    env = os.environ.get(ENV_KEY_ROOT)
    if env:
        add_protected_root(env)
    add_data_root(DATA_ROOT)
    denv = os.environ.get(ENV_DATA_ROOT)
    if denv:
        add_data_root(denv)
    with _lock:
        if _hook_installed:
            return
        sys.addaudithook(_hook)
        _hook_installed = True


def hook_installed() -> bool:
    return _hook_installed


def check_data_read(path) -> Path:
    """Realpath must lie under <data root>/<split> for a split in SPLITS and under no protected root."""
    r = _real(path)
    for root in _protected:
        if _under(r, root):
            raise SealedReadRefused(f'SEALED_READ_REFUSED data read under protected root: {r}')
    for droot in _data_roots:
        for split in SPLITS:
            if _under(r, os.path.join(droot, split)) and r != os.path.join(droot, split):
                return Path(r)
    raise SealedReadRefused(f'DATA_READ_REFUSED not under an allowed data split: {r}')


# ---------------------------------------------------------------------------------------------------------------------
# unlock (only score_sealed.py)

class _Proof:
    __slots__ = ('purpose',)

    def __init__(self, purpose: str):
        self.purpose = purpose


def expected_score_path() -> str:
    """Realpath of <code>/score_sealed.py, where <code> is the directory that holds the ratchet package."""
    return _real(Path(__file__).resolve().parent.parent / 'score_sealed.py')


def _issue_proof(purpose: str) -> object:
    """Called by score_sealed.main. Refuses unless both the caller's file and __main__ are <code>/score_sealed.py."""
    want = expected_score_path()
    caller = sys._getframe(1).f_code.co_filename
    main = getattr(sys.modules.get('__main__'), '__file__', None)
    if main is None or _real(main) != want or _real(caller) != want:
        raise SealedReadRefused(f'UNLOCK_REFUSED main={main} caller={caller} want={want}')
    if purpose not in ('seal', 'score'):
        raise SealedReadRefused(f'UNLOCK_REFUSED purpose={purpose}')
    p = _Proof(purpose)
    with _lock:
        _proofs.add(id(p))
        _proof_objs.append(p)
    return p


def _unlock(proof: object) -> None:
    global _unlocked
    if not isinstance(proof, _Proof) or id(proof) not in _proofs or proof not in _proof_objs:
        raise SealedReadRefused('UNLOCK_REFUSED: proof was not issued by guard._issue_proof')
    _unlocked = True


def _relock() -> None:
    global _unlocked
    _unlocked = False
