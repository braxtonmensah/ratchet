#!/bin/bash
# Submit the next ratchet job only when work remains (`ratchet next` says chain=1). Owner: builder D.
#   bash chain.sh <run dir> [--after <jobid>]
# h100-debug QoS (sacctmgr, 2026-11-04): MaxJobsPU 1, no MaxSubmitPU, so a dependent job may sit queued while this one
# runs. Never queues a second maxRATCH job if one is already pending.
set -uo pipefail
# Review fix 2026-11-04: test-only overrides never reach a production job (--export=ALL would carry them from a login
# shell): RATCHET_DATA_ROOT turns off the PREREG id-list checks, RATCHET_KEY_ROOT moves the key, RATCHET_SANDBOX_* weaken
# the sandbox, RATCHET_ROOT moves the silo tree. Same list in all three slurm scripts.
for v in RATCHET_DATA_ROOT RATCHET_KEY_ROOT RATCHET_SANDBOX_NET RATCHET_SANDBOX_SPAWN RATCHET_ROOT RATCHET_TEST; do
  if [ -n "${!v+x}" ]; then echo "TEST_ENV_REFUSED $v=${!v} (unset it; test overrides never run in a production job)"; exit 5; fi
done
RUN="${1:?run dir}"; shift
AFTER=""
if [ "${1:-}" = "--after" ]; then AFTER="${2:?jobid}"; fi
CODE="${RATCHET_CODE:-/N/scratch/bsmensah/silo/ratchet/code}"
PY="${RATCHET_PY:-/N/slate/bsmensah/arc26/lightning/venv_vllm/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
# The vLLM venv's python links a shared libpython that only loads with the module environment (measured on the login
# node 2026-11-04: "libpython3.13.so.1.0: cannot open shared object file" from a bare shell). Inside a job
# serve_and_step.sh has already sourced env_vllm.sh; from a login shell, source it here (read-only file).
if ! "$PY" -c 'import sys' >/dev/null 2>&1; then
  export BASE=/N/slate/bsmensah/arc26; export LIGHT=$BASE/lightning
  source /N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh >/dev/null 2>&1
  set -uo pipefail
fi
"$PY" -c 'import sys; assert sys.version_info >= (3, 10)' || { echo "CHAIN_PY_UNUSABLE $PY"; exit 1; }
cd "$CODE"
NEXT="$(PYTHONPATH="$CODE" "$PY" -m ratchet next --run "$RUN")" || { echo "CHAIN_NEXT_FAILED"; exit 1; }
CHAIN="$(printf '%s' "$NEXT" | "$PY" -c 'import json,sys; print(int(bool(json.load(sys.stdin)["chain"])))')"
PHASE="$(printf '%s' "$NEXT" | "$PY" -c 'import json,sys; n=json.load(sys.stdin)["next"] or {}; print((n.get("kind") or "none")[:12])')"
if [ "$CHAIN" != 1 ]; then echo "CHAIN_STOP next=$NEXT"; exit 0; fi
PENDING="$(squeue -h -u "$USER" -t PENDING -o '%j' | grep -c '^maxRATCH' || true)"
if [ "${PENDING:-0}" -gt 0 ]; then echo "CHAIN_SKIP a maxRATCH job is already pending"; exit 0; fi
DEP=()
[ -n "$AFTER" ] && DEP=(--dependency="afterany:$AFTER")
mkdir -p "$RUN/jobs"
sbatch "${DEP[@]}" -J "maxRATCH_$PHASE" -o "$RUN/jobs/%j.out" --export="ALL,RATCHET_RUN=$RUN,RATCHET_CODE=$CODE" \
  "$CODE/slurm/ratchet_step.sbatch"
