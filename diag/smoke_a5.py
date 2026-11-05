"""Amendment 5 candidate smoke (silicyte-0119, run v3 candidate; diagnostic only, registers nothing).

Question: does an assistant prefill of "```python\\n" (P1), plus one instruction sentence asking for top-level helper
functions (P2), cut the finish=length share and raise the number of demo-passing programs with reusable top-level helpers,
against V1 exactly as growth sends it (P0)? Same server, same 50 pilot ids, S = 4, the registered sampling
(temperature 0.8, top_p 0.95, max_tokens 4096, enable_thinking 0), the same fixed seed per task in every variant.

Everything is measured the way growth measures it, through the ratchet modules (none of them is modified):
  prompt.build_messages (V1 text from config) -> llm.VLLMClient (subclassed only to add the prefill message and the two
  vLLM flags) -> extract.extract_code on (rendered prefill + completion) -> sandbox.run_batch on demos and the test input
  -> test_correct as arms.execute -> select.pass2 as pilot.pass2_correct -> helpers.build_solution with an empty library
  -> helpers.accept(dedup_solutions(...), library.empty(...), tok).

Modes:
  serve    inside slurm/smoke_a5.sbatch: needs RATCHET_VLLM_URL; runs P0, P1, P2 one after another; writes
           <out>/SMOKE_A5.json, <out>/SMOKE_A5.md and per-variant samples/exec rows under <out>/smoke_a5/.
  control  CPU positive control on the login node: re-measures existing run v2 rows (read-only) through the same
           measuring code: pilot/V1_FLAT_A (want demo-pass tasks 22, finish=length 0.7750) and arms/STOCK/round_1 (want
           165 demo-pass tasks and 0 accepted helpers). Writes <out>/SMOKE_A5_CONTROL.json.
  dryrun   no server: builds all 600 sample ids and 150 requests, runs every refusal check, renders the P1 and P2 prompt
           tails offline with the model's chat template (transformers.apply_chat_template, the path vLLM uses), and runs
           the full serve path on 5 tasks against llm.StubLLM fed with V1_FLAT_A texts. Writes <out>/smoke_a5_dryrun/.

Safety: the pilot ids come from arc_io.pilot_ids (growth list sha-checked) and must equal the task set of the run's
pilot/V1_FLAT_A rows; the script refuses if any id is in arc_io.sealed_id_list() (the sha-checked repo id list, not the
sealed data dir). Only the 'pilot' / 'growth' splits are loaded. guard.install_audit_hook() is installed first. The output
directory must lie outside runs/. Nothing under runs/v2 is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

CODE = Path(os.environ.get('RATCHET_CODE', Path(__file__).resolve().parent.parent))
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from ratchet import guard   # noqa: E402

guard.install_audit_hook()

from ratchet import arc_io, config, extract, helpers, library, llm, prompt, sandbox, select, tok as tokmod  # noqa: E402
from ratchet.arms import seed_for   # noqa: E402
from ratchet.types import ExecResult   # noqa: E402

RUN_V2 = config.REAL_RUNS_DIR / 'v2'
DEFAULT_OUT = config.REAL_SILO_ROOT / 'diag'
PREFILL = '```python\n'
HELPER_SENTENCE = ('Put each reusable step (for example finding objects, cropping, rotating, recolouring, counting) in its '
                   'own top-level function with a descriptive name, and keep transform short by calling those functions.')
INSTR_V1 = config.INSTRUCTION_V1
INSTR_P2 = INSTR_V1 + ' ' + HELPER_SENTENCE
VARIANTS = {
    'P0': {'instruction': INSTR_V1, 'prefill': None, 'what': 'V1 exactly as growth sends it (control)'},
    'P1': {'instruction': INSTR_V1, 'prefill': PREFILL, 'what': 'V1 + assistant prefill "```python\\n"'},
    'P2': {'instruction': INSTR_P2, 'prefill': PREFILL, 'what': 'V1 + helper sentence + prefill'},
}
S = 4
N_TASKS = 50
SEED_PHASE = 'smoke_a5'
THINK_OFF_HEADER = '<|im_start|>assistant\n<think>\n\n</think>\n\n'


def now_et() -> str:
    return llm.now_et()


def sha256_text(t: str) -> str:
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


def log(*a) -> None:
    print('[%s ET]' % now_et(), *a, flush=True)


# ---------------------------------------------------------------------------------------------------------------------
# ids and refusals

def check_out_dir(out: Path) -> Path:
    out = Path(os.path.realpath(out))
    runs = os.path.realpath(config.REAL_RUNS_DIR)
    if str(out) == runs or str(out).startswith(runs + os.sep):
        raise SystemExit('OUT_DIR_REFUSED %s is under runs/ (write only under %s)' % (out, DEFAULT_OUT))
    if guard.is_protected(out):
        raise SystemExit('OUT_DIR_REFUSED %s is under a protected root' % out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'smoke_a5').mkdir(exist_ok=True)     # sbatch -o target
    return out


def v2_pilot_tasks(which: str = 'V1_FLAT_A') -> list[str]:
    p = RUN_V2 / 'pilot' / which / 'samples.jsonl'
    return sorted({json.loads(ln)['task'] for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip()})


def smoke_ids() -> list[str]:
    ids = sorted(arc_io.pilot_ids(N_TASKS))
    if len(ids) != N_TASKS:
        raise SystemExit('PILOT_IDS_COUNT %d != %d' % (len(ids), N_TASKS))
    v2 = v2_pilot_tasks()
    if ids != v2:
        raise SystemExit('PILOT_IDS_MISMATCH arc_io.pilot_ids differs from runs/v2/pilot/V1_FLAT_A tasks: %s'
                         % sorted(set(ids) ^ set(v2))[:5])
    sealed = set(arc_io.sealed_id_list())     # sha-checked repo list (splits/), never the sealed data dir
    growth = set(arc_io.growth_id_list())
    bad = sorted(set(ids) & sealed)
    if bad:
        raise SystemExit('SEALED_ID_REFUSED %s' % bad)
    if not set(ids) <= growth:
        raise SystemExit('NOT_GROWTH_REFUSED %s' % sorted(set(ids) - growth)[:5])
    log('IDS n=%d sealed_overlap=0 subset_of_growth=1 equal_to_v2_pilot=1 sha=%s'
        % (len(ids), arc_io.id_list_sha256(ids)))
    return ids


def load_tasks(ids, split='pilot') -> dict:
    if split not in ('pilot', 'growth'):
        raise SystemExit('SPLIT_REFUSED %s' % split)
    return {i: arc_io.load_task(i, split) for i in ids}


def check_model_files() -> dict:
    """Size and mtime of every model file against runs/v2/RUN.json (read-only), as `ratchet modelcheck` does for a job."""
    run = json.loads((RUN_V2 / 'RUN.json').read_text(encoding='utf-8'))
    rec = run.get('model_files_sha256') or {}
    model = Path(run.get('model') or config.MODEL_DIR)
    bad = []
    for name, v in sorted(rec.items()):
        st = os.stat(model / name)
        if st.st_size != int(v['size']) or st.st_mtime_ns != int(v['mtime_ns']):
            bad.append(name)
    if bad:
        raise SystemExit('MODEL_FILES_CHANGED %s' % bad[:5])
    return {'model': str(model), 'files': len(rec), 'size_mtime_match': True}


def v2_ledger_v1_flat_a() -> dict:
    """task -> V1_FLAT_A pilot ledger row of run v2 (read-only; ledger.iter_rows never writes)."""
    from ratchet.ledger import iter_rows
    return {r['task']: r for r in iter_rows(RUN_V2) if r.get('phase') == 'pilot' and r.get('arm') == 'V1_FLAT_A'}


def seed_base() -> int:
    run = json.loads((RUN_V2 / 'RUN.json').read_text(encoding='utf-8'))
    return int(run.get('seed_base', config.SEED_BASE))


# ---------------------------------------------------------------------------------------------------------------------
# client

class PrefillMixin:
    """Adds the assistant prefill as the final message with continue_final_message / add_generation_prompt false."""

    def build_body(self, req):
        b = super().build_body(req)
        pre = (req.meta or {}).get('prefill')
        if pre:
            b['messages'] = list(b['messages']) + [{'role': 'assistant', 'content': pre}]
            b['continue_final_message'] = True
            b['add_generation_prompt'] = False
        return b


class PrefillClient(PrefillMixin, llm.VLLMClient):
    pass


class PrefillStub(PrefillMixin, llm.StubLLM):
    pass


def build_requests(tasks: dict, tk, variant: str, sbase: int) -> tuple[list, dict]:
    v = VARIANTS[variant]
    reqs, info = [], {}
    for tid in sorted(tasks):
        pb = prompt.build_messages(tasks[tid], tk, instruction=v['instruction'])
        seed = seed_for(SimpleNamespace(seed_base=sbase), SEED_PHASE, 1, tid, 0, None)   # same seed in every variant
        rid = '%s|growth|r1|%s|b0' % (variant, tid)
        sids = ['%s|growth|r1|%s|s%d' % (variant, tid, i) for i in range(S)]
        reqs.append(llm.GenRequest(request_id=rid, messages=pb.messages, n=S, seed=seed,
                                   meta={'arm': variant, 'phase': 'growth', 'round': 1, 'task': tid,
                                         'prefill': v['prefill'], 'task_tokens': pb.task_tokens,
                                         'instruction_tokens': pb.instruction_tokens}))
        info[rid] = {'task': tid, 'sample_ids': sids, 'seed': seed, 'user_sha': sha256_text(pb.messages[-1]['content'])}
    return reqs, info


# ---------------------------------------------------------------------------------------------------------------------
# rendering check

def render_offline(messages_with_prefill: list) -> dict:
    """The model's chat template through transformers.apply_chat_template with continue_final_message (vLLM's path)."""
    from transformers import AutoTokenizer
    t = AutoTokenizer.from_pretrained(str(config.MODEL_DIR))
    s = t.apply_chat_template(messages_with_prefill, tokenize=False, add_generation_prompt=False,
                              continue_final_message=True, enable_thinking=False)
    g = t.apply_chat_template(messages_with_prefill[:-1], tokenize=False, add_generation_prompt=True,
                              enable_thinking=False)
    return {'tail': s[-220:], 'gen_prompt_tail': g[-160:], 'prefix_equals_gen_prompt': s.startswith(g),
            'after_gen_prompt': s[len(g):] if s.startswith(g) else None}


def render_server(base_url: str, model: str, messages_with_prefill: list, tk) -> dict:
    """POST /tokenize with the same flags as the chat request; decode the ids locally with the model tokenizer."""
    import http.client
    from urllib.parse import urlsplit
    u = urlsplit(base_url)
    body = {'model': model, 'messages': messages_with_prefill, 'add_generation_prompt': False,
            'continue_final_message': True, 'chat_template_kwargs': {'enable_thinking': False},
            'add_special_tokens': False}
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=60)
    try:
        conn.request('POST', '/tokenize', body=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        r = conn.getresponse()
        raw = r.read()
    finally:
        conn.close()
    if r.status != 200:
        return {'error': 'HTTP %d %r' % (r.status, raw[:300])}
    ids = json.loads(raw)['tokens']
    text = tk._tk.decode(ids, skip_special_tokens=False)
    return {'n_tokens': len(ids), 'tail': text[-220:], 'last_ids': ids[-8:]}


def effective_prefill(rendered_tail: str | None) -> str:
    """What the model actually sees after the think-off header (the template trims message content, so the prefill's
    trailing newline may be dropped). The program text re-attaches exactly this."""
    if rendered_tail and THINK_OFF_HEADER in rendered_tail:
        return rendered_tail.rsplit(THINK_OFF_HEADER, 1)[1]
    return PREFILL


# ---------------------------------------------------------------------------------------------------------------------
# measuring (shared by serve, control and dryrun)

def outputs_equal(got, want) -> bool:
    if got is None or want is None or len(got) != len(want):
        return False
    return all(tuple(tuple(int(v) for v in r) for r in a) == tuple(tuple(int(v) for v in r) for r in b)
               for a, b in zip(got, want))


def execute(rows: list, tasks: dict, workers: int) -> list:
    """rows: dicts with sample_id, task, code. Returns exec rows like arms.execute (callable mode, empty library)."""
    out, jobs, jrows = {}, [], []
    for r in rows:
        if not r.get('code'):
            out[r['sample_id']] = {'sample_id': r['sample_id'], 'code_sha': None, 'status': 'NO_CODE', 'demo_pass': False,
                                   'n_demo_pass': 0, 'n_demos': len(tasks[r['task']].train), 'first_fail_demo': None,
                                   'test_outputs': None, 'helper_calls': {}, 'static_refs': [], 'wall_s': [],
                                   'timeouts': 0, 'exec_mode': 'callable', 'cache_hit': False}
            continue
        jobs.append(sandbox.ExecJob(sample_id=r['sample_id'], task=tasks[r['task']], code=r['code'], library_src='',
                                    mode='callable'))
        jrows.append(r)
    for j, res in zip(jobs, sandbox.run_batch(jobs, workers)):
        out[j.sample_id] = res.to_row()
    for r in rows:
        e = out[r['sample_id']]
        e['test_correct'] = bool(e.get('demo_pass')) and outputs_equal(e.get('test_outputs'), tasks[r['task']].test_outputs)
    return [out[r['sample_id']] for r in rows]


def growth_sid(sid: str) -> str:
    """accept() refuses any sample whose id is not phase 'growth'; pilot rows (control) are relabelled for the count."""
    p = sid.split('|')
    if len(p) >= 2 and p[1] == 'pilot':
        p[1] = 'growth'
    return '|'.join(p)


def measure(rows: list, ex: list, tasks: dict, tk, label: str) -> dict:
    """rows: sample dicts (sample_id, task, text, code, finish_reason, gen_tokens); ex: exec rows in the same order."""
    n = len(rows)
    gens = [int(r['gen_tokens']) for r in rows]
    by_task: dict = {}
    for r, e in zip(rows, ex):
        by_task.setdefault(r['task'], []).append(select.candidate_from_exec(ExecResult.from_row(e), len(r.get('code') or '')))
    p2 = {}
    for t in sorted(tasks):
        sub = select.pass2(t, by_task.get(t, []))
        p2[t] = any(tuple(a.outputs) == tuple(tasks[t].test_outputs) for a in sub.attempts)
    dp = [(r, e) for r, e in zip(rows, ex) if e.get('demo_pass')]
    empty = library.empty(label)
    sols = []
    n_with_helper = 0
    hashes = set()
    for r, e in dp:
        sol = helpers.build_solution(growth_sid(r['sample_id']), r['task'], r['code'], empty.hashes(), demo_pass=True,
                                     code_sha=sha256_text(r['code']))
        if sol is None:
            continue
        sols.append(sol)
        if sol.helpers:
            n_with_helper += 1
        hashes.update(h.hash for h in sol.helpers)
    dd = helpers.dedup_solutions(sols)
    acc = helpers.accept(dd, empty, tk)
    statuses: dict = {}
    for e in ex:
        statuses[e['status']] = statuses.get(e['status'], 0) + 1
    return {
        'samples': n,
        'finish_length_share': (sum(1 for r in rows if r.get('finish_reason') == 'length') / n) if n else None,
        'median_gen_tokens': statistics.median(gens) if gens else None,
        'mean_gen_tokens': (sum(gens) / n) if n else None,
        'gen_tokens_total': sum(gens),
        'def_transform_share': (sum(1 for r in rows if 'def transform' in (r.get('text') or '')) / n) if n else None,
        'code_extracted_share': (sum(1 for r in rows if r.get('code')) / n) if n else None,
        'demo_pass_samples': len(dp),
        'demo_pass_tasks': len({r['task'] for r, _ in dp}),
        'test_correct_tasks_any': len({r['task'] for r, e in zip(rows, ex) if e.get('test_correct')}),
        'pass2_test_correct_tasks': sum(1 for v in p2.values() if v),
        'n_tasks': len(tasks),
        'solutions': len(sols), 'solutions_dedup': len(dd),
        'share_demo_pass_with_toplevel_helper': (n_with_helper / len(sols)) if sols else None,
        'demo_pass_with_toplevel_helper': n_with_helper,
        'distinct_helper_hashes': len(hashes),
        'helpers_accepted': len(acc),
        'accepted': [{'name': h.name, 'by': h.accepted_by, 'tasks': h.n_calling_tasks, 'k': h.n_solutions,
                      'mdl_gain': h.mdl_gain} for h in acc],
        'status_counts': dict(sorted(statuses.items())),
    }


# ---------------------------------------------------------------------------------------------------------------------
# sampling

def sample_variant(client, variant: str, tasks: dict, tk, sbase: int, prefill_eff: str, deadline) -> tuple[list, dict]:
    reqs, info = build_requests(tasks, tk, variant, sbase)
    rows: list = []
    usage = {'prompt': 0, 'completion': 0, 'cached': 0, 'requests': 0}

    def on_result(res) -> None:
        inf = info[res.request_id]
        u = res.usage or {}
        usage['prompt'] += int(u.get('prompt_tokens') or 0)
        usage['completion'] += int(u.get('completion_tokens') or 0)
        usage['cached'] += int(((u.get('prompt_tokens_details') or {}) or {}).get('cached_tokens') or 0)
        usage['requests'] += 1
        usage.setdefault('prompt_by_task', {})[inf['task']] = int(u.get('prompt_tokens') or 0)
        for i, (sid, comp) in enumerate(zip(inf['sample_ids'], res.texts)):
            text = (prefill_eff + comp) if VARIANTS[variant]['prefill'] else comp
            code = extract.extract_code(text)
            rows.append({'sample_id': sid, 'request_id': res.request_id, 'task': inf['task'], 'seed': inf['seed'],
                         'seed_idx': i, 'completion': comp, 'text': text, 'code': code,
                         'finish_reason': res.finish_reasons[i], 'gen_tokens': int(tk.count(comp)),
                         'user_sha': inf['user_sha']})

    t0 = time.time()
    out = client.run(reqs, on_result, deadline[0], deadline[1])
    usage['sampling_s'] = round(time.time() - t0, 1)
    usage['run'] = {k: v for k, v in out.items() if k != 'error_ids'}
    rows.sort(key=lambda r: (r['task'], r['seed_idx']))
    return rows, usage


def write_jsonl(p: Path, rows) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + '\n')


COLS = [('samples', 'samples'), ('finish_length_share', 'finish=length'), ('median_gen_tokens', 'median gen'),
        ('mean_gen_tokens', 'mean gen'), ('def_transform_share', 'def transform'), ('demo_pass_tasks', 'demo-pass tasks /50'),
        ('pass2_test_correct_tasks', 'pass@2 tasks /50'), ('share_demo_pass_with_toplevel_helper', 'demo-pass w/ helper'),
        ('distinct_helper_hashes', 'distinct helper hashes'), ('helpers_accepted', 'accepted (rule)'),
        ('wall_s', 'wall s')]


def fmt(v) -> str:
    if v is None:
        return 'NA'
    if isinstance(v, float):
        return '%.4f' % v if v < 10 else '%.1f' % v
    return str(v)


def md_table(res: dict) -> str:
    lines = ['| variant | ' + ' | '.join(c[1] for c in COLS) + ' |', '|---' * (len(COLS) + 1) + '|']
    for k, m in res.items():
        lines.append('| %s | ' % k + ' | '.join(fmt(m.get(c[0])) for c in COLS) + ' |')
    return '\n'.join(lines)


def run_serve(args, out: Path) -> int:
    t_job = float(os.environ.get('RATCHET_JOB_START_TS') or time.time())
    deadline = (t_job + config.STOP_ISSUE_S, t_job + config.HARD_STOP_S)
    ids = smoke_ids()
    mc = check_model_files()
    log('MODEL_FILES', json.dumps(mc))
    tk = tokmod.load_tokenizer(config.MODEL_DIR)
    tasks = load_tasks(ids)
    sbase = seed_base()
    url = os.environ['RATCHET_VLLM_URL']
    model = os.environ.get('RATCHET_SERVED_MODEL', 'ratchet')
    client = PrefillClient(url, model, None, tk, max_inflight=max(1, config.CLIENT_INFLIGHT_SEQS // S))
    client.wait_ready(120)
    # rendered prompt tail, server side, for one P1 and one P2 request
    render = {}
    t0id = ids[0]
    for v in ('P1', 'P2'):
        reqs, _ = build_requests({t0id: tasks[t0id]}, tk, v, sbase)
        msgs = list(reqs[0].messages) + [{'role': 'assistant', 'content': PREFILL}]
        render[v] = render_server(url, model, msgs, tk)
        log('RENDER_TAIL %s task=%s %s' % (v, t0id, json.dumps(render[v])))
    pre_eff = effective_prefill(render['P1'].get('tail'))
    log('PREFILL_EFFECTIVE %r (sent %r)' % (pre_eff, PREFILL))
    results, usage_all = {}, {}
    sub = out / 'smoke_a5'
    for v in ('P0', 'P1', 'P2'):
        t0 = time.time()
        rows, usage = sample_variant(client, v, tasks, tk, sbase, pre_eff, deadline)
        t1 = time.time()
        if len(rows) != S * len(ids):
            log('SAMPLE_INCOMPLETE %s %d of %d %s' % (v, len(rows), S * len(ids), usage['run']))
        ex = execute(rows, tasks, args.workers)
        t2 = time.time()
        m = measure(rows, ex, tasks, tk, 'SMOKE_' + v)
        m.update({'wall_s': round(t2 - t0, 1), 'sampling_s': round(t1 - t0, 1), 'exec_s': round(t2 - t1, 1),
                  'usage': usage, 'what': VARIANTS[v]['what'],
                  'instruction_sha': sha256_text(VARIANTS[v]['instruction']), 'prefill_sent': VARIANTS[v]['prefill']})
        results[v] = m
        usage_all[v] = usage
        write_jsonl(sub / ('%s_samples.jsonl' % v), rows)
        write_jsonl(sub / ('%s_exec.jsonl' % v), ex)
        log('VARIANT %s %s' % (v, json.dumps({k: m[k] for k in m if k not in ('accepted', 'usage')})))
        if v == 'P0':
            led = v2_ledger_v1_flat_a()
            pbt = usage.get('prompt_by_task', {})
            m['p0_prompt_tokens_equal_v1_flat_a'] = sum(1 for t in pbt if led.get(t, {}).get('prompt_tokens') == pbt[t])
            log('P0_PROMPT_TOKENS_EQUAL_V1_FLAT_A %d of %d' % (m['p0_prompt_tokens_equal_v1_flat_a'], len(pbt)))
        log('GEN_TOKENS %s per_sample_sum=%d usage_completion=%d prompt=%d cached=%d' % (
            v, m['gen_tokens_total'], usage['completion'], usage['prompt'], usage['cached']))
        if time.time() > deadline[0]:
            log('DEADLINE stop issuing after %s' % v)
            break
    body = {'schema': 'ratchet.smoke_a5.v1', 'created_et': now_et(), 'prereg': config.PREREG_ID,
            'code_sha': os.environ.get('RATCHET_CODE_SHA'), 'job': os.environ.get('SLURM_JOB_ID'),
            'gpu': os.environ.get('RATCHET_GPU_NAME'), 'model_dir': str(config.MODEL_DIR), 'S': S, 'n_tasks': len(ids),
            'sampling': dict(config.SAMPLING), 'seed_phase': SEED_PHASE, 'seed_base': sbase,
            'ids_sha256': arc_io.id_list_sha256(ids), 'helper_sentence': HELPER_SENTENCE, 'prefill': PREFILL,
            'prefill_effective': pre_eff, 'render': render, 'model_files': mc,
            'vllm_startup_s': os.environ.get('RATCHET_VLLM_STARTUP_S'), 'variants': results,
            'gen_tokens_total': {v: results[v]['gen_tokens_total'] for v in results}}
    (out / 'SMOKE_A5.json').write_text(json.dumps(body, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    md = ['# SMOKE_A5 (Amendment 5 candidate smoke, diagnostic only)', '',
          'Created %s ET, job %s, code %s, model %s, S=%d on the %d pilot ids, temperature 0.8, top_p 0.95, '
          'max_tokens 4096, enable_thinking 0; variants run one after another on one server (P1 and P2 share P0\'s '
          'prompt prefix in the cache).' % (body['created_et'], body['job'], body['code_sha'], body['model_dir'], S,
                                             len(ids)), '',
          md_table(results), '',
          'P0: %s. P1: %s. P2: %s.' % (VARIANTS['P0']['what'], VARIANTS['P1']['what'], VARIANTS['P2']['what']), '',
          'Helper sentence (P2): "%s"' % HELPER_SENTENCE, '',
          'Prefill sent %r; effective (as rendered by the server) %r; program text = effective prefill + completion.'
          % (PREFILL, pre_eff), '',
          'Generated tokens (per-sample tokenizer sum / server usage): ' + '; '.join(
              '%s %d / %d' % (v, results[v]['gen_tokens_total'], results[v]['usage']['completion']) for v in results),
          '', 'Rendered tails (server /tokenize): ', '']
    for v in render:
        md += ['%s: `%r`' % (v, render[v].get('tail', render[v])[-120:] if isinstance(render[v].get('tail'), str)
                              else render[v]), '']
    (out / 'SMOKE_A5.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    log('WROTE %s %s' % (out / 'SMOKE_A5.json', out / 'SMOKE_A5.md'))
    return 0


# ---------------------------------------------------------------------------------------------------------------------
# positive control (CPU, read-only on runs/v2)

def read_jsonl(p: Path) -> list:
    return [json.loads(ln) for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip()]


def control_one(d: Path, split: str, tk, workers: int, label: str) -> dict:
    srows = read_jsonl(d / 'samples.jsonl')
    stored_ex = {r['sample_id']: r for r in read_jsonl(d / 'exec.jsonl')}
    ids = sorted({r['task'] for r in srows})
    tasks = load_tasks(ids, split)
    rows, code_same, gen_same = [], 0, 0
    for r in sorted(srows, key=lambda r: r['sample_id']):
        code = extract.extract_code(r['text'])
        code_same += int(code == r.get('code'))
        g = int(tk.count(r['text']))
        gen_same += int(g == int(r.get('gen_tokens') or -1))
        rows.append({'sample_id': r['sample_id'], 'task': r['task'], 'text': r['text'], 'code': code,
                     'finish_reason': r.get('finish_reason'), 'gen_tokens': g})
    t0 = time.time()
    ex = execute(rows, tasks, workers)
    m = measure(rows, ex, tasks, tk, label)
    m['exec_s'] = round(time.time() - t0, 1)
    agree = sum(1 for r, e in zip(rows, ex) if bool(e.get('demo_pass')) == bool(stored_ex.get(r['sample_id'], {}).get('demo_pass')))
    st_dp_tasks = len({r['task'] for r in srows if stored_ex.get(r['sample_id'], {}).get('demo_pass')})
    m.update({'dir': str(d), 'code_reextracted_equal': code_same, 'gen_tokens_recount_equal': gen_same,
              'demo_pass_agree_with_stored_exec': agree, 'stored_demo_pass_tasks': st_dp_tasks})
    return m


def run_control(args, out: Path) -> int:
    tk = tokmod.load_tokenizer(config.MODEL_DIR)
    res = {}
    res['V1_FLAT_A'] = control_one(RUN_V2 / 'pilot' / 'V1_FLAT_A', 'pilot', tk, args.workers, 'CTRL_V1_FLAT_A')
    log('CONTROL V1_FLAT_A', json.dumps({k: v for k, v in res['V1_FLAT_A'].items() if k != 'accepted'}))
    if not args.skip_stock:
        res['STOCK_r1'] = control_one(RUN_V2 / 'arms' / 'STOCK' / 'round_1', 'growth', tk, args.workers, 'CTRL_STOCK')
        st = json.loads((RUN_V2 / 'arms' / 'STOCK' / 'round_1' / 'round_state.json').read_text(encoding='utf-8'))
        res['STOCK_r1']['stored_round_state'] = {k: st.get(k) for k in ('demo_pass_tasks', 'n_helpers', 'n_accepted',
                                                                         'n_solutions')}
        log('CONTROL STOCK_r1', json.dumps({k: v for k, v in res['STOCK_r1'].items() if k != 'accepted'}))
    want = {'V1_FLAT_A': {'demo_pass_tasks': 22, 'finish_length_share': 0.775},
            'STOCK_r1': {'demo_pass_tasks': 165, 'helpers_accepted': 0}}
    checks = {}
    for k, w in want.items():
        if k not in res:
            continue
        for f, v in w.items():
            got = res[k][f]
            checks['%s.%s' % (k, f)] = {'want': v, 'got': got, 'ok': abs(float(got) - float(v)) < 1e-9}
    body = {'created_et': now_et(), 'checks': checks, 'all_ok': all(c['ok'] for c in checks.values()), 'results': res}
    (out / 'SMOKE_A5_CONTROL.json').write_text(json.dumps(body, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    log('CONTROL_CHECKS', json.dumps(checks), 'ALL_OK=%d' % body['all_ok'])
    return 0 if body['all_ok'] else 1


# ---------------------------------------------------------------------------------------------------------------------
# dry run (no GPU)

def run_dryrun(args, out: Path) -> int:
    ids = smoke_ids()
    mc = check_model_files()
    tk = tokmod.load_tokenizer(config.MODEL_DIR)
    tasks = load_tasks(ids)
    sbase = seed_base()
    allsids, nreq = [], 0
    for v in VARIANTS:
        reqs, info = build_requests(tasks, tk, v, sbase)
        nreq += len(reqs)
        for i in info.values():
            allsids += i['sample_ids']
    p0, _ = build_requests(tasks, tk, 'P0', sbase)
    p1, _ = build_requests(tasks, tk, 'P1', sbase)
    same_seed = all(a.seed == b.seed for a, b in zip(p0, p1))
    same_msgs = all(a.messages == b.messages for a, b in zip(p0, p1))
    # P0 equals the run's V1_FLAT_A user message byte for byte (same builder, same instruction)
    led = v2_ledger_v1_flat_a()
    tok_eq = sum(1 for q in p0 if led.get(q.meta['task'], {}).get('task_tokens') == q.meta['task_tokens']
                 and led.get(q.meta['task'], {}).get('instruction_tokens') == q.meta['instruction_tokens'])
    log('P0_VS_V1_FLAT_A_LEDGER task_and_instruction_tokens_equal=%d of %d (ledger rows %d)' % (tok_eq, len(p0), len(led)))
    log('DRYRUN requests=%d samples=%d unique=%d P0_P1_same_seed=%d P0_P1_same_messages=%d model=%s' % (
        nreq, len(allsids), len(set(allsids)), same_seed, same_msgs, json.dumps(mc)))
    body0 = PrefillClient('http://127.0.0.1:1', 'ratchet', None, tk, 1).build_body(p0[0])
    body1 = PrefillClient('http://127.0.0.1:1', 'ratchet', None, tk, 1).build_body(p1[0])
    log('BODY P0 keys=%s n_msgs=%d' % (sorted(body0), len(body0['messages'])))
    log('BODY P1 keys=%s n_msgs=%d last=%r' % (sorted(body1), len(body1['messages']), body1['messages'][-1]))
    render = {}
    for v in ('P1', 'P2'):
        reqs, _ = build_requests({ids[0]: tasks[ids[0]]}, tk, v, sbase)
        msgs = list(reqs[0].messages) + [{'role': 'assistant', 'content': PREFILL}]
        try:
            render[v] = render_offline(msgs)
        except Exception as e:   # noqa: BLE001
            render[v] = {'error': '%s: %s' % (type(e).__name__, e)}
        log('RENDER_OFFLINE %s %s' % (v, json.dumps(render[v])))
    pre_eff = effective_prefill((render.get('P1') or {}).get('tail'))
    log('PREFILL_EFFECTIVE (offline) %r' % pre_eff)
    # full path on 5 tasks against the stub (fixtures = V1_FLAT_A texts of the same task; for prefill variants the
    # fixture is cut after its first occurrence of the effective prefill so prefill + completion looks like a real prefilled answer)
    small = {t: tasks[t] for t in ids[:5]}
    fx = {}
    for t in small:
        texts = [r['text'] for r in read_jsonl(RUN_V2 / 'pilot' / 'V1_FLAT_A' / 'samples.jsonl') if r['task'] == t]
        fx[t] = texts
    res = {}
    dd = out / 'smoke_a5_dryrun'
    for v in ('P0', 'P1', 'P2'):
        if VARIANTS[v]['prefill']:
            pool = {t: [x.split(pre_eff, 1)[1] if pre_eff in x else x for x in fx[t]] for t in fx}
        else:
            pool = fx
        stub = PrefillStub(pool, None, tk, gen_tokens=None, max_inflight=4)
        rows, usage = sample_variant(stub, v, small, tk, sbase, pre_eff, (time.time() + 600, time.time() + 900))
        ex = execute(rows, small, args.workers)
        m = measure(rows, ex, small, tk, 'DRY_' + v)
        res[v] = m
        write_jsonl(dd / ('%s_samples.jsonl' % v), rows)
        write_jsonl(dd / ('%s_exec.jsonl' % v), ex)
        last = stub.bodies[-1]
        log('DRY %s body_flags=%s n_msgs=%d %s' % (v, {k: last.get(k) for k in ('continue_final_message',
                                                                                 'add_generation_prompt')},
                                                     len(last['messages']),
                                                     json.dumps({k: m[k] for k in m if k not in ('accepted',)})))
    (dd / 'DRYRUN.json').write_text(json.dumps({'created_et': now_et(), 'render_offline': render,
                                                'prefill_effective': pre_eff, 'stub_results': res,
                                                'requests': nreq, 'samples': len(allsids),
                                                'p0_token_split_equal_v1_flat_a_ledger': tok_eq}, indent=1, sort_keys=True) + '\n',
                                    encoding='utf-8')
    log('WROTE', dd / 'DRYRUN.json')
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=('serve', 'control', 'dryrun'))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--workers', type=int, default=int(config.EXEC_WORKERS))
    ap.add_argument('--skip-stock', action='store_true')
    args = ap.parse_args(argv)
    out = check_out_dir(Path(args.out))
    log('SMOKE_A5 mode=%s out=%s workers=%d sandbox=%s' % (args.mode, out, args.workers, sandbox.probe_isolation()))
    return {'serve': run_serve, 'control': run_control, 'dryrun': run_dryrun}[args.mode](args, out)


if __name__ == '__main__':
    sys.exit(main())
