"""Builder A: perturbation (PREREG 6.4; SPEC 11 test_perturb, 13 I12)."""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import ratchet  # noqa: F401
from ratchet import arc_io, guard, perturb
from ratchet.perturb import Perturbation, apply_grid, apply_task, draw
from ratchet.types import Pair, Task

G = ((1, 2, 3), (4, 5, 6))
ID = Perturbation(perm=tuple(range(10)), geom='rot90')


class TestPerturb(unittest.TestCase):
    def test_perm_bijection_zero_fixed(self):
        for tid in arc_io.sealed_id_list():
            p = draw(tid, perturb.PERTURB_SEED)
            self.assertEqual(p.perm[0], 0)
            self.assertEqual(sorted(p.perm), list(range(10)))
            self.assertIn(p.geom, ('rot90', 'rot180', 'rot270', 'transpose'))

    def test_reproducible_and_seed_sensitive(self):
        self.assertEqual(draw('abc', 7), draw('abc', 7))
        ids = arc_io.sealed_id_list()
        self.assertNotEqual([draw(i, 1) for i in ids[:20]], [draw(i, 2) for i in ids[:20]])
        self.assertEqual(perturb.PERTURB_SEED, 20261104)

    def test_four_geometries_hit(self):
        counts = {}
        for tid in arc_io.sealed_id_list():
            g = draw(tid, perturb.PERTURB_SEED).geom
            counts[g] = counts.get(g, 0) + 1
        self.assertEqual(set(counts), {'rot90', 'rot180', 'rot270', 'transpose'})
        print('PERTURB_GEOM_COUNTS', dict(sorted(counts.items())))

    def test_geometry_values(self):
        ident = tuple(range(10))
        self.assertEqual(apply_grid(G, Perturbation(ident, 'rot90')), ((4, 1), (5, 2), (6, 3)))
        self.assertEqual(apply_grid(G, Perturbation(ident, 'rot180')), ((6, 5, 4), (3, 2, 1)))
        self.assertEqual(apply_grid(G, Perturbation(ident, 'rot270')), ((3, 6), (2, 5), (1, 4)))
        self.assertEqual(apply_grid(G, Perturbation(ident, 'transpose')), ((1, 4), (2, 5), (3, 6)))
        g = G
        for _ in range(4):
            g = apply_grid(g, Perturbation(ident, 'rot90'))
        self.assertEqual(g, G)

    def test_colour_map(self):
        perm = (0, 2, 3, 4, 5, 6, 7, 8, 9, 1)
        out = apply_grid(((0, 1), (9, 0)), Perturbation(perm, 'rot180'))
        self.assertEqual(out, ((0, 1), (2, 0)))
        with self.assertRaises(ValueError):
            apply_grid(G, Perturbation((1, 0, 2, 3, 4, 5, 6, 7, 8, 9), 'rot90'))

    def test_same_transform_demos_and_tests(self):
        t = Task(id='abcd1234', split='growth', train=(Pair(G, ((1,),)), Pair(((7, 7),), G)),
                 test_inputs=(G,), test_outputs=(((3, 0),),), src_sha256='x')
        p = draw(t.id, 11)
        pt = apply_task(t, p)
        self.assertEqual(pt.train[0].input, apply_grid(G, p))
        self.assertEqual(pt.train[1].output, apply_grid(G, p))
        self.assertEqual(pt.test_inputs[0], apply_grid(G, p))
        self.assertEqual(pt.test_outputs[0], apply_grid(((3, 0),), p))
        # the input-output relation is conjugated: identical demo input and test input stay identical
        self.assertEqual(pt.train[0].input, pt.test_inputs[0])

    def test_build_perturbed_split(self):
        tmp = Path(tempfile.mkdtemp(prefix='ratchet_a_pt_'))
        old = os.environ.get('RATCHET_DATA_ROOT')
        try:
            root = tmp / 'data'
            (root / 'sealed').mkdir(parents=True)
            os.environ['RATCHET_DATA_ROOT'] = str(root)
            guard.add_data_root(root)
            for i, tid in enumerate(('aaaa0001', 'aaaa0002', 'aaaa0003')):
                g = [[(i + r + c) % 10 for c in range(2)] for r in range(3)]
                (root / 'sealed' / f'{tid}.json').write_text(json.dumps(
                    {'train': [{'input': g, 'output': g[::-1]}], 'test': [{'input': g}]}))
            buf = io.StringIO()
            with redirect_stdout(buf):
                mpath = perturb.build_perturbed_split(seed=5)
            self.assertRegex(buf.getvalue(), r'LEVER PERTURB seed=5 tasks=3')
            man = json.loads(mpath.read_text())
            self.assertEqual(man['n_tasks'], 3)
            self.assertEqual(mpath, root / 'PERTURB.json')
            for tid in ('aaaa0001', 'aaaa0002', 'aaaa0003'):
                src = arc_io.load_task(tid, 'sealed')
                pt = arc_io.load_task(tid, 'sealed_perturbed')   # raises SealedLeak if an output was written
                p = draw(tid, 5)
                self.assertEqual(man['tasks'][tid]['perm'], list(p.perm))
                self.assertEqual(pt.train, apply_task(src, p).train)
                self.assertEqual(pt.test_inputs, apply_task(src, p).test_inputs)
                self.assertIsNone(pt.test_outputs)
        finally:
            if old is None:
                os.environ.pop('RATCHET_DATA_ROOT', None)
            else:
                os.environ['RATCHET_DATA_ROOT'] = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
