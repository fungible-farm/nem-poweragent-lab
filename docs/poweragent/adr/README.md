# PowerAgent architecture decisions

| ADR | Decision | Status |
|---|---|---|
| ADR-001 | Use the `mxc-sdk` Rust crate (pinned) and prefer the Windows `processcontainer` backend; do not copy its sandbox logic | Accepted; implemented (`poweragent-probe`, `poweragent-exec`) |
| ADR-002 | Fallback order MXC, then JEA, then `windows-rs`, then an isolated VM; fallback needs administrator policy; a failed authorisation never falls back; no permitted backend means deny | Accepted; implemented for MXC and the native adapter; JEA deferred (branch `feat/54-jea-endpoint-deferred`) |
| ADR-003 | Electron is presentation only | **Superseded by ADR-004** (no standalone desktop application; a status/control API instead). The text of issue #54 still lists it |
| [ADR-004](ADR-004-workbench-interfaces.md) | Three interfaces, two agent harnesses, one security and execution platform; **MVOC** as the organising goal, starting with a well-composed installer | **Accepted 2026-10-26**; MVOC-1 delivered; MVOC-2..5 tracked in #58 |

ADR-001..003 are recorded in the body of issue #54 (section 2); this directory holds the later decisions.
