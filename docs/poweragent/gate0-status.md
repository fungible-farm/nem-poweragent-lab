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

## Not done (remaining for #54)

- Gates 1–5: need the MSVC toolchain, a JEA endpoint, signed packaging and
  an Intune/SCCM tenant. Gates 1, 3 and 5 are only authoritative on the real machine.
- Open decisions: policy-authority ownership, Podman on managed workstations, paging vs silent denial.

## Running the chain (from WSL)

```bash
just poweragent::chain   # os-floor, toolchain, fetch, test (bubblewrap, no network), mxc-pin
```

Each step stops the chain with a reason on failure. The `test` step runs inside bubblewrap (the
MXC Linux backend primitive) with a read-only filesystem and no network; it is Linux evidence,
not proof of Windows enforcement. Using the MXC SDK itself for the build container is pending the
probe crate and the Windows toolchain.
