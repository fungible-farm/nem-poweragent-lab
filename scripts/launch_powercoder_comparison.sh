#!/usr/bin/env bash
#
# launch_powercoder_comparison.sh -- run training/run_comparison.py as one
# supervised systemd --user unit.
#
# Why: the 2026-10-21 r2 run was a detached exec session plus a driver that
# adopted an externally started evaluator, so nothing owned the whole pipeline
# and stopping it meant hunting PIDs. Here the driver starts every stage itself
# and runs inside a transient unit:
#   - `systemctl --user status <unit>` and `journalctl --user -u <unit>` show it;
#   - `systemctl --user stop <unit>` first stops this run's podman containers
#     (ExecStop), then SIGTERMs the driver and its evaluator children (default
#     KillMode=control-group). The containers' conmon processes sit in the
#     unit's cgroup but ignore SIGTERM -- r3's first launch spent its whole
#     120 s stop timeout on one -- so containers are stopped explicitly. When
#     the driver exits on its own (failure), ExecStop does not run; ExecStopPost
#     stops anything left after the stop timeout;
#   - Restart is never set: the driver refuses automatic re-execution, and a
#     failed unit stays "failed" for inspection (--remain-after-exit keeps a
#     finished one visible too).
#
# Usage:
#   ./scripts/launch_powercoder_comparison.sh training/unsloth/out/agent-domain-r3
#
# The run root must not exist yet; the driver creates it and refuses reuse.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${1:?usage: $0 <new run root, e.g. training/unsloth/out/agent-domain-r3>}"
RUN="$(basename "$ROOT")"
UNIT="powercoder-${RUN}"
# The verified, already-exited pinned Granite download (see the handoff).
DOWNLOAD_CONTAINER="powercoder-granite42-download-r1"
UV="$(command -v uv)"
STOP_CONTAINERS="/bin/sh -c 'podman ps -q --filter name=^powercoder-${RUN}- | xargs -r podman stop -t 30'"

if [[ -e "$REPO_ROOT/$ROOT" ]]; then
  echo "refusing: $ROOT already exists" >&2
  exit 1
fi

systemd-run --user --unit="$UNIT" --remain-after-exit \
  --description="PowerCoder Qwen/Granite comparison ($RUN)" \
  --working-directory="$REPO_ROOT" \
  --property=TimeoutStopSec=60 \
  --property="ExecStop=$STOP_CONTAINERS" \
  --property="ExecStopPost=$STOP_CONTAINERS" \
  "$UV" run --offline --no-sync python -m training.run_comparison \
    --root "$ROOT" --download-container "$DOWNLOAD_CONTAINER"

echo "started $UNIT; inspect with: systemctl --user status $UNIT"
