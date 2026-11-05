#!/bin/bash
# Start vLLM inside the job, wait until it serves, run `python -u -m ratchet step`, stop gracefully. Owner: builder D.
#   bash serve_and_step.sh <run dir>
# Timeline (driver side, ratchet/config.py): stop issuing at 52 min (3,120 s), abandon in-flight requests at 55 min
# (3,300 s) from RATCHET_JOB_START_TS; then SIGINT to vLLM, SIGKILL after 30 s.
# When the next PLAN unit needs no model call (freeze, builds, shared rounds), vLLM is not started.
set -uo pipefail
RUN="${1:?run dir}"
CODE="${RATCHET_CODE:-/N/scratch/bsmensah/silo/ratchet/code}"
JOB="${SLURM_JOB_ID:-local$$}"
MODEL="${RATCHET_MODEL_DIR:-/N/scratch/bsmensah/arc26/tufa/models/qwen36_35b_a3b_fp8}"
export RATCHET_JOB_START_TS="$(date +%s.%N)"
export RATCHET_CODE="$CODE"
export RATCHET_MODEL_DIR="$MODEL"
export RATCHET_REQUIRE_REAL_TOKENIZER=1     # no stub token counts inside a job (the 6,000 cap depends on them)
mkdir -p "$RUN/logs" "$RUN/jobs/$JOB"

export BASE=/N/slate/bsmensah/arc26
export LIGHT=$BASE/lightning
# env_vllm.sh is READ-ONLY (owned by the tufa lane): python 3.13 venv, HF_HUB_OFFLINE=1, node-local compile cache.
source /N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh
set -uo pipefail
# Review fix 2026-11-04: test-only overrides never reach a production job (--export=ALL would carry them from a login
# shell): RATCHET_DATA_ROOT turns off the PREREG id-list checks, RATCHET_KEY_ROOT moves the key, RATCHET_SANDBOX_* weaken
# the sandbox, RATCHET_ROOT moves the silo tree. Same list in all three slurm scripts.
for v in RATCHET_DATA_ROOT RATCHET_KEY_ROOT RATCHET_SANDBOX_NET RATCHET_SANDBOX_SPAWN RATCHET_ROOT RATCHET_TEST; do
  if [ -n "${!v+x}" ]; then echo "TEST_ENV_REFUSED $v=${!v} (unset it; test overrides never run in a production job)"; exit 5; fi
done
PY="${RATCHET_PY:-$LIGHT/venv_vllm/bin/python}"
cd "$CODE"
export PYTHONPATH="$CODE${PYTHONPATH:+:$PYTHONPATH}"
if [ -z "${RATCHET_CODE_SHA:-}" ]; then
  RATCHET_CODE_SHA="$(git -C "$CODE" rev-parse HEAD 2>/dev/null || cat "$CODE/CODE_SHA" 2>/dev/null || echo nogit)"
fi
export RATCHET_CODE_SHA
GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
export RATCHET_GPU_NAME="$GPU_NAME"

NEXT="$("$PY" -m ratchet next --run "$RUN")" || { echo "NEXT_FAILED (see the error above)"; exit 1; }
ROOTS="$("$PY" -c 'from ratchet import guard; print("data_root=%s key_root=%s" % (guard.data_root(), guard.key_root()))')"
# Sandbox refusal self-test on THIS node (SPEC 8 test 9; review fix 2026-11-04): production needs the bwrap mount view
SBX_OUT="$("$PY" -u -m ratchet sandbox-selftest 2>&1)"; SBX_RC=$?
SBX="$(echo "$SBX_OUT" | grep -E '^LEVER SANDBOX_SELFTEST|SANDBOX_NET_FAIL|SANDBOX_SELFTEST FAIL' | tail -1)"
echo "META job=$JOB node=$(hostname) gpu=$GPU_NAME model=$MODEL temperature=0.8 top_p=0.95 max_tokens=4096 enable_thinking=0 code_sha=$RATCHET_CODE_SHA run=$RUN $ROOTS sandbox=[$SBX] next=$NEXT"
if [ "$SBX_RC" != 0 ]; then echo "SANDBOX_NET_FAIL selftest rc=$SBX_RC"; echo "$SBX_OUT" | tail -20; exit 4; fi
nvidia-smi
NEED_GPU="$(printf '%s' "$NEXT" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(int(bool(d["gpu"])))')"
CHAIN="$(printf '%s' "$NEXT" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(int(bool(d["chain"])))')"

# Self-chain at start (h100-debug QoS: MaxJobsPU 1, no submit cap): the next job waits on this one (afterany).
if [ "$CHAIN" = 1 ]; then
  bash "$CODE/slurm/chain.sh" "$RUN" --after "$JOB" || echo "CHAIN_SUBMIT_FAILED"
fi

if [ "$NEED_GPU" != 1 ]; then
  "$PY" -u -m ratchet step --run "$RUN" --no-gpu 2>&1 | grep --line-buffered -v '^DEBUG' | tee -a "$RUN/logs/driver_$JOB.log"
  exit "${PIPESTATUS[0]}"
fi

# PREREG 3 weights fixed for the whole run: the first GPU job records sha256 of every model file in RUN.json, later
# jobs check size and mtime (rehash on change). Runs beside the vLLM load; the step waits for it.
"$PY" -u -m ratchet modelcheck --run "$RUN" > "$RUN/logs/modelcheck_$JOB.log" 2>&1 &
MCPID=$!
PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
T0=$(date +%s)
setsid "$PY" -m vllm.entrypoints.openai.api_server --model "$MODEL" --served-model-name ratchet \
  --host 127.0.0.1 --port "$PORT" --max-model-len 20480 --enable-prefix-caching --enable-prompt-tokens-details --max-num-seqs 256 \
  --gpu-memory-utilization 0.90 --seed 0 > "$RUN/logs/vllm_$JOB.log" 2>&1 &
VPID=$!
stop_vllm() {
  kill -INT -- -"$VPID" 2>/dev/null || kill -INT "$VPID" 2>/dev/null
  for _ in $(seq 1 30); do kill -0 "$VPID" 2>/dev/null || return 0; sleep 1; done
  kill -KILL -- -"$VPID" 2>/dev/null || kill -KILL "$VPID" 2>/dev/null
}
trap stop_vllm EXIT

UP=0
for _ in $(seq 1 180); do
  kill -0 "$VPID" 2>/dev/null || { echo "VLLM_DIED"; tail -40 "$RUN/logs/vllm_$JOB.log"; exit 2; }
  if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/v1/models")" = 200 ]; then UP=1; break; fi
  sleep 5
done
[ "$UP" = 1 ] || { echo "VLLM_NOT_UP after 900 s"; exit 2; }
export RATCHET_VLLM_STARTUP_S=$(( $(date +%s) - T0 ))
echo "VLLM_UP port=$PORT startup_s=$RATCHET_VLLM_STARTUP_S"
if ! wait "$MCPID"; then echo "MODEL_CHECK_FAILED"; cat "$RUN/logs/modelcheck_$JOB.log"; exit 3; fi
echo "MODELCHECK $(tail -1 "$RUN/logs/modelcheck_$JOB.log")"
export RATCHET_VLLM_URL="http://127.0.0.1:$PORT"
export RATCHET_SERVED_MODEL=ratchet

"$PY" -u -m ratchet step --run "$RUN" 2>&1 | grep --line-buffered -v '^DEBUG' | tee -a "$RUN/logs/driver_$JOB.log"
RC=${PIPESTATUS[0]}
echo "STEP_RC=$RC"
exit "$RC"
