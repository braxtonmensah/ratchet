#!/bin/bash
# Ratchet silicyte-0119 PREREG section 7 pilot, run v2 (AMENDMENTS 1 to 3: F3 instruction with sequential screen, type adapter,
# PLANT_SOLVE gate). Same pattern as launch_pilot_v1.sh; code commit = the CODE_SHA file on Quartz (harness e2a9c2d plus the PREREG append); run dir v2 (v1's PILOT_STOP.json stays in place).
# Requires VERIFIED=<verdict file whose first line is 'VERDICT: GO'> (pair gate) before anything is initialised.
set -uo pipefail
V="${VERIFIED:-}"
{ [ -n "$V" ] && [ -f "$V" ] && head -1 "$V" | grep -qx 'VERDICT: GO'; } || { echo "PAIR_GATE_REFUSED VERIFIED=<verdict file, first line 'VERDICT: GO'> (got '${V}')"; exit 4; }
cd /N/scratch/bsmensah/silo/ratchet/code && [ -s CODE_SHA ] || { echo "NO_CODE_SHA"; exit 3; }
env -u RATCHET_DATA_ROOT -u RATCHET_KEY_ROOT -u RATCHET_SANDBOX_NET -u RATCHET_SANDBOX_SPAWN -u RATCHET_ROOT -u RATCHET_TEST -u RATCHET_PY bash -c 'export RATCHET_CODE_SHA=$(cat CODE_SHA) SBATCH_PARTITION=h100-debug BASE=/N/slate/bsmensah/arc26 LIGHT=/N/slate/bsmensah/arc26/lightning; source /N/scratch/bsmensah/arc26/tufa/code/env_vllm.sh; PYTHONPATH=/N/scratch/bsmensah/silo/ratchet/code $LIGHT/venv_vllm/bin/python -m ratchet init --run /N/scratch/bsmensah/silo/ratchet/runs/v2 && bash slurm/chain.sh /N/scratch/bsmensah/silo/ratchet/runs/v2'
