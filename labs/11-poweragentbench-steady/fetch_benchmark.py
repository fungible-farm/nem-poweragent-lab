"""Fetch this lab's pinned PowerAgentBench checkout and verify its source hashes.

Levels 1-2 have no root licence at this pin. Use as MIT is the user's recorded
2026-10-23 assumption, not an upstream licence grant; see README.md. Nothing
from upstream is vendored. This stdlib helper is independent of other labs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

LAB: Path = Path(__file__).resolve().parent
CHECKOUT: Path = LAB.parents[1] / "data" / "poweragentbench"
EXPECTED: Path = LAB / "expected_sources.json"


def git(*arguments: str) -> str:
    """Run git in the dedicated checkout; preserve failures as nonzero exits."""
    return subprocess.run(["git", *arguments], cwd=CHECKOUT, check=True,
                          capture_output=True, text=True).stdout.strip()


def verify(expected: dict[str, Any]) -> list[str]:
    """Return mismatches against the pinned commit and every recorded file hash."""
    head = git("rev-parse", "HEAD")
    problems = [] if head == expected["commit"] else [f"HEAD is {head}, expected {expected['commit']}"]
    for relative, digest in expected["sha256"].items():
        path = CHECKOUT / relative
        if not path.is_file():
            problems.append(f"missing {relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"changed {relative}")
    return problems


def main() -> int:
    """Fetch the committed pin when necessary, then fail on any source mismatch."""
    expected = json.loads(EXPECTED.read_text())
    if not (CHECKOUT / ".git").is_dir():
        CHECKOUT.mkdir(parents=True, exist_ok=True)
        git("init", "--quiet")
        git("remote", "add", "origin", expected["upstream"])
    head = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"],
                          cwd=CHECKOUT, capture_output=True, text=True)
    if head.returncode or head.stdout.strip() != expected["commit"]:
        git("fetch", "--quiet", "--depth", "1", "origin", expected["commit"])
        git("checkout", "--quiet", "--detach", "FETCH_HEAD")
    problems = verify(expected)
    for problem in problems:
        print(f"FAIL {problem}", file=sys.stderr)
    if not problems:
        print(f"PASS PowerAgentBench {expected['commit'][:12]}: {len(expected['sha256'])} pinned files match")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
