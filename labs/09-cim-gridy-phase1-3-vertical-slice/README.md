# Lab 9 — cim-gridy Phases 1-3: one real vertical slice

> Status: **done — the full chain runs end to end, headless and live.** 17 tests pass
> (`just check-lab9`); the live `--grid2op-live` bridge was also run for real against the
> 503-bus CSIRO case. Two things are honestly scoped down rather than faked — the mission's
> rho limit is 0.030, not 1.0, and the live action vocabulary is `do_nothing` only. Both are
> explained below. Three real bugs were found and fixed along the way (a `rhai`/Bevy
> `Send + Sync` mismatch, a live-bridge startup race, and an unresolvable Bevy 0.19.1 feature
> path), in the same spirit as Lab 8 0a's three.

Lab 8 answered "does each piece work in isolation?" for cim-gridy's five Phase-0 questions. This
lab answers the next one on PRD-0009's V: **does the whole chain work together for one minimal
mission?** Grid2Op's episode loop, a Bevy `App`, a real native-Rust SysML v2 parser, `ufo-types`'
`Satisfies<C>` backed by a real `scryer-prolog` query, a TOML/Rhai mission FSM, and `ufo-types`'
DARE optimizer — one process, one grid, one contingency, one committed fixture, exact assertions.

- **PRD:** [`docs/prd/0009-cim-gridy-incose-v-plan.md`](../../docs/prd/0009-cim-gridy-incose-v-plan.md),
  Phases 1 (minimal end-to-end mission), 2 (Lab 6 CIM-URI traceability), 3 (strategic-objective
  optimizer).
- **Builds directly on:** Lab 8's five spikes (`labs/08-cim-gridy-phase0-spikes/`) and Lab 6's
  SysML digital thread (`labs/06-sysml-digital-thread/`). Every one of Lab 8 0a's three
  root-caused grid2op/pandapower fixes is carried forward verbatim in `build_dataset.py`.

## What you'll do

- Run the whole mission headless against the committed fixture (`just check-lab9`) — five real
  grid2op steps replayed through a Bevy `App`, scored, and driven through the mission FSM.
- Optionally rebuild the grid2op dataset and regenerate the fixtures from the real CSIRO case
  (`just lab9-dataset`, `just lab9-fixture`).
- Optionally drive the same Bevy app off the real live grid2op subprocess (`just lab9-live`).

## The actual result

```
step  0 | phase Monitoring          | rho_max 0.026553 | overloaded  0/19 | Satisfied
step  1 | phase Monitoring          | rho_max 0.026553 | overloaded  0/19 | Satisfied
step  2 | phase ContingencyDetected | rho_max 0.037622 | overloaded  2/19 | Violated(2 of 19 cluster branches over rho limit 0.030: line_4128_4148, line_4129_4148)
step  3 | phase MitigationSelected  | rho_max 0.037622 | overloaded  2/19 | Violated(2 of 19 cluster branches over rho limit 0.030: line_4128_4148, line_4129_4148)
step  4 | phase Resolved            | rho_max 0.026553 | overloaded  0/19 | Satisfied

== Phase 3: strategic-objective optimizer ==
  1. reclose_line_4125_4128     SATISFIED  confidence=1.000000 rho_max=0.026553
  2. do_nothing                 VIOLATED   confidence=0.894737 rho_max=0.037622
  3. open_line_4117_4131        VIOLATED   confidence=0.894737 rho_max=0.037631
  DARE proposal dispatched Decide -> Act (accepted=true)
```

Step 2 is a real N-1 trip of the real 275 kV circuit `bus_4125`-`bus_4128`; step 4 is a real
reclose. Every `rho` is grid2op's own, from a converged pandapower solve of `data/snemSA.m`.
`rust/mission-engine/tests/` asserts all of it against exact reference values — the same
discipline as `rust/phase-model/tests/physics.rs::real_log_matches_python`.

## Design notes

### The rho limit is 0.030, not 1.0 — and that is measured, not fudged

The obvious `GridSecurityObjective { rho_limit: 1.0 }` would never fire on this case. CSIRO's
synthetic `snemSA.m` carries effectively unconstrained branch ratings — Lab 6's own schema header
already flags `sn_mva: 10000.0` as a synthetic-case artifact "two orders of magnitude above a real
generator step-up transformer's typical rating" — so grid2op derives a **uniform ~20,995 A thermal
limit for every one of the cluster's 19 branches**, and rho stays tiny.

That was not assumed. `sweep_outages.py` trips **all 19 single-branch outages in Lab 6's
cluster**, one at a time from a fresh `env.reset()`, and measures the resulting cluster maximum for
each -- a committed, re-runnable script (`just lab9-sweep`), not an ad hoc session transcript
(AGENTS.md: "the proof scripts are the proof, not a transcript"):

| Outage | Cluster max rho after |
|---|---|
| base case (nothing tripped) | 0.026553 |
| `line_4125_4128` (chosen) | 0.037622 |
| `line_4128_4148` | **0.037629** (largest of all 19; `line_4125_4128` chosen instead as *the*
  contingency for its more central position in the cluster -- both are real, both converge, either
  would ground the same threshold) |
| `line_4129_4148` | 0.031362 |
| `line_4124_4125` | 0.031228 |
| the other 10 convergent outages | 0.0246 – 0.0283 |
| `line_4094_4124`, `line_4095_4124`, `xfmr_4128_4052/4053/4054` | **power flow diverges** (`done=True`) |

14 outages converge, 5 diverge, 19 total -- run `just lab9-sweep` to reproduce this table directly
against the real grid2op environment.

So the honest options were: fabricate an overload, or pick a real threshold. This lab picks a real
threshold. `rho_limit = 0.030` sits between the real base-case cluster maximum (0.026553) and the
real post-contingency maximum (0.037622), so the crossing the objective scores is a genuine,
measured change in the real grid state. It is a **mission security threshold, not a thermal
rating**, and it is named as such in `objectives.rs`, in `contingency_candidates.json`, and here.
Getting a true rho > 1.0 out of this data needs real branch ratings, which `snemSA.m` does not
carry — that is a data problem for a later phase, not something to paper over here.

`line_4125_4128` was chosen as *the* contingency because it is one of the two largest real
cluster-wide loading increases of any outage whose power flow still converges (`line_4128_4148`
measures marginally higher, 0.037629 vs. 0.037622 -- both real, both convergent; `line_4125_4128`
was picked for being the more centrally-connected branch of the two, not for being the single
worst). The five divergent outages are a real, different kind of N-1 insecurity (they island
generator buses) and are noted, not modelled.

### The grid2op line-ordering correlation was verified, not assumed

Nothing in this repo had ever confirmed how grid2op's line/rho index space lines up with
pandapower's `net.line`/`net.trafo` tables. `generate_fixture.py` asserts it directly before
writing any fixture, and the live bridge re-asserts it at startup:

```
[verify] line ordering verified: all 698 grid2op line endpoints match net.line rows 0..294 then net.trafo rows 0..402
[verify] Lab 6 cluster cross-check: all 19 cluster branches connect the exact bus pair grid_instances.yaml records for them
```

The first check compares `env.line_or_to_subid`/`line_ex_to_subid` against the pandapower row
endpoints for **every** one of the 698 branches (not a sample). The second re-derives Lab 6's own
branch naming rule (`line_<from>_<to>` / `xfmr_<hv>_<lv>`, with `_2` suffixes for parallel
branches, from `build_grid_instances.py`) and checks each resulting name against the bus pair
`grid_instances.yaml` records for it. Both pass; the flattened `net.line`-then-`net.trafo`
ordering is real.

### `ledgrrr` is cited by PRD-0009, but `rhai` is what is actually used

PRD-0009 names `ledgrrr`'s **TOML → Rhai FSM → Mermaid → Rust enum** pipeline as a ready-made
pattern for the mission/calendar-step loop. This lab implements that *pattern* **directly against
the `rhai` crate**. `ledgrrr` itself is a large, unrelated local FinOps-ledger product at
`~/.dotfiles/vendor/ledgrrr`; it is **not vendored, not depended on, and not required** to build or
run anything here. Only the shape is borrowed.

`mission_fsm.toml` is the transition table; every `guard` in it is a real Rhai boolean expression
evaluated against a `rhai::Scope` populated from the live observation each tick. A unit test
cross-checks the TOML's `states` list against the `MissionPhase` Rust enum so code and data cannot
drift, and `render_mermaid()` emits `fixtures/mission_fsm.mmd` (also asserted byte-exact).

**Real finding:** `rhai::Engine` is neither `Send` nor `Sync` with default features (it holds
`Rc<Locked<Dynamic>>` and a non-`Sync` string interner), and a Bevy `Resource` must be both. The
`sync` feature — which swaps rhai's internal `Rc`/`RefCell` for `Arc`/`RwLock` — is therefore
required, not stylistic. Found by compiling, not by reading docs.

### Known cost: `mission-engine` lives inside `rust/`'s workspace

Unlike Lab 8's 0b/0d spike crates (deliberately outside `rust/`), this is a real fifth workspace
member. The consequence is real and worth naming: an unscoped
`cargo build --manifest-path rust/Cargo.toml` now also pulls Bevy, `scryer-prolog`,
`sysml-v2-parser`, and `rhai` transitively — 444 packages in the lockfile, ~2.5 minutes cold on 8
cores. `check-lab7` and `check-lab8` were already `-p <crate>`-scoped and are unaffected;
`check-lab9` is scoped the same way (`-p mission-engine`).

Bevy is pulled with `default-features = false` for exactly this reason: the headless path needs
neither wgpu, winit, nor audio, and `just check-lab9` never builds them.

### `--release` is required

Lab 8 0d documented a real, reproducible **debug-profile-only** panic inside `scryer-prolog`'s own
`Heap::clear` (a `NonNull::new_unchecked` UB check that fires under `rustc`'s debug `ub_checks`),
unrelated to `ufo-types`. It reproduces here, confirmed directly rather than taken on trust:

```
$ cargo test --manifest-path rust/Cargo.toml -p mission-engine --lib objectives
thread 'objectives::tests::prolog_query_finds_exactly_the_overloaded_branches' panicked at
  library/alloc/src/alloc.rs:121:30:
unsafe precondition(s) violated: NonNull::new_unchecked requires that the pointer is non-null
thread caused non-unwinding panic. aborting.
... (signal: 6, SIGABRT: process abort signal)
```

Release builds are unaffected. `check-lab9` always passes `--release`; a debug build here would be
a false-negative CI failure, not a regression. This also has one knock-on effect on an existing
recipe: `just rust-test` (debug, whole workspace) now excludes `mission-engine` explicitly, with
that reason spelled out in the Justfile — `check-lab9` is what actually tests this crate.

### Lab 6's `output/` is gitignored, so the committed fixture is what's read

PRD-0009's plan pointed at `labs/06-sysml-digital-thread/output/grid_topology.sysml`. That path is
gitignored (Lab 6 regenerates everything under `output/` on every run) and does not exist in a
fresh checkout, so it cannot be what a CI gate reads. Lab 9 reads Lab 6's *committed* half of the
same pair, `fixtures/expected_grid_topology.sysml` — byte-identical by construction, since Lab 6's
own `generate_sysml.py --step check` asserts exactly that equality.

### `Satisfies<C>` really does call into Prolog

Lab 8 0d explicitly stopped short of wiring the two crates together ("`Satisfies<C>` is not wired
to call into scryer-prolog for real proof-search here; that is future work"). This lab is that
wiring. Every evaluation builds a real fact base from the live observation —

```prolog
line_loading('line_4117_4124', 0.005626500).
...
overloaded(L) :- line_loading(L, R), R > 0.030000000.
```

— loads it into a real `MachineBuilder::default().build()` machine, runs `overloaded(L).`, and
translates the answers into a `SatisfiesResult`. 0d's empirically-found trailing-`False`-after-
solutions behaviour is handled explicitly (it means "no more solutions", not a fourth answer).
Confidence on a violation is `1 - overloaded/total`, so step 2's real 2-of-19 result scores
`0.894737`.

### Phase 2's join needs the bus lookup Lab 8 0a threw away

0a's own "what a real Phase-1 integration would need" list said: `create_continuous_bus_index`'s
`bus_lookup` "should be persisted/logged if any downstream code needs to map a grid2op substation
ID back to `snemSA.m`'s real bus ID ... this spike prints the count but discards the mapping".
Phase 2 is exactly that downstream code. `build_dataset.py` now writes it
(`fixtures/bus_lookup.json`, 503 entries), and `cim_trace.rs` uses it to join Lab 6's static model
(`bus_4052` is "pandapower bus index 1683") to the live episode (grid2op substation 52). Without
it the two halves cannot be connected at all.

### Interactive mode

`--interactive` builds a real window with a `bevy_ui` card feed (Lab 8 0e's verdict: build cards
natively in Bevy; OperatorFabric's `Card` severity model kept as a design reference, not a
dependency). It is behind the optional `interactive` cargo feature because it pulls
winit/wgpu/text rendering into the build, and **`just check-lab9` deliberately never builds it** —
no other lab in this repo needs a display, and keeping that true was a deliberate choice.

```
cargo build --manifest-path rust/Cargo.toml -p mission-engine --release --features interactive
```

compiles cleanly (verified this session, ~4 min cold: winit 0.30.13, wgpu 29.0.4, bevy_ui_render
0.19.1). It was **not run visually** in this session — this is a headless shared host, so claiming
a screenshot would be claiming something not done.

**Third real upstream bug found, this one in Bevy's own publishing:** the obvious feature to use is
Bevy's `ui` meta-feature, and it does not resolve at all —

```
error: failed to select a version for the requirement `bevy_animation = "^0.19.1"`
candidate versions found which didn't match: 0.19.0, 0.19.0-rc.3, ...
required by package `bevy_internal v0.19.1`
```

`bevy` 0.19.1 was published without a matching `bevy_animation` 0.19.1, so every feature path that
reaches `bevy_animation` (`ui` → `default_app` → `scene` → …) is unresolvable on crates.io today.
The `interactive` feature therefore lists its Bevy components explicitly
(`bevy_ui`/`bevy_ui_render`/`bevy_core_pipeline`/`bevy_winit`/`bevy_window`/`bevy_text`/
`default_font`/`x11`), which stays clear of `bevy_animation` and builds. Worth re-checking when
Bevy 0.19.2 lands.

**Two Bevy 0.19 API notes**, both found by compiling rather than assumed: `BorderRadius` is a field
on `Node`, not a standalone `Component` (it was one in earlier releases), and `TextFont::font_size`
takes a `FontSize` enum (`FontSize::Px(18.0)`), not a bare `f32`.

## Scope — what this lab does and does not cover

**Covered, for real:**

- One 15-bus/5-generator/19-branch cluster — Lab 6's, unchanged — with a Bevy `Entity` each.
- One fixed, named contingency (`n1_line_4125_4128`) and three real candidate remedial actions,
  each measured in its own real grid2op what-if run.
- The full observe → score → transition → rank → DARE-dispatch chain, headless and live.

**Explicitly not covered:**

- **The rest of the grid.** The episode runs the real full ~503-bus network; only the named
  cluster gets entities, objectives, and cards. Full-grid modelling is later work.
- **A real action vocabulary on the live bridge.** `--grid2op-live` sends `{"action":
  "do_nothing"}` every step (the bridge protocol also accepts `set_line_status`, which
  `generate_fixture.py` uses); an agent choosing actions live is not built.
- **Real chronics.** The dataset uses grid2op's `ChangeNothing`, so load/generation are frozen at
  one snapshot — the same deferral Lab 8 0a made. PRD-0009's "calendar steps" concept wants a real
  `Multifolder` chronics tree, which is separate, real work.
- **Everything in PRD-0009 Phases 4-6**: geographic positioning, standardized iconography, the
  rename/narrative rewrite, global expansion.

## Command

```
just check-lab9        # the gate: 17 tests, deterministic, offline, no grid2op needed
just lab9-dataset      # rebuild dataset_snemSA/ from data/snemSA.m (needs `just fetch` first)
just lab9-fixture      # regenerate the committed fixtures from real grid2op runs
just lab9-live         # drive the same Bevy app off the real grid2op subprocess (~1-2 min)
```

The live run's real output (this session), showing the correlation check and five real steps:

```
[bridge] line ordering verified: all 698 grid2op line endpoints match net.line rows 0..294 then net.trafo rows 0..402
[bridge] Lab 6 cluster cross-check: all 19 cluster branches connect the exact bus pair grid_instances.yaml records for them
step  0 | phase Monitoring          | rho_max 0.026553 | overloaded  0/19 | Satisfied
... (five steps; every action is do_nothing, so the state is correctly unchanged)
```

**Real bug found and fixed while doing that:** the first `--grid2op-live` run printed no cards at
all. The Bevy side is non-blocking by design (that *is* the `bevy_rapier` pattern), so five instant
`app.update()` calls all raced past `try_recv()` while the subprocess was still spending ~60 s
importing grid2op and building the 503-bus environment. The fix belongs in the runner, not the
plugin: `main.rs` now waits (bounded by `--live-timeout-secs`) for each real observation before
rendering its card.

## Files

- `rust/mission-engine/` — the crate (fifth `rust/` workspace member):
  - `src/grid2op_bridge.rs` — `Grid2OpBridge` Resource + `Plugin`; fixture and live-subprocess sources.
  - `src/sysml_types.rs` — `sysml_v2_parser::parse()` on Lab 6's real model; AST → `SysmlPart`.
  - `src/grid_entities.rs` — one Entity per cluster Bus/Generator/Line, live rho each tick.
  - `src/cim_trace.rs` — **Phase 2**: `CimClassUri` Component + the `bus_lookup.json` join.
  - `src/objectives.rs` — `GridSecurityObjective` + `Satisfies` via a real scryer-prolog query.
  - `src/mission_fsm.rs` — TOML → Rhai guards → `MissionPhase` → Mermaid.
  - `src/optimizer.rs` — **Phase 3**: candidate ranking + `ufo-types` DARE/OODA wrap.
  - `src/card_feed.rs` — `bevy_ui` card feed (`--features interactive` only).
  - `tests/mission_end_to_end.rs`, `tests/cim_traceability.rs`, `tests/optimizer_ranking.rs`.
- `build_dataset.py` — grid2op dataset from `data/snemSA.m` (Lab 8 0a's three fixes + `bus_lookup.json`).
- `grid2op_bridge.py` — the live JSON-lines subprocess bridge + the line-ordering verification.
- `generate_fixture.py` — regenerates both committed fixtures from real grid2op runs.
- `mission_fsm.toml` — the mission state machine, as data.
- `fixtures/episode_observations.jsonl` — 5 real steps (trip + reclose), 19 branches, 15 buses.
- `fixtures/contingency_candidates.json` — the fixed contingency + 3 real what-if candidates.
- `fixtures/bus_lookup.json` — real `create_continuous_bus_index` output, 503 entries.
- `fixtures/mission_fsm.mmd` — the committed Mermaid rendering (`--emit-mermaid` regenerates it).
- `dataset_snemSA/` — gitignored; regenerated by `just lab9-dataset`.
