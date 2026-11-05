"""Builder A: pass@2 (PREREG 5; SPEC 11 test_select, 13 I9)."""
import dataclasses
import inspect
import unittest

import ratchet  # noqa: F401
from ratchet.select import candidate_from_exec, pass2
from ratchet.types import Candidate, ExecResult, Submission

A = (((1,),),)
B = (((2,),),)
C = (((3,),),)


def cand(sid, out, n=10, ok=True):
    return Candidate(sample_id=sid, code_len=n, demo_pass=ok, test_outputs=out)


class TestPass2(unittest.TestCase):
    def test_majority(self):
        s = pass2('t', [cand('a', A), cand('b', B), cand('c', B), cand('d', C)])
        self.assertEqual([a.outputs for a in s.attempts], [B, A])
        self.assertEqual(s.attempts[0].votes, 2)
        self.assertEqual(s.attempts[0].sample_ids, ('b', 'c'))
        self.assertEqual((s.n_candidates, s.n_demo_pass), (4, 4))

    def test_tie_by_shortest(self):
        s = pass2('t', [cand('a', A, n=50), cand('b', B, n=20), cand('c', C, n=30)])
        self.assertEqual([a.outputs for a in s.attempts], [B, C])
        self.assertEqual([a.min_len for a in s.attempts], [20, 30])

    def test_tie_fully_deterministic(self):
        cs = [cand('a', B, n=5), cand('b', A, n=5)]
        s1 = pass2('t', cs)
        s2 = pass2('t', list(reversed(cs)))
        self.assertEqual(s1.attempts, tuple(dataclasses.replace(a) for a in s2.attempts))
        self.assertEqual([a.outputs for a in s1.attempts], [A, B])   # repr order breaks the last tie

    def test_two_distinct_attempts_max(self):
        s = pass2('t', [cand('a', A), cand('b', A), cand('c', A)])
        self.assertEqual(len(s.attempts), 1)
        s = pass2('t', [cand('a', A), cand('b', B), cand('c', C)])
        self.assertEqual(len(s.attempts), 2)
        self.assertEqual(len({a.outputs for a in s.attempts}), 2)

    def test_demo_fail_ignored(self):
        s = pass2('t', [cand('a', A, ok=False), cand('b', A, ok=False), cand('c', B)])
        self.assertEqual([a.outputs for a in s.attempts], [B])
        self.assertEqual(s.n_demo_pass, 1)
        s = pass2('t', [cand('a', A, ok=False)])
        self.assertEqual(s.attempts, ())

    def test_demo_pass_without_outputs_ignored(self):
        s = pass2('t', [cand('a', None), cand('b', B)])
        self.assertEqual([a.outputs for a in s.attempts], [B])
        self.assertEqual(s.n_demo_pass, 2)

    def test_joint_key_multi_test(self):
        x = (((1,),), ((2,),))
        y = (((1,),), ((3,),))
        s = pass2('t', [cand('a', x), cand('b', y), cand('c', y)])
        self.assertEqual(s.attempts[0].outputs, y)
        self.assertEqual(s.attempts[1].outputs, x)

    def test_no_test_output_parameter_exists(self):
        self.assertEqual(list(inspect.signature(pass2).parameters), ['task_id', 'candidates', 'k'])
        self.assertEqual([f.name for f in dataclasses.fields(Candidate)],
                         ['sample_id', 'code_len', 'demo_pass', 'test_outputs'])
        src = inspect.getsource(pass2)
        for word in ('load_task', 'key', 'truth', 'expected'):
            if word == 'key':
                continue   # the vote key is a local variable name
            self.assertNotIn(word, src)

    def test_candidate_from_exec_and_json(self):
        r = ExecResult(sample_id='s', code_sha='x', status='DEMO_FAIL', demo_pass=False, n_demo_pass=0, n_demos=2,
                       first_fail_demo=0, test_outputs=A)
        c = candidate_from_exec(r, 12)
        self.assertIsNone(c.test_outputs)
        s = pass2('t', [cand('a', A), cand('b', B)])
        self.assertEqual(Submission.from_json(s.to_json()), s)


if __name__ == '__main__':
    unittest.main()
