#!/usr/bin/env bash
# cgmes_peer_check.sh -- check the G4 CGMES export against pypowsybl on an x86-64 peer (backlog 0034).
#
# pypowsybl has no Linux ARM64 wheel and no sdist, and this GB10 host has no x86-64 emulation,
# so its half runs on a peer over ssh, in an ephemeral uv environment, CPU only:
#   1. here: powercoder.semantic.peer_check export   -> CGMES zip + pandapower voltages
#   2. peer: peer_check.py check (pypowsybl only)    -> counts, status, voltages
#   3. here: peer_check compare                      -> exit 1 above the tolerance
# Usage: scripts/cgmes_peer_check.sh [peer-host] [out-dir]   (defaults: sm3lly.lan, a mktemp dir)
set -euo pipefail

PEER="${1:-sm3lly.lan}"
OUT="${2:-$(mktemp -d)}"
# The version measured 2026-10-23; pin it so a peer result is reproducible.
PYPOWSYBL_VERSION="1.16.1"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="$(command -v uv || true)"; UV="${UV:-$HOME/.local/bin/uv}"
[[ -x "$UV" ]] || { echo "refusing: uv not found on PATH or at ~/.local/bin/uv" >&2; exit 1; }

mkdir -p "$OUT"
cd "$ROOT"
"$UV" run python -m powercoder.semantic.peer_check export --zip "$OUT/cgmes.zip" --voltages "$OUT/pandapower_vm.json"

REMOTE="$(ssh -o BatchMode=yes "$PEER" 'mktemp -d /tmp/cgmes-peer-check.XXXX')"
trap 'ssh -o BatchMode=yes "$PEER" "rm -rf $REMOTE" || true' EXIT
scp -q "$ROOT/powercoder/semantic/peer_check.py" "$OUT/cgmes.zip" "$PEER:$REMOTE/"
ssh -o BatchMode=yes "$PEER" "cd $REMOTE && \$HOME/.local/bin/uv run -q --no-project --python 3.12 \
    --with pypowsybl==$PYPOWSYBL_VERSION python peer_check.py check --zip cgmes.zip --out peer.json"
scp -q "$PEER:$REMOTE/peer.json" "$OUT/peer.json"

"$UV" run python -m powercoder.semantic.peer_check compare --voltages "$OUT/pandapower_vm.json" --peer "$OUT/peer.json"
