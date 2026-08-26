//! `systhread-explorer [asset-path]` -- one generic viewer binary, reused by every adopting
//! project (design §5). The per-project part is the PositionedGraph JSON it loads, never a
//! recompile.

fn main() {
    let asset_path = std::env::args().nth(1).unwrap_or_else(|| "graph.json".to_string());
    systhread_explorer::app::run(&asset_path);
}
