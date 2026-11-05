#!/bin/bash
# ratchet_v1 (silicyte-0119) job: one 1 h h100-debug slot. Owner: builder D.
# Submit through slurm/chain.sh (it sets RATCHET_RUN, the job name maxRATCH_<phase> and the output path).
#SBATCH -A students
#SBATCH -p h100-debug,h100-interactive
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=24
#SBATCH --mem=180G
#SBATCH -t 01:00:00
#SBATCH -J maxRATCH_step
set -uo pipefail
# Review fix 2026-11-04: test-only overrides never reach a production job (--export=ALL would carry them from a login
# shell): RATCHET_DATA_ROOT turns off the PREREG id-list checks, RATCHET_KEY_ROOT moves the key, RATCHET_SANDBOX_* weaken
# the sandbox, RATCHET_ROOT moves the silo tree. Same list in all three slurm scripts.
for v in RATCHET_DATA_ROOT RATCHET_KEY_ROOT RATCHET_SANDBOX_NET RATCHET_SANDBOX_SPAWN RATCHET_ROOT RATCHET_TEST; do
  if [ -n "${!v+x}" ]; then echo "TEST_ENV_REFUSED $v=${!v} (unset it; test overrides never run in a production job)"; exit 5; fi
done
CODE="${RATCHET_CODE:-/N/scratch/bsmensah/silo/ratchet/code}"
RUN="${RATCHET_RUN:?set RATCHET_RUN to the run dir}"
exec bash "$CODE/slurm/serve_and_step.sh" "$RUN"
