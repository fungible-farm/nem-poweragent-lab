#!/usr/bin/env python3
"""Declarative host-state deploy for the demo/display tooling, run with pyinfra
(pyinfra is installed as a uv tool; see the root Justfile's `deploy` recipe).

    pyinfra @local scripts/deploy_demo_tools.py      # interactive: prompts for sudo once
    SUDO_PASSWORD=... pyinfra @local --use-sudo-password --password "$SUDO_PASSWORD" \
        scripts/deploy_demo_tools.py                 # non-interactive (scripted)

This is the canonical, idempotent way to maintain this host state -- pyinfra
only makes a change when the host's actual state differs from the requested
state (run it twice; the second run reports "No Change" for every operation).
It is also the natural extension point for future host-level demo state
(fonts, terminal graphics tools, a download cache, ...): add another
operation here, re-run the deploy, done.

Division of labour vs install.sh: install.sh step 7 is a best-effort direct
`sudo apt-get` bootstrap (non-interactive friendly on hosts whose sudoers
grants NOPASSWD for apt-get); this deploy is the declarative version of the
same intent and the one to grow. The package list MUST stay in sync with
install.sh step 7's `sudo apt-get install -y mpv chafa` (edit both together).

Sandbox/box note (found by running it, not assumed): pyinfra wraps every
sudo'd command in `sh`/`env` on the way out, so on a host like fung1 whose
sudo-rs NOPASSWD rules cover only apt/apt-get/dpkg, the deploy prompts for a
sudo password even though the bare `sudo apt-get` commands succeed without
one. That is why the non-interactive path requires SUDO_PASSWORD above, and
why install.sh's bootstrap uses a direct apt-get instead of this deploy.

Operates only on the local host (`@local`) -- this repo's demo runs on the
box you SSH into (fung1), so provisioning *that* host is the whole job.

Notes / provenance:
  - mpv and chafa: the two viewers behind the root Justfile's `watch`/`peek`
    recipes (mp4 playback windowed over X11/WSLg or --vo=tct in-terminal;
    chafa renders committed PNGs as true-color ANSI straight into the SSH
    terminal). Chosen after a live comparison -- see the demo-tooling notes.
  - _sudo=True because these are system packages; install.sh already
    documented the same sudo requirement for the previous inline install.
"""
from __future__ import annotations

from pyinfra.operations import apt

# The demo/display tool set install.sh step 7 also guarantees on the host.
# Kept as one named list so the deploy script and the smoke test's
# DISPLAY_TOOLS cannot drift apart (both must be edited together if this
# grows).
DISPLAY_TOOLS: list[str] = ["mpv", "chafa"]

apt.packages(
    name="Ensure demo/display tools (mpv, chafa) are installed",
    packages=DISPLAY_TOOLS,
    update=False,
    _sudo=True,
)
