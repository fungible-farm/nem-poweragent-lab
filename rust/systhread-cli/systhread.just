# systhread.just -- import into any adopting project's own Justfile with:
#   mod systhread "path/to/systhread.just"
# then call `just systhread::sysml-check <track> <path>` etc. No logic lives here --
# every recipe is a thin one-line call into the systhread binary (FR4).

# Generate + validate one track's .sysml (track: digital-thread | grid | pipeline).
sysml-check track path:
    systhread check --track {{track}} {{path}}

# Generate, validate, translate, and render one track to a manifest-described output directory.
sysml-render track path out:
    systhread render --track {{track}} {{path}} --out {{out}}

# Interactive model explorer (FR7 -- ships in Phase 3).
sysml-explore:
    systhread explore

# Per-commit drift check (FR10 -- ships in Phase 4).
sysml-drift:
    systhread drift
