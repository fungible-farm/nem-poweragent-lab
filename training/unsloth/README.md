# M06 recovery and verification

The crashed pi session left a Qwen3.5-4B rank-32 adapter and checkpoint-100.
The training log reports 273 training rows, 100 steps, 390.2732 seconds,
NVIDIA GB10, and torch 2.13.0+cu130. These are recorded observations from
that run; GPU reload and inference have not been verified by the recovery.

The saved checkpoint audit finds 688 finite F32 adapter tensors. All 248
language LoRA B matrices differ from their default zero initialization. The
96 vision B matrices are zero. Exact initial A tensors were not saved.
Checkpoint hashes describe the files at recovery, not a launch-time snapshot.

## CPU checks

From the repository root:

```sh
uv run --offline --no-sync python -m pytest training/unsloth/test_evaluation.py powercoder/distillation/test_distillation.py -q
uv run --offline --no-sync python training/unsloth/audit_checkpoint.py \
  --adapter training/unsloth/out/qwen3.5-4b-lora \
  --source training/unsloth/config.yaml training/unsloth/out/train_log.json \
    training/unsloth/out/train_full.log powercoder/datasets/smoke/splits/train.jsonl \
  --out training/unsloth/out/checkpoint_audit.json
```

The checkpoint audit should exit 0 with `saved_tensor_gate: true`. It does
not establish checkpoint reload, GPU execution, or model quality.

The old 227 held-out rows contain only 108 unique task inputs and 23 rows
overlapping training. Their combined independence audit must fail. The old
110-row topology-reserved benchmark contains only seven unique prompts.
Preserve these files as evidence; do not report them as 227 independent tasks.

Generate a fresh domain set in a new output directory:

```sh
uv run --offline --no-sync python -m powercoder.datasets.build_benchmark \
  --exclude powercoder/datasets/smoke/examples.jsonl \
  --out-dir benchmarks/power-agent-bench-lite/results/domain-held-out-20261020
```

This run generated 306 verified tasks: 26 power-flow reports, 120 load fits,
120 line-rating fits, and 40 dispatch fits. All 306 prompts and input sets are
distinct; none overlaps any task in the original 500-example dataset used for
teacher correction and training. The rows and manifest are ignored artifacts.
Generation refuses to overwrite an existing directory. Recheck independence:

```sh
uv run --offline --no-sync python -m powercoder.datasets.audit \
  --candidates benchmarks/power-agent-bench-lite/results/domain-held-out-20261020/examples.jsonl \
  --exclude powercoder/datasets/smoke/examples.jsonl
```

This is separation by prompt and concrete inputs, not separation by topology
or template. It covers four power-flow task families on the existing synthetic
NEM topology. General Python, agent behaviour, robustness, and the critical
fabrication suite remain required for M09.

## Next GPU gate

Inside the existing qualified GPU environment, with the repository mounted
as the working directory and the base model cached. Independent numerical
scoring also requires pandapower 3.5.4, powerio 0.7.2, and SciPy in that
environment; the updated container recipe includes them but still needs a
real build and GPU qualification:

```sh
python training/unsloth/evaluate.py \
  --adapter training/unsloth/out/qwen3.5-4b-lora \
  --splits benchmarks/power-agent-bench-lite/results/domain-held-out-20261020/examples.jsonl \
  --exclude powercoder/datasets/smoke/examples.jsonl \
  --out training/unsloth/out/eval_results.json
python training/unsloth/export.py training/unsloth/config.yaml
```

Evaluation loads the base and saved adapter separately, uses greedy decoding
and the same system prompt, retains full individual responses, and computes
Wilson pass-rate intervals and a paired percentile bootstrap interval for the
delta. Fit answers are checked by a fresh solver run with the task's actual
metric tolerance; report and trajectory answers use reference matching.
Tool execution and evidence use are not established by reference matching.
The overall G5 gate stays pending the separate regression and fabrication
suites even if domain improvement exceeds ten percentage points.

Export now loads the saved adapter before calling PEFT's
`merge_and_unload(safe_merge=True)`. The previous implementation loaded only
the base and could not produce a valid tuned export. Neither the corrected
GPU export nor the updated container recipe has been executed in recovery.

Recovery execution is currently limited: no `/dev/nvidia*` devices are visible,
`nvidia-smi` cannot reach the driver, and Podman fails on read-only
`/run/user/1000/libpod`. Ruff is absent from the offline cache, and fetching it
failed because `pypi.org` DNS was unavailable. Syntax compilation, CPU tests,
and actual pandapower dataset generation succeeded.

M06 still needs GPU reload/inference, baseline comparison, merged export,
validation loss, rank-64 and edge-student experiments, and a fully pinned
environment. M07 needs independent Axolotl training and verified resume/lineage.
M08 must follow evidence of SFT improvement. M09 needs the remaining suites
and actual model scorecards. M10 needs selected-model ONNX quantization and
physical Windows execution with a measured execution provider.
