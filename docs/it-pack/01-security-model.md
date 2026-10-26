# 01 — Security model

## Roles

| Role | Does | Must not be able to |
|---|---|---|
| **Agent / task author** | submits a *task profile*: the capabilities it requests | grant itself anything; supply a command; change policy |
| **Policy authority** | owns the *admin policy*: the capabilities that may ever be granted | — (see limitation L1: today the policy is a file the caller names) |
| **Host runner** (`poweragent`) | probes the host, decides, plans helpers, runs the work, audits | run anything not derived from an authorised decision |
| **OS / sandbox** (Windows MXC `processcontainer`, Podman) | enforces the boundary | be talked out of it by the task |

## The decision rule (ADR-002)

1. A request outside the policy is **denied**. A failed authorisation **never** triggers a fallback.
2. Untrusted (generated) code runs **only** inside the OS sandbox. If the sandbox is unavailable or cannot enforce
   a requirement, the task is **denied**, not run unprotected.
3. Anything not positively established is treated as unsupported. Network egress is *not yet supported*, so any
   request for it is denied.
4. Fallback backends (PowerShell JEA, native Win32, isolated VM) require an explicit administrator allow-list entry
   **and** a host probe that confirms they exist. In this kit only the MXC path and a native typed-operation
   adapter are implemented; JEA is deferred.

## Invariants and how each is met

| ID | Invariant | How | Test |
|---|---|---|---|
| SEC-001 | Authorisation is independent of the AI | decision is a pure function of profile, policy and host probe; no model input | policy tests (5) |
| SEC-002 | Helper services cannot add capabilities | resolver only accepts helpers already granted, with dependencies already granted | sidecar tests (10) |
| SEC-003 | A failed sandbox never silently falls back | denial reasons are distinct and audited; the runner has no second execution path | policy, e2e |
| SEC-004 | No arbitrary command execution through agent-facing APIs | request types are a closed set; unknown fields fail to parse; no script/command/exe-path field exists | fallback rules (6), exec (9) |
| SEC-005 | Helpers run least-privilege | `--network none`, read-only root, private tmpfs, all capabilities dropped, `no-new-privileges`, uid 65534, memory/CPU/PID limits — verified from inside the container; an existing container is reused or removed only if its labels and full configuration are read back as ours | podman (7 real, 5 args) |
| SEC-006 | Explicit authorisation for file and network access | read and write grants are separate; network is refused; the native adapter authorises the file's *real* location, resolved through an open handle, so a junction or symbolic link inside a granted folder cannot reach outside it | exec adversarial tests, native junction/symlink tests |
| SEC-007 | A compromised dashboard gives no host privilege | the dashboard is a read-only HTML file with no script and a strict content policy | audit tests |
| SEC-008 | Approvals, denials and results leave evidence | every decision and sidecar action is written to a hash-chained log *before* any viewer is told. If the log cannot be written, every helper already started is still stopped | audit (6), e2e, Podman audit-failure tests |
| SEC-009 | Updates need verifiable artifacts | helper images must be pinned by sha256 digest and already present (`--pull never`). **Signatures are not verified** (L5) | sidecar, podman args |
| SEC-010 | Failure defaults to denial | every error path in the runner is a denial or an error exit | e2e |
| SEC-011 | Agent content cannot change policy | policy is read from a separate file; a task cannot write to it (but see L1) | — |
| SEC-012 | Untrusted code requires OS containment | enforced by rule 2 above | policy, probe, e2e |

## What "enforced by the OS" means here

The sandbox restrictions in Gate 1 are applied by Windows when the process is created (AppContainer-style
isolation through the `processcontainer` backend of Microsoft's `mxc-sdk`). The worker cannot opt out. The tests
show this by running the same read/write/connect attempts **uncontained** (they succeed) and **contained** (they
fail with `Access is denied`, error 5, or `forbidden by its access permissions`, error 10013).

Microsoft's own MXC documentation says its sandbox profiles are not yet to be relied on as a security boundary.
Treat the results here as evidence of observed behaviour on tested builds, **not** as an audit. See L2.
