"""Builder D: freeze refusals, write-once, ack; CLI parser and `next`."""
from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ratchet import arms, cli, freeze, rounds
from ratchet.arms import Deadline

import test_d_fakes as F


class TestFreeze(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_df_'))
        self.kit = F.make_kit()
        self.d = self.tmp / 'v1'
        arms.init_run(self.d, S=2, R=2, skip_pilot=True, model='/fake/model')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _grow_all(self):
        run = arms.load_run(self.d, kit=self.kit)
        run.job_id = 'jF'
        arms.step(run, F.FakeClient(self.d, 'jF'), Deadline(0.0, clock=lambda: 0.0))
        return arms.load_run(self.d, kit=self.kit)

    def test_refuses_before_growth(self):
        run = arms.load_run(self.d, kit=self.kit)
        with self.assertRaises(freeze.FreezeRefused):
            freeze.freeze_libraries(run)
        with self.assertRaises(freeze.FreezeRefused):
            freeze.freeze_submissions(run)

    def test_freeze_gate_ack_and_edit_detection(self):
        run = self._grow_all()
        u = rounds.next_unit(run)
        self.assertEqual((u.kind, u.condition), ('lead_gate', 'FREEZE'))   # step stopped at the lead gate
        fr = json.loads((self.d / 'freeze' / 'FREEZE.json').read_text())
        self.assertIsNone(fr['libraries']['FLATTTC'])
        self.assertEqual(fr['libraries']['STATIC']['json'], fr['libraries']['STOCK']['json'].replace('round_2', 'round_1')
                         .replace('L_2', 'L_1'))
        sha = (self.d / 'freeze' / 'FREEZE.sha256').read_text().split()[0]
        p, sha2 = freeze.freeze_libraries(run)                 # idempotent
        self.assertEqual(sha, sha2)
        with self.assertRaises(freeze.FreezeRefused):
            freeze.ack(run, 'FREEZE', '0' * 64)
        freeze.ack(run, 'FREEZE', sha)
        self.assertTrue(rounds.gate_acked(run, 'FREEZE'))
        self.assertEqual(rounds.next_unit(run).kind, 'sealed')
        # a library edited after the freeze is caught before sealed sampling
        lib = self.d / fr['libraries']['SHAM']['json']
        lib.write_text(lib.read_text().replace('"round"', '"round" ', 1))
        with self.assertRaises(arms.ArmError):
            arms.frozen_library(arms.load_run(self.d, kit=self.kit), 'SHAM')
        with self.assertRaises(freeze.FreezeRefused):
            freeze.verify_freeze(run)

    def test_conflict_never_overwrites(self):
        run = self._grow_all()
        st = rounds.load_state(self.d / 'arms' / 'SHAM')
        st['library_json'] = rounds.load_state(self.d / 'arms' / 'PLANTL1')['library_json']
        rounds.save_state(self.d / 'arms' / 'SHAM', st)
        with self.assertRaises(freeze.FreezeConflict):
            freeze.freeze_libraries(run)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_dc_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parser_has_every_command(self):
        p = cli.build_parser()
        for argv in (['init', '--run', 'x'], ['pilot', '--run', 'x', '--step', 'choose'], ['grow', '--run', 'x', '--arm',
                     'STOCK', '--round', '2'], ['step', '--run', 'x'], ['perturb', '--run', 'x', '--build'],
                     ['freeze', '--run', 'x', '--submissions'], ['freeze', '--run', 'x', '--ack', 'ab', '--name', 'FREEZE'],
                     ['sample-sealed', '--run', 'x', '--arm', 'FLATTTC', '--seed', '1', '--condition', 'perturbed'],
                     ['score', '--run', 'x', '--condition', 'primary', '--freeze-sha', 'a', '--submit-sha', 'b'],
                     ['knockout', '--run', 'x', '--build'], ['status', '--run', 'x', '--map'], ['verdict', '--run', 'x'],
                     ['next', '--run', 'x']):
            self.assertTrue(p.parse_args(argv).fn)

    def test_init_and_next(self):
        d = self.tmp / 'v1'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['init', '--run', str(d)]), 0)
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(['next', '--run', str(d)])
        out = json.loads(buf.getvalue())
        self.assertEqual(out['next']['kind'], 'pilot')
        self.assertTrue(out['gpu'] and out['chain'])
        # two failed jobs in a row stop the chain
        rounds.atomic_write_json(d / 'STATUS.json', {'jobs': [{'job_id': '1', 'state': 'FAILED'},
                                                              {'job_id': '2', 'state': 'FAILED'}]})
        self.assertFalse(cli.chain_ok(arms.load_run(d))['chain'])

    def test_score_execs_score_sealed(self):
        with mock.patch('os.execv') as ex:
            cli.main(['score', '--run', '/r', '--condition', 'primary', '--freeze-sha', 'a', '--submit-sha', 'b'])
        exe, argv = ex.call_args[0]
        self.assertTrue(argv[1].endswith('score_sealed.py'))
        self.assertEqual(argv[2:], ['score', '--run', '/r', '--condition', 'primary', '--freeze-sha', 'a',
                                    '--submit-sha', 'b'])


if __name__ == '__main__':
    unittest.main()
