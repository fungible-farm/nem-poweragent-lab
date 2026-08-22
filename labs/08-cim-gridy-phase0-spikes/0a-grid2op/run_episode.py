#!/usr/bin/env python3
"""Phase 0a spike -- make() the grid2op dataset built by build_dataset.py
and run one real step of one episode against this repo's own snemSA.m
case data.

Grid2Op itself is NOT a dependency of this repo's pyproject.toml/uv.lock
(this is an unproven Phase-0 spike, not a committed dependency yet, per
docs/prd/0008-cim-gridy-mission-engine-prerequisites.md). It must be
installed ephemerally via uv's `--with` mechanism, run from the repo root:

    uv run --with grid2op --no-binary-package grid2op \\
        labs/08-cim-gridy-phase0-spikes/0a-grid2op/run_episode.py

`--no-binary-package grid2op` is REQUIRED, not optional -- see README.md
"grid2op 1.12.5's published PyPI wheel is broken" for the exact
ModuleNotFoundError this works around (grid2op/typing_variables.py is
missing from the wheel but present in the sdist; confirmed by diffing the
two installs directly, not assumed).
"""
from __future__ import annotations

import sys
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
DATASET_DIR = SPIKE_DIR / "dataset_snemSA"


def main() -> None:
    if not DATASET_DIR.exists():
        print(
            f"[FAIL] {DATASET_DIR} not found -- run build_dataset.py first "
            f"(uv run labs/08-cim-gridy-phase0-spikes/0a-grid2op/build_dataset.py)",
            file=sys.stderr,
        )
        sys.exit(1)

    import grid2op  # noqa: E402  (only importable once --with grid2op is active)

    print(f"grid2op version: {grid2op.__version__}")

    env = grid2op.make(str(DATASET_DIR), test=True)
    print(f"Environment created: {env}")
    print(f"n_sub={env.n_sub} n_line={env.n_line} n_load={env.n_load} "
          f"n_gen={env.n_gen}")

    obs = env.reset()
    print(f"Initial obs: {len(obs.load_p)} loads, {len(obs.gen_p)} gens, "
          f"{len(obs.v_or)} line-origin voltages")
    print(f"load_p (first 5 MW): {obs.load_p[:5]}")
    print(f"gen_p (first 5 MW): {obs.gen_p[:5]}")
    print(f"rho (line loading, first 5): {obs.rho[:5]}")

    # A real do-nothing action -- grid2op's own canonical "no-op" (empty
    # dict), not a fabricated placeholder; env.action_space({}) is
    # documented grid2op API for "change nothing this step."
    do_nothing = env.action_space({})
    obs2, reward, done, info = env.step(do_nothing)

    print(f"After 1 step: done={done} reward={reward}")
    print(f"info: {info}")
    print(f"post-step load_p (first 5 MW): {obs2.load_p[:5]}")
    print(f"post-step gen_p (first 5 MW): {obs2.gen_p[:5]}")
    print(f"post-step rho (first 5): {obs2.rho[:5]}")
    print(f"post-step topo_vect (first 10): {obs2.topo_vect[:10]}")

    env.close()
    print("Episode step completed successfully; environment closed.")


if __name__ == "__main__":
    main()
