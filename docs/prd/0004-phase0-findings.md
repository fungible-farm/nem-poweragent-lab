# PRD-0004 Phase 0 — env verification findings

Companion to [`0004-plexos-direct-mcp-and-strangler-fig.md`](0004-plexos-direct-mcp-and-strangler-fig.md)'s
Phase 0 ("env verification. Confirm `plexosdb-mcp` installs and runs (`uvx plexosdb-mcp health`,
`doctor`, `capabilities`) in this sandbox"). This file is the evidence record; the PRD's own Phase 0
bullet and acceptance-criteria checkbox point here rather than repeating the transcript inline —
same split PRD-0005 used between its terse "resolved" bullets and this session's actual
command-by-command trail.

**No lab directory created for this phase.** Phase 0 is verification only — no lab code exists yet.
Following PRD-0005's own Phase 0 precedent (which resolved its env-verification questions as prose
edits to the PRD itself, not a new file or lab dir), this findings doc is the lightest artifact that
still satisfies AGENTS.md's "name the specific tool you tried" discipline. `labs/10-plexos-direct-and-strangler-fig/`
should be created at Phase 1, when there is real workflow code to put in it (the lab number is
confirmed as **10**, not the PRD's originally-proposed `labs/07-...` — labs 07/08/09 are already
taken by `rust-comtrade-fft-detector` and the two cim-gridy labs; see PRD update below).

## Summary

| Check | Result | Evidence |
|---|---|---|
| `plexosdb` (the library) installs via `uv` | **PASS** | `uv add plexosdb` resolves and installs cleanly |
| `plexosdb` PyPI version matches PRD's "v1.6.0" claim | **PARTIAL — corrected** | Latest on PyPI is `1.6.1`; `uv add plexosdb` (no pin) resolves `1.5.0` by default because `1.6.0`/`1.6.1` depend on a prerelease-only transitive package (`plexos2duckdb`) that `uv` won't select without `--prerelease=allow` |
| `plexosdb-mcp` is "own PyPI package" per PRD | **FAIL — corrected** | `https://pypi.org/pypi/plexosdb-mcp/json` returns HTTP 404. It is **not published to PyPI**. `uvx plexosdb-mcp ...` (bare, PRD's literal command) fails: "plexosdb-mcp was not found in the package registry" |
| `plexosdb-mcp` exists and is installable some other way | **PASS** | Real source at `NatLabRockies/plexosdb`, `src/plexosdb-mcp/` (own `pyproject.toml`, console script `plexosdb-mcp`). Installs via `uv add "plexosdb-mcp @ git+https://github.com/NatLabRockies/plexosdb#subdirectory=src/plexosdb-mcp"` |
| `plexosdb-mcp --help` / `health` / `version` / `doctor` / `capabilities` | **PASS** (via `uv run` in a prepared project) | Real JSON output for all four documented subcommands, see below |
| `uvx --from git+...#subdirectory=... plexosdb-mcp --help` (cold, one-shot) | **BLOCKED in this session** | Hung past a 180s `timeout` (process observed in uninterruptible `D` state); killed, exit 124. Not reproduced under `uv add` + `uv run` in a persistent project (see below) |
| Stdio transport (Goal 3 / open question) | **Answered: yes, standard stdio MCP server** | A real `initialize` JSON-RPC request piped to `uv run plexosdb-mcp` (no subcommand) on stdin returned a spec-shaped MCP `initialize` response on stdout; banner/log noise went to stderr only |
| Network egress this session | GitHub (`github.com`, `raw.githubusercontent.com`, `api.github.com`) and PyPI (`pypi.org`) both reachable | Real `git clone`-via-`uv`, `curl`, and `uv add` calls all succeeded — see AGENTS.md capability-matrix framing: this is a session observation, not a standing guarantee |

## Detailed evidence

### 1. `plexosdb` (library) via `uv`

```
$ uv add plexosdb
Resolved 5 packages in 346ms
Installed 2 packages in 1ms
 + loguru==0.7.3
 + plexosdb==1.5.0
```

PyPI's own JSON API (`https://pypi.org/pypi/plexosdb/json`) reports the true latest release list up
to `1.6.1`: `[..., '1.4.0', '1.4.1', '1.5.0', '1.6.0', '1.6.1']`. Pinning explicitly:

```
$ uv add "plexosdb==1.6.1"
  × No solution found when resolving dependencies:
  ╰─▶ Because only the following versions of plexos2duckdb are available:
          plexos2duckdb<0.1.0b11
          plexos2duckdb>=0.1.0
      and plexosdb==1.6.1 depends on plexos2duckdb>=0.1.0b11,<0.1.0, we can
      conclude that plexosdb==1.6.1 cannot be used.
  help: ... `--prerelease=allow`
```

With `--prerelease=allow` it resolves and installs cleanly (`plexosdb==1.6.1`, pulling in
`plexos2duckdb==0.1.0b12` and a prerelease `duckdb==1.6.0.dev365`). **Finding**: the PRD's "v1.6.0
as of this session" is real (confirmed on PyPI) but not the version a plain `uv add plexosdb`
resolves to today — a future session pinning `plexosdb` should either accept `1.5.0` or explicitly
opt into prereleases, and should say so, rather than assume `uv add plexosdb` alone lands on the
newest release.

### 2. `plexosdb-mcp` is not on PyPI

```
$ curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/plexosdb-mcp/json
404

$ uvx plexosdb-mcp health
  × No solution found when resolving tool dependencies:
  ╰─▶ Because plexosdb-mcp was not found in the package registry and you
      require plexosdb-mcp, we can conclude that your requirements are
      unsatisfiable.
```

This directly contradicts the PRD's "(own PyPI package)" characterization, and means the PRD's
literal example commands (`uvx plexosdb-mcp health`, `doctor`, `capabilities`) do not work as
written against the public package index, in this session. This is a real, reportable Phase 0
finding, not a sandbox/network problem — PyPI itself confirms no such distribution exists (as of
this session; the maintainers may publish it later).

### 3. `plexosdb-mcp` source is real and does install from GitHub

`NatLabRockies/plexosdb`'s `src/` directory contains two packages side by side: `plexosdb` (the
library, published) and `plexosdb-mcp` (the MCP server, **not** published — source-only). Its own
`pyproject.toml` (fetched directly, not assumed):

```toml
[project]
name = "plexosdb-mcp"
version = "0.1.0"
...
dependencies = [
    "plexosdb>=1.3.4",
    "fastmcp>=3.0.0",
]
[project.scripts]
plexosdb-mcp = "plexosdb_mcp.__main__:main"
```

Installing it directly from the GitHub subdirectory — the "closest real equivalent" to the PRD's
`uvx plexosdb-mcp` per this task's own guidance — works cleanly:

```
$ uv add "plexosdb-mcp @ git+https://github.com/NatLabRockies/plexosdb#subdirectory=src/plexosdb-mcp"
   Building plexosdb-mcp @ git+https://github.com/NatLabRockies/plexosdb@fd605d0f...#subdirectory=src/plexosdb-mcp
   Building plexosdb @ git+https://github.com/NatLabRockies/plexosdb@fd605d0f...
Installed 81 packages in 46.02s
 + fastmcp==3.4.7
 + mcp==1.29.0
 + plexosdb==1.6.1 (from git+...)
 + plexosdb-mcp==0.1.0 (from git+...)
 ...
```

(Note: installing `plexosdb` from the git source, alongside `plexosdb-mcp`, did **not** require
`--prerelease=allow` — the git checkout pins its own internal `plexos2duckdb` constraint
consistently, unlike requesting `plexosdb==1.6.1` standalone from PyPI above.)

### 4. `health` / `version` / `doctor` / `capabilities` — all real, all pass

Run via `uv run plexosdb-mcp <subcommand>` inside the project that installed it in step 3 above
(this is the "genuinely usable" bar from PRD-0005's own Phase 0 precedent — actually invoked, not
just read from source):

```
$ uv run plexosdb-mcp health
{"ok": true, "active_sessions": 0, "mode": "cli"}

$ uv run plexosdb-mcp version
{"ok": true, "version": "0.1.0", "plexosdb_version": "1.6.1", "python": "3.13.5"}

$ uv run plexosdb-mcp doctor
{"ok": true, "checks": [{"name": "fastmcp", "ok": true, "detail": "3.4.7"}, {"name": "plexosdb", "ok": true, "detail": "1.6.1"}, {"name": "empty_session", "ok": true}]}

$ uv run plexosdb-mcp capabilities
{"ok": true, "tools": {"session": [...], "discovery": [...15 tools...], "edit": [...7 tools...], "export": ["save_xml", "to_csv"], "admin": ["get_server_config"]}, "subcommands": ["health", "version", "doctor", "capabilities"]}
```

All four diagnostic subcommands the PRD names exist, run, and return real JSON exactly matching the
PRD's tool-surface table (session/discovery/edit/export/admin groups). `--read-only`, `--json`,
`--version`, `--allow-tty`, `--xml-path` flags are also real (confirmed via `--help` output), not
yet individually exercised (out of scope for Phase 0 — Phase 1 loads an actual PLEXOS XML study).

### 5. `uvx --from git+...` cold-start hang (real friction, not reproduced under `uv run`)

The very first attempt used `uvx --from "git+https://github.com/NatLabRockies/plexosdb#subdirectory=src/plexosdb-mcp" plexosdb-mcp --help` directly (no prior `uv add`). It installed dependencies
successfully (`Installed 81 packages in 15.52s`) but then the actual `plexosdb-mcp --help` process
hung — observed via `ps` in uninterruptible-sleep (`D`) state — past a 180-second `timeout`, killed
with exit 124. Re-running the equivalent command (`--help`) via `uv run` inside a project that had
already run `uv add` for the same git source (step 3/4 above) returned instantly with normal
argparse `--help` output. This looks like `uvx`-specific friction with a fresh, one-shot tool
install from a git subdirectory (possibly first-run duckdb native-extension initialization, not
reproduced on a second invocation) rather than a bug in `plexosdb-mcp` itself — named here rather
than silently retried, per AGENTS.md's "don't route around a mismatch silently" rule. The **working,
repeatable path is `uv add` + `uv run`, not cold `uvx --from git+...`.**

### 6. Stdio transport — Goal 3's open question, answered with real evidence

Piped a real MCP `initialize` JSON-RPC request to `plexosdb-mcp` invoked with no subcommand
(the code path that reaches `build_mcp_server(...).run()`):

```
$ echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "phase0-probe", "version": "0.0.1"}}}' | uv run plexosdb-mcp
```

stdout (exactly one line, valid JSON-RPC):

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"experimental":{},"logging":{},"prompts":{"listChanged":false},"resources":{"subscribe":false,"listChanged":false},"tools":{"listChanged":true},"extensions":{"io.modelcontextprotocol/ui":{}}},"serverInfo":{"name":"plexosdb","version":"3.4.7"}}}
```

stderr got the FastMCP startup banner and `INFO Starting MCP server 'plexosdb' ... with transport
'stdio'` — never mixed into stdout. **This is exactly the shape a stdio MCP child process needs**:
clean JSON-RPC on stdout, everything else on stderr, standard `initialize` handshake honored. This
confirms `plexosdb-mcp` itself behaves as a normal stdio MCP server, which is the necessary
precondition for Goal 3's "does Agent Framework's MCP client support launching it directly as a
stdio subprocess" question — **but this session did not exercise Microsoft Agent Framework's own
MCP client against it** (out of scope for Phase 0; would need Phase 1's actual workflow code). Net:
real positive signal on the server side of the transport question, not a full answer to the
Agent-Framework-client side — reported honestly as partial, not overstated.

## Answer to PRD-0004's Phase 0 acceptance criterion

> `plexosdb-mcp` confirmed runnable in this sandbox (Phase 0), exact commands cited.

**Confirmed runnable — via `uv add "plexosdb-mcp @ git+https://github.com/NatLabRockies/plexosdb#subdirectory=src/plexosdb-mcp"` then `uv run plexosdb-mcp {health,version,doctor,capabilities}`,
not via the PRD's literal `uvx plexosdb-mcp ...` (that specific invocation fails: package not on
PyPI).** Both the corrected install path and the literal-PRD-command failure are real, cited
findings, not assumptions.

## Honest assessment for Phase 1

Phase 1 (wiring `plexosdb-mcp` into an Agent Framework workflow that loads a PLEXOS study and lists
its objects) looks feasible in this sandbox: the server installs cleanly from its real upstream
source, all four diagnostic subcommands work, and a real MCP `initialize` handshake over stdio
succeeded with a spec-correct response — the core mechanics an Agent Framework MCP stdio client
would rely on are demonstrably present. The one real gap Phase 1 must carry forward is packaging:
since `plexosdb-mcp` isn't on PyPI, any pinned dependency needs to reference the GitHub subdirectory
(a specific commit or tag, not a floating `main`) rather than a PyPI version string — a materially
different (and less stable) pin than the PRD assumed. Whether Microsoft Agent Framework's MCP
client can launch a `git+https://...#subdirectory=...` `uvx`/`uv run` target directly as a stdio
child process is itself untested here and should be Phase 1's first concrete check, given the
`uvx --from git+...` cold-start hang observed in finding 5 above.
