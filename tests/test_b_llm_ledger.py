"""Builder B: llm.py and ledger.py (SPEC 11 test_llm_ledger.py row). CPU only; the HTTP test talks to a fake
OpenAI-compatible server on 127.0.0.1 inside this process (no GPU, no model)."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ratchet import ledger as ledger_mod                        # noqa: E402
from ratchet.ledger import Ledger, LedgerSchemaError, NullLedger, iter_rows, totals, validate   # noqa: E402
from ratchet.llm import GenRequest, StubLLM, VLLMClient, parse_metrics   # noqa: E402
from ratchet.tok import StubTokenizer                          # noqa: E402

TOK = StubTokenizer()
POOL = [f'```python\ndef transform(grid):\n    return grid  # variant {i}\n```' for i in range(64)]


def req(rid, task='t1', n=4, seed=7, arm='STOCK', phase='growth', round=1, sealed_seed=None, content=None):
    msgs = [{'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': content or f'task {task}'}]
    return GenRequest(request_id=rid, messages=msgs, n=n, seed=seed,
                      meta={'run': 'v1', 'job_id': '42', 'arm': arm, 'phase': phase, 'round': round,
                            'sealed_seed': sealed_seed, 'task': task, 'library_tokens': 3, 'exemplar_tokens': 0,
                            'task_tokens': 2, 'instruction_tokens': 1, 'lib_sha': 'abc', 'model_sha': 'm'})


def good_row(**kw):
    r = {'ts_et': '2026-11-04 18:00:00', 'run': 'v1', 'job_id': '1', 'arm': 'STOCK', 'phase': 'growth', 'round': 1,
         'sealed_seed': None, 'task': 't', 'request_id': 'STOCK|growth|r1|t|b0', 'n': 2, 'seed': 5,
         'prompt_tokens': 100, 'prompt_tokens_logical': 200, 'cached_prompt_tokens': 10, 'library_tokens': 30,
         'exemplar_tokens': 0, 'task_tokens': 50, 'instruction_tokens': 15, 'gen_tokens': 40,
         'gen_tokens_per_sample': [20, 20], 'finish_reasons': ['stop', 'length'], 'latency_s': 1.5, 'lib_sha': 'x',
         'model_sha': 'y', 'sampling': {'temperature': 0.8, 'top_p': 0.95, 'max_tokens': 4096, 'enable_thinking': False}}
    r.update(kw)
    return r


class TmpDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_b_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestStub(TmpDir):
    def test_deterministic(self):
        a = StubLLM(POOL, NullLedger(), TOK).generate(req('r1'))
        b = StubLLM(POOL, NullLedger(), TOK).generate(req('r1'))
        self.assertEqual(a.texts, b.texts)
        self.assertEqual(len(a.texts), 4)
        c = StubLLM(POOL, NullLedger(), TOK).generate(req('r1', seed=8))
        self.assertNotEqual(a.texts, c.texts)

    def test_task_pool_and_files(self):
        fx = self.tmp / 'fx.json'
        fx.write_text(json.dumps({'*': ['generic'], 'tA': ['answer A']}), encoding='utf-8')
        s = StubLLM(fx, NullLedger(), TOK)
        self.assertEqual(s.generate(req('x', task='tA', n=2)).texts, ['answer A', 'answer A'])
        self.assertEqual(s.generate(req('y', task='tB', n=1)).texts, ['generic'])

    def test_body_sampling(self):
        s = StubLLM(POOL, NullLedger(), TOK)
        s.generate(req('r1', n=3, seed=99))
        b = s.bodies[0]
        self.assertEqual((b['temperature'], b['top_p'], b['max_tokens'], b['n'], b['seed']), (0.8, 0.95, 4096, 3, 99))
        self.assertEqual(b['chat_template_kwargs'], {'enable_thinking': False})

    def test_ledger_row_values(self):
        led = NullLedger()
        s = StubLLM(POOL, led, TOK, gen_tokens=50)
        r = s.generate(req('r1', n=4))
        row = led.rows[0]
        self.assertEqual(row, r.ledger_row)
        p = TOK.count('sys') + TOK.count('task t1')
        self.assertEqual(row['prompt_tokens'], p)
        self.assertEqual(row['prompt_tokens_logical'], 4 * p)
        self.assertEqual(row['gen_tokens'], 200)
        self.assertEqual(row['gen_tokens_per_sample'], [50, 50, 50, 50])
        self.assertEqual(row['library_tokens'], 3)
        self.assertEqual(row['cached_prompt_tokens'], 0)
        validate(row)

    def test_nothink_marker(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            s = StubLLM(['<think>hmm</think> code'], NullLedger(), TOK)
            s.generate(req('a'))
            s.generate(req('b'))
        out = buf.getvalue()
        self.assertEqual(out.count('LEVER NOTHINK'), 1)
        self.assertIn('first_response_has_think=1', out)
        self.assertEqual(s.counters['think_responses'], 2)


class TestLedger(TmpDir):
    def test_schema_rejects(self):
        validate(good_row())
        bad = [good_row(n=3), good_row(prompt_tokens_logical=100), good_row(phase='train'),
               good_row(n=True), good_row(cached_prompt_tokens=101), good_row(sampling={'temperature': 0.8})]
        r = good_row()
        del r['task']
        bad.append(r)
        for b in bad:
            with self.assertRaises(LedgerSchemaError):
                validate(b)
        validate(good_row(cached_prompt_tokens=None))

    def test_write_dedup_torn_totals(self):
        d = self.tmp / 'ledger'
        with Ledger(d / 'ledger_100.jsonl') as led:
            led.append(good_row(request_id='a', gen_tokens=40))
            led.append(good_row(request_id='b', arm='FLATTTC', phase='sealed', sealed_seed=1, round=None,
                                library_tokens=0))
        with Ledger(d / 'ledger_99.jsonl') as led:          # an earlier job (numeric order, not string order)
            led.append(good_row(request_id='a', gen_tokens=999, gen_tokens_per_sample=[500, 499]))
        with open(d / 'ledger_100.jsonl', 'a', encoding='utf-8') as f:
            f.write('{"request_id": "torn", "n": 2')         # job killed mid-write
        rows = list(iter_rows(self.tmp))
        self.assertEqual([r['request_id'] for r in rows], ['a', 'b'])
        self.assertEqual(rows[0]['gen_tokens'], 40)          # job 100 wins over job 99
        t = totals(self.tmp, arm='STOCK')
        self.assertEqual((t['prompt'], t['prompt_logical'], t['gen'], t['logical_total']), (100, 200, 40, 240))
        self.assertEqual((t['samples'], t['requests'], t['truncated'], t['library'], t['library_logical']),
                         (2, 1, 1, 30, 60))
        t2 = totals(self.tmp, phase='sealed', sealed_seed=1)
        self.assertEqual((t2['requests'], t2['samples']), (1, 2))
        self.assertEqual(totals(self.tmp)['requests'], 2)
        # reopening repairs the torn tail and keeps appending
        with Ledger(d / 'ledger_100.jsonl') as led:
            led.append(good_row(request_id='c'))
        self.assertEqual(sorted(r['request_id'] for r in iter_rows(self.tmp)), ['a', 'b', 'c'])

    def test_tokdiff_logged(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), Ledger(self.tmp / 'ledger' / 'ledger_1.jsonl') as led:
            led.append(good_row(gen_tokens_per_sample=[20, 21]))   # diff 1 <= n: silent
            led.append(good_row(request_id='z', gen_tokens_per_sample=[30, 20]))   # diff 10 > n
        self.assertEqual(buf.getvalue().count('LEDGER_TOKDIFF'), 1)
        self.assertEqual(led.tokdiff_rows, 1)


class TestRunDeadline(TmpDir):
    def test_all_done(self):
        led = Ledger(self.tmp / 'ledger' / 'ledger_7.jsonl')
        s = StubLLM(POOL, led, TOK, max_inflight=4)
        got = []
        now = time.time()
        out = s.run((req(f'r{i}', task=f't{i}') for i in range(30)), got.append, now + 60, now + 90)
        led.close()
        self.assertEqual((out['issued'], out['done'], out['exit'], out['abandoned']), (30, 30, 'DONE', 0))
        self.assertEqual(sorted(r.request_id for r in got), sorted(f'r{i}' for i in range(30)))
        self.assertEqual(totals(self.tmp)['requests'], 30)

    def test_stop_issue(self):
        led = NullLedger()
        s = StubLLM(POOL, led, TOK, max_inflight=2, delay_s=0.2)
        pulled = []

        def gen():
            for i in range(50):
                pulled.append(i)
                yield req(f'r{i}')
        now = time.time()
        out = s.run(gen(), lambda r: None, now + 0.5, now + 30)
        self.assertEqual(out['exit'], 'STOP_ISSUE')
        self.assertLess(out['issued'], 50)
        self.assertEqual(out['done'], out['issued'])   # in-flight ones finish after stop_issue
        self.assertEqual(len(pulled), out['issued'])   # the iterator is not drained past the stop
        self.assertEqual(len(led.rows), out['done'])

    def test_hard_stop_abandons_without_ledger_rows(self):
        led = NullLedger()
        s = StubLLM(POOL, led, TOK, max_inflight=3, delay_s=1.5)
        now = time.time()
        out = s.run((req(f'r{i}') for i in range(10)), lambda r: None, now + 0.1, now + 0.4)
        self.assertEqual(out['exit'], 'HARD_STOP')
        self.assertEqual((out['done'], out['abandoned']), (0, 3))
        self.assertLess(out['seconds'], 1.4)
        time.sleep(1.6)                                # the abandoned threads finish now
        self.assertEqual(led.rows, [])

    def test_errors_not_delivered(self):
        led = NullLedger()
        s = StubLLM(POOL, led, TOK, fail_ids={'r1'})
        got = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            now = time.time()
            out = s.run((req(f'r{i}') for i in range(3)), got.append, now + 10, now + 20)
        self.assertEqual((out['done'], out['errors'], out['error_ids']), (2, 1, ['r1']))
        self.assertNotIn('r1', [r.request_id for r in got])
        self.assertIn('LLM_ERROR request_id=r1', buf.getvalue())


METRICS = """# HELP vllm:prefix_cache_queries_total x
# TYPE vllm:prefix_cache_queries_total counter
vllm:prefix_cache_queries_total{engine="0",model_name="m"} 1000.0
vllm:prefix_cache_hits_total{engine="0",model_name="m"} 750.0
vllm:num_requests_running{engine="0",model_name="m"} 12.0
vllm:num_requests_waiting{engine="0",model_name="m"} 3.0
vllm:num_preemptions_total{engine="0",model_name="m"} 1.0
vllm:generation_tokens_total{engine="0",model_name="m"} 5555.0
"""


class _Fake(BaseHTTPRequestHandler):
    bodies: list = []
    calls = {'models': 0}

    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype='application/json'):
        raw = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/v1/models':
            _Fake.calls['models'] += 1
            if _Fake.calls['models'] < 2:
                return self._send(503, {'error': 'loading'})
            return self._send(200, {'data': [{'id': 'qwen'}]})
        if self.path == '/metrics':
            return self._send(200, METRICS, 'text/plain')
        self._send(404, {})

    def do_POST(self):
        n = int(self.headers['Content-Length'])
        b = json.loads(self.rfile.read(n))
        _Fake.bodies.append(b)
        if b['messages'][-1]['content'] == 'boom':
            return self._send(400, {'error': 'bad'})
        ch = [{'index': i, 'message': {'role': 'assistant', 'content': f'out {i} for seed {b["seed"]}'},
               'finish_reason': 'length' if i == 0 else 'stop'} for i in reversed(range(b['n']))]
        self._send(200, {'choices': ch, 'usage': {'prompt_tokens': 11, 'completion_tokens': 6 * b['n'],
                                                  'total_tokens': 11 + 6 * b['n'],
                                                  'prompt_tokens_details': {'cached_tokens': 8}}})


class TestHTTPClient(TmpDir):
    def setUp(self):
        super().setUp()
        _Fake.bodies = []
        _Fake.calls = {'models': 0}
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), _Fake)
        self.th = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.th.start()
        self.url = f'http://127.0.0.1:{self.srv.server_address[1]}/v1'

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def test_ready_generate_metrics(self):
        led = NullLedger()
        c = VLLMClient(self.url, 'qwen', led, TOK, max_inflight=4, timeout_s=10)
        from ratchet import llm
        # config.py now defines LLM_READY_POLL_S (integration pass), and config wins over _DEFAULTS: patch both
        llm._DEFAULTS['LLM_READY_POLL_S'] = 0.05
        _pc = mock.patch.object(llm._config, 'LLM_READY_POLL_S', 0.05, create=True)
        _pc.start()
        try:
            secs = c.wait_ready(5)
        finally:
            _pc.stop()
            llm._DEFAULTS['LLM_READY_POLL_S'] = 2.0
        self.assertGreaterEqual(_Fake.calls['models'], 2)
        self.assertLess(secs, 5)
        with contextlib.redirect_stdout(io.StringIO()):
            r = c.generate(req('h1', n=3, seed=1234))
        self.assertEqual(r.texts, ['out 0 for seed 1234', 'out 1 for seed 1234', 'out 2 for seed 1234'])
        self.assertEqual(r.finish_reasons, ['length', 'stop', 'stop'])
        row = led.rows[0]
        self.assertEqual((row['prompt_tokens'], row['prompt_tokens_logical'], row['gen_tokens'],
                          row['cached_prompt_tokens']), (11, 33, 18, 8))
        self.assertEqual(row['gen_tokens_per_sample'], [TOK.count(t) for t in r.texts])
        b = _Fake.bodies[0]
        self.assertEqual(b['chat_template_kwargs'], {'enable_thinking': False})
        self.assertEqual((b['model'], b['n'], b['seed']), ('qwen', 3, 1234))
        m = c.server_metrics()
        self.assertAlmostEqual(m['prefix_cache_hit_rate'], 0.75)
        self.assertEqual((m['running'], m['waiting'], m['preemptions']), (12.0, 3.0, 1.0))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            c.prefix_marker()
        self.assertRegex(buf.getvalue(), r'LEVER PREFIX hit_rate=0\.\d+')

    def test_http_400_not_retried(self):
        c = VLLMClient(self.url, 'qwen', NullLedger(), TOK, max_inflight=1, timeout_s=10)
        with self.assertRaises(Exception):
            c.generate(req('bad', content='boom'))
        self.assertEqual(len(_Fake.bodies), 1)

    def test_wrong_model_name_fails_fast(self):
        from ratchet import llm
        c = VLLMClient(self.url, 'other', NullLedger(), TOK, max_inflight=1, timeout_s=10)
        # config.py now defines LLM_READY_POLL_S (integration pass), and config wins over _DEFAULTS: patch both
        llm._DEFAULTS['LLM_READY_POLL_S'] = 0.05
        _pc = mock.patch.object(llm._config, 'LLM_READY_POLL_S', 0.05, create=True)
        _pc.start()
        try:
            t0 = time.time()
            with self.assertRaises(llm.LLMError):
                c.wait_ready(60)
            self.assertLess(time.time() - t0, 5)
        finally:
            _pc.stop()
            llm._DEFAULTS['LLM_READY_POLL_S'] = 2.0

    def test_parse_metrics_no_queries(self):
        self.assertIsNone(parse_metrics('vllm:num_requests_running 1\n')['prefix_cache_hit_rate'])


if __name__ == '__main__':
    unittest.main()
