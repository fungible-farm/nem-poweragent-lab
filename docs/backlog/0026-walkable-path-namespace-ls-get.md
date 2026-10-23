# 0026 — A walkable path namespace: one grammar, `ls` and `get`, answers that cite paths

- **Status:** open, the next step after 0024's step 1. This is the 80/20 cut of
  [0027](0027-functional-data-virtualization-layer.md), agreed with the user on 2026-10-23.
- **Affects:**
  - the tool set, which means a new run root and retrained students;
  - the provenance check (PC-REQ-004);
  - constrained decoding (PC-REQ-002);
  - backlog 0024's step 3, which this replaces.

## Why
The model only ever sees the interface: path syntax, listings, values. Changing the interface costs
a retrain. The engine underneath (Python now; Rust, RocksDB and DataFusion later in 0027) can be
swapped without retraining as long as the paths stay the same. So fix the interface first, on data
we already have.

## Scope
1. **A path grammar in one file.** It is context-free, written in the subset where PEG, GBNF and
   Lark agree: no lookahead and no choices that can overlap. Example shapes:
   - `/case/<network_id>/<kind>/<id>/<attribute>`, e.g. `/case/snem-sa-2000/bus/985/vn_kv`;
   - `/env/…` and an `as_of=<time>` segment, reserved for later and parsed but answering "no data".

   The same file is used three ways: to validate requests, to compile to GBNF/Lark for decoding,
   and to document the paths.
2. **`ls(path)`:** a node's children, paged, always with the total count. Listing
   `/case/snem-sa-2000/bus/` is how a model finds a valid bus. It removes FM-26's guessing by
   design, not by a better error.
3. **`get(path)`:** a value and its canonical path. It reads from pandapower's tables, as loaded by
   `pm._load_network_object`. Study results stay with `run_study_trial`, unchanged.
4. **Answers cite paths.** A number in an answer must equal `get(cited path)`, or appear in a tool
   response, as the provenance check requires today. The grader resolves the citation, which is a
   check, not a search.

## Not in scope (see 0027)
- **RocksDB and memoisation:** a study solve takes about a second (r6b journals).
- **DataFusion / Polars, FUSE / 9P, a Rust engine.**
- **Weather:** G5's data is blocked.
- **CIM containment paths:** snemSA has no Substation, VoltageLevel or Bay classes in its G4
  export.
- **Derived `/fn/…` nodes:** moving the fit trials into paths changes the trained procedure.

## Acceptance (deterministic)
- **Grammar consistency:** the PEG/EBNF source and its GBNF/Lark compilation accept and reject the
  same set of paths, using a corpus of valid paths and mutated ones.
- **`ls` is exact:** it returns exactly `net[table].index` for every table, with the right count;
  checked against pandapower.
- **Smoke run with the new tools:**
  - no attempt calls a tool with an id that the previous response didn't name and `ls` didn't list;
  - every number in an answer resolves through its citation or a tool response;
  - pass rate at least the r6b Qwen student's 17/20.
- **Comparability:** `compare_agents` refuses to compare with r6 unless the tool-set condition is
  named.

## Cost
- **Code (estimate, not measured):** a grammar file, two MCP tools, a path-based provenance check,
  trajectories that use `ls` after a bad id, and tests.
- **Measured cost of a retrain** (both students, from v2): 2.7 h for Qwen and 3.4 h for Granite, then
  a smoke run and an evaluation run.
