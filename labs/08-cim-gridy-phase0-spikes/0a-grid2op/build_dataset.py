#!/usr/bin/env python3
"""Phase 0a spike -- build a minimal Grid2Op dataset directory wrapping
this repo's own CSIRO snemSA.m case data via Grid2Op's PandaPowerBackend.

Run inside the *project's own* uv environment (has pandapower + powerio,
matching this repo's established loading pattern) -- this script does NOT
need grid2op itself, it only produces grid2op's on-disk dataset layout:

    uv run labs/08-cim-gridy-phase0-spikes/0a-grid2op/build_dataset.py

See README.md in this directory for the full writeup of why this
structure is what Grid2Op's PandaPowerBackend.load_grid() and
grid2op.make() actually require (reverse-engineered from grid2op 1.12.5's
own bundled "blank" example dataset,
grid2op/data/blank/{config.py,grid.json,chronics/}, not guessed).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandapower as pp

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "labs"))

from _shared.gridfit import load_case  # noqa: E402

DATA_FILE = REPO_ROOT / "data" / "snemSA.m"
SPIKE_DIR = Path(__file__).resolve().parent
DATASET_DIR = SPIKE_DIR / "dataset_snemSA"
CHRONICS_DIR = DATASET_DIR / "chronics"

# grid2op's PandaPowerBackend.load_grid() calls pandapower.from_json(path)
# directly (grid2op/Backend/pandaPowerBackend.py:377) -- so grid.json must
# be a plain pandapower.to_json() export, the exact format this repo's own
# labs 1-4 already produce/consume nowhere else, but a standard pandapower
# API regardless.
GRID_JSON_FILE = DATASET_DIR / "grid.json"

# Minimal config.py, modeled directly on grid2op's own bundled "blank"
# dataset (grid2op/data/blank/config.py in the installed 1.12.5 package --
# see README.md "What grid2op actually requires on disk" for the file
# listing this was read from). ChangeNothing is grid2op's own no-op
# chronics class (grid2op/Chronics/changeNothing.py): it advances
# current_datetime and max_iter without requiring any load_p.csv/gen
# time-series files on disk -- the correct minimal choice for "wrap an
# existing static case, not a multi-day scenario" per this spike's scope.
CONFIG_PY_CONTENT = '''\
from grid2op.Action import DontAct
from grid2op.Reward import FlatReward
from grid2op.Rules import AlwaysLegal
from grid2op.Chronics import ChangeNothing
from grid2op.Backend import PandaPowerBackend

config = {
    "backend": PandaPowerBackend,
    "action_class": DontAct,
    "observation_class": None,
    "reward_class": FlatReward,
    "gamerules_class": AlwaysLegal,
    "chronics_class": ChangeNothing,
    "grid_value_class": None,
    "volagecontroler_class": None,
    "thermal_limits": None,
    "names_chronics_to_grid": None,
}
'''


def main() -> None:
    """Load snemSA.m the exact way labs/01's run.py does (powerio ->
    pandapower via `_shared.gridfit.load_case`), then export it into a
    grid2op-shaped dataset directory under this spike's own folder.
    """
    if not DATA_FILE.exists():
        print(
            f"[FAIL] {DATA_FILE} not found -- run "
            f"'uv run scripts/fetch_csiro_nem_data.py' first",
            file=sys.stderr,
        )
        sys.exit(1)

    net, warnings = load_case(DATA_FILE)
    print(f"Loaded snemSA.m via powerio: {len(net.bus)} buses, "
          f"{len(net.line)} lines, {len(net.trafo)} trafos, "
          f"{len(net.gen)} gens, {len(net.sgen)} sgens, "
          f"{len(net.ext_grid)} ext_grid, {len(net.load)} loads, "
          f"{len(net.switch)} switches, {len(net.shunt)} shunts")
    print(f"powerio conversion warnings: {len(warnings)} "
          f"(first 3: {warnings[:3]})")

    # Real, reproducible pandapower 3.5.4 bug worked around here -- see
    # README.md "pandapower's own to_json/from_json round-trip is broken
    # for this repo's net" for the full diagnosis. powerio's
    # pandapower-JSON export stamps net.version = net.format_version =
    # "3.0.0" (an old pandapower schema marker), but net.load already
    # carries the *current* schema's columns (both const_i_p_percent and
    # const_i_q_percent). pandapower.convert_format() clamps
    # format_version down to net.version on load regardless of what
    # format_version says (convert_format.py: "if format_version >
    # version: format_version = version"), so it always re-attempts the
    # 3.0.0->3.1.0 "_rename_columns" migration on every subsequent
    # pp.from_json() of this net -- and that migration is not idempotent:
    # it unconditionally tries to insert a column that's already there,
    # raising `ValueError: cannot insert const_i_q_percent, already
    # exists`. Confirmed directly: this reproduces with plain
    # pandapower alone (pp.to_json + pp.from_json), no grid2op involved --
    # it is exactly the "load once via load_case(), never round-trip
    # through JSON again" pattern every existing lab (1-5) already
    # follows, which is why this bug has never surfaced in this repo
    # before grid2op's PandaPowerBackend.load_grid() (which always reloads
    # grid.json from disk) hit it. Stamping both fields to the real,
    # currently-installed pandapower's own version strings before saving
    # is the minimal fix -- verified: without this, the round-trip raises
    # immediately.
    from pandapower._version import __version__ as PP_VERSION
    from pandapower._version import __format_version__ as PP_FORMAT_VERSION
    net.version = PP_VERSION
    net.format_version = PP_FORMAT_VERSION

    # Second real, reproducible blocker worked around here: grid2op's
    # PandaPowerBackend._init_private_attrs() (grid2op/Backend/
    # pandaPowerBackend.py:694) assumes one substation per pandapower bus,
    # indexed 0..n_bus-1 dense, and pre-allocates
    # `self.sub_info = np.zeros(n_bus)` accordingly -- then indexes into it
    # using each line/trafo's raw `from_bus`/`to_bus` pandapower bus ID
    # directly, with no lookup through net.bus.index. snemSA.m's real bus
    # IDs are non-sequential (documented already in
    # labs/01-simple-loadflow-fit/run.py's TARGET_BUS comment: "986, 1633,
    # 1634, ... not 1..N"), so this raises
    # `IndexError: index 1634 is out of bounds for axis 0 with size 503`
    # the moment grid2op tries to load this repo's case -- confirmed by
    # a live run.py --with grid2op attempt against the unreindexed net,
    # see README.md "grid2op's PandaPowerBackend requires dense 0..N-1 bus
    # indices". Fixed by reindexing with pandapower's own
    # `create_continuous_bus_index` (pandapower/toolbox/
    # data_modification.py) *before* solving/exporting -- a standard
    # pandapower utility, not a hand-rolled workaround.
    from pandapower.toolbox import create_continuous_bus_index
    bus_lookup = create_continuous_bus_index(net, start=0)
    print(f"Reindexed {len(bus_lookup)} buses to a dense 0..N-1 range "
          f"(grid2op's PandaPowerBackend requires this; snemSA.m's real "
          f"bus IDs are not sequential -- see README.md)")

    pp.runpp(net)
    print(f"Base-case AC power flow converged: {net.converged}")

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    CHRONICS_DIR.mkdir(parents=True, exist_ok=True)

    pp.to_json(net, str(GRID_JSON_FILE))
    print(f"Wrote {GRID_JSON_FILE}")

    (DATASET_DIR / "config.py").write_text(CONFIG_PY_CONTENT)
    print(f"Wrote {DATASET_DIR / 'config.py'}")

    # ChangeNothing's GridValue base class still probes the chronics/
    # directory for structure (MULTI_CHRONICS=False, but MakeFromPath's
    # dataset-shape detection looks for *a* chronics/ dir to exist) --
    # an empty directory is sufficient; no CSV time-series files needed.
    # See README.md "What broke" if this assumption turns out wrong.
    print(f"chronics/ dir present (empty, ChangeNothing needs no files): "
          f"{CHRONICS_DIR}")


if __name__ == "__main__":
    main()
