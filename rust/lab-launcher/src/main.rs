//! Terminal launcher menu for the nem-poweragent-lab labs (issue #18).
//!
//! Not a new framework: this lists each lab's number/name/one-line
//! description (titles taken verbatim from each lab's own README.md) and,
//! on Enter, shells out to that lab's own already-existing `just` recipe --
//! the same command a contributor would type by hand. The launcher owns
//! discovery/dispatch only; each lab's run/check interface is unchanged.

use std::io;
use std::process::Command;

use crossterm::event::{self, Event, KeyCode, KeyEventKind};
use crossterm::terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen};
use crossterm::execute;
use ratatui::backend::CrosstermBackend;
use ratatui::layout::{Constraint, Direction, Layout};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, ListState, Paragraph};
use ratatui::Terminal;

struct Lab {
    number: &'static str,
    title: &'static str,
    description: &'static str,
    /// The `just` recipe this entry runs. Lab 8 has no run/demo step of its
    /// own (its README calls the spikes "throwaway", not a repeatable
    /// walkthrough) so it only offers its check gate, same as the others.
    recipe: &'static str,
}

const LABS: &[Lab] = &[
    Lab {
        number: "1",
        title: "Simple — Load-Flow Parameter Fit",
        description: "Fit a pandapower model to one real SCADA reading.",
        recipe: "lab1",
    },
    Lab {
        number: "2",
        title: "Medium — Interconnection / Asset-Provisioning Screening",
        description: "N-1 contingency screening + pypowsybl cross-check before a new connection.",
        recipe: "lab2",
    },
    Lab {
        number: "3",
        title: "Advanced — Multi-Provider Bake-off",
        description: "Re-runnable, diffable solver/provider scorecard instead of an anecdote.",
        recipe: "lab3",
    },
    Lab {
        number: "4",
        title: "Real AEMO Data — Digital-Twin Reconciliation & Constraint Literacy",
        description: "One real NEMWEB dispatch day reconciled against the model.",
        recipe: "lab4",
    },
    Lab {
        number: "5",
        title: "SPARTAN Chaos-Net — Transient Streams via DPsim + VILLASnode",
        description: "EMT-timestep transient stream, grid-forming stabilizer, VILLASnode.",
        recipe: "lab5",
    },
    Lab {
        number: "6",
        title: "SysML v2 Digital-Thread MVP",
        description: "LinkML -> SysML v2 -> iso-IR pipeline, three tracks, chained end to end.",
        recipe: "lab6-demo",
    },
    Lab {
        number: "7",
        title: "Rust FFT/COMTRADE Detector — a Generate/Detect Testbench",
        description: "Python writes a real COMTRADE file; a Rust FFT detector reads it back.",
        recipe: "check-lab7",
    },
    Lab {
        number: "8",
        title: "cim-gridy Phase 0 — real-tool spikes",
        description: "Grid2Op, SysML v2 parsers, sysand, ufo-types+scryer-prolog, OperatorFabric vs. Bevy.",
        recipe: "check-lab8",
    },
];

fn run_recipe(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>, recipe: &str) -> io::Result<()> {
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    println!("\n$ just {recipe}\n");
    let status = Command::new("just").arg(recipe).status();
    match status {
        Ok(s) if s.success() => println!("\n-- just {recipe} exited 0 --"),
        Ok(s) => println!("\n-- just {recipe} exited {s} --"),
        Err(e) => println!("\n-- failed to run `just {recipe}`: {e} --"),
    }
    println!("Press Enter to return to the launcher.");
    let mut discard = String::new();
    io::stdin().read_line(&mut discard)?;
    enable_raw_mode()?;
    execute!(terminal.backend_mut(), EnterAlternateScreen)?;
    terminal.clear()
}

fn main() -> io::Result<()> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut state = ListState::default();
    state.select(Some(0));

    let result = (|| -> io::Result<()> {
        loop {
            terminal.draw(|f| {
                let chunks = Layout::default()
                    .direction(Direction::Vertical)
                    .constraints([Constraint::Min(3), Constraint::Length(1)])
                    .split(f.area());

                let items: Vec<ListItem> = LABS
                    .iter()
                    .map(|lab| {
                        ListItem::new(Line::from(vec![
                            Span::styled(
                                format!("  {:>2}. ", lab.number),
                                Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
                            ),
                            Span::styled(lab.title, Style::default().add_modifier(Modifier::BOLD)),
                            Span::raw("  -- "),
                            Span::styled(lab.description, Style::default().fg(Color::DarkGray)),
                        ]))
                    })
                    .collect();

                let list = List::new(items)
                    .block(
                        Block::default()
                            .borders(Borders::ALL)
                            .title(" nem-poweragent-lab -- lab launcher (issue #18) "),
                    )
                    .highlight_style(Style::default().bg(Color::Blue).add_modifier(Modifier::BOLD))
                    .highlight_symbol("> ");

                f.render_stateful_widget(list, chunks[0], &mut state);

                let help = Paragraph::new(Line::from(
                    "j/k or ↑/↓ move -- Enter runs `just <recipe>` -- q quits",
                ))
                .style(Style::default().fg(Color::DarkGray));
                f.render_widget(help, chunks[1]);
            })?;

            if event::poll(std::time::Duration::from_millis(200))? {
                if let Event::Key(key) = event::read()? {
                    if key.kind != KeyEventKind::Press {
                        continue;
                    }
                    match key.code {
                        KeyCode::Char('q') | KeyCode::Esc => break,
                        KeyCode::Down | KeyCode::Char('j') => {
                            let i = state.selected().unwrap_or(0);
                            state.select(Some((i + 1).min(LABS.len() - 1)));
                        }
                        KeyCode::Up | KeyCode::Char('k') => {
                            let i = state.selected().unwrap_or(0);
                            state.select(Some(i.saturating_sub(1)));
                        }
                        KeyCode::Enter => {
                            if let Some(i) = state.selected() {
                                run_recipe(&mut terminal, LABS[i].recipe)?;
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
        Ok(())
    })();

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    result
}
