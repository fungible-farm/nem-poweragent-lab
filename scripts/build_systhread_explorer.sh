#!/usr/bin/env bash
# Builds the systhread explorer's self-contained web bundle into
# rust/systhread-explorer/dist/. Optional first argument: a PositionedGraph JSON to ship as the
# viewer's data (default: freshly rendered from Lab 6's grid track, so the bundle always has real
# content to show). Set SYSTHREAD_EXPLORER_FEATURES=explorer-web to use the WebGL2 fallback.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
features="${SYSTHREAD_EXPLORER_FEATURES:-explorer-3d}"
dist="$root/rust/systhread-explorer/dist"
graph="${1:-}"

echo "building systhread-explorer for wasm32-unknown-unknown (features: $features)"
cargo build -p systhread-explorer --manifest-path "$root/rust/Cargo.toml" \
    --target wasm32-unknown-unknown --features "$features" --release

rm -rf "$dist"
mkdir -p "$dist/assets"

wasm-bindgen --out-dir "$dist" --target web --no-typescript \
    "$root/rust/target/wasm32-unknown-unknown/release/systhread-explorer.wasm"

cp "$root/rust/systhread-explorer/web/index.html" "$dist/index.html"

if [[ -n "$graph" ]]; then
    cp "$graph" "$dist/assets/graph.json"
else
    tmp="$(mktemp -d)"
    cargo run -p systhread-cli --manifest-path "$root/rust/Cargo.toml" -- render --track grid \
        "$root/rust/systhread-core/tests/fixtures/lab6/schema/grid_instances.yaml" \
        --out "$tmp" --explorer --explorer-layout 3d
    cp "$tmp/grid_explorer.json" "$dist/assets/graph.json"
    rm -rf "$tmp"
fi

echo "bundle ready: $dist"
echo "serve it with:  python3 -m http.server 8765 --directory $dist"
