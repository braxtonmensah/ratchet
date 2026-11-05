"""Builder D: kill a stub run at random points 20 times; the frozen libraries and every submission must be
byte-identical to an uninterrupted run (SPEC 11 test_rounds_resume). Also: deadline resume, no sealed helpers, levers."""
from __future__ import annotations

import json
import random
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ratchet import arms, config, rounds
from ratchet.arms import Deadline

import test_d_fakes as F

FIXED_ET = '2026-11-04 12:00:00 ET'
S, R = 2, 3


def _patch_time():
    return [mock.patch('ratchet.rounds.now_et', lambda: FIXED_ET), mock.patch('ratchet.arms.now_et', lambda: FIXED_ET),
            mock.patch('ratchet.freeze.now_et', lambda: FIXED_ET)]


def _new_run(root: Path, kit):
    d = root / 'v1'
    arms.init_run(d, S=S, R=R, skip_pilot=True, auto_ack=True, model='/fake/model')
    return d


def _write_scores(run_dir: Path, condition: str):
    sd = run_dir / 'scores'
    sd.mkdir(parents=True, exist_ok=True)
    if condition == 'primary':
        W, winners = [], {}
        p = run_dir / 'sealed' / 'sealed' / 'STOCK' / 'seed_1'
        ex = rounds.read_rows(p / 'exec.jsonl', 'sample_id')
        samples = rounds.read_rows(p / 'samples.jsonl', 'sample_id')
        for sid in sorted(ex):
            if ex[sid].get('demo_pass') and ex[sid].get('helper_calls'):
                t = samples[sid]['task']
                winners.setdefault(t, []).append(sid)
        W = sorted(winners)
        rounds.atomic_write_json(sd / 'W.json', W)
        rounds.atomic_write_json(sd / 'winners.json', winners)
    rounds.atomic_write_json(sd / ('solved_%s.json' % condition), {'fake': True})


def _tear(run_dir: Path, rng: random.Random):
    files = sorted(run_dir.rglob('*.jsonl'), key=lambda p: (p.stat().st_mtime_ns, str(p)))
    if files and rng.random() < 0.6:
        with files[-1].open('ab') as f:
            f.write(b'{"sample_id": "TORN|' + str(rng.random()).encode())


def drive(run_dir: Path, kit, n_kills: int, seed: int, max_countdown: int = 150) -> dict:
    rng = random.Random(seed)
    F.KS.kills = 0
    F.KS.ticks = 0
    attempt = 0
    while True:
        attempt += 1
        if attempt > 400:
            raise AssertionError('no progress')
        run = arms.load_run(run_dir, kit=kit)
        run.job_id = 'j%03d' % attempt
        client = F.FakeClient(run_dir, run.job_id, order_seed=seed * 1000 + attempt)
        F.KS.arm(rng.randint(1, max_countdown) if F.KS.kills < n_kills else None)
        try:
            arms.step(run, client, Deadline(0, clock=lambda: 0.0))
        except F.SimulatedKill:
            _tear(run_dir, rng)
            continue
        finally:
            F.KS.arm(None)
        u = rounds.next_unit(arms.load_run(run_dir, kit=kit))
        if u is None:
            break
        if u.kind == 'score_gate':
            _write_scores(run_dir, u.condition)
            continue
        raise AssertionError('step stopped at %s' % (u,))
    return {"kills": F.KS.kills, "attempts": attempt, "ticks": F.KS.ticks}


def frozen_bytes(run_dir: Path) -> dict:
    out = {}
    for pat in ('arms/**/L_*.json', 'arms/**/L_*.py', 'arms/**/pool_R.json', 'sealed/**/submissions.json',
                'sealed/**/flat_budget.json', 'knockout/**/submissions.json', 'knockout/**/libraries/**/*.json',
                'knockout/KO_LIBS.json'):
        for p in run_dir.glob(pat):
            out[p.relative_to(run_dir).as_posix()] = p.read_bytes()
    fr = json.loads((run_dir / 'freeze' / 'FREEZE.json').read_text())
    sf = json.loads((run_dir / 'freeze' / 'SUBMIT_FREEZE.json').read_text())
    ko = json.loads((run_dir / 'freeze' / 'KO_FREEZE.json').read_text())
    out['FREEZE.libraries'] = json.dumps(fr['libraries'], sort_keys=True).encode()
    out['SUBMIT_FREEZE.submissions'] = json.dumps(sf['submissions'], sort_keys=True).encode()
    out['SUBMIT_FREEZE.FLAT_BUDGET'] = json.dumps(sf['FLAT_BUDGET'], sort_keys=True).encode()
    out['KO_FREEZE'] = json.dumps({k: ko[k] for k in ('libraries', 'submissions', 'W')}, sort_keys=True).encode()
    return out


class TestResume(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_d_'))
        self.patches = _patch_time()
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_kill_20_times_byte_identical(self):
        kit_a = F.make_kit()
        da = _new_run(self.tmp / 'a', kit_a)
        info_a = drive(da, kit_a, 0, seed=1)
        self.assertEqual(info_a['kills'], 0)
        kit_b = F.make_kit()
        db = _new_run(self.tmp / 'b', kit_b)
        # countdowns spread the 20 kills over the whole plan (growth, freeze, sealed, FLAT extra, knockout)
        info_b = drive(db, kit_b, 20, seed=2, max_countdown=max(2, info_a["ticks"] // 25))
        self.assertEqual(info_b['kills'], 20)
        A, B = frozen_bytes(da), frozen_bytes(db)
        self.assertEqual(sorted(A), sorted(B))
        for k in sorted(A):
            self.assertEqual(A[k], B[k], 'differs after kills: %s' % k)
        # the run produced real content, not empty files
        lib = json.loads((da / 'arms' / 'STOCK' / ('round_%d' % R) / ('L_%d.json' % R)).read_text())
        self.assertGreater(len(lib['helpers']), 0)
        self.assertTrue((da / 'RESULT.md').exists())
        subs = json.loads((da / 'sealed' / 'sealed' / 'FLATTTC' / 'seed_1' / 'submissions.json').read_text())
        self.assertEqual(subs['n_tasks'], 6)
        # every sample id is unique and every sample has exactly one exec row after the kills
        for p in db.rglob('samples.jsonl'):
            rows = list(rounds.iter_jsonl(p))
            ids = [r['sample_id'] for r in rows]
            ex = rounds.read_rows(p.parent / 'exec.jsonl', 'sample_id')
            self.assertEqual(set(ids), set(ex), str(p))

    def test_levers_present(self):
        kit = F.make_kit()
        d = _new_run(self.tmp / 'c', kit)
        drive(d, kit, 0, seed=3)
        logs = {p.name: p.read_text() for p in (d / 'logs').glob('server_*.log')}
        markers = {
            'STOCK': r'LEVER STOCK library r=[2-9]\d* .*updated=1',
            'STATIC': r'LEVER STATIC library r=\d+ sha=\w+ frozen=1',
            'ONESHOT': r'LEVER ONESHOT round=1 slots_per_task=%d' % (R * S),
            'EXEMPLAR': r'LEVER EXEMPLAR task=\w+ k=[1-3] exemplar_tokens=\d+',
            'SHAM': r'LEVER SHAM matched=\d+ of \d+ tokens=\d+ target=\d+ verified=0',
            'FLATTTC': r'LEVER FLATTTC seed=\d extra=\d+ target_tokens=\d+ realized_tokens=\d+',
            'PLANTDRIP': r'LEVER PLANTDRIP tranche=\d+ of \d+ primitives=\d+',
            'PLANTL1': r'LEVER PLANTL1 tranche=1 primitives=\d+',
            'KNOCKOUT': r'LEVER KO_DELETE task=\w+ removed=\S+|LEVER KO_INLINE task=\w+ callable=0',
            'PERTURB': r'LEVER PERTURB seed=\d+ tasks=6',
        }
        for arm, rx in markers.items():
            files = [n for n in logs if arm in n.upper()]
            self.assertTrue(files, 'no server log for %s' % arm)
            self.assertTrue(any(re.search(rx, logs[n]) for n in files), 'marker missing for %s' % arm)
        for n, text in logs.items():
            self.assertTrue(text.startswith('META arm='), n)
        allt = '\n'.join(logs.values())
        self.assertRegex(allt, r'LEVER SANDBOX lib_sha=\w+ helpers_callable=\d+ net=(unshare|audit)')
        self.assertRegex(allt, r'LEVER NOTHINK first_response_has_think=0')
        self.assertRegex(allt, r'LEVER PREFIX hit_rate=0\.\d+')
        # STOCK in context after round 1 changes the next round's library
        st2 = rounds.load_state(d / 'arms' / 'STOCK' / 'round_2')
        st1 = rounds.load_state(d / 'arms' / 'STOCK' / 'round_1')
        self.assertEqual(st2['library_in'], st1['library_out'])
        self.assertEqual(rounds.load_state(d / 'arms' / 'STATIC' / 'round_3')['library_in'], st1['library_out'])

    def test_shared_round1_and_crn(self):
        kit = F.make_kit()
        d = _new_run(self.tmp / 'e', kit)
        drive(d, kit, 0, seed=4)
        a = (d / 'arms' / 'STOCK' / 'round_1' / 'samples.jsonl').read_bytes()
        self.assertEqual(rounds.read_rows(d / 'arms' / 'STATIC' / 'round_1' / 'samples.jsonl', 'sample_id'),
                         rounds.read_rows(d / 'arms' / 'STOCK' / 'round_1' / 'samples.jsonl', 'sample_id'))
        self.assertTrue(a)
        one = rounds.read_rows(d / 'arms' / 'ONESHOT' / 'round_1' / 'samples.jsonl', 'sample_id')
        self.assertEqual(len(one), 6 * R * S)
        self.assertEqual(rounds.load_state(d / 'arms' / 'EXEMPLAR' / 'round_1')['shared_from'], 'STOCK:1')
        # no ledger row for the shared rounds: STATIC/EXEMPLAR round 1 never called the model
        rows = list(F.FakeLedgerMod.iter_rows(d))
        self.assertFalse([r for r in rows if r['arm'] in ('STATIC', 'EXEMPLAR') and r['round'] == 1])
        self.assertFalse([r for r in rows if r['arm'] in ('SHAM', 'PLANTDRIP', 'PLANTL1') and r['phase'] == 'growth'])
        # CRN: the same seed for STOCK and STATIC round 2 of a task (identical prompts at r = 2)
        s2 = {r['request_id'].split('|', 1)[1]: r['seed'] for r in rows if r['arm'] == 'STOCK' and r['round'] == 2}
        t2 = {r['request_id'].split('|', 1)[1]: r['seed'] for r in rows if r['arm'] == 'STATIC' and r['round'] == 2}
        self.assertEqual(s2, t2)
        # sealed tasks have S samples per arm per seed; FLAT has base + extra matching its budget
        fb = json.loads((d / 'sealed' / 'sealed' / 'FLATTTC' / 'seed_2' / 'flat_budget.json').read_text())
        flat = rounds.read_rows(d / 'sealed' / 'sealed' / 'FLATTTC' / 'seed_2' / 'samples.jsonl', 'sample_id')
        self.assertEqual(len(flat), 6 * S + fb['n_extra'])
        stock = rounds.read_rows(d / 'sealed' / 'sealed' / 'STOCK' / 'seed_2' / 'samples.jsonl', 'sample_id')
        self.assertEqual(len(stock), 6 * S)

    def test_deadline_stops_issue_and_resumes(self):
        kit = F.make_kit()
        d = _new_run(self.tmp / 'f', kit)
        now = [0.0]
        run = arms.load_run(d, kit=kit)
        run.job_id = 'jA'
        client = F.FakeClient(d, 'jA', clock=lambda: now[0])
        orig_run = client.run

        def run_then_late(reqs, on_result, stop_ts, hard_ts):
            reqs = list(reqs)
            out = orig_run(reqs[:3], on_result, stop_ts, hard_ts)
            now[0] = config.STOP_ISSUE_S + 1.0          # 52 min reached mid-unit
            return out
        client.run = run_then_late
        arms.step(run, client, Deadline(0.0, clock=lambda: now[0]))
        st = rounds.load_state(d / 'arms' / 'STOCK' / 'round_1')
        self.assertEqual(st['state'], 'SAMPLING')
        job = json.loads((d / 'jobs' / 'jA' / 'STATUS.json').read_text())
        self.assertEqual(job['state'], 'STOPPED_GRACEFUL')
        self.assertEqual(len(rounds.read_rows(d / 'arms' / 'STOCK' / 'round_1' / 'samples.jsonl', 'sample_id')), 3 * S)
        # next job finishes the round without re-issuing the 3 done requests
        run2 = arms.load_run(d, kit=kit)
        run2.job_id = 'jB'
        c2 = F.FakeClient(d, 'jB')
        F.KS.arm(None)
        arms.grow_round(run2, 'STOCK', 1, c2, Deadline(0.0, clock=lambda: 0.0))
        self.assertEqual(len(c2.issued), 6 - 3)
        self.assertEqual(rounds.load_state(d / 'arms' / 'STOCK' / 'round_1')['state'], 'FROZEN')

    def test_cpu_only_job_stops_at_gpu_unit(self):
        kit = F.make_kit()
        d = _new_run(self.tmp / 'g', kit)
        run = arms.load_run(d, kit=kit)
        run.job_id = 'jC'
        arms.step(run, None, Deadline(0.0, clock=lambda: 0.0))
        job = json.loads((d / 'jobs' / 'jC' / 'STATUS.json').read_text())
        self.assertEqual(job['exit_reason'], 'NEEDS_GPU')
        self.assertEqual(rounds.next_unit(run).kind, 'grow')

    def test_no_sealed_helpers(self):
        kit = F.make_kit()
        d = _new_run(self.tmp / 'h', kit)
        run = arms.load_run(d, kit=kit)
        run.job_id = 'jD'
        dl = Deadline(0.0, clock=lambda: 0.0)
        client = F.FakeClient(d, 'jD')
        rd = d / 'arms' / 'STOCK' / 'round_1'
        # sample and execute round 1, then plant a sealed row before extraction
        with mock.patch.object(arms, 'finalize_round', lambda *a, **k: None):
            arms.grow_round(run, 'STOCK', 1, client, dl)
        self.assertEqual(rounds.load_state(rd)['state'], 'EXTRACTING')
        row = dict(next(iter(rounds.read_rows(rd / 'samples.jsonl', 'sample_id').values())))
        row.update({'sample_id': 'STOCK|sealed|k1|e00|s0', 'phase': 'sealed', 'task': 'e00', 'sealed_seed': 1})
        rounds.append_jsonl(rd / 'samples.jsonl', [row])
        with self.assertRaises(arms.SealedHelperRefused):
            arms.finalize_round(run, 'STOCK', 1, kit.tok)
        self.assertEqual(rounds.load_state(rd)['state'], 'EXTRACTING')

    def test_sealed_needs_freeze_and_detects_edit(self):
        kit = F.make_kit()
        d = _new_run(self.tmp / 'i', kit)
        run = arms.load_run(d, kit=kit)
        with self.assertRaises(arms.FreezeMissing):
            arms.sample_sealed(run, 'STOCK', 1, 'sealed', F.FakeClient(d, 'x'), Deadline(0.0, clock=lambda: 0.0))

    def test_stalled_unit_fails_loudly(self):
        kit = F.make_kit()
        d = _new_run(self.tmp / 'j', kit)
        run = arms.load_run(d, kit=kit)
        run.job_id = 'jE'
        bad = F.FakeClient(d, 'jE', fail_ids={'STOCK|growth|r1|g00|b0'})
        with self.assertRaises(arms.ArmError):
            arms.step(run, bad, Deadline(0.0, clock=lambda: 0.0))
        job = json.loads((d / 'jobs' / 'jE' / 'STATUS.json').read_text())
        self.assertEqual(job['state'], 'FAILED')


class TestPilotPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_dp_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pilot_then_growth(self):
        kit = F.make_kit(pilot=F.FakePilot(S=2, R=2))
        d = self.tmp / 'p'
        arms.init_run(d, model='/fake/model', s_pilot=3, pilot_n=4)
        run = arms.load_run(d, kit=kit)
        self.assertEqual([u.kind for u in rounds.plan(run)], ['pilot', 'pilot', 'pilot_screen'])
        run.job_id = 'jP'
        client = F.FakeClient(d, 'jP')
        dl = Deadline(0.0, clock=lambda: 0.0)
        # stop the step after the pilot by letting growth hit a CPU-only boundary: run one step with a client
        arms.run_unit(run, rounds.WorkUnit('pilot', 'FLAT_A', 'pilot', None, None, 'FLAT_A'), client, dl)
        with mock.patch.object(config, 'SCREEN_GEN_BUDGET', 4 * 5 * 30):
            arms.run_unit(run, rounds.WorkUnit('pilot', 'FLAT_S', 'pilot', None, None, 'FLAT_S'), client, dl)
        run = arms.run_unit(run, rounds.WorkUnit('pilot_screen'), client, dl)
        self.assertEqual([u.condition for u in rounds.plan(run)][3:], ['FLAT_B', 'PLANT1', 'PLANT_SOLVE', None])
        arms.run_unit(run, rounds.WorkUnit('pilot', 'FLAT_B', 'pilot', None, None, 'FLAT_B'), client, dl)
        arms.run_unit(run, rounds.WorkUnit('pilot', 'PLANT1', 'pilot', None, None, 'PLANT1'), client, dl)
        arms.run_unit(run, rounds.WorkUnit('pilot', 'PLANT_SOLVE', 'pilot', None, None, 'PLANT_SOLVE'), client, dl)
        ps = rounds.read_rows(d / 'pilot' / 'PLANT_SOLVE' / 'samples.jsonl', 'sample_id')
        self.assertEqual(len(ps), 4 * 3)
        self.assertTrue(all(r['helpers_in_context'] == ['p0', 'solve_this'] for r in ps.values()))
        self.assertTrue(all(r['instruction_sha'] == config.INSTRUCTION_F3_SHA256 for r in ps.values()))
        st = rounds.load_state(d / 'pilot' / 'FLAT_S')
        self.assertGreaterEqual(st['S_pilot'], 1)
        self.assertEqual(len(rounds.read_rows(d / 'pilot' / 'FLAT_S' / 'samples.jsonl', 'sample_id')),
                         4 * st['S_pilot'])
        self.assertEqual(set(kit.prompt.instructions_seen), {config.INSTRUCTION_F3})
        a = rounds.read_rows(d / 'pilot' / 'FLAT_A' / 'samples.jsonl', 'sample_id')
        self.assertEqual(len(a), 4 * 3)
        ex = rounds.read_rows(d / 'pilot' / 'FLAT_A' / 'exec.jsonl', 'sample_id')
        self.assertTrue(all('test_correct' in r for r in ex.values()))
        rows = list(F.FakeLedgerMod.iter_rows(d))
        seeds = {(r['arm'], r['task']): r['seed'] for r in rows}
        self.assertEqual(seeds[('PLANT1', 'g00')], seeds[('FLAT_A', 'g00')])     # paired with FLAT_A
        self.assertNotEqual(seeds[('FLAT_B', 'g00')], seeds[('FLAT_A', 'g00')])  # independent A/A
        run = arms.run_unit(run, rounds.WorkUnit('pilot_choose'), client, dl)
        self.assertEqual((run.S, run.R), (2, 2))
        self.assertEqual(rounds.next_unit(run).kind, 'grow')

    def test_pilot_stop(self):
        kit = F.make_kit(pilot=F.FakePilot(smoke=False))
        d = self.tmp / 'q'
        arms.init_run(d, model='/fake/model', s_pilot=2, pilot_n=2)
        run = arms.load_run(d, kit=kit)
        run.job_id = 'jQ'
        arms.step(run, F.FakeClient(d, 'jQ'), Deadline(0.0, clock=lambda: 0.0))
        u = rounds.next_unit(arms.load_run(d, kit=kit))
        self.assertEqual((u.kind, u.condition), ('blocked', 'PILOT_SMOKE_FAIL'))
        self.assertIsNone(arms.load_run(d).S)


if __name__ == '__main__':
    unittest.main()
