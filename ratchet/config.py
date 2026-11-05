"""All constants and paths for ratchet_v1 (PREREG silicyte-0119). Owner: builder D.

Every number any module uses comes from here (SPEC preamble). Other builders add their own constants in the section
marked for them; nothing here is ever read from a sealed file. This module must not name the sealed key location (that
lives only in guard.py and score_sealed.py, SPEC 8 static test 8).
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------------------------------------------------
# Registration
PREREG_ID = 'silicyte-0119'
PREREG_NAME = 'ratchet_v1'
PREREG_COMMIT = 'cc5fb5b'

# ---------------------------------------------------------------------------------------------------------------------
# Paths (Quartz). RATCHET_ROOT may be overridden for CPU tests; the guard's roots are hardcoded in guard.py.
SILO_ROOT = Path(os.environ.get('RATCHET_ROOT', '/N/scratch/bsmensah/silo/ratchet'))
CODE_DIR = SILO_ROOT / 'code'
DATA_DIR = SILO_ROOT / 'data'
RUNS_DIR = SILO_ROOT / 'runs'
REPO_DIR = Path(__file__).resolve().parent.parent
SPLITS_DIR = REPO_DIR / 'splits'
SCORE_SEALED_PY = REPO_DIR / 'score_sealed.py'
GROWTH_IDS_FILE = SPLITS_DIR / 'growth_ids_arcagi1_train.txt'
SEALED_IDS_FILE = SPLITS_DIR / 'sealed_ids_arcagi1_eval.txt'
ATTEMPTS_FILE = RUNS_DIR / 'ATTEMPTS.json'
# The real silo tree, NOT overridable by RATCHET_ROOT: production checks (test switches, stub tokenizer, sandbox) use it.
REAL_SILO_ROOT = Path('/N/scratch/bsmensah/silo/ratchet')
REAL_RUNS_DIR = REAL_SILO_ROOT / 'runs'
FREEZE_NAMES = ('FREEZE', 'SUBMIT_FREEZE', 'KO_FREEZE', 'A2_SUBMIT_FREEZE')
LEVER_CHECK_PY = 'C:/Users/bmens/NQ_local/lane/lever_check.py'

# ---------------------------------------------------------------------------------------------------------------------
# Data (PREREG 2)
ARCAGI1_REPO = 'https://github.com/fchollet/ARC-AGI'
ARCAGI1_COMMIT = '399030444e0ab0cc8b4e199870fb20b863846f34'
ARCDSL_REPO = 'https://github.com/michaelhodel/arc-dsl'
GROWTH_IDS_SHA256 = 'c4e1b145daad71b4f02ac3482be215f1ab07863b67f13fc1bde1572f501ff75a'
SEALED_IDS_SHA256 = '911bf838d8843606d5fc1ba0550a0c23670027bf8f6e32e4e4fbf93854957ddd'
N_GROWTH = 400
N_SEALED = 400
SPLITS = ('growth', 'pilot', 'sealed', 'sealed_perturbed', 'arcagi2_sealed')
GRID_MAX_SIDE = 30
N_COLOURS = 10

# ---------------------------------------------------------------------------------------------------------------------
# Model and sampling (PREREG 3; SPEC 13 I14)
MODEL_DIR = Path('/N/scratch/bsmensah/arc26/tufa/models/qwen36_35b_a3b_fp8')
MODEL_NAME = 'qwen36_35b_a3b_fp8'
ENV_VLLM_SH = '/N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh'
TEMPERATURE = 0.8
TOP_P = 0.95
MAX_TOKENS = 4096
ENABLE_THINKING = False
SAMPLING = {'temperature': TEMPERATURE, 'top_p': TOP_P, 'max_tokens': MAX_TOKENS, 'enable_thinking': ENABLE_THINKING}

# vLLM server inside the job (SPEC 5 Slurm, 1.6 item 4)
VLLM_HOST = '127.0.0.1'
VLLM_MAX_MODEL_LEN = 20480
VLLM_MAX_NUM_SEQS = 256
VLLM_GPU_MEM_UTIL = 0.90
VLLM_SEED = 0
VLLM_READY_TIMEOUT_S = 900
VLLM_REQUEST_TIMEOUT_S = 900
VLLM_KILL_GRACE_S = 30
# Client concurrency counts sequences: in-flight requests = ceil(CLIENT_INFLIGHT_SEQS / n).
CLIENT_INFLIGHT_SEQS = 320

# ---------------------------------------------------------------------------------------------------------------------
# Arms (PREREG 4; SPEC 5 builder D)
ARMS = ('STOCK', 'STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'FLATTTC', 'PLANTDRIP', 'PLANTL1')
LIBRARY_ARMS = ('STOCK', 'STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'PLANTDRIP', 'PLANTL1')   # the 7 sealed library arms
GROWTH_SAMPLING_ARMS = ('STOCK', 'STATIC', 'ONESHOT', 'EXEMPLAR')                          # SPEC 13 I5
SHARED_ROUND1_ARMS = ('STATIC', 'EXEMPLAR')                                               # SPEC 13 I3
PERTURBED_ARMS = ('STOCK', 'FLATTTC')                                                     # PREREG 6.4
FLAT_ARM = 'FLATTTC'
PILOT_WHICH = ('FLAT_A', 'FLAT_B', 'PLANT1')

# ---------------------------------------------------------------------------------------------------------------------
# Library, acceptance, SHAM, EXEMPLAR, PLANT (PREREG 4; SPEC 13 I5 to I8, I17)
LIBRARY_CAP_TOKENS = 6000
ACCEPT_MIN_TASKS = 2
ACCEPT_MIN_MDL = 20
EXEMPLAR_K = 3
SHAM_TOKEN_TOL = 0.05
SHAM_SHUFFLE_TRIGGER = 0.95
SHAM_SEED = 20261104
LIBRARY_SCHEMA = 'ratchet.library.v1'

# ---------------------------------------------------------------------------------------------------------------------
# Sandbox (PREREG 3; SPEC 5 builder A)
SANDBOX_TIMEOUT_S = 2.0
SANDBOX_MEM_MB = 2048
SANDBOX_FSIZE_MB = 16
SANDBOX_IMPORT_ALLOW = ('math', 'itertools', 'collections', 'functools', 'copy', 'typing', 'numpy')
# Workers for program execution: the job's CPUs minus 2 for the driver and the HTTP pool.
EXEC_WORKERS = max(1, int(os.environ.get('SLURM_CPUS_PER_TASK', os.cpu_count() or 1)) - 2)
EXEC_BATCH = 256
# FLAT-TTC extra samples per request (n); the prompt is identical across a task's requests, so the prefix cache shares it.
FLAT_EXTRA_BATCH_N = 16

# ---------------------------------------------------------------------------------------------------------------------
# Selection and scoring (PREREG 5, 6; SPEC 13 I9 to I13)
PASS_AT = 2
SEALED_SEEDS = (1, 2, 3)
SOLVED_MIN_SEEDS = 2
MCNEMAR_ALPHA = 0.05
REUSE_MIN_FRAC = 0.5
KNOCKOUT_MAX_FRAC = 0.5
CONTAM_MIN_FRAC = 0.5
PERTURB_SEED = 20261104
PERTURB_GEOMS = ('rot90', 'rot180', 'rot270', 'transpose')
VOID_MAX_ATTEMPTS = 2

# ---------------------------------------------------------------------------------------------------------------------
# Pilot and S/R rule (PREREG 7; SPEC 13 I15)
S_GRID = (4, 8, 16)
R_GRID = (4, 6, 8)
H100_HOURS_BUDGET = 12
PILOT_N = 50
S_PILOT = 8
PILOT_R = 4
POWER_GAIN = 20
POWER_MIN = 0.60
POWER_SIMS = 100_000
PILOT_RATE_INTERVAL_S = 30
# Knockout size for the projection (SPEC 1.3: 2 modes x 3 seeds x |W| / 400 units). |W| is unknown before the sealed
# read; ASSUMED 40 of 400 (10%) until measured (review fix 2026-11-04).
KO_W_ASSUMED = 40

# ---------------------------------------------------------------------------------------------------------------------
# Seeds (SPEC 5 arms.seed_for; SPEC 13 I3)
SEED_BASE = 1000
SEED_BYTES = 4

# ---------------------------------------------------------------------------------------------------------------------
# Jobs (SPEC 5 Slurm). One 1 h h100-debug job at a time; stop issuing at 52 min, abandon at 55 min.
SLURM_PARTITION = 'h100-debug'
SLURM_GRES = 'gpu:h100:1'
SLURM_CPUS = 24
SLURM_MEM = '180G'
SLURM_WALL = '01:00:00'
JOB_PREFIX = 'maxRATCH'
JOB_WALL_S = 3600
STOP_ISSUE_S = 3120
HARD_STOP_S = 3300
STATUS_EVERY_S = 60

# ---------------------------------------------------------------------------------------------------------------------
# Physics floor inputs (SPEC 1.1; ASSUMED values are replaced by the pilot)
MODEL_BYTES = 35 * 10**9
KV_BYTES_PER_TOKEN = 20480
HBM_BYTES_PER_S_SXM = 3.35e12
HBM_BYTES_PER_S_PCIE = 2.0e12
ASSUMED_P_TASK = 1500
ASSUMED_GEN = 1000
ASSUMED_VLLM_STARTUP_S = 300

# ---------------------------------------------------------------------------------------------------------------------
# Prediction (PREREG 8; AMENDMENT 0)
PRED_POINT = 2
PRED_BAND = (-8, 14)
PRED_BAND_CALIBRATED = (-10.68, 17.216)
P_COMPOUNDS = 0.15

# ---------------------------------------------------------------------------------------------------------------------
# File schemas
ROUND_SCHEMA = 'ratchet.round.v1'
UNIT_SCHEMA = 'ratchet.unit.v1'
RUN_SCHEMA = 'ratchet.run.v1'
FREEZE_SCHEMA = 'ratchet.freeze.v1'
SUBMIT_FREEZE_SCHEMA = 'ratchet.submit_freeze.v1'
KO_FREEZE_SCHEMA = 'ratchet.ko_freeze.v1'

# ---------------------------------------------------------------------------------------------------------------------
# Prompt text (frozen before the pilot; builder B's prompt.py may import these)
SYSTEM_PROMPT = (
    'You solve ARC puzzles by writing Python. Each puzzle shows input and output grids of digits 0 to 9. '
    'Find the rule that maps every input to its output and write it as a function.'
)
INSTRUCTION = (
    'Write a Python function `def transform(grid):` that takes the input grid as a list of lists of ints and returns '
    'the output grid as a list of lists of ints (values 0 to 9, at most 30 by 30). It must produce the correct output '
    'for every example above and for the test input. You may import math, itertools, collections, functools, copy, '
    'typing and numpy. Return one ```python fenced block containing the complete program.'
)

# ---------------------------------------------------------------------------------------------------------------------
# Builder sections: A, B, C and E append constants below this line.

# Centralized by the integration pass (2026-11-04). Values are identical to each builder's in-module default, so moving
# them here changes no behaviour; the in-module defaults stay as fallbacks.
# Data pins (SPEC 13 I6: arc-dsl commit pinned at download; data/MANIFEST.json records it)
ARCDSL_COMMIT = '635de4902a5fb4e376f27333feaa396d3f5dfdcb'
# Builder A (sandbox)
SANDBOX_HARD_PAD_S = 2.0
SANDBOX_IMPORT_PAD_S = 2.0          # RLIMIT_CPU slack for interpreter start and numpy import (review fix 2026-11-04)
SANDBOX_BWRAP = '/usr/bin/bwrap'    # private mount view; required in production (review fix 2026-11-04)
SANDBOX_HIDE_ROOTS = ('/N/scratch', '/N/slate', '/N/project', '/geode3/home', '/geode3/projects', '/geode3/logs', '/home',
                      '/tmp', '/var/tmp', '/dev/shm', '/run', '/proc', '/root', '/mnt', '/media', '/srv')
SANDBOX_CACHE_MAX = 400_000
SANDBOX_BLOCKED_IMPORTS = ('ctypes', '_ctypes', 'cffi', 'socket', '_socket', 'ssl', '_ssl', 'subprocess',
                           '_posixsubprocess', 'multiprocessing', '_multiprocessing', 'mmap', 'pty', 'fcntl', 'gc',
                           'resource', 'signal', '_signal')
SANDBOX_SPAWN = 'zygote'            # 'spawn' = SPEC 5 literal one-python-per-program path; RATCHET_SANDBOX_SPAWN overrides
SANDBOX_ZYGOTE_READY_S = 120.0
SANDBOX_ZYGOTE_KILL_WAIT_S = 10.0
# Builder B (ledger, client, prompt)
LEDGER_FSYNC_EVERY = 32
LEDGER_PHASES = ('growth', 'sealed', 'perturbed', 'knockout_delete', 'knockout_inline', 'pilot', 'arcagi2')
LLM_RETRIES = 2
LLM_RETRY_SLEEP_S = 2.0
LLM_READY_POLL_S = 2.0
LLM_RESULT_WAIT_S = 0.5
LIB_HEADER_CALLABLE = 'These functions are already defined; call them directly.'
LIB_HEADER_INLINE = 'Reference code. These functions are NOT defined in your environment; copy any code you need.'
LIB_NOTE_CALLABLE = 'The library functions above are already defined in your environment; you may call them.'
LIB_NOTE_INLINE = 'The reference code above is not defined in your environment; copy any part you use.'
EXEMPLAR_HEADER = ('Verified programs that solve other, similar puzzles (each passes every example of its own '
                   'puzzle):')
EXEMPLAR_NOTE = 'The programs above solve other puzzles; they are shown for reference only.'
PROMPT_EST_MARGIN_PER_PIECE = 2
PROMPT_EST_MARGIN_BASE = 4
# Builder C (helpers, SHAM)
HASH_NAME_LEN = 12
SHAM_GENRE_BIN = 25
SHAM_SWAP_ITERS = 2000
# Builder E (pilot, verdict)
PILOT_PLANT_MIN_GAIN = 1
COMPARATORS = ('STATIC', 'ONESHOT', 'EXEMPLAR', 'SHAM', 'FLATTTC')
