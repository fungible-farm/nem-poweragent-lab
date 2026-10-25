//! Structured events (FR-010) and a hash-chained audit log (SEC-008).
//!
//! `Bus::emit` appends to the audit log first and only then offers the event to subscribers with a
//! non-blocking send, ignoring dead ones. A dashboard is therefore an optional observer: it can
//! never block, fail or disable execution or audit (SEC-007, Gate 4).

use poweragent_policy::{Decision, DenyReason};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::{File, OpenOptions},
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    sync::mpsc::{sync_channel, Receiver, SyncSender, TrySendError},
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum EventKind {
    Authorized { backend: String, capabilities: usize },
    Denied { reason: String },
    /// A start the reconciler decided on. No sidecar runtime exists yet, so nothing is launched.
    SidecarPlanned { name: String },
    SidecarStarted { name: String },
    SidecarStopped { name: String },
    /// A running helper was stopped because the current policy no longer allows it.
    SidecarRevoked { name: String },
    Finished { outcome: String },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Event {
    pub task: String,
    #[serde(flatten)]
    pub kind: EventKind,
}

/// Events describing a policy decision, so every approval and denial leaves evidence.
pub fn decision_event(task: &str, d: &Decision) -> Event {
    let kind = match d {
        Decision::Run { backend, granted } => {
            EventKind::Authorized { backend: format!("{backend:?}").to_lowercase(), capabilities: granted.len() }
        }
        Decision::Deny { reason } => EventKind::Denied {
            reason: match reason {
                DenyReason::InvalidProfile { .. } => "invalid_profile",
                DenyReason::CapabilityNotAuthorized { .. } => "capability_not_authorized",
                DenyReason::ContainmentUnavailable => "containment_unavailable",
                DenyReason::NoPermittedBackend => "no_permitted_backend",
            }
            .to_string(),
        },
    };
    Event { task: task.to_string(), kind }
}

#[derive(Serialize, Deserialize)]
struct Line {
    seq: u64,
    prev: String,
    event: Event,
    hash: String,
}

const GENESIS: &str = "0000000000000000000000000000000000000000000000000000000000000000";

fn digest(seq: u64, prev: &str, event: &Event) -> String {
    let body = serde_json::to_string(event).expect("event serializes");
    let mut h = Sha256::new();
    h.update(format!("{seq}|{prev}|{body}"));
    h.finalize().iter().map(|b| format!("{b:02x}")).collect()
}

/// Append-only JSONL log; each line commits to the previous one.
pub struct AuditLog {
    path: PathBuf,
    file: File,
    seq: u64,
    last: String,
}

impl AuditLog {
    /// Open (or create) a log, resuming the chain from its verified tail.
    pub fn open(path: &Path) -> Result<Self, String> {
        let (seq, last) = if path.exists() { verify(path)? } else { (0, GENESIS.to_string()) };
        let file = OpenOptions::new().create(true).append(true).open(path).map_err(|e| e.to_string())?;
        Ok(AuditLog { path: path.to_path_buf(), file, seq, last })
    }
    pub fn path(&self) -> &Path {
        &self.path
    }
    pub fn append(&mut self, event: &Event) -> Result<(), String> {
        let seq = self.seq + 1;
        let hash = digest(seq, &self.last, event);
        let line = Line { seq, prev: self.last.clone(), event: event.clone(), hash: hash.clone() };
        let mut s = serde_json::to_string(&line).map_err(|e| e.to_string())?;
        s.push('\n');
        self.file.write_all(s.as_bytes()).and_then(|_| self.file.sync_data()).map_err(|e| e.to_string())?;
        self.seq = seq;
        self.last = hash;
        Ok(())
    }
}

/// Re-compute the chain. Returns (entries, tail hash), or the first line that does not verify.
pub fn verify(path: &Path) -> Result<(u64, String), String> {
    let f = File::open(path).map_err(|e| e.to_string())?;
    let (mut seq, mut last) = (0u64, GENESIS.to_string());
    for (i, l) in BufReader::new(f).lines().enumerate() {
        let l = l.map_err(|e| e.to_string())?;
        let line: Line = serde_json::from_str(&l).map_err(|e| format!("line {}: {e}", i + 1))?;
        if line.seq != seq + 1 || line.prev != last || line.hash != digest(line.seq, &line.prev, &line.event) {
            return Err(format!("line {}: audit chain broken", i + 1));
        }
        seq = line.seq;
        last = line.hash;
    }
    Ok((seq, last))
}

pub struct Bus {
    log: AuditLog,
    subscribers: Vec<SyncSender<Event>>,
}

impl Bus {
    pub fn new(log: AuditLog) -> Self {
        Bus { log, subscribers: vec![] }
    }
    /// A bounded, lossy view for a dashboard. If it is slow or dropped, events are skipped for it only.
    pub fn subscribe(&mut self, capacity: usize) -> Receiver<Event> {
        let (tx, rx) = sync_channel(capacity);
        self.subscribers.push(tx);
        rx
    }
    /// Audit first; failure to audit is returned so the caller can fail closed (SEC-008).
    pub fn emit(&mut self, event: Event) -> Result<(), String> {
        self.log.append(&event)?;
        self.subscribers.retain(|tx| match tx.try_send(event.clone()) {
            Ok(()) | Err(TrySendError::Full(_)) => true,
            Err(TrySendError::Disconnected(_)) => false,
        });
        Ok(())
    }
}

fn esc(s: &str) -> String {
    s.chars().map(|c| match c {
        '&' => "&amp;".into(), '<' => "&lt;".into(), '>' => "&gt;".into(),
        '"' => "&quot;".into(), '\'' => "&#39;".into(), c => c.to_string(),
    }).collect()
}

/// A self-contained, read-only HTML view of the log (ADR-003: presentation only). No script, no
/// external resource, strict CSP; every value is escaped. The chain is re-verified first and a
/// broken log is stated at the top, never silently rendered as good.
pub fn render_html(path: &Path) -> Result<String, String> {
    let status = match verify(path) {
        Ok((n, tail)) => format!("<p class=ok>Chain verified: {n} entries, tail {}</p>", esc(&tail[..16])),
        Err(e) => format!("<p class=bad>AUDIT CHAIN BROKEN: {}</p>", esc(&e)),
    };
    let mut rows = String::new();
    let f = File::open(path).map_err(|e| e.to_string())?;
    for l in BufReader::new(f).lines() {
        let l = l.map_err(|e| e.to_string())?;
        if let Ok(line) = serde_json::from_str::<Line>(&l) {
            let detail = serde_json::to_string(&line.event.kind).unwrap_or_default();
            rows += &format!("<tr><td>{}</td><td>{}</td><td>{}</td></tr>\n", line.seq, esc(&line.event.task), esc(&detail));
        }
    }
    Ok(format!(
        "<!doctype html><meta charset=utf-8><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">\
<title>PowerAgent audit</title><style>body{{font:14px system-ui;margin:2rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #888;padding:4px 8px;text-align:left}}.ok{{color:#060}}.bad{{color:#b00;font-weight:700}}</style>\
<h1>PowerAgent audit</h1>{status}<table><tr><th>#</th><th>Task</th><th>Event</th></tr>\n{rows}</table>"
    ))
}
