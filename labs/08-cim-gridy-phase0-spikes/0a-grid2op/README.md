# Phase 0a — Grid2Op real-tool spike

> Status: **done — real success, with three real blockers found and worked around.**

- **Parent PRDs:** [`docs/prd/0008-cim-gridy-mission-engine-prerequisites.md`](../../../docs/prd/0008-cim-gridy-mission-engine-prerequisites.md)
  (Prerequisite 1 / Phase 0a), [`docs/prd/0009-cim-gridy-incose-v-plan.md`](../../../docs/prd/0009-cim-gridy-incose-v-plan.md)
  (Phase 0a, unchanged from 0008).
- **Question:** does [Grid2Op](https://github.com/Grid2op/grid2op) (MPL-2.0, LF Energy) wrap this
  repo's own CSIRO `data/snemSA.m` case cleanly via its pandapower backend, and run at least one
  real episode/timestep?
- **Method:** a real attempt, not a docs read. Grid2Op installed ephemerally via `uv run --with`
  (this repo's `pyproject.toml`/`uv.lock` are untouched — confirmed with `git diff --stat
  pyproject.toml uv.lock` at the end of this spike, no output). This repo's own
  `labs/_shared/gridfit.load_case` (powerio → pandapower) is reused verbatim — the exact function
  Lab 1's `run.py` calls — to load `data/snemSA.m`.

## TL;DR

**It works — but not "cleanly."** Three real, independent bugs/incompatibilities had to be found
and worked around before `grid2op.make()` + `env.step()` produced a real, sane result against this
repo's own case data:

1. **grid2op 1.12.5's published PyPI wheel is broken** (`ModuleNotFoundError:
   grid2op.typing_variables` — a file missing from the wheel, present in the sdist). Worked around
   with `--no-binary-package grid2op`.
2. **pandapower 3.5.4's own `to_json`/`from_json` round-trip is broken** for a net that has already
   passed once through `pp.from_json_string` (exactly what `load_case` does) — `ValueError: cannot
   insert const_i_q_percent, already exists`. Worked around by re-stamping `net.version`/
   `net.format_version` to the real installed pandapower's values before saving.
3. **grid2op's `PandaPowerBackend` assumes dense, 0-based bus indices** (`IndexError: index 1634 is
   out of bounds for axis 0 with size 503`) — `snemSA.m`'s real bus IDs are non-sequential (already
   documented in `labs/01-simple-loadflow-fit/run.py`'s `TARGET_BUS` comment: "986, 1633, 1634, ...
   not 1..N"). Worked around with pandapower's own `create_continuous_bus_index`.

After all three fixes, one real episode step ran end to end against the real, solved snemSA.m case
(503 buses, 698 lines, 186 loads, 57 gens) and returned real, sane load/gen/line-loading state — see
"Running one episode" below for the actual numbers.

**The single most important finding for someone deciding whether to build on Grid2Op:** the
pandapower backend integration is real and does ultimately work, and each of the three blockers has
a small, understandable, one-line-ish fix — but none of the three is discoverable from Grid2Op's own
docs, and all three had to be root-caused by reading Grid2Op's and pandapower's actual source
(`pandaPowerBackend.py`, `convert_format.py`). "Wraps cleanly" is not true as shipped; "wraps
workably, with real engineering effort to root-cause each gap" is the honest verdict. A Phase-1 team
should budget real days for this integration layer, not treat it as a given.

## What grid2op actually requires on disk

Reverse-engineered directly from grid2op 1.12.5's own bundled example datasets
(`grid2op/data/*` in the installed package — not the docs, the actual shipped files), because
`grid2op.make()`'s real directory-shape requirements are not clearly spelled out in one place in
its docs.

The minimal shape, confirmed by reading `grid2op/data/blank/` (grid2op's own smallest bundled
example, meant exactly for "wrap an arbitrary grid" use):

```
<dataset_dir>/
  grid.json       # a plain pandapower.to_json() export — PandaPowerBackend.load_grid()
                   # calls pandapower.from_json(path) directly (pandaPowerBackend.py:377)
  config.py       # a `config = {...}` dict naming backend/action/reward/rules/chronics classes
  chronics/       # can be a near-empty directory when chronics_class=ChangeNothing
```

`config.py`, modeled on `grid2op/data/blank/config.py` (the exact file this spike's
`build_dataset.py` writes):

```python
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
```

`ChangeNothing` (`grid2op/Chronics/changeNothing.py`) is grid2op's own no-op chronics class — it
advances `current_datetime`/`max_iter` without requiring any `load_p.csv`/`prod_p.csv` time-series
files. This is the correct minimal choice for "wrap one static case snapshot," as opposed to
`Multifolder`/`GridStateFromFileWithForecasts` (what the fuller `rte_case5_example` bundled dataset
uses), which requires a real multi-day chronics directory tree (`load_p.csv.bz2`, `prod_p.csv.bz2`,
`maintenance.csv.bz2`, etc. per scenario folder) — real work for a later phase, not attempted here;
see "What a real Phase-1 integration would need" below.

`PandaPowerBackend.load_grid()` (`grid2op/Backend/pandaPowerBackend.py:356-`) only *warns*, doesn't
error, on pandapower element types it doesn't model (`trafo3w`, `sgen`, `switch`, `impedance`,
`ward`, `xward`, `dcline`, `measurement`) — so a case with those elements still loads, just with
reduced grid2op-side controllability over them. `snemSA.m` has none of these except `trafo3w=0,
sgen=0, switch=0` — i.e. it's already clean on this axis (confirmed by `build_dataset.py`'s own
printed element counts below).

## Blocker 1 — grid2op 1.12.5's published PyPI wheel is broken

**This blocked the literal instruction in this spike's own brief** ("install via
`uv run --with grid2op`") and had to be found before anything else could be attempted.

```
$ uv run --with grid2op python -c "import grid2op"
...
  File ".../grid2op/Space/GridObjects.py", line 35, in <module>
    from grid2op.typing_variables import CLS_AS_DICT_TYPING, N_BUSBAR_PER_SUB_TYPING
ModuleNotFoundError: No module named 'grid2op.typing_variables'
```

Confirmed as a real PyPI packaging defect, not a local misconfiguration, by diffing two clean
installs side by side:

```
$ uv venv /tmp/g2o_venv && uv pip install --python /tmp/g2o_venv/bin/python grid2op   # normal wheel install
$ find /tmp/g2o_venv/.../grid2op -iname '*typing_variable*'   # -> nothing, file absent

$ uv venv /tmp/g2o_venv_sdist && uv pip install --python /tmp/g2o_venv_sdist/bin/python \
      --no-binary grid2op grid2op==1.12.5   # force build from sdist
$ find /tmp/g2o_venv_sdist/.../grid2op -iname '*typing_variable*'
/tmp/g2o_venv_sdist/lib/python3.12/site-packages/grid2op/typing_variables.py   # -> present
```

`grid2op/Space/GridObjects.py:35` imports a module that exists in the source tree (and the sdist,
which is built from source) but was never included in the `grid2op-1.12.5-py3-none-any.whl`
published to PyPI. Every plain `pip install grid2op` / `uv pip install grid2op` / `uv run --with
grid2op` on PyPI today hits this immediately, on the very first `import grid2op` — this is not an
edge case, it's the default install path failing for everyone.

**Workaround used for the rest of this spike:**

```
uv run --with grid2op --no-binary-package grid2op python labs/08-cim-gridy-phase0-spikes/0a-grid2op/run_episode.py
```

Real and cheap, but worth re-checking on a later grid2op release before Phase 1 pins a version —
if a `1.12.6+` fixes the wheel, this flag becomes unnecessary.

## Sandbox note: this session's host was under heavy load

`uptime` during this spike showed `load average: 31.72, 32.36, 31.48` with 106 concurrent user
sessions on the shared host. Processes doing nothing more exotic than parsing a 257KB `.m` file via
`load_case`, or importing `pandapower`/`numba`/`grid2op` cold, sat in Linux `D` (uninterruptible
disk-sleep) state for minutes at a time — confirmed directly via `/proc/<pid>/status` and
`/proc/<pid>/io` showing steadily climbing `read_bytes` (real forward progress, not a hang/deadlock)
across repeated checks. This is host-level I/O contention, not a defect in grid2op, pandapower, or
this spike's own code. Named here per this repo's `AGENTS.md` "sandbox stand-ins must be named"
convention — a production run on a dedicated machine would be materially faster than the wall-clock
times implied by this session.

## Building the dataset from this repo's own case data

`build_dataset.py` in this directory reuses `labs/_shared/gridfit.load_case` verbatim to load
`data/snemSA.m`, runs one real `pandapower.runpp()` (matching Lab 1's own base-case solve), applies
the two pandapower-side fixes below, then writes `pandapower.to_json()` output as
`dataset_snemSA/grid.json` plus the `config.py`/`chronics/` scaffold above. Real output from
`uv run labs/08-cim-gridy-phase0-spikes/0a-grid2op/build_dataset.py`:

```
Loaded snemSA.m via powerio: 503 buses, 295 lines, 403 trafos, 57 gens, 0 sgens, 0 ext_grid, 186 loads, 0 switches, 782 shunts
powerio conversion warnings: 2 (first 3: ['698 branch angle limit(s) dropped: pandapower line/trafo tables do not carry MATPOWER angle limits', "714 transformer terminal charging shunt(s) written into `shunt`: pandapower's trafo magnetizing model is inductive only, so MATPOWER transformer line charging b rides as bus shunts (Y_bus exact)"])
Reindexed 503 buses to a dense 0..N-1 range (grid2op's PandaPowerBackend requires this; snemSA.m's real bus IDs are not sequential -- see README.md)
Base-case AC power flow converged: True
Wrote .../dataset_snemSA/grid.json
Wrote .../dataset_snemSA/config.py
chronics/ dir present (empty, ChangeNothing needs no files): .../dataset_snemSA/chronics
```

(295 lines + 403 trafos = grid2op's later-reported `n_line=698`, since grid2op's `PandaPowerBackend`
treats trafos as lines in its own unified line-index space — expected, not a bug.)

### Blocker 2 — pandapower's own `to_json`/`from_json` round-trip is broken for this repo's net

Discovered mid-spike: `grid2op.make()` got as far as `PandaPowerBackend.load_grid()` calling
`pandapower.from_json(grid.json)`, and crashed *inside pandapower itself*, before grid2op's own code
ran at all:

```
  File ".../pandapower/convert_format.py", line 337, in _rename_columns
    net.load.insert(net.load.columns.get_loc('const_i_p_percent') + 1, 'const_i_q_percent', net.load.const_i_p_percent)
  File ".../pandas/core/frame.py", line 5180, in insert
    raise ValueError(f"cannot insert {column}, already exists")
ValueError: cannot insert const_i_q_percent, already exists
```

Confirmed as a pure pandapower bug, independent of grid2op, by reproducing it with pandapower alone
(no grid2op imported at all):

```python
>>> import pandapower as pp
>>> net = pp.from_json("labs/08-cim-gridy-phase0-spikes/0a-grid2op/dataset_snemSA/grid.json")
...
ValueError: cannot insert const_i_q_percent, already exists
```

Root cause, traced exactly: `labs/_shared/gridfit.load_case`'s `pp.from_json_string(pp_json)` call
(powerio's own MATPOWER→pandapower-JSON output) leaves the resulting net stamped with `net.version =
net.format_version = "3.0.0"` — an old pandapower schema marker — **even though the net's `load`
table already has the current schema's columns** (both `const_i_p_percent` and
`const_i_q_percent` present). Confirmed directly:

```python
>>> net.format_version, net.version
('3.0.0', '3.0.0')
>>> from pandapower._version import __format_version__
>>> __format_version__
'3.1.0'
>>> 'const_i_p_percent' in net.load.columns, 'const_i_q_percent' in net.load.columns
(True, True)
```

`pandapower.convert_format()` (`convert_format.py:30-`) has this clamp:

```python
if Version(str(net.format_version)) > Version(str(net.version).split('.dev')[0]):
    net.format_version = net.version
```

Since `net.version` stays `"3.0.0"` regardless of what `net.format_version` is set to, this clamp
resets `format_version` back down to `"3.0.0"` on every load, which re-triggers the (non-idempotent)
`3.0.0 → 3.1.0` column-migration path (`_rename_columns`) every single time — and that migration
unconditionally tries to insert a column that, this time, is already there. This means **any**
`pp.to_json()` → `pp.from_json()` round-trip of a net produced via `load_case()` is broken, not
something specific to grid2op — it has simply never surfaced in Labs 1-5, because none of them ever
reload a net from JSON a second time; they load once via `load_case()` and operate on the in-memory
object for the rest of the run. Grid2Op's architecture (always reloading `grid.json` from disk via
`PandaPowerBackend.load_grid()`) is the first thing in this repo to exercise that second round-trip.

**Fix (in `build_dataset.py`, verified working):** stamp both fields to the real, currently-running
pandapower's own version strings before saving:

```python
from pandapower._version import __version__ as PP_VERSION, __format_version__ as PP_FORMAT_VERSION
net.version = PP_VERSION
net.format_version = PP_FORMAT_VERSION
```

### Blocker 3 — grid2op's PandaPowerBackend requires dense 0..N-1 bus indices

With Blocker 2 fixed, `grid2op.make()` got further — past `pp.from_json`, past
`_check_for_non_modeled_elements`, into `PandaPowerBackend._init_private_attrs()` — and hit a new,
different real error:

```
  File ".../grid2op/Backend/pandaPowerBackend.py", line 694, in _init_private_attrs
    self.sub_info[sub_or_id] += 1
IndexError: index 1634 is out of bounds for axis 0 with size 503
```

Root cause: grid2op's `PandaPowerBackend` treats one pandapower bus as one substation, and
pre-allocates `sub_info = np.zeros(n_bus)` (correctly sized 503), but then indexes into it using
each line/trafo's **raw pandapower bus ID** (`from_bus`/`to_bus`) directly, with no lookup through
`net.bus.index` — i.e. it silently assumes bus IDs are a dense `0..n_bus-1` range. `snemSA.m`'s real
bus IDs are not sequential — this is already documented in this repo's own
`labs/01-simple-loadflow-fit/run.py` (`TARGET_BUS` comment: "snemSA.m's real bus IDs are
non-sequential (986, 1633, 1634, ... not 1..N)"). Bus `1634` is real CSIRO case data, not a bug in
this repo's loader.

**Fix (in `build_dataset.py`, verified working):** pandapower ships exactly this utility —

```python
from pandapower.toolbox import create_continuous_bus_index
bus_lookup = create_continuous_bus_index(net, start=0)
```

## Running one episode

Real command (from the repo root, after `build_dataset.py` has written the fixed dataset):

```
uv run --with grid2op --no-binary-package grid2op python \
    labs/08-cim-gridy-phase0-spikes/0a-grid2op/run_episode.py
```

Real output:

```
grid2op version: 1.12.5
Environment created: <Environment_dataset_snemSAPandaPowerBackend instance named dataset_snemSAPandaPowerBackend>
n_sub=503 n_line=698 n_load=186 n_gen=57
Initial obs: 186 loads, 57 gens, 698 line-origin voltages
load_p (first 5 MW): [138.5526   -43.45995   -2.006882 -23.353794 -19.8507  ]
gen_p (first 5 MW): [2.7496748e+01 8.0896912e+01 1.7264698e+01 0.0000000e+00 5.5543519e-30]
rho (line loading, first 5): [0.00827552 0.00033702 0.00816415 0.00029929 0.00040886]
After 1 step: done=False reward=1.0
post-step load_p (first 5 MW): [138.5526   -43.45995   -2.006882 -23.353794 -19.8507  ]
post-step gen_p (first 5 MW): [2.7496748e+01 8.0896912e+01 1.7264698e+01 0.0000000e+00 5.5543519e-30]
post-step rho (first 5): [0.00827552 0.00033702 0.00816415 0.00029929 0.00040886]
post-step topo_vect (first 10): [1 1 1 1 1 1 1 1 1 1]
Episode step completed successfully; environment closed.
```

`env.reset()` and one `env.step(env.action_space({}))` (grid2op's own canonical do-nothing action)
both ran to completion. `done=False, reward=1.0` (a `FlatReward` of 1.0 for a non-terminal step,
matching this spike's minimal `config.py`), the reported `n_sub`/`n_line`/`n_load`/`n_gen` counts
exactly match `build_dataset.py`'s own printed element counts, and `load_p`/`gen_p`/`rho` are real
values carried over from the real, converged `pandapower.runpp()` solve — not fabricated,
zero-filled, or placeholder data. `load_p` values include negatives (e.g. `-43.46 MW`) reflecting
`snemSA.m`'s own MATPOWER PQ-bus data as loaded by powerio, not an artifact of this spike.
`ChangeNothing`'s do-nothing step correctly leaves state numerically identical pre/post-step (no
chronics driving any change yet — expected, since Phase 1's real "calendar step" scenario data is
exactly what's not built yet, see below).

## Verdict

**Real success, with real friction.** Grid2Op's pandapower backend does genuinely wrap this repo's
own CSIRO case data and run real episode steps that reflect the real, solved grid state — the core
PRD-0008/0009 premise ("Grid2Op is not a tool to evaluate from a cold start; it's built to consume
exactly the kind of case data this repo already has") holds up under an actual attempt, not just on
paper. But "wraps cleanly" oversold it: three independent, real bugs/incompatibilities (a broken
PyPI wheel, a broken pandapower JSON round-trip triggered by this repo's own loading pattern, and a
bus-indexing assumption this repo's real case data violates) had to be found by reading source code,
not docs, before any of this worked. None of the three is exotic or a dead end — all three have
small, durable fixes now captured in `build_dataset.py` — but "install it and go" was never true.

## What a real Phase-1 integration would need

- Carry forward the three fixes above (or their durable equivalents) into whatever code owns the
  pandapower → grid2op dataset export going forward — they are not one-off spike hacks, they will
  recur for `data/snem1803.m` and any other CSIRO case slice this repo loads the same way.
- Decide `ChangeNothing` vs. a real chronics tree (`Multifolder` + per-scenario `load_p.csv`/
  `prod_p.csv`) — the "calendar steps" mission concept in PRD-0008/0009 almost certainly wants real
  chronics (varying load/gen per step), not a static `ChangeNothing` grid frozen at one snapshot;
  this spike deliberately used the minimal no-op path to answer "does the wrapper work at all"
  first, and it does — chronics authoring is real, separate work.
- Pin an exact grid2op version once the wheel-packaging bug is confirmed fixed upstream, or document
  `--no-binary-package grid2op` as a permanent, committed requirement if not (check before Phase 1
  commits to a version).
- No `grid_layout.json` was provided in this spike's dataset (grid2op warns but doesn't fail without
  one) — grid2op's own bundled datasets all ship one for plotting/rendering. PRD-0008 already flags
  `snemSA.m` itself has no real geographic coordinates, so this is the same open gap surfacing again
  on the grid2op side, not a new one — Lab 1's own `_plot_network` synthetic-layout approach
  (`networkx.spring_layout`) is a plausible stand-in to adapt here too.
- `create_continuous_bus_index`'s `bus_lookup` return value should be persisted/logged if any
  downstream code needs to map a grid2op substation ID back to `snemSA.m`'s real bus ID (e.g. for
  a mission's card text to reference a real, recognizable bus) — this spike prints the count but
  discards the mapping; Phase 1 will want to keep it.
