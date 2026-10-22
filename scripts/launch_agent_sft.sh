#!/usr/bin/env bash
#
# launch_agent_sft.sh -- train the Qwen3.5-4B and Granite 4.2 8B tool-call
# students (training/agent_sft.py) one after the other in one supervised
# systemd --user unit.
#
# Why one unit, not detached podman runs: see launch_powercoder_comparison.sh
# and AGENTS.md FM-11/FM-13. `systemctl --user stop powercoder-agent-sft` stops
# this unit's containers first (ExecStop), because conmon ignores SIGTERM.
# Restart is never set; a failed unit stays "failed" for inspection.
#
# expandable_segments limits the caching allocator's growth: the first Qwen run
# held ~93 GB of the shared memory. The students train sequentially, not side by side: each trainer holds its
# model, activations and optimizer state in the GB10's shared 121 GB, and two
# at once beside a llama-swap model is the FM-10 OOM shape.
#
# Each trainer refuses an existing output directory, so a finished student is
# never overwritten; the evaluation driver verifies each hash_manifest.json.
#
# Usage:
#   ./scripts/launch_agent_sft.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT="powercoder-agent-sft"
# training/agent/Containerfile: the pinned training image
# (training/run_comparison.TRAINING_IMAGE) plus flash-linear-attention 0.5.2.
IMAGE="c890642db1726a2f21c39444bda33d7399f8bb8c485fddf7e7ed541378084d9c"
HUB="$HOME/.cache/huggingface/.cache/hub"
STOP_CONTAINERS="/bin/sh -c 'podman ps -q --filter name=^${UNIT}- | xargs -r podman stop -t 30'"

run_one() {
  # $1: config stem under training/agent/
  printf 'podman run --rm --name %s-%s --device nvidia.com/gpu=all --network none --security-opt label=disable -v %q:/workspace -w /workspace -v %q:/hub:ro -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 -e PYTHONUNBUFFERED=1 -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True %s python -m training.agent_sft --config training/agent/config.%s.yaml' \
    "$UNIT" "$1" "$REPO_ROOT" "$HUB" "$IMAGE" "$1"
}

systemd-run --user --unit="$UNIT" --remain-after-exit \
  --description="PowerCoder tool-call student training (Qwen3.5-4B, then Granite 4.2 8B)" \
  --working-directory="$REPO_ROOT" \
  --property=TimeoutStopSec=60 \
  --property="ExecStop=$STOP_CONTAINERS" \
  --property="ExecStopPost=$STOP_CONTAINERS" \
  /bin/bash -c "set -euo pipefail; $(run_one qwen35-4b); $(run_one granite42-8b)"

echo "started $UNIT; inspect with: journalctl --user -u $UNIT -f"
