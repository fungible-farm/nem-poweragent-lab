mod track;

use clap::{Parser, Subcommand};
use std::path::PathBuf;
use track::Track;

#[derive(Parser)]
#[command(name = "systhread", version, about = "SysML v2 digital-thread tooling (systhread-core Phase 1 CLI)")]
struct Cli {
    /// Run as an MCP server over stdio transport instead of a CLI subcommand.
    #[arg(long)]
    stdio: bool,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Generate the .sysml text for one track and validate it.
    Check {
        #[arg(long, value_enum)]
        track: Track,
        path: PathBuf,
    },
    /// Generate, validate, translate to iso-IR, and render SVG + a ledgrrr manifest.
    Render {
        #[arg(long, value_enum)]
        track: Track,
        path: PathBuf,
        #[arg(long)]
        out: PathBuf,
    },
    /// Interactive model explorer (FR7 — ships in Phase 3, not yet implemented).
    Explore,
    /// Per-commit drift check (FR10 — ships in Phase 4, not yet implemented).
    Drift,
}

fn main() -> std::process::ExitCode {
    let cli = Cli::parse();

    if cli.stdio {
        todo!("Task 4 wires this to the MCP stdio server");
    }

    match cli.command {
        Some(Commands::Check { .. }) => todo!("Task 2"),
        Some(Commands::Render { .. }) => todo!("Task 3"),
        Some(Commands::Explore) => todo!("Task 9"),
        Some(Commands::Drift) => todo!("Task 9"),
        None => {
            eprintln!("systhread: no command given (try --help)");
            std::process::ExitCode::FAILURE
        }
    }
}
