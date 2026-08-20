"""pytest wrapper around Lab 6's pipeline scripts -- subprocess-driven, matching
labs/02-medium-interconnection-screening/test_lab2.py's pattern. Never reimplements the generator/
translator/renderer logic; only drives each script's own --step check gate and asserts on its
stdout, the same discipline every other lab's test file follows."""

import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
TRACKS = ["digital-thread", "grid", "pipeline"]


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
