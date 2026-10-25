# poweragent.just -- issue #54 build chain. Run from WSL:  just poweragent::chain
# One recipe per step; a failing step stops the chain with a non-zero exit and a reason.
# Windows facts are read through WSL interop (powershell.exe / vswhere.exe), not re-implemented.

set shell := ["bash", "-c"]

rust := justfile_directory() / "rust"
docs := justfile_directory() / "docs/poweragent"

# Every step in order.
chain: os-floor toolchain fetch test mxc-pin

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
        cargo test -p poweragent-policy --locked --offline

# ADR-001: the mxc-sdk version must be recorded before anything builds against it.
mxc-pin:
    @test -f "{{docs}}/mxc-pin.json" && cat "{{docs}}/mxc-pin.json" && echo "PASS" \
        || { echo "FAIL: {{docs}}/mxc-pin.json missing -- record the mxc-sdk version"; exit 1; }
