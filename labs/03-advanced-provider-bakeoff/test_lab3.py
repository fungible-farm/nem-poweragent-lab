"""pytest wrapper around Lab 3's orchestrator, for scripts/run_labs_1_3.sh."""
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent
RESULTS_DIR = LAB_DIR.parent.parent / "benchmarks" / "power-agent-bench-lite" / "results"
SCORECARD_CHART_FILE = RESULTS_DIR / "scorecard_chart.png"


def test_lab3_scorecard_matches_fixture():
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "orchestrator.py"), "--step", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab3_report_renders_scorecard_chart():
    """SCORECARD_CHART_FILE is regenerated, gitignored output (see
    orchestrator.py's SCORECARD_CHART_FILE comment) -- check_step() never
    touches it (it calls sweep_step() directly, not report_step()), so this
    is the one place that actually exercises `_plot_scorecard()` still
    rendering successfully. Existence only, no pixel diff, matching
    docs/backlog/0003-lab3-scorecard-visualization.md's documented scope.
    """
    SCORECARD_CHART_FILE.unlink(missing_ok=True)
    result = subprocess.run(
        [sys.executable, str(LAB_DIR / "orchestrator.py"), "--step", "report"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert SCORECARD_CHART_FILE.exists()
