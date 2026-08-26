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
