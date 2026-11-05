"""Builder E: pilot rules, rate fit, SPEC 1.3 projection and the S/R rule (PREREG 7)."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import ratchet  # noqa: F401
from ratchet import pilot


def write_jsonl(p: Path, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def exec_rows(which, passing, n=50):
    rows = []
    for i in range(n):
        t = f't{i:02d}'
        for s in range(2):
            rows.append({'sample_id': f'{which}|pilot|r1|{t}|s{s}', 'demo_pass': (i < passing and s == 0)})
    return rows


SPEC_RATES = {'g': 1000.0, 'P_task': 1500.0, 'L': 6000, 'a': 5370.0, 'b': 0.0, 'startup_s': 0.0,
              'u_flat_req': 0.0, 'u_lib_req': 0.0, 'd': 0.2}


class TestSteps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_smoke_and_plant(self):
        write_jsonl(self.run / 'pilot/FLAT_A/exec.jsonl', exec_rows('FLAT_A', 20))
        write_jsonl(self.run / 'pilot/FLAT_B/exec.jsonl', exec_rows('FLAT_B', 24))
        write_jsonl(self.run / 'pilot/PLANT1/exec.jsonl', exec_rows('PLANT1', 21))
        s1 = pilot.step1_smoke(self.run)
        self.assertEqual((s1['kA'], s1['kB'], s1['n']), (20, 24, 50))
        self.assertTrue(s1['pass'])
        s2 = pilot.step2_plant(self.run)
        self.assertEqual(s2['gain'], 1)
        self.assertTrue(s2['pass'])

    def test_smoke_fails_on_big_gap_and_plant_needs_one(self):
        self.assertFalse(pilot.smoke_rule(10, 30, 50)['pass'])
        write_jsonl(self.run / 'pilot/FLAT_A/exec.jsonl', exec_rows('FLAT_A', 20))
        write_jsonl(self.run / 'pilot/PLANT1/exec.jsonl', exec_rows('PLANT1', 20))
        self.assertFalse(pilot.step2_plant(self.run)['pass'])

    def test_rate_fit_recovers_a_b(self):
        # 40 requests, each 30 s long, in 30 s slots; prefill varies; gen = (a - b * prefill_rate) * 30
        a, b = 4000.0, 0.5
        t0 = dt.datetime(2026, 11, 5, 10, 0, 0)
        rows = []
        for i in range(40):
            pre_rate = 1000.0 + 200.0 * (i % 5)
            gen = (a - b * pre_rate) * 30
            end = t0 + dt.timedelta(seconds=30 * (i + 1))
            rows.append({'request_id': f'r{i}', 'phase': 'pilot', 'ts_et': end.strftime('%Y-%m-%d %H:%M:%S'),
                         'latency_s': 30.0, 'gen_tokens': gen, 'prompt_tokens': pre_rate * 30,
                         'cached_prompt_tokens': 0, 'n': 8})
        f = pilot.fit_rates(rows, bucket_s=30)
        self.assertEqual(f['method'], 'ols')
        self.assertAlmostEqual(f['a'], a, places=3)
        self.assertAlmostEqual(f['b'], b, places=6)
        f2 = pilot.fit_rates(rows[:3], bucket_s=30)
        self.assertEqual(f2['method'], 'mean')

    def test_step3_with_injected_correctness(self):
        t0 = dt.datetime(2026, 11, 5, 10, 0, 0)
        rows = [{'request_id': f'r{i}', 'phase': 'pilot', 'arm': 'FLAT_A',
                 'ts_et': (t0 + dt.timedelta(seconds=10 * i)).strftime('%Y-%m-%d %H:%M:%S'), 'latency_s': 40.0,
                 'gen_tokens': 8000, 'n': 8, 'prompt_tokens': 1500, 'cached_prompt_tokens': 300,
                 'task_tokens': 1100, 'instruction_tokens': 400, 'library_tokens': 0,
                 'finish_reasons': ['stop'] * 7 + ['length']} for i in range(30)]
        write_jsonl(self.run / 'ledger/ledger_1.jsonl', rows)
        ca = {f't{i}': i < 10 for i in range(50)}
        cb = {f't{i}': (i < 8 or i in (40, 41, 42)) for i in range(50)}
        r = pilot.step3_rates(self.run, correct_fn=lambda d, w: ca if w == 'FLAT_A' else cb)
        self.assertEqual(r['g'], 1000.0)
        self.assertEqual(r['P_task'], 1500.0)
        self.assertEqual(r['u_flat_req'], 1200.0)
        self.assertEqual(r['truncated_samples'], 30)
        self.assertEqual(r['discordance']['discordant'], 5)
        self.assertAlmostEqual(r['d'], 0.1)


class TestProjection(unittest.TestCase):
    def test_spec_floor_table(self):
        # Review fix 2026-11-04: FLAT extra per seed = T_STOCK / m_F = 1 + R x rho (STOCK round 1 has an empty context),
        # plus the knockout term 2 x 3 x KO_W_ASSUMED / 400 = 0.6 units. U(4) = 13 + 21 + 2 x (3 + 3 x 14.6) + 3 + 0.6.
        p = pilot.project(SPEC_RATES, 4, 4)
        self.assertAlmostEqual(p['rho'], 3.4)
        self.assertAlmostEqual(p['units']['total'], 131.2)
        self.assertAlmostEqual(p['units']['knockout'], 0.6)
        self.assertAlmostEqual(p['samples'], 209920.0)
        self.assertAlmostEqual(p['required_tok_s_12h'], 209920 * 1000 / 43200)
        self.assertAlmostEqual(pilot.project(SPEC_RATES, 4, 6)['units']['total'], 180.0)
        self.assertAlmostEqual(pilot.project(SPEC_RATES, 16, 8)['samples'], 1464320.0)
        # FLAT extra share at S = R = 4: 6 x 14.6 = 87.6 of 131.2 units (SPEC 1.6 item 2)
        self.assertAlmostEqual(p['units']['flat_extra'], 87.6)
        self.assertTrue(p['L_assumed'])
        self.assertEqual(p['exec_s'], 0.0)

    def test_jobs_and_feasibility(self):
        r = dict(SPEC_RATES, a=6000.0, startup_s=300.0)
        p = pilot.project(r, 4, 4)
        # decode s = 209,920,000 / 6000 = 34,986.7; usable per job = 3120 - 300 = 2820 -> 13 jobs > 12
        self.assertEqual(p['jobs'], 13)
        self.assertFalse(p['feasible'])
        r2 = dict(SPEC_RATES, a=10000.0, startup_s=300.0)
        self.assertEqual(pilot.project(r2, 4, 4)['jobs'], 8)
        # measured sandbox seconds count in the same jobs: 209,920 samples x 0.05 s = 10,496 s more -> 12 jobs
        self.assertEqual(pilot.project(dict(r2, exec_s_per_sample=0.05), 4, 4)['jobs'], 12)

    def test_choose(self):
        r = dict(SPEC_RATES, a=10000.0, startup_s=300.0)
        c = pilot.choose_SR(r, power_sims=2000)
        self.assertEqual(c['status'], 'OK')
        # at 10,000 tok/s and 2,820 usable s per job: (4,4) 8 jobs, (4,6) 11, (4,8) 13, (8,4) 15
        self.assertEqual((c['S'], c['R']), (4, 6))
        self.assertEqual({(p['S'], p['R']): p['jobs'] for p in c['grid']}[(4, 6)], 11)
        r_fast = dict(SPEC_RATES, a=40000.0, startup_s=300.0)
        c = pilot.choose_SR(r_fast, power_sims=2000)
        feas = {(p['S'], p['R']) for p in c['grid'] if p['feasible']}
        best = max(feas, key=lambda sr: (sr[0] * sr[1], sr[0]))
        self.assertEqual((c['S'], c['R']), best)
        slow = dict(SPEC_RATES, a=1000.0)
        c = pilot.choose_SR(slow, power_sims=2000)
        self.assertEqual(c['status'], 'PILOT_NO_FEASIBLE_SR')
        self.assertIsNone(c['S'])

    def test_tie_goes_to_larger_S(self):
        # S x R ties: (8, 4) = 32 and (4, 8) = 32; with both feasible, S = 8 wins
        r = dict(SPEC_RATES, a=1e9)
        c = pilot.choose_SR(r, power_sims=1000)
        self.assertEqual((c['S'], c['R']), (16, 8))
        grid = [pilot.project(r, S, R) for S, R in ((8, 4), (4, 8))]
        best = max(grid, key=lambda p: (p['S'] * p['R'], p['S']))
        self.assertEqual(best['S'], 8)

    def test_underpowered_flag(self):
        c = pilot.choose_SR(dict(SPEC_RATES, a=1e9, d=0.6), power_sims=4000)
        self.assertTrue(c['underpowered'])
        c = pilot.choose_SR(dict(SPEC_RATES, a=1e9, d=0.06), power_sims=4000)
        self.assertFalse(c['underpowered'])


class TestReport(unittest.TestCase):
    def test_write_report(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            write_jsonl(run / 'pilot/FLAT_A/exec.jsonl', exec_rows('FLAT_A', 20))
            write_jsonl(run / 'pilot/FLAT_B/exec.jsonl', exec_rows('FLAT_B', 21))
            write_jsonl(run / 'pilot/PLANT1/exec.jsonl', exec_rows('PLANT1', 25))
            t0 = dt.datetime(2026, 11, 5, 10, 0, 0)
            write_jsonl(run / 'ledger/ledger_1.jsonl', [
                {'request_id': f'r{i}', 'phase': 'pilot', 'ts_et': (t0 + dt.timedelta(seconds=5 * i)).strftime(
                    '%Y-%m-%d %H:%M:%S'), 'latency_s': 30.0, 'gen_tokens': 8000, 'n': 8, 'prompt_tokens': 1500,
                 'cached_prompt_tokens': 0, 'task_tokens': 1100, 'instruction_tokens': 400} for i in range(100)])
            # no correctness at all: d cannot be computed -> POWER_MISSING, the run stops (PREREG 7.3)
            pilot.write_pilot_report(run, correct_fn=lambda d_, w: {}, power_sims=1000)
            self.assertIn(json.loads((run / 'PILOT.json').read_text())['status'], ('POWER_MISSING', 'PILOT_NO_FEASIBLE_SR'))
            self.assertIsNone(json.loads((run / 'PILOT.json').read_text())['S'])
            p = pilot.write_pilot_report(run, correct_fn=lambda d_, w: {'t00': w == 'FLAT_A', 't01': True},
                                         power_sims=1000)
            text = p.read_text()
            self.assertIn('Status:', text)
            self.assertNotIn(chr(0x2014), text)
            res = json.loads((run / 'PILOT.json').read_text())
            self.assertIn(res['status'], ('OK', 'PILOT_NO_FEASIBLE_SR'))
            if res['status'] == 'OK':
                (run / 'RUN.json').write_text(json.dumps({'S': None, 'R': None}))
                out = pilot.apply_choice(run)
                self.assertEqual((out['S'], out['R']), (res['S'], res['R']))


if __name__ == '__main__':
    unittest.main()
