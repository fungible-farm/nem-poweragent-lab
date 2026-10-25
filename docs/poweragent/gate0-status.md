# Issue #54 — Gate 0 status and environment limits

Observed 2026-10-25 on the developer machine (read-only checks, non-admin shell).

## Environment

| Item | Observed |
|---|---|
| OS | Windows 11 Pro 25H2, build **26200.6899**, x64 |
| MXC `processcontainer` floor | Was 26200.6899 (25H2, below 26200.9278). After update: **26300.9711 (26H2) meets the 26300.9550 floor** — Gate 1 is no longer blocked on the OS build |
| Management | not domain-joined, not Intune-enrolled; no AppLocker rules; WDAC policy folder present |
| Tooling present | Rust (cargo), PowerShell 7.6.8, Git, Podman, WSL2, gh |
| Tooling missing | MSVC Build Tools / Windows SDK (needed for `windows-rs` and `mxc-sdk` on Windows) |
| Not checked (needs elevation) | Hyper-V and Windows Sandbox optional features, WinRM/JEA endpoint |
| Engineering apps | none of PowerFactory, PSS/E, PowerWorld installed |

## What is implemented (Linux-provable, per issue §7)

`rust/poweragent-policy` — pure logic, no OS calls:

- `TaskProfile` (`poweragent.dev/v1alpha1`) schema with `deny_unknown_fields`, and a validator.
  There is no "run command" capability variant.
- Policy intersection: any requested capability outside `AdminPolicy` denies the task.
- `decide()` — ADR-002 selector. Fails closed: authorization failure never falls back; untrusted
  code never runs without MXC; fallbacks (JEA, `windows-rs`, isolated VM) need an administrator
  allow-list entry **and** a probe report; empty/default probe denies.
- Table-driven tests: `cargo test -p poweragent-policy` (5 tests).

## Phase 2 scope (descoped 2026-10-26)

**Delivered and verified on the reference machine** — everything in #54 that can be built and proven without
external dependencies: the MXC-first runner (probe, decision, sidecar plan and launch, sandboxed worker, audit),
Gates 0 and 1 on the real Windows backend, Gate 2 logic plus a real Podman sidecar runtime with revocation,
Gate 3's native adapter, Gate 4's event/audit core with a static report, and a scriptable installer with a
34-check preflight (current-user scope: 26 cases; all-users scope: 9 elevated cases), plus the IT pilot kit
and documentation pack.

**Tracked as named blockers, not delivered** (each needs an input outside this repository):

| Blocker | Needs | Owner |
|---|---|---|
| Gate 5: signed install, Intune/SCCM assignment, standard-user operation, clean uninstall | a code-signing certificate; a tenant with a full Intune licence and an MDM-enrolled reference machine | tenant/PKI administrator |
| Gate 3, JEA half | a machine where a loopback WinRM login works (the development machine is Entra-joined and cannot); scripts are on branch `feat/54-jea-endpoint-deferred`, unverified. MXC covers the contained-execution path without it | security / platform |
| Gate 4, Electron dashboard | a decision; ADR-003 permits a browser or CLI view, which the static HTML report provides | architecture owner |
| Helper-image signature verification | an image-signing process (digest pinning is enforced today) | platform |
| Windows-adapter helpers; policy authority separate from the caller; network egress (proxy-only) | design decisions listed in the issue's open questions | architecture owner |

Issue #54 is therefore **not closed** by this work; its acceptance criteria in section 9 are met for the
runner, boundary, helpers, audit and installer, and not met for signed distribution on a managed workstation.

## Gate 0 result (real machine, 2026-10-25) — PASS

`rust/poweragent-probe` wraps the pinned `mxc-sdk =1.0.1` (`v1::available_backends`) and maps its facts to
the policy crate's `Probe`. On this host (build 26300.9711) it reports backend `processcontainer`, tier
`base-container`, capabilities captureDenials / filesystemDeniedPaths / filesystemEnumeratePaths
(full output: `evidence/gate0-probe-2026-10-25.json`). `just poweragent::gate0` asserts the fixture matrix:

| Case | Expected | Observed |
|---|---|---|
| authorized fs-only profile | run on `mxc`, exit 0 | pass |
| empty admin policy | deny `capability_not_authorized`, exit 3 | pass |
| network egress requested | deny `containment_unavailable` (unverified until Gate 1), exit 3 | pass |

Pass condition "unsupported containment requirements fail closed": met. Network enforcement is deliberately
not claimed by the probe; Gate 1 must prove it.

## Gate 1 result (real machine, 2026-10-25) — PASS

`rust/poweragent-exec` builds an MXC `processcontainer` request only from a `Decision::Run` on the MXC
backend, translating *granted* capabilities (fs_read -> read-only path, fs_write -> read-write path;
network egress and ingress default-deny; timeout from the profile). A closed `Job` set is the only way to
choose what the fixed worker does: there is no `execute(command)`. `just poweragent::gate1` runs
`tests/gate1.rs` against the real Windows backend and saves output to `evidence/gate1-adversarial-*.txt`.

| Test | Result (enforced by Windows, not by the worker) |
|---|---|
| worker reads read-only input, writes only the output dir, twice, same result | pass |
| write into the read-only input dir | denied, os error 5, file not created |
| read an ungranted directory | denied, os error 5, contents not leaked |
| write an ungranted directory | denied, os error 5, file not created |
| connect to host loopback listener | denied, os error 10013 |
| connect to 1.1.1.1:443 | denied, os error 10013 |
| 60 s sleep with 3 s timeout | `TimedOut` |
| a net_egress grant, or a Deny decision | no request is built |

Positive controls: the same read, write and loopback connect succeed when the worker runs uncontained,
so the denials come from the container. Limits: unprivileged shell on one machine (build 26300.9711,
not domain-joined or Intune-managed); `mxc-sdk` docs call the profiles not yet a security boundary.
Allowing a specific egress host (proxy-only model) is not implemented or claimed.

## Gates 2–4 and integration

| Gate | Implemented and tested | Not proven |
|---|---|---|
| 2 Dynamic sidecars | `poweragent-sidecar`: registry, resolver (authorised MXC decision only, dependencies first, no capability escalation), reference-counted idempotent reconciler, revocation. 9 tests; two-solver NEM study, Windows adapter, disable-blocks-activation | Windows-adapter sidecars and image signature verification (digest pinning is enforced, signatures are not checked) |
| 3 Fallback | Rules (6 tests) plus the **native `windows-rs` adapter** (`poweragent-fallback::native`, 6 tests on the real OS: authorised `GetFileVersionInfo` returns a real version; path outside the grant, wrong-backend decision, deny decision and missing file are refused). No process is spawned and no executable path is accepted | **JEA**: compartmentalised on branch `feat/54-jea-endpoint-deferred`, unverified (Entra account cannot authenticate to a loopback WinRM listener). MXC is the golden path and does not need it. The interactive-session COM case is untested |
| 4 Logging/dashboard | `poweragent-audit`: events, hash-chained log written before subscribers are told; static script-free HTML report with CSP, escaping, and a loud banner for a broken chain. Audit and result identical with the dashboard on, off and dead (unit and end-to-end tests) | **Electron dashboard** not built (ADR-003 allows a browser or CLI view; the HTML report and CLI stand in) |
| Sidecar runtime | `poweragent-podman`: starts/stops administrator-registered sidecars with Podman. Typed argv, no shell, no caller command; image must be digest-pinned and already present (`--pull never`); `--network none`, read-only root, private tmpfs, `--cap-drop ALL`, `no-new-privileges`, user 65534, memory/CPU/PID limits; per-task container names for state isolation. 5 argument tests (Linux sandbox) + a real lifecycle test that checks, from inside the container, empty capability sets, uid 65534, read-only root, writable tmpfs. 3 end-to-end tests: sidecars are running while the MXC worker runs and gone after; a failing sidecar start tears down the ones already up and runs nothing; a denied task starts no container | Resource limits are Podman's, enforced inside the Podman VM; a sidecar that needs network gets none (egress is unsupported) |
| Integration | `poweragent run` / `poweragent report`: probe -> decide -> sidecar plan (and launch with `--podman`) -> MXC-contained worker -> audit. 5 end-to-end tests (no-launch runtime audits sidecars as planned only, never as started) on the real backend (happy path with only the required sidecars, unauthorised, network, missing dependency, dashboard on/off). `just poweragent::demo` reproduces `evidence/phase2-run/` | The worker is a fixed deterministic job (sum); real solver workloads are not wired |

`just poweragent::test` runs the pure-logic crates in bubblewrap (read-only filesystem, no network); `gate0`, `gate1`,
`gate2-4`, `native` and `e2e` run on the real Windows host. `just poweragent::chain` runs them all.

## Not done (remaining for #54)

- **Gate 5 prerequisites** (checked 2026-10-25, generic): Gate 5 needs a tenant with a full Intune (device
  management) licence and a machine enrolled in it. The development machine is Entra-joined but not MDM-enrolled,
  and the development tenant did not have the device-management service available, so Gate 5 cannot be run on it
  as things stand. A code-signing certificate is also required.
- **Gate 5** (enterprise distribution): signed package, Intune/SCCM assignment, silent install/upgrade/rollback, standard-user
  operation, clean uninstall. Needs a code-signing certificate and an Intune/SCCM tenant on a managed reference machine.
  Not started and not provable on this unmanaged machine.
- **JEA** (Gate 3 JEA half) and the **Electron dashboard** (Gate 4 UI): deferred, see above.
- Windows-adapter sidecars and image signature verification. Revoking a *running* helper is done by `poweragent revoke` (on demand, tested on real Podman); no daemon watches the policy for changes.
- **Network egress** (proxy-only model) is deliberately unsupported; every egress grant is refused.
- Open decisions for the owner: policy-authority ownership and storage, Podman on managed workstations, paging vs silent denial.
- Environment: one unmanaged developer machine, unprivileged shell. The MXC README says its profiles are not yet security boundaries.

## Running the chain (from WSL)

```bash
just poweragent::chain   # os-floor, toolchain, fetch, test (bubblewrap, no network), mxc-pin, gate0, gate1, gate2-4, native, e2e, sidecars
```

Each step stops the chain with a reason on failure. The `test` step runs inside bubblewrap (the
MXC Linux backend primitive) with a read-only filesystem and no network; it is Linux evidence,
not proof of Windows enforcement. `gate0` and `gate1` run the Windows build and tests through WSL interop (`cargo.exe`) because only the
Windows backend can show processcontainer enforcement. Using MXC itself as the build container is not done.
