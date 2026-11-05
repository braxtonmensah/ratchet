#!/bin/bash
# Amendment 5 candidate smoke (silicyte-0119; diagnostic only, writes nothing under runs/). One 1 h h100-debug slot.
# Starts vLLM exactly as slurm/serve_and_step.sh does (same env_vllm.sh, model, flags, readiness loop, graceful stop),
# runs the sandbox self-test as serve_and_step.sh does, then `python -u diag/smoke_a5.py serve`.
# Submit (lead, after the verifier's GO):
#   sbatch -o /N/scratch/bsmensah/silo/ratchet/diag/smoke_a5/%j.out /N/scratch/bsmensah/silo/ratchet/code/slurm/smoke_a5.sbatch
#SBATCH -A students
#SBATCH -p h100-debug
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=24
#SBATCH --mem=180G
#SBATCH -t 01:00:00
#SBATCH -J maxRATCH_smokeA5
set -uo pipefail
for v in RATCHET_DATA_ROOT RATCHET_KEY_ROOT RATCHET_SANDBOX_NET RATCHET_SANDBOX_SPAWN RATCHET_ROOT RATCHET_TEST; do
  if [ -n "${!v+x}" ]; then echo "TEST_ENV_REFUSED $v=${!v} (unset it; test overrides never run in a production job)"; exit 5; fi
done
CODE="${RATCHET_CODE:-/N/scratch/bsmensah/silo/ratchet/code}"
OUT="${SMOKE_OUT:-/N/scratch/bsmensah/silo/ratchet/diag}"
case "$(realpath -m "$OUT")" in /N/scratch/bsmensah/silo/ratchet/runs*) echo "OUT_REFUSED $OUT is under runs/"; exit 7;; esac
JOB="${SLURM_JOB_ID:-local$$}"
MODEL="${RATCHET_MODEL_DIR:-/N/scratch/bsmensah/arc26/tufa/models/qwen36_35b_a3b_fp8}"
export RATCHET_JOB_START_TS="$(date +%s.%N)"
export RATCHET_CODE="$CODE"
export RATCHET_MODEL_DIR="$MODEL"
export RATCHET_REQUIRE_REAL_TOKENIZER=1
LOGD="$OUT/smoke_a5"
mkdir -p "$LOGD"

export BASE=/N/slate/bsmensah/arc26
export LIGHT=$BASE/lightning
source /N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh
set -uo pipefail
PY="${RATCHET_PY:-$LIGHT/venv_vllm/bin/python}"
cd "$CODE"
export PYTHONPATH="$CODE${PYTHONPATH:+:$PYTHONPATH}"
if [ -s "$CODE/CODE_SHA" ]; then RATCHET_CODE_SHA="$(head -c 40 "$CODE/CODE_SHA")"; else RATCHET_CODE_SHA=nogit; fi
export RATCHET_CODE_SHA
GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
export RATCHET_GPU_NAME="$GPU_NAME"
SBX_OUT="$("$PY" -u -m ratchet sandbox-selftest 2>&1)"; SBX_RC=$?
SBX="$(echo "$SBX_OUT" | grep -E '^LEVER SANDBOX_SELFTEST|SANDBOX_NET_FAIL|SANDBOX_SELFTEST FAIL' | tail -1)"
echo "META job=$JOB node=$(hostname) gpu=$GPU_NAME model=$MODEL temperature=0.8 top_p=0.95 max_tokens=4096 enable_thinking=0 code_sha=$RATCHET_CODE_SHA out=$OUT sandbox=[$SBX] smoke=A5"
if [ "$SBX_RC" != 0 ]; then echo "SANDBOX_NET_FAIL selftest rc=$SBX_RC"; echo "$SBX_OUT" | tail -20; exit 4; fi
nvidia-smi

PORT="$("$PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
T0=$(date +%s)
setsid "$PY" -m vllm.entrypoints.openai.api_server --model "$MODEL" --served-model-name ratchet \
  --host 127.0.0.1 --port "$PORT" --max-model-len 20480 --enable-prefix-caching --enable-prompt-tokens-details --max-num-seqs 256 \
  --gpu-memory-utilization 0.90 --seed 0 > "$LOGD/vllm_$JOB.log" 2>&1 &
VPID=$!
stop_vllm() {
  kill -INT -- -"$VPID" 2>/dev/null || kill -INT "$VPID" 2>/dev/null
  for _ in $(seq 1 30); do kill -0 "$VPID" 2>/dev/null || return 0; sleep 1; done
  kill -KILL -- -"$VPID" 2>/dev/null || kill -KILL "$VPID" 2>/dev/null
}
trap stop_vllm EXIT

UP=0
for _ in $(seq 1 180); do
  kill -0 "$VPID" 2>/dev/null || { echo "VLLM_DIED"; tail -40 "$LOGD/vllm_$JOB.log"; exit 2; }
  if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/v1/models")" = 200 ]; then UP=1; break; fi
  sleep 5
done
[ "$UP" = 1 ] || { echo "VLLM_NOT_UP after 900 s"; exit 2; }
export RATCHET_VLLM_STARTUP_S=$(( $(date +%s) - T0 ))
echo "VLLM_UP port=$PORT startup_s=$RATCHET_VLLM_STARTUP_S"
export RATCHET_VLLM_URL="http://127.0.0.1:$PORT"
export RATCHET_SERVED_MODEL=ratchet

"$PY" -u "$CODE/diag/smoke_a5.py" serve --out "$OUT" 2>&1 | grep --line-buffered -v '^DEBUG' | tee -a "$LOGD/driver_$JOB.log"
RC=${PIPESTATUS[0]}
echo "SMOKE_RC=$RC"
exit "$RC"
