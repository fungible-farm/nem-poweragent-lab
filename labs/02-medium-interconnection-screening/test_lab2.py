"""pytest wrapper around Lab 2's workflow steps, for scripts/run_labs_1_3.sh."""
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LAB_DIR / "workflow.py"), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def test_lab2_contingency_table_matches_fixture():
    result = _run("--step", "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab2_memo_blocks_without_approval():
    result = _run("--step", "memo")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "BLOCKED" in result.stdout
    assert "MEMO FINALIZED" not in result.stdout


def test_lab2_memo_finalizes_with_approval():
    result = _run("--step", "memo", "--approve", "APPROVE")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MEMO FINALIZED" in result.stdout


def test_lab2_memo_reports_contingency_induced_breaches():
    """Regression gate for draft_memo()'s classification bug: a row whose
    reason carries BOTH a pre-existing voltage clause AND a
    contingency-induced thermal clause (lines 151/152, the [175-608] parallel
    pair) must be reported as a real breach, not swallowed by the
    pre-existing label. The memo must say the outages break limits and name
    line 151 -- not the old, false "No contingency introduces a *new* limit
    breach."."""
    result = _run("--step", "memo", "--approve", "APPROVE")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "BREACH limits as a direct result of the outage" in result.stdout
    assert "line 151" in result.stdout
    assert "contingency-induced" in result.stdout
    assert "No contingency introduces a *new* limit breach" not in result.stdout
