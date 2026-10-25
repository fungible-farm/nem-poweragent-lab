# 02 — Prerequisites

## Windows

The MXC `processcontainer` backend needs a recent Windows 11 servicing level. Minimum builds (from Microsoft's
MXC documentation, recorded in `docs/poweragent/mxc-os-floor.txt` in the source repository):

| Release | Process isolation needs build |
|---|---|
| Windows 11 24H2 | 26100.9278 |
| Windows 11 25H2 | 26200.9278 |
| 26H2 | 26300.9550 |
| 26H1 | 28000.2804 |

Check yours with `winver` or `(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').UBR`.
**If a build is below its floor the probe reports the backend unavailable and every untrusted task is denied** —
that is the designed outcome, not a bug.

- **Tested:** Windows 11 Pro, build 26300.9711, x64, Entra-joined, no device management, standard (non-elevated) shell.
- **Not tested:** ARM64, Windows Server, Windows 10, virtual machines, domain-joined or Intune-managed devices,
  machines with WDAC/AppLocker policy. Treat each as an open question for your pilot (see the checklist).

## Rights

| Action | Admin needed? |
|---|---|
| Run `Verify-Pilot.ps1`, `poweragent.exe`, `poweragent-probe.exe` | **No** |
| Read the audit report | No |
| Use Podman helper services | Only whatever Podman itself needs on your fleet (a rootless machine is enough in our test) |

The kit does **not** need: PowerShell remoting or WinRM, firewall changes, services, scheduled tasks, registry
changes, or any installer. It writes only inside its own folder (`work\`, `verify-pilot.log`).

## Optional: Podman helper services

Only needed if your profiles request helper services.

- Podman 5.x/6.x for Windows (tested 6.1.4), which itself requires WSL2 or Hyper-V.
- Helper images must already be on the machine, referenced by **sha256 digest** in the registry file.
  PowerAgent never pulls images.
- Whether Podman is permitted on your managed workstations is a decision for your team (checklist item 3).

## Building from source (optional; the kit already contains binaries)

Rust stable with the MSVC toolchain, Visual Studio Build Tools with the Windows SDK, Git, and `just`.
`just poweragent::chain` runs the whole verification (needs WSL for the shell recipes). Dependencies and licences:
`docs\DEPENDENCIES.md`.

## Network

The kit and its verification need **no network** after unzip. A source build needs crates.io.
