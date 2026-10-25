# PowerAgent pilot kit — for IT teams

**Status: pilot / lab evaluation. Not production. Unsigned.** Read [05-limitations.md](05-limitations.md) before anything else.

## What this is

Engineering agents (software that plans and runs analysis for power-system engineers) need to run code on
Windows workstations. PowerAgent is a small host-side component that lets that happen with **explicit,
verifiable OS-level boundaries**:

> The agent *requests* capabilities. An independent policy decides which it may have.
> The operating system *enforces* the result.

Concretely it:

- accepts a declarative **task profile** (which folders to read, which to write, which helper services are needed);
- intersects it with an administrator **policy**, and **denies anything not explicitly allowed**;
- runs the work inside Microsoft's **MXC** `processcontainer` sandbox (a Windows 11 feature), with network off
  and a timeout, so a misbehaving task cannot read or write outside what was granted;
- starts only the required **helper services** (Podman containers), each locked down, and stops them afterwards;
- writes a **tamper-evident audit log** and renders it as a plain HTML report.

There is **no way to ask it to run an arbitrary command or PowerShell script**; the request language cannot express one.

## What is proven, in one table

| Claim | Evidence | Where |
|---|---|---|
| The sandbox backend is present and reported on a real Windows 11 build | probe on build 26300.9711 | `evidence/gate0-probe-*.json` |
| Sandbox denies reads/writes outside the grant, denies network, enforces a timeout | 9 adversarial tests on the real OS, with uncontained controls that succeed | `evidence/gate1-adversarial-*.txt` |
| Unauthorised or unsupported requests are denied before anything runs | policy, probe and end-to-end tests | [04-evidence.md](04-evidence.md) |
| Helper containers run with no network, no capabilities, read-only root, non-root user | checked from *inside* the container | [04-evidence.md](04-evidence.md) |
| Audit is identical with a dashboard attached, absent, or dead; edits to the log are detected | unit and end-to-end tests | [04-evidence.md](04-evidence.md) |

Not proven, and said plainly in [05-limitations.md](05-limitations.md): production hardening, managed-fleet
behaviour (Intune/WDAC/AppLocker), signed distribution, and a separated policy authority.

## Try it in 10 minutes (no admin rights, installs nothing)

1. Unzip the kit anywhere (a path without spaces is simplest).
2. Check the zip against the `.sha256` file that came with it (`Get-FileHash <zip>`).
3. In PowerShell, from the kit folder: `.\Verify-Pilot.ps1`
4. Expect `ALL CHECKS PASSED`. The script writes `verify-pilot.log` and a `work\report.html` audit report.

If a check fails, send us `verify-pilot.log` and the output of `winver`. See [03-pilot-runbook.md](03-pilot-runbook.md).

## Contents

| Path | What |
|---|---|
| `bin\` | `poweragent.exe` (runner and report), `poweragent-worker.exe` (fixed demo workload), `poweragent-probe.exe` (backend probe) |
| `Verify-Pilot.ps1` | self-check described above |
| `SHA256SUMS` | hashes of every file in the kit |
| `fixtures\` | example profiles and policies |
| `evidence\` | saved probe, adversarial-test and end-to-end run output |
| `docs\` | this pack; `DEPENDENCIES.md` lists every third-party library and its licence; `gate-status.md` is the engineering status |

## Documents

1. [01-security-model.md](01-security-model.md) — the invariants and how each is enforced and tested
2. [02-prerequisites.md](02-prerequisites.md) — Windows builds, hardware, rights, what it does *not* need
3. [03-pilot-runbook.md](03-pilot-runbook.md) — run, write your own profile/policy, read the audit, remove it
4. [04-evidence.md](04-evidence.md) — what each test proves and how to reproduce it
5. [05-limitations.md](05-limitations.md) — what this is not
6. [06-it-checklist.md](06-it-checklist.md) — decisions and pilot success criteria for your team

Licence: MIT OR Apache-2.0. Third-party licences are in `docs\DEPENDENCIES.md`.
