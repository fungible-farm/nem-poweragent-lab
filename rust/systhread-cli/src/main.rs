mod commands;
mod mcp;
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

#[tokio::main]
async fn main() -> std::process::ExitCode {
    let cli = Cli::parse();

    if cli.stdio {
        return match mcp::run_stdio().await {
            Ok(()) => std::process::ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("systhread --stdio: {e}");
                std::process::ExitCode::FAILURE
            }
        };
    }

    match cli.command {
        Some(Commands::Check { track, path }) => match commands::check::run(track, &path) {
            Ok(()) => std::process::ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("systhread check: {e}");
                std::process::ExitCode::FAILURE
            }
        },
        Some(Commands::Render { track, path, out }) => match commands::render::run(track, &path, &out) {
            Ok(paths) => {
                for p in paths {
                    println!("wrote {}", p.display());
                }
                std::process::ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("systhread render: {e}");
                std::process::ExitCode::FAILURE
            }
        },
        Some(Commands::Explore) => todo!("Task 9"),
        Some(Commands::Drift) => todo!("Task 9"),
        None => {
            eprintln!("systhread: no command given (try --help)");
            std::process::ExitCode::FAILURE
        }
    }
}
