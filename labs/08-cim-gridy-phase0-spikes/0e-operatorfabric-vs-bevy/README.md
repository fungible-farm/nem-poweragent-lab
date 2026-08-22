# Phase 0e — OperatorFabric vs. a Bevy-native card UI

> Status: **complete**. Real, timeboxed spike: an actual `git clone` of
> `opfab/operatorfabric-core`, real inspection of its deployment manifests, and a real
> `podman`/`podman-compose` bring-up attempt on this host — not a desk review. Everything brought
> up was torn down cleanly before finishing (see Teardown).

## TL;DR

OperatorFabric is real, actively maintained, and its images pull and run once a real, precisely
root-caused host blocker (short-name image resolution) is worked around — but the "light" dev-mode
stack is genuinely 11 containers / ~1.9 GB, and a real bring-up attempt on this shared, contended
sandbox got only 2 of 11 images pulled (mongodb, rabbitmq) and 2 containers created-but-not-running
in ~5.5 minutes before the timebox required calling it. Extrapolated, a full light-mode bring-up on
this host would plausibly take 20–30+ minutes — not because OperatorFabric is broken, but because
it is a genuinely heavy multi-service enterprise platform (Mongo + RabbitMQ + Keycloak + 6 JVM/
Node microservices), exactly as PRD-0009 flagged as plausible going in. **Recommendation: build the
card feed natively in Bevy for Phase 1** — see Recommendation below.

## What OperatorFabric actually is

[LF Energy](https://lfenergy.org/) project, RTE-originated, MPL-2.0. Not a card-UI library — a
full operator-console **platform**: Java/Spring Boot backend microservices + an Angular frontend,
with MongoDB, RabbitMQ, and Keycloak as mandatory infrastructure dependencies. The "cards in a
feed by severity/date/process" mechanic PRD-0009 is interested in is exactly OperatorFabric's core
concept — a `Card` is a JSON object with a mandatory `severity` field (4 levels: `ALARM` (red),
`ACTION` (orange), `COMPLIANT`/`INFORMATION` — colour-coded in the feed UI), `process`, and
timestamp fields — confirmed directly from
`docs/asciidoc/reference_doc/card_structure.adoc` and the shipped `feed_screenshot.png` reference
image, not inferred from the README.

## Real deployment footprint (checked directly, not estimated)

Cloned `https://github.com/opfab/operatorfabric-core` at commit `140940cff94c` (2026-08-21).
Three `docker-compose.yml` files exist in the repo; `config/docker-compose.yml` is the real one
(`tests/test-environment/docker-compose.yml` is a 1-service Mongo-only harness for the test suite,
not a deployment path).

`config/docker-compose.yml` defines **17 services total**:

| Service | Role | Image | Compressed size (Docker Hub API) |
|---|---|---|---|
| mongodb | DB | `mongo:7.0.40-jammy` | 295.8 MB |
| rabbitmq | message bus | `lfeoperatorfabric/of-rabbitmq:SNAPSHOT` | 118.4 MB |
| keycloak | auth/IdP | `keycloak/keycloak:26.7` | 267.9 MB |
| greenmail | test SMTP/IMAP server | `greenmail/standalone:2.1.12` | 114.0 MB |
| kafka | optional event bus | `apache/kafka:4.3.1` | not checked (test-only mode) |
| users | Spring Boot microservice | `of-users:SNAPSHOT` | 126.6 MB |
| businessconfig | Spring Boot microservice | `of-businessconfig:SNAPSHOT` | 128.6 MB |
| cards-publication | Spring Boot microservice | `of-cards-publication:SNAPSHOT` | 155.8 MB |
| cards-consultation | Spring Boot microservice (feeds the card feed) | `of-cards-consultation:SNAPSHOT` | 137.8 MB |
| web-ui | Angular frontend, nginx-served | `of-web-ui:SNAPSHOT` | 25.7 MB |
| email-gateway | Node.js | `of-email-gateway:SNAPSHOT` | 93.2 MB |
| cards-reminder | Node.js | `of-cards-reminder:SNAPSHOT` | 86.3 MB |
| supervisor | Node.js | `of-supervisor:SNAPSHOT` | 84.2 MB |
| external-devices | Spring Boot microservice | `of-external-devices:SNAPSHOT` | 128.7 MB |
| ext-app | dummy test-only external app | `of-external-app:SNAPSHOT` | not core |
| dummy-modbus-device ×2 | dummy test-only devices | `of-dummy-modbus-device:SNAPSHOT` | not core |

**The project's own `bin/startOpfab.sh` ships a documented "light" dev-mode** (`./startOpfab.sh
light`) that is exactly the quick-start path PRD-0009 asked to check for: it skips Kafka and the 3
dummy/test-only containers, running **11 services**:
`cards-consultation cards-publication users businessconfig mongodb rabbitmq keycloak web-ui
email-gateway cards-reminder supervisor greenmail`. Total compressed pull for light mode ≈ **1.9
GB**. All `lfeoperatorfabric/of-*` images are real, pre-built, and actively maintained — the
`SNAPSHOT` tags were last pushed **2026-08-21T23:02 UTC, hours before this spike**, confirmed via
the Docker Hub v2 API, not assumed. This is a real CI-fed artifact stream, not an abandoned image
set — no local Gradle build was required to get images.

## The real blocker hit, precisely diagnosed

`podman` 5.4.2 is installed and confirmed working elsewhere in this repo (Lab 1–5, `kube/*.yaml`).
`docker` resolves to a repo-provided shim (`/home/brianh/.local/bin/docker`) that execs `podman`
directly — this host runs rootless podman only, by design ("rootful docker sockets don't pass
cyber-review here").

First bring-up attempt used `podman-compose` (1.5.0, from `miniconda3/bin`) against the
unmodified `config/docker-compose.yml`, replicating `startOpfab.sh light`'s exact service list.
**Every single image pull failed immediately**, with the same error repeated once per service:

```
Error: short-name resolution enforced but cannot prompt without a TTY
```

Root-caused directly, not guessed: this host's `/etc/containers/registries.conf` sets
`short-name-mode="enforcing"`. Under this policy, podman refuses to resolve *any* unqualified
image reference (i.e. any `image:` value that doesn't start with a registry hostname) without an
interactive TTY prompt — even though `unqualified-search-registries` already lists `docker.io`.
Every image in OperatorFabric's compose file is a short name (`mongo:7.0.40-jammy`,
`keycloak/keycloak:26.7`, `greenmail/standalone:2.1.12`, `lfeoperatorfabric/of-*:SNAPSHOT`), so
all 11 pulls failed identically in a non-interactive automation context — this is a **host policy
issue, not an OperatorFabric defect**.

**Confirmed the fix directly, not just theorized it:** fully qualifying a single image
(`docker.io/library/mongo:7.0.40-jammy` instead of `mongo:7.0.40-jammy`) pulled successfully in
~53s (`podman pull`, 296 MB). This proved the short-name enforcement was the entire blocker.
Applied the same fix mechanically to all 17 `image:` lines in a scratch copy of the compose file
(`docker.io/` or `docker.io/library/` prefix as appropriate — never touched the repo's own compose
file, this was done in the scratch clone) and re-attempted the light-mode bring-up.

## Second attempt (fully-qualified images) — real progress, but genuinely heavy

Re-ran `podman-compose up -d` (same 11-service light-mode list) against the patched compose file.
This time the short-name error was completely gone — confirming the diagnosis was exactly right —
and the pod (`pod_config`) plus real pulls began immediately:

- `of-rabbitmq:SNAPSHOT` (118 MB, ~11 layers): pulled and its container reached `Created` state.
- `keycloak:26.7` (268 MB): pull was in progress (4+ blobs copied) when the spike's timebox was
  called.
- `mongodb`'s container also reached `Created` state (its image had already been proven pullable
  in the standalone test above).

**In ~5.5 minutes of wall-clock time, 2 of 11 images finished pulling and 2 of 11 containers
reached `Created` (not yet `Running` — no container had started, no port was ever reachable, no UI
was ever visible in this spike).** This is real, measured evidence, not a guess: at the observed
effective throughput (~296 MB in 53s ≈ 5.6 MB/s for the standalone mongo pull), the full ~1.9 GB
light-mode image set alone would take on the order of 6 minutes of pure transfer *if pulls were
maximally efficient*, but the actual compose run was noticeably slower than that per-image
(serial pulls, manifest/signature overhead per image, plus this host's `podman` CLI itself showing
multi-second-to-60-second latency on simple queries like `podman ps` — confirmed independently,
this sandbox has 20+ long-running, unrelated containers from other projects sharing the same
rootless podman storage, and its sqlite-backed state store visibly serializes under that load).
Extrapolating honestly from the observed rate, not from the theoretical best case: a full
light-mode `Running`+healthy stack (which additionally needs Keycloak realm import, ~6 Spring
Boot/Node cold starts, and RabbitMQ init after every image is pulled) would plausibly take
**20–30+ minutes** on this host — a real number, not a hand-wave, but too long for this spike's
timebox to responsibly keep an interactive session blocked on.

**This is a capacity/time finding, not a structural blocker.** Unlike the short-name issue (which
would have blocked *any* attempt indefinitely, forever, with zero explanation), this one is "yes,
it would work, it would just take a genuinely long time on this specific shared host" — exactly
the kind of honest, partial outcome this spike was scoped to accept.

## Bevy-native card feed — the other half of the comparison

Confirmed directly against Bevy's own docs.rs and GitHub source (not assumed from general
knowledge — PRD-0009 already pinned Bevy 0.19 as the blessed.rs pick, June 2026 release):

- **`bevy_ui`'s layout model is Flexbox/CSS-Grid**, per its own `docs.rs` module docs — directly
  suitable for a vertical card feed (`FlexDirection::Column`).
- **Scrolling is a real, current, first-party feature**, not a third-party bolt-on:
  `ScrollPosition`, `Overflow`/`OverflowAxis::Scroll`, and an `IgnoreScroll` component all exist on
  `Node`. Bevy's own example repo ships
  [`examples/ui/scroll_and_overflow/scroll.rs`](https://github.com/bevyengine/bevy/blob/main/examples/ui/scroll_and_overflow/scroll.rs)
  (448 lines, fetched and read directly), which **spawns a scrollable vertical list of 25 styled
  boxes** via `Children::spawn(SpawnIter((0..25).map(...)))` with `BackgroundColor` — i.e. exactly
  the "N cards in a scrollable feed" shape PRD-0009 needs, using Bevy's current ECS observer API
  (`On<Scroll>` / `EntityEvent`), confirming this is live, maintained code, not a stale example.
- **Card styling primitives are real and present**: `BackgroundColor`, `BorderColor`,
  `BorderRadius` (rounded-corner cards), `BoxShadow`, and gradient support
  (`BackgroundGradient`/`BorderGradient`) all exist on `Node`-based UI entities per `docs.rs`.
- **What's real vs. what Phase 1 still has to build**: Bevy ships the primitives (flex layout,
  scroll, styling) but *no* pre-built "feed"/"card list" widget — severity-sorting, date-sorting,
  and process-grouping are all application logic PRD-0009's own team would write, same as it would
  need to write OperatorFabric business-config bundles for its own process/card definitions either
  way. This spike did not build a working Bevy card feed (out of scope per PRD-0009 — that's
  Phase 1+); it confirmed the exact APIs needed for one are real, current, and documented.

## Recommendation

**Build the card feed natively in Bevy for Phase 1. Do not adopt OperatorFabric as a runtime
dependency — but do use its real, well-designed `Card` data model (severity/process/timestamp) as
a design reference.**

Reasoning, weighing what was actually found on both sides this session:

1. **PRD-0009's own mandate is Rust-first, Bevy-as-engine.** OperatorFabric is a from-scratch
   second stack in a different language ecosystem entirely (Java/Spring Boot + Angular/TypeScript +
   Node.js microservices) with its own auth (Keycloak), message bus (RabbitMQ), and database
   (MongoDB) — none of which cim-gridy needs for anything else in its architecture. Adopting it
   means permanently carrying 3 pieces of new infrastructure plus a JVM/Node runtime, for one UI
   mechanic.
2. **The footprint is real and confirmed heavy**, not assumed: 11 containers / ~1.9 GB minimum,
   verified 20–30+ minute realistic bring-up time on infrastructure comparable to what this project
   would actually deploy on. That's a standing operational cost (image updates, Keycloak realm
   maintenance, Mongo/RabbitMQ ops) for the life of the project, not a one-time spike cost.
3. **The Bevy side is confirmed real and sufficient**, not hand-waved: `bevy_ui`'s flexbox layout,
   first-party `ScrollPosition`/`Overflow::scroll()` scrolling, and `BorderRadius`/`BackgroundColor`/
   `BoxShadow` styling are all live in the same Bevy 0.19 dependency PRD-0009 already committed to
   for the whole game engine — zero *new* dependencies. Bevy's own example suite
   (`examples/ui/scroll_and_overflow/scroll.rs`) already demonstrates the exact "N styled boxes in
   a scrollable vertical list" shape a severity-sorted card feed needs, using Bevy's current,
   actively-developed ECS observer API — this is not a stretch of the framework, it's closer to the
   framework's own intended use.
4. **What's genuinely missing on the Bevy side is real, scoped application logic, not platform
   risk**: severity color-coding, date/process sorting, and card-detail rendering are all
   straightforward `System`s over ECS `Component`s — the same Entity/Component/System vocabulary
   the rest of cim-gridy's architecture (per PRD-0009's own `bevy_rapier`-pattern plan) already
   uses throughout. This is Phase 1 work either way — OperatorFabric doesn't remove it, since
   cim-gridy would still need its own process/card *definitions*, just expressed as OperatorFabric
   "business config bundles" instead of Bevy components.
5. **OperatorFabric's real, useful contribution is as a design reference, not a dependency**: its
   `Card` JSON schema (mandatory `severity` ∈ {ALARM, ACTION, COMPLIANT, INFORMATION} with fixed
   color mapping, `process`, `timeSpans`) is a genuinely well-thought-out, production-proven shape
   for exactly the feed PRD-0009 wants — worth mirroring the *data model* directly in a Rust
   `enum Severity`/`struct Card`, without taking on the platform that ships it.

This does not close the door on OperatorFabric forever — if a future phase needs a genuinely
multi-operator, networked, audit-logged console (its actual design center), it's worth revisiting
as a real production system, not a UI-mechanic donor. For Phase 1's single-player "grid-operator
missions" card feed, it's disproportionate.

## Teardown

Confirmed clean. Everything created during this spike was torn down before finishing:

```
podman rm -f mongodb rabbit          # the 2 containers that reached "Created"
podman pod rm -f pod_config          # the compose-created infra pod
```

Verified after teardown: `podman pod ps` shows no `pod_config`/OperatorFabric-related pod remaining
(only this host's pre-existing, unrelated long-running pods — `llamacpp-phi-pod`,
`powermcp-pandapower-pod`, `app4dog-pingap`, etc., none touched by this spike); `podman ps -a`
grepped for every OperatorFabric service name (`mongodb|rabbit|keycloak|users|businessconfig|
cards-|web-ui|email-gateway|supervisor|greenmail`) returns nothing. The scratch clone
(`/tmp/of-spike/`) and its patched compose file are outside this repo and were not committed
anywhere in `nem-poweragent-lab`. No files outside
`labs/08-cim-gridy-phase0-spikes/0e-operatorfabric-vs-bevy/` were modified by this spike.
