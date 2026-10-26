"""Dependency and licence inventory for the PowerAgent crates (an SBOM-style table for IT review).

Reads `cargo metadata` (all targets, so it is a superset of what any one platform builds), walks the
dependency graph from the poweragent-* workspace members only, and writes a markdown table. It exits
non-zero if any dependency has no declared licence, so an unknown cannot slip through unnoticed.

usage: python3 deps.py OUT.md   (run from anywhere; uses rust/Cargo.toml next to this repo)
"""
import json, os, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
manifest = os.path.join(here, "..", "..", "rust", "Cargo.toml")
out = sys.argv[1] if len(sys.argv) > 1 else "DEPENDENCIES.md"

meta = json.loads(subprocess.check_output(
    ["cargo", "metadata", "--format-version", "1", "--locked", "--manifest-path", manifest]))
pkgs = {p["id"]: p for p in meta["packages"]}
nodes = {n["id"]: n for n in meta["resolve"]["nodes"]}
roots = [p["id"] for p in meta["packages"] if p["name"].startswith("poweragent") and p["source"] is None]

seen, stack = set(), list(roots)
while stack:
    i = stack.pop()
    if i in seen:
        continue
    seen.add(i)
    for d in nodes[i]["deps"]:
        if any(k["kind"] in (None, "build") for k in d["dep_kinds"]):  # skip dev-only edges
            stack.append(d["pkg"])

rows, unknown = [], []
for i in sorted(seen, key=lambda x: (pkgs[x]["name"], pkgs[x]["version"])):
    p = pkgs[i]
    if p["source"] is None:
        continue  # our own crates
    lic = p.get("license") or ""
    if not lic:
        unknown.append(p["name"])
    src = "crates.io" if (p["source"] or "").startswith("registry+https://github.com/rust-lang/crates.io-index") else p["source"]
    rows.append((p["name"], p["version"], lic or "**UNDECLARED**", src))

ours = [pkgs[i] for i in roots]
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write("# Dependency and licence inventory\n\n")
    f.write(f"Generated from `Cargo.lock` by `scripts/poweragent/deps.py`. {len(rows)} third-party crates "
            f"reachable from {len(ours)} PowerAgent crates (all platforms; build/runtime edges, not dev-only).\n\n")
    f.write("| Crate | Version | Licence (as declared) | Source |\n|---|---|---|---|\n")
    for r in rows:
        f.write("| {} | {} | {} | {} |\n".format(*r))
    f.write("\nOur crates: " + ", ".join(sorted(p["name"] + " " + p["version"] for p in ours)) + ".\n")
    f.write("\nLicence strings are what each crate declares; they are not legal advice or a substitute for review.\n")
print(f"{len(rows)} third-party crates; undeclared licences: {unknown or 'none'}")
sys.exit(1 if unknown else 0)
