"""pytest wrapper around Lab 4's self-checking steps, for
scripts/run_labs_1_3.sh-style CI use.

Network note: unlike Labs 1-3's pytest wrappers (fully offline once
data/*.m is fetched), these tests make real NEMOSIS/nemweb.com.au calls --
see this lab's README "Sandbox notes." They rely on fetch_day.py's cache
(data/nemosis_cache/, gitignored) already being warm from a prior run; if
it's cold, the first test to run will populate it itself (NEMOSIS pulls
live), just slower.
"""
import csv
import subprocess
import sys
from pathlib import Path

LAB_DIR = Path(__file__).resolve().parent


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LAB_DIR / script), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def test_lab4_reconciliation_matches_fixture():
    result = _run("reconcile.py", "--step", "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout


def test_lab4_duid_mapping_csv_is_committed_and_populated():
    """duid_mapping.csv is the auditable artifact AGENTS.md/docs/
    DEFINITION_OF_DONE.md require ("committed, human-readable CSV with a
    rationale column, not implicit in code") -- check it's actually there
    and shaped right, independent of re-running map_duids.py."""
    mapping_csv = LAB_DIR / "duid_mapping.csv"
    assert mapping_csv.exists(), "duid_mapping.csv must be committed, see map_duids.py"

    with mapping_csv.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 0
    expected_columns = {
        "real_duid", "station_id", "participant_id", "region",
        "capacity_proxy_mw", "synthetic_gen_bus", "synthetic_gen_max_p_mw",
        "capacity_diff_mw", "rationale",
    }
    assert expected_columns.issubset(rows[0].keys())
    for row in rows:
        assert row["rationale"], f"empty rationale for {row['real_duid']}"


def test_lab4_explain_constraint_finds_sa1_relevant_binding_constraint():
    """explain_constraint.py has no fixture (a real constraint's binding
    status is live AEMO data, not something to freeze -- see this lab's
    README "Sandbox notes"), so this test checks the mechanic actually
    runs end to end and finds a real, decoded, SA1-relevant constraint,
    not that any particular constraint ID comes back."""
    result = _run("explain_constraint.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SA1-relevant: True" in result.stdout
    assert "LHS terms" in result.stdout
