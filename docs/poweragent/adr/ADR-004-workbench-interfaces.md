# ADR-004 (PROPOSED) — PowerAgent Workbench: three interfaces, one security and execution platform

**Status: proposed, not ratified. Nothing in this ADR is built.** It records an architecture proposal for the next
revision of issue #54 so it can be reviewed, with the claims it depends on marked verified or unverified. The
Electron dashboard in ADR-003 is deferred by this proposal; see "Relationship to the current code".

## Decision proposed

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

## Proposed acceptance gates for the next increment

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
| Execution platform (MXC sandbox, Podman helpers, audit, installer) | **Built** and verified on one reference machine (PR #57) |
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

## Consequences if ratified

- ADR-003 (Electron) is superseded: no standalone desktop application; a small shared status/control API instead.
- The next increment is the gateway plus one real workload, with UX-0..UX-4 as a single vertical slice.
- Issue #54's Gate 5 (signed enterprise distribution) is unchanged by this and still needs a signing certificate and a
  managed reference machine.

## Open questions

Who operates the gateway and where it runs; how workspaces map to storage and access rights; which model gateway is
used and whether prompts may leave the organisation; whether the interfaces and the gateway share one Entra tenant;
how SPIFFE trust domains are provisioned on workstations; and who owns the capability policy.
