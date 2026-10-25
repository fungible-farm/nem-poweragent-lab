# 07 — Installer

`Install-PowerAgent.ps1` (PowerShell 7) is the supported way to put the kit on a machine. It is **not** an MSI and
not yet signed (see limitations L4, L11); it is a scriptable installer you can drive from your own deployment
tooling, and it makes every dependency and every change explicit.

## Principles

- **Preflight first, always.** Every action begins with the full check list below. A failed *required* check stops
  the action before anything is changed. Warnings are shown; `failOnWarning` makes them fatal.
- **Nothing hidden.** `-WhatIf` prints every step and changes nothing. `-Action ListChecks` prints the catalogue.
  `-ReportPath` writes a JSON report (checks, every load-time DLL and whether it resolved, steps, result).
- **Strict config.** Unknown keys are rejected (exit 64), so a typo cannot silently weaken a setting.
- **Reversible.** Upgrades keep the previous version and roll back automatically if install or post-install
  verification fails. `Rollback` swaps versions by hand. `Uninstall` removes exactly what the manifest lists.
- **Safe defaults.** The installed policy file allows **nothing** until an administrator edits it.

## Quick start

```powershell
# 1. See exactly what would be checked, then check this machine (read-only; writes a JSON report)
.\Install-PowerAgent.ps1 -Action ListChecks
.\Install-PowerAgent.ps1 -Action Preflight -ReportPath preflight.json

# 2. Show every step without doing any of them
.\Install-PowerAgent.ps1 -Action Install -WhatIf

# 3. Install for the current user (no admin rights), driven by a config file
.\Install-PowerAgent.ps1 -Action Install -ConfigPath .\install.config.json

# 4. Machine-wide (elevated PowerShell)
.\Install-PowerAgent.ps1 -Action Install -Scope AllUsers

# Later
.\Install-PowerAgent.ps1 -Action Status                    # health + drift check against the manifest
.\Install-PowerAgent.ps1 -Action Upgrade                   # run from a newer kit
.\Install-PowerAgent.ps1 -Action Rollback                  # swap with the previous version
.\Install-PowerAgent.ps1 -Action Uninstall [-PurgeData]
```

## Actions

| Action | Does |
|---|---|
| `Preflight` | runs all checks; changes nothing; exit 0 / 10 / 11 |
| `Install` / `Upgrade` | preflight, stage, keep previous, activate, create data dirs, PATH, uninstall entry, verify; rolls back on failure |
| `Rollback` | swaps the installed and previous versions (run again to swap back) |
| `Uninstall` | removes files, PATH entry and uninstall entry; **keeps policy and audit data** unless `-PurgeData` |
| `Status` | verifies installed files against the manifest; exit 12 on drift |
| `ListChecks` | prints the catalogue of checks |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | `Status`: not installed |
| 10 | preflight: a **required** check failed (nothing changed) |
| 11 | preflight: warnings and `failOnWarning` is set (nothing changed) |
| 12 | `Status`: installed files differ from the manifest |
| 20 | install failed and was **rolled back** |
| 30 | post-install verification failed and was **rolled back** |
| 40 | refused: PowerAgent is running from the install directory, or there is nothing to roll back |
| 64 | bad arguments or config |

## Configuration (`install.config.json`)

Every key is optional; parameters on the command line override the file. Paths may use `%ENVIRONMENT%` variables.

| Key | Default | Meaning |
|---|---|---|
| `scope` | `CurrentUser` | `CurrentUser` (no admin) or `AllUsers` (elevated; Program Files / ProgramData; machine PATH; HKLM) |
| `installDir` | per scope | `%LOCALAPPDATA%\Programs\PowerAgent` or `%ProgramFiles%\PowerAgent` |
| `dataDir` | per scope | policy, registry, audit, work, logs: `%LOCALAPPDATA%\PowerAgent` or `%ProgramData%\PowerAgent` |
| `addToPath` | `true` | add `<installDir>\bin` to the user (or machine) PATH |
| `registerUninstallEntry` | `true` | register "PowerAgent (pilot)" in Apps & features / for Intune detection rules |
| `requireSignedBinaries` | `false` | make an invalid Authenticode signature a required failure |
| `failOnWarning` | `false` | treat warnings as exit 11 |
| `minFreeDiskMB` | `200` | free space needed on the install drive |
| `podman.require` | `false` | make Podman and its engine required checks |
| `podman.bin` | `podman` | Podman executable |
| `registryFile` | `null` | sidecar registry JSON; preflight confirms each image is digest-pinned and present locally |
| `verify.expectBackend` | `processcontainer` | the MXC backend that must be reported available, before and after install |

Command-line equivalents: `-Scope -InstallDir -DataDir -NoPath -NoUninstallEntry -FailOnWarning -Force -PurgeData -ReportPath -Quiet -WhatIf`.

## What gets installed, and where

| Item | CurrentUser | AllUsers |
|---|---|---|
| Binaries, docs, fixtures, manifest | `%LOCALAPPDATA%\Programs\PowerAgent` | `%ProgramFiles%\PowerAgent` |
| `policy\` (starts **deny-all**), `registry\` | `%LOCALAPPDATA%\PowerAgent\policy` | `%ProgramData%\PowerAgent\policy` — **ACL: administrators write, everyone else read-only** |
| `audit\`, `work\`, `logs\` | under `%LOCALAPPDATA%\PowerAgent` | under `%ProgramData%\PowerAgent`, users may write |
| PATH | user | machine |
| Uninstall entry | `HKCU` | `HKLM` |

No services, scheduled tasks, drivers, firewall rules or WinRM changes are made. Upgrades never overwrite an
existing `policy.json` or `registry.json`.

## Dependency checks (the full catalogue)

| Id | Category | Required | Check |
|---|---|---|---|
| PLAT-01 | Platform | yes | Operating system is Windows |
| PLAT-02 | Platform | yes | 64-bit process on x64 hardware (ARM64 is untested) |
| PLAT-03 | Platform | yes | Windows build meets the MXC processcontainer floor (data\mxc-os-floor.txt) |
| PLAT-04 | Platform | no | Windows edition and virtual-machine status (informational) |
| RIGHT-01 | Rights | yes | Elevation matches the requested scope (AllUsers needs administrator) |
| RIGHT-02 | Rights | yes | Install directory location is writable |
| RIGHT-03 | Rights | yes | Data directory location is writable |
| RIGHT-04 | Rights | yes | Free disk space on the install drive |
| KIT-01 | Kit integrity | yes | SHA256SUMS present |
| KIT-02 | Kit integrity | yes | Every kit file matches SHA256SUMS |
| KIT-03 | Kit integrity | yes | Required kit files present (binaries, data) |
| KIT-04 | Kit integrity | no | No Mark-of-the-Web (downloaded-file block) on kit files |
| KIT-05 | Kit integrity | no | Authenticode signatures (required only if requireSignedBinaries) |
| DEP-01 | Dependencies | yes | Every load-time DLL of poweragent.exe resolves on this machine |
| DEP-02 | Dependencies | yes | Every load-time DLL of poweragent-worker.exe resolves on this machine |
| DEP-03 | Dependencies | yes | Every load-time DLL of poweragent-probe.exe resolves on this machine |
| DEP-04 | Dependencies | no | No Visual C++ Redistributable needed (static C runtime) |
| BACK-01 | Sandbox backend | yes | The probe executes on this machine |
| BACK-02 | Sandbox backend | yes | The expected MXC backend is reported available |
| BACK-03 | Sandbox backend | no | Backend tier (informational) |
| BACK-04 | Sandbox backend | yes | Fail-closed: a network request is denied (self-test) |
| SEC-01 | Security posture | no | Code-integrity (WDAC) policies present (informational) |
| SEC-02 | Security posture | no | AppLocker policy present (informational) |
| SEC-03 | Security posture | no | Microsoft Defender real-time protection (informational) |
| SEC-04 | Security posture | no | PowerShell execution policy (informational) |
| MGMT-01 | Management | no | Entra / domain join state (informational) |
| MGMT-02 | Management | no | MDM (Intune) enrollment (informational) |
| OPT-01 | Optional: Podman | no | Podman installed (required only if podman.require) |
| OPT-02 | Optional: Podman | no | Podman engine reachable (required only if podman.require) |
| OPT-03 | Optional: Podman | no | Every digest-pinned image in registryFile is present locally |
| INST-01 | Existing install | no | Existing installation and version (informational) |
| INST-02 | Existing install | yes | No downgrade without -Force |
| INST-03 | Existing install | no | No other poweragent.exe earlier on PATH |
| INST-04 | Existing install | yes | No PowerAgent process running from the install directory |

`DEP-01..03` resolve **every load-time DLL** of each binary on the target machine (the lists are in
`data\imports.json`, extracted from the binaries when the kit is built). The binaries link the C runtime
statically, so **no Visual C++ Redistributable is needed**; this was a real dependency of the first build, found
while writing this installer.

## For deployment tooling (Intune, SCCM, scripts)

- Run `-Action Install -Quiet -ConfigPath <file>` and branch on the exit code; read the JSON report for detail.
- Detection rule: the registry key `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\PowerAgent`
  (`DisplayVersion`), or `-Action Status` exit 0.
- Uninstall command: the `UninstallString` the installer registers, or `-Action Uninstall -Quiet`.
- Wrapping as `.intunewin` / MSI and signing are **not done** (limitation L11).

## What is tested

`scripts/poweragent/kit/Test-Installer.ps1` (development suite, 26 cases) drives the installer against a throwaway
prefix: read-only preflight, catalogue parity, strict config, tamper, missing binary, unresolvable DLL, signing
and warning policy, `-WhatIf`, install (including the deny-all default policy and a real contained run from the
installed copy), status and drift, idempotent re-install, upgrade preserving policy, downgrade refusal,
rollback, three injected failures during upgrade, an injected failure on a first install, a running-process
lock, and uninstall with exact PATH restoration. `AllUsers` scope has a separate elevated suite (`Test-AllUsers.ps1`, 9 cases): preflight when elevated, install to
test folders, machine PATH and HKLM entry created, **policy folder read-only for Users and full control only for
Administrators and SYSTEM with inheritance removed** (and not writable by Everyone or Authenticated Users),
audit/work/logs modifiable by Users, deny-all default policy, drift, an injected upgrade failure that restores the
machine PATH and HKLM entry, and uninstall with exact machine-PATH restoration. It was run once, on one machine.
**Not tested:** ARM64, managed devices, and a real Intune/SCCM deployment.
