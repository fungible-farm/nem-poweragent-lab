# 0006 — SysML v2 digital-thread MVP: MBSE tooling evaluation (Lab 6)

- **Status:** implemented (both tracks, first pass — see Open questions for what's deliberately
  left for a later phase)
- **Depends on:** none directly; reuses real components from Labs 1, 3, 4, 5 as Track A seed data
  and a real `data/snemSA.m` subset (the same CSIRO case Lab 1 loads) as Track B seed data
- **Touches:** new `labs/06-sysml-digital-thread/`, `pyproject.toml`/`uv.lock` (`linkml`,
  `linkml-runtime`, `cyclonedx-python-lib`), `Justfile` (`check-lab6`, `lab6`, `lab6-demo`),
  `.gitignore`, `AGENTS.md`, `docs/VISION.md`, `docs/DEFINITION_OF_DONE.md`, root `README.md`,
  `docs/PSCADOSSE.md` (license map), `docs/prd/0004-plexos-direct-mcp-and-strangler-fig.md`
  (renumber note — its own `labs/06-plexos...` reference becomes `labs/07` whenever that work
  starts, since this PRD claims Lab 6 first)

## Problem

This is a **greenfield capability evaluation**, not a feature build: is MBSE/SysML v2 (a formal
systems-modelling notation and its current, 2025-era language version) viable tooling for two
different, emerging jobs in this repo's world — **(1) modelling AI agent/MCP/data workflows**, the
software side of what this repo already runs, and **(2) grid network system design/simulation**,
the power-systems side every other lab studies? The sprint's own framing: "buying knowledge," with
breadth (as many real options de-risked as feasible) weighted over picking the cheapest path on day
one. `linkml.io` was named as one candidate schema technology, explicitly "not essential — just
under consideration," not a hard requirement.

## What was checked this session, not assumed

**Tool landscape, researched before any code was written:**

- **SysML v2 Pilot/Reference Implementation**
  (`Systems-Modeling/SysML-v2-Pilot-Implementation`, EPL-2.0, normative, Java ≥21) is real, and
  there's prior container art (`gorenje/sysmlv2-jupyter-docker`), directly analogous to how this
  repo already handles VILLASnode in Lab 5 (a real OCI image, run via `podman`, not reimplemented).
- **Syside** (Sensmetry) — the free tier is a VS Code *editor* extension only; the scriptable
  headless CLI/Python API is part of the paid Modeler tier. Not confirmed usable for a non-commercial
  evaluation without a purchase; not pursued further this sprint.
- **`DaanV2/isometric-diagrams`** is real (a person's GitHub project, MIT-licensed): a small Svelte
  5/SvelteKit app, YAML spec → isometric SVG, rendered in-browser only.
- **`isoflow`** (`markmanx/isoflow`) is effectively superseded by **FossFLOW**
  (`stan-smith/fossflow`) — React-based, also browser-only.

**Real-tool attempts, both genuinely tried and timeboxed, both written up in full in
[`labs/06-sysml-digital-thread/README.md`](../../labs/06-sysml-digital-thread/README.md)'s
"Design notes" (not repeated in full here):**

- **Syntax gate**: the official Pilot Implementation's `.github/workflows/build.yml` proved a real
  headless Maven/Tycho build path exists (JDK 21, no IDE). A `ghcr.io/graalvm/graalvm-community:21`
  podman container removed this host's Java-17 blocker cleanly. Scoping the Tycho reactor to
  `org.omg.sysml.interactive` got real progress (pom parsing, plugin resolution, first module build
  all clean) before failing on a specific, confirmed third-party defect: an `UnsatisfiedLinkError` in
  `com.sensmetry:sysand-maven-plugin:0.1.0-rc.1`'s native JNI loader — not an architecture mismatch,
  not an environment misconfiguration on this repo's side. Fallback: a named structural stand-in
  (`validate_sysml.py`) checking exactly the grammar subset this lab's generator emits, with real
  line/column error reporting.
- **Diagram renderer**: `DaanV2/isometric-diagrams` was driven headlessly via real Playwright
  (Node ≥22 via `nvm`, `npx playwright install chromium`) against this lab's real Track A data —
  **confirmed correct, 7/7 nodes rendered with right labels/icons** via its `#d=<base64url-yaml>`
  permalink mechanism. Confirmed disproportionate to wire into this Python-only repo's pipeline (a
  second-language toolchain plus a ~290MB headless-Chromium download for what a ~100-line pure-Python
  isometric-projection writer already satisfies deterministically). Fallback:
  `render_diagram.py`, whose iso-IR JSON schema matches DaanV2's real `DiagramSpec` field names 1:1
  on purpose, so the real tool stays usable by hand at any time.

## Goals

1. Prove or disprove, with a real generated pipeline (not a mockup), that one SysML v2 schema/
   generator/validator/renderer approach generalizes across both named business cases (AI workflow
   modelling and grid topology modelling) — Track A and Track B share the exact same code.
2. Attempt the real, normative tools first for both the syntax gate and the diagram render, timeboxed,
   and treat the findings — whichever way each lands — as a first-class deliverable, not a discarded
   exploration.
3. Ground every seed instance in real, already-committed data (this repo's own agents/MCP
   servers/data sources for Track A; a real `data/snemSA.m` subset for Track B) rather than
   fabricated examples.
4. Demonstrate the full "one schema edit → one command → regenerated artifacts" loop end to end,
   under a 2-minute walkthrough budget.

## Non-goals

- **Not building Port/Flow/connection-usage SysML v2 syntax.** Part/containment only — "straight
  boxes are enough" for this MVP; Track B's `Line.fromBus`/`toBus` are plain string attributes, named
  explicitly as the exact substitution a future phase would replace with real reference/connection
  syntax.
- **Not a semantic/type-checking gate** (`mercurio-sysml` or equivalent) — `validate_sysml.py` is a
  structural syntax check only, named as such.
- **Not a git-hook/CI-integrated modelling workflow** (`Rocky` or equivalent) — out of scope for this
  evaluation sprint.
- **Not live k8s cluster enumeration** — `build_k8s_fixture.py` reshapes this repo's own committed,
  already-proven `kube/*.yaml` manifests, not a live `kubectl` call.
- **Not SBOM drift/vulnerability detection** — `generate_sbom.py` emits `version: "unknown"` for
  every component; no scanner integration.
- **Not SHACL or any other RDF-based validation layer** for the LinkML schemas.
- **Not a Track-B SBOM equivalent** — a CycloneDX bill of materials doesn't map onto physical grid
  assets; what that third artifact should be (an equipment register? NER asset schedule shape?) is
  named as an open question below, not invented under time pressure.
- **Not settling LinkML as a permanent dependency** — explicitly provisional, see Open questions.

## Phasing

- **Phase 1 (this sprint, complete)** — both tracks' schemas + instance data, the generator/
  validator/translator/renderer pipeline, Track A's SBOM, the chained demo script, and the two
  real-tool-evaluation write-ups above.
- **Phase 2 (not started)** — revisit the syntax gate once `sysand-maven-plugin` ships a fixed
  release past `0.1.0-rc.1`, or a newer/maintained community SysML v2 API container appears.
- **Phase 3 (not started)** — revisit the diagram renderer as a dedicated follow-up (a Node/Svelte +
  Playwright toolchain addition to this repo, if the business case justifies the added
  infrastructure) rather than folding it into this sprint.
- **Phase 4 (not started, contingent on Phase 1's findings holding up)** — Track B's own
  third-artifact question (equipment register / NER asset schedule shape).

## Acceptance criteria for this PRD

- [x] `uv run python -m pytest labs/06-sysml-digital-thread/test_lab6.py -v` passes, both tracks,
      on a clean checkout.
- [x] `./scripts/demo_lab6.sh` (and `just lab6-demo`) runs end to end, both tracks, under 2 minutes
      (measured: well under a second on this host).
- [x] Every Track A seed instance's `source` field traces to a real, already-committed file in this
      repo; every Track B seed instance traces to a real row/table entry in `data/snemSA.m`.
- [x] Both real-tool attempts (syntax gate, diagram renderer) are genuinely attempted, not assumed
      to fail, and precisely root-caused (not "too hard") wherever they didn't land — written up in
      the lab's own README.
- [x] Zero secrets in `fixtures/k8s_snapshot.json` (source manifests and the generated fixture both
      checked).
- [x] `podman build`/`podman run` parity against the Lab 6 `Containerfile`, matching every other
      lab's container-parity bar.
- [x] New dependencies' licenses (`linkml`, `linkml-runtime`, `cyclonedx-python-lib`, and their new
      transitive packages) recorded in `docs/PSCADOSSE.md`.

## Open questions

- **Does LinkML earn its keep, or would plain Pydantic/dataclasses serve this repo just as well for
  Track A/B's schema needs?** Left genuinely open — LinkML's own tooling (`linkml validate`, its
  broader ecosystem) wasn't stress-tested past this MVP's two small schemas.
- **Is Syside's paid Modeler tier worth a trial license for a future phase**, given the free tier is
  editor-only and this sprint didn't purchase access to check its scriptable API directly?
- **What is Track B's own third downstream artifact** (an equipment register? a NER asset schedule
  shape?), now that SBOM is confirmed Track-A-only — not decided in this PRD, a Phase 4 question.
- **Would a newer/maintained SysML v2 API container (replacing the stale `2023-02`-pinned
  `gorenje/sysmlv2-jupyter-docker`) or a fixed `sysand-maven-plugin` release change the syntax-gate
  finding?** Worth re-checking periodically, not attempted again this sprint.
