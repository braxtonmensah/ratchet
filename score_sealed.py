#!/usr/bin/env python3
"""score_sealed.py: the only code that opens the sealed key (PREREG 2, SPEC 8 layers 1, 4 and 6).

  python score_sealed.py seal  --arcagi1 <clone> [--arcagi2 <clone>] [--test]
  python score_sealed.py seal-arcagi2 --arcagi2 <clone> [--test]   (adds the ARC-AGI-2 key to an existing seal)
  python score_sealed.py score --run <dir> --condition primary|knockout|arcagi2 --freeze-sha <hex> --submit-sha <hex>
                               [--amendment <id>] [--test]
  python score_sealed.py freeze-arcagi2 --run <dir>      (no key access; freezes ARC-AGI-2 submissions)

--test is required to use a key or data root other than the real ones (RATCHET_KEY_ROOT / RATCHET_DATA_ROOT), and
refused without such an override, so a test variable left in a shell cannot redirect a production read (review fix
2026-11-04).

Key-read log (review fix 2026-11-04): besides runs/<run>/scores/KEY_READS.jsonl, every read is appended to
<key root>/KEY_READS.jsonl, which only this file writes, only while unlocked, and which sits at mode 000 like every key
file. A condition that already has a row there (from any run, any freeze) is refused, unless --amendment <id> names an
`AMENDMENT <id>` that PREREG.md carries and no earlier row used; the id is recorded in the row. Deleting the run-local
file or scoring a fresh run dir therefore no longer buys another sealed read (PREREG 2: once per frozen library). A
retired harness (runs/ATTEMPTS.json, PREREG 9) is refused too. Every freeze the read relies on must carry the lead's
ack (`freeze/<NAME>.ack` holding the freeze file's sha256, written by `ratchet freeze --ack` after the commit).

seal: verifies the ARC-AGI-1 commit and both id-list sha256 values, writes data/growth (original bytes), inputs-only
data/sealed, key/arcagi1/<id>.json (mode 000), then moves the clone's data/evaluation AND its .git (git objects hold
every evaluation output) into the key. For ARC-AGI-2 it moves the clone's whole data/ (its training split contains
ARC-AGI-1 evaluation tasks with outputs) and .git into the key.

score: refuses unless __main__ is <code>/score_sealed.py, FREEZE.json and the condition's submission freeze match the
given sha256 values and every listed file still matches, every submissions.json on disk is listed, every key file is
mode 000, and KEY_READS.jsonl has no earlier read of this condition. It logs one KEY_READS row, chmods each key file
400, reads it, sets it back to 000, and writes only booleans, ids and counts to scores/.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import ratchet  # noqa: E402,F401  installs the audit hook
from ratchet import guard  # noqa: E402
from ratchet.e_util import (as_grid, canonical_json, cfg, get, iter_jsonl, now_et, read_json, sha256_bytes,  # noqa: E402
                            sha256_file, write_json_atomic)

CONDITIONS = ('primary', 'knockout', 'arcagi2')
SUBMIT_FREEZE_FILE = {'primary': 'SUBMIT_FREEZE.json', 'knockout': 'KO_FREEZE.json', 'arcagi2': 'A2_SUBMIT_FREEZE.json'}
GLOBAL_READS = 'KEY_READS.jsonl'          # under the key root, mode 000 at rest, written only here while unlocked
KEY_SUBDIR = {'primary': 'arcagi1', 'knockout': 'arcagi1', 'arcagi2': 'arcagi2'}
KO_MODES = ('delete', 'inline')


class ScoreRefused(RuntimeError):
    pass


# ---------------------------------------------------------------------------------------------------------------------
# small helpers

def _ids_sha(ids) -> str:
    return sha256_bytes(''.join(f'{i}\n' for i in sorted(ids)).encode())


def _git_head(clone: Path) -> str | None:
    try:
        out = subprocess.run(['git', '-C', str(clone), 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=60)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    head = clone / '.git' / 'HEAD'
    if not head.exists():
        return None
    ref = head.read_text().strip()
    if not ref.startswith('ref:'):
        return ref
    ref = ref.split(None, 1)[1]
    rp = clone / '.git' / ref
    if rp.exists():
        return rp.read_text().strip()
    packed = clone / '.git' / 'packed-refs'
    if packed.exists():
        for line in packed.read_text().splitlines():
            if line.endswith(' ' + ref):
                return line.split()[0]
    return None


def _chmod_tree(root: Path, file_mode: int = 0o000, dir_mode: int = 0o700) -> int:
    n = 0
    for dp, dns, fns in os.walk(root):
        os.chmod(dp, dir_mode)
        for fn in fns:
            os.chmod(os.path.join(dp, fn), file_mode)
            n += 1
    return n


def _mkdir700(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)
    os.chmod(p, 0o700)


def _write_key_file(p: Path, obj) -> str:
    data = (canonical_json(obj) + '\n').encode()
    with open(p, 'wb') as f:
        f.write(data)
    os.chmod(p, 0o000)
    return sha256_bytes(data)


def _read_key_file(p: Path) -> dict:
    os.chmod(p, 0o400)
    try:
        with open(p, 'rb') as f:
            return json.loads(f.read().decode())
    finally:
        os.chmod(p, 0o000)


def correct(sub, outputs) -> bool:
    """Some attempt equals all test outputs (SPEC 13 I9). `sub` is a Submission or its JSON dict; only the first
    PASS_AT attempts count."""
    want = tuple(as_grid(g) for g in outputs)
    for att in _attempts(sub)[:int(cfg('PASS_AT'))]:
        if tuple(as_grid(g) for g in get(att, 'outputs', ())) == want:
            return True
    return False


def _attempts(sub) -> list:
    return list(get(sub, 'attempts', ()) or ())


def _correct_attempt_ids(sub, outputs) -> list[str] | None:
    want = tuple(as_grid(g) for g in outputs)
    for att in _attempts(sub)[:int(cfg('PASS_AT'))]:
        if tuple(as_grid(g) for g in get(att, 'outputs', ())) == want:
            return list(get(att, 'sample_ids', ()) or ())
    return None


def parse_submissions(obj) -> dict[str, dict]:
    """task -> submission dict, from {'submissions': {...}|[...]}, {task: sub} or [sub, ...]."""
    if isinstance(obj, dict) and 'submissions' in obj:
        obj = obj['submissions']
    out: dict[str, dict] = {}
    if isinstance(obj, dict):
        for t, s in obj.items():
            if isinstance(s, dict) and 'attempts' in s:
                out[str(s.get('task', t))] = s
    elif isinstance(obj, list):
        for s in obj:
            if isinstance(s, dict) and 'attempts' in s:
                out[str(s['task'])] = s
    return out


def _resolve(run_dir: Path, p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else run_dir / q


_HEX64 = set('0123456789abcdef')


def _is_sha(v) -> bool:
    return isinstance(v, str) and len(v) == 64 and set(v) <= _HEX64


def freeze_entries(obj, run_dir: Path) -> dict[str, str]:
    """Every (file, sha256) pair a freeze JSON lists, keyed by resolved path. Recognised shapes:
    {"path"|"file": p, "sha256": h}; {"json": p, "sha256_json": h, "py": p, "sha256_py": h} (any K with sha256_K);
    {"<path ending .json/.py>": h}."""
    out: dict[str, str] = {}

    def visit(o):
        if isinstance(o, dict):
            for k in ('path', 'file'):
                if isinstance(o.get(k), str) and _is_sha(o.get('sha256')):
                    out[str(_resolve(run_dir, o[k]))] = o['sha256']
            for k, v in o.items():
                if isinstance(v, str) and _is_sha(o.get(f'sha256_{k}')):
                    out[str(_resolve(run_dir, v))] = o[f'sha256_{k}']
                if isinstance(k, str) and _is_sha(v) and (k.endswith(('.json', '.py', '.jsonl')) or '/' in k):
                    out[str(_resolve(run_dir, k))] = v
            for v in o.values():
                if isinstance(v, (dict, list)):
                    visit(v)
        elif isinstance(o, list):
            for v in o:
                visit(v)

    visit(obj)
    return out


def _submission_globs(condition: str) -> list[str]:
    if condition == 'primary':
        return ['sealed/sealed/*/seed_*/submissions.json', 'sealed/perturbed/*/seed_*/submissions.json']
    if condition == 'knockout':
        return ['knockout/*/seed_*/submissions.json']
    return ['sealed/arcagi2/*/seed_*/submissions.json']


def _on_disk_submissions(run_dir: Path, condition: str) -> list[Path]:
    out = []
    for g in _submission_globs(condition):
        out += [Path(p) for p in sorted(glob.glob(str(run_dir / g)))]
    return out


def _seeds(freeze: dict) -> tuple[int, ...]:
    return tuple(int(s) for s in (freeze.get('sealed_seeds') or cfg('SEALED_SEEDS')))


# ---------------------------------------------------------------------------------------------------------------------
# seal

def _seal_split(src_eval: Path, ids: list[str], data_out: Path, key_out: Path) -> dict[str, str]:
    """Write inputs-only task files to data_out and output-only key files (mode 000) to key_out. Returns key shas."""
    data_out.mkdir(parents=True, exist_ok=True)
    _mkdir700(key_out)
    shas = {}
    for i in ids:
        raw = (src_eval / f'{i}.json').read_bytes()
        obj = json.loads(raw.decode())
        tests = obj.get('test', [])
        sealed = {'train': obj['train'], 'test': [{'input': t['input']} for t in tests]}
        with open(data_out / f'{i}.json', 'w', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(sealed, separators=(',', ':')))
        shas[f'{key_out.name}/{i}.json'] = _write_key_file(
            key_out / f'{i}.json', {'id': i, 'test_outputs': [t['output'] for t in tests], 'src_sha256': sha256_bytes(raw)})
    return shas


def cmd_seal(arcagi1_clone: Path, arcagi2_clone: Path | None = None) -> None:
    proof = guard._issue_proof('seal')
    key = guard.key_root()
    data = guard.data_root()
    if os.path.exists(key / 'KEY_MANIFEST.json'):
        raise ScoreRefused(f'ALREADY_SEALED {key}/KEY_MANIFEST.json exists')
    a1 = Path(arcagi1_clone).resolve()
    head = _git_head(a1)
    if head != cfg('ARCAGI1_COMMIT'):
        raise ScoreRefused(f'ARCAGI1_COMMIT_MISMATCH head={head} want={cfg("ARCAGI1_COMMIT")}')
    train_ids = sorted(p.stem for p in (a1 / 'data' / 'training').glob('*.json'))
    eval_ids = sorted(p.stem for p in (a1 / 'data' / 'evaluation').glob('*.json'))
    if _ids_sha(train_ids) != cfg('GROWTH_IDS_SHA256'):
        raise ScoreRefused(f'GROWTH_IDS_MISMATCH sha={_ids_sha(train_ids)}')
    if _ids_sha(eval_ids) != cfg('SEALED_IDS_SHA256'):
        raise ScoreRefused(f'SEALED_IDS_MISMATCH sha={_ids_sha(eval_ids)}')
    a2 = Path(arcagi2_clone).resolve() if arcagi2_clone else None
    a2_head = _git_head(a2) if a2 else None
    guard._unlock(proof)
    try:
        _mkdir700(key)
        manifest = {'growth': {}, 'sealed': {}, 'arcagi2_sealed': {}}
        gdir = data / 'growth'
        gdir.mkdir(parents=True, exist_ok=True)
        for i in train_ids:
            b = (a1 / 'data' / 'training' / f'{i}.json').read_bytes()
            with open(gdir / f'{i}.json', 'wb') as f:
                f.write(b)
            manifest['growth'][i] = sha256_bytes(b)
        key_shas = _seal_split(a1 / 'data' / 'evaluation', eval_ids, data / 'sealed', key / 'arcagi1')
        for i in eval_ids:
            manifest['sealed'][i] = sha256_file(data / 'sealed' / f'{i}.json')
        shutil.move(str(a1 / 'data' / 'evaluation'), str(key / 'raw_arcagi1_eval'))
        if (a1 / '.git').exists():
            shutil.move(str(a1 / '.git'), str(key / 'raw_arcagi1_git'))
        a2_ids: list[str] = []
        if a2 is not None:
            a2_ids = sorted(p.stem for p in (a2 / 'data' / 'evaluation').glob('*.json'))
            key_shas.update(_seal_split(a2 / 'data' / 'evaluation', a2_ids, data / 'arcagi2_sealed', key / 'arcagi2'))
            for i in a2_ids:
                manifest['arcagi2_sealed'][i] = sha256_file(data / 'arcagi2_sealed' / f'{i}.json')
            shutil.move(str(a2 / 'data'), str(key / 'raw_arcagi2_data'))
            if (a2 / '.git').exists():
                shutil.move(str(a2 / '.git'), str(key / 'raw_arcagi2_git'))
        n_locked = _chmod_tree(key)
        _write_key_file(key / 'KEY_MANIFEST.json', {'created_et': now_et(), 'key_files_sha256': key_shas})
        os.chmod(key, 0o700)
    finally:
        guard._relock()
    write_json_atomic(data / 'MANIFEST.json', {
        'created_et': now_et(), 'arcagi1_commit': head, 'arcagi2_commit': a2_head,
        'growth_ids_sha256': _ids_sha(train_ids), 'sealed_ids_sha256': _ids_sha(eval_ids),
        'arcagi2_ids_sha256': _ids_sha(a2_ids) if a2_ids else None, 'files_sha256': manifest})
    print(f'SEAL growth={len(train_ids)} sealed={len(eval_ids)} arcagi2={len(a2_ids)} key_files={n_locked + 1} '
          f'commit={head}', flush=True)


def cmd_seal_arcagi2(arcagi2_clone: Path) -> None:
    """Add the ARC-AGI-2 secondary key (PREREG 2) to an existing seal: data/arcagi2_sealed (inputs only),
    key/arcagi2/<id>.json (mode 000), the clone's whole data/ (its training split holds ARC-AGI-1 evaluation tasks with
    outputs) and .git moved into the key, KEY_MANIFEST.json and data/MANIFEST.json updated. Refuses before the
    ARC-AGI-1 seal or if key/arcagi2 already exists. SPEC 13 I16: commit recorded at download, no pinned commit."""
    proof = guard._issue_proof('seal')
    key = guard.key_root()
    data = guard.data_root()
    a2 = Path(arcagi2_clone).resolve()
    a2_head = _git_head(a2)
    a2_ids = sorted(p.stem for p in (a2 / 'data' / 'evaluation').glob('*.json'))
    if not a2_ids:
        raise ScoreRefused(f'ARCAGI2_NO_EVAL_TASKS {a2}/data/evaluation')
    guard._unlock(proof)
    try:
        if not os.path.exists(key / 'KEY_MANIFEST.json'):
            raise ScoreRefused(f'NOT_SEALED {key}/KEY_MANIFEST.json missing (run seal first)')
        if os.path.exists(key / 'arcagi2') or os.path.exists(data / 'arcagi2_sealed'):
            raise ScoreRefused('ARCAGI2_ALREADY_SEALED')
        exposed = _key_files_locked(key)
        if exposed:
            raise ScoreRefused(f'KEY_EXPOSED {len(exposed)} files not mode 000, first {exposed[0]}')
        key_shas = _seal_split(a2 / 'data' / 'evaluation', a2_ids, data / 'arcagi2_sealed', key / 'arcagi2')
        shutil.move(str(a2 / 'data'), str(key / 'raw_arcagi2_data'))
        if (a2 / '.git').exists():
            shutil.move(str(a2 / '.git'), str(key / 'raw_arcagi2_git'))
        mp = key / 'KEY_MANIFEST.json'
        man = _read_key_file(mp)
        man.setdefault('key_files_sha256', {}).update(key_shas)
        man['arcagi2'] = {'added_et': now_et(), 'commit': a2_head, 'n': len(a2_ids), 'ids_sha256': _ids_sha(a2_ids)}
        os.chmod(mp, 0o600)
        _write_key_file(mp, man)
        n_locked = _chmod_tree(key)
        os.chmod(key, 0o700)
    finally:
        guard._relock()
    mpath = data / 'MANIFEST.json'
    dm = read_json(mpath, {}) or {}
    dm['arcagi2_commit'] = a2_head
    dm['arcagi2_ids_sha256'] = _ids_sha(a2_ids)
    dm.setdefault('files_sha256', {})['arcagi2_sealed'] = {
        i: sha256_file(data / 'arcagi2_sealed' / f'{i}.json') for i in a2_ids}
    write_json_atomic(mpath, dm)
    print(f'SEAL_ARCAGI2 tasks={len(a2_ids)} key_files={n_locked} commit={a2_head}', flush=True)


# ---------------------------------------------------------------------------------------------------------------------
# score: checks that need no key access

def preflight(run_dir: Path, condition: str, freeze_sha: str, submit_sha: str) -> dict:
    """Every refusal of SPEC 8 layer 4 that can be decided without touching the key. Returns the parsed freezes."""
    if condition not in CONDITIONS:
        raise ScoreRefused(f'BAD_CONDITION {condition}')
    run_dir = Path(run_dir).resolve()
    fz = run_dir / 'freeze'
    fpath = fz / 'FREEZE.json'
    spath = fz / SUBMIT_FREEZE_FILE[condition]
    for p in (fpath, spath):
        if not p.exists():
            raise ScoreRefused(f'MISSING_FREEZE {p}')
    if sha256_file(fpath) != freeze_sha:
        raise ScoreRefused(f'FREEZE_SHA_MISMATCH file={sha256_file(fpath)} arg={freeze_sha}')
    if sha256_file(spath) != submit_sha:
        raise ScoreRefused(f'SUBMIT_SHA_MISMATCH file={sha256_file(spath)} arg={submit_sha}')
    side = fz / 'FREEZE.sha256'
    if side.exists() and side.read_text().split()[0] != freeze_sha:
        raise ScoreRefused('FREEZE_SHA256_FILE_MISMATCH')
    freeze = read_json(fpath)
    sfreeze = read_json(spath)
    if sfreeze.get('freeze_sha') not in (None, freeze_sha):
        raise ScoreRefused(f'SUBMIT_FREEZE_POINTS_ELSEWHERE freeze_sha={sfreeze.get("freeze_sha")}')
    listed = freeze_entries(freeze, run_dir)
    sub_listed = freeze_entries(sfreeze, run_dir)
    chain = []
    if condition in ('knockout', 'arcagi2'):
        p1 = fz / 'SUBMIT_FREEZE.json'
        if not p1.exists():
            raise ScoreRefused(f'MISSING_FREEZE {p1}')
        if sfreeze.get('submit_sha') not in (None, sha256_file(p1)):
            raise ScoreRefused(f'KO_FREEZE_POINTS_ELSEWHERE submit_sha={sfreeze.get("submit_sha")}')
        chain.append(p1)
        listed.update(freeze_entries(read_json(p1), run_dir))
    if not listed:
        raise ScoreRefused('FREEZE_LISTS_NO_FILES')
    allf = dict(listed)
    allf.update(sub_listed)
    for p, want in sorted(allf.items()):
        if not os.path.exists(p):
            raise ScoreRefused(f'FROZEN_FILE_MISSING {p}')
        got = sha256_file(p)
        if got != want:
            raise ScoreRefused(f'FROZEN_FILE_CHANGED {p} frozen={want} now={got}')
    disk = _on_disk_submissions(run_dir, condition)
    if not disk:
        raise ScoreRefused(f'NO_SUBMISSIONS for {condition}')
    for p in disk:
        if str(p) not in sub_listed:
            raise ScoreRefused(f'UNLISTED_SUBMISSION {p}')
    reads = run_dir / 'scores' / 'KEY_READS.jsonl'
    for row in iter_jsonl(reads):
        if row.get('condition') == condition:
            raise ScoreRefused(f'REPEATED_CONDITION {condition} (read at {row.get("ts_et")})')
    if condition == 'knockout' and not (run_dir / 'scores' / 'W.json').exists():
        raise ScoreRefused('KNOCKOUT_BEFORE_PRIMARY')
    if condition == 'arcagi2' and not (run_dir / 'RESULT.md').exists():
        raise ScoreRefused('ARCAGI2_BEFORE_RESULT (SPEC 13 I16)')
    # PREREG 2: the key opens only after every library is frozen AND hash-committed: the lead's ack of each freeze
    acks = [('FREEZE', freeze_sha), (SUBMIT_FREEZE_FILE[condition][:-len('.json')], submit_sha)]
    acks += [(p.stem, sha256_file(p)) for p in chain]
    for name, want in acks:
        ap = fz / f'{name}.ack'
        got = ap.read_text().split()[:1] if ap.exists() else []
        if got != [want]:
            raise ScoreRefused(f'NOT_ACKED {name}.ack {"missing" if not ap.exists() else "holds " + str(got)} '
                               f'(lead: commit {name}.json, then `ratchet freeze --ack {want} --name {name}`)')
    retired = _retired(run_dir)
    if retired:
        raise ScoreRefused(f'HARNESS_RETIRED {retired} (PREREG 9: a VOID run is retired after two attempts)')
    if condition == 'primary':
        _check_perturb(sfreeze, freeze, disk, run_dir)
    return {'run_dir': run_dir, 'freeze': freeze, 'sfreeze': sfreeze, 'disk': disk, 'chain': chain}


def _retired(run_dir: Path) -> str:
    a = read_json(Path(run_dir).parent / 'ATTEMPTS.json', {}) or {}
    void_runs = list(a.get('void_runs', []))
    if a.get('retired') or len(void_runs) >= int(cfg('VOID_MAX_ATTEMPTS')):
        return 'void_runs=' + ','.join(void_runs)
    return ''


def _check_perturb(sfreeze: dict, freeze: dict, disk: list[Path], run_dir: Path) -> None:
    """PREREG 6.4 binding (review fix 2026-11-04): SUBMIT_FREEZE lists PERTURB.json with its sha256 (checked with every
    other frozen file above); its seed equals FREEZE perturb_seed; every perturbed task's recorded perm and geometry
    equal perturb.draw(task, seed); every data/sealed_perturbed/<id>.json still has the sha256 PERTURB.json recorded.
    The scorer then perturbs the key outputs with that same draw."""
    from ratchet import perturb
    ent = sfreeze.get('perturb') or {}
    p = ent.get('path')
    if not p or not _is_sha(ent.get('sha256')):
        raise ScoreRefused('PERTURB_NOT_FROZEN (SUBMIT_FREEZE.json has no perturb {path, sha256})')
    p = _resolve(run_dir, p)
    man = read_json(p, {}) or {}
    seed = int(freeze.get('perturb_seed') or cfg('PERTURB_SEED'))
    if int(man.get('seed', -1)) != seed:
        raise ScoreRefused(f'PERTURB_SEED_MISMATCH PERTURB.json seed={man.get("seed")} FREEZE perturb_seed={seed}')
    rows = man.get('tasks') or {}
    tasks = set()
    for f in disk:
        if _split_path(run_dir, f)[0] == 'perturbed':
            tasks |= set(parse_submissions(read_json(f)))
    for t in sorted(tasks):
        r = rows.get(t)
        want = perturb.draw(t, seed).to_json()
        if r is None or list(r.get('perm', [])) != want['perm'] or r.get('geom') != want['geom']:
            raise ScoreRefused(f'PERTURB_DRAW_MISMATCH task={t} recorded={r and {k: r.get(k) for k in ("perm", "geom")}} '
                               f'draw={want}')
        out_sha = r.get('out_sha256')
        f = p.parent / 'sealed_perturbed' / f'{t}.json'
        if out_sha and (not f.exists() or sha256_file(f) != out_sha):
            raise ScoreRefused(f'PERTURBED_FILE_CHANGED {f}')


def _key_files_locked(key: Path) -> list[str]:
    exposed = []
    for dp, dns, fns in os.walk(key):
        for fn in fns:
            p = os.path.join(dp, fn)
            if stat.S_IMODE(os.lstat(p).st_mode) != 0:
                exposed.append(p)
    return exposed


def _global_reads(key: Path) -> list[dict]:
    """Rows of <key root>/KEY_READS.jsonl (call only while unlocked)."""
    p = key / GLOBAL_READS
    if not p.exists():
        return []
    os.chmod(p, 0o400)
    try:
        with open(p, 'rb') as f:
            text = f.read().decode()
    finally:
        os.chmod(p, 0o000)
    return [json.loads(ln) for ln in text.splitlines() if ln.strip()]


def _append_global_read(key: Path, row: dict) -> None:
    p = key / GLOBAL_READS
    if p.exists():
        os.chmod(p, 0o600)
    try:
        with open(p, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, sort_keys=True) + '\n')
            f.flush()
            os.fsync(f.fileno())
    finally:
        os.chmod(p, 0o000)


KEY_GRANT_PHRASE = 'grants one key access'


def amendment_paragraph(prereg_text: str, amendment: str) -> str | None:
    """The paragraph of `- AMENDMENT <id> (` under `## AMENDMENTS`, up to the next `- AMENDMENT ` or the end of the
    file, whitespace collapsed (so a phrase wrapped across lines still reads as one); None if there is no such line."""
    import re
    if not amendment or not re.fullmatch(r'[0-9A-Za-z._-]+', str(amendment)):
        return None
    _head, sep, amend = prereg_text.partition('## AMENDMENTS')
    if not sep:
        return None
    flat = ' '.join(amend.split())
    start = flat.find(f'- AMENDMENT {amendment} (')
    if start < 0:
        return None
    nxt = flat.find('- AMENDMENT ', start + 1)
    return flat[start: nxt if nxt >= 0 else len(flat)]


def amendment_key_grant(prereg_text: str, amendment: str) -> str:
    """'OK' iff amendment <id>'s own paragraph contains the exact phrase KEY_GRANT_PHRASE; else 'NOT_IN_PREREG' or
    'GRANTS_NO_KEY_ACCESS'. Review fix 2026-11-04: any `AMENDMENT <id> ` text used to authorise a repeated key read, so
    every harness amendment (truncation, adapter, PLANT_SOLVE gate) would have minted a re-read token."""
    para = amendment_paragraph(prereg_text, amendment)
    if para is None:
        return 'NOT_IN_PREREG'
    return 'OK' if KEY_GRANT_PHRASE in para else 'GRANTS_NO_KEY_ACCESS'


def _amendment_status(amendment: str) -> str:
    prereg = guard.expected_score_path()
    text = Path(os.path.dirname(prereg), 'PREREG.md').read_text(encoding='utf-8')
    return amendment_key_grant(text, amendment)


def _amendment_registered(amendment: str) -> bool:
    return _amendment_status(amendment) == 'OK'


def _read_outputs(condition: str, argv: list[str], pf: dict, freeze_sha: str, submit_sha: str,
                  amendment: str | None = None) -> dict[str, tuple]:
    """The only key read. Unlock, check modes and the key-root read log, log, read each file (400 then back to 000),
    relock."""
    proof = guard._issue_proof('score')
    key = guard.key_root()
    run_dir = pf['run_dir']
    sub = key / KEY_SUBDIR[condition]
    guard._unlock(proof)
    try:
        if not sub.is_dir():
            raise ScoreRefused(f'KEY_MISSING {sub}')
        exposed = _key_files_locked(key)
        if exposed:
            raise ScoreRefused(f'KEY_EXPOSED {len(exposed)} files not mode 000, first {exposed[0]}')
        earlier = [r for r in _global_reads(key) if r.get('condition') == condition]
        if earlier:
            used = {r.get('amendment') for r in _global_reads(key)}
            if not amendment:
                e = earlier[0]
                raise ScoreRefused(f'REPEATED_CONDITION_KEY {condition}: {len(earlier)} earlier read(s) in the key log, '
                                   f'first {e.get("ts_et")} run={e.get("run")} freeze_sha={e.get("freeze_sha")} '
                                   '(PREREG 2: once per frozen library; a re-read needs --amendment <id>)')
            if amendment in used:
                raise ScoreRefused(f'AMENDMENT_ALREADY_USED {amendment}')
            ast_ = _amendment_status(amendment)
            if ast_ == 'NOT_IN_PREREG':
                raise ScoreRefused(f'AMENDMENT_NOT_IN_PREREG {amendment} (PREREG.md AMENDMENTS has no "- AMENDMENT '
                                   f'{amendment} (" line)')
            if ast_ != 'OK':
                raise ScoreRefused(f'AMENDMENT_GRANTS_NO_KEY_ACCESS {amendment} (its paragraph lacks the exact phrase '
                                   f'"{KEY_GRANT_PHRASE}")')
        files = sorted(p for p in os.listdir(sub) if p.endswith('.json'))
        row = {'ts_et': now_et(), 'condition': condition, 'freeze_sha': freeze_sha, 'submit_sha': submit_sha,
               'n_files': len(files), 'key_root': str(key), 'run': str(run_dir), 'amendment': amendment,
               'job': os.environ.get('SLURM_JOB_ID') or socket.gethostname(), 'argv': list(argv)}
        _append_global_read(key, row)
        reads = run_dir / 'scores' / 'KEY_READS.jsonl'
        reads.parent.mkdir(parents=True, exist_ok=True)
        with open(reads, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, sort_keys=True) + '\n')
            f.flush()
            os.fsync(f.fileno())
        out = {}
        for fn in files:
            obj = _read_key_file(sub / fn)
            out[str(obj['id'])] = tuple(as_grid(g) for g in obj['test_outputs'])
        return out
    finally:
        guard._relock()


# ---------------------------------------------------------------------------------------------------------------------
# score: pure computation on submissions plus outputs (no key access below this line)

def _split_path(run_dir: Path, p: Path) -> tuple[str, str, int]:
    """(condition or knockout mode, arm, seed) from sealed/<cond>/<ARM>/seed_<k>/... or knockout/<mode>/seed_<k>/..."""
    rel = p.relative_to(run_dir).parts
    if rel[0] == 'sealed':
        return rel[1], rel[2], int(rel[3].split('_')[1])
    return 'knockout_' + rel[1], 'STOCK', int(rel[2].split('_')[1])


def _per_seed_correct(run_dir: Path, files: list[Path], outputs: dict[str, tuple], perturb_seed: int | None,
                      only: frozenset | None = None):
    """{cond: {arm: {seed: {task: bool}}}} and correct-attempt sample ids {cond: {arm: {seed: {task: [ids]}}}}."""
    per: dict = {}
    ids: dict = {}
    pert = None
    for p in files:
        cond, arm, seed = _split_path(run_dir, p)
        subs = parse_submissions(read_json(p))
        tasks = sorted(outputs) if only is None else sorted(only)
        dst = per.setdefault(cond, {}).setdefault(arm, {}).setdefault(seed, {})
        idst = ids.setdefault(cond, {}).setdefault(arm, {}).setdefault(seed, {})
        for t in tasks:
            want = outputs.get(t)
            s = subs.get(t)
            if want is None or s is None:
                dst[t] = False
                continue
            if cond == 'perturbed':
                if pert is None:
                    from ratchet import perturb as pert
                pp = pert.draw(t, perturb_seed)
                want = tuple(as_grid(pert.apply_grid(g, pp)) for g in want)
            hit = _correct_attempt_ids(s, want)
            dst[t] = hit is not None
            if hit is not None:
                idst[t] = hit
    return per, ids


def _solved(per_arm: dict[int, dict[str, bool]], seeds, min_seeds: int) -> frozenset[str]:
    tasks = set()
    for k in seeds:
        tasks |= set(per_arm.get(k, {}))
    return frozenset(t for t in tasks if sum(bool(per_arm.get(k, {}).get(t)) for k in seeds) >= min_seeds)


def _library_names(run_dir: Path, freeze: dict, arm: str = 'STOCK') -> frozenset[str]:
    ent = (freeze.get('libraries') or {}).get(arm) or {}
    p = ent.get('json')
    if not p:
        return frozenset()
    lib = read_json(_resolve(run_dir, p), {}) or {}
    return frozenset(h['name'] for h in lib.get('helpers', []))


def _merge_gates(run_dir: Path, key: str, value: dict) -> None:
    p = run_dir / 'scores' / 'gates.json'
    g = read_json(p, {}) or {}
    g[key] = value
    write_json_atomic(p, g)


def _score_primary(run_dir: Path, pf: dict, outputs: dict[str, tuple]) -> dict:
    from ratchet import gates
    freeze = pf['freeze']
    seeds = _seeds(freeze)
    min_seeds = int(cfg('SOLVED_MIN_SEEDS'))
    perturb_seed = int(freeze.get('perturb_seed') or cfg('PERTURB_SEED'))
    per, ids = _per_seed_correct(run_dir, pf['disk'], outputs, perturb_seed)
    arms = tuple(cfg('ARMS'))
    flat = cfg('FLAT_ARM')
    need = [('sealed', a) for a in arms] + [('perturbed', a) for a in cfg('PERTURBED_ARMS')]
    missing = [f'{c}/{a}/seed_{k}' for c, a in need for k in seeds if k not in per.get(c, {}).get(a, {})]
    if missing:
        raise ScoreRefused('MISSING_SUBMISSION ' + ', '.join(missing))
    solved = {c: {a: _solved(per[c][a], seeds, min_seeds) for a in per[c]} for c in per}
    S = solved['sealed']
    W = S['STOCK'] - S[flat]
    winners = {}
    for t in sorted(W):
        pooled: list[str] = []
        for k in seeds:
            for sid in ids['sealed']['STOCK'].get(k, {}).get(t, []):
                if sid not in pooled:
                    pooled.append(sid)
        winners[t] = pooled
    from ratchet.knockout import winner_exec_rows
    rows = winner_exec_rows(run_dir, winners)
    accepted = _library_names(run_dir, freeze, 'STOCK')
    comps = {f'STOCK_vs_{b}': gates.compare(S, 'STOCK', b) for b in cfg('COMPARATORS')}
    void = gates.compare(S, 'PLANTDRIP', 'PLANTL1')
    P = solved['perturbed']
    pert_cmp = gates.compare(P, 'STOCK', flat)
    contam = gates.contamination_gate(comps[f'STOCK_vs_{flat}']['net'], pert_cmp['net'])
    reuse = gates.reuse_gate(W, rows, accepted)
    aa = gates.aa_pairs({k: frozenset(t for t, v in per['sealed'][flat][k].items() if v) for k in seeds})
    counts = {c: {a: {'solved': len(solved[c][a]),
                      'per_seed': {str(k): sum(per[c][a][k].values()) for k in seeds}} for a in per[c]} for c in per}
    out = {'condition': 'primary', 'n_tasks': len(outputs), 'seeds': list(seeds), 'counts': counts,
           'compare': comps, 'void_compare': void, 'perturbed_compare': pert_cmp, 'contamination': contam,
           'W': len(W), 'reuse': reuse, 'accepted_helpers': len(accepted), 'aa_flat': aa,
           'pred_stock_minus_static': comps['STOCK_vs_STATIC']['net']}
    sd = run_dir / 'scores'
    write_json_atomic(sd / 'solved_primary.json', {
        'schema': 'ratchet.solved.v1', 'condition': 'primary', 'seeds': list(seeds),
        'per_seed': {c: {a: {str(k): per[c][a][k] for k in per[c][a]} for a in per[c]} for c in per},
        'solved': {c: {a: sorted(solved[c][a]) for a in solved[c]} for c in solved}})
    write_json_atomic(sd / 'W.json', {'W': sorted(W), 'n': len(W)})
    write_json_atomic(sd / 'winners.json', {'winners': winners})
    write_json_atomic(sd / 'mcnemar.json', {'primary': {**comps, 'PLANTDRIP_vs_PLANTL1': void,
                                                        'perturbed_STOCK_vs_FLATTTC': pert_cmp}})
    _merge_gates(run_dir, 'primary', out)
    return out


def _score_knockout(run_dir: Path, pf: dict, outputs: dict[str, tuple]) -> dict:
    from ratchet import gates
    seeds = _seeds(pf['freeze'])
    W = frozenset((read_json(run_dir / 'scores' / 'W.json', {}) or {}).get('W', []))
    per, _ = _per_seed_correct(run_dir, pf['disk'], outputs, None, only=W)
    min_seeds = int(cfg('SOLVED_MIN_SEEDS'))
    solved = {}
    for mode in KO_MODES:
        cond = 'knockout_' + mode
        arm = per.get(cond, {}).get('STOCK', {})
        missing = [k for k in seeds if k not in arm]
        if missing:
            raise ScoreRefused(f'MISSING_SUBMISSION knockout/{mode} seeds {missing}')
        solved[mode] = _solved(arm, seeds, min_seeds) & W
    ko = gates.knockout_gate(W, solved['delete'], solved['inline'])
    write_json_atomic(run_dir / 'scores' / 'solved_knockout.json', {
        'schema': 'ratchet.solved.v1', 'condition': 'knockout', 'seeds': list(seeds),
        'per_seed': {c: {a: {str(k): per[c][a][k] for k in per[c][a]} for a in per[c]} for c in per},
        'solved': {'knockout_' + m: {'STOCK': sorted(solved[m])} for m in KO_MODES}})
    _merge_gates(run_dir, 'knockout', ko)
    return ko


def _score_arcagi2(run_dir: Path, pf: dict, outputs: dict[str, tuple]) -> dict:
    from ratchet import gates
    seeds = _seeds(pf['freeze'])
    per, _ = _per_seed_correct(run_dir, pf['disk'], outputs, None)
    min_seeds = int(cfg('SOLVED_MIN_SEEDS'))
    S = {a: _solved(per['arcagi2'][a], seeds, min_seeds) for a in per.get('arcagi2', {})}
    comps = {f'STOCK_vs_{b}': gates.compare(S, 'STOCK', b) for b in cfg('COMPARATORS') if b in S and 'STOCK' in S}
    write_json_atomic(run_dir / 'scores' / 'solved_arcagi2.json', {
        'schema': 'ratchet.solved.v1', 'condition': 'arcagi2', 'seeds': list(seeds),
        'per_seed': {a: {str(k): per['arcagi2'][a][k] for k in per['arcagi2'][a]} for a in per.get('arcagi2', {})},
        'solved': {'arcagi2': {a: sorted(v) for a, v in S.items()}}})
    out = {'n_tasks': len(outputs), 'counts': {a: len(v) for a, v in S.items()}, 'compare': comps}
    _merge_gates(run_dir, 'arcagi2', out)
    return out


def cmd_score(run_dir: Path, condition: str, freeze_sha: str, submit_sha: str, argv: list[str] | None = None,
              amendment: str | None = None) -> dict:
    run_dir = Path(run_dir).resolve()
    pf = preflight(run_dir, condition, freeze_sha, submit_sha)
    outputs = _read_outputs(condition, list(argv or sys.argv), pf, freeze_sha, submit_sha, amendment)
    if condition == 'primary':
        res = _score_primary(run_dir, pf, outputs)
        print(f'SCORE condition=primary tasks={len(outputs)} W={res["W"]} '
              f'stock={res["counts"]["sealed"]["STOCK"]["solved"]} reuse_pass={int(res["reuse"]["pass"])}', flush=True)
    elif condition == 'knockout':
        res = _score_knockout(run_dir, pf, outputs)
        print(f'SCORE condition=knockout W={res["W"]} kept_delete={res["kept_delete"]} '
              f'kept_inline={res["kept_inline"]} pass={int(res["pass"])}', flush=True)
    else:
        res = _score_arcagi2(run_dir, pf, outputs)
        print(f'SCORE condition=arcagi2 tasks={len(outputs)}', flush=True)
    return res


def solved_sets(run_dir: Path, condition: str, arms) -> dict[str, frozenset[str]]:
    """Arm -> tasks solved in at least 2 of 3 seeds. condition: sealed | perturbed | knockout_delete |
    knockout_inline | arcagi2 (or primary, meaning sealed). Reads scores/ only."""
    sub = 'sealed' if condition == 'primary' else condition
    fname = {'sealed': 'primary', 'perturbed': 'primary', 'knockout_delete': 'knockout', 'knockout_inline': 'knockout',
             'arcagi2': 'arcagi2'}[sub]
    d = read_json(Path(run_dir) / 'scores' / f'solved_{fname}.json', {}) or {}
    s = (d.get('solved') or {}).get(sub, {})
    return {a: frozenset(s.get(a, [])) for a in arms}


def write_a2_freeze(run_dir: Path) -> tuple[Path, str]:
    """A2_SUBMIT_FREEZE.json (and its .sha256) via ratchet.freeze.freeze_arcagi2: sha256 of every ARC-AGI-2
    submissions.json, chained to FREEZE and SUBMIT_FREEZE (no key access). The lead then acks it."""
    from ratchet import arms, freeze
    try:
        out, s = freeze.freeze_arcagi2(arms.load_run(Path(run_dir).resolve()))
    except freeze.FreezeRefused as e:
        raise ScoreRefused(str(e)) from None
    print(f'A2_SUBMIT_FREEZE sha256={s}', flush=True)
    return out, s


def _check_roots(test: bool) -> None:
    """--test is the only way to use a non-default key or data root, and it needs one (review fix 2026-11-04)."""
    over = [n for n, real, cur in ((guard.ENV_KEY_ROOT, guard.KEY_ROOT, guard.key_root()),
                                   (guard.ENV_DATA_ROOT, guard.DATA_ROOT, guard.data_root()))
            if os.path.realpath(str(cur)) != os.path.realpath(str(real))]
    if over and not test:
        raise ScoreRefused('ROOT_OVERRIDE_REFUSED %s set without --test (unset it for the real key)' % ','.join(over))
    if test and not over:
        raise ScoreRefused('TEST_ON_REAL_KEY --test needs RATCHET_KEY_ROOT or RATCHET_DATA_ROOT (a fake key)')


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog='score_sealed.py')
    sp = ap.add_subparsers(dest='cmd', required=True)
    a = sp.add_parser('seal')
    a.add_argument('--arcagi1', required=True)
    a.add_argument('--arcagi2')
    a.add_argument('--test', action='store_true')
    a2 = sp.add_parser('seal-arcagi2')
    a2.add_argument('--arcagi2', required=True)
    a2.add_argument('--test', action='store_true')
    b = sp.add_parser('score')
    b.add_argument('--run', required=True)
    b.add_argument('--condition', required=True, choices=CONDITIONS)
    b.add_argument('--freeze-sha', required=True)
    b.add_argument('--submit-sha', required=True)
    b.add_argument('--amendment', default=None, help='PREREG AMENDMENT id that authorises a repeated condition')
    b.add_argument('--test', action='store_true')
    c = sp.add_parser('freeze-arcagi2')
    c.add_argument('--run', required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd in ('seal', 'seal-arcagi2', 'score'):
            _check_roots(bool(args.test))
        if args.cmd == 'seal':
            cmd_seal(Path(args.arcagi1), Path(args.arcagi2) if args.arcagi2 else None)
        elif args.cmd == 'seal-arcagi2':
            cmd_seal_arcagi2(Path(args.arcagi2))
        elif args.cmd == 'score':
            cmd_score(Path(args.run), args.condition, args.freeze_sha, args.submit_sha, argv=['score_sealed.py'] + argv,
                      amendment=args.amendment)
        else:
            write_a2_freeze(Path(args.run))
    except (ScoreRefused, guard.SealedReadRefused) as e:
        print(f'REFUSED {e}', file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
