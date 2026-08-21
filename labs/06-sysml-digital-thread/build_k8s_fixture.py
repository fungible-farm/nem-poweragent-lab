"""Derive a `kubectl get pods,configmaps -o json`-shaped fixture from this repo's own real,
already-committed `kube/*.yaml` Pod/Job manifests -- not a live cluster call (PRD-0006 scope item
2: "NOT a live cluster call"). Every field in the emitted fixture traces back to a real manifest
already proven with `podman kube play` elsewhere in this repo (see each source file's own header
comment and `AGENTS.md`'s kube/ notes) -- this script only reshapes their already-real content into
the JSON list shape `kubectl get -o json` would emit, so Lab 6's generator has something snapshot-
shaped to read without needing an actual cluster.

No ConfigMap objects exist in this repo's kube/*.yaml manifests (every pod mounts real data via a
hostPath volume, not a ConfigMap) -- so the emitted List's `items` are Pods only, not fabricated
ConfigMaps to satisfy the letter of "pods,configmaps". `benchmark-runner-job.yaml`'s `kind: Job`
carries its own Pod template (`spec.template.spec`); this script lifts that template into a
synthesized Pod item the same way `kubectl get pods` would show for a Job's running pod, tagged
with `metadata.ownerReferences` pointing at the Job so that provenance isn't hidden.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Final, TypedDict

import yaml

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
KUBE_DIR: Final[Path] = REPO_ROOT / "kube"
OUTPUT_PATH: Final[Path] = Path(__file__).resolve().parent / "fixtures" / "k8s_snapshot.json"

# Every manifest this script reads -- named explicitly rather than globbed, so a new kube/*.yaml
# added later doesn't silently change this committed fixture until someone deliberately updates
# this list (matching AGENTS.md's "no undocumented magic numbers"/explicit-over-implicit spirit).
MANIFEST_FILES: Final[list[str]] = [
    "powermcp-pandapower-pod.yaml",
    "villasnode-tap-pod.yaml",
    "llamacpp-phi-pod.yaml",
    "benchmark-runner-job.yaml",
]


class PodItem(TypedDict):
    apiVersion: str
    kind: str
    metadata: dict[str, Any]
    spec: dict[str, Any]
    status: dict[str, Any]


def _pod_item_from_spec(
    name: str, labels: dict[str, str], pod_spec: dict[str, Any], owner: dict[str, Any] | None
) -> PodItem:
    """Build one kubectl-shaped Pod item. `status.phase` is honestly "Unknown" -- this fixture is
    derived from static manifests, not a live cluster, so there is no real phase to report."""
    metadata: dict[str, Any] = {"name": name, "labels": labels}
    if owner is not None:
        metadata["ownerReferences"] = [owner]
    containers = [
        {"name": c["name"], "image": c["image"], "ports": c.get("ports", [])}
        for c in pod_spec.get("containers", [])
    ]
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": metadata,
        "spec": {"containers": containers},
        "status": {"phase": "Unknown"},
    }


def load_manifests() -> list[PodItem]:
    items: list[PodItem] = []
    for filename in MANIFEST_FILES:
        path = KUBE_DIR / filename
        docs = list(yaml.safe_load_all(path.read_text()))
        for doc in docs:
            if doc is None:
                continue
            kind = doc.get("kind")
            if kind == "Pod":
                meta = doc["metadata"]
                items.append(_pod_item_from_spec(meta["name"], meta.get("labels", {}), doc["spec"], None))
            elif kind == "Job":
                meta = doc["metadata"]
                tmpl = doc["spec"]["template"]
                owner = {"kind": "Job", "name": meta["name"], "apiVersion": doc["apiVersion"]}
                items.append(
                    _pod_item_from_spec(
                        f"{meta['name']}-pod",
                        tmpl.get("metadata", {}).get("labels", {}),
                        tmpl["spec"],
                        owner,
                    )
                )
            # Any other kind (e.g. a future ConfigMap) would need its own branch here -- there
            # are none in this repo's kube/*.yaml today, see module docstring.
    return items


def build_fixture() -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "List",
        "items": load_manifests(),
    }


def check_step() -> bool:
    """--step check: regenerate in memory and diff against the committed fixture file."""
    fresh = build_fixture()
    if not OUTPUT_PATH.exists():
        print(f"FAIL: {OUTPUT_PATH} does not exist -- run --step run first")
        return False
    committed = json.loads(OUTPUT_PATH.read_text())
    if fresh == committed:
        print(f"MATCH: {len(fresh['items'])} pod items vs {OUTPUT_PATH.name}")
        return True
    print("FAIL: k8s_snapshot.json is stale -- source kube/*.yaml manifests changed, re-run --step run")
    return False


def main() -> None:
    step = sys.argv[sys.argv.index("--step") + 1] if "--step" in sys.argv else "run"
    if step == "check":
        sys.exit(0 if check_step() else 1)
    fixture = build_fixture()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUTPUT_PATH} ({len(fixture['items'])} pod items, derived from {len(MANIFEST_FILES)} real kube/*.yaml manifests)")


if __name__ == "__main__":
    main()
