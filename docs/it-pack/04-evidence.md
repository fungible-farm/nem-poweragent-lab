# 04 — Evidence

Everything below was run on one machine: **Windows 11 Pro build 26300.9711, x64, Entra-joined, not device-managed,
non-elevated shell, Podman 6.1.4.** 63 automated tests, a 26-case installer suite, plus the saved run outputs. "Real OS" means the test
exercises the actual Windows or Podman behaviour, not a simulation.

| Suite | Tests | Runs on | What it shows |
|---|---|---|---|
| Policy (`poweragent-policy`) | 5 | sandboxed Linux | request ∩ policy; untrusted code never runs unprotected; fallbacks need admin allow-list and a probe |
| Probe (`poweragent-probe`) | 4 | Windows | maps SDK-reported backends to the decision input; network requirement reported unsupported |
| **Sandbox adversarial** (`poweragent-exec`) | 9 | **real OS** | see below |
| Sidecar logic (`poweragent-sidecar`) | 10 | Linux + Windows | dependency order, no capability escalation, ref-counted stop, revocation, digest-pin rule |
| Audit (`poweragent-audit`) | 6 | Linux + Windows | hash chain, tamper and deletion detected, dashboard on/off/dead gives identical audit, HTML is script-free and escaped |
| Fallback rules (`poweragent-fallback`) | 6 | Linux + Windows | typed operations only; arbitrary PowerShell / exe path cannot be expressed; no fallback after failed authorisation |
| **Native adapter** | 6 | **real OS** | a typed Win32 call (file version) runs only behind authorisation; out-of-grant paths refused before any call |
| Podman args | 5 | Linux | exact `podman run` flags; nothing that widens access can appear |
| **Podman lifecycle** | 2 | **real Podman** | start, idempotent start, stop; inside the container: empty capability sets, uid 65534, read-only root, writable tmpfs |
| **End to end** | 5 | **real OS** | probe → decide → plan → sandboxed worker → audit; denials stop before anything runs |
| **End to end with Podman** | 5 | **real OS + Podman** | helpers are running *while* the sandboxed worker runs and gone after; a failed helper start tears down the others and runs nothing; a denied task starts no container; **revoking policy stops running helpers it no longer allows (and audits it) while leaving allowed and unrelated containers alone** |
| **Installer** (`Test-Installer.ps1`) | 26 | real OS (current-user scope) | preflight, strict config, tamper, WhatIf, install, drift, upgrade, rollback incl. injected failures, uninstall with exact PATH restoration |

## Sandbox adversarial results (`evidence/gate1-adversarial-*.txt`)

| Attempt inside the sandbox | Result |
|---|---|
| Worker reads read-only input, writes only to the one output folder (run twice) | succeeds, same result |
| Write into the read-only input folder | **denied**, error 5, file not created |
| Read a folder that was not granted | **denied**, error 5, contents not leaked |
| Write a folder that was not granted | **denied**, error 5, file not created |
| Connect to a listener on the host's loopback | **denied**, error 10013 |
| Connect to 1.1.1.1:443 | **denied**, error 10013 |
| Sleep 60 s with a 3 s timeout | terminated (`TimedOut`) |
| A network grant, or a Deny decision, reaches the sandbox builder | no request is built |

**Controls:** the same read, write and loopback connect **succeed** when the worker runs outside the sandbox, so the
denials are the sandbox's doing and not artefacts of the test.

## Reproduce

Kit (no tools needed): `.\Verify-Pilot.ps1`.

From source (WSL + Windows toolchain): `just poweragent::chain`, which runs the OS-build check, toolchain check,
sandboxed logic tests, probe matrix, sandbox adversarial tests, logic suites, native adapter test, end-to-end
tests and the Podman tests, and exits non-zero on any failure. `just poweragent::demo` regenerates
`evidence/phase2-run/` (an authorised run, a denied run, and the HTML audit report) with a reproducible audit hash.

Saved outputs in `evidence\`: `gate0-probe-*.json`, `gate1-adversarial-*.txt`, `phase2-run\` (profile, policy,
audit log, report, output).
