#!/usr/bin/env python3
"""Fetch the Phi-4-mini-instruct GGUF used by kube/llamacpp-phi-pod.yaml.

Idempotent: skips the file if it already exists and its sha256 matches.
Pinned to a specific file (not "latest") so CHECKSUM below stays correct
forever, same discipline as scripts/fetch_csiro_nem_data.py.

Source: https://huggingface.co/unsloth/Phi-4-mini-instruct-GGUF, file
Phi-4-mini-instruct-Q4_K_M.gguf (Q4_K_M quant, chosen over the several other
Phi-4-mini-instruct GGUF requantizers on Hugging Face Hub for
download-count/provenance confidence at time of pinning -- verified against
this repo's own microsoft/Phi-4-mini-instruct upstream, not the differently
named/older microsoft/Phi-3-mini-* results the same search surfaces).
CHECKSUM was cross-checked against Hugging Face's own recorded LFS sha256
for this file (`GET https://huggingface.co/api/models/<repo>?blobs=true`)
at pin time, same verification this script re-does on every download.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

REPO = "unsloth/Phi-4-mini-instruct-GGUF"
FILENAME = "Phi-4-mini-instruct-Q4_K_M.gguf"
URL = f"https://huggingface.co/{REPO}/resolve/main/{FILENAME}"

MODEL_DIR = Path(__file__).resolve().parent.parent / "data" / "models"

# Verified byte-for-byte against Hugging Face's own recorded LFS metadata for
# this file at pin time (2026-08-01) -- see kube/llamacpp-phi-pod.yaml's own
# header for the exact verification command.
CHECKSUM_SHA256 = "88c00229914083cd112853aab84ed51b87bdf6b9ce42f532d8c85c7c63b1730a"
EXPECTED_SIZE_BYTES = 2_491_874_272

# 8 MiB read chunks -- large enough to keep syscall overhead negligible for a
# multi-GB download, small enough to bound peak memory well below the file
# size (unlike scripts/fetch_csiro_nem_data.py's read-whole-file-into-memory
# approach, which is fine for its ~single-digit-MB case files but would be
# wasteful/risky here).
CHUNK_BYTES: int = 8 * 1024 * 1024


def sha256_of(path: Path) -> str:
    """Stream-hash `path` without loading it fully into memory."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    dest = MODEL_DIR / FILENAME

    if dest.exists() and dest.stat().st_size == EXPECTED_SIZE_BYTES and sha256_of(dest) == CHECKSUM_SHA256:
        print(f"[skip] {FILENAME} already present and checksum-verified")
        print("PASS: Phi-4-mini-instruct GGUF present and checksum-verified in data/models/")
        return

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] {FILENAME} ({EXPECTED_SIZE_BYTES / 1e9:.2f} GB) <- {URL}")
    print("        this is the one one-time model-download exception named in")
    print("        docs/DEFINITION_OF_DONE.md's Composition section -- cached after this run")

    tmp_dest = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    downloaded = 0
    with urllib.request.urlopen(URL, timeout=60) as resp, tmp_dest.open("wb") as out:
        while chunk := resp.read(CHUNK_BYTES):
            out.write(chunk)
            h.update(chunk)
            downloaded += len(chunk)
            print(f"\r        {downloaded / 1e9:.2f} / {EXPECTED_SIZE_BYTES / 1e9:.2f} GB", end="", flush=True)
    print()

    actual = h.hexdigest()
    if actual != CHECKSUM_SHA256 or downloaded != EXPECTED_SIZE_BYTES:
        tmp_dest.unlink(missing_ok=True)
        print(
            f"[FAIL] checksum/size mismatch for {FILENAME}: "
            f"expected sha256={CHECKSUM_SHA256} size={EXPECTED_SIZE_BYTES}, "
            f"got sha256={actual} size={downloaded}",
            file=sys.stderr,
        )
        sys.exit(1)

    tmp_dest.rename(dest)
    print(f"[ok] {FILENAME} written to {dest} ({downloaded} bytes, sha256 verified)")
    print("PASS: Phi-4-mini-instruct GGUF present and checksum-verified in data/models/")


if __name__ == "__main__":
    main()
