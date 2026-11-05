"""vLLM OpenAI-compatible client and StubLLM (SPEC 5 builder B; PREREG 3). Owner: builder B.

Stdlib `http.client` only. Every request is POST /v1/chat/completions with the registered sampling
(temperature 0.8, top_p 0.95, max_tokens 4096, n, per-request seed) and `chat_template_kwargs
{'enable_thinking': False}` (SPEC 13 I14). One ledger row per completed request (SPEC 4.4).

vLLM 0.30.0 facts read from the venv source on 2026-11-04 (rule 5):
- `v1/engine/parallel_sampling.py`: with n > 1 and a seed, child i samples with seed + i. Two requests on the same
  prompt whose seeds differ by less than n share child streams; seeds from a 4-byte sha256 (arms.seed_for) collide
  that way with probability about n / 2**32 per pair.
- `v1/sample/ops/topk_topp_sampler.py`: seeded requests get their own torch.Generator, so the draw sequence is
  fixed; the logits still depend on batch composition unless VLLM_BATCH_INVARIANT=1, so a re-run is not
  guaranteed byte-identical (the pilot determinism smoke measures this; it does not assume it).
- `entrypoints/openai/chat_completion/serving.py`: `usage.prompt_tokens_details.cached_tokens` is filled only when
  the server runs with --enable-prompt-tokens-details; without it the ledger stores cached_prompt_tokens = null.
- Prometheus counters `vllm:prefix_cache_queries` / `vllm:prefix_cache_hits` (exported with `_total`).

Deadlines: `run` stops issuing at `stop_issue_ts` and abandons in-flight requests at `hard_stop_ts`. Worker threads
are daemons, so an abandoned HTTP call never blocks interpreter exit; an abandoned request writes no ledger row and
is re-issued by the next job (its request_id is not done).
"""
from __future__ import annotations

import hashlib
import http.client
import json
import queue
import re
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit

try:   # builder D owns config.py
    from ratchet import config as _config
except ImportError:   # pragma: no cover
    _config = None

_DEFAULTS = {
    'TEMPERATURE': 0.8,
    'TOP_P': 0.95,
    'MAX_TOKENS': 4096,
    'ENABLE_THINKING': False,
    'VLLM_REQUEST_TIMEOUT_S': 900,
    'LLM_RETRIES': 2,               # retries on connection errors and HTTP 5xx (same seed, so the same draw)
    'LLM_RETRY_SLEEP_S': 2.0,
    'LLM_READY_POLL_S': 2.0,
    'LLM_RESULT_WAIT_S': 0.5,       # main-loop wait for a finished request before re-checking the deadlines
}


def _cfg(name: str):
    if _config is not None and hasattr(_config, name):
        return getattr(_config, name)
    return _DEFAULTS[name]


def now_et(fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    try:
        from zoneinfo import ZoneInfo
        import datetime as _dt
        return _dt.datetime.now(ZoneInfo('America/New_York')).strftime(fmt)
    except Exception:   # no tz database: Quartz local time is Eastern
        return time.strftime(fmt, time.localtime())


class LLMError(RuntimeError):
    pass


class Abandoned(LLMError):
    pass


@dataclass
class GenRequest:
    request_id: str
    messages: list[dict]
    n: int
    seed: int
    meta: dict = field(default_factory=dict)   # ledger fields: run, job_id, arm, phase, round, sealed_seed, task,
                                               # library_tokens, exemplar_tokens, task_tokens, instruction_tokens,
                                               # lib_sha, model_sha


@dataclass
class GenResult:
    request_id: str
    texts: list[str]
    finish_reasons: list[str]
    usage: dict
    latency_s: float
    gen_tokens_per_sample: list[int] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)   # reasoning_content per choice, '' when absent
    ledger_row: dict | None = None
    req: GenRequest | None = None


_META_DEFAULTS = {'run': '', 'job_id': '', 'arm': '', 'phase': 'growth', 'round': None, 'sealed_seed': None,
                  'task': '', 'library_tokens': 0, 'exemplar_tokens': 0, 'task_tokens': 0, 'instruction_tokens': 0,
                  'lib_sha': None, 'model_sha': None}
_THINK_RE = re.compile(r'<think>|</think>')


def sampling_params() -> dict:
    return {'temperature': float(_cfg('TEMPERATURE')), 'top_p': float(_cfg('TOP_P')),
            'max_tokens': int(_cfg('MAX_TOKENS')), 'enable_thinking': bool(_cfg('ENABLE_THINKING'))}


class VLLMClient:
    def __init__(self, base_url: str, model: str, ledger, tok, max_inflight: int, timeout_s: float | None = None):
        u = urlsplit(base_url if '://' in base_url else 'http://' + base_url)
        self.base_url = base_url
        self.host = u.hostname or '127.0.0.1'
        self.port = u.port or 80
        self.prefix = u.path.rstrip('/')
        if self.prefix.endswith('/v1'):
            self.prefix = self.prefix[:-3]
        self.model = model
        self.ledger = ledger
        self.tok = tok
        self.max_inflight = max(1, int(max_inflight))
        self.timeout_s = float(timeout_s if timeout_s is not None else _cfg('VLLM_REQUEST_TIMEOUT_S'))
        self.sampling = sampling_params()
        self._lock = threading.Lock()
        self._abandoned: set[str] = set()
        self._think_marker_done = False
        self.counters = {'requests': 0, 'errors': 0, 'retries': 0, 'abandoned': 0, 'prompt': 0, 'gen': 0,
                         'cached': 0, 'think_responses': 0}

    # ------------------------------------------------------------------ HTTP
    def _http(self, method: str, path: str, body: bytes | None, timeout_s: float) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection(self.host, self.port, timeout=max(0.1, timeout_s))
        try:
            headers = {'Content-Type': 'application/json'} if body is not None else {}
            conn.request(method, self.prefix + path, body=body, headers=headers)
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def wait_ready(self, timeout_s: float) -> float:
        """Polls GET /v1/models until it answers 200 with this model; returns the seconds waited."""
        t0 = time.time()
        poll = float(_cfg('LLM_READY_POLL_S'))
        last = None
        while True:
            try:
                st, raw = self._http('GET', '/v1/models', None, timeout_s=10)
                if st == 200:
                    ids = [m.get('id') for m in json.loads(raw).get('data', [])]
                    if not self.model or self.model in ids or not ids:
                        return time.time() - t0
                    # the server is up but serves another name: a config error, fail now, not after timeout_s
                    raise LLMError(f'vLLM serves {ids}, not {self.model!r} (set --served-model-name or the client model)')
                else:
                    last = f'HTTP {st}'
            except (OSError, http.client.HTTPException, ValueError) as e:
                last = f'{type(e).__name__}: {e}'
            if time.time() - t0 + poll > timeout_s:
                raise TimeoutError(f'vLLM not ready after {time.time() - t0:.0f} s ({last})')
            time.sleep(poll)

    def build_body(self, req: GenRequest) -> dict:
        s = self.sampling
        return {'model': self.model, 'messages': req.messages, 'n': int(req.n), 'seed': int(req.seed),
                'temperature': s['temperature'], 'top_p': s['top_p'], 'max_tokens': s['max_tokens'],
                'chat_template_kwargs': {'enable_thinking': s['enable_thinking']}}

    def _post_chat(self, body: dict, req: GenRequest, timeout_s: float) -> dict:
        """One POST; returns the parsed response JSON. Raises LLMError (retryable flag in .retry)."""
        raw_body = json.dumps(body).encode('utf-8')
        try:
            st, raw = self._http('POST', '/v1/chat/completions', raw_body, timeout_s)
        except (OSError, http.client.HTTPException) as e:
            err = LLMError(f'{req.request_id}: {type(e).__name__}: {e}')
            err.retry = not isinstance(e, socket.timeout)
            raise err from e
        if st != 200:
            err = LLMError(f'{req.request_id}: HTTP {st}: {raw[:300]!r}')
            err.retry = st >= 500
            raise err
        try:
            return json.loads(raw)
        except ValueError as e:
            err = LLMError(f'{req.request_id}: bad JSON: {raw[:200]!r}')
            err.retry = True
            raise err from e

    # ------------------------------------------------------------------ one request
    def generate(self, req: GenRequest, hard_stop_ts: float | None = None) -> GenResult:
        body = self.build_body(req)
        t0 = time.time()
        tries = int(_cfg('LLM_RETRIES')) + 1
        resp = None
        for attempt in range(tries):
            timeout = self.timeout_s
            if hard_stop_ts is not None:
                timeout = min(timeout, hard_stop_ts - time.time())
                if timeout <= 0:
                    raise Abandoned(f'{req.request_id}: past hard stop')
            try:
                resp = self._post_chat(body, req, timeout)
                break
            except LLMError as e:
                if hard_stop_ts is not None and time.time() >= hard_stop_ts - 0.05:
                    raise Abandoned(f'{req.request_id}: cut at hard stop ({e})') from e
                if not getattr(e, 'retry', False) or attempt == tries - 1:
                    with self._lock:
                        self.counters['errors'] += 1
                    raise
                with self._lock:
                    self.counters['retries'] += 1
                time.sleep(float(_cfg('LLM_RETRY_SLEEP_S')))
        latency = time.time() - t0
        res = self._parse(req, resp, latency)
        with self._lock:
            abandoned = req.request_id in self._abandoned
        if abandoned:
            raise Abandoned(f'{req.request_id}: finished after abandon; no ledger row')
        res.ledger_row = self._ledger_row(req, res)
        if self.ledger is not None:
            self.ledger.append(res.ledger_row)
        self._think_marker(res)
        with self._lock:
            self.counters['requests'] += 1
            self.counters['prompt'] += res.ledger_row['prompt_tokens']
            self.counters['gen'] += res.ledger_row['gen_tokens']
            self.counters['cached'] += res.ledger_row['cached_prompt_tokens'] or 0
        return res

    def _parse(self, req: GenRequest, resp: dict, latency: float) -> GenResult:
        choices = sorted(resp.get('choices') or [], key=lambda c: int(c.get('index', 0)))
        if len(choices) != req.n:
            raise LLMError(f'{req.request_id}: {len(choices)} choices for n={req.n}')
        texts, frs, reas = [], [], []
        for c in choices:
            msg = c.get('message') or {}
            texts.append(msg.get('content') or '')
            reas.append(msg.get('reasoning_content') or msg.get('reasoning') or '')
            frs.append(str(c.get('finish_reason') or 'unknown'))
        usage = dict(resp.get('usage') or {})
        if 'prompt_tokens' not in usage or 'completion_tokens' not in usage:
            raise LLMError(f'{req.request_id}: usage lacks prompt_tokens/completion_tokens: {usage}')
        per = [self.tok.count(t) + (self.tok.count(r) if r else 0) for t, r in zip(texts, reas)]
        return GenResult(request_id=req.request_id, texts=texts, finish_reasons=frs, usage=usage, latency_s=latency,
                         gen_tokens_per_sample=per, reasoning=reas, req=req)

    def _ledger_row(self, req: GenRequest, res: GenResult) -> dict:
        meta = {**_META_DEFAULTS, **{k: v for k, v in req.meta.items() if k in _META_DEFAULTS}}
        u = res.usage
        details = u.get('prompt_tokens_details') or {}
        cached = details.get('cached_tokens') if isinstance(details, dict) else None
        p = int(u['prompt_tokens'])
        row = {
            'ts_et': now_et(), 'run': str(meta['run']), 'job_id': str(meta['job_id']), 'arm': str(meta['arm']),
            'phase': str(meta['phase']), 'round': meta['round'], 'sealed_seed': meta['sealed_seed'],
            'task': str(meta['task']), 'request_id': req.request_id, 'n': int(req.n), 'seed': int(req.seed),
            'prompt_tokens': p, 'prompt_tokens_logical': p * int(req.n),
            'cached_prompt_tokens': None if cached is None else int(cached),
            'library_tokens': int(meta['library_tokens']), 'exemplar_tokens': int(meta['exemplar_tokens']),
            'task_tokens': int(meta['task_tokens']), 'instruction_tokens': int(meta['instruction_tokens']),
            'gen_tokens': int(u['completion_tokens']), 'gen_tokens_per_sample': list(res.gen_tokens_per_sample),
            'finish_reasons': list(res.finish_reasons), 'latency_s': round(float(res.latency_s), 3),
            'lib_sha': meta['lib_sha'], 'model_sha': meta['model_sha'], 'sampling': dict(self.sampling),
        }
        return row

    def _think_marker(self, res: GenResult) -> None:
        has = any(_THINK_RE.search(t) for t in res.texts) or any(r for r in res.reasoning)
        with self._lock:
            if has:
                self.counters['think_responses'] += 1
            first = not self._think_marker_done
            self._think_marker_done = True
        if first:
            print(f'LEVER NOTHINK first_response_has_think={int(has)} request_id={res.request_id}', flush=True)

    # ------------------------------------------------------------------ many requests
    def run(self, reqs: Iterable[GenRequest], on_result: Callable[[GenResult], None],
            stop_issue_ts: float, hard_stop_ts: float) -> dict:
        """Issue `reqs` (pulled lazily) with at most max_inflight in flight; call on_result in this thread for each
        finished request. Stops issuing at stop_issue_ts; at hard_stop_ts abandons whatever is in flight.
        Returns {'issued', 'done', 'errors', 'abandoned', 'exhausted', 'exit', 'seconds', 'error_ids'}."""
        t0 = time.time()
        it = iter(reqs)
        results: queue.Queue = queue.Queue()
        inflight: dict[int, GenRequest] = {}
        out = {'issued': 0, 'done': 0, 'errors': 0, 'abandoned': 0, 'exhausted': False, 'exit': None,
               'seconds': 0.0, 'error_ids': []}
        wait = float(_cfg('LLM_RESULT_WAIT_S'))
        k = 0

        def worker(key: int, req: GenRequest) -> None:
            try:
                results.put((key, self.generate(req, hard_stop_ts=hard_stop_ts), None))
            except BaseException as e:   # noqa: BLE001  (reported in the main thread)
                results.put((key, None, e))

        try:
            while True:
                now = time.time()
                if now >= hard_stop_ts:
                    out['exit'] = 'HARD_STOP'
                    break
                while not out['exhausted'] and len(inflight) < self.max_inflight and time.time() < stop_issue_ts:
                    try:
                        req = next(it)
                    except StopIteration:
                        out['exhausted'] = True
                        break
                    k += 1
                    inflight[k] = req
                    threading.Thread(target=worker, args=(k, req), daemon=True,
                                     name=f'llm-{req.request_id}').start()
                    out['issued'] += 1
                if not inflight:
                    out['exit'] = 'DONE' if out['exhausted'] else 'STOP_ISSUE'
                    break
                try:
                    key, res, err = results.get(timeout=max(0.01, min(wait, hard_stop_ts - time.time())))
                except queue.Empty:
                    continue
                req = inflight.pop(key)
                if err is not None:
                    if isinstance(err, Abandoned):
                        out['abandoned'] += 1
                    else:
                        out['errors'] += 1
                        out['error_ids'].append(req.request_id)
                        print(f'LLM_ERROR request_id={req.request_id} {type(err).__name__}: {err}', flush=True)
                    continue
                on_result(res)
                out['done'] += 1
        finally:
            if inflight:
                with self._lock:
                    self._abandoned.update(r.request_id for r in inflight.values())
                    self.counters['abandoned'] += len(inflight)
                out['abandoned'] += len(inflight)
                inflight.clear()
            if self.ledger is not None and hasattr(self.ledger, 'sync'):
                self.ledger.sync()
            out['seconds'] = round(time.time() - t0, 3)
        return out

    # ------------------------------------------------------------------ server metrics
    def _metrics_text(self) -> str:
        st, raw = self._http('GET', '/metrics', None, timeout_s=10)
        if st != 200:
            raise LLMError(f'/metrics HTTP {st}')
        return raw.decode('utf-8', 'replace')

    def server_metrics(self) -> dict:
        """Prefix-cache hit rate (cumulative hits / queries), running, waiting, preemptions, token counters."""
        return parse_metrics(self._metrics_text())

    def prefix_marker(self) -> str:
        """Prints and returns the LEVER PREFIX line (SPEC 9)."""
        try:
            m = self.server_metrics()
            hr = m.get('prefix_cache_hit_rate')
            line = (f'LEVER PREFIX hit_rate={hr:.4f} queries={int(m.get("prefix_cache_queries", 0))} '
                    f'hits={int(m.get("prefix_cache_hits", 0))}' if hr is not None else 'LEVER PREFIX hit_rate=NA')
        except (OSError, http.client.HTTPException, LLMError) as e:
            line = f'LEVER PREFIX hit_rate=NA error={type(e).__name__}'
        print(line, flush=True)
        return line


_METRIC_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eEinfINFaN]+)')
_WANT = {
    'vllm:prefix_cache_queries': 'prefix_cache_queries', 'vllm:prefix_cache_hits': 'prefix_cache_hits',
    'vllm:num_requests_running': 'running', 'vllm:num_requests_waiting': 'waiting',
    'vllm:num_preemptions': 'preemptions', 'vllm:prompt_tokens': 'prompt_tokens',
    'vllm:prompt_tokens_cached': 'prompt_tokens_cached', 'vllm:generation_tokens': 'generation_tokens',
    'vllm:kv_cache_usage_perc': 'kv_cache_usage_perc', 'vllm:request_success': 'request_success',
    'vllm:gpu_prefix_cache_hit_rate': 'legacy_prefix_cache_hit_rate',
}


def parse_metrics(text: str) -> dict:
    """Prometheus text -> summed values for the names in _WANT (a `_total` suffix is stripped; labels summed)."""
    out: dict[str, float] = {}
    for ln in text.splitlines():
        if not ln or ln.startswith('#'):
            continue
        m = _METRIC_RE.match(ln)
        if not m:
            continue
        name = m.group(1)
        if name.endswith('_total'):
            name = name[:-6]
        key = _WANT.get(name)
        if key is None:
            continue
        try:
            v = float(m.group(3))
        except ValueError:
            continue
        out[key] = out.get(key, 0.0) + v
    q, h = out.get('prefix_cache_queries'), out.get('prefix_cache_hits')
    if q:
        out['prefix_cache_hit_rate'] = h / q if h is not None else 0.0
    elif 'legacy_prefix_cache_hit_rate' in out:
        out['prefix_cache_hit_rate'] = out['legacy_prefix_cache_hit_rate']
    else:
        out['prefix_cache_hit_rate'] = None
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Stub

def _load_fixtures(fixtures) -> dict[str, list[str]]:
    """A fixture pool: a list of texts (global), a dict {task_id or '*': [texts]}, a .json file holding either, or a
    directory of *.txt / *.md / *.py files (global pool, sorted by name)."""
    if isinstance(fixtures, (list, tuple)):
        return {'*': [str(x) for x in fixtures]}
    if isinstance(fixtures, dict):
        return {str(k): [str(x) for x in v] for k, v in fixtures.items()}
    p = Path(fixtures)
    if p.is_dir():
        files = sorted(x for x in p.iterdir() if x.suffix in ('.txt', '.md', '.py'))
        return {'*': [x.read_text(encoding='utf-8') for x in files]}
    obj = json.loads(p.read_text(encoding='utf-8'))
    return _load_fixtures(obj)


class StubLLM(VLLMClient):
    """Deterministic fake server: choice i of a request is pool[int(sha256(prompt|seed|i)) % len(pool)], where the
    pool is fixtures[task] if present, else fixtures['*'], and prompt = canonical JSON of the messages. Usage is
    computed with `tok`: prompt_tokens = sum of message content counts; completion tokens per choice = gen_tokens
    when given, else tok.count(text). Goes through the same parse, ledger and run() code as VLLMClient."""

    def __init__(self, fixtures, ledger, tok, gen_tokens: int | None = 50, *, max_inflight: int = 8,
                 delay_s: float = 0.0, finish_reason: str = 'stop', cached_tokens: int | None = 0,
                 fail_ids: Iterable[str] = ()):
        super().__init__('http://stub.invalid:1', 'stub', ledger, tok, max_inflight=max_inflight, timeout_s=60)
        self.pool = _load_fixtures(fixtures)
        if not any(self.pool.values()):
            raise ValueError('empty fixture pool')
        self.gen_tokens = gen_tokens
        self.delay_s = float(delay_s)
        self.finish_reason = finish_reason
        self.cached_tokens = cached_tokens
        self.fail_ids = set(fail_ids)
        self.bodies: list[dict] = []

    def wait_ready(self, timeout_s: float) -> float:
        return 0.0

    def server_metrics(self) -> dict:
        return {'prefix_cache_hit_rate': 0.0, 'prefix_cache_queries': 0.0, 'prefix_cache_hits': 0.0,
                'running': 0.0, 'waiting': 0.0, 'preemptions': 0.0}

    def pick(self, messages: list[dict], seed: int, i: int, task: str | None) -> str:
        pool = self.pool.get(task or '', None) or self.pool.get('*') or next(v for v in self.pool.values() if v)
        prompt = json.dumps(messages, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        h = hashlib.sha256(f'{prompt}|{seed}|{i}'.encode('utf-8')).hexdigest()
        return pool[int(h[:16], 16) % len(pool)]

    def _post_chat(self, body: dict, req: GenRequest, timeout_s: float) -> dict:
        with self._lock:
            self.bodies.append(body)
        if req.request_id in self.fail_ids:
            err = LLMError(f'{req.request_id}: stub failure')
            err.retry = False
            raise err
        if self.delay_s:
            if self.delay_s > timeout_s:     # behave like a socket timeout
                time.sleep(max(0.0, timeout_s))
                err = LLMError(f'{req.request_id}: stub timeout after {timeout_s:.2f} s')
                err.retry = False
                raise err
            time.sleep(self.delay_s)
        task = (req.meta or {}).get('task')
        texts = [self.pick(body['messages'], int(body['seed']), i, task) for i in range(int(body['n']))]
        per = [int(self.gen_tokens) if self.gen_tokens is not None else self.tok.count(t) for t in texts]
        p = sum(self.tok.count(str(m.get('content', ''))) for m in body['messages'])
        usage = {'prompt_tokens': p, 'completion_tokens': sum(per), 'total_tokens': p + sum(per)}
        if self.cached_tokens is not None:
            usage['prompt_tokens_details'] = {'cached_tokens': min(int(self.cached_tokens), p)}
        return {'id': 'stub-' + req.request_id, 'object': 'chat.completion', 'model': 'stub',
                'choices': [{'index': i, 'message': {'role': 'assistant', 'content': t}, 'finish_reason':
                             self.finish_reason} for i, t in enumerate(texts)],
                'usage': usage, '_per': per}

    def _parse(self, req: GenRequest, resp: dict, latency: float) -> GenResult:
        res = super()._parse(req, resp, latency)
        if self.gen_tokens is not None:     # the stub's "local tokenizer" agrees with its own usage
            res.gen_tokens_per_sample = list(resp['_per'])
        return res
