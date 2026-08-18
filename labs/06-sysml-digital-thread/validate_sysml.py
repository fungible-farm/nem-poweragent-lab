"""Syntax gate for the .sysml text `generate_sysml.py` produces -- a real, named structural
stand-in for the normative SysML v2 grammar, not the normative grammar itself. See this lab's
README "Design notes" for the full write-up; short version:

Real paths to the normative parser were tried and timeboxed out on 2026-08-18:

1. `gorenje/sysmlv2-jupyter-docker`'s `Dockerfile.api` -- a real, working community container,
   but it builds `Systems-Modeling/SysML-v2-API-Services` via SBT/Scala/Play against a PostgreSQL
   backend, pinned to release `2023-02` (three years stale against this repo's clock), and needs a
   3-container compose stack (API + Postgres + Jupyter) for what this gate only needs as a single
   CLI check.
2. The official `Systems-Modeling/SysML-v2-Pilot-Implementation` repo's README.adoc only documents
   an Eclipse Modeling Tools IDE install -- but its `.github/workflows/build.yml` proves a real
   headless path exists: `./mvnw -B clean verify --file pom.xml` on JDK 21, no IDE. This host's
   system Java is 17; a `ghcr.io/graalvm/graalvm-community:21` podman container (confirmed
   `java -version` clean) removes that blocker with zero build changes. Scoping the Tycho reactor
   to just `org.omg.sysml.interactive` (`-pl org.omg.sysml.interactive -am`, skipping the
   `.editor`/`.edit`/`.plantuml`/`.jupyter.*` UI-only modules) got real progress: pom parsing,
   plugin resolution, and the reactor's first module build all ran cleanly. It then failed on a
   different, more specific problem: `com.sensmetry:sysand-maven-plugin:0.1.0-rc.1`'s `build-kpar`
   goal throws `UnsatisfiedLinkError: Native library resource not found2: linux-x86_64/sysand.so`
   -- confirmed NOT an architecture mismatch (`uname -m` is `x86_64` on both host and container).
   This is a packaging bug in a pre-1.0 (`-rc.1`) native-JNI Maven plugin from Sensmetry (the same
   company behind Syside, see the lab README) that the official build's own bootstrap step depends
   on -- a third-party defect outside this repo, not an environment mismatch on our end. Worth
   revisiting once `sysand-maven-plugin` ships a fixed release.

Neither path is "one dependency, ships in a day" territory today. This stand-in instead checks exactly the
grammar subset `generate_sysml.py` actually emits (`package`/`part def`/`part`/`attribute`,
Part/containment only -- no Port/Flow, matching this MVP's own scope cut) line by line, reporting
real line/column errors on the first line that doesn't match an allowed shape or on unbalanced
braces. It is not a general SysML v2 parser and does not claim to be -- a future phase revisiting
either real path above (a newer community image, or a CI-friendly headless build if one appears
upstream) would replace this file's `_check_lines()` function, not the rest of this pipeline.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Final, NamedTuple

LAB_DIR: Final[Path] = Path(__file__).resolve().parent

# One compiled pattern per allowed line shape. Order doesn't matter -- a line is valid if it
# matches ANY of these (after stripping trailing whitespace), invalid otherwise.
_IDENT: Final[str] = r"[A-Za-z_][A-Za-z0-9_]*"
_STRING: Final[str] = r'"(?:[^"\\]|\\.)*"'
_NUMBER: Final[str] = r"-?\d+(?:\.\d+)?"
PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"^package " + _IDENT + r" \{$"),
    re.compile(r"^part def " + _IDENT + r" \{$"),
    re.compile(r"^part " + _IDENT + r"(?: : " + _IDENT + r")? \{$"),
    re.compile(r"^attribute " + _IDENT + r" : " + _IDENT + r";$"),
    re.compile(r"^attribute " + _IDENT + r" = (?:" + _STRING + r"|" + _NUMBER + r");$"),
    re.compile(r"^\}$"),
    re.compile(r"^//.*$"),
    re.compile(r"^$"),
]


class SyntaxError_(NamedTuple):
    line: int
    column: int
    message: str


def _check_lines(text: str) -> SyntaxError_ | None:
    """Returns the first syntax error found, or None if the text is clean. Real line/column
    numbers, 1-indexed, matching how an editor or a real compiler would report them."""
    depth = 0
    open_stack: list[tuple[int, int]] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if not any(p.match(stripped) for p in PATTERNS):
            return SyntaxError_(lineno, indent + 1, f"line does not match any known statement shape: {stripped!r}")

        if stripped.endswith("{"):
            depth += 1
            open_stack.append((lineno, indent + 1))
        elif stripped == "}":
            if depth == 0:
                return SyntaxError_(lineno, indent + 1, "unexpected closing brace, nothing open")
            depth -= 1
            open_stack.pop()

    if depth != 0:
        bad_line, bad_col = open_stack[-1]
        return SyntaxError_(bad_line, bad_col, "unterminated block: '{' here is never closed")
    return None


def validate(path: Path) -> bool:
    text = path.read_text()
    err = _check_lines(text)
    if err is None:
        print(f"OK: {path} -- {len(text.splitlines())} lines, structurally clean")
        return True
    print(f"FAIL: {path}:{err.line}:{err.column}: {err.message}")
    return False


FIXTURES: Final[list[Path]] = [
    LAB_DIR / "fixtures" / "expected_digital_thread.sysml",
    LAB_DIR / "fixtures" / "expected_grid_topology.sysml",
]


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--step":
        # `--step check`: validate the committed fixtures (both tracks) -- matches this repo's
        # per-lab `--step check` convention. No `--step run` exists for this gate: there is
        # nothing to regenerate, only something to check.
        paths = FIXTURES
    elif args:
        paths = [Path(p) for p in args]
    else:
        print("usage: validate_sysml.py <path-to-.sysml-file> [<path> ...]  |  validate_sysml.py --step check")
        sys.exit(2)
    ok = all(validate(p) for p in paths)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
