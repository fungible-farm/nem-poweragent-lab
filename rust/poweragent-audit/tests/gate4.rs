use poweragent_audit::*;
use poweragent_policy::{Backend, Decision, DenyReason};
use std::{fs, path::PathBuf};

fn tmp(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("poweragent-audit-{}-{name}", std::process::id()));
    let _ = fs::remove_file(&d);
    d
}
fn script(task: &str) -> Vec<Event> {
    vec![
        decision_event(task, &Decision::Run { backend: Backend::Mxc, granted: vec![] }),
        Event { task: task.into(), kind: EventKind::SidecarStarted { name: "pandapower".into() } },
        Event { task: task.into(), kind: EventKind::Finished { outcome: "exited(0)".into() } },
    ]
}

#[test]
fn same_audit_with_dashboard_on_off_and_killed_midway() {
    let (a, b, c) = (tmp("on"), tmp("off"), tmp("killed"));

    let mut on = Bus::new(AuditLog::open(&a).unwrap());
    let rx = on.subscribe(8);
    for e in script("t") { on.emit(e).unwrap(); }
    assert_eq!(rx.try_iter().count(), 3, "dashboard saw every event");

    let mut off = Bus::new(AuditLog::open(&b).unwrap());
    for e in script("t") { off.emit(e).unwrap(); }

    let mut killed = Bus::new(AuditLog::open(&c).unwrap());
    let rx = killed.subscribe(1);
    let mut it = script("t").into_iter();
    killed.emit(it.next().unwrap()).unwrap();
    drop(rx); // the dashboard dies mid-run
    for e in it { killed.emit(e).expect("execution and audit continue"); }

    let (na, ta) = verify(&a).unwrap();
    let (nb, tb) = verify(&b).unwrap();
    let (nc, tc) = verify(&c).unwrap();
    assert_eq!((na, nb, nc), (3, 3, 3));
    assert_eq!(ta, tb, "audit identical with dashboard on and off");
    assert_eq!(ta, tc, "audit identical when the dashboard is killed");
}

#[test]
fn slow_dashboard_cannot_block_execution() {
    let mut bus = Bus::new(AuditLog::open(&tmp("slow")).unwrap());
    let _never_read = bus.subscribe(1);
    for i in 0..100 {
        bus.emit(Event { task: format!("t{i}"), kind: EventKind::Finished { outcome: "ok".into() } }).unwrap();
    }
}

#[test]
fn tampering_with_the_log_is_detected() {
    let p = tmp("tamper");
    let mut bus = Bus::new(AuditLog::open(&p).unwrap());
    for e in script("t") { bus.emit(e).unwrap(); }
    assert!(verify(&p).is_ok());
    let text = fs::read_to_string(&p).unwrap().replace("pandapower", "powerfactory");
    fs::write(&p, text).unwrap();
    assert!(verify(&p).unwrap_err().contains("chain broken"));
    let removed: Vec<_> = fs::read_to_string(&p).unwrap().lines().skip(1).map(String::from).collect();
    fs::write(&p, removed.join("\n") + "\n").unwrap();
    assert!(verify(&p).is_err(), "deleting the first entry is detected");
}

#[test]
fn log_resumes_after_restart() {
    let p = tmp("resume");
    { let mut bus = Bus::new(AuditLog::open(&p).unwrap()); for e in script("t") { bus.emit(e).unwrap(); } }
    { let mut bus = Bus::new(AuditLog::open(&p).unwrap()); bus.emit(script("u").remove(0)).unwrap(); }
    assert_eq!(verify(&p).unwrap().0, 4);
}

#[test]
fn denials_leave_evidence() {
    let e = decision_event("t", &Decision::Deny { reason: DenyReason::ContainmentUnavailable });
    assert_eq!(e.kind, EventKind::Denied { reason: "containment_unavailable".into() });
}

#[test]
fn html_report_is_static_escaped_and_flags_a_broken_chain() {
    let p = tmp("html");
    let mut bus = Bus::new(AuditLog::open(&p).unwrap());
    bus.emit(Event { task: "<script>alert(1)</script>".into(), kind: EventKind::Finished { outcome: "a&b".into() } }).unwrap();
    let html = render_html(&p).unwrap();
    assert!(html.contains("Chain verified: 1 entries"));
    assert!(!html.contains("<script"), "no script element may be emitted");
    assert!(html.contains("&lt;script&gt;") && html.contains("a&amp;b"));
    assert!(html.contains("default-src 'none'"));
    fs::write(&p, fs::read_to_string(&p).unwrap().replace("a&b", "ok")).unwrap();
    assert!(render_html(&p).unwrap().contains("AUDIT CHAIN BROKEN"));
}
