"""Track-A-only: emit a CycloneDX-shaped SBOM stub for this digital thread's Agent/MCPServer/
DataSource instances, via the real `cyclonedx-python-lib` (Apache-2.0, PyPI) rather than a
hand-built dict -- a real library exists and fits this MVP's "one dependency" budget, so it's used
instead of reimplementing the CycloneDX JSON schema by hand.

Per PRD-0006 scope: `version: "unknown"` for every component (no scanner integration, no drift
detection -- those need real syft/grype-style scanner output as input, out of scope until that
pipeline exists independently) and each component's real `source`/`owner`/`refresh_cadence` carried
as CycloneDX `properties` so the provenance this schema exists to capture isn't lost in translation.

Track B (grid topology) has no SBOM: a software bill-of-materials doesn't map onto physical grid
assets. What Track B's own third-artifact equivalent should be (an equipment register? NER asset
schedule shape?) is named as an open question for a later phase in PRD-0006, not invented here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

import yaml
from cyclonedx.model import Property
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.output.json import JsonV1Dot5

LAB_DIR: Final[Path] = Path(__file__).resolve().parent
SCHEMA_DIR: Final[Path] = LAB_DIR / "schema"
FIXTURES_DIR: Final[Path] = LAB_DIR / "fixtures"
OUTPUT_DIR: Final[Path] = LAB_DIR / "output"
OUTPUT_PATH: Final[Path] = OUTPUT_DIR / "digital_thread_sbom.json"
EXPECTED_PATH: Final[Path] = FIXTURES_DIR / "expected_sbom.json"

TYPE_BY_KIND: Final[dict[str, ComponentType]] = {
    "agents": ComponentType.APPLICATION,
    "mcp_servers": ComponentType.APPLICATION,
    "data_sources": ComponentType.DATA,
}


def _component(kind: str, entry: dict[str, str]) -> Component:
    return Component(
        name=entry["name"],
        # cyclonedx-python-lib defaults bom_ref to a fresh random UUID per Component if not given
        # -- pinned to the instance's own name instead so this stub's output (and its --step check
        # fixture diff) is deterministic across runs, matching every other lab's convention.
        bom_ref=entry["name"],
        type=TYPE_BY_KIND[kind],
        version="unknown",
        properties=[
            Property(name="digital-thread:source", value=entry["source"]),
            Property(name="digital-thread:owner", value=entry["owner"]),
            Property(name="digital-thread:refresh_cadence", value=entry["refresh_cadence"]),
        ],
    )


def build_sbom() -> dict[str, Any]:
    instances = yaml.safe_load((SCHEMA_DIR / "digital_thread_instances.yaml").read_text())
    bom = Bom()
    for kind in ("agents", "mcp_servers", "data_sources"):
        for entry in instances.get(kind, []):
            bom.components.add(_component(kind, entry))
    output = JsonV1Dot5(bom)
    doc = json.loads(output.output_as_string())
    # serialNumber/metadata.timestamp are non-deterministic (a fresh UUID/clock read every call)
    # -- stripped so this stub's --step check can do a real byte-for-byte comparison, matching
    # every other lab's fixture convention, without treating an unavoidably-fresh UUID as drift.
    doc.pop("serialNumber", None)
    doc.get("metadata", {}).pop("timestamp", None)
    return doc


def check_step() -> bool:
    fresh = build_sbom()
    if not EXPECTED_PATH.exists():
        print(f"FAIL: {EXPECTED_PATH} does not exist")
        return False
    expected = json.loads(EXPECTED_PATH.read_text())
    if fresh == expected:
        print(f"MATCH: SBOM ({len(fresh['components'])} components) vs {EXPECTED_PATH.name}")
        return True
    print(f"FAIL: SBOM differs from {EXPECTED_PATH.name}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["run", "check"], default="run")
    args = parser.parse_args()

    if args.step == "check":
        sys.exit(0 if check_step() else 1)

    doc = build_sbom()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT_PATH} ({len(doc['components'])} components)")


if __name__ == "__main__":
    main()
