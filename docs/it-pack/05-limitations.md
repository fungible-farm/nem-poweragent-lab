# 05 — Limitations (read this first)

These are the things this kit is **not**. They are listed so nobody has to discover them.

| # | Limitation | Consequence |
|---|---|---|
| **L1** | **The policy authority is not yet separate from the caller.** The runner reads the policy from a file path the caller passes. | The kit demonstrates the *decision logic* and the sandbox, not separation of duties. A real deployment needs a protected policy store (ACL-protected path, signed policy, or a service) owned by someone other than the task author. This is an open design decision. |
| **L2** | **The sandbox is Microsoft's, and Microsoft's documentation says its profiles are not yet to be treated as a security boundary.** | Our tests show observed behaviour on one build. They are not a penetration test or an audit. Do not use for untrusted code on sensitive systems without your own security review. |
| **L3** | **The workload is a fixed demonstration job** (sums the bytes of a file). | It proves the boundary. Real solver workloads (power-flow, dynamic studies) are not wired in. |
| **L4** | **Unsigned.** `SHA256SUMS` detects corruption, not a malicious publisher. | Expect WDAC/AppLocker/SmartScreen to block it on locked-down fleets. Signed packaging, Intune/SCCM deployment, silent install/upgrade/rollback and standard-user operation are *not done*. |
| **L5** | **Helper-image signatures are not verified.** Digest pinning is enforced, so a swapped image is refused, but nothing checks who produced the pinned digest. | Source your helper images from a registry and process you trust. |
| **L6** | **Network access is unsupported.** Every `net_egress` request is denied, and helpers run with no network. | Helpers that need network (data feeds, licence servers) will not work yet. A proxy-only egress model is the planned approach and is unproven. |
| **L7** | **The audit log is tamper-*evident*, not tamper-proof.** Edits and deletions of earlier entries are detected. Someone who can rewrite the whole file can recompute the chain, and truncating the tail is not detected. | Forward the log to a protected store / SIEM, or anchor the chain tail externally, before relying on it. There is no log shipping yet. |
| **L8** | **One test machine.** Windows 11 build 26300.9711, x64, Entra-joined, unmanaged. | ARM64, Server, VMs, domain-joined and Intune-managed devices, and machines under WDAC/AppLocker are untested. |
| **L9** | **Not implemented:** PowerShell JEA fallback (deferred; a first attempt is kept on a separate branch, unverified), an Electron dashboard (an HTML report is provided instead), Windows-adapter helpers. Revoking a *running* helper is an on-demand command (`poweragent revoke`), not a background service that reacts to policy changes. | Features described in the architecture may be absent; see `gate-status.md` for the exact state. |
| **L12** | **Automated CI exercises Windows only in part.** A `poweragent-windows` job compiles every PowerAgent crate for Windows and runs the native adapter (including its junction tests), the logic suites and the Podman argument tests. Hosted runners do not guarantee the Windows build or Podman that the sandbox tests need, so those are not run there. | The sandbox adversarial, end-to-end and Podman tests are run on a prepared Windows 11 machine (`just poweragent::chain`) and their output is saved under `evidence\`. A green CI run is not proof of sandbox enforcement. |
| **L10** | **Podman is optional and has its own requirements** (WSL2 or Hyper-V). | Whether it is permitted on your fleet is a policy decision for you. |
| **L11** | **The installer is a PowerShell script, not an MSI or `.intunewin`, and it is unsigned.** | Wrapping for Intune/SCCM and signing are still to do. `CurrentUser` scope is covered by 26 automated cases and `AllUsers` by an 11-case elevated test (run once, on one machine, with the folder permissions and restore-after checks). A real Intune/SCCM deployment is untested. |

## Not claimed

- Compliance with any standard or regulator's requirement.
- Suitability for operational (production) power-system access.
- Protection against a malicious administrator, a compromised OS, or a flaw in the Windows sandbox itself.
- That an AI model will behave; the design assumes it may not, and relies on the OS boundary instead.
