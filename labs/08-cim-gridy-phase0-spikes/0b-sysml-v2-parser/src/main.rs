//! PRD-0009 Phase 0b spike: does either native-Rust SysML v2 parser
//! (`sysml-v2-parser` or `syster-base`) actually parse (a) real GfSE
//! `SysML-v2-Models` fixtures, and (b) this repo's own Lab 6 `.sysml` output?
//!
//! Not a demo -- this prints real pass/fail per file plus the actual error
//! text so the README can quote it verbatim.

use std::fs;
use std::path::{Path, PathBuf};

fn find_sysml_files(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else {
        return;
    };
    let mut entries: Vec<_> = entries.flatten().collect();
    entries.sort_by_key(|e| e.path());
    for entry in entries {
        let path = entry.path();
        if path.is_dir() {
            find_sysml_files(&path, out);
        } else if path.extension().and_then(|e| e.to_str()) == Some("sysml") {
            out.push(path);
        }
    }
}

struct Outcome {
    ok: bool,
    detail: String,
}

fn try_sysml_v2_parser(src: &str) -> Outcome {
    match sysml_v2_parser::parse(src) {
        Ok(_root) => Outcome {
            ok: true,
            detail: "parse() OK (strict)".to_string(),
        },
        Err(e) => {
            // Also try the resilient editor entry point to see how far it gets.
            let editor_result = sysml_v2_parser::parse_for_editor(src);
            Outcome {
                ok: false,
                detail: format!(
                    "parse() FAILED: {e}\n        parse_for_editor(): {} diagnostic(s), first: {:?}",
                    editor_result.errors.len(),
                    editor_result.errors.first()
                ),
            }
        }
    }
}

fn try_syster_base(src: &str) -> Outcome {
    let parsed = syster::parser::parse_sysml(src);
    if parsed.errors.is_empty() {
        Outcome {
            ok: true,
            detail: "parse_sysml() OK, 0 errors".to_string(),
        }
    } else {
        let first_few: Vec<String> = parsed
            .errors
            .iter()
            .take(3)
            .map(|e| format!("{e:?}"))
            .collect();
        Outcome {
            ok: false,
            detail: format!(
                "parse_sysml() {} error(s). First up to 3:\n        {}",
                parsed.errors.len(),
                first_few.join("\n        ")
            ),
        }
    }
}

fn main() {
    let fixtures_dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("fixtures");
    let mut files = Vec::new();
    find_sysml_files(&fixtures_dir, &mut files);
    files.sort();

    println!("Found {} .sysml files under {:?}\n", files.len(), fixtures_dir);

    let mut sysml_v2_parser_pass = 0;
    let mut sysml_v2_parser_fail = 0;
    let mut syster_base_pass = 0;
    let mut syster_base_fail = 0;

    for path in &files {
        let rel = path.strip_prefix(&fixtures_dir).unwrap_or(path);
        let src = match fs::read_to_string(path) {
            Ok(s) => s,
            Err(e) => {
                println!("=== {} ===\n  READ ERROR: {e}\n", rel.display());
                continue;
            }
        };

        println!("=== {} ({} bytes) ===", rel.display(), src.len());

        let a = try_sysml_v2_parser(&src);
        println!(
            "  sysml-v2-parser : {} -- {}",
            if a.ok { "PASS" } else { "FAIL" },
            a.detail
        );
        if a.ok {
            sysml_v2_parser_pass += 1;
        } else {
            sysml_v2_parser_fail += 1;
        }

        let b = try_syster_base(&src);
        println!(
            "  syster-base     : {} -- {}",
            if b.ok { "PASS" } else { "FAIL" },
            b.detail
        );
        if b.ok {
            syster_base_pass += 1;
        } else {
            syster_base_fail += 1;
        }

        println!();
    }

    println!("=== SUMMARY ===");
    println!(
        "sysml-v2-parser : {sysml_v2_parser_pass} pass / {} total ({sysml_v2_parser_fail} fail)",
        sysml_v2_parser_pass + sysml_v2_parser_fail
    );
    println!(
        "syster-base     : {syster_base_pass} pass / {} total ({syster_base_fail} fail)",
        syster_base_pass + syster_base_fail
    );
}
