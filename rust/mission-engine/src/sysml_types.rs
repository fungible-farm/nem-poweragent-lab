//! Phase 1 -- the static type layer: `sysml-v2-parser` over Lab 6's real
//! SysML v2 model.
//!
//! PRD-0009 Phase 0b recommended `sysml-v2-parser` as primary and proved it
//! parses this exact file (3/3 on Lab 6's `.sysml` output). The same
//! `sysml_v2_parser::parse()` call Lab 8's 0b spike made is made here at
//! `Startup`, and the resulting [`RootNamespace`] is kept as a Bevy `Resource`
//! so `grid_entities` and `cim_trace` both read one parse, not three.

use bevy::prelude::*;
use sysml_v2_parser::{
    Expression, PackageBody, PackageBodyElement, PartUsage, PartUsageBody, PartUsageBodyElement,
    RootElement, RootNamespace,
};

/// The parsed Lab 6 grid model.
#[derive(Resource)]
pub struct SysmlModel {
    pub root: RootNamespace,
    /// The file that was parsed (for diagnostics/logging).
    pub source_path: std::path::PathBuf,
}

/// One `part <name> : <Type> { ... }` usage flattened out of the model, with
/// the string-valued attributes this lab cares about.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SysmlPart {
    pub name: String,
    /// `Bus`, `Generator`, or `Line` in Lab 6's model.
    pub type_name: String,
    pub cim_class_uri: Option<String>,
    /// Lab 6's `source` attribute, e.g.
    /// `"data/snemSA.m (pandapower bus index 1683)"`.
    pub source: Option<String>,
    pub from_bus: Option<String>,
    pub to_bus: Option<String>,
    pub bus: Option<String>,
}

fn string_attr(part: &PartUsage, wanted: &str) -> Option<String> {
    let PartUsageBody::Brace { elements } = &part.body else {
        return None;
    };
    for element in elements {
        // NOTE `Node<T>` derefs to `T`, and both `Node` and `AttributeUsage`
        // have a field literally called `value` -- `attr.value` resolves to
        // the Node's payload, so the attribute's own value clause is
        // `usage.value`. Naming the inner binding keeps that unambiguous.
        if let PartUsageBodyElement::AttributeUsage(attr) = &element.value {
            let usage = &attr.value;
            if usage.name == wanted
                && let Some(feature_value) = &usage.value
                && let Expression::LiteralString(s) = &feature_value.value.expression.value
            {
                return Some(s.clone());
            }
        }
    }
    None
}

fn collect_from_part(part: &PartUsage, out: &mut Vec<SysmlPart>) {
    // Lab 6 emits one outer `part gridTopology { ... }` whose body holds the
    // real instances; only the typed inner usages carry a cimClassUri.
    if !part.type_name.is_empty() {
        out.push(SysmlPart {
            name: part.name.clone(),
            type_name: part.type_name.clone(),
            cim_class_uri: string_attr(part, "cimClassUri"),
            source: string_attr(part, "source"),
            from_bus: string_attr(part, "fromBus"),
            to_bus: string_attr(part, "toBus"),
            bus: string_attr(part, "bus"),
        });
    }
    if let PartUsageBody::Brace { elements } = &part.body {
        for element in elements {
            if let PartUsageBodyElement::PartUsage(nested) = &element.value {
                collect_from_part(&nested.value, out);
            }
        }
    }
}

/// Walk the parsed model and return every typed `part` usage in source order.
pub fn collect_parts(root: &RootNamespace) -> Vec<SysmlPart> {
    let mut out = Vec::new();
    for element in &root.elements {
        let body = match &element.value {
            RootElement::Package(pkg) => &pkg.value.body,
            RootElement::Namespace(ns) => &ns.value.body,
            _ => continue,
        };
        if let PackageBody::Brace { elements } = body {
            for member in elements {
                if let PackageBodyElement::PartUsage(part) = &member.value {
                    collect_from_part(&part.value, &mut out);
                }
            }
        }
    }
    out
}

pub struct SysmlTypesPlugin;

impl Plugin for SysmlTypesPlugin {
    fn build(&self, app: &mut App) {
        let path = crate::paths::lab6_sysml();
        let src = std::fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("reading {}: {e}", path.display()));
        // Strict `parse()`, not `parse_for_editor()` -- this is a gate, not an
        // editor: a Lab 6 model that no longer parses must fail the mission
        // build loudly rather than silently modelling half a grid.
        let root = sysml_v2_parser::parse(&src)
            .unwrap_or_else(|e| panic!("sysml_v2_parser::parse({}) failed: {e}", path.display()));
        app.insert_resource(SysmlModel {
            root,
            source_path: path,
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_lab6_model_and_finds_the_cluster() {
        let src = std::fs::read_to_string(crate::paths::lab6_sysml()).unwrap();
        let root = sysml_v2_parser::parse(&src).expect("Lab 6's .sysml parses strictly");
        let parts = collect_parts(&root);
        let buses: Vec<_> = parts.iter().filter(|p| p.type_name == "Bus").collect();
        let gens: Vec<_> = parts.iter().filter(|p| p.type_name == "Generator").collect();
        let lines: Vec<_> = parts.iter().filter(|p| p.type_name == "Line").collect();
        assert_eq!(buses.len(), 15);
        assert_eq!(gens.len(), 5);
        assert_eq!(lines.len(), 19);
        assert_eq!(buses[0].name, "bus_4052");
        assert_eq!(
            buses[0].cim_class_uri.as_deref(),
            Some("http://iec.ch/TC57/2013/CIM-schema-cim16#TopologicalNode")
        );
    }
}
