"""Builder E test fixtures: a fake sealed key, a fake run with frozen libraries and submissions, a subprocess runner.

The fake key lives in a temp dir. Tests that need the audit hook to protect it run in a subprocess that sets
RATCHET_KEY_ROOT (or calls guard.add_protected_root), so the test process itself never holds an unremovable root.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable
SCORE = REPO / 'score_sealed.py'
ARMS = ('STOCK', 'STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'FLATTTC', 'PLANTDRIP', 'PLANTL1')
SEEDS = (1, 2, 3)
TASKS = tuple(f'e{i}' for i in range(6))
WRONG = [[8]]


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_py(code: str, env_extra: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env['PYTHONPATH'] = str(REPO)
    env.update(env_extra or {})
    return subprocess.run([PY, '-c', code], capture_output=True, text=True, env=env, timeout=300,
                          cwd=str(cwd or REPO))


def run_score(args: list[str], key: Path, data: Path | None = None, test_flag: bool = True) -> subprocess.CompletedProcess:
    """score_sealed.py with a fake key root. --test is required for a non-default key root (review fix 2026-11-04)."""
    env = dict(os.environ)
    env['RATCHET_KEY_ROOT'] = str(key)
    if data is not None:
        env['RATCHET_DATA_ROOT'] = str(data)
    if test_flag and args and args[0] in ('score', 'seal', 'seal-arcagi2'):
        args = [args[0], '--test'] + list(args[1:])
    return subprocess.run([PY, str(SCORE)] + args, capture_output=True, text=True, env=env, timeout=300,
                          cwd=str(REPO))


def ack(run: Path, name: str) -> str:
    """The lead's ack of freeze/<name>.json (what `ratchet freeze --ack` writes)."""
    s = sha(run / 'freeze' / f'{name}.json')
    (run / 'freeze' / f'{name}.ack').write_text(f'{s}  2026-11-04 12:00:00 ET\n')
    return s


LEVER_LINES = {
    'STOCK': ['LEVER STOCK library r=2 sha=abc updated=1 helpers_in_context=2', 'LEVER PERTURB seed=20261104 tasks=6'],
    'STATIC': ['LEVER STATIC library r=2 sha=abc frozen=1'],
    'ONESHOT': ['LEVER ONESHOT round=1 slots_per_task=4'],
    'EXEMPLAR': ['LEVER EXEMPLAR task=e0 k=3 exemplar_tokens=100'],
    'SHAM': ['LEVER SHAM matched=2 of 2 tokens=10 target=10 verified=0'],
    'FLATTTC': ['LEVER FLATTTC seed=1 extra=10 target_tokens=100 realized_tokens=100',
                'LEVER PERTURB seed=20261104 tasks=6'],
    'PLANTDRIP': ['LEVER PLANTDRIP tranche=2 of 2 primitives=5'],
    'PLANTL1': ['LEVER PLANTL1 tranche=1 primitives=3'],
}


def write_levers(run: Path, skip: tuple = ()) -> None:
    """Rule-6 marker lines (SPEC 9) in logs/server_<ARM>_sealed_fixture.log for every arm not in `skip`."""
    for arm, lines in LEVER_LINES.items():
        if arm in skip:
            continue
        common = ['LEVER SANDBOX lib_sha=abc helpers_callable=2 net=unshare fs=bwrap',
                  'LEVER NOTHINK first_response_has_think=0', 'LEVER PREFIX hit_rate=0.5000']
        p = run / 'logs' / f'server_{arm}_sealed_fixture.log'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('META fixture\n' + '\n'.join(common + lines) + '\n')


def out_grid(i: int):
    return [[i]]


def write_json(p: Path, obj) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, sort_keys=True))
    return p


def make_key(root: Path) -> tuple[Path, Path]:
    """Fake ARC-AGI-1 evaluation dir -> data/sealed (inputs only) and key/arcagi1 (mode 000) via score_sealed._seal_split."""
    import score_sealed
    ev = root / 'raw_eval'
    for i, t in enumerate(TASKS):
        write_json(ev / f'{t}.json', {'train': [{'input': [[i]], 'output': out_grid(i)}],
                                      'test': [{'input': [[i]], 'output': out_grid(i)}]})
    key = root / 'key'
    data = root / 'data'
    score_sealed._seal_split(ev, list(TASKS), data / 'sealed', key / 'arcagi1')
    os.chmod(key, 0o700)
    return key, data


def _sub(task: str, outputs: list, sids: list[str]) -> dict:
    return {'task': task, 'n_candidates': len(sids), 'n_demo_pass': len(sids),
            'attempts': [{'outputs': outputs, 'votes': len(sids), 'min_len': 10, 'sample_ids': sids}]}


def make_run(root: Path, perturb_seed: int = 20261104, manifest_seed: int | None = None) -> dict:
    """A run where COMPOUNDS holds:
    - STOCK correct on e0..e4 in all seeds, e5 only in seed 1 (so e5 fails the 2-of-3 rule); FLATTTC correct on e5 in
      seed 2 only; STATIC, ONESHOT, EXEMPLAR, SHAM, PLANTL1 never correct; PLANTDRIP correct everywhere.
    - perturbed STOCK correct on e0..e4, perturbed FLATTTC never.
    - winners e0..e3 call helper h1 at runtime, e4's winner calls nothing (reuse 4 of 5).
    - knockout delete keeps e0, e1; inline keeps e0 (each <= 5 // 2 = 2)."""
    from ratchet import perturb
    run = root / 'runs' / 'v1'
    lib = write_json(run / 'arms/STOCK/round_2/L_2.json', {'arm': 'STOCK', 'round': 2, 'helpers': [
        {'name': 'h1', 'deps': [], 'in_context': True, 'first_round': 1},
        {'name': 'h2', 'deps': ['h1'], 'in_context': True, 'first_round': 2}]})
    libs = {}
    for arm in ARMS:
        if arm == 'FLATTTC':
            libs[arm] = None
            continue
        p = lib if arm == 'STOCK' else write_json(run / f'arms/{arm}/L.json', {'arm': arm, 'helpers': []})
        libs[arm] = {'json': p.relative_to(run).as_posix(), 'py': None, 'sha256_json': sha(p), 'sha256_py': None}
    fz = write_json(run / 'freeze/FREEZE.json', {'schema': 'ratchet.freeze.v1', 'run': 'v1', 'S': 2, 'R': 2,
                                                 'sealed_seeds': list(SEEDS), 'perturb_seed': perturb_seed,
                                                 'libraries': libs, 'flat_budget': None})
    fsha = sha(fz)
    (run / 'freeze/FREEZE.sha256').write_text(f'{fsha}  FREEZE.json\n')

    def correct_for(cond, arm, k, t):
        i = int(t[1:])
        if cond == 'perturbed':
            return arm == 'STOCK' and i <= 4
        if arm == 'STOCK':
            return i <= 4 or k == 1
        if arm == 'FLATTTC':
            return i == 5 and k == 2
        return arm == 'PLANTDRIP'

    subs_listed = {}
    for cond, arms in (('sealed', ARMS), ('perturbed', ('STOCK', 'FLATTTC'))):
        for arm in arms:
            for k in SEEDS:
                subs = []
                for t in TASKS:
                    i = int(t[1:])
                    good = out_grid(i)
                    if cond == 'perturbed':
                        good = [list(r) for r in perturb.apply_grid(((i,),), perturb.draw(t, perturb_seed))]
                    o = good if correct_for(cond, arm, k, t) else WRONG
                    subs.append(_sub(t, [o], [f'{arm}|{cond}|k{k}|{t}|s0', f'{arm}|{cond}|k{k}|{t}|s1']))
                p = write_json(run / f'sealed/{cond}/{arm}/seed_{k}/submissions.json',
                               {'schema': 'ratchet.submissions.v1', 'arm': arm, 'condition': cond, 'submissions': subs})
                subs_listed[p.relative_to(run).as_posix()] = sha(p)
                if cond == 'sealed' and arm == 'STOCK':
                    rows = []
                    for t in TASKS:
                        calls = {'h1': 2} if t in ('e0', 'e1', 'e2', 'e3') else {}
                        for s in (0, 1):
                            rows.append({'sample_id': f'STOCK|sealed|k{k}|{t}|s{s}', 'code_sha': f'code_{t}',
                                         'status': 'OK', 'demo_pass': True, 'helper_calls': calls})
                    (p.parent / 'exec.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    # PERTURB.json and the perturbed task files (inputs only), bound into SUBMIT_FREEZE (review fix 2026-11-04)
    pdata = root / 'data'
    rows = {}
    for t in TASKS:
        f = write_json(pdata / 'sealed_perturbed' / f'{t}.json', {'train': [], 'test': [{'input': [[int(t[1:])]]}]})
        rows[t] = {**perturb.draw(t, perturb_seed).to_json(), 'out_sha256': sha(f)}
    pm = write_json(pdata / 'PERTURB.json', {'schema': 'ratchet.perturb.v1', 'n_tasks': len(TASKS), 'tasks': rows,
                                             'seed': perturb_seed if manifest_seed is None else manifest_seed})
    sf = write_json(run / 'freeze/SUBMIT_FREEZE.json', {'schema': 'ratchet.submit_freeze.v1', 'freeze_sha': fsha,
                                                        'submissions': subs_listed, 'FLAT_BUDGET': {},
                                                        'perturb': {'path': str(pm.resolve()), 'sha256': sha(pm)}})
    ack(run, 'FREEZE')
    ack(run, 'SUBMIT_FREEZE')
    write_levers(run)
    write_json(run / 'PILOT.json', {'status': 'OK', 'S': 2, 'R': 2, 'underpowered': False,
                                    'choice': {'status': 'OK', 'S': 2, 'R': 2, 'power': 0.9}})
    return {'run': run, 'freeze_sha': fsha, 'submit_sha': sha(sf)}


def make_knockout(run: Path, freeze_sha: str, submit_sha: str) -> str:
    """Knockout submissions (delete keeps e0, e1; inline keeps e0) and a KO_FREEZE.json in builder D's format."""
    W = json.loads((run / 'scores/W.json').read_text())['W']
    libp = write_json(run / 'knockout/libraries/e0/L_ko_e0.json', {'helpers': []})
    subs = {}
    for mode, keep in (('delete', ('e0', 'e1')), ('inline', ('e0',))):
        for k in SEEDS:
            items = []
            for t in W:
                o = out_grid(int(t[1:])) if t in keep else WRONG
                items.append(_sub(t, [o], [f'STOCK|knockout_{mode}|k{k}|{t}|s0']))
            p = write_json(run / f'knockout/{mode}/seed_{k}/submissions.json', {'submissions': items})
            subs[p.relative_to(run).as_posix()] = sha(p)
    ko = write_json(run / 'freeze/KO_FREEZE.json', {
        'schema': 'ratchet.ko_freeze.v1', 'freeze_sha': freeze_sha, 'submit_sha': submit_sha, 'W': W,
        'libraries': {libp.relative_to(run).as_posix(): sha(libp)}, 'submissions': subs})
    (run / 'logs' / 'server_STOCK_knockout_fixture.log').write_text(
        'META fixture\nLEVER KO_DELETE task=e0 removed=h1 kept=h2\nLEVER KO_INLINE task=e0 callable=0 inlined=h1\n')
    return ack(run, 'KO_FREEZE')


def key_modes(key: Path) -> list[int]:
    out = []
    for dp, dns, fns in os.walk(key):
        for fn in fns:
            out.append(os.lstat(os.path.join(dp, fn)).st_mode & 0o777)
    return out
