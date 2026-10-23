"""The Rust command IR (rust/command-ir) is pinned to this exact served schema; a drift on either side fails."""

from __future__ import annotations

import json
from pathlib import Path

from powercoder.inference.studies import tool_schema

FIXTURE: Path = Path(__file__).resolve().parents[2] / "rust/command-ir/tests/served_run_study_trial.json"


def test_the_served_study_schema_is_the_one_the_ir_emits() -> None:
    """Regenerate the fixture only together with the IR (FM-23: train/serve schema skew)."""
    assert json.dumps(tool_schema()) + "\n" == FIXTURE.read_text()
