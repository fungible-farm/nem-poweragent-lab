mod common;
use common::fixture_path;
use serde_json::json;
use systhread_core::instances::{load_digital_thread, load_grid, load_pipeline};
use systhread_core::iso_ir::{build_digital_thread_iso_ir, build_grid_iso_ir, build_pipeline_iso_ir};
use systhread_core::render::render_svg;

#[test]
fn digital_thread_svg_matches_fixture_byte_identical() {
    let inst = load_digital_thread(&fixture_path("schema/digital_thread_instances.yaml"));
    let got = render_svg(&build_digital_thread_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_digital_thread.svg")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn grid_svg_matches_fixture_byte_identical() {
    let inst = load_grid(&fixture_path("schema/grid_instances.yaml"));
    let got = render_svg(&build_grid_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_grid_topology.svg")).unwrap();
    assert_eq!(got, expected);
}

#[test]
fn pipeline_svg_matches_fixture_byte_identical() {
    let inst = load_pipeline(&fixture_path("schema/pipeline_phases_instances.yaml"));
    let got = render_svg(&build_pipeline_iso_ir(&inst));
    let expected = std::fs::read_to_string(fixture_path("expected/expected_pipeline_phases.svg")).unwrap();
    assert_eq!(got, expected);
}

// Regression test for a real bug (nem-poweragent-lab#37): a project-supplied instance name
// containing XML-significant characters was interpolated unescaped into the SVG's <text>
// content, corrupting the document's XML well-formedness and permitting a crafted label to
// break out of the enclosing <text> element entirely. None of the three committed fixture
// tracks above exercise this path, since none of their real labels contain `<`/`>`/`&`.
#[test]
fn node_label_is_escaped_in_svg_text_content() {
    let spec = json!({
        "title": "Test",
        "type": "generic",
        "nodes": [{
            "id": "n1",
            "label": "</text><script>alert(1)</script><text>A & B <C>",
            "type": "generic",
            "shape": "box",
            "position": { "x": 0, "y": 0 }
        }],
        "edges": []
    });

    let svg = render_svg(&spec);

    assert!(
        svg.contains("A &amp; B &lt;C&gt;"),
        "expected the escaped label text in the SVG, got:\n{svg}"
    );
    assert!(
        !svg.contains("<script>"),
        "unescaped label broke out of its <text> element:\n{svg}"
    );
    assert!(
        !svg.contains("</text><script>"),
        "unescaped label was not contained inside a single <text>...</text> element:\n{svg}"
    );
}
