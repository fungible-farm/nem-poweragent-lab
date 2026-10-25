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

## Not done (remaining for #54)

- Gates 2–5: see the sections below as they are completed. Gate 3 needs a JEA endpoint (elevation); Gate 5 needs signing and an Intune/SCCM tenant.
- Open decisions: policy-authority ownership, Podman on managed workstations, paging vs silent denial.

## Running the chain (from WSL)

```bash
just poweragent::chain   # os-floor, toolchain, fetch, test (bubblewrap, no network), mxc-pin
```

Each step stops the chain with a reason on failure. The `test` step runs inside bubblewrap (the
MXC Linux backend primitive) with a read-only filesystem and no network; it is Linux evidence,
not proof of Windows enforcement. Using the MXC SDK itself for the build container is pending the
probe crate and the Windows toolchain.
