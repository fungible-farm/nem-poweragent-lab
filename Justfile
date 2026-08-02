# Canonical command entry point for nem-poweragent-lab -- the repo's "just
# does this" truth (see AGENTS.md "Running the labs"). Recipes are the
# canonical example commands; anything non-trivial lives in a committed
# script (./install.sh, scripts/run_labs_1_3.sh, scripts/deploy_demo_tools.py,
# scripts/peek_viz.sh, scripts/watch_viz.sh) that a recipe simply RUNS -- just
# is the index, not a re-implementation. `just --list` for everything.
#
# Written against the `b00t learn just` gospel: simple recipes stay one line,
# env vars are $VAR, just vars are {{var}}, complex logic goes in scripts.

set dotenv-load
set shell := ["bash", "-c"]

# --- aliases ---------------------------------------------------------------
alias s := sync
alias f := fetch
alias t := test
alias p := proof
alias d := deploy
alias r := render

# --- setup -----------------------------------------------------------------
# One-command install -- RUNS ./install.sh (the committed checks-then-acts
# script owns the logic; this recipe is just the canonical pointer).
install:
    ./install.sh

# Install pinned deps from pyproject.toml/uv.lock.
sync:
    uv sync

# Fetch + checksum-verify the CSIRO case data into data/ (idempotent).
fetch:
    uv run scripts/fetch_csiro_nem_data.py

# Declarative host-state deploy for the demo/display tools (pyinfra @local).
# Idempotent; prompts for sudo once, or export SUDO_PASSWORD for scripted
# runs (see scripts/deploy_demo_tools.py). Bootstraps pyinfra itself if
# absent (uv tool install -- the user-global tool, not a repo dependency).
deploy:
    command -v pyinfra >/dev/null 2>&1 || uv tool install pyinfra
    pyinfra @local scripts/deploy_demo_tools.py

# --- proof / test ----------------------------------------------------------
# The committed end-to-end proofs (the proof scripts are the proof, not a
# transcript -- AGENTS.md).
proof: proof-labs-1-3 proof-lab4

proof-labs-1-3:
    ./scripts/run_labs_1_3.sh

proof-lab4:
    ./scripts/run_lab4.sh

# pytest across every lab.
test:
    uv run python -m pytest labs/ -q

# --- per-lab self-check gates ----------------------------------------------
check: check-lab1 check-lab2 check-lab3 check-lab4 check-lab5

check-lab1:
    uv run labs/01-simple-loadflow-fit/run.py --step check

check-lab2:
    uv run labs/02-medium-interconnection-screening/workflow.py --step check

check-lab3:
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step check

check-lab4:
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check

check-lab5:
    uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py
    uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --step check

# --- per-lab walkthrough steps (canonical examples) -------------------------
# e.g. `just lab2 base`, `just lab2 memo -- APPROVE`, `just lab3 report`
lab1 step="check":
    uv run labs/01-simple-loadflow-fit/run.py --step {{step}}

lab2 step="check":
    uv run labs/02-medium-interconnection-screening/workflow.py --step {{step}}

lab3 step="check":
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step {{step}}

lab4:
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check

lab5:
    uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py

# --- demo: render the animations (PowerPoint-friendly MP4s) -----------------
render: render-lab1 render-lab2 render-lab5

render-lab1:
    uv run python labs/01-simple-loadflow-fit/animate_convergence.py

render-lab2:
    uv run python labs/02-medium-interconnection-screening/animate_contingencies.py

render-lab5:
    uv run python labs/05-spartan-chaosnet-transient-stream/animate_transient.py

# --- demo: display without file transfer ------------------------------------
# chafa-render a named committed chart straight into the SSH terminal.
# `just peek` lists the named charts; `just peek <name>` renders one.
peek name="list":
    ./scripts/peek_viz.sh {{name}}

# Play a named animation with mpv -- windowed over X11/WSLg by default.
# `just watch` lists the named animations; `just watch <name>` plays one.
watch name="list":
    ./scripts/watch_viz.sh {{name}}

# Same, but truecolor playback inside the SSH terminal (mpv --vo=tct).
watch-tct name="list":
    ./scripts/watch_viz.sh --in-terminal {{name}}

# --- help -------------------------------------------------------------------
default:
    @just --list
