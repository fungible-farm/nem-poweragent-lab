//! Fixed worker executed inside the container. Prints `OK ...` or `DENIED: <os error>` on stdout;
//! exits 0 on success and 1 on denial, so the host can assert on both.
use std::{
    env, fs,
    io::Write,
    net::{SocketAddr, TcpStream},
    process::ExitCode,
    thread,
    time::Duration,
};

fn report<T>(r: std::io::Result<T>, what: &str) -> ExitCode {
    match r {
        Ok(_) => {
            println!("OK {what}");
            ExitCode::SUCCESS
        }
        Err(e) => {
            println!("DENIED: {what}: {e}");
            ExitCode::from(1)
        }
    }
}

fn main() -> ExitCode {
    let a: Vec<String> = env::args().skip(1).collect();
    match a.iter().map(String::as_str).collect::<Vec<_>>().as_slice() {
        ["sum", input, output] => match fs::read(input) {
            Ok(b) => {
                let s: u64 = b.iter().map(|&x| x as u64).sum();
                report(fs::write(output, s.to_string()), "sum")
            }
            Err(e) => {
                println!("DENIED: read input: {e}");
                ExitCode::from(1)
            }
        },
        ["try-read", p] => report(fs::read(p), "read"),
        ["try-write", p] => report(fs::File::create(p).and_then(|mut f| f.write_all(b"x")), "write"),
        ["try-connect", addr] => match addr.parse::<SocketAddr>() {
            Ok(sa) => report(TcpStream::connect_timeout(&sa, Duration::from_secs(3)), "connect"),
            Err(e) => {
                println!("bad addr: {e}");
                ExitCode::from(2)
            }
        },
        ["sleep", s] => {
            thread::sleep(Duration::from_secs(s.parse().unwrap_or(0)));
            ExitCode::SUCCESS
        }
        _ => {
            eprintln!("usage: sum IN OUT | try-read P | try-write P | try-connect ADDR | sleep S");
            ExitCode::from(2)
        }
    }
}
