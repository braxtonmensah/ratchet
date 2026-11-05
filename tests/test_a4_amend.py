"""AMENDMENT 4 (sec. 7.3 budget 12 -> 48 H100-hours): re-choose S, R from run v2's recorded PILOT.json, no re-sampling.

The fixture tests/fixtures/pilot_v2_PILOT.json is runs/v2/PILOT.json as written at 2026-11-05 00:08:55 ET
(sha256 a3b5988a7749b027d8edb09dd9f0edc170913ae4c62827eaf86aabcbe5b287f9).

Set RATCHET_A4_REAL_RUN to a COPY of runs/v2 (never the real tree) to also dry-run and apply on the real pilot files.
"""
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import ratchet  # noqa: F401
from ratchet import amend, cli, config, pilot, rounds

FIX = Path(__file__).resolve().parent / 'fixtures' / 'pilot_v2_PILOT.json'
FIX_SHA = 'a3b5988a7749b027d8edb09dd9f0edc170913ae4c62827eaf86aabcbe5b287f9'
A4_TEXT = Path(__file__).resolve().parent / 'fixtures' / 'amendment_4_block.txt'

PREREG_HEAD = """# PREREG test copy

## 7. Pilot
3. ... fit 12 H100-hours at the measured rate ...

## AMENDMENTS
- AMENDMENT 0 (2026-11-04 16:47 ET, before any model call): registered.
- AMENDMENT 3 (2026-11-04 23:20 ET, same conditions): section 7.2 gate.
"""
A4 = """- AMENDMENT 4 (2026-11-05 01:30 ET, after pilot v2 read PILOT_NO_FEASIBLE_SR, before any growth job): section 7.3
  budget. The 12 H100-hours of section 7.3 become 48
  H100-hours for every arm. S = 4, R = 4 at 41 jobs. Grants no key access.
"""


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def make_run(root: Path) -> Path:
    run = root / 'v2'
    (run / 'pilot').mkdir(parents=True)
    shutil.copy(FIX, run / 'PILOT.json')
    (run / 'PILOT.md').write_text('# PILOT (PREREG 7)\nold\n')
    (run / 'RUN.json').write_text(json.dumps({'schema': config.RUN_SCHEMA, 'name': 'v2', 'S': None, 'R': None,
                                              'seed_base': 1000, 'instruction': 'V1',
                                              'instruction_sha': config.INSTRUCTION_SHAS['V1']}))
    (run / 'pilot' / 'PILOT_CHOICE.json').write_text(json.dumps({'status': 'PILOT_NO_FEASIBLE_SR',
                                                                 'created_et': '2026-11-05 00:08:55 ET'}))
    (run / 'pilot' / 'PILOT_STOP.json').write_text(json.dumps({'reason': 'PILOT_NO_FEASIBLE_SR',
                                                               'created_et': '2026-11-05 00:08:55 ET'}))
    (run / 'pilot' / 'SCREEN.json').write_text(json.dumps({'decision': 'V1'}))
    for w in ('FLAT_A', config.PILOT_SCREEN) + tuple(config.PILOT_AFTER_SCREEN['V1']):
        (run / 'pilot' / w).mkdir()
        (run / 'pilot' / w / 'round_state.json').write_text(json.dumps({'state': 'DONE'}))
    (run / 'ledger').mkdir()
    (run / 'ledger' / 'ledger_1.jsonl').write_text(json.dumps({'request_id': 'p1', 'phase': 'pilot'}) + '\n')
    return run


def make_prereg(root: Path, block: str | None = A4, name: str = 'PREREG.md') -> Path:
    p = root / name
    p.write_text(PREREG_HEAD + (block or ''), encoding='utf-8')
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run = make_run(self.root)
        self.prereg = make_prereg(self.root)
        self.pil = json.loads(FIX.read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self):
        return {str(p.relative_to(self.run)): sha(p) for p in sorted(self.run.rglob('*')) if p.is_file()}


class TestFixture(Base):
    def test_fixture_is_the_v2_pilot(self):
        self.assertEqual(sha(FIX), FIX_SHA)
        self.assertEqual(self.pil['status'], 'PILOT_NO_FEASIBLE_SR')
        self.assertEqual((self.pil['smoke']['kA'], self.pil['smoke']['kB']), (22, 22))
        self.assertEqual((self.pil['plant']['k_plant_solve'], self.pil['plant']['k_flat_a']), (49, 22))
        self.assertAlmostEqual(self.pil['rates']['g'], 3607.9, places=1)
        self.assertEqual(self.pil['rates']['d'], 0.14)


class TestRechoose(Base):
    def test_picks_S4_R4_at_48(self):
        c = amend.rechoose(self.pil, 48)
        self.assertEqual(c['status'], 'OK')
        self.assertEqual((c['S'], c['R']), (4, 4))
        self.assertEqual(c['chosen']['jobs'], 41)
        self.assertEqual(c['n_feasible'], 1)
        self.assertEqual(c['budget_h100_hours'], 48.0)
        self.assertAlmostEqual(c['power'], 0.83181, places=5)
        self.assertFalse(c['underpowered'])
        jobs = {(g['S'], g['R']): g['jobs'] for g in c['grid']}
        self.assertEqual(jobs[(4, 6)], 55)
        self.assertEqual(jobs[(8, 4)], 82)

    def test_infeasible_at_12_as_registered(self):
        c = amend.rechoose(self.pil, 12)
        self.assertEqual(c['status'], 'PILOT_NO_FEASIBLE_SR')
        self.assertEqual(c['n_feasible'], 0)
        # the registered default is still 12
        self.assertEqual(pilot.choose_SR(self.pil['rates'], power=0.83181)['status'], 'PILOT_NO_FEASIBLE_SR')
        self.assertEqual(pilot.budget_hours(self.run), 12.0)

    def test_rule_unchanged_larger_budget_takes_larger_cell(self):
        c = amend.rechoose(self.pil, 60)
        self.assertEqual((c['S'], c['R']), (4, 6))   # S x R = 24 beats 16; S 8 R 4 needs 82

    def test_projection_drift_refused(self):
        bad = json.loads(FIX.read_text())
        bad['choice']['grid'][0]['jobs'] = 40
        with self.assertRaisesRegex(amend.AmendRefused, 'PROJECTION_DRIFT'):
            amend.rechoose(bad, 48)


class TestApply(Base):
    def test_apply_at_48(self):
        before = {k: sha(self.run / k) for k in ('PILOT.json', 'PILOT.md', 'pilot/PILOT_CHOICE.json',
                                                 'pilot/PILOT_STOP.json')}
        r0 = rounds.next_unit(self._load())
        self.assertEqual((r0.kind, r0.condition), ('blocked', 'PILOT_NO_FEASIBLE_SR'))
        res = amend.apply_budget_amendment(self.run, '4', 48, self.prereg)
        self.assertEqual((res['S'], res['R']), (4, 4))
        run = json.loads((self.run / 'RUN.json').read_text())
        self.assertEqual((run['S'], run['R'], run['h100_hours_budget']), (4, 4, 48.0))
        rec = run['budget_amendment']
        self.assertEqual(rec['id'], '4')
        self.assertEqual(rec['prereg_block_sha256'],
                         hashlib.sha256(amend.prereg_block(self.prereg, '4').encode('utf-8')).hexdigest())
        self.assertEqual(rec['pilot_json_sha256_before'], FIX_SHA)
        self.assertEqual(json.loads((self.run / 'AMENDMENTS.json').read_text())['amendments'][0]['id'], '4')
        # archived, never deleted: the old bytes survive under the A4 names
        self.assertFalse((self.run / 'pilot/PILOT_STOP.json').exists())
        self.assertEqual(sha(self.run / 'pilot/PILOT_STOP.superseded_A4.json'), before['pilot/PILOT_STOP.json'])
        self.assertEqual(sha(self.run / 'PILOT.pre_A4.json'), before['PILOT.json'])
        self.assertEqual(sha(self.run / 'PILOT.pre_A4.md'), before['PILOT.md'])
        self.assertEqual(sha(self.run / 'pilot/PILOT_CHOICE.pre_A4.json'), before['pilot/PILOT_CHOICE.json'])
        for w in ('FLAT_A', 'V1_FLAT_A', 'V1_PLANT_SOLVE'):
            self.assertTrue((self.run / 'pilot' / w / 'round_state.json').exists())
        new = json.loads((self.run / 'PILOT.json').read_text())
        self.assertEqual((new['status'], new['S'], new['R']), ('OK', 4, 4))
        self.assertEqual(new['rates'], self.pil['rates'])
        ch = json.loads((self.run / 'pilot/PILOT_CHOICE.json').read_text())
        self.assertEqual((ch['choice']['S'], ch['choice']['R'], ch['budget_amendment']['id']), (4, 4, '4'))
        md = (self.run / 'PILOT.md').read_text()
        self.assertIn('Budget: 48 H100-hours (AMENDMENT 4', md)
        self.assertIn('Choice: S = 4, R = 4 (OK).', md)
        self.assertEqual(pilot.budget_hours(self.run), 48.0)
        # the chain resumes at growth
        u = rounds.next_unit(self._load())
        self.assertEqual((u.kind, u.arm, u.round), ('grow', 'STOCK', 1))

    def _load(self):
        from ratchet import arms
        return arms.load_run(self.run)

    def test_refuses_at_12(self):
        pre = make_prereg(self.root, A4.replace('become 48\n  H100-hours', 'stay 12\n  H100-hours'), 'p_12.md')
        snap = self.snapshot()
        with self.assertRaisesRegex(amend.AmendRefused, 'STILL_INFEASIBLE'):
            amend.apply_budget_amendment(self.run, '4', 12, pre)
        self.assertEqual(self.snapshot(), snap)

    def test_refuses_after_growth_started(self):
        for kind in ('arms', 'ledger'):
            with self.subTest(kind=kind):
                if kind == 'arms':
                    p = self.run / 'arms' / 'STOCK' / 'round_1'
                    p.mkdir(parents=True)
                    (p / 'round_state.json').write_text(json.dumps({'state': 'SAMPLING'}))
                else:
                    shutil.rmtree(self.run / 'arms')
                    with open(self.run / 'ledger' / 'ledger_2.jsonl', 'w') as f:
                        f.write(json.dumps({'request_id': 'g1', 'phase': 'growth'}) + '\n')
                snap = self.snapshot()
                with self.assertRaisesRegex(amend.AmendRefused, 'GROWTH_STARTED'):
                    amend.apply_budget_amendment(self.run, '4', 48, self.prereg)
                self.assertEqual(self.snapshot(), snap)

    def test_refuses_sealed_or_freeze_dirs(self):
        (self.run / 'freeze').mkdir()
        (self.run / 'freeze' / 'FREEZE.json').write_text('{}')
        with self.assertRaisesRegex(amend.AmendRefused, 'GROWTH_STARTED freeze/'):
            amend.apply_budget_amendment(self.run, '4', 48, self.prereg)

    def test_amendment_must_exist_in_prereg(self):
        snap = self.snapshot()
        for pre, msg in ((make_prereg(self.root, None, 'p_none.md'), 'AMENDMENT_NOT_IN_PREREG'),
                         (make_prereg(self.root, A4.replace('01:30', 'HH:MM'), 'p_hhmm.md'),
                          'AMENDMENT_TIME_PLACEHOLDER'),
                         (make_prereg(self.root, A4.replace('become 48', 'become 40'), 'p_40.md'),
                          'AMENDMENT_BUDGET_NOT_STATED')):
            with self.subTest(msg=msg):
                with self.assertRaisesRegex(amend.AmendRefused, msg):
                    amend.apply_budget_amendment(self.run, '4', 48, pre)
        with self.assertRaisesRegex(amend.AmendRefused, 'AMENDMENT_NOT_IN_PREREG'):
            amend.apply_budget_amendment(self.run, '5', 48, self.prereg)
        # a body line that merely mentions "AMENDMENT 4" outside an item head does not count
        pre = make_prereg(self.root, '- AMENDMENT 5 (x): see AMENDMENT 4 (later), 48 H100-hours.\n', 'p_mention.md')
        with self.assertRaisesRegex(amend.AmendRefused, 'AMENDMENT_NOT_IN_PREREG'):
            amend.apply_budget_amendment(self.run, '4', 48, pre)
        self.assertEqual(self.snapshot(), snap)

    def test_block_ends_at_next_item(self):
        pre = make_prereg(self.root, A4 + '- AMENDMENT 5 (2026-11-06 10:00 ET): other.\n', 'p_next.md')
        b = amend.prereg_block(pre, '4')
        self.assertTrue(b.startswith('- AMENDMENT 4 ('))
        self.assertNotIn('AMENDMENT 5', b)
        self.assertEqual(b, amend.prereg_block(self.prereg, '4'))

    def test_refuses_second_application(self):
        amend.apply_budget_amendment(self.run, '4', 48, self.prereg)
        with self.assertRaisesRegex(amend.AmendRefused, 'GROWTH_STARTED|RUN_SR_ALREADY_SET|BUDGET_ALREADY'):
            amend.apply_budget_amendment(self.run, '4', 48, self.prereg)

    def test_refuses_other_stop_reason(self):
        (self.run / 'pilot' / 'PILOT_STOP.json').write_text(json.dumps({'reason': 'PILOT_PLANT_FAIL'}))
        with self.assertRaisesRegex(amend.AmendRefused, 'PILOT_STOP_REASON'):
            amend.apply_budget_amendment(self.run, '4', 48, self.prereg)

    def test_dry_run_writes_nothing(self):
        snap = self.snapshot()
        res = amend.apply_budget_amendment(self.run, '4', 48, self.prereg, dry_run=True)
        self.assertTrue(res['dry_run'])
        self.assertEqual((res['record']['S'], res['record']['R'], res['record']['jobs']), (4, 4, 41))
        self.assertEqual(self.snapshot(), snap)

    def test_budget_without_record_refused(self):
        d = json.loads((self.run / 'RUN.json').read_text())
        d['h100_hours_budget'] = 48
        (self.run / 'RUN.json').write_text(json.dumps(d))
        with self.assertRaisesRegex(RuntimeError, 'BUDGET_WITHOUT_AMENDMENT'):
            pilot.budget_hours(self.run)

    def test_append_ready_text(self):
        """The append-ready AMENDMENT 4 text (BUILD_A4.md): refused while it still says HH:MM, applies once filled."""
        raw = A4_TEXT.read_text(encoding='utf-8')
        self.assertIn('HH:MM', raw)
        with self.assertRaisesRegex(amend.AmendRefused, 'AMENDMENT_TIME_PLACEHOLDER'):
            amend.apply_budget_amendment(self.run, '4', 48, make_prereg(self.root, raw, 'p_raw.md'))
        pre = make_prereg(self.root, raw.replace('HH:MM', '01:45'), 'p_filled.md')
        want = '\n'.join(ln.rstrip() for ln in raw.replace('HH:MM', '01:45').splitlines())
        self.assertEqual(amend.prereg_block(pre, '4'), want)
        res = amend.apply_budget_amendment(self.run, '4', 48, pre)
        self.assertEqual((res['S'], res['R'], res['record']['jobs']), (4, 4, 41))

    def test_cli(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(['amend-budget', '--run', str(self.run), '--amendment', '4', '--budget', '12',
                           '--prereg', str(self.prereg)])
        self.assertEqual(rc, 3)
        self.assertIn('AMEND_REFUSED', buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli.main(['amend-budget', '--run', str(self.run), '--amendment', '4', '--budget', '48',
                           '--prereg', str(self.prereg)])
        self.assertEqual(rc, 0)
        self.assertIn('AMEND_APPLIED A4 budget=48 S=4 R=4', buf.getvalue())


@unittest.skipUnless(os.environ.get('RATCHET_A4_REAL_RUN'), 'RATCHET_A4_REAL_RUN (a copy of runs/v2) not set')
class TestRealCopy(unittest.TestCase):
    """On a scratch COPY of runs/v2: dry-run, apply, and the chain resumes at growth."""

    def test_real_copy(self):
        run = Path(os.environ['RATCHET_A4_REAL_RUN'])
        real = os.path.realpath(str(config.REAL_RUNS_DIR))
        self.assertFalse(os.path.realpath(str(run)).startswith(real), 'must be a copy, not the real runs tree')
        self.assertEqual(sha(run / 'PILOT.json'), FIX_SHA)
        with tempfile.TemporaryDirectory() as t:
            pre = Path(t) / 'PREREG.md'
            block = A4_TEXT.read_text(encoding='utf-8').replace('HH:MM', '01:45')
            pre.write_text((config.REPO_DIR / 'PREREG.md').read_text(encoding='utf-8').rstrip('\n') + '\n' + block,
                           encoding='utf-8')
            dry = amend.apply_budget_amendment(run, '4', 48, pre, dry_run=True)
            self.assertEqual((dry['record']['S'], dry['record']['R'], dry['record']['jobs']), (4, 4, 41))
            res = amend.apply_budget_amendment(run, '4', 48, pre)
        self.assertEqual((res['S'], res['R']), (4, 4))
        from ratchet import arms
        u = rounds.next_unit(arms.load_run(run))
        self.assertEqual((u.kind, u.arm, u.round), ('grow', 'STOCK', 1))


if __name__ == '__main__':
    unittest.main()
