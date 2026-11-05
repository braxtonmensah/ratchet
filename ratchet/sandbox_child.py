"""Sandbox child (SPEC 5 builder A, 8 layer 5). Owner: builder A.

Run as `python -I -B sandbox_child.py` (stdlib only; never imports the ratchet package; -I keeps this directory, which
holds ratchet/types.py and ratchet/select.py, off sys.path so they cannot shadow the stdlib) with cwd = a fresh temp dir
and one JSON request on stdin. With `--zygote` it is a pre-fork server instead (see zygote()); each request then runs in
its own forked process with the same steps. Writes JSON lines to the original stdout fd: one {"ev": "in", ...} per input as it finishes,
then one {"ev": "done", ...}. The program's own prints go to the parent's stderr sink (DEVNULL).

Order: rlimits, optional numpy pre-import, audit hook, then library exec (skipped in mode 'inline'), program exec, demos
(stop at the first failure), test inputs (only if every demo passed; helper calls counted on test inputs only).
Per input: signal.setitimer(ITIMER_REAL, timeout_s); a timed-out input is TIMEOUT.

Harness v2 (PLANT_FAIL_DIAGNOSIS 4.1): the library runs in its own namespace and reaches the program through the type
adapter (_adapt): arguments at parameters annotated Grid, Element or Piece that are non-empty lists of rows go in as
tuples of tuples, tuple-of-tuples results of functions so annotated come back as lists of lists, and every other helper
is the same function object. Call counting wraps the functions inside the library namespace, as in v1. The request key
`adapter` (default true) exists only so tests can reproduce the v1 boundary; no driver path sets it.
"""
import builtins
import functools
import json
import operator
import os
import resource
import signal
import sys
import time


class _Timeout(BaseException):
    pass


class _Bad(Exception):
    pass


def _make_hook(tmp, read_roots, deny_roots, blocked_imports):
    tmp = os.path.realpath(tmp)
    read_roots = tuple(os.path.realpath(r) for r in read_roots if r)
    deny_roots = tuple(os.path.realpath(r) for r in deny_roots if r)
    blocked = frozenset(blocked_imports)
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    dev_ok = frozenset(('/dev/null', '/dev/urandom', '/dev/random'))
    proc_events = frozenset(('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn', 'os.fork',
                             'os.forkpty', 'pty.spawn', 'os.startfile', 'os.kill', 'os.killpg', 'signal.pthread_kill',
                             'sys._current_frames', 'os.chdir', 'os.fchdir', 'os.chroot', 'resource.setrlimit',
                             'resource.prlimit', 'os.setuid', 'os.setgid', 'os.putenv', 'os.unsetenv', 'mmap.__new__',
                             'os.unshare', 'os.setns', 'os.pidfd_open', 'os.memfd_create', 'os.eventfd',
                             'sys.remote_exec', 'sys.setprofile', 'sys.settrace', 'sys.addaudithook',
                             'socket.sethostname', 'os.add_dll_directory', 'ctypes.dlopen', 'os.ptsname'))
    mutate_events = frozenset(('os.remove', 'os.rename', 'os.mkdir', 'os.rmdir', 'os.chmod', 'os.chown', 'os.link',
                               'os.symlink', 'os.truncate', 'os.utime', 'os.chflags', 'os.lchflags', 'os.setxattr',
                               'os.removexattr', 'shutil.copyfile', 'shutil.copymode', 'shutil.copystat',
                               'shutil.copytree', 'shutil.move', 'shutil.rmtree', 'shutil.chown',
                               'shutil.make_archive', 'shutil.unpack_archive', 'os.mkfifo', 'os.mknod'))
    list_events = frozenset(('os.listdir', 'os.scandir', 'glob.glob', 'glob.glob/2', 'os.walk', 'pathlib.Path.glob',
                             'pathlib.Path.rglob', 'os.fwalk'))
    realpath = os.path.realpath
    fsdecode = os.fsdecode
    sep = os.sep

    def under(p, root):
        return p == root or p.startswith(root.rstrip(sep) + sep)

    def resolve(a):
        if isinstance(a, bytes):
            a = fsdecode(a)
        return realpath(a)

    def readable(p):
        if any(under(p, d) for d in deny_roots):
            return False
        return p in dev_ok or under(p, tmp) or any(under(p, r) for r in read_roots)

    def writable(p):
        if any(under(p, d) for d in deny_roots):
            return False
        return under(p, tmp) or p == '/dev/null'

    def hook(event, args):
        if event == 'open':
            path = args[0] if args else None
            if path is None or isinstance(path, int):
                return
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            w = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or bool((flags or 0) & write_flags)
            p = resolve(path)
            if not (writable(p) if w else readable(p)):
                raise PermissionError(f'SANDBOX_REFUSED open {"write" if w else "read"} {p}')
            return
        if event == 'import':
            mod = args[0] if args else ''
            if isinstance(mod, str) and mod.split('.')[0] in blocked:
                raise ImportError(f'SANDBOX_REFUSED import {mod}')
            return
        if event.startswith('socket.') or event.startswith('ctypes.') or event.startswith('gc.get_r') \
                or event == 'gc.get_objects' or event in proc_events:
            raise PermissionError(f'SANDBOX_REFUSED {event}')
        if event in mutate_events:
            for a in args:
                if isinstance(a, (str, bytes)) and not writable(resolve(a)):
                    raise PermissionError(f'SANDBOX_REFUSED {event} {a!r}')
            return
        if event in list_events:
            a = args[0] if args else None
            if isinstance(a, (str, bytes)) and not readable(resolve(a)):
                raise PermissionError(f'SANDBOX_REFUSED {event} {a!r}')
            return

    return hook


def _norm(out, max_side, n_colours):
    """Program output -> list of lists of int. Raises _Bad('shape' | 'side' | 'type' | 'colour')."""
    if hasattr(out, 'tolist') and not isinstance(out, (list, tuple)):
        out = out.tolist()
    if not isinstance(out, (list, tuple)):
        raise _Bad('shape')
    if len(out) == 0:
        raise _Bad('shape')
    if len(out) > max_side:
        raise _Bad('side')
    rows = []
    width = None
    for r in out:
        if hasattr(r, 'tolist') and not isinstance(r, (list, tuple)):
            r = r.tolist()
        if not isinstance(r, (list, tuple)) or len(r) == 0:
            raise _Bad('shape')
        if len(r) > max_side:
            raise _Bad('side')
        if width is None:
            width = len(r)
        elif len(r) != width:
            raise _Bad('shape')
        row = []
        for v in r:
            if isinstance(v, bool) or type(v).__name__ == 'bool_':
                raise _Bad('type')
            try:
                iv = operator.index(v)
            except TypeError:
                raise _Bad('type') from None
            if iv < 0 or iv >= n_colours:
                raise _Bad('colour')
            row.append(iv)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------------------------------------------------
# type adapter (harness v2; PLANT_FAIL_DIAGNOSIS 4.1). Same rule as ratchet/adapter.py (this file never imports the
# package); tests/test_v2_adapter.py checks the two copies agree.

_GRID_TYPES = frozenset(('Grid', 'Element', 'Piece'))


def _is_grid_ann(a):
    # A string annotation. Under `from __future__ import annotations` a quoted 'Grid' arrives as "'Grid'" and a bare
    # Grid as 'Grid'; both count (ratchet/adapter.py reads the source the same way).
    return isinstance(a, str) and a.strip().strip('\'"').strip() in _GRID_TYPES


def _grid_sig(fn):
    """(positional indices, keyword names, return) that are grid-typed by fn's own annotations, or None."""
    try:
        ann = dict(getattr(fn, '__annotations__', None) or {})
    except Exception:  # noqa: BLE001  (a hostile __annotations__ property)
        return None
    code = getattr(fn, '__code__', None)
    if code is None or not ann:
        return None
    npos = code.co_argcount
    nkw = code.co_kwonlyargcount
    names = code.co_varnames[:npos + nkw]
    pos = tuple(i for i, nm in enumerate(names[:npos]) if _is_grid_ann(ann.get(nm)))
    kw = frozenset(nm for nm in names[code.co_posonlyargcount:] if _is_grid_ann(ann.get(nm)))
    ret = _is_grid_ann(ann.get('return'))
    if not pos and not kw and not ret:
        return None
    return pos, kw, ret


def _to_tuple_grid(x):
    if isinstance(x, list) and x and all(isinstance(r, (list, tuple)) for r in x):
        return tuple(tuple(r) for r in x)
    return x


def _to_list_grid(x):
    if isinstance(x, tuple) and x and all(isinstance(r, tuple) for r in x):
        return [list(r) for r in x]
    return x


_CO_VARARGS = 0x04
_CO_VARKEYWORDS = 0x08


def _clone_signature(fn, impl):
    """A function with fn's exact parameter list (so fn.__code__.co_argcount and friends are preserved) that calls
    impl(*positional, *varargs, kwonly=..., **varkw). arc-dsl's rbind / lbind pick a lambda's arity from
    function.__code__.co_argcount, so a bare (*a, **k) wrapper (v1's call counter) breaks every solver that binds a
    library function (harness v2 finding: 19 of 50 pilot solvers). Falls back to a (*a, **k) wrapper for callables
    without a plain code object."""
    code = getattr(fn, '__code__', None)
    if code is None or not hasattr(code, 'co_varnames'):
        @functools.wraps(fn)
        def generic(*a, **k):
            return impl(*a, **k)
        return generic
    npos, nposonly, nkw = code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount
    names = code.co_varnames
    pos = list(names[:npos])
    kwo = list(names[npos:npos + nkw])
    i = npos + nkw
    star = names[i] if code.co_flags & _CO_VARARGS else None
    i += 1 if star else 0
    dstar = names[i] if code.co_flags & _CO_VARKEYWORDS else None
    allp = pos + kwo + [n for n in (star, dstar) if n]
    if '_rt_impl' in allp or not all(isinstance(n, str) and n.isidentifier() for n in allp):
        @functools.wraps(fn)
        def generic2(*a, **k):
            return impl(*a, **k)
        return generic2
    parts = pos[:nposonly] + (['/'] if nposonly else []) + pos[nposonly:]
    if star:
        parts.append('*' + star)
    elif kwo:
        parts.append('*')
    parts += kwo
    if dstar:
        parts.append('**' + dstar)
    call = pos + (['*' + star] if star else []) + ['%s=%s' % (k, k) for k in kwo] + (['**' + dstar] if dstar else [])
    ns = {'_rt_impl': impl}
    exec('def _rt_w(%s):\n    return _rt_impl(%s)\n' % (', '.join(parts), ', '.join(call)), ns)
    w = ns['_rt_w']
    w.__defaults__ = getattr(fn, '__defaults__', None)
    w.__kwdefaults__ = getattr(fn, '__kwdefaults__', None)
    functools.update_wrapper(w, fn)
    return w


def _adapt(fn, sig):
    """The program-side view of library function fn: identity (the same object) when sig is None."""
    if sig is None:
        return fn
    pos, kw, ret = sig

    def adapted(*args, **kwargs):
        if pos:
            args = list(args)
            for i in pos:
                if i < len(args):
                    args[i] = _to_tuple_grid(args[i])
        for k in kw:
            if k in kwargs:
                kwargs[k] = _to_tuple_grid(kwargs[k])
        out = fn(*args, **kwargs)
        return _to_list_grid(out) if ret else out
    return _clone_signature(fn, adapted)


def _emit_fd(fd, obj):
    data = (json.dumps(obj, separators=(',', ':')) + '\n').encode()
    while data:
        n = os.write(fd, data)
        data = data[n:]


def zygote():
    """Pre-fork server: import numpy once, then fork one fresh child per request line on stdin.
    Per request: {"ev": "pid"} line, the child's own lines, then {"ev": "end", "rc": int}. The zygote never runs
    program code; every child is a fork of the same clean state, so programs cannot see each other."""
    import shutil
    import tempfile
    try:
        import numpy  # noqa: F401
    except Exception:  # noqa: BLE001
        pass
    base = os.getcwd()
    _emit_fd(1, {'ev': 'ready', 'pid': os.getpid()})
    stdin = sys.stdin.buffer
    while True:
        line = stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
        except ValueError:
            _emit_fd(1, {'ev': 'end', 'rc': 65})
            continue
        tmp = tempfile.mkdtemp(prefix='p', dir=base)
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(w)
                os.read(r, 1)        # wait until the zygote has written the pid line
                os.close(r)
                os.close(0)
                os.chdir(tmp)
                run_request(req)     # ends with os._exit
            except BaseException:   # noqa: BLE001
                pass
            os._exit(70)
        os.close(r)
        _emit_fd(1, {'ev': 'pid', 'pid': pid})
        os.write(w, b'x')
        os.close(w)
        _, status = os.waitpid(pid, 0)
        rc = -os.WTERMSIG(status) if os.WIFSIGNALED(status) else os.WEXITSTATUS(status)
        shutil.rmtree(tmp, ignore_errors=True)
        _emit_fd(1, {'ev': 'end', 'rc': rc})


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--zygote':
        zygote()
        return
    run_request(json.loads(sys.stdin.buffer.read()))


def run_request(req):
    out_fd = os.dup(1)
    os.dup2(2, 1)   # program prints go wherever stderr goes (the parent passes DEVNULL)

    class _Sink:
        def write(self, s):
            return len(s)

        def flush(self):
            pass

    sys.stdout = _Sink()
    sys.stderr = _Sink()

    def emit(obj):
        _emit_fd(out_fd, obj)

    timeout_s = float(req['timeout_s'])
    demos = req['demos']
    tests = req['tests']
    n_inputs = len(demos) + len(tests)
    mem = int(req['mem_mb']) * 1024 * 1024
    # One timeout_s window per input plus one each for the library exec and the program's top-level exec (the same
    # total as the parent's hard kill), plus interpreter start and imports (review fix 2026-11-04).
    agg = int(req.get('agg_windows', 2))
    cpu = int(timeout_s * (n_inputs + agg) + 1.0 + float(req.get('import_pad_s', 2.0)) + 0.999)
    fsize = int(req.get('fsize_mb', 16)) * 1024 * 1024
    for lim, val in ((resource.RLIMIT_AS, mem), (resource.RLIMIT_CPU, cpu), (resource.RLIMIT_FSIZE, fsize),
                     (resource.RLIMIT_CORE, 0)):
        try:
            soft, hard = resource.getrlimit(lim)
            hv = val if lim != resource.RLIMIT_CPU else val + 1
            if hard != resource.RLIM_INFINITY:
                hv = min(hv, hard)
                val = min(val, hv)
            resource.setrlimit(lim, (val, hv))
        except (ValueError, OSError):
            pass

    code = req['code']
    lib = req['library_src'] or ''
    mode = req['mode']
    if req.get('preimport_numpy'):
        try:
            import numpy  # noqa: F401  (before the hook: numpy's own imports touch ctypes)
        except Exception:
            pass

    allow = frozenset(req['allow_imports'])
    state = {'fired': False, 'armed': False, 'counting': False, 'refused_import': None}
    calls = {}

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split('.')[0]
        if level != 0 or root not in allow:
            if state['refused_import'] is None:
                state['refused_import'] = name if level == 0 else '.' + name
            raise ImportError(f'IMPORT_REFUSED:{name}')
        return real_import(name, globals, locals, fromlist, level)

    safe_builtins = dict(builtins.__dict__)
    safe_builtins['__import__'] = guarded_import
    for k in ('input', 'breakpoint', 'help', 'exit', 'quit'):
        safe_builtins.pop(k, None)

    def on_alarm(signum, frame):
        # Integration fix 2026-11-04: under load the Python-level handler can run AFTER timed() disarmed the timer
        # (the C handler only sets a flag; the re-armed 0.05 s alarm lands late), raising _Timeout outside timed():
        # the child then died with rc 70 (zygote) or 1 (spawn) and a timeout was recorded as ERROR CHILD_EXIT:70
        # (seen in the full suite at load average 14.5). Outside a timed call the alarm is ignored.
        if not state['armed']:
            return
        state['fired'] = True
        signal.setitimer(signal.ITIMER_REAL, 0.05)   # fire again if a bare except swallowed it
        raise _Timeout()

    signal.signal(signal.SIGALRM, on_alarm)

    tmp = os.getcwd()
    read_roots = [sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix]
    read_roots += [p for p in sys.path if p and os.path.isabs(p) and os.path.isdir(p)]
    hook = _make_hook(tmp, read_roots, req.get('deny_roots') or [], req['blocked_imports'])
    sys.addaudithook(hook)
    del hook

    max_side = int(req.get('max_side', 30))
    n_colours = int(req.get('n_colours', 10))
    res = {'ev': 'done', 'status': 'OK', 'demo_pass': False, 'n_demo_pass': 0, 'first_fail_demo': None,
           'test_outputs': None, 'helper_calls': {}, 'wall_s': [], 'timeouts': 0, 'error': None,
           'helpers_callable': 0}

    def timed(fn, *a):
        state['fired'] = False
        t0 = time.perf_counter()
        try:
            state['armed'] = True
            signal.setitimer(signal.ITIMER_REAL, timeout_s)
            try:
                v = fn(*a)
            finally:
                while True:     # a late _Timeout raised before the disarm lands here; retry until disarmed
                    try:
                        state['armed'] = False
                        signal.setitimer(signal.ITIMER_REAL, 0)
                        break
                    except _Timeout:
                        state['fired'] = True
        except _Timeout:
            return None, 'TIMEOUT', None, time.perf_counter() - t0
        except BaseException as e:   # noqa: BLE001  (SystemExit, MemoryError, RecursionError, anything)
            if state['fired']:
                return None, 'TIMEOUT', None, time.perf_counter() - t0
            return None, 'ERROR', f'{type(e).__name__}:{str(e)[:160]}', time.perf_counter() - t0
        if state['fired']:
            return None, 'TIMEOUT', None, time.perf_counter() - t0
        return v, 'OK', None, time.perf_counter() - t0

    def finish(status, error=None):
        res['status'] = status
        if error is None and state['refused_import'] is not None:
            error = f'IMPORT_REFUSED:{state["refused_import"]}'
        res['error'] = error
        res['helper_calls'] = dict(sorted(calls.items()))
        emit(res)
        os._exit(0)

    g = {'__name__': '__ratchet_program__', '__builtins__': safe_builtins}

    # library (harness v2, PLANT_FAIL_DIAGNOSIS 4.1): executed in its own namespace lib_g, so library-internal calls
    # resolve inside lib_g and arc-dsl's own tuple dispatch is never disturbed. The call counters wrap the functions IN
    # lib_g (internal calls are still counted: helper_calls semantics unchanged). The program's globals g then receive
    # every public library name: functions through _adapt (identity unless the helper's own annotations name a grid
    # type), every other value as is (as in v1, where the library ran in g).
    lib_names = []
    if mode != 'inline' and lib.strip():
        lib_g = {'__name__': '__ratchet_library__', '__builtins__': safe_builtins}
        try:
            lib_code = compile(lib, '<library>', 'exec')
        except BaseException as e:   # noqa: BLE001
            finish('ERROR', f'LIBRARY_SYNTAX:{type(e).__name__}')
        _, st, err, _w = timed(exec, lib_code, lib_g)
        if st != 'OK':
            finish('ERROR' if st == 'ERROR' else 'TIMEOUT', f'LIBRARY:{err}' if st == 'ERROR' else 'LIB_TIMEOUT')
        lib_names = [k for k, v in lib_g.items()
                     if callable(v) and getattr(getattr(v, '__code__', None), 'co_filename', None) == '<library>']
        res['helpers_callable'] = len(lib_names)
        trace = req.get('trace')
        names = lib_names if not trace else [n for n in trace if n in lib_g and callable(lib_g[n])]
        sigs = {n: _grid_sig(lib_g[n]) for n in lib_names}

        def wrap(name, fn):
            def w(*a, **k):
                if state['counting']:
                    calls[name] = calls.get(name, 0) + 1
                return fn(*a, **k)
            return _clone_signature(fn, w)   # same counting as v1, with fn's own signature (rbind / lbind arity)

        for n in names:
            lib_g[n] = wrap(n, lib_g[n])
        adapt_on = bool(req.get('adapter', True))
        for k, v in lib_g.items():
            if k.startswith('__') and k.endswith('__'):
                continue
            if k in sigs and adapt_on:
                g[k] = _adapt(v, sigs[k])
            else:
                g[k] = v

    # program
    try:
        prog = compile(code, '<program>', 'exec')
    except BaseException as e:   # noqa: BLE001  (the parent checks syntax first; this is a backstop)
        finish('SYNTAX', f'{type(e).__name__}')
    _, st, err, _w = timed(exec, prog, g)
    if st != 'OK':
        finish(st, f'PROGRAM:{err}' if err else ('PROGRAM_TIMEOUT' if st == 'TIMEOUT' else None))
    fn = g.get('transform')
    if not callable(fn):
        finish('ERROR', 'NO_TRANSFORM')

    def run_one(grid):
        return fn([list(r) for r in grid])

    n_pass = 0
    for i, (gin, gout) in enumerate(demos):
        v, st, err, w = timed(run_one, gin)
        res['wall_s'].append(round(w, 5))
        if st == 'OK':
            try:
                v = _norm(v, max_side, n_colours)
            except _Bad as b:
                st, err = 'BAD_OUTPUT', f'BAD_OUTPUT:{b}'
            except BaseException as e:   # noqa: BLE001  (a hostile __len__ or tolist)
                st, err = 'BAD_OUTPUT', f'BAD_OUTPUT:{type(e).__name__}'
        if st == 'OK' and v != gout:
            st = 'DEMO_FAIL'
        emit({'ev': 'in', 'k': 'demo', 'i': i, 'st': st})
        if st != 'OK':
            res['first_fail_demo'] = i
            res['n_demo_pass'] = n_pass
            if st == 'TIMEOUT':
                res['timeouts'] += 1
            finish(st, err)
        n_pass += 1
    res['n_demo_pass'] = n_pass
    res['demo_pass'] = True

    outs = []
    state['counting'] = True
    for i, gin in enumerate(tests):
        v, st, err, w = timed(run_one, gin)
        res['wall_s'].append(round(w, 5))
        if st == 'OK':
            try:
                v = _norm(v, max_side, n_colours)
            except _Bad as b:
                st, err = 'BAD_OUTPUT', f'BAD_OUTPUT:{b}'
            except BaseException as e:   # noqa: BLE001
                st, err = 'BAD_OUTPUT', f'BAD_OUTPUT:{type(e).__name__}'
        emit({'ev': 'in', 'k': 'test', 'i': i, 'st': st})
        if st != 'OK':
            state['counting'] = False
            if st == 'TIMEOUT':
                res['timeouts'] += 1
            finish(st, f'TEST:{err}' if err else 'TEST')
        outs.append(v)
    state['counting'] = False
    res['test_outputs'] = outs
    finish('OK', None)


if __name__ == '__main__':
    main()
