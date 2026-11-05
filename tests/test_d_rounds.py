"""Builder D: atomic state, torn-tail jsonl, PLAN order, seeds, deadline, config hygiene."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ratchet import arms, config, rounds
from ratchet.arms import Deadline, Run


def mkrun(d, S=4, R=4, **cfg):
    return Run(dir=Path(d), S=S, R=R, seed_base=1000, cfg=cfg)


class TestFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_dr_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_torn_tail(self):
        p = self.tmp / 'x.jsonl'
        rounds.append_jsonl(p, [{'sample_id': 'a'}, {'sample_id': 'b'}])
        with p.open('ab') as f:
            f.write(b'{"sample_id": "c", "te')
        self.assertEqual(rounds.done_ids(p, 'sample_id'), {'a', 'b'})
        self.assertGreater(rounds.repair_jsonl(p), 0)
        rounds.append_jsonl(p, [{'sample_id': 'c'}])
        self.assertEqual(rounds.done_ids(p, 'sample_id'), {'a', 'b', 'c'})
        self.assertEqual(rounds.repair_jsonl(p), 0)

    def test_corrupt_middle_line_raises(self):
        p = self.tmp / 'y.jsonl'
        p.write_bytes(b'{"sample_id": "a"}\nGARBAGE\n{"sample_id": "b"}\n')
        with self.assertRaises(ValueError):
            rounds.done_ids(p, 'sample_id')

    def test_last_row_wins(self):
        p = self.tmp / 'z.jsonl'
        rounds.append_jsonl(p, [{'sample_id': 'a', 'v': 1}, {'sample_id': 'a', 'v': 2}])
        self.assertEqual(rounds.read_rows(p, 'sample_id')['a']['v'], 2)

    def test_atomic_state(self):
        d = self.tmp / 'r'
        rounds.save_state(d, {'state': 'SAMPLING', 'arm': 'STOCK'})
        st = rounds.load_state(d)
        self.assertEqual(st['state'], 'SAMPLING')
        self.assertEqual(st['schema'], config.ROUND_SCHEMA)
        self.assertEqual([p.name for p in d.iterdir()], ['round_state.json'])   # no temp file left behind
        self.assertEqual(rounds.load_state(self.tmp / 'missing'), {})


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_dp_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_SR_plans_pilot_only(self):
        run = mkrun(self.tmp, S=None, R=None)
        # pilot v2: FLAT_A, the screen FLAT_S, the decision; the rest is planned once pilot/SCREEN.json exists
        self.assertEqual([(u.kind, u.condition) for u in rounds.plan(run)],
                         [('pilot', 'FLAT_A'), ('pilot', 'FLAT_S'), ('pilot_screen', None)])
        (self.tmp / 'pilot').mkdir(parents=True, exist_ok=True)
        (self.tmp / 'pilot' / 'SCREEN.json').write_text(json.dumps({'decision': 'V1'}))
        self.assertEqual([u.condition for u in rounds.plan(run)][3:],
                         ['V1_FLAT_A', 'V1_FLAT_B', 'V1_PLANT1', 'V1_PLANT_SOLVE', None])
        (self.tmp / 'pilot' / 'SCREEN.json').write_text(json.dumps({'decision': 'F3'}))
        self.assertEqual([u.condition for u in rounds.plan(run)][3:], ['FLAT_B', 'PLANT1', 'PLANT_SOLVE', None])
        (self.tmp / 'pilot' / 'SCREEN.json').write_text(json.dumps({'decision': 'BOTH'}))
        with self.assertRaises(ValueError):
            rounds.plan(run)

    def test_order(self):
        run = mkrun(self.tmp, S=4, R=4, skip_pilot=True)
        p = rounds.plan(run)
        keys = [u.key() for u in p]
        self.assertEqual(len(keys), len(set(keys)))
        idx = {u.key(): i for i, u in enumerate(p)}

        def at(kind, arm=None, phase=None, rnd=None, seed=None, cond=None):
            return idx[rounds.WorkUnit(kind, arm, phase, rnd, seed, cond).key()]
        self.assertLess(at('grow', 'STOCK', 'growth', 1), at('grow', 'STATIC', 'growth', 1))
        self.assertLess(at('grow', 'STOCK', 'growth', 4), at('grow', 'EXEMPLAR', 'growth', 2))
        self.assertLess(at('grow', 'EXEMPLAR', 'growth', 4), at('grow', 'ONESHOT', 'growth', 1))
        self.assertLess(at('build_sham', 'SHAM'), at('grow', 'STATIC', 'growth', 2))
        self.assertLess(at('grow', 'STATIC', 'growth', 4), at('freeze_libraries'))
        self.assertLess(at('freeze_libraries'), at('lead_gate', cond='FREEZE'))
        self.assertLess(at('lead_gate', cond='FREEZE'), at('sealed', 'STOCK', 'sealed', None, 1, 'sealed'))
        self.assertLess(at('sealed', 'STOCK', 'sealed', None, 1, 'sealed'),
                        at('flat_extra', 'FLATTTC', 'sealed', None, 1, 'sealed'))
        self.assertLess(at('flat_extra', 'FLATTTC', 'sealed', None, 3, 'sealed'), at('perturb_build'))
        self.assertLess(at('flat_extra', 'FLATTTC', 'perturbed', None, 3, 'perturbed'), at('freeze_submissions'))
        self.assertLess(at('lead_gate', cond='SUBMIT_FREEZE'), at('score_gate', cond='primary'))
        self.assertLess(at('score_gate', cond='primary'), at('knockout_build'))
        self.assertLess(at('freeze_knockout'), at('score_gate', cond='knockout'))
        self.assertEqual(p[-1].kind, 'verdict')
        sealed = [u for u in p if u.kind == 'sealed' and u.condition == 'sealed']
        self.assertEqual(len(sealed), 3 * 8)
        self.assertFalse([u for u in p if u.kind == 'grow' and u.arm in ('SHAM', 'FLATTTC', 'PLANTDRIP', 'PLANTL1')])
        self.assertFalse([u for u in p if 'arcagi2' in u.key()])   # outside the 12 h (SPEC 13 I16)

    def test_gpu_and_manual_flags(self):
        self.assertTrue(rounds.WorkUnit('grow', 'STOCK', 'growth', 1).gpu)
        self.assertFalse(rounds.WorkUnit('grow', 'STATIC', 'growth', 1).gpu)
        self.assertTrue(rounds.WorkUnit('grow', 'STATIC', 'growth', 2).gpu)
        self.assertFalse(rounds.WorkUnit('freeze_libraries').gpu)
        self.assertTrue(rounds.WorkUnit('lead_gate', condition='FREEZE').manual)

    def test_gate_ack(self):
        run = mkrun(self.tmp, skip_pilot=True)
        fd = self.tmp / 'freeze'
        fd.mkdir()
        (fd / 'FREEZE.sha256').write_text('abc  FREEZE.json\n')
        self.assertFalse(rounds.gate_acked(run, 'FREEZE'))
        (fd / 'FREEZE.ack').write_text('abd  2026\n')
        self.assertFalse(rounds.gate_acked(run, 'FREEZE'))
        (fd / 'FREEZE.ack').write_text('abc  2026\n')
        self.assertTrue(rounds.gate_acked(run, 'FREEZE'))

    def test_next_unit_blocked_by_pilot_stop(self):
        run = mkrun(self.tmp, S=None, R=None)
        (self.tmp / 'pilot').mkdir()
        (self.tmp / 'pilot' / 'PILOT_STOP.json').write_text(json.dumps({'reason': 'PILOT_NO_FEASIBLE_SR'}))
        u = rounds.next_unit(run)
        self.assertEqual((u.kind, u.condition), ('blocked', 'PILOT_NO_FEASIBLE_SR'))
        self.assertTrue(u.manual)


class TestSeedsDeadline(unittest.TestCase):
    def test_seed_excludes_arm_and_is_stable(self):
        run = mkrun('/x')
        a = arms.seed_for(run, 'growth', 2, '007bbfb7', 0, None)
        self.assertEqual(a, arms.seed_for(mkrun('/y'), 'growth', 2, '007bbfb7', 0, None))
        self.assertNotEqual(a, arms.seed_for(run, 'growth', 3, '007bbfb7', 0, None))
        self.assertNotEqual(a, arms.seed_for(run, 'growth', 2, '007bbfb7', 4, None))
        self.assertNotEqual(arms.seed_for(run, 'sealed', None, 't', 0, 1), arms.seed_for(run, 'sealed', None, 't', 0, 2))
        self.assertTrue(0 <= a < 2 ** 32)
        r2 = Run(dir=Path('/x'), S=4, R=4, seed_base=1001, cfg={})
        self.assertNotEqual(a, arms.seed_for(r2, 'growth', 2, '007bbfb7', 0, None))

    def test_deadline(self):
        t = [100.0]
        dl = Deadline(100.0, clock=lambda: t[0])
        self.assertTrue(dl.issue_ok())
        t[0] = 100.0 + config.STOP_ISSUE_S
        self.assertFalse(dl.issue_ok())
        self.assertFalse(dl.hard())
        t[0] = 100.0 + config.HARD_STOP_S
        self.assertTrue(dl.hard())
        self.assertEqual((config.STOP_ISSUE_S, config.HARD_STOP_S), (3120, 3300))


class TestConfigHygiene(unittest.TestCase):
    def test_d_files_never_name_the_key(self):
        root = Path(__file__).resolve().parent.parent
        for name in ('config.py', 'rounds.py', 'arms.py', 'budget.py', 'freeze.py', 'cli.py', '__main__.py'):
            text = (root / 'ratchet' / name).read_text(encoding='utf-8')
            self.assertNotIn('key/', text, name)
            self.assertNotIn('KEY_ROOT', text, name)
            self.assertNotIn('—', text, name)     # no em dashes

    def test_registered_constants(self):
        self.assertEqual((config.TEMPERATURE, config.TOP_P, config.MAX_TOKENS), (0.8, 0.95, 4096))
        self.assertEqual(config.LIBRARY_CAP_TOKENS, 6000)
        self.assertEqual((config.ACCEPT_MIN_TASKS, config.ACCEPT_MIN_MDL), (2, 20))
        self.assertEqual(config.SEALED_SEEDS, (1, 2, 3))
        self.assertEqual((config.S_GRID, config.R_GRID), ((4, 8, 16), (4, 6, 8)))
        self.assertEqual(config.GROWTH_IDS_SHA256, 'c4e1b145daad71b4f02ac3482be215f1ab07863b67f13fc1bde1572f501ff75a')
        self.assertEqual(config.SEALED_IDS_SHA256, '911bf838d8843606d5fc1ba0550a0c23670027bf8f6e32e4e4fbf93854957ddd')
        self.assertEqual(len(config.LIBRARY_ARMS), 7)


if __name__ == '__main__':
    unittest.main()
