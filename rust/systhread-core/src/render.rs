use serde_json::Value;

const TILE_W: f64 = 120.0;
const TILE_H: f64 = 60.0;
const BOX_HEIGHT: f64 = 40.0;
const PADDING: f64 = 60.0;
const FONT_SIZE: f64 = 13.0;
const CHAR_WIDTH: f64 = FONT_SIZE * 0.6;
const GEN_RX: f64 = TILE_W * 0.28;
const GEN_RY: f64 = TILE_H * 0.28;
const XFMR_GLYPH_R: f64 = 4.0;
const BOW_HEIGHT: f64 = TILE_H;

const BACKGROUND: &str = "#0f172a";
const LABEL_FILL: &str = "#e2e8f0";
const TRANSMISSION_STROKE: &str = "#38bdf8";
const TRANSFORMER_STROKE: &str = "#f59e0b";
const ATTACHMENT_STROKE: &str = "#a78bfa";
const SEQUENCE_STROKE: &str = "#34d399";
const SEQUENCE_ARROW_LEN: f64 = 10.0;
const SEQUENCE_ARROW_WIDTH: f64 = 6.0;

#[derive(Clone, Copy)]
struct Point {
    x: f64,
    y: f64,
}

/// Escapes text for placement inside SVG/XML element content (not attribute values -- this
/// crate never places project-supplied text inside an attribute). Node labels come from
/// project-supplied instance YAML (`name` fields) and are otherwise interpolated unescaped,
/// which lets an unescaped `<`/`&` in a label corrupt the SVG's XML well-formedness or break
/// out of the enclosing `<text>` element entirely.
fn escape_xml_text(s: &str) -> String {
    s.replace('&', "&amp;").replace('<', "&lt;").replace('>', "&gt;")
}

fn fill_by_type(node_type: &str) -> &'static str {
    match node_type {
        "generic" => "#6b7280",
        "server" => "#2563eb",
        "database" => "#059669",
        "router" => "#d97706",
        "warehouse" => "#7c3aed",
        _ => "#6b7280",
    }
}

fn tile_center(col: f64, row: f64) -> Point {
    Point {
        x: (col - row) * TILE_W / 2.0,
        y: (col + row) * TILE_H / 2.0,
    }
}

fn box_faces(center: Point) -> (Vec<Point>, Vec<Point>, Vec<Point>) {
    let top_apex = Point { x: center.x, y: center.y - TILE_H / 2.0 };
    let right_apex = Point { x: center.x + TILE_W / 2.0, y: center.y };
    let bottom_apex = Point { x: center.x, y: center.y + TILE_H / 2.0 };
    let left_apex = Point { x: center.x - TILE_W / 2.0, y: center.y };
    let down = |p: Point| Point { x: p.x, y: p.y + BOX_HEIGHT };

    let top_face = vec![top_apex, right_apex, bottom_apex, left_apex];
    let left_face = vec![left_apex, bottom_apex, down(bottom_apex), down(left_apex)];
    let right_face = vec![right_apex, bottom_apex, down(bottom_apex), down(right_apex)];
    (top_face, left_face, right_face)
}

fn bar_face(center: Point) -> Vec<Point> {
    vec![
        Point { x: center.x, y: center.y - TILE_H / 2.0 },
        Point { x: center.x + TILE_W / 2.0, y: center.y },
        Point { x: center.x, y: center.y + TILE_H / 2.0 },
        Point { x: center.x - TILE_W / 2.0, y: center.y },
    ]
}

fn poly(points: &[Point], fill: &str, opacity: f64, stroke: &str, stroke_width: f64) -> String {
    let pts: Vec<String> = points.iter().map(|p| format!("{:.1},{:.1}", p.x, p.y)).collect();
    format!(
        "<polygon points=\"{}\" fill=\"{}\" fill-opacity=\"{:?}\" stroke=\"{}\" stroke-width=\"{}\"/>",
        pts.join(" "),
        fill,
        opacity,
        stroke,
        fmt_g(stroke_width)
    )
}

/// Rust's `Display` for `f64` (drops trailing `.0` for whole numbers, e.g. `1.0` -> `"1"`), which
/// happens to match Python's `{:g}` format only for this crate's actual stroke-width call sites
/// (fixed literals `1.0`/`1.5`/`3.0`) -- it is NOT a general port of Python's `%g`/`{:g}`
/// semantics (which switches to exponential notation for large magnitudes; this does not).
fn fmt_g(v: f64) -> String {
    let s = format!("{v}");
    s
}

fn edge_skips_node(from: &str, to: &str, positions_by_id: &std::collections::BTreeMap<String, (f64, f64)>) -> bool {
    let (Some(&a), Some(&b)) = (positions_by_id.get(from), positions_by_id.get(to)) else {
        return false;
    };
    if a.1 != b.1 {
        return false;
    }
    let (lo, hi) = if a.0 <= b.0 { (a.0, b.0) } else { (b.0, a.0) };
    positions_by_id.iter().any(|(nid, pos)| {
        nid != from && nid != to && pos.1 == a.1 && lo < pos.0 && pos.0 < hi
    })
}

fn quad_point(p0: Point, ctrl: Point, p1: Point, t: f64) -> Point {
    Point {
        x: (1.0 - t).powi(2) * p0.x + 2.0 * (1.0 - t) * t * ctrl.x + t.powi(2) * p1.x,
        y: (1.0 - t).powi(2) * p0.y + 2.0 * (1.0 - t) * t * ctrl.y + t.powi(2) * p1.y,
    }
}

fn edge_style(edge_type: &str, kind: Option<&str>) -> (&'static str, &'static str) {
    if edge_type == "attachment" {
        return (ATTACHMENT_STROKE, "stroke-width=\"1.5\" stroke-dasharray=\"1,3\" stroke-linecap=\"round\"");
    }
    if edge_type == "sequence" {
        return (SEQUENCE_STROKE, "stroke-width=\"3\" stroke-linecap=\"round\"");
    }
    if kind == Some("transformer") {
        return (TRANSFORMER_STROKE, "stroke-width=\"3\"");
    }
    (TRANSMISSION_STROKE, "stroke-width=\"3\"")
}

fn arrowhead(tip: Point, tail_direction: Point, fill: &str) -> String {
    let dx = tip.x - tail_direction.x;
    let dy = tip.y - tail_direction.y;
    let length = (dx * dx + dy * dy).sqrt();
    if length == 0.0 {
        return String::new();
    }
    let (ux, uy) = (dx / length, dy / length);
    let (px, py) = (-uy, ux);
    let base = Point { x: tip.x - ux * SEQUENCE_ARROW_LEN, y: tip.y - uy * SEQUENCE_ARROW_LEN };
    let left = Point { x: base.x + px * SEQUENCE_ARROW_WIDTH / 2.0, y: base.y + py * SEQUENCE_ARROW_WIDTH / 2.0 };
    let right = Point { x: base.x - px * SEQUENCE_ARROW_WIDTH / 2.0, y: base.y - py * SEQUENCE_ARROW_WIDTH / 2.0 };
    format!(
        "<polygon points=\"{:.1},{:.1} {:.1},{:.1} {:.1},{:.1}\" fill=\"{}\"/>",
        tip.x, tip.y, left.x, left.y, right.x, right.y, fill
    )
}

pub fn render_svg(spec: &Value) -> String {
    let nodes = spec["nodes"].as_array().cloned().unwrap_or_default();
    let edges = spec.get("edges").and_then(|e| e.as_array()).cloned().unwrap_or_default();

    let mut centers: std::collections::BTreeMap<String, Point> = std::collections::BTreeMap::new();
    let mut positions_by_id: std::collections::BTreeMap<String, (f64, f64)> = std::collections::BTreeMap::new();
    for n in &nodes {
        let id = n["id"].as_str().unwrap().to_string();
        let x = n["position"]["x"].as_f64().unwrap();
        let y = n["position"]["y"].as_f64().unwrap();
        centers.insert(id.clone(), tile_center(x, y));
        positions_by_id.insert(id, (x, y));
    }

    let mut node_body: Vec<String> = Vec::new();
    let mut all_points: Vec<Point> = Vec::new();

    for node in &nodes {
        let id = node["id"].as_str().unwrap();
        let x = node["position"]["x"].as_f64().unwrap();
        let y = node["position"]["y"].as_f64().unwrap();
        let center = tile_center(x, y);
        let node_type = node["type"].as_str().unwrap_or("generic");
        let fill = fill_by_type(node_type);
        let shape = node["shape"].as_str().unwrap_or("box");
        let label = node["label"].as_str().unwrap();

        node_body.push(format!("<g data-node-id=\"{id}\">"));
        let label_y: f64;
        match shape {
            "bar" => {
                let bar = bar_face(center);
                all_points.extend(&bar);
                node_body.push(poly(&bar, fill, 1.0, LABEL_FILL, 1.5));
                label_y = center.y + TILE_H / 2.0 + FONT_SIZE;
            }
            "circle" => {
                node_body.push(format!(
                    "<ellipse cx=\"{:.1}\" cy=\"{:.1}\" rx=\"{:.1}\" ry=\"{:.1}\" fill=\"{}\" stroke=\"{}\" stroke-width=\"1.5\"/>",
                    center.x, center.y, GEN_RX, GEN_RY, fill, LABEL_FILL
                ));
                node_body.push(format!(
                    "<text x=\"{:.1}\" y=\"{:.1}\" font-family=\"monospace\" font-weight=\"bold\" font-size=\"{:.0}\" fill=\"{}\" text-anchor=\"middle\">G</text>",
                    center.x, center.y + FONT_SIZE * 0.35, FONT_SIZE, LABEL_FILL
                ));
                all_points.push(Point { x: center.x - GEN_RX, y: center.y - GEN_RY });
                all_points.push(Point { x: center.x + GEN_RX, y: center.y + GEN_RY });
                label_y = center.y + GEN_RY + FONT_SIZE;
            }
            _ => {
                let (top_face, left_face, right_face) = box_faces(center);
                all_points.extend(&top_face);
                all_points.extend(&left_face);
                all_points.extend(&right_face);
                node_body.push(poly(&left_face, fill, 0.7, "#0f172a", 1.0));
                node_body.push(poly(&right_face, fill, 0.55, "#0f172a", 1.0));
                node_body.push(poly(&top_face, fill, 1.0, "#0f172a", 1.0));
                label_y = center.y + BOX_HEIGHT + TILE_H / 2.0 + FONT_SIZE;
            }
        }

        node_body.push(format!(
            "<text x=\"{:.1}\" y=\"{:.1}\" font-family=\"monospace\" font-size=\"{:.0}\" fill=\"{}\" text-anchor=\"middle\">{}</text>",
            center.x, label_y, FONT_SIZE, LABEL_FILL, escape_xml_text(label)
        ));
        node_body.push("</g>".to_string());
        all_points.push(Point { x: center.x - label.chars().count() as f64 * CHAR_WIDTH / 2.0, y: label_y });
        all_points.push(Point { x: center.x + label.chars().count() as f64 * CHAR_WIDTH / 2.0, y: label_y });
    }

    let mut edge_body: Vec<String> = Vec::new();
    for edge in &edges {
        let from = edge["from"].as_str().unwrap();
        let to = edge["to"].as_str().unwrap();
        let edge_type = edge["type"].as_str().unwrap_or("");
        let kind = edge.get("kind").and_then(|k| k.as_str());
        let a = centers[from];
        let b = centers[to];
        let (stroke, extra_attrs) = edge_style(edge_type, kind);

        let glyph_points: Vec<Point>;
        if edge_skips_node(from, to, &positions_by_id) {
            let ctrl = Point { x: (a.x + b.x) / 2.0, y: (a.y + b.y) / 2.0 - BOW_HEIGHT };
            all_points.push(ctrl);
            edge_body.push(format!(
                "<path d=\"M {:.1} {:.1} Q {:.1} {:.1} {:.1} {:.1}\" fill=\"none\" stroke=\"{}\" {}/>",
                a.x, a.y, ctrl.x, ctrl.y, b.x, b.y, stroke, extra_attrs
            ));
            glyph_points = [1.0 / 3.0, 2.0 / 3.0].iter().map(|&t| quad_point(a, ctrl, b, t)).collect();
        } else {
            edge_body.push(format!(
                "<line x1=\"{:.1}\" y1=\"{:.1}\" x2=\"{:.1}\" y2=\"{:.1}\" stroke=\"{}\" {}/>",
                a.x, a.y, b.x, b.y, stroke, extra_attrs
            ));
            glyph_points = [1.0 / 3.0, 2.0 / 3.0]
                .iter()
                .map(|&frac| Point { x: a.x + (b.x - a.x) * frac, y: a.y + (b.y - a.y) * frac })
                .collect();
        }
        if kind == Some("transformer") {
            for gp in &glyph_points {
                edge_body.push(format!(
                    "<circle cx=\"{:.1}\" cy=\"{:.1}\" r=\"{:.1}\" fill=\"{}\" stroke=\"{}\" stroke-width=\"2\"/>",
                    gp.x, gp.y, XFMR_GLYPH_R, BACKGROUND, stroke
                ));
            }
        }
        if edge_type == "sequence" {
            edge_body.push(arrowhead(b, a, stroke));
        }
    }

    let min_x = all_points.iter().map(|p| p.x).fold(f64::INFINITY, f64::min) - PADDING;
    let max_x = all_points.iter().map(|p| p.x).fold(f64::NEG_INFINITY, f64::max) + PADDING;
    let min_y = all_points.iter().map(|p| p.y).fold(f64::INFINITY, f64::min) - PADDING;
    let max_y = all_points.iter().map(|p| p.y).fold(f64::NEG_INFINITY, f64::max) + PADDING;
    let width = max_x - min_x;
    let height = max_y - min_y;

    let title = spec["title"].as_str().unwrap_or("");

    let mut svg: Vec<String> = vec![
        format!(
            "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"{:.1} {:.1} {:.1} {:.1}\" width=\"{:.0}\" height=\"{:.0}\">",
            min_x, min_y, width, height, width, height
        ),
        format!(
            "<rect x=\"{:.1}\" y=\"{:.1}\" width=\"{:.1}\" height=\"{:.1}\" fill=\"{}\"/>",
            min_x, min_y, width, height, BACKGROUND
        ),
        format!("<title>{title}</title>"),
    ];
    svg.extend(node_body);
    svg.extend(edge_body);
    svg.push("</svg>".to_string());
    svg.join("\n") + "\n"
}
