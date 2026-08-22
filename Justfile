# Canonical command entry point for nem-poweragent-lab -- the repo's "just
# does this" truth (see AGENTS.md "Running the labs"). Recipes are the
# canonical example commands; anything non-trivial lives in a committed
# script (./install.sh, scripts/run_labs_1_3.sh, scripts/deploy_demo_tools.sh,
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

# Declarative host-state deploy for the demo/display tools.
#
# Per-command authorization model (scoped sudoers, no password anywhere):
# the ONLY NOPASSWD root surface is the committed, reviewed
# scripts/deploy_demo_tools.sh (see scripts/sudoers.d/nem-poweragent-lab,
# installed by `just authorize`). `deploy` runs that script as root and, if
# the rule isn't installed yet, tells you exactly what to run instead of
# stopping dead -- the just workflow is never the blocker.
#
# Future-just note: this pattern is a candidate for an upstream `just`
# feature -- a recipe attribute like `[elevated]` that routes a recipe's
# commands through a configured elevation boundary (the authorized script
# here). Filed as an idea, not needed for today.
deploy args="":
    #!/usr/bin/env bash
    set -euo pipefail
    script="{{justfile_directory()}}/scripts/deploy_demo_tools.sh"
    if ! sudo -n "$script" {{args}}; then
        echo "deploy: not authorized to run the deploy script as root (yet)."
        echo "  One-time setup -- run:  just authorize"
        echo "  (installs scripts/sudoers.d/nem-poweragent-lab: NOPASSWD for"
        echo "   exactly $script and nothing else.)"
        exit 1
    fi

# One-time install of the scoped sudoers rule (prompts for your sudo password
# once). Fills the <REPO_USER>/<REPO_ROOT> placeholders from this checkout and
# validates the result with visudo. Re-run after moving the repo.
authorize:
    #!/usr/bin/env bash
    set -euo pipefail
    repo_root="{{justfile_directory()}}"
    tmp="/tmp/nem-poweragent-lab.sudoers.$$"
    sed -e "s|<REPO_USER>|$(id -un)|" -e "s|<REPO_ROOT>|${repo_root}|g" \
        "$repo_root/scripts/sudoers.d/nem-poweragent-lab" > "$tmp"
    sudo cp "$tmp" /etc/sudoers.d/nem-poweragent-lab
    sudo chmod 0440 /etc/sudoers.d/nem-poweragent-lab
    rm -f "$tmp"
    sudo visudo -c

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
check: check-lab1 check-lab2 check-lab3 check-lab4 check-lab5 check-lab6 check-lab7 check-lab8 check-lab9

check-lab1:
    uv run labs/01-simple-loadflow-fit/run.py --step check

check-lab2:
    uv run labs/02-medium-interconnection-screening/workflow.py --step check
    uv run labs/02-medium-interconnection-screening/pypowsybl_cross_check.py --step check
    uv run labs/02-medium-interconnection-screening/render_network_diagram.py

check-lab3:
    uv run labs/03-advanced-provider-bakeoff/orchestrator.py --step check
    uv run labs/03-advanced-provider-bakeoff/spike_pypowsybl.py --step check

check-lab4:
    uv run labs/04-aemo-digital-twin-reconciliation/reconcile.py --step check

check-lab5:
    uv run labs/05-spartan-chaosnet-transient-stream/generate_topology.py
    uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --step check
    uv run labs/05-spartan-chaosnet-transient-stream/grid_forming.py --step check
    uv run labs/05-spartan-chaosnet-transient-stream/headroom_translation.py --step check
    uv run labs/05-spartan-chaosnet-transient-stream/delay_compensation.py --step check

check-lab6:
    ./scripts/demo_lab6.sh

# Rust FFT/COMTRADE detector: run the committed fixtures through the real
# Rust binary in --check mode (recovers the Python-computed reference
# finding by reading the COMTRADE file back, not by re-running pandapower).
check-lab7:
    cargo run --manifest-path rust/Cargo.toml -p fft-detector --release -- \
        labs/07-rust-comtrade-fft-detector/fixtures/local_mode.cfg \
        labs/07-rust-comtrade-fft-detector/fixtures/local_mode.dat \
        --check labs/07-rust-comtrade-fft-detector/fixtures/local_mode.expected.json
    cargo run --manifest-path rust/Cargo.toml -p fft-detector --release -- \
        labs/07-rust-comtrade-fft-detector/fixtures/inter_area_mode.cfg \
        labs/07-rust-comtrade-fft-detector/fixtures/inter_area_mode.dat \
        --check labs/07-rust-comtrade-fft-detector/fixtures/inter_area_mode.expected.json

# Lab 8 (cim-gridy Phase 0 spikes): build+run smoke test for the two
# standalone, deterministic, offline-after-fetch crates (0b sysml-v2-parser,
# 0d ufo-types+scryer-prolog -- both intentionally outside the rust/
# workspace, see labs/08-cim-gridy-phase0-spikes/README.md). --release is
# required for 0d: the spike's own README documents a real debug-profile-only
# scryer-prolog panic, so a debug build here would be a false-negative CI
# failure, not a regression. 0a/0c/0e are excluded on purpose -- they need
# CSIRO grid2op data + a patched pandapower round-trip, a network clone of
# sysand to scratch, and a multi-container OperatorFabric stack respectively,
# none of which fit a repeatable CI check (they're throwaway spikes, not
# fixtures -- same distinction Labs 1-7 draw between committed fixtures and
# one-off investigation scripts).
check-lab8:
    cargo run --manifest-path labs/08-cim-gridy-phase0-spikes/0b-sysml-v2-parser/Cargo.toml --release
    cargo run --manifest-path labs/08-cim-gridy-phase0-spikes/0d-ufo-types-scryer-prolog/Cargo.toml --release

# Lab 9 (cim-gridy PRD-0009 Phases 1-3): the full mission chain -- grid2op
# observation -> Bevy ECS -> SysML v2 type layer -> ufo-types/scryer-prolog
# objective -> Rhai mission FSM -> Mermaid -> DARE optimizer -- asserted
# against exact reference values.
#
# Deterministic and offline: the tests read the committed
# labs/09-.../fixtures/episode_observations.jsonl and NEVER spawn the real
# grid2op subprocess (that needs a local uv + grid2op install and a built
# dataset_snemSA/) -- same exclusion reasoning Lab 8 gives spike 0a. Use
# `just lab9-live` for the real bridge.
#
# --release is REQUIRED, not a preference: Lab 8 0d documented a real,
# reproducible debug-profile-only panic inside scryer-prolog's own
# Heap::clear (a rustc ub_checks NonNull assertion), unrelated to ufo-types.
# A debug build here would be a false-negative CI failure, not a regression.
#
# -p mission-engine keeps this scoped: an unscoped
# `cargo test --manifest-path rust/Cargo.toml` now also builds Bevy +
# scryer-prolog + sysml-v2-parser + rhai, which check-lab7's own
# -p fft-detector scoping already avoids.
check-lab9:
    cargo test --manifest-path rust/Cargo.toml -p mission-engine --release

# Lab 9 against the REAL grid2op subprocess (needs `just lab9-dataset` first,
# and takes ~1-2 min just to import grid2op and build the 503-bus env).
lab9-live:
    cargo run --manifest-path rust/Cargo.toml -p mission-engine --release -- --grid2op-live

# Lab 9: build the grid2op dataset from data/snemSA.m (carries Lab 8 0a's
# three real pandapower/grid2op fixes; writes the gitignored dataset_snemSA/
# plus the committed fixtures/bus_lookup.json).
lab9-dataset:
    uv run labs/09-cim-gridy-phase1-3-vertical-slice/build_dataset.py

# Lab 9: regenerate the committed episode + contingency-candidate fixtures
# from real grid2op runs. Only needed if the case data or the scenario change
# -- `just check-lab9` (fast, no grid2op) is what CI actually runs.
lab9-fixture:
    uv run --with grid2op --with pyyaml --no-binary-package grid2op python \
        labs/09-cim-gridy-phase1-3-vertical-slice/generate_fixture.py

# Lab 9: re-derive the README's N-1 outage sweep table for real (the numbers
# that ground RHO_LIMIT = 0.030 in generate_fixture.py) -- a committed,
# re-runnable script, not an ad hoc session transcript (AGENTS.md: "the proof
# scripts are the proof"). Read-only diagnostic, writes no fixture.
lab9-sweep:
    uv run --with grid2op --no-binary-package grid2op python \
        labs/09-cim-gridy-phase1-3-vertical-slice/sweep_outages.py

# --- notebook playbook (docs/backlog/0005) ----------------------------------
# Executes notebooks/lab_playbook.py (jupytext `percent` format -- plain
# .py, diffable, no baked-in outputs) end to end: every lab's own --step
# check re-run live, in order, each asserted PASS before that lab's
# already-committed fixtures/charts are rendered inline. Writes
# notebooks/lab_playbook.ipynb -- a regenerated execution artifact
# (gitignored, never committed; the .py is the committed source, matching
# AGENTS.md "the proof scripts are the proof, not a transcript").
playbook:
    uv run jupytext --to notebook --execute notebooks/lab_playbook.py

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

# Lab 6 pipeline step for one track, e.g. `just lab6`, `just lab6 run grid`, `just lab6 run pipeline`.
lab6 step="check" track="digital-thread":
    uv run labs/06-sysml-digital-thread/generate_sysml.py --track {{track}} --step {{step}}

# Lab 6 full demo: all three tracks, chained end to end (see scripts/demo_lab6.sh).
lab6-demo:
    ./scripts/demo_lab6.sh

# Lab 7: regenerate the committed COMTRADE fixtures + expected-finding JSON
# from a real precursor-scenario pandapower solve (~40s wall-clock). Only
# needs re-running if the precursor scenario's own physics change --
# `just check-lab7` (fast, no pandapower) is what CI/regression actually runs.
lab7-fixture:
    uv run python labs/07-rust-comtrade-fft-detector/generate_fixture.py

# --- demo: render the animations (PowerPoint-friendly MP4s) -----------------
render: render-lab1 render-lab2 render-lab5

render-lab1:
    uv run python labs/01-simple-loadflow-fit/animate_convergence.py

render-lab2:
    uv run python labs/02-medium-interconnection-screening/animate_contingencies.py

render-lab5:
    uv run python labs/05-spartan-chaosnet-transient-stream/animate_transient.py

# Lab 5 KISS viewer: isometric 3D phase-space PNG (committed sample) + a
# 3-channel WAV sonification (playable with mpv) + prints the peak-deviation
# anomaly bins (per 1 s / 5 s) that seed the anomaly classifier.
view-lab5:
    uv run python labs/05-spartan-chaosnet-transient-stream/view_3d_audio.py

# Lab 5 telemetry-rate views: static stacked still (sample_telemetry_rates.png,
# committed) + the animated isolated time-aligned feeds MP4 (gitignored).
view-lab5-rates:
    uv run python labs/05-spartan-chaosnet-transient-stream/view_telemetry_rates.py
    uv run python labs/05-spartan-chaosnet-transient-stream/animate_telemetry_rates.py

# Lab 5 time-frequency view: STFT spectrogram of the fault transient
# (sample_spectrogram.png, committed -- docs/backlog/0006 option 3).
view-lab5-spectrogram:
    uv run python labs/05-spartan-chaosnet-transient-stream/view_spectrogram.py

# PRD-0005 Phase 1: run chaos_schedule.yaml's real fault twice -- once with
# the grid-forming stabilizer off, once on -- and print/write the real
# measured before/after mitigation (peak sag, recovery time, RoCoF) to
# stabilizer_comparison.json (gitignored, regenerated every run).
lab5-stabilizer:
    uv run labs/05-spartan-chaosnet-transient-stream/grid_forming.py --step run

# PRD-0005 Phase 1.5: translate the above stabilizer_comparison.json result
# into a steady-state constraint-headroom question against a real
# pandapower net (chaosnet.to_pandapower(), same topology as the DPsim
# run) and report the real yes/no on whether a binding constraint changed.
# Writes headroom_translation.json (gitignored, regenerated every run).
lab5-headroom:
    uv run labs/05-spartan-chaosnet-transient-stream/headroom_translation.py --step run

# PRD-0005 Phase 2: run chaos_schedule.yaml's real fault three ways (no
# stabilizer / stabilizer without delay compensation / stabilizer with
# cable-length delay compensation) and report the real peak-sag comparison.
# Writes delay_compensation.json (gitignored, regenerated every run).
lab5-delay-compensation:
    uv run labs/05-spartan-chaosnet-transient-stream/delay_compensation.py --step run

# --- Lab 5 VILLASnode stream tap (real podman pod, see README "Sandbox
# notes" 4-6 and kube/villasnode-tap-pod.yaml's own header) ------------------
# `run_dpsim.py` must have run at least once first -- it writes the real
# villas/chaos_stream.csv the pod reads. `just lab5-villasnode` runs the
# full up -> verify -> down round trip in one shot; the three split recipes
# below are for stepping through it by hand (e.g. to `podman logs`/`podman
# ps` against a pod left running between `up` and `down`).
villasnode-up:
    podman kube play {{justfile_directory()}}/kube/villasnode-tap-pod.yaml

villasnode-verify node="sub-3-tap":
    uv run labs/05-spartan-chaosnet-transient-stream/verify_stream.py --node {{node}}

villasnode-down:
    podman kube play --down {{justfile_directory()}}/kube/villasnode-tap-pod.yaml

lab5-villasnode: villasnode-up villasnode-verify villasnode-down

# --- Rust / WASM (the oxidized phase_model, PSCADOSSE) -----------------------
# Native (debug-profile) tests across the workspace -- includes
# real_log_matches_python (phase-model) and
# local_mode_matches_python_reference/inter_area_mode_matches_python_reference
# (fft-detector): the Rust ports must match the Python numbers exactly on
# real fixtures, not just pass synthetic unit tests.
#
# mission-engine is EXCLUDED here and only here, and the reason is real, not
# stylistic: its objective layer calls into scryer-prolog, which aborts
# (SIGABRT, "unsafe precondition(s) violated: NonNull::new_unchecked") inside
# its own Heap::clear under rustc's debug ub_checks. Lab 8 0d found this;
# Lab 9 re-confirmed it reproduces here. Release builds are unaffected, so
# `just check-lab9` is what actually tests this crate.
rust-test:
    cargo test --manifest-path rust/Cargo.toml --workspace --exclude mission-engine

# Build the simulation crate to WASM (the "sim compiled into wasm, shipped to
# the browser" piece the Dioxus UI will load client-side).
rust-wasm:
    cargo build --manifest-path rust/Cargo.toml -p phase-model --target wasm32-unknown-unknown

# Build the Dioxus web app -> scripts/demo_dist/ (served by `just demo`).
# Requires trunk + wasm-bindgen-cli (see docs/PSCADOSSE.md).
rust-web:
    trunk build --manifest-path rust/demo-app/Trunk.toml

# --- demo: browser dashboard + display without file transfer ----------------
# One command: starts a local HTTP server and opens the demo dashboard in your
# browser (WSL3/Windows capable -- no X, no WSLg dependency, full-res video +
# audio). `just demo-stop` stops it; `just demo-tui` is the terminal fzf
# fallback for an SSH-only session.
demo:
    #!/usr/bin/env bash
    set -euo pipefail
    pkill -f serve_demo.py 2>/dev/null || true
    nohup python3 -u scripts/serve_demo.py --open >/tmp/demo_server.log 2>&1 &
    sleep 1
    grep -m1 "http://" /tmp/demo_server.log

demo-stop:
    pkill -f serve_demo.py 2>/dev/null || true
    echo "demo server stopped (if it was running)."

# Terminal fallback: fzf menu of every visualization, launched in the SSH
# terminal (no browser needed).
demo-tui:
    ./scripts/demo.sh

# Lab launcher (issue #18): a ratatui menu of all 8 labs -- number, name,
# one-line description -- that dispatches to each lab's own `just` recipe on
# Enter (lab1..lab6, check-lab7, check-lab8; see rust/lab-launcher). Separate
# from demo-tui, which lists rendered visualizations, not labs.
launch:
    cargo run --manifest-path rust/Cargo.toml -p lab-launcher --release

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
