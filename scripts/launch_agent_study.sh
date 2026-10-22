#!/usr/bin/env bash
#
# launch_agent_study.sh -- run training/run_agent_study.py (r6: smoke gates,
# four-model evaluation, latency and memory) as one supervised systemd --user
# unit, with the same stop handling as launch_powercoder_comparison.sh
# (AGENTS.md FM-11/FM-13).
#
# Run it after scripts/launch_agent_sft.sh has finished: the driver re-hashes
# both students and refuses to start without them.
#
# Usage:
#   ./scripts/launch_agent_study.sh training/unsloth/out/agent-study-r6
#   ./scripts/launch_agent_study.sh training/unsloth/out/agent-study-r6-forced \
#       --forced-arm-from training/unsloth/out/agent-study-r6   # forced-tool-call arm
#
# Arguments after the root pass through to training/run_agent_study.py.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${1:?usage: $0 <new run root, e.g. training/unsloth/out/agent-study-r6>}"
shift
RUN="$(basename "$ROOT")"
UNIT="powercoder-${RUN}"
UV="$(command -v uv)"
STOP_CONTAINERS="/bin/sh -c 'podman ps -q --filter name=^powercoder-${RUN}- | xargs -r podman stop -t 30'"

if [[ -e "$REPO_ROOT/$ROOT" ]]; then
  echo "refusing: $ROOT already exists" >&2
  exit 1
fi
# --remain-after-exit keeps a finished training unit "active (exited)", so test
# its sub-state and result rather than is-active.
if [[ "$(systemctl --user show -p SubState --value powercoder-agent-sft)" == "running" ]]; then
  echo "refusing: powercoder-agent-sft is still training" >&2
  exit 1
fi

systemd-run --user --unit="$UNIT" --remain-after-exit \
  --description="PowerCoder r6 agent study ($RUN)" \
  --working-directory="$REPO_ROOT" \
  --property=TimeoutStopSec=60 \
  --property="ExecStop=$STOP_CONTAINERS" \
  --property="ExecStopPost=$STOP_CONTAINERS" \
  "$UV" run --offline --no-sync python -m training.run_agent_study --root "$ROOT" "$@"

echo "started $UNIT; inspect with: systemctl --user status $UNIT"
