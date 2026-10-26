# 03 — Pilot runbook

All commands are PowerShell 7 (`pwsh`), run from the kit folder, **non-elevated**.

## 1. Verify the kit

```powershell
Get-FileHash .\..\poweragent-pilot-*.zip -Algorithm SHA256   # compare with the .sha256 file shipped beside the zip
.\Verify-Pilot.ps1        # in pwsh
```

`Verify-Pilot.ps1` checks every file against `SHA256SUMS`, runs the probe matrix, runs one contained task and one
denied task, and renders the audit report. `ALL CHECKS PASSED` means the sandbox backend works on this machine.
Hash checks detect corruption or tampering *after* publication; they do not prove who published the kit
(it is unsigned — L4).

## 2. Look at the backend

```powershell
.\bin\poweragent-probe.exe
```

Prints JSON: the operating system, the available backends (for example `processcontainer` with its tier), and the
capabilities of each. If `processcontainer` is missing, see "Troubleshooting".

## 3. Write a task profile and a policy

Profile (what the task *asks for*):

```json
{ "apiVersion": "poweragent.dev/v1alpha1", "kind": "TaskProfile",
  "metadata": { "name": "study-1" },
  "spec": { "untrustedCode": true, "timeoutSeconds": 60,
            "capabilities": [
              { "kind": "fs_read",  "path": "C:/data/in"  },
              { "kind": "fs_write", "path": "C:/data/out" },
              { "kind": "sidecar",  "name": "pandapower"  } ] } }
```

Policy (what may *ever* be granted; the profile is intersected with it):

```json
{ "allowedCapabilities": [
    { "kind": "fs_read",  "path": "C:/data/in"  },
    { "kind": "fs_write", "path": "C:/data/out" },
    { "kind": "sidecar",  "name": "pandapower"  } ],
  "allowedFallbacks": [] }
```

Rules to know: `..` in a path is rejected; `fs_read`/`fs_write` are exact path grants; `net_egress` is currently
always denied; the capability kinds are fixed (`fs_read`, `fs_write`, `net_egress`, `sidecar`); there is no
"run command" kind.

## 4. Run a task

```powershell
.\bin\poweragent.exe run --profile profile.json --policy policy.json --registry registry.json `
    --audit audit.jsonl --in C:\data\in\data.bin --out C:\data\out\sum.txt
```

Exit codes: `0` worker succeeded, `1` worker failed or timed out, `2` usage or I/O error, `3` **denied**.
In this kit the workload is a **fixed demonstration job** (it sums the bytes of the input file); it exists to prove
the boundary, not to do engineering work (L3).

## 5. Helper services (optional)

Registry file (administrator-owned) — a helper must be pinned by digest and already present:

```json
[ { "name": "pandapower", "runtime": "podman",
    "image": "registry.example/pandapower@sha256:<64 hex digits>",
    "command": ["serve"], "memoryMb": 512, "cpuMillis": 1000, "pids": 128 },
  { "name": "powerio", "runtime": "podman", "dependsOn": ["pandapower"],
    "image": "registry.example/powerio@sha256:<64 hex digits>" } ]
```

Helpers are launched with Podman by default. A task that needs a helper is **denied** if it cannot be launched; it never
succeeds with a helper silently skipped. Add `--plan-only` for an explicit dry run in which helpers are audited as
*planned* and nothing is launched. Each helper runs with no network, a read-only root, no capabilities, uid 65534 and
the stated limits, is named after the task, and is removed when the task ends — including when a later helper fails to
start or the audit log cannot be written.

PowerAgent only reuses or removes a container it can prove it started: the labels and the full configuration (image,
network, read-only root, user, limits) are read back from Podman. A container that merely has the expected name is
treated as a collision and left alone.

## 5b. Revoke running helpers when policy changes, and recover from crashes

Removing a `sidecar` capability from the policy file does not by itself stop a helper that is already running.
Run:

```powershell
.\bin\poweragent.exe revoke --policy policy.json --registry registry.json --audit audit.jsonl
```

It stops every running helper that PowerAgent started (found by its `poweragent.*` labels) that the policy no longer
fully authorises: its own `sidecar` capability, every capability it requires, and every helper it depends on. A helper
that is missing from the registry is revoked, and writes a `sidecar_revoked` audit event for each. Helpers the policy
still allows keep running; containers PowerAgent did not start are never touched. It is idempotent. It is a
command you run (or schedule), not a background service (limitation L9).

If `poweragent run` is killed (power loss, task manager), no cleanup code can run. Recover with:

```powershell
.\bin\poweragent.exe reap --audit audit.jsonl     # stops every running helper PowerAgent started, whatever the policy says
```

## 6. Read the audit

```powershell
.\bin\poweragent.exe report --audit audit.jsonl --out report.html   # open report.html in a browser
```

Exit `4` and a red banner mean the log chain does not verify. Events: `authorized`, `denied` (with reason),
`sidecar_planned`, `sidecar_started`, `sidecar_stopped`, `sidecar_revoked`, `finished`.

## 7. Remove it

Delete the folder. Nothing was installed. (If you used `--podman`: `podman ps -a --filter name=pa-` should list
nothing; remove any stragglers with `podman rm -f`.)

## Troubleshooting

| Symptom | Meaning / action |
|---|---|
| `processcontainer` not in the probe output | build below the floor, or the feature is unavailable; update Windows, or record the build for us |
| Authorised task is denied as `containment_unavailable` | the probe could not show the sandbox can enforce a requirement (for example network). Expected for `net_egress` |
| Hash check fails | the file changed after packaging; re-download |
| WDAC/AppLocker blocks the exes | the kit is unsigned; this is expected on locked-down fleets (L4) — report which policy |
| Podman helper will not start | image not present locally, or not digest-pinned; `--pull never` is deliberate |
