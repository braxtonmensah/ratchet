"""FREEZE.json, SUBMIT_FREEZE.json, KO_FREEZE.json (SPEC 4.8, 7.1 steps 3, 5, 7). Owner: builder D.

A freeze file lists every file it covers with its sha256 and is never overwritten: a second call with the same content
returns the existing file, a call with different content raises FreezeConflict. <NAME>.sha256 holds the sha256 of the
freeze file's bytes; the lead commits the freeze file and then acknowledges that sha (`ratchet freeze --ack <sha>`),
which is the lead gate in the PLAN.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from . import config, rounds
from .rounds import atomic_write_bytes, dumps, now_et, read_json


class FreezeRefused(RuntimeError):
    pass


class FreezeConflict(RuntimeError):
    pass


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _entry(run, json_rel: str | None, py_rel: str | None) -> dict:
    if not json_rel:
        raise FreezeRefused('missing library file')
    d = Path(run.dir)
    e = {'json': json_rel, 'py': py_rel, 'sha256_json': sha256_file(d / json_rel),
         'sha256_py': sha256_file(d / py_rel) if py_rel else None}
    return e


def _state(dir: Path) -> dict:
    return rounds.load_state(dir)


def library_entries(run) -> dict:
    """The frozen library of every arm (FLATTTC: None). Refuses unless every growth round and build is complete."""
    if run.S is None or run.R is None:
        raise FreezeRefused('S and R are not fixed (pilot not chosen)')
    R = run.R
    need = [('STOCK', r) for r in range(1, R + 1)] + [('STATIC', r) for r in range(1, R + 1)] + \
           [('EXEMPLAR', r) for r in range(1, R + 1)] + [('ONESHOT', 1)]
    for arm, r in need:
        st = _state(rounds.round_dir(run, arm, r))
        if st.get('state') != 'FROZEN':
            raise FreezeRefused('%s round %d is %s, not FROZEN' % (arm, r, st.get('state')))
    for arm in ('SHAM', 'PLANTDRIP', 'PLANTL1'):
        st = _state(rounds.arm_dir(run, arm))
        if st.get('state') != 'DONE':
            raise FreezeRefused('%s build is %s, not DONE' % (arm, st.get('state')))
    stock_R = _state(rounds.round_dir(run, 'STOCK', R))
    stock_1 = _state(rounds.round_dir(run, 'STOCK', 1))
    one = _state(rounds.round_dir(run, 'ONESHOT', 1))
    ex_R = _state(rounds.round_dir(run, 'EXEMPLAR', R))
    libs = {
        'STOCK': _entry(run, stock_R.get('library_json'), stock_R.get('library_py')),
        'STATIC': _entry(run, stock_1.get('library_json'), stock_1.get('library_py')),
        'ONESHOT': _entry(run, one.get('library_json'), one.get('library_py')),
        'EXEMPLAR': _entry(run, ex_R.get('library_json'), None),
    }
    for arm in ('SHAM', 'PLANTDRIP', 'PLANTL1'):
        st = _state(rounds.arm_dir(run, arm))
        libs[arm] = _entry(run, st.get('library_json'), st.get('library_py'))
    libs[config.FLAT_ARM] = None
    return libs


def _write_once(path: Path, body: dict, compare_keys: tuple[str, ...]) -> tuple[Path, str]:
    path = Path(path)
    if path.exists():
        old = read_json(path)
        if all(old.get(k) == body.get(k) for k in compare_keys):
            return path, sha256_file(path)
        raise FreezeConflict('%s exists with different content; a freeze is never overwritten' % path)
    data = dumps(body).encode('utf-8')
    atomic_write_bytes(path, data)
    sha = hashlib.sha256(data).hexdigest()
    atomic_write_bytes(path.with_suffix('.sha256'), ('%s  %s\n' % (sha, path.name)).encode('ascii'))
    return path, sha


def verify_files(run, files: dict) -> None:
    """files: {relpath: sha256}. Raises FreezeRefused on any mismatch."""
    d = Path(run.dir)
    for rel, want in sorted(files.items()):
        if want is None:
            continue
        p = d / rel
        if not p.exists():
            raise FreezeRefused('frozen file missing: %s' % rel)
        got = sha256_file(p)
        if got != want:
            raise FreezeRefused('FROZEN_FILE_CHANGED %s %s != %s' % (rel, got, want))


def _freeze_files(fr: dict) -> dict:
    out = {}
    for e in fr['libraries'].values():
        if e:
            out[e['json']] = e['sha256_json']
            if e.get('py'):
                out[e['py']] = e['sha256_py']
    return out


def verify_freeze(run) -> str:
    p = rounds.freeze_dir(run) / 'FREEZE.json'
    fr = read_json(p)
    if fr is None:
        raise FreezeRefused('FREEZE.json missing')
    verify_files(run, _freeze_files(fr))
    return sha256_file(p)


def check_pilot(run) -> dict:
    """PREREG 7: S and R come from the pilot rule, and power is computed before any sealed read (review fix
    2026-11-04). Refuses unless PILOT.json says OK with a power value. Only a test run (skip_pilot, refused on the real
    runs tree and inside SLURM by rounds.check_test_switches) has no pilot."""
    if run.cfg.get('skip_pilot'):
        rounds.check_test_switches(run)
        return {'status': 'SKIPPED_TEST_RUN'}
    pil = read_json(Path(run.dir) / 'PILOT.json')
    if pil is None:
        raise FreezeRefused('PILOT_MISSING: PILOT.json absent (PREREG 7 fixes S and R before any sealed read)')
    if pil.get('status') != 'OK':
        raise FreezeRefused('PILOT_NOT_OK status=%s' % pil.get('status'))
    if (pil.get('choice') or {}).get('power') is None:
        raise FreezeRefused('POWER_MISSING: PILOT.json has no projected power (PREREG 7.3)')
    if (pil.get('S'), pil.get('R')) != (run.S, run.R):
        raise FreezeRefused('PILOT_SR_MISMATCH PILOT.json S=%s R=%s, RUN.json S=%s R=%s' % (
            pil.get('S'), pil.get('R'), run.S, run.R))
    return pil


def check_tokenizers(run, libs: dict) -> str | None:
    """Every frozen library JSON records the same tokenizer_sha; on the real runs tree it must be the model's
    tokenizer, never the stub (the 6,000-token cap, the MDL 20 threshold and the SHAM 5% match are counted in it)."""
    seen = {}
    for arm, e in sorted(libs.items()):
        if not e or arm == 'EXEMPLAR':
            continue
        d = read_json(Path(run.dir) / e['json'], {}) or {}
        seen[arm] = d.get('tokenizer_sha') or (d.get('extra') or {}).get('tokenizer_sha')
    vals = {v for v in seen.values() if v is not None}
    if len(vals) > 1:
        raise FreezeRefused('TOKENIZER_MISMATCH across frozen libraries: %s' % seen)
    if rounds.production_run(run) and (None in seen.values() or 'stub' in vals):
        raise FreezeRefused('STUB_TOKENIZER_IN_PRODUCTION %s' % seen)
    return next(iter(vals)) if vals else None


def freeze_libraries(run) -> tuple[Path, str]:
    pilot = check_pilot(run)
    libs = library_entries(run)
    tok_sha = check_tokenizers(run, libs)
    from .arms import code_git_sha
    body = {'schema': config.FREEZE_SCHEMA, 'run': run.name, 'created_et': now_et(), 'code_git_sha': code_git_sha(),
            'S': run.S, 'R': run.R, 'sealed_seeds': list(rounds.sealed_seeds(run)),
            'perturb_seed': int(run.cfg.get('perturb_seed', config.PERTURB_SEED)), 'libraries': libs,
            'flat_budget': None, 'prereg': config.PREREG_ID, 'tokenizer_sha': tok_sha,
            'pilot': {k: pilot.get(k) for k in ('status', 'S', 'R', 'underpowered')},
            'model_files_sha256': run.cfg.get('model_files_sha256')}
    return _write_once(rounds.freeze_dir(run) / 'FREEZE.json', body, ('libraries', 'S', 'R', 'sealed_seeds'))


def required_submissions(run) -> list[tuple[str, str, int]]:
    out = []
    for k in rounds.sealed_seeds(run):
        for arm in config.LIBRARY_ARMS + (config.FLAT_ARM,):
            out.append(('sealed', arm, k))
    for k in rounds.sealed_seeds(run):
        for arm in config.PERTURBED_ARMS:
            out.append(('perturbed', arm, k))
    return out


def freeze_submissions(run) -> tuple[Path, str]:
    freeze_sha = verify_freeze(run)
    subs, budgets = {}, {}
    for cond, arm, k in required_submissions(run):
        d = rounds.sealed_dir(run, cond, arm, k)
        st = _state(d)
        p = d / 'submissions.json'
        if st.get('state') != 'DONE' or not p.exists():
            raise FreezeRefused('submissions missing: %s %s seed %d (state %s)' % (cond, arm, k, st.get('state')))
        subs[p.relative_to(Path(run.dir)).as_posix()] = sha256_file(p)
        if arm == config.FLAT_ARM:
            b = st.get('budget') or {}
            budgets.setdefault(cond, {})[str(k)] = {
                'target_tokens': b.get('target_tokens'), 'm_flat': b.get('m_flat'), 'n_extra': b.get('n_extra'),
                'realized': st.get('realized')}
    body = {'schema': config.SUBMIT_FREEZE_SCHEMA, 'run': run.name, 'created_et': now_et(), 'freeze_sha': freeze_sha,
            'submissions': subs, 'FLAT_BUDGET': budgets, 'perturb': perturb_entry(run)}
    return _write_once(rounds.freeze_dir(run) / 'SUBMIT_FREEZE.json', body, ('freeze_sha', 'submissions'))


def perturb_entry(run) -> dict | None:
    """PERTURB.json (the perturbed split's manifest: seed, perm and geometry per task, sha256 of every perturbed task
    file), bound into SUBMIT_FREEZE so score_sealed can check it against FREEZE perturb_seed (review fix 2026-11-04)."""
    done = read_json(Path(run.dir) / 'PERTURB_DONE.json', {}) or {}
    out = done.get('out')
    if out and Path(out).exists():
        man = read_json(Path(out), {}) or {}
        seed = int(run.cfg.get('perturb_seed', config.PERTURB_SEED))
        if man.get('seed') != seed:
            raise FreezeRefused('PERTURB_SEED_MISMATCH PERTURB.json seed=%s RUN.json perturb_seed=%s' % (
                man.get('seed'), seed))
        return {'path': str(Path(out).resolve()), 'sha256': sha256_file(Path(out)), 'seed': seed,
                'n_tasks': man.get('n_tasks')}
    if rounds.production_run(run):
        raise FreezeRefused('PERTURB_MISSING: PERTURB_DONE.json names no PERTURB.json')
    return None


def freeze_arcagi2(run) -> tuple[Path, str]:
    """A2_SUBMIT_FREEZE.json: every ARC-AGI-2 submissions.json with its sha256, chained to FREEZE and SUBMIT_FREEZE
    (PREREG 2 secondary read, SPEC 13 I16: only after RESULT.md)."""
    if not (Path(run.dir) / 'RESULT.md').exists():
        raise FreezeRefused('ARCAGI2_BEFORE_RESULT (SPEC 13 I16)')
    freeze_sha = verify_freeze(run)
    submit_sha = verify_submit_freeze(run)
    subs = {}
    for k in rounds.sealed_seeds(run):
        for arm in config.LIBRARY_ARMS + (config.FLAT_ARM,):
            d = rounds.sealed_dir(run, 'arcagi2', arm, k)
            p = d / 'submissions.json'
            if _state(d).get('state') != 'DONE' or not p.exists():
                raise FreezeRefused('arcagi2 submissions missing: %s seed %d' % (arm, k))
            subs[p.relative_to(Path(run.dir)).as_posix()] = sha256_file(p)
    body = {'schema': config.SUBMIT_FREEZE_SCHEMA, 'run': run.name, 'condition': 'arcagi2', 'created_et': now_et(),
            'freeze_sha': freeze_sha, 'submit_sha': submit_sha, 'submissions': subs}
    return _write_once(rounds.freeze_dir(run) / 'A2_SUBMIT_FREEZE.json', body, ('freeze_sha', 'submit_sha',
                                                                                 'submissions'))


def verify_submit_freeze(run) -> str:
    p = rounds.freeze_dir(run) / 'SUBMIT_FREEZE.json'
    sf = read_json(p)
    if sf is None:
        raise FreezeRefused('SUBMIT_FREEZE.json missing')
    verify_files(run, sf['submissions'])
    return sha256_file(p)


def freeze_knockout(run) -> tuple[Path, str]:
    """Knockout libraries and knockout submissions, frozen before the knockout key read."""
    freeze_sha = verify_freeze(run)
    submit_sha = verify_submit_freeze(run)
    idx = read_json(Path(run.dir) / 'knockout' / 'KO_LIBS.json')
    if idx is None:
        raise FreezeRefused('knockout libraries not built')
    libs = {}
    inl = idx.get('inline') or {}
    inl_entries = [inl] if 'json' in inl else [e for _, e in sorted(inl.items())]   # per-task since the 2026-11-04 fix
    entries = [e for _, e in sorted(idx['libraries'].items())] + inl_entries
    for e in entries:
        for key in ('json', 'py'):
            if e.get(key):
                libs[e[key]] = sha256_file(Path(run.dir) / e[key])
    subs = {}
    for mode in ('delete', 'inline'):
        for k in rounds.sealed_seeds(run):
            d = rounds.knockout_dir(run, mode, k)
            p = d / 'submissions.json'
            if _state(d).get('state') != 'DONE' or not p.exists():
                raise FreezeRefused('knockout %s seed %d submissions missing' % (mode, k))
            subs[p.relative_to(Path(run.dir)).as_posix()] = sha256_file(p)
    body = {'schema': config.KO_FREEZE_SCHEMA, 'run': run.name, 'created_et': now_et(), 'freeze_sha': freeze_sha,
            'submit_sha': submit_sha, 'W': sorted(idx['W']), 'libraries': libs, 'submissions': subs}
    return _write_once(rounds.freeze_dir(run) / 'KO_FREEZE.json', body,
                       ('freeze_sha', 'submit_sha', 'W', 'libraries', 'submissions'))


def ack(run, name: str, sha: str) -> Path:
    """Lead gate: record that the lead committed <name>.json with this sha256."""
    if name not in config.FREEZE_NAMES:
        raise FreezeRefused('unknown freeze %s' % name)
    fd = rounds.freeze_dir(run)
    sf = fd / (name + '.sha256')
    if not sf.exists():
        raise FreezeRefused('%s.sha256 missing' % name)
    want = sf.read_text().split()[0]
    got = sha256_file(fd / (name + '.json'))
    if got != want:
        raise FreezeRefused('%s.json changed since freeze: %s != %s' % (name, got, want))
    if sha != want:
        raise FreezeRefused('ack sha %s does not match %s.json %s' % (sha, name, want))
    p = fd / (name + '.ack')
    atomic_write_bytes(p, ('%s  %s\n' % (want, now_et())).encode('ascii'))
    return p
