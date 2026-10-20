"""Measure token and loss-mask parity before independent Axolotl training.

Run in the Unsloth environment with the prepared Axolotl Arrow files mounted.
No model weights are loaded and no benchmark or test rows are read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def fingerprint(value: object) -> str:
    """Hash token arrays in canonical JSON, including duplicate multiplicity."""
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def main() -> int:
    """Compare actual trainer preprocessing, rather than assuming template parity."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("training/unsloth/config.yaml"))
    parser.add_argument("--prepared-root", type=Path, default=Path("training/axolotl/out/prepared-4b"))
    parser.add_argument("--out", type=Path, default=Path("training/axolotl/out/token-parity.json"))
    parser.add_argument("--export-tokens", action="store_true")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--messages-dir", type=Path, default=Path("training/axolotl/out/data"))
    args = parser.parse_args()
    # Import the original trainer first so Unsloth patches precede transformers.
    from training.unsloth.train import build_dataset, load_config, load_train_examples
    # isort: split
    from datasets import load_from_disk
    from transformers import AutoProcessor

    config = load_config(str(args.config))
    system = config["dataset"]["system_prompt"]
    rows = load_train_examples(config["dataset"]["split"], system)
    processor = AutoProcessor.from_pretrained(
        config["model"]["name"], revision=config["model"].get("revision"), local_files_only=True
    )
    tokenizer = processor.tokenizer if hasattr(processor, "tokenizer") else processor
    reference = build_dataset(rows, processor, tokenizer, system, config["training"]["seq_len"])
    if args.export_tokens or args.export_only:
        exported = {}
        for split in ("train", "validation"):
            source = args.messages_dir / f"{split}.jsonl"
            messages = [json.loads(line)["messages"] for line in source.read_text().splitlines()]
            examples = [
                {"user": turns[1]["content"], "assistant": turns[2]["content"]}
                for turns in messages
            ]
            tokens = build_dataset(examples, processor, tokenizer, system, config["training"]["seq_len"])
            target = args.messages_dir / f"tokenized-{split}.jsonl"
            with target.open("x") as stream:
                for row in tokens:
                    stream.write(json.dumps(row) + "\n")
            exported[str(target)] = {
                "rows": len(tokens),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        (args.messages_dir / "tokenized-manifest.json").write_text(json.dumps({
            "files": exported,
            "tokenizer_vocab_sha256": fingerprint(tokenizer.get_vocab()),
            "chat_template_sha256": fingerprint(tokenizer.chat_template),
            "benchmark_access": False,
        }, indent=2) + "\n")
        if args.export_only:
            print(json.dumps(exported, indent=2))
            return 0
    prepared = [load_from_disk(str(path.parent)) for path in args.prepared_root.rglob("dataset_info.json")]
    matching = [dataset for dataset in prepared if len(dataset) == len(reference)]
    if len(matching) != 1:
        raise ValueError("Expected exactly one prepared dataset matching train row count")
    actual = matching[0]
    inputs = lambda dataset: Counter(fingerprint(row["input_ids"]) for row in dataset)
    labels = lambda dataset: Counter(
        fingerprint({"input_ids": row["input_ids"], "labels": row["labels"]}) for row in dataset
    )
    same_inputs = inputs(reference) == inputs(actual)
    same_labels = labels(reference) == labels(actual)
    report = {
        "train_rows": len(reference),
        "input_sequences_identical": same_inputs,
        "supervised_labels_identical": same_labels,
        "unsloth_supervised_tokens": sum(sum(token != -100 for token in row["labels"]) for row in reference),
        "axolotl_supervised_tokens": sum(sum(token != -100 for token in row["labels"]) for row in actual),
        "benchmark_access": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if same_inputs and same_labels else 1


if __name__ == "__main__":
    raise SystemExit(main())
