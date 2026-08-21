"""pytest wrapper around Lab 6's pipeline scripts -- subprocess-driven, matching
labs/02-medium-interconnection-screening/test_lab2.py's pattern. Never reimplements the generator/
translator/renderer logic; only drives each script's own --step check gate and asserts on its
stdout, the same discipline every other lab's test file follows. One additional test
(`test_demo_script_runs_end_to_end_and_regenerates_every_artifact`) runs the real chained pipeline
(`scripts/demo_lab6.sh`) instead of a single script's gate, proving the whole thing works together,
not just each stage in isolation."""

import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
REPO_ROOT = LAB_DIR.parent.parent
DEMO_SCRIPT = REPO_ROOT / "scripts" / "demo_lab6.sh"
OUTPUT_DIR = LAB_DIR / "output"
TRACKS = ["digital-thread", "grid", "pipeline"]
DEMO_OUTPUTS = [
    "digital_thread.sysml",
    "digital_thread_iso_ir.json",
    "digital_thread.svg",
    "digital_thread_sbom.json",
    "grid_topology.sysml",
    "grid_topology_iso_ir.json",
    "grid_topology.svg",
    "pipeline_phases.sysml",
    "pipeline_phases_iso_ir.json",
    "pipeline_phases.svg",
]


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LAB_DIR / script), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def test_k8s_fixture_matches_real_kube_manifests():
    result = _run("build_k8s_fixture.py", "--step", "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_grid_instances_matches_real_snemsa_case():
    result = _run("build_grid_instances.py", "--step", "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_generated_sysml_matches_fixture_all_tracks():
    for track in TRACKS:
        result = _run("generate_sysml.py", "--track", track, "--step", "check")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "MATCH" in result.stdout


def test_grid_topology_carries_cim_class_uri_for_every_kind():
    """PRD-0007: the generated grid .sysml must carry a real CIM16 class URI for at least one Bus,
    one Generator, one transmission Line, and one transformer Line instance -- explicit beyond the
    fixture-diff coverage `test_generated_sysml_matches_fixture_all_tracks` already gives it."""
    result = _run("generate_sysml.py", "--track", "grid", "--step", "run")
    assert result.returncode == 0, result.stdout + result.stderr
    text = (OUTPUT_DIR / "grid_topology.sysml").read_text()
    for expected_uri in (
        "http://iec.ch/TC57/2013/CIM-schema-cim16#TopologicalNode",
        "http://iec.ch/TC57/2013/CIM-schema-cim16#SynchronousMachine",
        "http://iec.ch/TC57/2013/CIM-schema-cim16#ACLineSegment",
        "http://iec.ch/TC57/2013/CIM-schema-cim16#PowerTransformer",
    ):
        assert f'attribute cimClassUri = "{expected_uri}";' in text, expected_uri


def test_syntax_gate_accepts_clean_fixtures():
    result = _run("validate_sysml.py", "--step", "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_syntax_gate_rejects_broken_input(tmp_path):
    broken = tmp_path / "broken.sysml"
    broken.write_text("package Broken {\n    part def X {\n")  # unterminated block
    result = _run("validate_sysml.py", str(broken))
    assert result.returncode == 1
    assert "FAIL" in result.stdout
    assert ":" in result.stdout  # a real line:column locator, not a bare "invalid"


def test_iso_ir_matches_fixture_all_tracks():
    for track in TRACKS:
        result = _run("translate_iso_ir.py", "--track", track, "--step", "check")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "MATCH" in result.stdout


def test_rendered_svg_matches_fixture_all_tracks():
    for track in TRACKS:
        result = _run("render_diagram.py", "--track", track, "--step", "check")
        assert result.returncode == 0, result.stdout + result.stderr
        assert "MATCH" in result.stdout


def test_sbom_matches_fixture_track_a_only():
    result = _run("generate_sbom.py", "--step", "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_demo_script_runs_end_to_end_and_regenerates_every_artifact():
    """Runs the real chained pipeline (scripts/demo_lab6.sh) once, start to finish -- unlike every
    test above, which drives one script's own --step check gate in isolation. Deletes each expected
    output first so a pass actually proves regeneration, not stale output left over from a previous
    run."""
    for name in DEMO_OUTPUTS:
        path = OUTPUT_DIR / name
        if path.exists():
            path.unlink()

    result = subprocess.run(
        [str(DEMO_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: Lab 6's pipeline ran end to end for all three tracks." in result.stdout

    for name in DEMO_OUTPUTS:
        path = OUTPUT_DIR / name
        assert path.exists(), f"{name} was not regenerated by the end-to-end run"
        assert path.stat().st_size > 0, f"{name} was regenerated but empty"
