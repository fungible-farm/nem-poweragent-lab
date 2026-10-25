# 06 — Decisions and pilot checklist for your IT team

## Decisions only you can make

| # | Question | Why it matters |
|---|---|---|
| 1 | Which Windows 11 builds and editions does your fleet run, and do they meet the build floor in [02-prerequisites.md](02-prerequisites.md)? | below the floor, the sandbox backend is unavailable and tasks are denied |
| 2 | Are WDAC or AppLocker policies in force? What is the process to allow a new, signed binary? | the kit is unsigned; production needs your signing and allow-listing path |
| 3 | Is Podman (and so WSL2 or Hyper-V) permitted on managed workstations? If not, where may Linux helper services run, and how are they reached? | determines the helper-service design |
| 4 | **Who owns the capability policy, and where is it stored and signed?** (limitation L1) | this is the "independent policy authority"; today it is a plain file |
| 5 | Which backend failures should page a person, and which should deny silently? | audit and alerting design |
| 6 | Where should audit logs go (SIEM, file share, WORM storage)? How long are they kept? (L7) | tamper-evidence needs an external anchor |
| 7 | Is outbound network access from helpers ever acceptable? Through which proxy? (L6) | decides whether the unproven egress model is worth building |
| 8 | Which engineering applications (power-system simulators, licensed tools) are in scope, and may they run through a native adapter? | the golden path must not require commercial software |
| 9 | What is the code-signing certificate and release process? Intune or SCCM? (L4) | needed before any managed rollout |

## Pilot success criteria (suggested)

A pilot on **one or two non-production lab machines** succeeds if:

- [ ] `Verify-Pilot.ps1` prints `ALL CHECKS PASSED` on every pilot machine, or fails with a recorded, understood reason.
- [ ] The probe output (`poweragent-probe.exe`) is recorded for each build in your fleet sample.
- [ ] Your security team reviews [01-security-model.md](01-security-model.md) and the adversarial test list in
      [04-evidence.md](04-evidence.md) and either reproduces a sample of it or lists gaps.
- [ ] Your team attempts at least three escapes of its own devising (read a path outside the grant, write to a
      read-only folder, reach the network, run a second process) and records the outcomes.
- [ ] `Install-PowerAgent.ps1 -Action Preflight -ReportPath` is run on each pilot machine and the JSON reports are kept.
- [ ] A `-WhatIf` install is reviewed by whoever owns your software-deployment standards.
- [ ] A denied task and an authorised task each leave an audit report that verifies.
- [ ] The decisions above have named owners.

## What to send back

`verify-pilot.log`, the probe JSON, `winver` output, whether WDAC/AppLocker/Intune were present, and any escape
that succeeded. A successful escape is the most valuable result of the pilot.

## Stop conditions

Stop and do not proceed to any production-adjacent use if: an escape succeeds, the audit chain fails to verify
without explanation, or the sandbox backend is absent on a build your fleet needs.
