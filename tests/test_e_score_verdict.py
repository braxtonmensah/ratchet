"""Builder E: score_sealed.py refusals and one full stub scoring pass (SPEC 8 tests 7 and 10), verdict precedence."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import ratchet  # noqa: F401
from ratchet import verdict

import _e_support as S


class ScoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.key, self.data = S.make_key(self.root)
        f = S.make_run(self.root)
        self.run, self.fsha, self.ssha = f['run'], f['freeze_sha'], f['submit_sha']

    def tearDown(self):
        self.tmp.cleanup()

    def score(self, condition='primary', fsha=None, ssha=None):
        return S.run_score(['score', '--run', str(self.run), '--condition', condition,
                            '--freeze-sha', fsha or self.fsha, '--submit-sha', ssha or self.ssha], self.key)

    def reads(self):
        p = self.run / 'scores' / 'KEY_READS.jsonl'
        return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []

    def refused(self, r, code):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(code, r.stderr)
        self.assertEqual(self.reads(), [])
        self.assertFalse((self.run / 'scores' / 'solved_primary.json').exists())


class TestScoreRefusals(ScoreCase):
    def test7a_missing_freeze(self):
        os.remove(self.run / 'freeze' / 'FREEZE.json')
        self.refused(self.score(), 'MISSING_FREEZE')

    def test7b_sha_mismatch(self):
        self.refused(self.score(fsha='0' * 64), 'FREEZE_SHA_MISMATCH')
        self.refused(self.score(ssha='0' * 64), 'SUBMIT_SHA_MISMATCH')

    def test7c_library_edited_after_freeze(self):
        p = self.run / 'arms/STOCK/round_2/L_2.json'
        p.write_text(p.read_text().replace('"h2"', '"h3"'))
        self.refused(self.score(), 'FROZEN_FILE_CHANGED')

    def test7c2_submission_edited_or_unlisted(self):
        p = self.run / 'sealed/sealed/FLATTTC/seed_1/submissions.json'
        p.write_text(p.read_text() + ' ')
        self.refused(self.score(), 'FROZEN_FILE_CHANGED')

    def test7c3_unlisted_submission(self):
        extra = self.run / 'sealed/sealed/NEWARM/seed_1/submissions.json'
        S.write_json(extra, {'submissions': []})
        self.refused(self.score(), 'UNLISTED_SUBMISSION')

    def test7d_key_mode_not_000(self):
        os.chmod(self.key / 'arcagi1' / 'e3.json', 0o400)
        self.refused(self.score(), 'KEY_EXPOSED')
        os.chmod(self.key / 'arcagi1' / 'e3.json', 0o000)

    def test7e_repeated_condition(self):
        r = self.score()
        self.assertEqual(r.returncode, 0, r.stderr)
        r2 = self.score()
        self.assertEqual(r2.returncode, 2)
        self.assertIn('REPEATED_CONDITION', r2.stderr)
        self.assertEqual(len(self.reads()), 1)

    def test7f_knockout_before_primary(self):
        S.write_json(self.run / 'freeze/KO_FREEZE.json', {'submissions': {}})
        r = self.score('knockout', ssha=S.sha(self.run / 'freeze/KO_FREEZE.json'))
        self.assertEqual(r.returncode, 2)

    def test7g_not_run_as_main_cannot_unlock(self):
        code = (f'import score_sealed, sys; sys.exit(score_sealed.main(["score", "--test", "--run", {str(self.run)!r}, '
                f'"--condition", "primary", "--freeze-sha", {self.fsha!r}, "--submit-sha", {self.ssha!r}]))')
        r = S.run_py(code, {'RATCHET_KEY_ROOT': str(self.key)})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('UNLOCK_REFUSED', r.stderr)
        self.assertEqual(self.reads(), [])


class TestScoreEndToEnd(ScoreCase):
    def test10_primary_then_knockout_then_verdict(self):
        r = self.score()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('SCORE condition=primary tasks=6 W=5', r.stdout)
        self.assertTrue(all(m == 0 for m in S.key_modes(self.key)), S.key_modes(self.key))
        sd = self.run / 'scores'
        solved = json.loads((sd / 'solved_primary.json').read_text())
        self.assertEqual(solved['solved']['sealed']['STOCK'], ['e0', 'e1', 'e2', 'e3', 'e4'])
        self.assertEqual(solved['solved']['sealed']['FLATTTC'], [])
        self.assertEqual(solved['per_seed']['sealed']['FLATTTC']['2']['e5'], True)
        self.assertEqual(solved['solved']['perturbed']['STOCK'], ['e0', 'e1', 'e2', 'e3', 'e4'])
        self.assertEqual(json.loads((sd / 'W.json').read_text())['W'], ['e0', 'e1', 'e2', 'e3', 'e4'])
        win = json.loads((sd / 'winners.json').read_text())['winners']
        self.assertEqual(len(win['e0']), 6)          # 2 samples x 3 correct seeds
        g = json.loads((sd / 'gates.json').read_text())['primary']
        self.assertEqual(g['reuse']['programs'], 5)
        self.assertEqual(g['reuse']['programs_calling'], 4)
        self.assertTrue(g['contamination']['pass'])
        self.assertTrue(all(c['pass'] for c in g['compare'].values()))
        self.assertAlmostEqual(g['compare']['STOCK_vs_FLATTTC']['p'], 1 / 32)
        self.assertTrue(g['void_compare']['pass'])
        # only booleans, ids and counts left the key: no file in scores/ holds a grid value list
        for p in sd.iterdir():
            self.assertNotIn('[[', p.read_text().replace(' ', ''), p.name)
        v = verdict.verdict(self.run)
        self.assertEqual(v['label'], 'PENDING_KNOCKOUT')
        # knockout read
        ko_sha = S.make_knockout(self.run, self.fsha, self.ssha)
        r = self.score('knockout', ssha=ko_sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('kept_delete=2 kept_inline=1 pass=1', r.stdout)
        rows = self.reads()
        self.assertEqual([x['condition'] for x in rows], ['primary', 'knockout'])
        self.assertEqual(rows[0]['n_files'], 6)
        self.assertTrue(all(m == 0 for m in S.key_modes(self.key)))
        self.assertIn('REPEATED_CONDITION', self.score('knockout', ssha=ko_sha).stderr)
        v = verdict.verdict(self.run)
        self.assertEqual(v['label'], 'COMPOUNDS')
        self.assertEqual(v['prediction']['quantity'], 5)
        out = verdict.write_result(self.run, None)
        text = out.read_text()
        self.assertIn('**Outcome: COMPOUNDS**', text)
        self.assertNotIn(chr(0x2014), text)
        # an edit to a knockout submission after KO_FREEZE is refused (and the condition is already used anyway)
        self.assertTrue((self.run / 'VERDICT.json').exists())

    def test_perturbed_scoring_uses_transformed_outputs(self):
        # same run, but perturbed STOCK submissions carry the UNperturbed outputs: they must score as wrong
        for k in S.SEEDS:
            p = self.run / f'sealed/perturbed/STOCK/seed_{k}/submissions.json'
            d = json.loads(p.read_text())
            for s in d['submissions']:
                i = int(s['task'][1:])
                s['attempts'][0]['outputs'] = [S.out_grid(i)]
            p.write_text(json.dumps(d))
        sf = json.loads((self.run / 'freeze/SUBMIT_FREEZE.json').read_text())
        for rel in list(sf['submissions']):
            sf['submissions'][rel] = S.sha(self.run / rel)
        (self.run / 'freeze/SUBMIT_FREEZE.json').write_text(json.dumps(sf))
        r = self.score(ssha=S.ack(self.run, 'SUBMIT_FREEZE'))
        self.assertEqual(r.returncode, 0, r.stderr)
        g = json.loads((self.run / 'scores/gates.json').read_text())['primary']
        # perturbations that fix colour 1..5 or identity-on-1x1 could make some match; 1x1 grids only change colour
        from ratchet import perturb
        expect = sum(1 for t in ('e0', 'e1', 'e2', 'e3', 'e4')
                     if perturb.apply_grid(((int(t[1:]),),), perturb.draw(t, 20261104)) == ((int(t[1:]),),))
        self.assertEqual(g['counts']['perturbed']['STOCK']['solved'], expect)


class TestDecide(unittest.TestCase):
    def prim(self, beats=None, reuse=True, contam=True, void_ok=True):
        beats = beats or {}
        comps = {f'STOCK_vs_{b}': {'pass': beats.get(b, True)} for b in ('STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'FLATTTC')}
        return {'compare': comps, 'void_compare': {'pass': void_ok}, 'reuse': {'pass': reuse},
                'contamination': {'pass': contam}}

    def test_precedence(self):
        ko_ok, ko_bad = {'pass': True}, {'pass': False}
        D = verdict.decide
        self.assertEqual(D(self.prim(void_ok=False), ko_ok)['label'], 'VOID')
        self.assertEqual(D(self.prim(), ko_ok)['label'], 'COMPOUNDS')
        self.assertEqual(D(self.prim(), None)['label'], 'PENDING_KNOCKOUT')
        self.assertEqual(D(self.prim(), ko_bad)['label'], 'NULL')
        self.assertEqual(D(self.prim(beats={'STATIC': False}), ko_ok)['label'], 'LIBRARY HELPS, NOT COMPOUNDING')
        self.assertEqual(D(self.prim(beats={'STATIC': False, 'FLATTTC': False}), ko_ok)['label'], 'NULL')
        self.assertEqual(D(self.prim(reuse=False), ko_ok)['label'], 'CONTEXT EFFECT')
        self.assertEqual(D(self.prim(contam=False), ko_ok)['label'], 'RETRIEVAL')
        self.assertEqual(D(self.prim(reuse=False, contam=False), None)['label'], 'CONTEXT EFFECT')
        self.assertEqual(D(self.prim(beats={'SHAM': False}), ko_ok)['label'], 'NULL')
        self.assertEqual(D(None, None)['label'], 'NOT_SCORED')

    def test_void_attempts_retire_after_two(self):
        with tempfile.TemporaryDirectory() as d:
            runs = Path(d) / 'runs'
            for name in ('v1', 'v1', 'v2'):
                (runs / name).mkdir(parents=True, exist_ok=True)
                a = verdict.record_attempt(runs / name, 'VOID')
            self.assertEqual(a['void_runs'], ['v1', 'v2'])
            self.assertTrue(a['retired'])
            self.assertFalse(verdict.record_attempt(Path(d) / 'other' / 'v9', 'NULL')['retired'])


if __name__ == '__main__':
    unittest.main()
