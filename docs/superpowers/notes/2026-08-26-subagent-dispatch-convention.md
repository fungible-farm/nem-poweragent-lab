# Subagent dispatch convention (internal reference, non-binding)

**Status:** reference only. Not part of the systhread spec, not enforced by CI, not a
requirement for this repo, adds no new dependency. A controller session may use this
naming/header shape when writing a dispatch prompt under
`superpowers:subagent-driven-development` — or ignore it and write plain prose. Either
is fine.

**Origin:** produced 2026-08-26 by three parallel, independently-dispatched subagents —
one drafted a naming vocabulary, one adversarially attacked the idea of a naming
convention before trusting it, one built and validated a SysML v2 model of this
coordination structure itself (see `2026-08-26-agent-coordination.sysml`, same
directory). This doc is the controller's synthesis of the two prose findings.

## 1. Role vocabulary

Four names, one-to-one with the four real roles `subagent-driven-development` already
defines. No fifth role — if a task doesn't fit one of these four, it isn't a dispatch;
do it inline in the controller session.

| Name | Maps to | Why this name |
|---|---|---|
| `builder` | implementer | produces the artifact — code, tests, one commit |
| `checker` | task reviewer / scoped re-reviewer | a fast, scoped pass against one diff |
| `auditor` | final whole-branch reviewer | broad, post-merge-candidate scan, most capable model |
| `fuzzer` | adversarial reviewer | actively tries to break a claim or design, not just confirm it |

## 2. Scope and lineage

A flat role name collides across cases that matter operationally. Two real collisions,
found by adversarial review of the naive scheme, that this section exists to close:

- **`checker` covers three different authority scopes**: a task-scoped review (gates one
  task's `BASE..HEAD`), a scoped re-review of one fix round (gates only that round's
  diff — new findings on untouched code go to the ledger, not the loop), and the final
  `auditor` pass (branch-scoped, triage authority over deferred minors). Distinguish them
  with a scope tag, not a new name — `auditor` already covers the third case.
- **`builder` identity is not continuous across a fix loop.** Fix rounds 1-3 resume the
  same dispatched agent; round 4-5 discards it and dispatches a fresh one on a stronger
  model. A flat name can't tell "the builder, still" from "a new builder, replacing one
  that got stuck" — the distinction the controller's own escalation judgment depends on.

**Tag shape:** `<role>:<scope>[#<generation>]`

- `scope` — `unit` (one file), `member` (one task or one fix round, named:
  `task-N` or `fix-N.R`), `workspace` (whole branch).
- `generation` — only meaningful for `builder` across a fix loop. Stays flat across
  resumed rounds 1-3 (`builder:task3#1`), increments once on round 4-5's fresh dispatch
  (`builder:task3#2`). Written once by the controller in its ledger line; a dispatched
  agent never queries its own tag — this is dead data for the ledger, not a live lookup.

Examples: `checker:task3` (initial task review) vs. `checker:fix3.2` (re-review of fix
round 2 only) vs. `auditor:workspace` (final review) — same role family, three scopes,
no ambiguity about what diff range each one may pass judgment on.

## 3. Capability header

A name alone does not enforce anything — it is a label a human or a ledger entry reads,
not a boundary the dispatched process is prevented from crossing. The header below is
the part that actually states, before the task prose, what this dispatch may touch.
Whether it stays advisory (read by the controller when composing the prompt) or becomes
mechanically checked is a future decision; today it is advisory, and that's stated
honestly rather than implied otherwise.

```
role:       builder | checker | auditor | fuzzer
scope:      unit | member | workspace
generation: <N>                    # builder only, see §2
tier:       cheap | standard | most-capable   # unchanged from the existing SDD skill
targets:    <explicit path or paths this agent may touch>
write:      ro | rw                # rw implies targets is authoritative, not "anything nearby"
commit:     yes | no                # yes => exactly one commit, no --amend, no --no-verify
dispatch:   none                    # always none — a dispatched agent never spawns its
                                     # own subagents or reviewers; that stays the
                                     # controller's job alone
reports-to: controller
status:     DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
```

`targets` is the actual scope boundary — `scope` names the *shape* (file/task/branch),
`targets` names the *paths*. A `checker` or `auditor` is `write: ro` by construction: it
reports findings, it does not patch the diff it is reviewing.

## 4. Worked example — PR #38, SVG-escaping fix

Real, already-shipped task: project-supplied instance labels were interpolated
unescaped into SVG `<text>` content in `rust/systhread-core/src/render.rs` (issue #37).

**Builder dispatch header:**

```
role:       builder
scope:      member (task: escape SVG node labels — closes #37)
generation: 1
tier:       standard
targets:
  - rust/systhread-core/src/render.rs        (rw)
  - rust/systhread-core/tests/render_test.rs (rw)
write:      rw, scoped to the two paths above — do not touch sysml_gen.rs or numfmt.rs
commit:     yes — one commit on fix/systhread-svg-escaping
dispatch:   none
reports-to: controller
```

**Checker dispatch header** (reviewing the builder's diff once it lands):

```
role:       checker
scope:      member (review: escape SVG node labels, builder commit e99e336)
tier:       cheap
targets:
  - rust/systhread-core/src/render.rs        (ro, diff only)
  - rust/systhread-core/tests/render_test.rs (ro, diff only)
write:      none — report findings only
commit:     no
dispatch:   none
reports-to: controller
```

PR #41 (the `numfmt` consolidation) has the same shape: `targets` would list `lib.rs`,
`numfmt.rs`, `render.rs`, `sysml_gen.rs` — the four files that diff actually touched —
with `scope: member` since it was one P2 cleanup task, not a branch-wide pass.

## 5. Non-goals

This is naming and header discipline for dispatch prompts, nothing else. It is not a
requirement, is not wired into systhread's spec or CI, adds no new file, tool, or
dependency to the repo, and does not change what a `builder`/`checker`/`auditor`/
`fuzzer` is *allowed* to do — that is still whatever `subagent-driven-development` and
the controller's own judgment already say. Treat this as available, not mandatory.
