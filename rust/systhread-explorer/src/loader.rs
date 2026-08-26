use systhread_core::positioned::PositionedGraph;

/// Parses a `PositionedGraph` artifact and refuses one whose layout does not line up with its
/// graph. Everything downstream indexes nodes and positions in parallel, so this is the single
/// place that invariant is enforced -- after this returns `Ok`, `scene::scene_spec` is infallible.
pub fn load_positioned_graph(json: &str) -> Result<PositionedGraph, String> {
    let graph = PositionedGraph::from_json(json)?;
    if !graph.layout_matches_graph() {
        return Err(format!(
            "PositionedGraph layout does not match its graph: {} nodes but {} layout entries (or ids in a different order)",
            graph.graph.nodes.len(),
            graph.layout.len()
        ));
    }
    Ok(graph)
}

/// The byte-oriented entry point the Bevy asset loader uses. Kept here, outside the `explorer-3d`
/// feature, so the only parsing logic in the crate is testable on both targets without Bevy.
pub fn positioned_graph_from_bytes(bytes: &[u8]) -> Result<PositionedGraph, String> {
    let text = std::str::from_utf8(bytes)
        .map_err(|e| format!("PositionedGraph artifact is not valid UTF-8: {e}"))?;
    load_positioned_graph(text)
}
