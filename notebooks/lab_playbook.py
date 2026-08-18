# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # NEM PowerAgent Lab -- Unified Playbook
#
# `docs/backlog/0005-unified-notebook-playbook.md`: one linear document that
# narrates and renders what the five labs' own committed proof scripts
# already proved, in the order `README.md` teaches them
# (`install.sh` -> Lab 1 -> Lab 2 -> Lab 3 -> Lab 4 -> Lab 5).
#
# **This notebook computes nothing of its own.** `AGENTS.md` "Non-negotiable
# conventions" states plainly: *"The proof scripts are the proof, not a
# transcript ... Running commands ad hoc in a session is not proof anything
# works -- a committed script re-deriving the same result on a clean
# checkout is."* Every section below therefore does exactly two things, in
# order, and refuses to go further if the first one fails:
#
# 1. Shells out to that lab's own `--step check` (its real, current CLI
#    entry point -- `uv run labs/0N-.../<script>.py --step check`, per
#    `AGENTS.md` "Running the labs") and **asserts it exits 0**. A failed
#    check raises immediately, in-notebook -- this notebook will not plot
#    stale numbers next to a lab whose own proof doesn't currently hold.
# 2. Loads that lab's already-committed fixture JSON and displays that
#    lab's already-committed chart PNG(s) -- rendered, never recomputed.
#
# The one deliberate exception is Lab 3's `scorecard_chart.png`, which
# `AGENTS.md`'s own repo-layout notes document as gitignored, regenerated,
# local-only output (never committed) -- that section calls the lab's own
# `--step report` to regenerate it for real, the same real re-derivation
# `just lab3 report` runs, before displaying it (see that section for why).
#
# Nothing here is committed back to git: this file is jupytext `percent`
# format (plain `.py`, `# %%` cell markers) specifically so no rendered
# image or execution output ever lands in this notebook's own history --
# see `docs/backlog/0005` "Explicitly out of scope."
#
# Run it (see `Justfile`'s `playbook` recipe / `scripts/run_playbook.sh`):
#
# ```
# just playbook
# ```

# %%
"""Shared imports and helpers for every lab section below."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("module://matplotlib_inline.backend_inline")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from IPython.display import Image, display  # noqa: E402


def _find_repo_root(start: Path) -> Path:
    """Walk upward from `start` until a directory containing both this
    repo's `Justfile` and `AGENTS.md` is found.

    nbconvert executes a notebook with the notebook's own directory as CWD,
    and there is no `__file__` inside a live Jupyter kernel, so neither
    `Path(__file__)` nor a hard-coded relative path is reliable here --
    this is the same "don't assume where you're being run from" problem
    every lab script's own `LAB_DIR = Path(__file__).resolve().parent`
    solves for itself; this notebook solves the analogous problem by
    searching for a known repo-root marker instead.
    """
    for candidate in (start, *start.parents):
        if (candidate / "Justfile").exists() and (candidate / "AGENTS.md").exists():
            return candidate
    raise RuntimeError(f"could not find repo root (Justfile + AGENTS.md) above {start}")


REPO_ROOT: Path = _find_repo_root(Path.cwd())


def run_cmd(description: str, cmd: list[str]) -> str:
    """Run one command to completion and assert it exits 0.

    This is the notebook's "fail loudly" primitive: every lab section below
    calls this (via `run_lab_check`) before touching any fixture or chart,
    so a lab whose own proof currently fails stops this notebook's
    execution right there with a clear `AssertionError`, rather than
    silently falling through to plot old numbers.

    Args:
        description: human-readable label for the PASS/FAIL print and the
            assertion message.
        cmd: the full argv to run, executed with `REPO_ROOT` as CWD (every
            lab script's own path handling, e.g. `EXPECTED_FILE`, is
            relative to its own file location, not CWD, but data/fixture
            fetches elsewhere in this repo assume repo-root CWD, matching
            how `AGENTS.md` documents every command).

    Returns:
        The subprocess's captured stdout (for optional inline display).

    Raises:
        AssertionError: if the command exits non-zero.
    """
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
    assert result.returncode == 0, (
        f"{description} FAILED (exit {result.returncode}) -- this lab's own "
        "proof does not currently hold; refusing to render possibly-stale "
        "fixtures/charts below it. See stdout/stderr above."
    )
    print(f"PASS: {description}")
    return result.stdout


def run_lab_check(description: str, script: Path, *step_args: str) -> str:
    """Shell out to one lab script with `sys.executable` (this kernel's own
    interpreter -- the project's uv-managed venv, since this notebook is
    itself executed via `uv run jupytext --to notebook --execute`) rather
    than re-invoking `uv run` a second time. Mirrors the same subprocess
    pattern every lab's own `test_labN.py` pytest wrapper already uses
    (e.g. `labs/03-advanced-provider-bakeoff/test_lab3.py`).
    """
    return run_cmd(description, [sys.executable, str(script), *step_args])


def load_fixture(path: Path) -> Any:
    """Load an already-committed fixture/result JSON file. Never computes
    anything -- the preceding `run_lab_check` cell in each section is what
    proves this file's numbers are currently true; this just reads it."""
    assert path.exists(), f"expected committed fixture missing: {path}"
    return json.loads(path.read_text())


def show_chart(path: Path, caption: str) -> None:
    """Display an already-committed chart PNG inline. Never renders a new
    one -- the chart on disk is the artifact; this notebook only looks at
    it, per `docs/backlog/0005` "Explicitly out of scope."""
    assert path.exists(), f"expected committed chart missing: {path}"
    print(f"[chart] {caption}  ({path.relative_to(REPO_ROOT)})")
    display(Image(filename=str(path)))


# %% [markdown]
# ## 0. Setup -- `install.sh` / `uv sync`
#
# The full golden path (`./install.sh`) provisions `podman` pods (a local
# Phi-4-mini-instruct LLM server, a PowerMCP pandapower pod, a VILLASnode
# stream pod) via interactive/`sudo`-gated steps that are out of scope for a
# notebook cell to re-run unattended -- see `AGENTS.md`'s capability matrix
# and `install.sh` itself. What this notebook *can* safely and usefully
# re-assert on every run is that the pinned dependency set every lab script
# (and this notebook) needs actually resolves: `uv sync` is idempotent and
# side-effect-free to re-run, exactly the `Justfile`'s own `sync` recipe.

# %%
run_cmd("uv sync (pinned deps resolve)", ["uv", "sync"])

# %% [markdown]
# ## Lab 1 -- Simple Load-Flow Fit
#
# Single-agent bisection fit of a load-scaling parameter against the real
# CSIRO `snemSA.m` case, matching a field SCADA voltage at bus 2008. See
# `labs/01-simple-loadflow-fit/README.md`.

# %%
LAB1_DIR = REPO_ROOT / "labs" / "01-simple-loadflow-fit"
run_lab_check("Lab 1 --step check", LAB1_DIR / "run.py", "--step", "check")

# %%
lab1_fixture = load_fixture(LAB1_DIR / "expected_results.json")
lab1_fixture

# %% [markdown]
# Convergence, straight from the fixture just re-verified above (not
# recomputed here): the bisection search closed the gap between the
# base-case and field-SCADA voltage at the target bus down to
# `residual_pu`, comfortably inside `tolerance_pu`, in `iterations` steps.

# %%
fig, ax = plt.subplots(figsize=(5, 3))
bars = ["field SCADA", "base case (unscaled)", "fitted"]
values = [
    lab1_fixture["field_scada_voltage_pu"],
    lab1_fixture["base_case_voltage_pu"],
    lab1_fixture["fitted_voltage_pu"],
]
ax.bar(bars, values, color=["#8c8c8c", "#c44e52", "#4c72b0"])
ax.axhline(
    lab1_fixture["field_scada_voltage_pu"], color="#8c8c8c", linestyle="--", linewidth=1
)
ax.set_ylabel(f"bus {lab1_fixture['target_bus']} voltage (pu)")
ax.set_ylim(min(values) - 0.01, max(values) + 0.01)
ax.set_title(
    f"Lab 1 fit converged in {lab1_fixture['iterations']} iterations: "
    f"residual {lab1_fixture['residual_pu']:+.4f} pu "
    f"(tolerance ±{lab1_fixture['tolerance_pu']} pu)"
)
plt.tight_layout()
plt.show()

# %%
show_chart(
    LAB1_DIR / "sample_network_chart.png",
    "Lab 1 network topology (bus color = solved voltage, target bus highlighted)",
)

# %% [markdown]
# ## Lab 2 -- Medium Interconnection N-1 Screening
#
# Sequential base case + genuinely-concurrent N-1 contingency screen against
# the real CSIRO `snem1803.m` case, scored against voltage/loading planning
# bands. See `labs/02-medium-interconnection-screening/README.md`.

# %%
LAB2_DIR = REPO_ROOT / "labs" / "02-medium-interconnection-screening"
run_lab_check("Lab 2 --step check", LAB2_DIR / "workflow.py", "--step", "check")

# %%
lab2_fixture = load_fixture(LAB2_DIR / "expected_contingency_table.json")
lab2_df = pd.DataFrame(lab2_fixture)
lab2_df.sort_values("worst_loading_percent", ascending=False).head(10)

# %%
show_chart(
    LAB2_DIR / "sample_contingency_chart.png",
    "Lab 2 worst-case contingency loading vs planning bands",
)

# %% [markdown]
# ## Lab 3 -- Advanced Provider Bake-off
#
# 3 task families x 3 provider stand-ins + a non-agentic forecasting
# baseline, scored into a diffable scorecard. See
# `labs/03-advanced-provider-bakeoff/README.md`.
#
# `scorecard_chart.png` is deliberately **not** a committed fixture --
# `AGENTS.md`'s own repo-layout notes: *"Both `scorecard.json` and
# `scorecard_chart.png` are regenerated, local-only output from `--step
# report`/`--step check` ... never committed -- the committed, diffable
# fixture is `expected_scorecard.json`."* `orchestrator.py`'s own
# `check_step()` re-derives the JSON rows via `sweep_step()` directly and
# never calls `report_step()`, so the chart PNG does not necessarily exist
# on disk after just the check below. This section therefore also calls the
# lab's own `--step report` -- the same real re-derivation `just lab3
# report` runs, not an independent computation invented in this notebook --
# to regenerate it before displaying it.

# %%
LAB3_DIR = REPO_ROOT / "labs" / "03-advanced-provider-bakeoff"
run_lab_check("Lab 3 --step check", LAB3_DIR / "orchestrator.py", "--step", "check")

# %%
lab3_fixture = load_fixture(LAB3_DIR / "expected_scorecard.json")
lab3_df = pd.DataFrame(lab3_fixture)
lab3_df

# %%
run_lab_check(
    "Lab 3 --step report (regenerates scorecard_chart.png, gitignored/local-only)",
    LAB3_DIR / "orchestrator.py",
    "--step",
    "report",
)
SCORECARD_CHART_FILE = (
    REPO_ROOT / "benchmarks" / "power-agent-bench-lite" / "results" / "scorecard_chart.png"
)
show_chart(
    SCORECARD_CHART_FILE,
    "Lab 3 provider bake-off scorecard (regenerated this run -- gitignored, never committed)",
)

# %% [markdown]
# ## Lab 4 -- AEMO Digital-Twin Reconciliation
#
# Real `NEMOSIS` pulls of AEMO's live NEMWeb MMS archive, reconciled against
# a real `pandapower.runpp()` solve of the matching synthetic-generator
# subset. See `labs/04-aemo-digital-twin-reconciliation/README.md`.

# %%
LAB4_DIR = REPO_ROOT / "labs" / "04-aemo-digital-twin-reconciliation"
run_lab_check("Lab 4 --step check", LAB4_DIR / "reconcile.py", "--step", "check")

# %%
lab4_fixture = load_fixture(LAB4_DIR / "expected_reconciliation.json")
lab4_fixture

# %% [markdown]
# `"passed": false` above is not a notebook bug or a stale fixture. Lab 4's
# own `README.md` documents this as an *honest* result: the digital twin's
# modelled interconnector flow misses the actual AEMO-observed flow by more
# than the lab's own documented `tolerance_fraction`, and the closing memo
# quantifies exactly why. `--step check` still PASSes above because it only
# asserts this run *reproduces* `expected_reconciliation.json` exactly
# (including its `passed: false`), not that the reconciliation itself
# succeeded -- those are different questions, and conflating them is
# exactly the kind of silently-stale-looking-fine result this notebook's
# fail-loudly discipline exists to avoid.

# %%
show_chart(
    LAB4_DIR / "sample_reconciliation_chart.png",
    "Lab 4 modelled vs actual interconnector flow / losses",
)

# %% [markdown]
# ## Lab 5 -- Spartan Chaos-Net Transient Stream
#
# A real SimBench + NetworkX chaos-net topology, a real DPsim EMT solve
# (200us timestep) with a scheduled 3-phase fault, and a real VILLASnode UDP
# stream tap. See `labs/05-spartan-chaosnet-transient-stream/README.md`.
#
# This section runs **three** `--step check` gates, not the two the
# `Justfile`'s own `check-lab5` recipe wires up by default (which runs
# `generate_topology.py` with its bare default step -- topology
# *generation*, not `--step check` -- then `verify_stream.py --step
# check`). This notebook calls `generate_topology.py --step check`
# explicitly, and additionally calls `run_dpsim.py --step check`: the
# transient fixtures this section displays below
# (`expected_dpsim_run.json` / `dpsim_transient_log.json`) are exactly what
# that check re-derives and diffs, so per `AGENTS.md`'s "every lab is
# self-checking" convention, every fixture this notebook renders gets its
# own proof re-run first, not just the two the Justfile's shorthand
# happens to cover. `run_dpsim.py --step check` uses the fast countdown
# path (`FAST_COUNTDOWN_SECONDS`, not the interactive one) and completes in
# well under 30s; neither check requires a live pod (`verify_stream.py`'s
# own `check_step()` docstring: *"without requiring a live pod ... a
# network capture against a container that may or may not be running is
# not something a CI/pytest run should depend on"*).

# %%
LAB5_DIR = REPO_ROOT / "labs" / "05-spartan-chaosnet-transient-stream"
run_lab_check("Lab 5 topology --step check", LAB5_DIR / "generate_topology.py", "--step", "check")
run_lab_check("Lab 5 DPsim EMT solve --step check", LAB5_DIR / "run_dpsim.py", "--step", "check")
run_lab_check("Lab 5 stream verify --step check", LAB5_DIR / "verify_stream.py", "--step", "check")

# %%
lab5_topology = load_fixture(LAB5_DIR / "expected_topology.json")
lab5_dpsim = load_fixture(LAB5_DIR / "expected_dpsim_run.json")
lab5_stream = load_fixture(LAB5_DIR / "sample_stream_summary.json")
{"topology": lab5_topology, "dpsim_run": lab5_dpsim, "stream": lab5_stream}

# %%
show_chart(LAB5_DIR / "sample_topology_plot.png", "Lab 5 chaos-net topology")
show_chart(LAB5_DIR / "sample_transient_plot.png", "Lab 5 DPsim 3-phase fault transient (RMS/phasor view)")
show_chart(LAB5_DIR / "sample_transient_3d.png", "Lab 5 isometric 3D phase-space trajectory")
show_chart(LAB5_DIR / "sample_telemetry_rates.png", "Lab 5 telemetry feed rates (5kHz raw / C37.118 / SCADA)")
show_chart(
    LAB5_DIR / "sample_spectrogram.png",
    "Lab 5 STFT spectrogram of the fault transient (docs/backlog/0006 option 3)",
)

# %% [markdown]
# ## Summary
#
# Every section above ran that lab's own `--step check` (or, for Lab 5,
# checks) live in this execution and asserted PASS before rendering
# anything -- if you're reading this notebook's output, all five labs'
# proofs held on the machine/commit that executed it. Nothing above was
# recomputed independently of those checks, and no chart's pixels are owned
# by this notebook -- see `docs/backlog/0005` for the full rationale.
