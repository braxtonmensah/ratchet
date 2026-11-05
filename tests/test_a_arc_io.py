"""Builder A: arc_io (SPEC 11 test_arc_io). CPU only, no sealed content read (only committed id lists and temp fakes)."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import ratchet  # noqa: F401  (installs the guard hook first, as every loop process does)
from ratchet import arc_io, guard
from ratchet.types import Task

GROWTH_SHA = 'c4e1b145daad71b4f02ac3482be215f1ab07863b67f13fc1bde1572f501ff75a'
SEALED_SHA = '911bf838d8843606d5fc1ba0550a0c23670027bf8f6e32e4e4fbf93854957ddd'
# sha256 of the 50 pilot ids (sorted, LF, trailing LF); pinned from the first Quartz run of this test, 2026-11-04
PILOT_LIST_SHA = '0ac994f4d12e53441a487e8f807d6c4e5acdb92ef5aceb9275bf71f6eaa7e004'


def fake_task(seed=0, n_test=1, with_output=True):
    g = [[(seed + i + j) % 10 for j in range(3)] for i in range(2)]
    o = [[(v + 1) % 10 for v in r] for r in g]
    test = [{'input': g, 'output': o} if with_output else {'input': g} for _ in range(n_test)]
    return {'train': [{'input': g, 'output': o}, {'input': o, 'output': [[(v + 1) % 10 for v in r] for r in o]}],
            'test': test}


class DataRootCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_a_io_'))
        self.root = self.tmp / 'data'
        for d in ('growth', 'sealed', 'sealed_perturbed', 'arcagi2_sealed'):
            (self.root / d).mkdir(parents=True)
        self.old_env = os.environ.get('RATCHET_DATA_ROOT')
        os.environ['RATCHET_DATA_ROOT'] = str(self.root)
        guard.add_data_root(self.root)

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop('RATCHET_DATA_ROOT', None)
        else:
            os.environ['RATCHET_DATA_ROOT'] = self.old_env
        # protected roots are add-only and the guard hook refuses removal inside them from this process
        subprocess.run(['rm', '-rf', str(self.tmp)], check=False)

    def put(self, split, tid, obj):
        p = self.root / split / f'{tid}.json'
        p.write_text(json.dumps(obj))
        return p


class TestIdLists(unittest.TestCase):
    def test_prereg_hashes(self):
        g = arc_io.verify_id_list(arc_io.GROWTH_IDS_FILE, GROWTH_SHA)
        s = arc_io.verify_id_list(arc_io.SEALED_IDS_FILE, SEALED_SHA)
        self.assertEqual((len(g), len(s)), (400, 400))
        self.assertEqual(g, sorted(g))
        self.assertFalse(set(g) & set(s))
        self.assertEqual(arc_io.GROWTH_IDS_SHA256, GROWTH_SHA)
        self.assertEqual(arc_io.SEALED_IDS_SHA256, SEALED_SHA)
        # the canonical form equals the committed bytes (LF, trailing LF)
        self.assertEqual(hashlib.sha256(arc_io.GROWTH_IDS_FILE.read_bytes()).hexdigest(), GROWTH_SHA)

    def test_mismatch_and_crlf(self):
        tmp = Path(tempfile.mkdtemp(prefix='ratchet_a_ids_'))
        try:
            ids = arc_io.growth_id_list()
            crlf = tmp / 'crlf.txt'
            crlf.write_bytes(''.join(i + '\r\n' for i in ids).encode())
            self.assertEqual(arc_io.verify_id_list(crlf, GROWTH_SHA), ids)
            bad = tmp / 'bad.txt'
            bad.write_text(''.join(i + '\n' for i in ids[:-1]))
            with self.assertRaises(arc_io.IdListMismatch):
                arc_io.verify_id_list(bad, GROWTH_SHA)
            dup = tmp / 'dup.txt'
            dup.write_text(''.join(i + '\n' for i in ids + ids[:1]))
            with self.assertRaises(arc_io.IdListMismatch):
                arc_io.verify_id_list(dup, GROWTH_SHA)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_pilot_ids_stable(self):
        a = arc_io.pilot_ids()
        b = arc_io.pilot_ids(50)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 50)
        self.assertEqual(a, sorted(a))
        g = arc_io.growth_id_list()
        self.assertTrue(set(a) <= set(g))
        want = sorted(sorted(g, key=lambda i: hashlib.sha256(('ratchet-pilot|' + i).encode()).hexdigest())[:50])
        self.assertEqual(a, want)
        sha = arc_io.id_list_sha256(a)
        print(f'PILOT_IDS_SHA256 {sha} first={a[0]} last={a[-1]}')
        if PILOT_LIST_SHA is not None:
            self.assertEqual(sha, PILOT_LIST_SHA)


class TestGrids(unittest.TestCase):
    def test_validate_ok(self):
        g = arc_io.validate_grid([[0, 1], [9, 2]])
        self.assertEqual(g, ((0, 1), (9, 2)))
        self.assertEqual(arc_io.validate_grid([[5] * 30] * 30)[29][29], 5)

    def test_validate_bad(self):
        for bad in ([], [[]], [[1, 2], [3]], [[10]], [[-1]], [[True]], [[1.0]], [['1']], [[1] * 31], [[1]] * 31,
                    'ab', None, [1, 2]):
            with self.assertRaises(arc_io.BadGrid, msg=repr(bad)[:40]):
                arc_io.validate_grid(bad)

    def test_render_round_trip(self):
        g = arc_io.validate_grid([[0, 1, 2], [3, 4, 5]])
        s = arc_io.render_grid(g)
        self.assertEqual(s, '012\n345')
        self.assertEqual(arc_io.parse_rendered(s), g)
        self.assertEqual(arc_io.grid_to_json(g), [[0, 1, 2], [3, 4, 5]])


class TestLoad(DataRootCase):
    def test_growth_load(self):
        p = self.put('growth', 'aaaa0001', fake_task(1, n_test=2))
        t = arc_io.load_task('aaaa0001', 'growth')
        self.assertIsInstance(t, Task)
        self.assertEqual(t.split, 'growth')
        self.assertEqual(len(t.train), 2)
        self.assertEqual(len(t.test_inputs), 2)
        self.assertEqual(len(t.test_outputs), 2)
        self.assertEqual(t.src_sha256, hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(arc_io.task_ids('growth'), ['aaaa0001'])
        self.assertEqual([x.id for x in arc_io.load_split('growth')], ['aaaa0001'])

    def test_pilot_reads_growth_dir(self):
        self.put('growth', 'aaaa0002', fake_task(2))
        t = arc_io.load_task('aaaa0002', 'pilot')
        self.assertEqual(t.split, 'pilot')
        self.assertIsNotNone(t.test_outputs)

    def test_sealed_inputs_only(self):
        self.put('sealed', 'bbbb0001', fake_task(3, with_output=False))
        t = arc_io.load_task('bbbb0001', 'sealed')
        self.assertIsNone(t.test_outputs)

    def test_sealed_leak(self):
        for split in ('sealed', 'sealed_perturbed', 'arcagi2_sealed'):
            self.put(split, 'bbbb0002', fake_task(4, with_output=True))
            with self.assertRaises(arc_io.SealedLeak):
                arc_io.load_task('bbbb0002', split)

    def test_growth_without_output_is_bad(self):
        self.put('growth', 'aaaa0003', fake_task(5, with_output=False))
        with self.assertRaises(arc_io.BadTask):
            arc_io.load_task('aaaa0003', 'growth')

    def test_bad_ids_and_split(self):
        for bad in ('../growth/aaaa0001', 'a/b', '', 'x' * 65):
            with self.assertRaises(ValueError):
                arc_io.load_task(bad, 'growth')
        with self.assertRaises(ValueError):
            arc_io.load_task('aaaa0001', 'evaluation')

    def test_symlink_outside_refused(self):
        outside = self.tmp / 'outside.json'
        outside.write_text(json.dumps(fake_task(6)))
        os.symlink(outside, self.root / 'growth' / 'cccc0001.json')
        with self.assertRaises(guard.SealedReadRefused):
            arc_io.load_task('cccc0001', 'growth')

    def test_symlink_into_protected_root_refused(self):
        fake_key = self.tmp / 'fakekey'
        fake_key.mkdir()
        target = fake_key / 'dddd0001.json'
        target.write_text(json.dumps(fake_task(7, with_output=False)))
        os.symlink(target, self.root / 'sealed' / 'dddd0001.json')   # before protecting: the hook refuses it after
        guard.add_protected_root(fake_key)
        with self.assertRaises(guard.SealedReadRefused):
            arc_io.load_task('dddd0001', 'sealed')

    def test_read_json_outside_data_root_refused(self):
        p = self.tmp / 'x.json'
        p.write_text('{}')
        with self.assertRaises(guard.SealedReadRefused):
            arc_io._read_json(p)
        with self.assertRaises(guard.SealedReadRefused):
            arc_io._read_json(self.root / 'growth' / '..' / '..' / 'x.json')

    def test_write_json_confined(self):
        sha = arc_io._write_json(self.root / 'sealed_perturbed' / 'eeee0001.json', {'a': 1})
        self.assertEqual(sha, hashlib.sha256(b'{"a":1}').hexdigest())
        with self.assertRaises(PermissionError):
            arc_io._write_json(self.tmp / 'escape.json', {'a': 1})
        self.assertFalse((self.tmp / 'escape.json').exists())

    def test_task_to_json_strips_outputs(self):
        self.put('growth', 'aaaa0004', fake_task(8))
        t = arc_io.load_task('aaaa0004', 'growth')
        j = arc_io.task_to_json(t, include_test_outputs=False)
        self.assertTrue(all('output' not in x for x in j['test']))
        j2 = arc_io.task_to_json(t, include_test_outputs=True)
        self.assertEqual(j2, fake_task(8))


if __name__ == '__main__':
    unittest.main()
