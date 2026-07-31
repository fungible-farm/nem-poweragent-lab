"""pytest wrapper around Lab 5's three --step check gates, following
labs/01-simple-loadflow-fit/test_lab1.py's pattern.

None of these tests requires a running podman pod: generate_topology.py and
run_dpsim.py's --step check re-derive their real result from scratch (a real
pandapower.runpp() and a real DPsim EMT solve, respectively) and diff against
their committed fixtures; verify_stream.py's --step check validates the
committed sample_stream_summary.json fixture structurally (see its own
module docstring for why a live-pod network capture is not something a
pytest run should depend on -- the pod is verified separately, for real,
during interactive/manual runs of the walkthrough).
"""
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent


def _run_check(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LAB_DIR / script), "--step", "check"],
        capture_output=True,
        text=True,
    )


def test_lab5_topology_matches_fixture():
    result = _run_check("generate_topology.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_dpsim_run_matches_fixture():
    result = _run_check("run_dpsim.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab5_stream_summary_matches_fixture():
    result = _run_check("verify_stream.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
