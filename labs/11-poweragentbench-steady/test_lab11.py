"""Lab 11 self-checks: pinned sources, the published Level 1 baseline, the committed Level 2 fixture."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

LAB: Path = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB))

import steady_lab  # noqa: E402

FETCHED: bool = (steady_lab.CHECKOUT / ".git").is_dir()


@pytest.mark.skipif(not FETCHED, reason="run `just lab11-fetch` first")
def test_checkout_is_the_pinned_commit_with_unchanged_files() -> None:
    """A different commit or an edited case file would be a different benchmark."""
    assert steady_lab.step_verify() == []


def write_run(directory: Path, recall: float, false_safe: float) -> Path:
    """A minimal Level 2 output directory: one agent, one case."""
    directory.mkdir()
    (directory / "baseline_summary.csv").write_text(
        "agent," + ",".join(steady_lab.HEADLINE_METRICS) + "\nHybrid-tool,0.5,1.0,0.0,0.25\n")
    (directory / "baseline_per_case.csv").write_text(
        "agent,case_seed,evidence_rate,unvalidated_claim_rate,unvalidated_claims,reported_top20_recall,"
        f"top20_false_safe_rate,validated_calls,validation_budget_used\nHybrid-tool,1000,1.0,0.0,0,{recall},{false_safe},20,0.25\n")
    return directory


def test_a_row_breaking_score_agents_identities_is_reported(tmp_path: Path) -> None:
    """Recall and false-safe rate over the oracle top 20 must sum to 1, whatever was recorded."""
    assert steady_lab.identity_violations(write_run(tmp_path / "ok", 0.5, 0.5)) == []
    assert steady_lab.identity_violations(write_run(tmp_path / "bad", 0.5, 0.4)) == [
        "Hybrid-tool seed 1000: reported_top20_recall + top20_false_safe_rate = 0.9, not 1"]


def test_published_level1_numbers_are_compared_field_by_field() -> None:
    worst, count, problems = steady_lab.max_abs_difference({"a": {"x": 1.0, "ok": True}}, {"a": {"x": 1.5, "ok": True}})
    assert (worst, count, problems) == (0.5, 2, [])


@pytest.mark.skipif(not FETCHED or not os.environ.get("RUN_SLOW_LABS"),
                    reason="~45 s of PyPSA/DC studies; opt in with RUN_SLOW_LABS=1 after `just lab11-fetch`")
def test_level1_and_level2_reproduce_their_references() -> None:
    """Level 1 against the benchmark's published baseline; Level 2 against the committed run."""
    run = subprocess.run([sys.executable, str(LAB / "steady_lab.py"), "--step", "check"], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]


def test_local_fetch_verifier_rejects_source_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The independent fetch helper uses this lab's manifest format and detects drift."""
    import hashlib
    import fetch_benchmark

    source = tmp_path / "source.py"
    source.write_text("original")
    expected = {"commit": "pinned", "sha256": {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()}}
    monkeypatch.setattr(fetch_benchmark, "CHECKOUT", tmp_path)
    monkeypatch.setattr(fetch_benchmark, "git", lambda *args: "pinned")
    assert fetch_benchmark.verify(expected) == []
    source.write_text("changed")
    assert fetch_benchmark.verify(expected) == ["changed source.py"]
