"""PREREG 7 pilot rules (growth tasks only; never touches the seal). SPEC 5 E, 1.3, 13 I15, I18, I19.

Step 1 (smoke): FLAT_A and FLAT_B demo-pass task counts on the 50 pilot ids must each lie in the other's Clopper-Pearson
95% interval. Step 2 (PLANT): demo-pass tasks(PLANT1) - demo-pass tasks(FLAT_A) >= 1. Step 3 (rates): decode model
gen_rate = a - b x uncached_prefill_rate fitted on 30 s intervals of the pilot ledger, vLLM startup seconds, mean
generated tokens g, task-plus-instruction tokens P_task, uncached prompt tokens per request, and the discordance d (the
fraction of pilot tasks where FLAT_A and FLAT_B differ on pass@2 test-correct). Then project() every (S, R) with the
SPEC 1.3 unit model and choose_SR() the feasible pair with the largest S x R (ties to larger S).

Review fixes 2026-11-04: the projection adds sandbox execution seconds (measured per executed sample in the pilot jobs;
execution runs inside the same GPU jobs) and the knockout units (SPEC 1.3, |W| ASSUMED as config.KO_W_ASSUMED), and
counts FLAT's extra per seed as T_STOCK / m_F = 1 + R x rho (STOCK round 1 has an empty context). L stays the 6,000 cap,
marked ASSUMED (an upper bound) until growth measures it. With no discordance d the status is POWER_MISSING (the run
stops: PREREG 7.3 needs power before the sealed read), and with no cached-token field in the ledger it is RATES_MISSING
(the vLLM server needs --enable-prompt-tokens-details for the measured prefill rate).

Pilot v2 (RATCHET_V2_AMENDMENTS.md AMENDMENTS 1 to 3): FLAT_A under F3, then the screen FLAT_S (screen_decision: F3
stands iff >= 23 demo-pass tasks AND >= 22 pass@2 test-correct tasks; else the run falls back to INSTRUCTION_V1 at
4,096 and the gate arms re-run under pilot/V1_<arm>). Step 2 is now the PLANT_SOLVE gate (demo-pass tasks >= FLAT_A + 5);
the L_plant_1 (PLANT1) minus FLAT_A count is still computed and reported, not gating. Step 3 reads the rate arms FLAT_A,
FLAT_B, PLANT1 under the instruction in force (as v1), fits the decode model per job (a job boundary is not an idle
interval), and PILOT.md reports per arm the finish_reason=length share, median gen tokens, the share of samples with
`def transform`, and the library-to-FLAT token price ratio per sample.
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import math
import os
from pathlib import Path
from typing import Callable, Mapping

from .e_util import cfg, iter_jsonl, now_et, read_json, task_of_sample, write_json_atomic, write_text_atomic
from .stats import clopper_pearson, power_mc

PILOT_WHICH = tuple(cfg('PILOT_WHICH'))                 # logical gate arms: FLAT_A, FLAT_B, PLANT1, PLANT_SOLVE
PILOT_PHYSICAL = tuple(cfg('PILOT_PHYSICAL'))           # every pilot dir a v2 run can hold
RATE_ARMS = ('FLAT_A', 'FLAT_B', 'PLANT1')              # throughput, g, P_task and prompt rates (as v1)


# ---------------------------------------------------------------------------------------------------------------------
# readers

def _row_task(r: dict) -> str:
    return r.get('task') or task_of_sample(r.get('sample_id', ''))


def screen_record(run_dir: Path) -> dict | None:
    return read_json(Path(run_dir) / 'pilot' / 'SCREEN.json', None)


def physical(run_dir: Path, which: str) -> str:
    """Pilot dir of a logical gate arm: V1_<which> after a failed F3 screen, else <which>. Physical names (FLAT_S,
    V1_*) map to themselves."""
    sc = screen_record(run_dir) or {}
    if which in PILOT_WHICH and sc.get('decision') == 'V1':
        return str(cfg('PILOT_V1_PREFIX')) + which
    return which


def exec_rows(run_dir: Path, which: str) -> list[dict]:
    return list(iter_jsonl(Path(run_dir) / 'pilot' / physical(run_dir, which) / 'exec.jsonl'))


def sample_rows(run_dir: Path, which: str) -> list[dict]:
    return list(iter_jsonl(Path(run_dir) / 'pilot' / physical(run_dir, which) / 'samples.jsonl'))


def demo_pass_tasks(rows) -> frozenset[str]:
    return frozenset(_row_task(r) for r in rows if r.get('demo_pass'))


def pilot_tasks(run_dir: Path) -> list[str]:
    ts = set()
    for w in PILOT_PHYSICAL:
        for r in iter_jsonl(Path(run_dir) / 'pilot' / w / 'samples.jsonl'):
            ts.add(r.get('task') or task_of_sample(r.get('sample_id', '')))
    ts.discard('')
    return sorted(ts)


def ledger_rows(run_dir: Path, phase: str | None = 'pilot') -> list[dict]:
    """Ledger rows, dedup by request_id (last wins). Uses ledger.iter_rows (builder B) when present."""
    try:
        from .ledger import iter_rows
        rows = list(iter_rows(Path(run_dir)))
    except Exception:
        by: dict[str, dict] = {}
        for p in sorted(glob.glob(os.path.join(str(run_dir), 'ledger', 'ledger_*.jsonl'))):
            for r in iter_jsonl(p):
                by[r.get('request_id') or f'{p}:{len(by)}'] = r
        rows = list(by.values())
    return [r for r in rows if phase is None or r.get('phase') == phase]


def parse_ts(r: dict) -> float | None:
    if isinstance(r.get('ts'), (int, float)):
        return float(r['ts'])
    s = r.get('ts_et')
    if not s:
        return None
    try:
        return _dt.datetime.strptime(str(s)[:19], '%Y-%m-%d %H:%M:%S').timestamp()
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------------------------------
# step 1 and 2

def step1_smoke(run_dir: Path, n: int | None = None) -> dict:
    n = int(cfg('PILOT_N') if n is None else n)
    kA = len(demo_pass_tasks(exec_rows(run_dir, 'FLAT_A')))
    kB = len(demo_pass_tasks(exec_rows(run_dir, 'FLAT_B')))
    return smoke_rule(kA, kB, n)


def smoke_rule(kA: int, kB: int, n: int) -> dict:
    ciA = clopper_pearson(kA, n)
    ciB = clopper_pearson(kB, n)
    inA = ciA[0] <= kB / n <= ciA[1]
    inB = ciB[0] <= kA / n <= ciB[1]
    return {'kA': kA, 'kB': kB, 'n': n, 'cp95_A': list(ciA), 'cp95_B': list(ciB),
            'kB_in_cpA': inA, 'kA_in_cpB': inB, 'pass': bool(inA and inB)}


def step2_plant(run_dir: Path) -> dict:
    """L_plant_1 (PLANT1) minus FLAT_A demo-pass tasks. Pilot v2: computed and reported, no longer gating
    (AMENDMENT 3); 'pass' keeps the registered +1 reading for the report."""
    kP = len(demo_pass_tasks(exec_rows(run_dir, 'PLANT1')))
    kA = len(demo_pass_tasks(exec_rows(run_dir, 'FLAT_A')))
    gain = kP - kA
    return {'k_plant1': kP, 'k_flat_a': kA, 'gain': gain, 'min_gain': int(cfg('PILOT_PLANT_MIN_GAIN')),
            'pass': gain >= int(cfg('PILOT_PLANT_MIN_GAIN')), 'gates': False}


def step2_plant_solve(run_dir: Path) -> dict:
    """The pilot v2 gate of 7.2 (AMENDMENT 3): PLANT_SOLVE demo-pass tasks >= FLAT_A demo-pass tasks + 5."""
    rows = exec_rows(run_dir, 'PLANT_SOLVE')
    kS = len(demo_pass_tasks(rows))
    kA = len(demo_pass_tasks(exec_rows(run_dir, 'FLAT_A')))
    need = int(cfg('PILOT_PLANT_SOLVE_MIN_GAIN'))
    name = str(cfg('PLANT_SOLVE_NAME'))
    return {'k_plant_solve': kS, 'k_flat_a': kA, 'gain': kS - kA, 'min_gain': need, 'pass': kS - kA >= need,
            'gates': True, 'samples': len(rows),
            'samples_referencing_solver': sum(1 for r in rows if name in (r.get('static_refs') or [])),
            'samples_calling_solver_on_test': sum(1 for r in rows if (r.get('helper_calls') or {}).get(name))}


# ---------------------------------------------------------------------------------------------------------------------
# F3 screen (VERDICT_AMENDMENT_2 3.4, 3.5; AMENDMENT 1)

def demo_fit_share(rows) -> dict:
    """Demo-pass samples whose test output is wrong (v1: 13 of 299)."""
    dp = [r for r in rows if r.get('demo_pass')]
    wrong = sum(1 for r in dp if not r.get('test_correct'))
    return {'demo_pass_samples': len(dp), 'demo_pass_test_wrong': wrong, 'share': (wrong / len(dp)) if dp else None}


def screen_decision(run_dir: Path, correct_fn: Callable[[Path, str], Mapping[str, bool]] | None = None) -> dict:
    """F3 stands iff FLAT_S has >= 23 demo-pass tasks AND >= 22 pass@2 test-correct tasks; decision 'F3' or 'V1'."""
    run_dir = Path(run_dir)
    which = str(cfg('PILOT_SCREEN'))
    d = run_dir / 'pilot' / which
    st = read_json(d / 'round_state.json', {}) or {}
    if st.get('state') != 'DONE':
        raise RuntimeError('SCREEN_NOT_DONE pilot/%s state=%s' % (which, st.get('state')))
    rows = list(iter_jsonl(d / 'exec.jsonl'))
    samples = list(iter_jsonl(d / 'samples.jsonl'))
    k_demo = len(demo_pass_tasks(rows))
    p2 = (correct_fn or pass2_correct)(run_dir, which)
    k_p2 = sum(1 for v in p2.values() if v)
    need_d, need_p = int(cfg('SCREEN_MIN_DEMO_TASKS')), int(cfg('SCREEN_MIN_PASS2_TASKS'))
    stands = k_demo >= need_d and k_p2 >= need_p
    return {'decision': 'F3' if stands else 'V1', 'stands': stands, 'demo_pass_tasks': k_demo, 'pass2_tasks': k_p2,
            'min_demo_pass_tasks': need_d, 'min_pass2_tasks': need_p, 'n_tasks': len(p2),
            'S_screen': st.get('S_pilot'), 'screen': st.get('screen') or {}, 'samples': len(samples),
            'gen_tokens': sum(int(r.get('gen_tokens') or 0) for r in samples),
            'gen_tokens_budget': int(cfg('SCREEN_GEN_BUDGET')),
            'finish_length': sum(1 for r in samples if r.get('finish_reason') == 'length'),
            'demo_fit': demo_fit_share(rows)}


def arm_stats(run_dir: Path, which: str) -> dict:
    """Per pilot dir: samples, finish_reason=length share, median gen tokens, share with `def transform`, demo-pass
    and pass@2-relevant counts, and the demo-pass-but-test-wrong share."""
    d = Path(run_dir) / 'pilot' / which
    s = list(iter_jsonl(d / 'samples.jsonl'))
    e = list(iter_jsonl(d / 'exec.jsonl'))
    gens = sorted(int(r.get('gen_tokens') or 0) for r in s)
    n = len(s)
    med = None
    if gens:
        m = n // 2
        med = float(gens[m]) if n % 2 else (gens[m - 1] + gens[m]) / 2.0
    return {'which': which, 'samples': n, 'length_share': (sum(1 for r in s if r.get('finish_reason') == 'length') / n)
            if n else None, 'median_gen_tokens': med, 'mean_gen_tokens': (sum(gens) / n) if n else None,
            'def_transform_share': (sum(1 for r in s if 'def transform' in (r.get('text') or '')) / n) if n else None,
            'demo_pass_tasks': len(demo_pass_tasks(e)), 'demo_fit': demo_fit_share(e)}


# ---------------------------------------------------------------------------------------------------------------------
# step 3

def fit_rates(rows: list[dict], bucket_s: int | None = None) -> dict:
    """Least-squares gen_rate = a - b x uncached_prefill_rate over full 30 s intervals of the busy span.

    Each request is active over [end - latency_s, end]; its generated tokens are spread uniformly over that span and its
    uncached prompt tokens (prompt_tokens - cached_prompt_tokens) go to the interval holding its start. The first and
    last intervals are dropped (partial). If fewer than 3 intervals remain, or the fit gives b < 0 or a <= 0, the
    fallback is b = 0, a = total generated tokens / busy seconds (method 'mean')."""
    bucket = int(cfg('PILOT_RATE_INTERVAL_S') if bucket_s is None else bucket_s)
    by_job: dict[str, list] = {}
    for r in rows:
        end = parse_ts(r)
        if end is None:
            continue
        lat = float(r.get('latency_s') or 0.0)
        gen = float(r.get('gen_tokens') or 0)
        unc = float((r.get('prompt_tokens') or 0) - (r.get('cached_prompt_tokens') or 0))
        by_job.setdefault(str(r.get('job_id') or ''), []).append((end - max(lat, 1e-6), end, gen, max(unc, 0.0)))
    if not by_job:
        return {'a': None, 'b': None, 'method': 'none', 'intervals': 0, 'busy_s': 0.0}
    # Harness v2: one busy span per job (a pilot may span jobs; the gap between jobs is not an idle interval).
    xs, ys, busy, tot_gen = [], [], 0.0, 0.0
    for spans in by_job.values():
        t0 = min(s[0] for s in spans)
        t1 = max(s[1] for s in spans)
        busy_j = max(t1 - t0, 1e-6)
        nb = max(1, int(math.ceil(busy_j / bucket)))
        G = [0.0] * nb
        P = [0.0] * nb
        for s, e, gen, unc in spans:
            P[min(nb - 1, int((s - t0) // bucket))] += unc
            dur = e - s
            for i in range(int((s - t0) // bucket), min(nb - 1, int((e - t0) // bucket)) + 1):
                lo, hi = t0 + i * bucket, t0 + (i + 1) * bucket
                ov = max(0.0, min(hi, e) - max(lo, s))
                G[i] += gen * ov / dur
        xs += [p / bucket for p in P[1:-1]]
        ys += [g / bucket for g in G[1:-1]]
        busy += busy_j
        tot_gen += sum(s[2] for s in spans)
    res = {'intervals': len(xs), 'busy_s': busy, 'gen_tokens': tot_gen, 'bucket_s': bucket, 'jobs': len(by_job)}
    if len(xs) >= 3:
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        if sxx > 0:
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
            a = my - slope * mx
            b = -slope
            if b >= 0 and a > 0:
                res.update({'a': a, 'b': b, 'method': 'ols'})
                return res
    res.update({'a': tot_gen / busy, 'b': 0.0, 'method': 'mean'})
    return res


def startup_seconds(run_dir: Path) -> float | None:
    vals = []
    for p in sorted(glob.glob(os.path.join(str(run_dir), 'jobs', '*', 'STATUS.json'))):
        st = read_json(p, {}) or {}
        if 'phase=pilot' not in str(st.get('meta', '')):
            continue
        v = (st.get('seconds') or {}).get('vllm_startup')
        if v:
            vals.append(float(v))
    return (sum(vals) / len(vals)) if vals else None


def exec_seconds_per_sample(run_dir: Path) -> dict:
    """Wall seconds of sandbox execution per executed sample, from the pilot jobs' STATUS.json (seconds.exec_only over
    exec.runs: measured with the job's own worker pool). Fallback: the pilot exec rows' summed per-input wall_s divided
    by EXEC_WORKERS."""
    ex_s = runs = 0.0
    for p in sorted(glob.glob(os.path.join(str(run_dir), 'jobs', '*', 'STATUS.json'))):
        st = read_json(p, {}) or {}
        if 'phase=pilot' not in str(st.get('meta', '')):
            continue
        ex_s += float((st.get('seconds') or {}).get('exec_only') or 0)
        runs += float((st.get('exec') or {}).get('runs') or 0)
    if runs > 0:
        return {'s_per_sample': ex_s / runs, 'source': 'job_status', 'runs': int(runs), 'exec_s': ex_s}
    tot = n = 0
    for w in PILOT_PHYSICAL:
        for r in iter_jsonl(Path(run_dir) / 'pilot' / w / 'exec.jsonl'):
            tot += sum(float(x) for x in (r.get('wall_s') or []))
            n += 1
    workers = max(1, int(cfg('EXEC_WORKERS')))
    if n:
        return {'s_per_sample': tot / n / workers, 'source': 'exec_rows_wall_over_workers', 'runs': n,
                'workers': workers}
    return {'s_per_sample': None, 'source': 'none', 'runs': 0}


def _mean(xs):
    xs = list(xs)
    return (sum(xs) / len(xs)) if xs else None


def pass2_correct(run_dir: Path, which: str) -> dict[str, bool]:
    """Per pilot task: is the pass@2 submission (select.pass2 over this pilot arm's exec rows) test-correct on the
    public growth outputs? Uses builder A's select, types and arc_io."""
    from .select import pass2, candidate_from_exec
    from .types import ExecResult
    from . import arc_io
    d = Path(run_dir) / 'pilot' / physical(run_dir, which)
    code_len = {r['sample_id']: len(r.get('code') or '') for r in iter_jsonl(d / 'samples.jsonl')}
    by: dict[str, list] = {}
    for r in iter_jsonl(d / 'exec.jsonl'):
        er = ExecResult.from_row(r)
        by.setdefault(_row_task(r), []).append(candidate_from_exec(er, code_len.get(er.sample_id, 0)))
    out = {}
    for t in pilot_tasks(run_dir):
        sub = pass2(t, by.get(t, []))
        task = arc_io.load_task(t, 'pilot')
        out[t] = any(tuple(a.outputs) == tuple(task.test_outputs) for a in sub.attempts)
    return out


def discordance(ca: Mapping[str, bool], cb: Mapping[str, bool], tasks=None) -> dict:
    tasks = sorted(tasks if tasks is not None else set(ca) | set(cb))
    dis = [t for t in tasks if bool(ca.get(t)) != bool(cb.get(t))]
    n = len(tasks)
    return {'n': n, 'discordant': len(dis), 'd': (len(dis) / n) if n else None,
            'correct_a': sum(bool(ca.get(t)) for t in tasks), 'correct_b': sum(bool(cb.get(t)) for t in tasks)}


def step3_rates(run_dir: Path, correct_fn: Callable[[Path, str], Mapping[str, bool]] | None = None) -> dict:
    rate_arms = {physical(run_dir, a) for a in RATE_ARMS}
    rows = [r for r in ledger_rows(run_dir, 'pilot') if r.get('arm') is None or r.get('arm') in rate_arms]
    fit = fit_rates(rows)
    flat = [r for r in rows if not (r.get('library_tokens') or 0) and not (r.get('exemplar_tokens') or 0)]
    lib = [r for r in rows if (r.get('library_tokens') or 0)]
    n_samples = sum(int(r.get('n') or 1) for r in rows)
    g = (sum(float(r.get('gen_tokens') or 0) for r in rows) / n_samples) if n_samples else None
    p_task = _mean(float((r.get('task_tokens') or 0) + (r.get('instruction_tokens') or 0)) for r in flat or rows)
    u_flat = _mean(float((r.get('prompt_tokens') or 0) - (r.get('cached_prompt_tokens') or 0)) for r in flat)
    u_lib = _mean(float((r.get('prompt_tokens') or 0) - (r.get('cached_prompt_tokens') or 0)) for r in lib)
    lib_tok = _mean(float(r.get('library_tokens') or 0) for r in lib)
    trunc = sum(sum(1 for f in (r.get('finish_reasons') or []) if f == 'length') for r in rows)
    cached_known = sum(1 for r in rows if r.get('cached_prompt_tokens') is not None)
    cached = sum(float(r.get('cached_prompt_tokens') or 0) for r in rows)
    prompt = sum(float(r.get('prompt_tokens') or 0) for r in rows)
    fn = correct_fn or pass2_correct
    try:
        dd = discordance(fn(run_dir, 'FLAT_A'), fn(run_dir, 'FLAT_B'), pilot_tasks(run_dir) or None)
    except Exception as e:  # report, never guess d
        dd = {'n': 0, 'discordant': None, 'd': None, 'error': f'{type(e).__name__}: {e}'}
    st = startup_seconds(run_dir)
    ex = exec_seconds_per_sample(run_dir)

    def per_sample(rs):
        v = [float(r.get('prompt_tokens') or 0) + float(r.get('gen_tokens') or 0) / max(1, int(r.get('n') or 1))
             for r in rs]
        return _mean(v)
    ps_flat, ps_lib = per_sample(flat), per_sample(lib)
    L = float(cfg('LIBRARY_CAP_TOKENS'))
    price = {'flat_logical_per_sample': ps_flat, 'library_logical_per_sample': ps_lib,
             'measured_ratio': (ps_lib / ps_flat) if (ps_flat and ps_lib) else None,
             'cap_ratio': ((p_task + L + g) / (p_task + g)) if (p_task is not None and g is not None) else None}
    return {'price': price, 'rate_arms': sorted(rate_arms), 'a': fit.get('a'), 'b': fit.get('b'), 'fit': fit, 'startup_s': st, 'cached_known_rows': cached_known,
            'exec_s_per_sample': ex.get('s_per_sample'), 'exec': ex,
            'startup_measured': st is not None, 'g': g, 'P_task': p_task, 'u_flat_req': u_flat, 'u_lib_req': u_lib,
            'library_tokens_plant1': lib_tok, 'L': int(cfg('LIBRARY_CAP_TOKENS')), 'requests': len(rows),
            'samples': n_samples, 'truncated_samples': trunc,
            'prefix_cache_share': (cached / prompt) if prompt else None, **{k: dd[k] for k in ('d',)},
            'discordance': dd}


# ---------------------------------------------------------------------------------------------------------------------
# projection and the S/R rule

def units(R: int, rho: float) -> dict:
    """SPEC 1.3 sample units (one unit = 400 x S samples). Library-context and flat-context units split out."""
    n_seeds = len(tuple(cfg('SEALED_SEEDS')))
    n_lib_arms = len(tuple(cfg('LIBRARY_ARMS')))
    n_pert = len(tuple(cfg('PERTURBED_ARMS')))
    growth = 4 * R - 3                              # STOCK R + STATIC R-1 + ONESHOT R + EXEMPLAR R - shared 3
    growth_flat = 1                                 # shared round 1 has an empty context
    # FLAT extra per seed = T_STOCK / m_F: STOCK round 1 (empty context, 1 unit of m_F) + rounds 2..R and the sealed
    # pass (R units of m_S = rho m_F). Review fix 2026-11-04: was (R + 1) x rho, which charged round 1 at m_S.
    extra = 1 + R * rho
    sealed_lib = n_lib_arms * n_seeds
    sealed_flat = n_seeds + n_seeds * extra
    pert_lib = (n_pert - 1) * n_seeds
    pert_flat = n_seeds + n_seeds * extra
    knockout = 2 * n_seeds * float(cfg('KO_W_ASSUMED')) / float(cfg('N_SEALED'))   # SPEC 1.3, library context
    total = growth + sealed_lib + sealed_flat + pert_lib + pert_flat + knockout
    flat_units = growth_flat + sealed_flat + pert_flat
    return {'growth': growth, 'sealed': sealed_lib + sealed_flat, 'perturbed': pert_lib + pert_flat,
            'flat_extra': 2 * n_seeds * extra, 'knockout': knockout, 'total': total, 'flat_context': flat_units,
            'library_context': total - flat_units}


def project(rates: dict, S: int, R: int) -> dict:
    """Samples, tokens and H100 job-hours for (S, R) with measured rates (SPEC 1.3 to 1.5 with measured values).

    m_F = P_task + g, m_S = P_task + L + g (logical tokens per sample), rho = m_S / m_F.
    decode seconds = (generated + b x uncached prefill) / a; uncached prefill per sample = measured uncached prompt
    tokens per request / S (one request per task carries its S samples). Jobs = ceil(decode s / (STOP_ISSUE_S -
    startup s)); each job is one H100-hour."""
    g = float(rates['g'])
    p_task = float(rates['P_task'])
    L = float(rates.get('L') or cfg('LIBRARY_CAP_TOKENS'))
    a = float(rates['a'])
    b = float(rates.get('b') or 0.0)
    startup = float(rates['startup_s'] if rates.get('startup_s') is not None else 0.0)
    m_F = p_task + g
    m_S = p_task + L + g
    rho = m_S / m_F
    U = units(R, rho)
    per_unit = int(cfg('N_SEALED')) * S
    samples = U['total'] * per_unit
    gen = samples * g
    u_flat = float(rates.get('u_flat_req') if rates.get('u_flat_req') is not None else p_task)
    u_lib = float(rates.get('u_lib_req') if rates.get('u_lib_req') is not None else p_task)
    prefill = (U['flat_context'] * u_flat + U['library_context'] * u_lib) * per_unit / S
    logical = (U['flat_context'] * m_F + U['library_context'] * m_S) * per_unit
    decode_s = (gen + b * prefill) / a
    ex_per = rates.get('exec_s_per_sample')
    exec_s = samples * float(ex_per) if ex_per is not None else 0.0     # execution runs inside the same GPU jobs
    usable = float(cfg('STOP_ISSUE_S')) - startup
    jobs = int(math.ceil((decode_s + exec_s) / usable)) if usable > 0 else 10 ** 9
    return {'S': S, 'R': R, 'rho': rho, 'm_F': m_F, 'm_S': m_S, 'L': L, 'L_assumed': True, 'units': U,
            'samples': samples, 'gen_tokens': gen, 'exec_s': exec_s, 'exec_measured': ex_per is not None,
            'uncached_prefill_tokens': prefill, 'logical_tokens': logical, 'decode_s': decode_s,
            'usable_s_per_job': usable, 'jobs': jobs, 'h100_hours': jobs,
            'required_tok_s_12h': gen / (float(cfg('H100_HOURS_BUDGET')) * 3600.0),
            'feasible': jobs <= float(cfg('H100_HOURS_BUDGET'))}


def choose_SR(rates: dict, power_sims: int | None = None) -> dict:
    if any(rates.get(k) is None for k in ('a', 'g', 'P_task')):
        return {'status': 'RATES_MISSING', 'S': None, 'R': None, 'grid': [], 'n_feasible': 0, 'power': None,
                'underpowered': None, 'missing': [k for k in ('a', 'g', 'P_task') if rates.get(k) is None]}
    grid = [project(rates, S, R) for S in cfg('S_GRID') for R in cfg('R_GRID')]
    feas = [p for p in grid if p['feasible']]
    out = {'grid': grid, 'n_feasible': len(feas)}
    d = rates.get('d')
    if d is not None:
        pw = power_mc(float(d), sims=power_sims)
        out['power'] = pw
        out['power_all5_independent'] = pw ** len(tuple(cfg('COMPARATORS')))
        out['underpowered'] = pw < float(cfg('POWER_MIN'))
    else:
        out['power'] = None
        out['underpowered'] = None
    if not feas:
        out.update({'status': 'PILOT_NO_FEASIBLE_SR', 'S': None, 'R': None})
        return out
    best = max(feas, key=lambda p: (p['S'] * p['R'], p['S']))
    if out['power'] is None:
        # PREREG 7.3: power (and an UNDERPOWERED tag) must exist before the sealed read; without d the run stops here
        out.update({'status': 'POWER_MISSING', 'S': None, 'R': None, 'would_choose': {'S': best['S'], 'R': best['R']},
                    'power_error': (rates.get('discordance') or {}).get('error')})
        return out
    out.update({'status': 'OK', 'S': best['S'], 'R': best['R'], 'chosen': best})
    return out


# ---------------------------------------------------------------------------------------------------------------------
# report

def run_pilot_rules(run_dir: Path, correct_fn=None, power_sims: int | None = None) -> dict:
    s1 = step1_smoke(run_dir)
    s2 = step2_plant_solve(run_dir)          # pilot v2: the PLANT_SOLVE gate (AMENDMENT 3)
    s2_plant1 = step2_plant(run_dir)         # registered L_plant_1 check: report-only
    rates = step3_rates(run_dir, correct_fn)
    screen = screen_record(run_dir)
    arms = {w: arm_stats(run_dir, w) for w in PILOT_PHYSICAL if (Path(run_dir) / 'pilot' / w).is_dir()}
    status = 'OK'
    choice = None
    if not s1['pass']:
        status = 'SMOKE_FAIL'
    elif not s2['pass']:
        status = 'PLANT_FAIL'
    if rates.get('a') is None or rates.get('g') is None or rates.get('P_task') is None \
            or not rates.get('cached_known_rows'):
        status = status if status != 'OK' else 'RATES_MISSING'
    elif status == 'OK':
        choice = choose_SR(rates, power_sims)
        status = choice['status']
    return {'schema': 'ratchet.pilot.v2', 'created_et': now_et(), 'status': status, 'smoke': s1, 'plant': s2,
            'plant1': s2_plant1, 'screen': screen, 'arms': arms,
            'gate_dirs': {w: physical(run_dir, w) for w in PILOT_WHICH},
            'rates': rates, 'choice': choice,
            'S': choice.get('S') if choice else None, 'R': choice.get('R') if choice else None,
            'underpowered': choice.get('underpowered') if choice else None}


def _fmt(x, nd=3):
    if x is None:
        return 'n/a'
    if isinstance(x, float):
        return f'{x:,.{nd}f}'
    if isinstance(x, int):
        return f'{x:,}'
    return str(x)


def render_pilot_md(res: dict) -> str:
    s1, s2, r, c = res['smoke'], res['plant'], res['rates'], res['choice']
    L = ['# PILOT (PREREG 7)', '', f'Written {res["created_et"]}. Growth tasks only; no sealed read.', '',
         f'Status: **{res["status"]}**', '',
         '## 7.1 Determinism smoke', '',
         f'FLAT_A demo-pass tasks {s1["kA"]} of {s1["n"]}, CP95 [{s1["cp95_A"][0]:.4f}, {s1["cp95_A"][1]:.4f}]; '
         f'FLAT_B {s1["kB"]} of {s1["n"]}, CP95 [{s1["cp95_B"][0]:.4f}, {s1["cp95_B"][1]:.4f}]. '
         f'Pass: {s1["pass"]}.', '',
         '## 7.2 PLANT checks (as amended: AMENDMENT 3)', '']
    if 'k_plant_solve' in s2:
        L += [f'Gate, PLANT_SOLVE: demo-pass tasks {s2["k_plant_solve"]}, FLAT_A {s2["k_flat_a"]}, gain {s2["gain"]} '
              f'(needs >= {s2["min_gain"]}). Pass: {s2["pass"]}. Samples referencing solve_this '
              f'{s2.get("samples_referencing_solver")} of {s2.get("samples")}; calling it on a test input '
              f'{s2.get("samples_calling_solver_on_test")}.', '']
    p1 = res.get('plant1') or (s2 if 'k_plant1' in s2 else None)
    if p1:
        L += [f'Report only, L_plant_1 (PLANT1): demo-pass tasks {p1["k_plant1"]}, FLAT_A {p1["k_flat_a"]}, gain '
              f'{p1["gain"]} (the registered +{p1["min_gain"]} rule reads {p1["pass"]}; it no longer gates).', '']
    sc = res.get('screen')
    if sc:
        df = sc.get('demo_fit') or {}
        L += ['## F3 screen (AMENDMENT 1)', '',
              f'FLAT_S at S_screen = {sc.get("S_screen")} (g of the F3 FLAT_A = {_fmt((sc.get("screen") or {}).get("g_flat_a"), 1)}; '
              f'{_fmt(sc.get("gen_tokens"))} generated tokens against the {_fmt(sc.get("gen_tokens_budget"))} budget): '
              f'demo-pass tasks {sc.get("demo_pass_tasks")} (needs >= {sc.get("min_demo_pass_tasks")}), pass@2 '
              f'test-correct tasks {sc.get("pass2_tasks")} (needs >= {sc.get("min_pass2_tasks")}). Demo-pass but '
              f'test-wrong samples: {df.get("demo_pass_test_wrong")} of {df.get("demo_pass_samples")} (v1: 13 of 299). '
              f'Decision: **{sc.get("decision")}**' + (' (F3 stands).' if sc.get('decision') == 'F3' else
                                                        ' (fallback: INSTRUCTION_V1 at max_tokens 4,096; the F3 '
                                                        'FLAT_A stays on disk, reported below, not used for gates).'),
              '']
    arms = res.get('arms') or {}
    if arms:
        gd = res.get('gate_dirs') or {}
        L += ['## Per pilot dir', '', f'Gate dirs: {", ".join("%s=%s" % kv for kv in sorted(gd.items()))}.', '',
              '| dir | samples | finish=length share | median gen tokens | mean gen tokens | share with `def transform` '
              '| demo-pass tasks | demo-pass test-wrong |', '|---|---|---|---|---|---|---|---|']
        for w, a in arms.items():
            df = a.get('demo_fit') or {}
            L.append(f'| {w} | {a["samples"]} | {_fmt(a.get("length_share"), 4)} | {_fmt(a.get("median_gen_tokens"), 1)} '
                     f'| {_fmt(a.get("mean_gen_tokens"), 1)} | {_fmt(a.get("def_transform_share"), 4)} | '
                     f'{a.get("demo_pass_tasks")} | {df.get("demo_pass_test_wrong")} of {df.get("demo_pass_samples")} |')
        L.append('')
    pr = r.get('price') or {}
    L += ['## 7.3 Throughput and discordance', '',
          f'- library-to-FLAT token price per sample: measured {_fmt(pr.get("measured_ratio"), 3)} (PLANT1 '
          f'{_fmt(pr.get("library_logical_per_sample"), 1)} vs FLAT {_fmt(pr.get("flat_logical_per_sample"), 1)} '
          f'logical tokens per sample); at the 6,000 cap {_fmt(pr.get("cap_ratio"), 3)} (v1: 2.26)',
         f'- decode fit: a = {_fmt(r.get("a"))} gen tok/s, b = {_fmt(r.get("b"), 5)} '
         f'(method {r["fit"].get("method")}, {r["fit"].get("intervals")} intervals of {r["fit"].get("bucket_s")} s, '
         f'busy {_fmt(r["fit"].get("busy_s"), 1)} s)',
         f'- vLLM startup s: {_fmt(r.get("startup_s"), 1)} (measured: {r.get("startup_measured")})',
         f'- requests {r["requests"]}, samples {r["samples"]}, truncated samples {r["truncated_samples"]}',
         f'- g = {_fmt(r.get("g"), 1)} gen tokens per sample; P_task = {_fmt(r.get("P_task"), 1)}; '
         f'uncached prompt per request flat {_fmt(r.get("u_flat_req"), 1)}, library {_fmt(r.get("u_lib_req"), 1)}; '
         f'PLANT1 library tokens {_fmt(r.get("library_tokens_plant1"), 1)}; projection uses L = {r["L"]} '
         '(ASSUMED: the cap, an upper bound, until growth measures L_r)',
         f'- ledger rows with a cached-token count: {r.get("cached_known_rows")} of {r["requests"]} '
         '(0 = server ran without --enable-prompt-tokens-details: RATES_MISSING)',
         f'- sandbox execution: {_fmt(r.get("exec_s_per_sample"), 5)} wall s per executed sample '
         f'(source {(r.get("exec") or {}).get("source")}); knockout units use |W| = {cfg("KO_W_ASSUMED")} (ASSUMED)',
         f'- prefix cache share of prompt tokens: {_fmt(r.get("prefix_cache_share"), 4)}',
         f'- d = {_fmt(r.get("d"), 4)} ({r["discordance"].get("discordant")} of {r["discordance"].get("n")} pilot '
         f'tasks differ on pass@2 test-correct between FLAT_A and FLAT_B)', '']
    if c:
        L += ['| S | R | units | samples | gen tokens | decode s | exec s | jobs (H100-h) | feasible |',
              '|---|---|---|---|---|---|---|---|---|']
        for p in c['grid']:
            L.append(f'| {p["S"]} | {p["R"]} | {p["units"]["total"]:.1f} | {p["samples"]:,.0f} | '
                     f'{p["gen_tokens"]:,.0f} | {p["decode_s"]:,.0f} | {p.get("exec_s", 0):,.0f} | {p["jobs"]} | '
                     f'{p["feasible"]} |')
        L += ['', f'Choice: S = {c["S"]}, R = {c["R"]} ({c["status"]}).',
              f'Projected power for a net gain of +{cfg("POWER_GAIN")} of {cfg("N_SEALED")} at d = {_fmt(r.get("d"), 4)}: '
              f'{_fmt(c.get("power"), 4)} (all five comparators under independence: '
              f'{_fmt(c.get("power_all5_independent"), 4)}, reported, not decisive).']
        if c.get('underpowered'):
            L += ['', f'**UNDERPOWERED**: projected power is below {cfg("POWER_MIN")}. RESULT.md will carry this tag '
                      'whatever it reads (PREREG 7.3), stated here before any sealed read.']
        if c['status'] == 'POWER_MISSING':
            L += ['', '**POWER_MISSING**: the discordance d could not be computed, so projected power is unknown. PREREG '
                      '7.3 requires it before the sealed read; the run stops until the lead amends.']
        if c['status'] == 'PILOT_NO_FEASIBLE_SR':
            L += ['', '**PILOT_NO_FEASIBLE_SR**: no (S, R) fits the budget. PREREG 7.3 registers no outcome for this; '
                      'the run stops until the lead amends.']
    return '\n'.join(L) + '\n'


def write_pilot_report(run_dir: Path, correct_fn=None, power_sims: int | None = None) -> Path:
    run_dir = Path(run_dir)
    res = run_pilot_rules(run_dir, correct_fn, power_sims)
    write_json_atomic(run_dir / 'PILOT.json', res)
    p = write_text_atomic(run_dir / 'PILOT.md', render_pilot_md(res))
    print(f'PILOT status={res["status"]} S={res["S"]} R={res["R"]} underpowered={res["underpowered"]}', flush=True)
    return p


def apply_choice(run_dir: Path) -> dict:
    """Copy PILOT.json's S and R into RUN.json (keys S, R only). Refuses to change an S or R already set."""
    run_dir = Path(run_dir)
    pil = read_json(run_dir / 'PILOT.json', {}) or {}
    if pil.get('status') != 'OK':
        raise RuntimeError(f'PILOT_NOT_OK status={pil.get("status")}')
    run = read_json(run_dir / 'RUN.json', {}) or {}
    for k in ('S', 'R'):
        if run.get(k) not in (None, pil[k]):
            raise RuntimeError(f'RUN_{k}_ALREADY_SET {run.get(k)} != {pil[k]}')
        run[k] = pil[k]
    run['pilot_underpowered'] = pil.get('underpowered')
    write_json_atomic(run_dir / 'RUN.json', run)
    return run
