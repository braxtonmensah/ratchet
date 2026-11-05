"""`python -m ratchet <cmd>` (SPEC 6). Owner: builder D.

Only `score` touches the sealed key, and only by exec'ing into score_sealed.py (SPEC 8 layer 4). Commands:
  init, pilot, grow, step, perturb, freeze, sample-sealed, score, knockout, status, verdict, next,
  modelcheck (PREREG 3 weights fixed: sha256 of every model file at the first GPU job, size and mtime after),
  sandbox-selftest (SPEC 8 test 9 on this node; serve_and_step.sh runs it before every job)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from . import config, rounds
from .arms import Deadline


def _run(args, kit=None):
    from . import arms
    run = arms.load_run(Path(args.run), kit=kit)
    return run


def _job_start_ts() -> float:
    v = os.environ.get('RATCHET_JOB_START_TS')
    return float(v) if v else time.time()


def make_client(run, url: str | None):
    """The real vLLM client inside a job. Returns None when no server URL is given."""
    url = url or os.environ.get('RATCHET_VLLM_URL')
    if not url:
        return None
    from . import arms
    kit = arms.kit_of(run)
    ledger = kit.ledger.Ledger(rounds.ledger_dir(run) / ('ledger_%s.jsonl' % run.job_id))
    n = max(1, int(run.S or run.cfg.get('s_pilot', config.S_PILOT)))
    inflight = max(1, math.ceil(config.CLIENT_INFLIGHT_SEQS / n))
    model = os.environ.get('RATCHET_SERVED_MODEL', run.cfg.get('model', str(config.MODEL_DIR)))
    return kit.llm.VLLMClient(url, model, ledger, kit.tok, inflight, timeout_s=config.VLLM_REQUEST_TIMEOUT_S)


def cmd_init(args) -> int:
    from . import arms
    cfg = {}
    if args.skip_pilot:
        cfg['skip_pilot'] = True
    run = arms.init_run(Path(args.run), S=args.S, R=args.R, seed_base=args.seed_base, **cfg)
    print(json.dumps(run.cfg, sort_keys=True))
    return 0


def cmd_step(args) -> int:
    from . import arms
    run = _run(args)
    client = None if args.no_gpu else make_client(run, args.url)
    deadline = Deadline(_job_start_ts())
    if client is not None and hasattr(client, 'wait_ready'):
        client.wait_ready(config.VLLM_READY_TIMEOUT_S)
    arms.step(run, client, deadline)
    return 0


def cmd_pilot(args) -> int:
    from . import arms
    run = _run(args)
    deadline = Deadline(_job_start_ts())
    which = {'smoke': ('FLAT_A', 'FLAT_B'), 'plant': ('PLANT1',), 'all': config.PILOT_WHICH}.get(args.step, ())
    if which:
        client = make_client(run, args.url)
        for w in which:
            arms.run_pilot_round(run, w, client, deadline)
    if args.step == 'rates':
        print(json.dumps(arms.kit_of(run).pilot.step3_rates(Path(run.dir)), sort_keys=True, default=str))
    if args.step in ('choose', 'all'):
        if all(rounds.unit_done(run, rounds.WorkUnit('pilot', w, 'pilot', None, None, w)) for w in config.PILOT_WHICH):
            arms.pilot_choose(run)
        else:
            print('PILOT_NOT_DONE (pilot rounds incomplete)')
            return 1
    return 0


def cmd_grow(args) -> int:
    from . import arms
    run = _run(args)
    if args.finalize:
        print(arms.finalize_round(run, args.arm, args.round, arms.kit_of(run).tok))
        return 0
    client = make_client(run, args.url)
    deadline = Deadline(_job_start_ts())
    rs = [args.round] if args.round else range(1, (1 if args.arm == 'ONESHOT' else run.R) + 1)
    for r in rs:
        state = arms.grow_round(run, args.arm, r, client, deadline)
        print('GROW %s r=%d %s' % (args.arm, r, state))
        if state != 'FROZEN':
            return 1
    return 0


def cmd_perturb(args) -> int:
    from . import arms
    run = _run(args)
    if args.build:
        arms.build_perturbed(run)
    return 0


def cmd_freeze(args) -> int:
    from . import freeze
    run = _run(args)
    if args.ack:
        print(freeze.ack(run, args.name, args.ack))
        return 0
    if args.submissions:
        p, sha = freeze.freeze_submissions(run)
    elif args.knockout:
        p, sha = freeze.freeze_knockout(run)
    else:
        p, sha = freeze.freeze_libraries(run)
    print('%s %s' % (sha, p))
    return 0


def cmd_sample_sealed(args) -> int:
    from . import arms
    run = _run(args)
    client = make_client(run, args.url)
    deadline = Deadline(_job_start_ts())
    arms.sample_sealed(run, args.arm, args.seed, args.condition, client, deadline)
    if args.arm == config.FLAT_ARM and args.condition in ('sealed', 'perturbed'):
        arms.sample_flat_extra(run, args.seed, args.condition, client, deadline)
    elif args.arm == config.FLAT_ARM:
        st = rounds.load_state(arms.sealed_out_dir(run, args.arm, args.seed, args.condition))
        if st.get('state') == 'BASE_DONE':        # arcagi2: no token match is registered; submit the base pass
            arms.write_submissions(run, args.arm, args.seed, args.condition)
            st['state'] = 'DONE'
            rounds.save_state(arms.sealed_out_dir(run, args.arm, args.seed, args.condition), st)
    return 0


def cmd_score(args) -> int:
    """Exec into score_sealed.py: this process never opens the key itself."""
    exe = sys.executable
    # no -I: it implies -P, which would drop the repo root from sys.path and score_sealed.py could not import ratchet
    argv = [exe, str(config.SCORE_SEALED_PY), 'score', '--run', str(args.run), '--condition', args.condition,
            '--freeze-sha', args.freeze_sha, '--submit-sha', args.submit_sha]
    if getattr(args, 'amendment', None):
        argv += ['--amendment', args.amendment]
    sys.stdout.flush()
    os.execv(exe, argv)
    return 0  # pragma: no cover


def cmd_knockout(args) -> int:
    from . import arms
    run = _run(args)
    if args.build:
        arms.build_knockout(run)
    if args.sample:
        client = make_client(run, args.url)
        deadline = Deadline(_job_start_ts())
        for mode in ('delete', 'inline'):
            for k in rounds.sealed_seeds(run):
                arms.sample_knockout(run, mode, k, client, deadline)
    return 0


def cmd_status(args) -> int:
    from . import arms
    run = _run(args)
    arms.write_run_status(run)
    print((Path(run.dir) / 'STATUS.json').read_text())
    if args.map:
        rep = arms.kit_of(run).report
        fn = getattr(rep, 'render_map', None) or getattr(rep, 'byte_map', None)
        if fn is None:
            print('report.py has no map function')
            return 1
        out = fn(Path(run.dir))
        if out is not None:
            print(out if isinstance(out, str) else json.dumps(out, sort_keys=True, indent=1, default=str))
    return 0


def cmd_verdict(args) -> int:
    from . import arms
    run = _run(args)
    print(arms.kit_of(run).verdict.write_result(Path(run.dir), config.REPO_DIR))
    return 0


def chain_ok(run) -> dict:
    """Whether a job should be (re)submitted: work remains, it is not a lead or score gate, and the last two jobs did
    not both fail (a failing step must not chain forever)."""
    u = rounds.next_unit(run)
    st = rounds.read_json(Path(run.dir) / 'STATUS.json', {}) or {}
    jobs = st.get('jobs', [])
    failed_twice = len(jobs) >= 2 and all(j.get('state') == 'FAILED' for j in jobs[-2:])
    return {'next': u.to_dict() if u else None, 'gpu': bool(u and u.gpu), 'manual': bool(u and u.manual),
            'chain': bool(u and not u.manual and not failed_twice), 'failed_twice': failed_twice}


def cmd_modelcheck(args) -> int:
    from . import arms
    run = _run(args)
    try:
        out = arms.model_check(run)
    except arms.ArmError as e:
        print('MODELCHECK FAIL %s' % e, flush=True)
        return 3
    print('MODELCHECK %s' % ' '.join('%s=%s' % (k, v) for k, v in sorted(out.items())), flush=True)
    return 0


def cmd_sandbox_selftest(args) -> int:
    from . import sandbox
    try:
        res = sandbox.selftest()
    except sandbox.SandboxIsolationError as e:
        print('SANDBOX_SELFTEST FAIL %s' % e, flush=True)
        return 4
    return 0 if res['pass'] else 4


def cmd_next(args) -> int:
    run = _run(args)
    print(json.dumps(chain_ok(run), sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='ratchet')
    sub = p.add_subparsers(dest='cmd', required=True)

    def add(name, fn, url=False):
        sp = sub.add_parser(name)
        sp.add_argument('--run', required=True)
        if url:
            sp.add_argument('--url', default=None, help='vLLM base url (default $RATCHET_VLLM_URL)')
        sp.set_defaults(fn=fn)
        return sp

    sp = add('init', cmd_init)
    sp.add_argument('--S', type=int, default=None)
    sp.add_argument('--R', type=int, default=None)
    sp.add_argument('--seed-base', type=int, default=config.SEED_BASE)
    sp.add_argument('--skip-pilot', action='store_true')
    sp = add('step', cmd_step, url=True)
    sp.add_argument('--no-gpu', action='store_true')
    sp = add('pilot', cmd_pilot, url=True)
    sp.add_argument('--step', choices=('smoke', 'plant', 'rates', 'choose', 'all'), default='all')
    sp = add('grow', cmd_grow, url=True)
    sp.add_argument('--arm', required=True, choices=config.GROWTH_SAMPLING_ARMS)
    sp.add_argument('--round', type=int, default=None)
    sp.add_argument('--finalize', action='store_true')
    sp = add('perturb', cmd_perturb)
    sp.add_argument('--build', action='store_true')
    sp = add('freeze', cmd_freeze)
    g = sp.add_mutually_exclusive_group()
    g.add_argument('--submissions', action='store_true')
    g.add_argument('--knockout', action='store_true')
    g.add_argument('--ack', default=None, metavar='SHA256')
    sp.add_argument('--name', default='FREEZE', choices=config.FREEZE_NAMES)
    sp = add('sample-sealed', cmd_sample_sealed, url=True)
    sp.add_argument('--arm', required=True, choices=config.ARMS)
    sp.add_argument('--seed', type=int, required=True)
    sp.add_argument('--condition', choices=('sealed', 'perturbed', 'arcagi2'), default='sealed')
    sp = add('score', cmd_score)
    sp.add_argument('--condition', required=True, choices=('primary', 'knockout', 'arcagi2'))
    sp.add_argument('--freeze-sha', required=True)
    sp.add_argument('--submit-sha', required=True)
    sp.add_argument('--amendment', default=None)
    sp = add('knockout', cmd_knockout, url=True)
    sp.add_argument('--build', action='store_true')
    sp.add_argument('--sample', action='store_true')
    sp = add('status', cmd_status)
    sp.add_argument('--map', action='store_true')
    add('verdict', cmd_verdict)
    add('next', cmd_next)
    add('modelcheck', cmd_modelcheck)
    st = sub.add_parser('sandbox-selftest')
    st.set_defaults(fn=cmd_sandbox_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == '__main__':
    sys.exit(main())
