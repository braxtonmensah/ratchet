"""PREREG AMENDMENT 4 (silicyte-0119): apply a sec. 7.3 budget amendment to a stopped run WITHOUT re-sampling the pilot.

Pilot v2 (runs/v2) stopped on PILOT_NO_FEASIBLE_SR at the registered 12 H100-hours. AMENDMENT 4 changes only that budget
(to 48); the rule "largest S in {4, 8, 16} and R in {4, 6, 8} that fits" is unchanged. This module re-runs that rule on
the rates PILOT.json already recorded (re-projecting every grid cell and refusing if any projection drifts from the
recorded one), then:

  1. archives PILOT.json, PILOT.md and pilot/PILOT_CHOICE.json as *.pre_A<id>.* (never deleting pilot data),
  2. writes the new PILOT.json, PILOT.md and pilot/PILOT_CHOICE.json (status OK, the chosen S and R),
  3. records the amendment in RUN.json (h100_hours_budget, budget_amendment with the sha256 of the PREREG block) and
     appends it to the run-level AMENDMENTS.json, sets S and R in RUN.json,
  4. moves pilot/PILOT_STOP.json to pilot/PILOT_STOP.superseded_A<id>.json, so rounds.next_unit plans growth.

Refusals: the amendment id is not in PREREG.md's AMENDMENTS (or still carries the HH:MM placeholder, or does not state
the budget); the budget does not yield a feasible (S, R); any growth, sealed, knockout or freeze artefact exists, or any
non-pilot ledger row; S or R already set; the pilot did not stop on PILOT_NO_FEASIBLE_SR with smoke and gate passing.
Grants no key access: it reads only PILOT.json, RUN.json, the run's directory listing and PREREG.md.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from . import pilot
from .e_util import cfg, now_et, read_json, write_json_atomic, write_text_atomic

STOP_REASON = 'PILOT_NO_FEASIBLE_SR'
NON_PILOT_DIRS = ('arms', 'sealed', 'knockout', 'freeze', 'scores')
NON_PILOT_FILES = ('PERTURB_DONE.json', 'RESULT.md')


class AmendRefused(RuntimeError):
    pass


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def prereg_block(prereg_path: Path, amendment_id: str) -> str:
    """The text of '- AMENDMENT <id> (' under '## AMENDMENTS', up to the next '- AMENDMENT ' item, heading or EOF.
    Lines are kept as written (right-stripped), joined by '\\n', no trailing newline."""
    text = Path(prereg_path).read_text(encoding='utf-8')
    lines = [ln.rstrip() for ln in text.splitlines()]
    try:
        start = lines.index('## AMENDMENTS')
    except ValueError:
        raise AmendRefused(f'PREREG_NO_AMENDMENTS_SECTION {prereg_path}')
    head = re.compile(r'^- AMENDMENT %s \(' % re.escape(str(amendment_id)))
    hits = [i for i in range(start + 1, len(lines)) if head.match(lines[i])]
    if len(hits) != 1:
        raise AmendRefused(f'AMENDMENT_NOT_IN_PREREG id={amendment_id} matches={len(hits)} in {prereg_path}')
    i = hits[0]
    j = i + 1
    while j < len(lines) and not (lines[j].startswith('- AMENDMENT ') or lines[j].startswith('#')):
        j += 1
    while j > i + 1 and not lines[j - 1].strip():
        j -= 1
    return '\n'.join(lines[i:j])


def _check_block(block: str, amendment_id: str, budget: float) -> None:
    if 'HH:MM' in block:
        raise AmendRefused(f'AMENDMENT_TIME_PLACEHOLDER id={amendment_id}: fill the HH:MM time before applying')
    flat = ' '.join(block.split())
    b = int(budget) if float(budget).is_integer() else budget
    if f'{b} H100-hours' not in flat:
        raise AmendRefused(f'AMENDMENT_BUDGET_NOT_STATED id={amendment_id} budget={b}: the block does not say '
                           f'"{b} H100-hours"')


def growth_started(run_dir: Path) -> list[str]:
    """Every artefact that shows the run went past the pilot (empty list = nothing)."""
    run_dir = Path(run_dir)
    found = []
    for d in NON_PILOT_DIRS:
        p = run_dir / d
        if p.exists() and (not p.is_dir() or any(p.iterdir())):
            found.append(d + '/')
    for f in NON_PILOT_FILES:
        if (run_dir / f).exists():
            found.append(f)
    other = sorted({str(r.get('phase')) for r in pilot.ledger_rows(run_dir, phase=None) if r.get('phase') != 'pilot'})
    found += ['ledger phase=%s' % p for p in other]
    return found


def _code_sha() -> str | None:
    try:
        from .arms import code_git_sha
        return code_git_sha()
    except Exception:  # noqa: BLE001
        return None


def _grid_key(g: dict) -> tuple:
    return (int(g['S']), int(g['R']))


def rechoose(pil: dict, budget: float) -> dict:
    """PREREG 7.3 on the recorded pilot rates at `budget`, reusing the recorded power. Refuses on projection drift."""
    rates = pil.get('rates') or {}
    old = pil.get('choice') or {}
    new = pilot.choose_SR(rates, budget=budget, power=old.get('power'))
    old_jobs = {_grid_key(g): int(g['jobs']) for g in old.get('grid') or []}
    new_jobs = {_grid_key(g): int(g['jobs']) for g in new.get('grid') or []}
    if not old_jobs or old_jobs != new_jobs:
        raise AmendRefused(f'PROJECTION_DRIFT recorded={sorted(old_jobs.items())} now={sorted(new_jobs.items())}')
    if old.get('power') is not None:
        new['power_all5_independent'] = old.get('power_all5_independent', new.get('power_all5_independent'))
        new['underpowered'] = float(old['power']) < float(cfg('POWER_MIN'))
    return new


def apply_budget_amendment(run_dir: Path, amendment_id: str, budget: float, prereg_path: Path,
                           dry_run: bool = False) -> dict:
    run_dir = Path(run_dir)
    aid = str(amendment_id)
    tag = 'A' + aid
    pdir = run_dir / 'pilot'
    stop_p, choice_p = pdir / 'PILOT_STOP.json', pdir / 'PILOT_CHOICE.json'
    stop_arch = pdir / f'PILOT_STOP.superseded_{tag}.json'
    budget = float(budget)

    # 1. the amendment must be in PREREG, filled in, and state this budget
    block = prereg_block(Path(prereg_path), aid)
    _check_block(block, aid, budget)
    prereg_bytes = Path(prereg_path).read_bytes()

    # 2. the run must be stopped on PILOT_NO_FEASIBLE_SR with nothing past the pilot
    run = read_json(run_dir / 'RUN.json', None)
    if run is None:
        raise AmendRefused(f'NO_RUN_JSON {run_dir}')
    done = growth_started(run_dir)
    if done:
        raise AmendRefused('GROWTH_STARTED ' + ', '.join(done))
    if run.get('S') is not None or run.get('R') is not None:
        raise AmendRefused(f'RUN_SR_ALREADY_SET S={run.get("S")} R={run.get("R")}')
    if run.get('budget_amendment'):
        raise AmendRefused(f'BUDGET_ALREADY_AMENDED {run["budget_amendment"].get("id")}')
    if not stop_p.exists():
        raise AmendRefused(f'NO_PILOT_STOP {stop_p}')
    if stop_arch.exists():
        raise AmendRefused(f'ARCHIVE_EXISTS {stop_arch}')
    stop = read_json(stop_p, {}) or {}
    if stop.get('reason') != STOP_REASON:
        raise AmendRefused(f'PILOT_STOP_REASON {stop.get("reason")} (this amendment only applies to {STOP_REASON})')
    pil = read_json(run_dir / 'PILOT.json', None)
    if pil is None:
        raise AmendRefused(f'NO_PILOT_JSON {run_dir}')
    if pil.get('status') != STOP_REASON:
        raise AmendRefused(f'PILOT_STATUS {pil.get("status")}')
    if not (pil.get('smoke') or {}).get('pass') or not (pil.get('plant') or {}).get('pass'):
        raise AmendRefused('PILOT_GATES_NOT_PASSED')

    # 3. re-choose on the recorded rates
    choice = rechoose(pil, budget)
    if choice.get('status') != 'OK':
        raise AmendRefused(f'STILL_INFEASIBLE status={choice.get("status")} budget={budget:g} '
                           f'min_jobs={min(g["jobs"] for g in choice["grid"])}')
    S, R = int(choice['S']), int(choice['R'])
    rec = {'id': aid, 'kind': 'sec7.3_budget', 'h100_hours_budget': budget,
           'registered_h100_hours_budget': float(cfg('H100_HOURS_BUDGET')),
           'prereg_block_sha256': _sha(block.encode('utf-8')), 'prereg_file_sha256': _sha(prereg_bytes),
           'prereg_path': str(prereg_path), 'S': S, 'R': R, 'jobs': int(choice['chosen']['jobs']),
           'power': choice.get('power'), 'pilot_json_sha256_before': _sha((run_dir / 'PILOT.json').read_bytes()),
           'superseded_stop': stop, 'applied_code_sha': _code_sha(), 'applied_et': now_et()}
    if dry_run:
        return {'dry_run': True, 'record': rec, 'choice_status': choice['status']}

    # 4. archive (copy) the pre-amendment pilot outputs; never delete
    for src, dst in ((run_dir / 'PILOT.json', run_dir / f'PILOT.pre_{tag}.json'),
                     (run_dir / 'PILOT.md', run_dir / f'PILOT.pre_{tag}.md'),
                     (choice_p, pdir / f'PILOT_CHOICE.pre_{tag}.json')):
        if dst.exists():
            raise AmendRefused(f'ARCHIVE_EXISTS {dst}')
        if src.exists():
            shutil.copy2(src, dst)

    # 5. new pilot outputs
    new_pil = dict(pil)
    new_pil.update({'status': 'OK', 'choice': choice, 'S': S, 'R': R, 'underpowered': choice.get('underpowered'),
                    'budget_amendment': rec, 'rechosen_et': rec['applied_et']})
    write_json_atomic(run_dir / 'PILOT.json', new_pil)
    write_text_atomic(run_dir / 'PILOT.md', pilot.render_pilot_md(new_pil))
    old_choice = read_json(choice_p, {}) or {}
    write_json_atomic(choice_p, {'smoke': pil.get('smoke'), 'plant': pil.get('plant'), 'choice': choice,
                                 'status': 'OK', 'report': str(run_dir / 'PILOT.md'), 'created_et': rec['applied_et'],
                                 'budget_amendment': rec,
                                 'superseded': {'file': f'PILOT_CHOICE.pre_{tag}.json',
                                                'created_et': old_choice.get('created_et')}})

    # 6. run-level record, then S and R
    al = read_json(run_dir / 'AMENDMENTS.json', None) or {'schema': 'ratchet.run_amendments.v1', 'amendments': []}
    al['amendments'].append(rec)
    write_json_atomic(run_dir / 'AMENDMENTS.json', al)
    run = read_json(run_dir / 'RUN.json', {}) or {}
    run.update({'S': S, 'R': R, 'pilot_choice': choice, 'pilot_underpowered': choice.get('underpowered'),
                'h100_hours_budget': budget, 'budget_amendment': rec})
    write_json_atomic(run_dir / 'RUN.json', run)

    # 7. last: lift the stop (moved, not deleted)
    stop_p.replace(stop_arch)
    return {'dry_run': False, 'record': rec, 'S': S, 'R': R, 'archived_stop': str(stop_arch)}
