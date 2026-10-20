# Granite 4.2 8B comparison experiment

This experiment uses IBM's Apache-2.0
[`ibm-granite/granite-4.2-8b`](https://huggingface.co/ibm-granite/granite-4.2-8b),
revision `b3791992239dce12d0038f1f54a8adb7b02d59ab`, as a separate starting
checkpoint. The four downloaded weight shards were verified against the pinned
Hub metadata on 2026-10-21. Evidence is local, ignored output at
`training/unsloth/out/granite42-download-verified.json`. A completed download is
not a trained model or an accuracy result.

1. Read `training/unsloth/config.granite42.yaml`. Its training rows and
   hyperparameters match the original Qwen experiment: the same 273 verified
   training rows, rank 32, alpha 64, seed 42 and 100 optimizer steps. The
   Granite checkpoint and output paths are separate from the Qwen artifacts.

   Granite training uses real Transformers/PEFT on the physical GB10, in the
   existing pinned training image. It does not use Unsloth model patches.
   These are two different training implementations, with their package
   versions recorded in the Granite preflight. No new package is installed.
   Dependency licenses are recorded in `train.py`.

2. The native-template tokenization check was run on all 273 original training
   rows. You should see a nonempty assistant target on every row and a maximum
   length of 281 tokens, within the configured 1,024-token limit. `encode_example`
   derives its mask from the actual rendered answer boundary, verifies token
   prefix equality, and refuses any truncated target. The benchmark is never
   opened by the trainer.

3. Run training on a free GPU, with the repository mounted at `/workspace`:

   ```sh
   podman run --name powercoder-granite42-training --device nvidia.com/gpu=all \
     --network none --security-opt label=disable \
     -v "$PWD:/workspace" -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
     -e PYTHONUNBUFFERED=1 \
     74feb3e2e84cfde5d1d2d21c34213d60114d7eb7a80bb1f9352ff2dda15c00ff \
     python -m training.granite.train --config training/unsloth/config.granite42.yaml
   ```

   The trainer refuses an existing output directory, rechecks each base shard
   against its pinned revision and SHA-256, and requires CUDA. You should see
   100 completed steps, a saved adapter, an independently reloaded saved-adapter
   merge and a hash manifest. `train_log.json` records the source hashes,
   completed steps, loss history, runtime versions and physical GPU. The
   configuration alone does not prove any of these steps completed.

4. Evaluate Granite base and student on the complete 306-task suite using
   `powercoder.inference.evaluate_agent`; see `powercoder/inference/README.md`.
   IBM documents `qwen3_coder` tool parsing and permits the built-in
   `nemotron_v3` reasoning parser. Preserve the same greedy decoding, token,
   turn, tool and HTTP budgets as the Qwen runs.

   Compare Granite student with Granite base, Qwen base and Qwen student.
   You should see paired task counts, pass rates, deltas and uncertainty.
   The ten-percentage-point domain gain is a measured gate, not a guaranteed
   consequence of training. Report scoring currently uses the original
   reference's field labels; a numerically correct differently formatted
   report can fail that parser. Keep raw responses to audit this limitation.

## Sequential driver

`uv run --offline --no-sync python -m training.run_comparison --help` describes
the driver that adopts an already-running full Qwen base evaluation by its
actual PID and output directory. It verifies that PID's command and birth time,
waits for terminal process state, and requires all 306 scored tasks before
advancing. It then runs Qwen student, Granite training, Granite base and Granite
student, followed by all four comparisons. It releases each owned server only
after its full evaluation. It never retries a failed stage or silently mixes
new results with an old run.

The active 2026-10-21 run is `training/unsloth/out/agent-domain-r2/`.
`pipeline.jsonl` records actual child PIDs, commands, stage exits and errors;
per-model logs and fsynced per-task journals retain raw evidence. A PID in the
journal alone does not prove the driver is still running: check `/proc` process
birth/state or the corresponding live tool session. `pipeline_complete` means
the stages completed, even if their measured gain misses the threshold.

For an AEMO modeller, the comparison tests whether changing and fine-tuning a
local model improves independently checked AC study answers under equal tool
access. It makes no claim of a real-network digital twin, a release-wide G5
pass, or Windows deployment qualification.
