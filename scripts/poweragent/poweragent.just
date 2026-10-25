# poweragent.just -- issue #54 build chain. Run from WSL:  just poweragent::chain
# One recipe per step; a failing step stops the chain with a non-zero exit and a reason.
# Windows facts are read through WSL interop (powershell.exe / vswhere.exe), not re-implemented.

set shell := ["bash", "-c"]

rust := justfile_directory() / "rust"
docs := justfile_directory() / "docs/poweragent"

# Every step in order.
chain: os-floor toolchain fetch test mxc-pin gate0 gate1 gate2-4 native e2e sidecars

# Windows build must meet MXC's processcontainer floor (docs/poweragent/mxc-os-floor.txt: "build min-ubr").
os-floor:
    #!/usr/bin/env bash
    set -euo pipefail
    read -r build ubr < <(powershell.exe -NoProfile -Command '$c = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion"; "$($c.CurrentBuild) $($c.UBR)"' | tr -d '\r')
    need=$(awk -v b="$build" '$1 == b { print $2 }' "{{docs}}/mxc-os-floor.txt")
    [[ -n "$need" ]] || { echo "FAIL: Windows build $build is not in mxc-os-floor.txt"; exit 1; }
    (( ubr >= need )) || { echo "FAIL: build $build.$ubr below MXC floor $build.$need"; exit 1; }
    echo "PASS: build $build.$ubr >= floor $build.$need"

# Tools the build needs: WSL side (cargo, bwrap, podman) and Windows MSVC Build Tools.
toolchain:
    #!/usr/bin/env bash
    set -euo pipefail
    for t in cargo bwrap podman; do command -v "$t" >/dev/null || { echo "FAIL: $t missing in WSL"; exit 1; }; done
    vswhere="/mnt/c/Program Files (x86)/Microsoft Visual Studio/Installer/vswhere.exe"
    [[ -x "$vswhere" ]] && "$vswhere" -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | grep -q . \
        || { echo "FAIL: MSVC Build Tools not installed on Windows"; exit 1; }
    echo "PASS"

# Fetch crates with network access, so the sandboxed test step needs none.
fetch:
    cd {{rust}} && cargo fetch --locked -q

# Gate 0 logic tests inside a bubblewrap sandbox (the MXC Linux backend primitive): read-only
# filesystem, no network, only target/ writable. Not a Windows-enforcement result.
test:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{rust}}"
    mkdir -p target
    bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --bind "$PWD/target" "$PWD/target" \
        --unshare-net --unshare-pid --die-with-parent \
        cargo test -p poweragent-policy -p poweragent-sidecar -p poweragent-audit -p poweragent-fallback -p poweragent-podman --locked --offline

# ADR-001: the mxc-sdk version must be recorded before anything builds against it.
mxc-pin:
    @test -f "{{docs}}/mxc-pin.json" && cat "{{docs}}/mxc-pin.json" && echo "PASS" \
        || { echo "FAIL: {{docs}}/mxc-pin.json missing -- record the mxc-sdk version"; exit 1; }

# Gate 0 on the real Windows host: the probe (pinned mxc-sdk) reports backends, and the fixture matrix
# must give: authorized fs-only -> run on mxc (exit 0); empty policy -> deny (3); unsupported net -> deny (3).
# Runs cargo.exe through WSL interop because only the Windows build can see processcontainer.
gate0:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{rust}}"
    cargo.exe build -q -p poweragent-probe
    probe=./target/debug/poweragent-probe.exe
    fx=../docs/poweragent/fixtures
    check() { # name profile policy want_exit want_text
        set +e; out=$($probe --profile "$fx/$2.json" --policy "$fx/$3.json" | tr -d ''); rc=$?; set -e
        [[ $rc -eq $4 ]] && grep -q "$5" <<<"$out" || { echo "FAIL: $1 (exit $rc, wanted $4 and '$5')"; echo "$out"; exit 1; }
        echo "PASS: $1"
    }
    check "authorized fs-only runs on mxc"  profile-fs  policy-allow 0 '"backend": "mxc"'
    check "empty policy denies"             profile-fs  policy-empty 3 'capability_not_authorized'
    check "unverified network fails closed" profile-net policy-allow 3 'containment_unavailable'
    echo "backends on this host:"; $probe | tr -d '' | grep -A4 '"backend"'

# Gate 1 on the real Windows host: a deterministic worker runs in processcontainer with read-only input,
# a single writable output dir, network denied and a timeout; adversarial tests must be denied by the OS.
# Output is saved to docs/poweragent/evidence/ so the run is auditable.
gate1:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{rust}}"
    log="{{docs}}/evidence/gate1-adversarial-$(date -u +%Y-%m-%d).txt"
    cargo.exe test -p poweragent-exec --test gate1 -- --nocapture --test-threads=1 2>&1 | tr -d '' | tee "$log"
    grep -q "test result: ok. 9 passed" "$log" || { echo "FAIL: Gate 1 tests did not all pass"; exit 1; }
    echo "PASS: Gate 1 (evidence: $log)"

# Gates 2-4 logic plus the integrated runner, on the real Windows host (the Linux copies run in `test`).
gate2-4:
    cd "{{rust}}" && cargo.exe test -q -p poweragent-sidecar -p poweragent-audit -p poweragent-fallback --test gate2 --test gate4 --test gate3_rules

# Gate 3 native half: windows-rs typed operation behind the same authorisation.
native:
    cd "{{rust}}" && cargo.exe test -q -p poweragent-fallback --test native_windows

# Section 9 happy path and denials end to end: probe -> decide -> sidecars -> MXC worker -> audit.
e2e:
    cd "{{rust}}" && cargo.exe build -q -p poweragent-exec -p poweragent && cargo.exe test -q -p poweragent --test e2e

# Phase 2 demo on the real host: one authorised contained run, one denial, and the HTML audit report.
demo:
    cd "{{rust}}" && cargo.exe build -q -p poweragent-exec -p poweragent && python3 "{{justfile_directory()}}/scripts/poweragent/demo.py"

# Real Podman sidecars (needs Podman and docker.io/library/alpine:3.20 locally; a missing prerequisite FAILS here):
# hardened lifecycle, then the full run with sidecars up during the MXC-contained worker and torn down after.
sidecars:
    cd "{{rust}}" && cargo.exe build -q -p poweragent-exec && POWERAGENT_REQUIRE_PODMAN=1 WSLENV=POWERAGENT_REQUIRE_PODMAN cargo.exe test -q -p poweragent-podman --test podman_real --test args && POWERAGENT_REQUIRE_PODMAN=1 WSLENV=POWERAGENT_REQUIRE_PODMAN cargo.exe test -q -p poweragent --test e2e_podman

# Pilot kit for IT teams: release build, checksums, docs, dependency inventory -> dist/*.zip (unsigned, lab use).
pack:
    cd "{{justfile_directory()}}" && python3 scripts/poweragent/pack.py

# Installer test suite (26 cases) against the newest dist/*.zip; run `pack` first. CurrentUser scope only; restores the user PATH.
installer-test:
    pwsh.exe -NoProfile -File "{{justfile_directory()}}/scripts/poweragent/kit/Test-Installer.ps1"
