#!/usr/bin/env python3
"""Lab 9 Phase 1 -- build the Grid2Op dataset directory wrapping this repo's
own CSIRO `data/snemSA.m` case, graduated from Lab 8's Phase 0a spike
(`labs/08-cim-gridy-phase0-spikes/0a-grid2op/build_dataset.py`).

Run inside the *project's own* uv environment (pandapower + powerio; this
script does NOT import grid2op itself, it only writes grid2op's on-disk
dataset layout):

    uv run labs/09-cim-gridy-phase1-3-vertical-slice/build_dataset.py

Carries forward all three of 0a's real, root-caused fixes verbatim (see that
spike's README for the full diagnosis of each -- they are reproduced in
condensed form at their use sites below), plus two Phase-1 changes 0a
explicitly deferred:

1. **`bus_lookup` is persisted**, not discarded. 0a's own "What a real Phase-1
   integration would need" says: "`create_continuous_bus_index`'s `bus_lookup`
   return value should be persisted/logged if any downstream code needs to map
   a grid2op substation ID back to `snemSA.m`'s real bus ID ... this spike
   prints the count but discards the mapping; Phase 1 will want to keep it."
   PRD-0009 Phase 2 (Lab 6 CIM-URI traceability) is exactly that downstream
   code, so it is written to `dataset_snemSA/bus_lookup.json` and copied to
   the committed `fixtures/bus_lookup.json`.
2. **`action_class` is `TopologyAction`, not `DontAct`.** 0a only needed
   `env.step(do_nothing)`; Lab 9's `generate_fixture.py` has to force a real
   line disconnection to produce a genuine overload, and `DontAct` rejects
   every action by construction. `TopologyAction` is grid2op's own
   line-status/topology action class -- still no redispatch, which this lab
   does not use.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandapower as pp

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "labs"))

from _shared.gridfit import load_case  # noqa: E402

DATA_FILE = REPO_ROOT / "data" / "snemSA.m"
LAB_DIR = Path(__file__).resolve().parent
DATASET_DIR = LAB_DIR / "dataset_snemSA"
CHRONICS_DIR = DATASET_DIR / "chronics"
FIXTURES_DIR = LAB_DIR / "fixtures"

GRID_JSON_FILE = DATASET_DIR / "grid.json"
BUS_LOOKUP_FILE = DATASET_DIR / "bus_lookup.json"
FIXTURE_BUS_LOOKUP_FILE = FIXTURES_DIR / "bus_lookup.json"

# Modeled on grid2op's own bundled `blank` dataset config (0a reverse-engineered
# this from the installed package, not the docs). The one deliberate divergence
# from 0a: action_class = TopologyAction so a real line disconnection is a legal
# action -- see this module's docstring.
CONFIG_PY_CONTENT = '''\
from grid2op.Action import TopologyAction
from grid2op.Reward import FlatReward
from grid2op.Rules import AlwaysLegal
from grid2op.Chronics import ChangeNothing
from grid2op.Backend import PandaPowerBackend

config = {
    "backend": PandaPowerBackend,
    "action_class": TopologyAction,
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
          f"{len(net.gen)} gens, {len(net.load)} loads")
    print(f"powerio conversion warnings: {len(warnings)}")

    # 0a Blocker 2: pandapower 3.5.4's to_json/from_json round-trip is broken
    # for a net that has already passed through pp.from_json_string once (which
    # is exactly what _shared.gridfit.load_case does). powerio's export stamps
    # net.version = net.format_version = "3.0.0" while net.load already carries
    # the current schema's columns, so convert_format() re-runs the
    # non-idempotent 3.0.0 -> 3.1.0 _rename_columns migration on every load and
    # raises `ValueError: cannot insert const_i_q_percent, already exists`.
    from pandapower._version import __version__ as PP_VERSION
    from pandapower._version import __format_version__ as PP_FORMAT_VERSION
    net.version = PP_VERSION
    net.format_version = PP_FORMAT_VERSION

    # 0a Blocker 3: grid2op's PandaPowerBackend._init_private_attrs() indexes
    # `sub_info = np.zeros(n_bus)` with each branch's raw pandapower bus ID, so
    # it silently requires a dense 0..N-1 bus index. snemSA.m's real bus IDs are
    # not sequential (986, 1633, 1634, ...), which raises
    # `IndexError: index 1634 is out of bounds for axis 0 with size 503`.
    from pandapower.toolbox import create_continuous_bus_index
    bus_lookup = create_continuous_bus_index(net, start=0)
    print(f"Reindexed {len(bus_lookup)} buses to a dense 0..N-1 range")

    pp.runpp(net)
    print(f"Base-case AC power flow converged: {net.converged}")

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    CHRONICS_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    pp.to_json(net, str(GRID_JSON_FILE))
    print(f"Wrote {GRID_JSON_FILE}")

    (DATASET_DIR / "config.py").write_text(CONFIG_PY_CONTENT)
    print(f"Wrote {DATASET_DIR / 'config.py'}")

    # The Phase-1 addition 0a called for: keep the mapping. Keys are the
    # ORIGINAL (pre-reindex) pandapower bus IDs -- the ones Lab 6's
    # schema/grid_instances.yaml quotes in each bus's `source:` field
    # ("data/snemSA.m (pandapower bus index 1683)") -- values are the dense
    # 0..N-1 IDs grid2op sees as substation IDs. JSON object keys must be
    # strings, so the int keys are stringified; Phase 2's Rust side parses
    # them back.
    payload = {str(old): int(new) for old, new in bus_lookup.items()}
    BUS_LOOKUP_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    FIXTURE_BUS_LOOKUP_FILE.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    print(f"Wrote {BUS_LOOKUP_FILE} ({len(payload)} entries)")
    print(f"Wrote {FIXTURE_BUS_LOOKUP_FILE} (committed fixture copy)")

    print(f"chronics/ dir present (empty, ChangeNothing needs no files): "
          f"{CHRONICS_DIR}")


if __name__ == "__main__":
    main()
