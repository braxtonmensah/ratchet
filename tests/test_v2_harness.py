"""Harness v2 (silicyte-0119): type adapter, header and legend, lever check, F3 instruction and its sha refusal, the
sequential F3 screen, the PLANT_SOLVE control and its isolation from every growth path, and the key-grant rule of
score_sealed.py. CPU only. Tests that execute programs need Linux (the sandbox child); tests that read arc-dsl or the
model tokenizer skip when those are absent."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ratchet  # noqa: F401
from ratchet import adapter, arms, config, library, pilot, prompt, rounds
from ratchet.arms import Deadline
from ratchet.tok import StubTokenizer
from ratchet.types import Pair, Task

import test_d_fakes as F

REPO = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / 'fixtures' / 'plant1_v1_helper_programs.json'
LINUX = sys.platform.startswith('linux')
ARCDSL = Path(os.environ.get('RATCHET_ARCDSL_DIR', str(config.DATA_DIR / 'raw' / 'arc-dsl')))
HAVE_ARCDSL = (ARCDSL / 'solvers.py').exists()


def _child():
    spec = importlib.util.spec_from_file_location('ratchet_sandbox_child_v2', REPO / 'ratchet' / 'sandbox_child.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _task(tid='abcd0001', split='growth'):
    g = ((1, 2, 3), (4, 5, 6))
    return Task(id=tid, split=split, train=(Pair(g, g),), test_inputs=(g,), test_outputs=(g,), src_sha256='s' + tid)


def _fixture():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def _grids(task_json, part):
    return [tuple(tuple(r) for r in p[part]) for p in task_json]


# ---------------------------------------------------------------------------------------------------------------------
# F1 adapter

class TestAdapterRule(unittest.TestCase):
    def setUp(self):
        self.c = _child()

    def test_child_and_parent_agree_on_grid_types(self):
        self.assertEqual(self.c._GRID_TYPES, frozenset(config.ADAPTER_GRID_TYPES))
        self.assertEqual(adapter.GRID_TYPES, frozenset(config.ADAPTER_GRID_TYPES))

    def test_unannotated_helper_is_returned_by_identity(self):
        ns = {}
        exec('def h(g, k):\n    return g\n', ns)
        f = ns['h']
        self.assertIsNone(self.c._grid_sig(f))
        self.assertIs(self.c._adapt(f, self.c._grid_sig(f)), f)
        exec("def h2(x: 'Object', n: 'Integer') -> 'Indices':\n    return x\n", ns)   # annotated, not grid-typed
        self.assertIs(self.c._adapt(ns['h2'], self.c._grid_sig(ns['h2'])), ns['h2'])

    def test_grid_args_in_as_tuples_results_out_as_lists(self):
        ns = {}
        exec("def f(grid: 'Grid', obj: 'Object', *, piece: 'Piece' = None) -> 'Grid':\n"
             "    assert isinstance(grid, tuple) and isinstance(grid[0], tuple)\n"
             "    assert piece is None or isinstance(piece, tuple)\n"
             "    assert isinstance(obj, list)\n"
             "    return grid\n", ns)
        a = self.c._adapt(ns['f'], self.c._grid_sig(ns['f']))
        out = a([[1, 2], [3, 4]], [1, 2], piece=[[0]])
        self.assertEqual(out, [[1, 2], [3, 4]])
        self.assertIsInstance(out, list)
        self.assertEqual(a(grid=((1,),), obj=[]), [[1]])              # tuple in stays tuple, result back as list
        exec("def e(element: 'Element') -> 'Element':\n    return element\n", ns)
        b = self.c._adapt(ns['e'], self.c._grid_sig(ns['e']))
        fs = frozenset({(1, (0, 0))})
        self.assertIs(b(fs), fs)                                       # a patch is not a grid: untouched
        self.assertEqual(b([]), [])                                    # empty list: identity
        self.assertEqual(b([1, 2]), [1, 2])                            # items not rows: identity

    def test_wrappers_keep_the_signature(self):
        ns = {}
        exec("def f(a, b: 'Grid', /, c=3, *rest, d, e=5, **kw) -> 'Grid':\n    return (a, b, c, rest, d, e, kw)\n", ns)
        f = ns['f']
        seen = []
        w = self.c._clone_signature(f, lambda *a, **k: seen.append((a, k)) or f(*a, **k))
        self.assertEqual(w.__code__.co_argcount, f.__code__.co_argcount)
        self.assertEqual(w.__code__.co_kwonlyargcount, f.__code__.co_kwonlyargcount)
        self.assertEqual(w(1, 2, d=4), f(1, 2, d=4))
        self.assertEqual(w(1, 2, 9, 8, d=4, z=1), f(1, 2, 9, 8, d=4, z=1))
        self.assertEqual(w.__name__, 'f')
        a = self.c._adapt(f, self.c._grid_sig(f))
        self.assertEqual(a.__code__.co_argcount, 3)
        self.assertEqual(a(1, [[1]], d=0)[1], ((1,),))

    def test_legend_rule(self):
        self.assertEqual(adapter.legend(['def h(g):\n    return g\n']), '')
        lg = adapter.legend(["def f(grid: 'Grid', p: 'Patch') -> 'Objects':\n    pass\n"])
        self.assertEqual(lg.splitlines(), ['# Grid: list of lists of ints (rows)', '# Objects: frozenset of Object',
                                           '# Patch: Object or Indices'])
        self.assertEqual(adapter.legend(["def f(x: 'list') -> 'Callable':\n    pass\n"]), '')


@unittest.skipUnless(LINUX, 'sandbox child needs Linux')
class TestAdapterInSandbox(unittest.TestCase):
    def test_counting_unchanged_and_library_namespace(self):
        from ratchet import sandbox
        lib = ("def inner(grid: 'Grid') -> 'Integer':\n    return len(grid)\n"
               "def outer(grid: 'Grid') -> 'Grid':\n    inner(grid)\n    return grid if isinstance(grid, tuple) else 0\n"
               "def plain(g):\n    return g\nK = 7\n")
        code = 'def transform(grid):\n    out = outer(grid)\n    assert K == 7\n    return plain(out)\n'
        g = ((1, 2), (3, 4))
        r = sandbox.run_program(code, lib, [g], [g], [g])
        self.assertEqual(r.status, 'OK', r.error)
        self.assertEqual(r.helper_calls, {'inner': 1, 'outer': 1, 'plain': 1})   # internal call counted as in v1
        self.assertEqual(r.helpers_callable, 3)
        r0 = sandbox.run_program(code, lib, [g], [g], [g], adapter=False)
        self.assertEqual(r0.status, 'BAD_OUTPUT')                                  # v1 boundary: list in, 0 out

    def test_arity_introspection_survives_counting_and_adapter(self):
        # arc-dsl rbind reads function.__code__.co_argcount; v1's (*a, **k) counter made it 0 (19 of 50 pilot solvers)
        from ratchet import sandbox
        lib = ("def rbind(function: 'Callable', fixed: 'Any') -> 'Callable':\n"
               "    n = function.__code__.co_argcount\n"
               "    if n == 2:\n        return lambda x: function(x, fixed)\n"
               "    return lambda x, y: function(x, y, fixed)\n"
               "def size2(grid: 'Grid', k: 'Integer') -> 'Integer':\n    return len(grid) + k\n"
               "def via(grid: 'Grid') -> 'Integer':\n    return rbind(size2, 0)(grid)\n")
        g = ((1, 2), (3, 4))
        out = ((2,),)
        code = 'def transform(grid):\n    return [[via(grid), rbind(size2, 0)(grid)][:1]]\n'
        r = sandbox.run_program(code, lib, [g], [out], [g])
        self.assertEqual(r.status, 'OK', r.error)
        self.assertEqual(r.helper_calls, {'rbind': 2, 'size2': 2, 'via': 1})

    def test_future_annotations_parent_and_child_agree(self):
        from ratchet import sandbox
        lib = ('from __future__ import annotations\n'
               'def f(grid: Grid) -> Grid:\n    return grid if isinstance(grid, tuple) else 0\n'
               "def q(grid: 'Grid') -> 'Grid':\n    return grid if isinstance(grid, tuple) else 0\n")
        self.assertEqual(adapter.grid_helpers(lib), ['f', 'q'])
        self.assertEqual(adapter.grid_helpers(lib.split('\n', 1)[1]), ['q'])   # bare Grid without the future import
        g = ((1, 2), (3, 4))
        # the import allowlist refuses __future__ in a library, so this case never executes; the child's quote rule
        # (for the record) is checked directly
        r = sandbox.run_program('def transform(grid):\n    return q(f(grid))\n', lib, [g], [g], [g])
        self.assertEqual((r.status, r.error), ('ERROR', 'LIBRARY:ImportError:IMPORT_REFUSED:__future__'))
        c = _child()
        self.assertTrue(c._is_grid_ann("'Grid'") and c._is_grid_ann('Grid') and not c._is_grid_ann('Grids'))
        lib2 = "def q(grid: 'Grid') -> 'Grid':\n    return grid if isinstance(grid, tuple) else 0\n"
        r2 = sandbox.run_program('def transform(grid):\n    return q(grid)\n', lib2, [g], [g], [g])
        self.assertEqual(r2.status, 'OK', r2.error)

    def test_replay_v1_plant1_helper_programs(self):
        from ratchet import sandbox
        fx = _fixture()
        lib = fx['library_py']
        self.assertEqual(len(fx['crash']), 41)
        self.assertEqual(len(fx['other']), 4)

        def run(item, adapt=True):
            t = fx['tasks'][item['task']]
            return sandbox.run_program(item['code'], lib, _grids(t['train'], 'input'), _grids(t['train'], 'output'),
                                       _grids(t['test'], 'input'), sample_id=item['sample_id'], adapter=adapt)

        base = [run(it, adapt=False) for it in fx['crash']]
        self.assertTrue(all(r.status == 'ERROR' and 'too many values to unpack' in (r.error or '') for r in base),
                        [r.error for r in base if r.status != 'ERROR'][:3])
        res = [run(it) for it in fx['crash']]
        n_pass = sum(1 for r in res if r.demo_pass)
        tasks = sorted({it['task'] for it, r in zip(fx['crash'], res) if r.demo_pass})
        statuses = {}
        for r in res:
            statuses[r.status] = statuses.get(r.status, 0) + 1
        print('V2_REPLAY crash_programs=41 demo_pass=%d tasks=%d statuses=%s' % (n_pass, len(tasks), statuses))
        self.assertGreaterEqual(n_pass, 20)
        for it in fx['other']:
            r = run(it)
            want = it['v1_test_outputs']
            got = None if r.test_outputs is None else [[list(row) for row in g] for g in r.test_outputs]
            self.assertEqual((r.status, r.demo_pass), (it['v1_status'], it['v1_demo_pass']), it['sample_id'])
            self.assertEqual(got, want, it['sample_id'])

    def test_lever_smoke_on_v1_L_plant_1(self):
        from ratchet import sandbox
        fx = _fixture()
        t = fx['tasks'][fx['crash'][0]['task']]
        g = _grids(t['train'], 'input')[0]
        on = sandbox.adapter_smoke(fx['library_py'], g)
        off = sandbox.adapter_smoke(fx['library_py'], g, adapter=False)     # positive control: the v1 boundary
        print('V2_LEVER_L_PLANT_1 %s | v1 boundary %s refused=%s' % (
            adapter.lever_line(on['grid_helpers'], on['list_smoke_ok']),
            adapter.lever_line(off['grid_helpers'], off['list_smoke_ok']), ','.join(off['refused'])))
        self.assertTrue(on['ok'], on)
        self.assertEqual(on['grid_helpers'], 13)
        self.assertEqual(on['list_smoke_ok'], 13)
        self.assertFalse(off['ok'])
        self.assertLess(off['list_smoke_ok'], 13)
        self.assertIn('mostcolor', off['refused'])

    def test_no_driver_path_can_turn_the_adapter_off(self):
        for p in (REPO / 'ratchet').glob('*.py'):
            if p.name == 'sandbox.py':
                continue
            self.assertNotIn('adapter=False', p.read_text(encoding='utf-8'), p.name)
        from ratchet.sandbox import ExecJob
        self.assertNotIn('adapter', ExecJob.__dataclass_fields__)


# ---------------------------------------------------------------------------------------------------------------------
# F2 header, legend, note placement; SPEC 13 I3

def _lib(sources, arm='STOCK'):
    hs = []
    for i, (n, s) in enumerate(sources):
        hs.append(library.Helper(name=n, hash='h%d' % i, source=s, canonical=s, token_len=len(s.split()),
                                 n_calling_tasks=2, calling_tasks=['a', 'b']))
    return library.Library(arm=arm, round=1, helpers=hs, parent_sha=None, meta={})


class TestPromptV2(unittest.TestCase):
    def setUp(self):
        self.tok = StubTokenizer()
        self.t = _task()

    def test_default_is_v1_bytes(self):
        pb = prompt.build_messages(self.t, self.tok)
        self.assertEqual(pb.messages[1]['content'], prompt.task_block(self.t) + '\n\n' + config.INSTRUCTION_V1)
        self.assertEqual(config.INSTRUCTION, config.INSTRUCTION_V1)

    def test_instruction_texts_and_shas(self):
        self.assertEqual(config.INSTRUCTION_F3, config.INSTRUCTION_V1 + ' ' + (
            'State the rule in at most three sentences, then give the code block. Do not trace the grids cell by '
            'cell; your program is run on every example for you.'))
        self.assertEqual(arms.instruction_sha(config.INSTRUCTION_V1), config.INSTRUCTION_V1_SHA256)
        self.assertEqual(arms.instruction_sha(config.INSTRUCTION_F3), config.INSTRUCTION_F3_SHA256)
        self.assertEqual(config.MAX_TOKENS, 4096)
        self.assertEqual(config.VLLM_MAX_MODEL_LEN, 20480)

    def test_round1_byte_identity_stock_static_exemplar(self):
        for instr in (config.INSTRUCTION_V1, config.INSTRUCTION_F3):
            stock = prompt.build_messages(self.t, self.tok, library=library.empty('STOCK'), instruction=instr)
            static = prompt.build_messages(self.t, self.tok, library=library.empty('STATIC'), instruction=instr)
            ex = prompt.build_messages(self.t, self.tok, exemplars=[], instruction=instr)
            self.assertEqual(stock.messages, static.messages)
            self.assertEqual(stock.messages, ex.messages)
            self.assertTrue(stock.messages[1]['content'].endswith(instr))

    def test_header_legend_and_note_order(self):
        grown = _lib([('h_abc', 'def h_abc(g):\n    return [list(r) for r in g]\n')])
        plant = _lib([('mostcolor', "def mostcolor(element: 'Element') -> 'Integer':\n    return 0\n")], arm='PLANTL1')
        for instr, tail in ((config.INSTRUCTION_F3, config.INSTRUCTION_TAILS['F3']),
                            (config.INSTRUCTION_V1, config.INSTRUCTION_TAILS['V1'])):
            pg = prompt.build_messages(self.t, self.tok, library=grown, instruction=instr)
            u = pg.messages[1]['content']
            self.assertTrue(u.startswith(config.LIB_HEADER_CALLABLE + '\n```python\ndef h_abc'))   # no legend
            self.assertIn('Pass grids exactly as transform receives them; these functions accept and return grids '
                          'as lists of lists of ints.', u)
            self.assertTrue(u.endswith(config.LIB_NOTE_CALLABLE + ' ' + tail), u[-300:])
            pp = prompt.build_messages(self.t, self.tok, library=plant, instruction=instr)
            v = pp.messages[1]['content']
            self.assertTrue(v.startswith(config.LIB_HEADER_CALLABLE + '\n```python\n# Integer: int\n'
                                         '# Element: Object or Grid\n\ndef mostcolor'), v[:300])   # config order
            block, _n, ntok = prompt.library_block(plant, 6000, self.tok)
            self.assertIn('# Element: Object or Grid', block)
            self.assertEqual(ntok, self.tok.count(block))                     # the legend counts against the cap
        flat = prompt.build_messages(self.t, self.tok, instruction=config.INSTRUCTION_F3)
        self.assertTrue(flat.messages[1]['content'].endswith(config.INSTRUCTION_F3))

    def test_legend_is_inside_the_cap(self):
        plant = _lib([('mostcolor', "def mostcolor(element: 'Element') -> 'Integer':\n    return 0\n")], arm='PLANTL1')
        with_legend = self.tok.count(prompt._render_library(config.LIB_HEADER_CALLABLE,
                                                            [plant.helpers[0].source], True))
        _b, names, _t = prompt.library_block(plant, with_legend - 1, self.tok)
        self.assertEqual(names, ())                                            # does not fit one token under


# ---------------------------------------------------------------------------------------------------------------------
# F3 instruction recorded per run, the sha refusal, the screen

class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ratchet_v2_'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mk(self, name='r', pilot=None, **cfg):
        kit = F.make_kit(pilot=pilot or F.FakePilot(S=2, R=2))
        d = self.tmp / name
        arms.init_run(d, model='/fake/model', s_pilot=2, pilot_n=4, **cfg)
        run = arms.load_run(d, kit=kit)
        run.job_id = 'j1'
        return run, kit, d


class TestInstructionRefusal(_Base):
    def test_init_records_f3(self):
        run, _kit, d = self.mk()
        cfg = json.loads((d / 'RUN.json').read_text())
        self.assertEqual((cfg['instruction'], cfg['instruction_sha']), ('F3', config.INSTRUCTION_F3_SHA256))
        self.assertEqual(arms.run_instruction(run)[1], config.INSTRUCTION_F3)
        self.assertIn('LEVER INSTRUCTION sha=%s' % config.INSTRUCTION_F3_SHA256, arms.lever_instruction_line(run))
        with self.assertRaises(arms.ArmError):
            arms.init_run(self.tmp / 'v1start', model='/fake/model', instruction='V1')    # piloted runs start at F3

    def test_tampered_sha_refuses_before_any_model_call(self):
        run, kit, d = self.mk()
        run = arms.update_run(run, instruction_sha='0' * 64)
        client = F.FakeClient(d, 'j1')
        client.run = mock.Mock(side_effect=AssertionError('model called'))
        with self.assertRaises(arms.InstructionRefused):
            arms.run_unit(run, rounds.WorkUnit('pilot', 'FLAT_A', 'pilot', None, None, 'FLAT_A'), client,
                          Deadline(0.0, clock=lambda: 0.0))
        client.run.assert_not_called()
        with self.assertRaises(arms.InstructionRefused):
            arms.step(run, client, Deadline(0.0, clock=lambda: 0.0))
        st = json.loads((d / 'STATUS.json').read_text())
        self.assertEqual(st['jobs'][-1]['state'], 'FAILED')

    def test_name_sha_mismatch_and_pre_v2_run_refused(self):
        run, _kit, _d = self.mk()
        run = arms.update_run(run, instruction='V1')          # sha still F3's
        with self.assertRaises(arms.InstructionRefused):
            arms.run_instruction(run)
        legacy = arms.Run(dir=self.tmp / 'legacy', S=None, R=None, seed_base=1000, cfg={'name': 'v1'})
        with self.assertRaises(arms.InstructionRefused):
            arms.run_instruction(legacy)

    def test_v1_pilot_dir_refused_under_f3_and_f3_dir_after_fallback(self):
        run, _kit, d = self.mk()
        dl = Deadline(0.0, clock=lambda: 0.0)
        with self.assertRaises(arms.InstructionRefused):
            arms.run_pilot_round(run, 'V1_FLAT_A', F.FakeClient(d, 'j1'), dl)
        run = arms.update_run(run, instruction='V1', instruction_sha=config.INSTRUCTION_V1_SHA256)
        with self.assertRaises(arms.InstructionRefused):
            arms.run_pilot_round(run, 'FLAT_B', F.FakeClient(d, 'j1'), dl)


class TestScreen(_Base):
    def _flat_s(self, d, demo_tasks, n=50):
        rows = []
        for i in range(n):
            t = 't%02d' % i
            rows.append({'sample_id': 'FLAT_S|pilot|r1|%s|s0' % t, 'task': t, 'demo_pass': i < demo_tasks,
                         'test_correct': i < demo_tasks - 1})
        p = d / 'pilot' / 'FLAT_S'
        p.mkdir(parents=True, exist_ok=True)
        (p / 'exec.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        (p / 'samples.jsonl').write_text(''.join(json.dumps({'sample_id': r['sample_id'], 'task': r['task'],
                                                             'gen_tokens': 100, 'finish_reason': 'stop'}) + '\n'
                                                 for r in rows))
        rounds.save_state(p, {'state': 'DONE', 'S_pilot': 58, 'screen': {'g_flat_a': 500.0}})

    def test_screen_rule_both_branches(self):
        d = self.tmp / 's'
        for demo, p2, want in ((23, 22, 'F3'), (22, 30, 'V1'), (30, 21, 'V1'), (40, 40, 'F3')):
            self._flat_s(d, demo)
            res = pilot.screen_decision(d, correct_fn=lambda _d, _w, k=p2: {'t%02d' % i: i < k for i in range(50)})
            self.assertEqual(res['decision'], want, (demo, p2))
            self.assertEqual(res['demo_fit']['demo_pass_test_wrong'], 1)
        self.assertEqual((config.SCREEN_MIN_DEMO_TASKS, config.SCREEN_MIN_PASS2_TASKS, config.SCREEN_GEN_BUDGET),
                         (23, 22, 1451835))

    def test_fallback_sets_v1_once_and_replans(self):
        run, _kit, d = self.mk(pilot=F.FakePilot(decision='V1'))
        run = arms.pilot_screen(run)
        cfg = json.loads((d / 'RUN.json').read_text())
        self.assertEqual((cfg['instruction'], cfg['instruction_sha']), ('V1', config.INSTRUCTION_V1_SHA256))
        self.assertEqual([h['instruction'] for h in cfg['instruction_history']], ['F3', 'V1'])
        self.assertEqual([u.condition for u in rounds.plan(run)][3:],
                         ['V1_FLAT_A', 'V1_FLAT_B', 'V1_PLANT1', 'V1_PLANT_SOLVE', None])
        before = (d / 'pilot' / 'SCREEN.json').read_bytes()
        run.kit.pilot.decision = 'F3'
        run = arms.pilot_screen(run)                          # written once, never rewritten
        self.assertEqual((d / 'pilot' / 'SCREEN.json').read_bytes(), before)
        self.assertEqual(arms.run_instruction(run)[0], 'V1')
        (d / 'pilot' / 'SCREEN.json').write_text(json.dumps({'decision': 'V1'}))
        self.assertEqual(pilot.physical(d, 'FLAT_A'), 'V1_FLAT_A')
        self.assertEqual(pilot.physical(d, 'FLAT_S'), 'FLAT_S')

    def test_stands_keeps_f3(self):
        run, _kit, d = self.mk(pilot=F.FakePilot(decision='F3'))
        run = arms.pilot_screen(run)
        self.assertEqual(arms.run_instruction(run)[0], 'F3')
        self.assertEqual([u.condition for u in rounds.plan(run)][3:], ['FLAT_B', 'PLANT1', 'PLANT_SOLVE', None])


# ---------------------------------------------------------------------------------------------------------------------
# F5 PLANT_SOLVE: isolation and cap

class TestPlantSolveIsolation(_Base):
    def _ps_lib(self):
        h = library.Helper(name='solve_this', hash='x', source="def solve_this(grid: 'Grid') -> 'Grid':\n    return grid\n",
                           canonical='', token_len=10, accepted_by='plant_solve', provenance={'pilot_only': True})
        return library.Library(arm='PLANT_SOLVE', round=1, helpers=[h], parent_sha=None, meta={'pilot_only': True})

    def test_never_saved_into_a_growth_dir(self):
        lib = self._ps_lib()
        with self.assertRaises(ValueError):
            library.save(lib, self.tmp / 'arms' / 'STOCK' / 'round_1', 6000, StubTokenizer())
        jp, _pp, _s = library.save(lib, self.tmp / 'pilot' / 'PLANT_SOLVE' / 'libs', 6000, StubTokenizer(), stem='L')
        self.assertTrue(jp.exists())

    def test_never_merged_into_a_growth_library(self):
        lib = self._ps_lib()
        with self.assertRaises(ValueError):
            library.merge(library.empty('STOCK'), [lib.helpers[0]], 2, [])
        with self.assertRaises(ValueError):
            library.merge(lib, [], 2, [])

    def test_never_frozen(self):
        from ratchet import freeze
        run, _kit, d = self.mk()
        p = d / 'pilot' / 'PLANT_SOLVE' / 'libs'
        jp, _pp, _s = library.save(self._ps_lib(), p, 6000, StubTokenizer(), stem='L_solve_x')
        with self.assertRaises(freeze.FreezeRefused):
            freeze._entry(run, jp.relative_to(d).as_posix(), None)
        q = d / 'arms' / 'STOCK'
        q.mkdir(parents=True)
        shutil.copy(jp, q / 'L_1.json')                       # even copied into an arm dir by hand
        with self.assertRaises(freeze.FreezeRefused):
            freeze._entry(run, 'arms/STOCK/L_1.json', None)

    def test_never_in_a_non_pilot_prompt(self):
        run, _kit, _d = self.mk()
        lib = self._ps_lib()
        for phase, split in (('growth', 'growth'), ('sealed', 'sealed'), ('pilot', 'sealed')):
            spec = arms.ReqSpec(request_id='x', task=_task(split=split), arm='STOCK', phase=phase, round=1,
                                sealed_seed=None, slots=[0], sample_ids=['x|s0'], seed=1, library=lib)
            with self.assertRaises(arms.ArmError, msg=(phase, split)):
                arms._check_pilot_only(run, spec)
        ok = arms.ReqSpec(request_id='y', task=_task(split='pilot'), arm='PLANT_SOLVE', phase='pilot', round=1,
                          sealed_seed=None, slots=[0], sample_ids=['y|s0'], seed=1, library=lib)
        arms._check_pilot_only(run, ok)
        ex = arms.ReqSpec(request_id='z', task=_task(), arm='EXEMPLAR', phase='growth', round=2, sealed_seed=None,
                          slots=[0], sample_ids=['z|s0'], seed=1,
                          exemplars=[{'sample_id': 'PLANT_SOLVE|pilot|r1|t|s0', 'task': 't', 'code': ''}])
        with self.assertRaises(arms.ArmError):
            arms._check_pilot_only(run, ex)

    def test_growth_readers_never_see_pilot_rows(self):
        from ratchet import exemplar, sham
        run, _kit, d = self.mk()
        code = 'def hx(g):\n    return g\ndef transform(grid):\n    return hx(grid)\n'
        # pilot rows, even if they were copied into growth round dirs, are dropped by phase
        for arm, ok in (('EXEMPLAR', True), ('STOCK', False)):
            p = d / 'arms' / arm / 'round_1'
            p.mkdir(parents=True)
            sid = 'PLANT_SOLVE|pilot|r1|t|s0'
            (p / 'samples.jsonl').write_text(json.dumps({'sample_id': sid, 'task': 't', 'phase': 'pilot',
                                                         'code': code}) + '\n')
            (p / 'exec.jsonl').write_text(json.dumps({'sample_id': sid, 'demo_pass': ok, 'status': 'DEMO_FAIL'}) + '\n')
        self.assertEqual(sham.failed_pool(d, 'STOCK'), [])
        self.assertEqual(exemplar.pool_from_rounds(d, 'EXEMPLAR', 1), [])

    def test_cap_refusal(self):
        run, kit, d = self.mk(cap_tokens=8)                   # fake closure is 9 tokens
        tasks = arms.tasks_of(run, 'pilot', sorted(kit.arc_io.pilot_ids(4)))
        with self.assertRaises(arms.ArmError) as cm:
            arms.plant_solve_libraries(run, d / 'pilot' / 'PLANT_SOLVE', tasks)
        self.assertIn('PLANT_SOLVE_CAP_REFUSED', str(cm.exception))


@unittest.skipUnless(HAVE_ARCDSL, 'arc-dsl not on this machine')
class TestPlantSolveArcDsl(unittest.TestCase):
    def test_closures_fit_the_cap_and_are_pilot_only(self):
        from ratchet import arc_io, plant
        try:
            from ratchet import tok as tokmod
            tok = tokmod.load_tokenizer(config.MODEL_DIR)
        except Exception:  # noqa: BLE001
            tok = StubTokenizer()
        src = plant.load_arcdsl(ARCDSL)
        ids = sorted(arc_io.pilot_ids(config.PILOT_N, growth_ids=arc_io.growth_id_list()))
        worst = 0
        for t in ids:
            lib = plant.solver_library(src, t, tok)
            self.assertTrue(library.is_pilot_only(lib))
            _b, names, ntok = prompt.library_block(lib, config.LIBRARY_CAP_TOKENS, tok)
            self.assertEqual(set(names), {h.name for h in lib.helpers}, t)
            self.assertIn('solve_this', names)
            worst = max(worst, ntok)
            s = next(h.source for h in lib.helpers if h.name == 'solve_this')
            self.assertTrue(s.startswith("def solve_this(grid: 'Grid') -> 'Grid':\n    \"\"\"returns the output grid "
                                         "for this puzzle\"\"\""), s[:120])
        print('V2_PLANT_SOLVE tasks=%d max_block_tokens=%d tokenizer=%s' % (len(ids), worst, type(tok).__name__))
        self.assertLessEqual(worst, config.LIBRARY_CAP_TOKENS)


# ---------------------------------------------------------------------------------------------------------------------
# lever check refusal in the driver

class TestLeverAdapterDriver(_Base):
    def test_refuses_when_smoke_fails_and_prints_marker(self):
        run, kit, d = self.mk()
        lib_src = "def mostcolor(element: 'Element') -> 'Integer':\n    return 0\n"
        patch = mock.patch.object(F.FakeLibraryMod, 'render_py', staticmethod(lambda lib, names: lib_src))
        patch.start()
        self.addCleanup(patch.stop)
        kit.sandbox.adapter_smoke = lambda src, grid: {'grid_helpers': 1, 'list_smoke_ok': 0, 'ok': False,
                                                       'refused': ['mostcolor'], 'status': 'OK', 'error': None}
        lib = F.Library('PLANTL1', 1, [F.Helper('mostcolor', 'h', 3, ['a'], in_context=True)], None, {})
        spec = arms.ReqSpec(request_id='r', task=_task(split='pilot'), arm='PLANT1', phase='pilot', round=1,
                            sealed_seed=None, slots=[0], sample_ids=['PLANT1|pilot|r1|abcd0001|s0'], seed=1,
                            library=lib)
        client = F.FakeClient(d, 'j1')
        client.run = mock.Mock(side_effect=AssertionError('model called'))
        with self.assertRaises(arms.ArmError) as cm:
            arms.sample(run, [spec], d / 's.jsonl', client, Deadline(0.0, clock=lambda: 0.0), 'PLANT1', 'pilot', 1)
        self.assertIn('LEVER_ADAPTER_REFUSED', str(cm.exception))
        client.run.assert_not_called()
        log = (d / 'logs' / 'server_PLANT1_pilot_j1.log').read_text()
        self.assertIn('LEVER ADAPTER grid_helpers=1 list_smoke_ok=0', log)
        self.assertIn('LEVER INSTRUCTION sha=%s' % config.INSTRUCTION_F3_SHA256, log)


# ---------------------------------------------------------------------------------------------------------------------
# score_sealed: an amendment authorises a key read only if its own paragraph says it grants one

def _score_mod():
    spec = importlib.util.spec_from_file_location('score_sealed_v2_test', REPO / 'score_sealed.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestAmendmentKeyGrant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.S = _score_mod()

    def test_rule(self):
        text = ('# P\n\n## AMENDMENTS\n- AMENDMENT 0 (2026-11-04 16:47 ET): registered.\n'
                '- AMENDMENT 4 (2026-11-05 10:00 ET): the perturbed copy was built wrong; this amendment grants one\n'
                '  key access for the perturbed condition.\n'
                '- AMENDMENT 5 (2026-11-05 11:00 ET): harness fix. It grants no key access.\n')
        f = self.S.amendment_key_grant
        self.assertEqual(f(text, '4'), 'OK')
        self.assertEqual(f(text, '0'), 'GRANTS_NO_KEY_ACCESS')
        self.assertEqual(f(text, '5'), 'GRANTS_NO_KEY_ACCESS')
        self.assertEqual(f(text, '9'), 'NOT_IN_PREREG')
        self.assertEqual(f(text, ''), 'NOT_IN_PREREG')
        self.assertEqual(f(text.replace('## AMENDMENTS', '## NOTES'), '4'), 'NOT_IN_PREREG')
        # the phrase in ANOTHER amendment's paragraph does not leak into this one
        self.assertEqual(f(text, '0'), 'GRANTS_NO_KEY_ACCESS')

    def test_planned_v2_amendments_grant_nothing(self):
        # verbatim copy of the code block of RATCHET_V2_AMENDMENTS.md (the lead's file; not committed here)
        block = (Path(__file__).resolve().parent / 'fixtures' / 'ratchet_v2_amendments_block.txt').read_text(
            encoding='utf-8')
        self.assertIn('- AMENDMENT 3 (', block)
        text = '# PREREG\n\n## AMENDMENTS\n- AMENDMENT 0 (2026-11-04 16:47 ET): registered.\n' + block.strip() + '\n'
        for i in ('1', '2', '3'):
            self.assertIsNotNone(self.S.amendment_paragraph(text, i), i)
            self.assertEqual(self.S.amendment_key_grant(text, i), 'GRANTS_NO_KEY_ACCESS', i)

    def test_real_prereg_amendment_0_grants_nothing(self):
        self.assertEqual(self.S.amendment_key_grant((REPO / 'PREREG.md').read_text(encoding='utf-8'), '0'),
                         'GRANTS_NO_KEY_ACCESS')


if __name__ == '__main__':
    unittest.main()
