#!/usr/bin/env bash
# Authorized root boundary for the demo/display tooling.
#
# This script is the ENTIRE root surface granted NOPASSWD by the scoped
# sudoers rule (scripts/sudoers.d/nem-poweragent-lab -- which authorizes
# exactly this one path and nothing else). It runs AS ROOT via:
#
#   sudo /abs/path/scripts/deploy_demo_tools.sh [--update]
#
# and whitelists its own operations below. Never widen the sudoers rule to a
# binary, and never add "env" or "sh" to it -- that would be blanket root.
# If a new demo tool needs installing, extend THIS whitelist, not sudoers.
#
# Kept in lockstep with install.sh step 7 and the smoke test's DISPLAY_TOOLS
# (the same package set, edited together).
set -euo pipefail

# The only accepted argument: --update refreshes apt lists first (needs
# network). Anything else is rejected so the boundary cannot be coerced into
# running an arbitrary command.
case "${1:-}" in
    "" | "--update") ;;
    *)
        echo "deploy_demo_tools.sh: unknown argument '${1:-}' -- only '' or '--update' allowed" >&2
        exit 2
        ;;
esac

if [[ "${1:-}" == "--update" ]]; then
    apt-get update
fi

# Idempotent: apt only touches absent packages. Same package set as
# install.sh step 7 / scripts/install_smoke_test.py's DISPLAY_TOOLS.
apt-get install -y mpv chafa fzf
