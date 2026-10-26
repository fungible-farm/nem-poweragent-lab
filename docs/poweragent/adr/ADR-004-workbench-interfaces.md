# ADR-004 — PowerAgent Workbench: three interfaces, one security and execution platform

**Status: ACCEPTED (2026-10-26), ratified by the project owner as the next architecture revision of issue #54, with
MVOC as the organising goal (next section). Supersedes ADR-003 (Electron dashboard).** The target architecture below is
the direction; **only the execution platform and the installer exist today.** The claims the architecture depends on
carry a verification status at the end; ratification does not turn an unverified claim into a verified one.

## MVOC — Minimum Viable Operational Capability (the organising goal)

MVOC is the smallest capability an operator can **deploy, inspect, run, update, roll back and remove in a managed
environment, and trust**. It is deliberately smaller than the full Workbench: the interfaces below are built *on* it, and
none of them is worth shipping until the layer under them is installable and verifiable. Priority order:

| # | Increment | Done when | State |
|---|---|---|---|
| **MVOC-1** | **A well-composed installer** | modular; every part inspectable; extensible without editing core; payloads described as components; ready for signed OCI artifacts | **Delivered** (this revision; see "Installer composition") |
| MVOC-2 | **Signed OCI distribution** | component images come from an OCI registry by digest and their signatures are verified (fail closed) before install; the kit itself can be fetched the same way | Next. Design below; the installer's signature gate currently refuses, by design |
| MVOC-3 | **Separated policy authority** | policy lives in a protected, signed store owned by someone other than the task author, behind a minimal gateway (closes limitation L1) | Not started |
| MVOC-4 | **One real workload** through the gateway, from the Pi CLI over MCP | a real engineering calculation replaces the demonstration worker | Not started |
| MVOC-5 | **Operability** | audit export to a protected store/SIEM, a status/control API, an update channel with rollback | Not started |

The UX gates further down (LibreChat, VS Code with Pi, shared workspaces, unified audit, SPIFFE) follow MVOC-3/4.

## Installer composition (MVOC-1) — what "well composed" means here

| Property | How it is met |
|---|---|
| **Modular** | `Install-PowerAgent.ps1` is only an entry point. Behaviour lives in `installer/core` (output, config, utilities, check registry, components, system helpers), `installer/checks` (one file per category), `installer/actions` (preflight, install, uninstall, rollback, status). Each file has one job and a stated contract in its header. |
| **Inspectable** | The check catalogue is *derived from the registered checks*, not a second list to keep in sync (`-Action ListChecks`). Every run can write a JSON report (checks, components, every load-time DLL, steps). `-WhatIf` lists every mutation. The install manifest records each file's hash and owning component. `Status` verifies files and permissions against it. |
| **Extensible** | A new check is one `Register-Check` call in a new file. A new payload is one component descriptor. Neither edits core. A check that throws becomes a FAIL (fail closed); a duplicate check id is refused. |
| **Trustworthy to load** | Before any module is loaded, the entry point verifies that every file under `installer/`, `components/` and `extensions/` is listed in `SHA256SUMS` with a matching hash. An unlisted or altered file is refused (exit 10) and is never executed. Extending the kit therefore means regenerating `SHA256SUMS`, which changes the published kit hash. |
| **Component-based** | `components/*.json` (schema `poweragent.component/v1`, strict) describe what is installed: id, required or optional, dependencies (ordered, cycles rejected), and a source — `kit` (files from the extracted kit) or `oci` (an image by digest). Operators exclude optional components in config; required ones cannot be excluded. |
| **Reversible** | Staged install, kept previous version, automatic rollback on failure, manual rollback, uninstall from the manifest, exact restoration of PATH and registry entries (tested). |
| **Safe by default** | Policy starts deny-all; on AllUsers the policy folder is administrator-write only and the installer reads the permissions back and refuses to finish if they are wrong. |

### Compatibility with signed OCI artifacts (the path, and what is not built)

The `oci` component source is the seam. Today it enforces everything that does not need a verifier:

- the reference must be **pinned by digest** (a tag is rejected at validation);
- the image must already be present in the local Podman store (**the installer never pulls**; `pull` must be `never`);
- `verify.signature` is `required` or an explicit `unverified-allowed` opt-out;
- **`required` currently fails closed**: no verification mechanism is implemented, so a required signature cannot be met.
  A required component then blocks the install; an optional one is skipped with a warning and recorded; `-FailOnWarning`
  makes that a refusal. `unverified-allowed` installs with a loud warning and records `verified: false`.

MVOC-2 replaces the refusal with a real mechanism. The recommended primary mechanism is **Podman's own signature policy**
(`policy.json` with a `sigstoreSigned` or `signedBy` requirement scoped to the registry), because Podman enforces it at
pull time and is already a dependency. The installer would (1) confirm that an effective policy requires signatures for
the reference's scope, (2) pull **by digest** under that policy, (3) record the digest and the verifying identity in the
manifest. `cosign` (run from a container) and `notation` remain recognised mechanism names for sites that standardise on
them. **Not verified here:** that the Podman version on the target fleet enforces `sigstoreSigned` for the registry in
use; confirm on the reference machine before relying on it. The kit itself should also be publishable as a signed OCI
artifact so the whole distribution chain is registry-based; that is part of MVOC-2.

## Decision (the Workbench architecture)

> Three user interfaces, two agent harnesses, one security and execution platform.

| Interface | Primary user | Agent harness | Experience |
|---|---|---|---|
| LibreChat | engineers, analysts, operations teams | LibreChat's agents | conversational assistant, studies, reports |
| VS Code with Pi | engineering-software developers, modellers | Pi (SDK / RPC) | code, models, scripts, debugging, interactive studies |
| Pi CLI | advanced engineers, automation | Pi (native) | terminal-first agent with tools and workflow automation |

All three call the same **PowerAgent gateway**, which supplies identity, policy, workspace authorisation, capability
discovery, execution (the MXC sandbox and Podman helpers) and audit. The gateway is the common platform, not the
common agent harness, so the interfaces can evolve independently while policy enforcement is identical. A new
interface does not change the execution subsystem.

```
   engineer          developer          power user
      │                  │                  │
  LibreChat         VS Code + Pi          Pi CLI
      └──────────────────┼──────────────────┘
                  POWERAGENT GATEWAY
        identity · policy · workspaces · capability discovery · audit
                         │
        ┌────────────────┼────────────────┐
   Windows MXC       Podman / WSL2     enterprise tools
   (contained)       (helpers)         (through the same gateway)
                         │
                 tasks · artifacts · audit
```

### Shared objects, not shared conversations

The interfaces share durable engineering objects, not each other's conversation state: **workspace id**, **task id**,
**artifact id**, **trace id**, **capability profile**. A study started in one interface can be inspected or continued
from another; what transfers is the workspace, task state, artifacts and provenance. Synchronising two agent
harnesses' mutable conversation stores is deliberately avoided; a later "session hand-off" can attach an approved
summary instead.

### Identity (proposed)

| Client | Registration | Authentication |
|---|---|---|
| LibreChat | confidential web app | OIDC single sign-on |
| VS Code integration | public native client | authorisation code + PKCE |
| Pi CLI | public native client | browser authorisation or device code |
| Gateway | protected API resource | validates identity and delegated permissions |
| Headless automation | federated workload identity | SPIFFE JWT-SVID exchanged for an Entra token |

A workload's SPIFFE identity must **not** substitute for user authorisation. A request carries an independently
validated binding: user → client application → task → workload → permitted resources.

### Audit at three boundaries (proposed)

Agent harness (prompts, turns, tool requests and results) · model gateway (the actual model-bound requests, model,
usage, latency) · PowerAgent gateway (identity, authorisation, resource access, execution, results). Use OpenTelemetry
for correlation. The execution audit stays independently authoritative. Prompts and tool outputs for sensitive
workloads belong in a separately access-controlled transcript store, not ordinary operational logs.

### One design constraint (accepted as stated)

IDE and agent extensions can run commands and read files under their host process identity. Their permission prompts
are usability controls, **not** isolation equivalent to MXC or Podman. Privileged engineering operations must always
pass through the authenticated gateway; ordinary IDE file editing is a different class.

## Acceptance gates for the Workbench interfaces (after MVOC-3 and MVOC-4)

| Gate | Requirement | Demonstration |
|---|---|---|
| UX-0 | LibreChat with Entra sign-in | an engineer signs in and sees only authorised engineering tools |
| UX-1 | Pi CLI with tools | the same user inspects and runs an approved study |
| UX-2 | VS Code with Pi | the same study and solver capabilities from the editor |
| UX-3 | shared workspace | results produced in one interface are visible in the other two |
| UX-4 | unified audit | each interface yields correlated user, model, tool and execution events |
| UX-5 | workload federation | workloads authenticate independently and cannot impersonate each other |
| UX-6 | independent upgrades | updating LibreChat, Pi or the extension does not require rebuilding the sandbox layer |

UX-0..UX-4 should be one vertical slice using a **real engineering calculation**, not the demonstration worker.

## Relationship to the current code (what exists, what does not)

| Proposed element | State in this repository |
|---|---|
| Execution platform (MXC sandbox, Podman helpers, audit) | **Built** and verified on one reference machine (PR #57) |
| **Installer (MVOC-1)**: modular, component-based, extensible, OCI-ready, with a fail-closed signature gate | **Built** and tested (44 current-user cases, 11 elevated cases) |
| Signed OCI verification and pull-by-digest (MVOC-2) | **Not built**; the gate refuses until a mechanism exists |
| Gateway: identity, policy authority, workspace authorisation, capability discovery over MCP | **Not started.** Today `poweragent run` is a CLI that takes a caller-chosen policy file (limitation L1) |
| Entra / SPIFFE integration | **Not started** |
| Shared workspace / task / artifact / trace objects | **Not started** (the audit log has task names, not these ids) |
| Real solver workload | **Not started** (the workload is a fixed demonstration job) |
| Any of the three interfaces | **Not started** |
| Status/control API usable by all three interfaces (optionally a Podman Desktop extension) | **Not started**; this is what replaces the deferred Electron dashboard |

The gateway is what closes limitation L1 (the policy authority must not be the caller). Until it exists, the
runner demonstrates the boundary and the audit, not separation of duties.

## Claims this proposal relies on, and their verification status

Checked on 2026-10-26 with a web search; sources are secondary and should be confirmed against the projects themselves.

| Claim | Status |
|---|---|
| LibreChat supports MCP tools with OAuth, and per-agent tool selection | **Supported** by [LibreChat's MCP docs](https://librechat.ai/docs/features/mcp) (OAuth callback and configuration described) |
| LibreChat integrates Entra ID sign-in | **Supported**: an [OpenID token-reuse page](https://www.librechat.ai/docs/configuration/authentication/OAuth2-OIDC/token-reuse) covers Entra. **Not found:** an Entra-specific MCP authorisation guide. OIDC token placeholders for MCP are only available to servers defined in `librechat.yaml`, not UI-created ones |
| Pi exposes `tool_call` and `tool_result` hooks | **Supported** by [Pi's extensions documentation](https://pi.dev/docs/latest/extensions) and third-party hook docs |
| Pi exposes `before_provider_request` | **Partly**: seen in a third-party hooks package; payload not confirmed |
| Pi exposes `agent_settled` | **Not found** in any source checked |
| Pi supports MCP (stdio and Streamable HTTP) natively | **Unconfirmed**: MCP tools were seen arriving through extensions, not as a core feature |
| A VS Code extension for Pi embedding the SDK, with sidebar chat, diffs, approvals and checkpoints, under MIT | The extension [Zetaphor/pi-vscode-extension](https://github.com/Zetaphor/pi-vscode-extension) **exists** with a sidebar chat UI; its **licence and maturity were not confirmed** |
| A second Pi extension using the installed CLI, under AGPL-3.0 ("YeSho-cpp/pi-coding-agent") | **Not found.** Other Pi extensions exist ([pithings/pi-vscode](https://github.com/pithings/pi-vscode), cdervis/vscode-pi, vs-pi-agent); none confirmed AGPL |
| Podman Desktop can host an extension for status and control | **Not verified here** |
| SPIFFE JWT-SVID can be exchanged for an Entra token (workload identity federation) | **Not verified here** |

Before building on any row marked partly, unconfirmed or not found, read the project's own repository and licence.
Do not treat the extension choice as decided: evaluate each candidate's release maturity, licence and security model.

## Consequences

- ADR-003 (Electron) is **superseded**: no standalone desktop application; a small shared status/control API instead.
- The order of work is MVOC-1 (done), MVOC-2 (signed OCI), MVOC-3 (policy authority and gateway), MVOC-4 (one real workload),
  then the interface gates. Interfaces are not started before MVOC-3.
- Issue #54's Gate 5 (signed enterprise distribution) is unchanged by this and still needs a signing certificate and a
  managed reference machine.

## Open questions

Who operates the gateway and where it runs; how workspaces map to storage and access rights; which model gateway is
used and whether prompts may leave the organisation; whether the interfaces and the gateway share one Entra tenant;
how SPIFFE trust domains are provisioned on workstations; and who owns the capability policy.
