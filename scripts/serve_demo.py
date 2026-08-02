#!/usr/bin/env python3
"""Serve the local demo dashboard (browser-based, WSL3/Windows capable).

`just demo` runs this: a small stdlib HTTP server serving the repo root so
your Windows browser (or any browser on the LAN) can open `demo_index.html`
-- a single page embedding every lab visualization (videos, the 3-channel
audio, charts). No X server, no WSLg dependency, no new packages: it is the
most robust way to land the demo on the user's screen (vs. GNOME/GTK over
ssh -X via WSLg, or a future Slint/Rust native app on the oxidation roadmap).

Usage:
    python3 scripts/serve_demo.py [--port N] [--open]

Prints the URL. With --open, attempts to launch the default browser
(explorer.exe on WSL hosts; xdg-open elsewhere); over a plain SSH session it
just prints the URL for the operator to open in their Windows browser, or an
`ssh -L` tunnel hint.

The server runs until Ctrl-C; `just demo-stop` kills it.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
DEFAULT_PORT: int = 8008
# The dashboard page lives in scripts/ next to this server; the server serves
# REPO_ROOT, so the page URL is the repo-relative path.
INDEX_PAGE: str = "scripts/demo_index.html"


def lan_ip() -> str:
    """Best-effort LAN address (UDP-connect trick; no packets are sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def try_open_browser(url: str) -> None:
    """Launch the platform default browser if possible (non-fatal)."""
    explorer = shutil.which("explorer.exe")
    if explorer is not None:  # WSL host -> Windows default browser
        subprocess.Popen([explorer, url])
        return
    if shutil.which("xdg-open") is not None:  # has a local display
        subprocess.Popen(["xdg-open", url])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="attempt to open the browser")
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    handler = lambda *a, **k: SimpleHTTPRequestHandler(*a, directory=str(REPO_ROOT), **k)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), handler)
    url = f"http://{lan_ip()}:{args.port}/{INDEX_PAGE}"

    print(f"[demo] serving {REPO_ROOT}")
    print(f"[demo] open in your Windows/WSL browser: {url}")
    print(f"[demo] or tunnel:  ssh -L {args.port}:localhost:{args.port} fung1  "
          f"then http://localhost:{args.port}/{INDEX_PAGE}")
    print(f"[demo] stop with:  just demo-stop")

    if args.open:
        try_open_browser(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[demo] stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
