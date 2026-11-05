"""PREREG 6, 8, 9 verdict and RESULT.md (SPEC 13 I13 precedence). Reads scores/ (written by score_sealed.py),
PILOT.json and runs/ATTEMPTS.json; never opens the key.

Precedence: VOID (PLANT-DRIP does not beat PLANT-L1 at p < 0.05); else COMPOUNDS (6.1 to 6.4 all pass); else
LIBRARY HELPS, NOT COMPOUNDING (beats FLAT-TTC, not STATIC); else CONTEXT EFFECT (6.1 holds, reuse fails); else RETRIEVAL
(6.1 and 6.2 hold, contamination fails); else NULL. UNDERPOWERED is a tag on any label. While 6.1, 6.2 and 6.4 pass and
the knockout read has not happened, the label is PENDING_KNOCKOUT (not a registered outcome; nothing is published).

Review fixes 2026-11-04: a registered label (RESULT.md) also needs (a) PILOT.json with a computed power (PREREG 7.3;
otherwise POWER_MISSING or PILOT_MISSING, except a skip_pilot test run) and (b) every rule-6 lever marker of SPEC 9 in
the run's own logs, plus STOCK's frozen L_R putting in context a non-empty helper set that differs from L_1's. A failed
check writes RESULT_DRAFT.md with the reason (LEVER_VOID: <arm> <marker>); no ratio from a VOID arm is a result.
"""
from __future__ import annotations

import glob
import os
import re
from pathlib import Path

from .e_util import cfg, now_et, read_json, write_json_atomic, write_text_atomic

LABELS = ('VOID', 'COMPOUNDS', 'LIBRARY HELPS, NOT COMPOUNDING', 'CONTEXT EFFECT', 'RETRIEVAL', 'NULL',
          'PENDING_KNOCKOUT', 'NOT_SCORED')


def decide(primary: dict | None, knockout: dict | None) -> dict:
    if not primary:
        return {'label': 'NOT_SCORED', 'c1': None, 'c2': None, 'c3': None, 'c4': None, 'void': None}
    comps = primary['compare']
    flat = cfg('FLAT_ARM')
    void = not primary['void_compare']['pass']
    c1 = all(comps[f'STOCK_vs_{b}']['pass'] for b in cfg('COMPARATORS'))
    c2 = bool(primary['reuse']['pass'])
    c3 = None if knockout is None else bool(knockout['pass'])
    c4 = bool(primary['contamination']['pass'])
    beats_flat = comps[f'STOCK_vs_{flat}']['pass']
    beats_static = comps['STOCK_vs_STATIC']['pass']
    if void:
        label = 'VOID'
    elif c1 and c2 and c4 and c3 is None:
        label = 'PENDING_KNOCKOUT'
    elif c1 and c2 and c3 and c4:
        label = 'COMPOUNDS'
    elif beats_flat and not beats_static:
        label = 'LIBRARY HELPS, NOT COMPOUNDING'
    elif c1 and not c2:
        label = 'CONTEXT EFFECT'
    elif c1 and c2 and not c4:
        label = 'RETRIEVAL'
    else:
        label = 'NULL'
    return {'label': label, 'void': void, 'c1': c1, 'c2': c2, 'c3': c3, 'c4': c4,
            'beats_flat': beats_flat, 'beats_static': beats_static}


# SPEC 9 marker regexes (rule 6). Each arm's logs/server_<ARM>_*.log must carry every listed marker.
_EVERY_ARM = {'SANDBOX': r'LEVER SANDBOX lib_sha=\w+ helpers_callable=\d+ net=unshare',
              'NOTHINK': r'LEVER NOTHINK first_response_has_think=0',
              'PREFIX': r'LEVER PREFIX hit_rate=(0\.\d+|1\.0+)\b'}
_ARM_MARKERS = {
    'STOCK': {'STOCK': r'LEVER STOCK library r=[2-9]\d* .*updated=1', 'PERTURB': r'LEVER PERTURB seed=\d+ tasks=\d+'},
    'STATIC': {'STATIC': r'LEVER STATIC library r=\d+ sha=\w+ frozen=1'},
    'ONESHOT': {'ONESHOT': r'LEVER ONESHOT round=1 slots_per_task=\d+'},
    'EXEMPLAR': {'EXEMPLAR': r'LEVER EXEMPLAR task=\w+ k=[1-3] exemplar_tokens=\d+'},
    'SHAM': {'SHAM': r'LEVER SHAM matched=\d+ of \d+ tokens=\d+ target=\d+ verified=0'},
    'FLATTTC': {'FLATTTC': r'LEVER FLATTTC seed=\d extra=\d+ target_tokens=\d+ realized_tokens=\d+',
                'PERTURB': r'LEVER PERTURB seed=\d+ tasks=\d+'},
    'PLANTDRIP': {'PLANTDRIP': r'LEVER PLANTDRIP tranche=\d+ of \d+ primitives=\d+'},
    'PLANTL1': {'PLANTL1': r'LEVER PLANTL1 tranche=1 primitives=\d+'},
}
_VOID_LINES = {'NOTHINK': r'LEVER NOTHINK first_response_has_think=1'}
_KO_MARKERS = {'KO_DELETE': r'LEVER KO_DELETE task=\w+ removed=\S+', 'KO_INLINE': r'LEVER KO_INLINE task=\w+ callable=0'}


def _arm_log_text(run_dir: Path, arm: str) -> str:
    out = []
    for p in sorted(glob.glob(os.path.join(str(run_dir), 'logs', 'server_%s_*.log' % arm))):
        out.append(Path(p).read_text(encoding='utf-8', errors='replace'))
    return ''.join(out)


def _in_ctx_set(run_dir: Path, rel: str | None) -> frozenset | None:
    if not rel:
        return None
    lib = read_json(Path(run_dir) / rel, None)
    if lib is None:
        return None
    return frozenset(h.get('hash') or h.get('name') for h in lib.get('helpers', []) if h.get('in_context'))


def lever_status(run_dir: Path, with_knockout: bool = False) -> dict:
    """Rule 6 before any registered label: every SPEC 9 marker of every arm in its own logs, no NOTHINK=1 line, and
    STOCK's frozen L_R putting in context a non-empty helper set that differs from L_1's (read from the frozen files).
    A run on the real runs tree also needs the bwrap mount view (fs=bwrap) on every arm's SANDBOX line."""
    run_dir = Path(run_dir)
    void: list[str] = []
    try:
        from .config import REAL_RUNS_DIR
        prod = os.path.realpath(str(run_dir)).startswith(os.path.realpath(str(REAL_RUNS_DIR)) + os.sep)
    except Exception:  # noqa: BLE001
        prod = False
    perturb_text = _arm_log_text(run_dir, 'PERTURB')
    for arm in cfg('ARMS'):
        text = _arm_log_text(run_dir, arm)
        if not text:
            void.append('%s no_logs' % arm)
            continue
        for name, rx in list(_EVERY_ARM.items()) + list(_ARM_MARKERS.get(arm, {}).items()):
            hay = text + (perturb_text if name == 'PERTURB' else '')
            if not re.search(rx, hay):
                void.append('%s %s' % (arm, name))
        if prod and not re.search(r'LEVER SANDBOX .*net=unshare fs=bwrap', text):
            void.append('%s SANDBOX_FS' % arm)
        for name, rx in _VOID_LINES.items():
            if re.search(rx, text):
                void.append('%s %s=1' % (arm, name))
    if with_knockout:
        text = _arm_log_text(run_dir, 'STOCK')
        for name, rx in _KO_MARKERS.items():
            if not re.search(rx, text):
                void.append('STOCK %s' % name)
    fz = read_json(run_dir / 'freeze' / 'FREEZE.json', {}) or {}
    libs = fz.get('libraries') or {}
    lr = _in_ctx_set(run_dir, (libs.get('STOCK') or {}).get('json'))
    l1 = _in_ctx_set(run_dir, (libs.get('STATIC') or {}).get('json'))
    if lr is None:
        void.append('STOCK L_R_unreadable')
    elif not lr:
        void.append('STOCK L_R_no_helpers_in_context')
    elif l1 is not None and lr == l1:
        void.append('STOCK L_R_in_context_equals_L_1')
    return {'void': void, 'ok': not void, 'production': prod}


def pilot_status(run_dir: Path) -> str:
    """'' if PILOT.json has a computed power (or the run is a skip_pilot test run), else PILOT_MISSING/POWER_MISSING."""
    run = read_json(Path(run_dir) / 'RUN.json', {}) or {}
    pil = read_json(Path(run_dir) / 'PILOT.json', None)
    if pil is None:
        return '' if run.get('skip_pilot') else 'PILOT_MISSING'
    if (pil.get('choice') or {}).get('power') is None:
        return 'POWER_MISSING'
    return ''


def _flat_match(run_dir: Path) -> dict:
    """Realized FLAT-TTC tokens against STOCK's total per seed and condition (SPEC 13 I2: FLAT gets its base samples
    plus round(T_STOCK / m_F) extra, so its total is above STOCK's; reported, review fix 2026-11-04)."""
    sf = read_json(Path(run_dir) / 'freeze' / 'SUBMIT_FREEZE.json', {}) or {}
    out = {}
    for cond, seeds in sorted((sf.get('FLAT_BUDGET') or {}).items()):
        for k, b in sorted(seeds.items()):
            real = b.get('realized') or {}
            tot = (real.get('base') or 0) + (real.get('extra') or 0)
            tgt = b.get('target_tokens') or 0
            out['%s/%s' % (cond, k)] = {'target_tokens': tgt, 'flat_base': real.get('base'),
                                         'flat_extra': real.get('extra'), 'flat_total': tot,
                                         'ratio_total_to_stock': (tot / tgt) if tgt else None}
    return out


def _attempts_path(run_dir: Path) -> Path:
    return Path(run_dir).parent / 'ATTEMPTS.json'


def record_attempt(run_dir: Path, label: str) -> dict:
    """Idempotent: a VOID run is listed once in runs/ATTEMPTS.json; retired after VOID_MAX_ATTEMPTS (PREREG 9)."""
    p = _attempts_path(run_dir)
    a = read_json(p, {}) or {}
    void_runs = list(a.get('void_runs', []))
    name = Path(run_dir).name
    if label == 'VOID' and name not in void_runs:
        void_runs.append(name)
        a['void_runs'] = void_runs
        a['updated_et'] = now_et()
        a['retired'] = len(void_runs) >= int(cfg('VOID_MAX_ATTEMPTS'))   # written, so init, step and score refuse
        write_json_atomic(p, a)
    a.setdefault('void_runs', void_runs)
    a['retired'] = len(void_runs) >= int(cfg('VOID_MAX_ATTEMPTS'))
    return a


def verdict(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    g = read_json(run_dir / 'scores' / 'gates.json', {}) or {}
    primary, knockout = g.get('primary'), g.get('knockout')
    d = decide(primary, knockout)
    pil = read_json(run_dir / 'PILOT.json', {}) or {}
    under = bool(pil.get('underpowered'))
    d['underpowered'] = under
    d['label_tagged'] = d['label'] + (' (UNDERPOWERED)' if under else '')
    d['primary'] = primary
    d['knockout'] = knockout
    blocks = []
    ps = pilot_status(run_dir)
    if ps:
        blocks.append(ps)
    if primary:
        lv = lever_status(run_dir, with_knockout=knockout is not None)
        d['levers'] = lv
        if not lv['ok']:
            blocks.append('LEVER_VOID: ' + '; '.join(lv['void']))
    d['blocks'] = blocks
    if blocks:
        d['label_tagged'] += ' (NOT REGISTERED: %s)' % ' | '.join(blocks)
    d['flat_match'] = _flat_match(run_dir)
    d['arcagi2'] = g.get('arcagi2')
    d['pilot'] = {k: pil.get(k) for k in ('status', 'S', 'R', 'underpowered')}
    if pil.get('choice'):
        d['pilot']['power'] = pil['choice'].get('power')
    if primary:
        q = primary['pred_stock_minus_static']
        lo, hi = cfg('PRED_BAND')
        clo, chi = cfg('PRED_BAND_CALIBRATED')
        d['prediction'] = {'quantity': q, 'point': cfg('PRED_POINT'), 'band': [lo, hi], 'in_band': lo <= q <= hi,
                           'band_calibrated': [clo, chi], 'in_band_calibrated': clo <= q <= chi,
                           'p_compounds_prior': cfg('P_COMPOUNDS')}
    return d


def _yn(x) -> str:
    return 'n/a' if x is None else ('PASS' if x else 'FAIL')


def render_result(run_dir: Path, v: dict) -> str:
    from . import report
    L = ['# RESULT ratchet_v1 (silicyte-0119)', '', f'Written {now_et()} from scores/ (score_sealed.py) and the loop logs.',
         '', f'**Outcome: {v["label_tagged"]}**', '']
    p = v.get('primary')
    if p:
        L += ['## PREREG 6 gates', '',
              f'- VOID check, PLANT-DRIP vs PLANT-L1: b = {p["void_compare"]["b_only_a"]}, c = {p["void_compare"]["c_only_b"]}, '
              f'p = {p["void_compare"]["p"]:.6f}: {"VOID" if v["void"] else "valid positive control"}',
              f'- 6.1 STOCK beats every comparator: {_yn(v["c1"])}']
        for b in cfg('COMPARATORS'):
            c = p['compare'][f'STOCK_vs_{b}']
            L.append(f'  - vs {b}: STOCK {c["solved_a"]}, {b} {c["solved_b"]}, b = {c["b_only_a"]}, c = {c["c_only_b"]}, '
                     f'net {c["net"]:+d}, exact one-sided p = {c["p"]:.6f}: {_yn(c["pass"])}')
        r = p['reuse']
        L += [f'- 6.2 reuse gate: {r["programs_calling"]} of {r["programs"]} distinct winning programs on W '
              f'({p["W"]} tasks) call an accepted helper, fraction {r["fraction"]:.4f} (needs >= {r["min_fraction"]}); '
              f'samples {r["samples_calling"]} of {r["samples"]}: {_yn(v["c2"])}']
        k = v.get('knockout')
        if k:
            L.append(f'- 6.3 knockout: W = {k["W"]}, kept after delete {k["kept_delete"]}, kept after inline '
                     f'{k["kept_inline"]} (each must be <= {k["max_kept"]}): {_yn(v["c3"])}')
        else:
            L.append('- 6.3 knockout: not scored yet')
        ct = p['contamination']
        L += [f'- 6.4 contamination: net gain over FLAT-TTC unperturbed {ct["net_primary"]:+d}, perturbed '
              f'{ct["net_perturbed"]:+d} (needs perturbed >= half of unperturbed): {_yn(v["c4"])}', '',
              '## A/A noise (FLAT-TTC sealed seeds)', '']
        for a in p.get('aa_flat', []):
            L.append(f'- seed {a["seed_a"]} vs seed {a["seed_b"]}: b = {a["b"]}, c = {a["c"]}, net {a["net"]:+d}, '
                     f'discordant {a["discordant"]}, p = {a["p"]:.6f}')
        pr = v.get('prediction')
        if pr:
            L += ['', '## PREREG 8 prediction', '',
                  f'STOCK minus STATIC net sealed solves: {pr["quantity"]:+d} (registered point {pr["point"]:+d}, '
                  f'80% band [{pr["band"][0]}, {pr["band"][1]}]: {"inside" if pr["in_band"] else "outside"}; '
                  f'calibrated band [{pr["band_calibrated"][0]}, {pr["band_calibrated"][1]}]: '
                  f'{"inside" if pr["in_band_calibrated"] else "outside"}). Registered P(COMPOUNDS) = {pr["p_compounds_prior"]}.']
    fm = v.get('flat_match') or {}
    if fm:
        L += ['', '## FLAT-TTC token match (SPEC 13 I2: base samples plus round(T_STOCK / m_F) extra)', '']
        for key, m in fm.items():
            r = m['ratio_total_to_stock']
            L.append(f'- {key}: STOCK total {m["target_tokens"]}, FLAT base {m["flat_base"]} + extra {m["flat_extra"]} '
                     f'= {m["flat_total"]} (ratio {"n/a" if r is None else f"{r:.4f}"})')
    if v.get('blocks'):
        L += ['', '## Not a registered outcome yet', ''] + [f'- {b}' for b in v['blocks']]
    pil = v.get('pilot') or {}
    L += ['', '## Pilot', '', f'S = {pil.get("S")}, R = {pil.get("R")}, pilot status {pil.get("status")}, '
          f'projected power {pil.get("power")}, underpowered {pil.get("underpowered")}.']
    if v.get('attempts'):
        a = v['attempts']
        L += ['', f'VOID runs so far: {len(a.get("void_runs", []))} ({", ".join(a.get("void_runs", [])) or "none"}); '
                  f'harness retired: {a.get("retired")}.']
    L += ['', report.render_tables(run_dir), report.render_map(run_dir)]
    if v.get('arcagi2'):
        L += ['## Secondary read (ARC-AGI-2, reported, not decisive)', '',
              ', '.join(f'{a}: {n}' for a, n in sorted(v['arcagi2']['counts'].items()))]
    text = '\n'.join(L) + '\n'
    return text.replace(chr(0x2014), ', ').replace(chr(0x2013), '-')


def write_result(run_dir: Path, repo_dir: Path | None = None) -> Path:
    run_dir = Path(run_dir)
    v = verdict(run_dir)
    final = v['label'] not in ('NOT_SCORED', 'PENDING_KNOCKOUT') and not v.get('blocks')
    if final:
        v['attempts'] = record_attempt(run_dir, v['label'])
    text = render_result(run_dir, v)
    # RESULT.md only for a registered outcome: its existence unlocks the ARC-AGI-2 read (SPEC 13 I16)
    out = write_text_atomic(run_dir / ('RESULT.md' if final else 'RESULT_DRAFT.md'), text)
    write_json_atomic(run_dir / 'VERDICT.json', {k: v.get(k) for k in (
        'label', 'label_tagged', 'void', 'c1', 'c2', 'c3', 'c4', 'beats_flat', 'beats_static', 'underpowered',
        'prediction', 'pilot', 'attempts', 'blocks', 'levers', 'flat_match')})
    if repo_dir is not None and final:
        write_text_atomic(Path(repo_dir) / 'RESULT.md', text)
    print(f'VERDICT {v["label_tagged"]}', flush=True)
    return out
