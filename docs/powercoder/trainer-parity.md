# Trainer parity — M07 qualification in progress

This records measured preprocessing and environment qualification. Axolotl GPU
training, checkpoint resume, accuracy comparison, and performance parity have
not yet been demonstrated. M07 remains incomplete.

## Environments

| Component | Unsloth evaluation image | Separate Axolotl image |
| --- | --- | --- |
| Image ID | `74feb3e2e84cfde5d1d2d21c34213d60114d7eb7a80bb1f9352ff2dda15c00ff` | `3bbe9128db0886d5a89bbaf5de7050c7877e0804b19e6e56b4dbc97e4840b2b2` |
| Framework | Unsloth 2026.10.7 | Axolotl 0.21.1.dev0 |
| PyTorch | 2.13.0+cu130 | 2.13.0+cu130 |
| Transformers | 5.17.0 | 5.20.1 |
| PEFT | 0.21.2 | 0.21.2 |
| Datasets | 4.8.5 | 5.0.1 |
| Accelerate | 1.15.0 | 1.15.0 |
| bitsandbytes | 0.50.2 | 0.50.2 |

The Axolotl image contains no Unsloth package. It starts from the existing
ARM64 PyTorch GPU-test image
`bbee48c815a1210eed3ccbd63035ccb7b8008fa2db6e62e3c41b94bcbd6f08c8`.
That substrate was created by the prior pi session; rebuilding it from a fully
committed, locked recipe remains part of environment qualification. Full
resolved inventories are in `training/unsloth/out/eval-environment.lock.txt`
and `training/axolotl/out/environment.lock.txt`.

Axolotl source is pinned to
[`cc83a1c12e2d2010345806702d8ad3f794fad7f6`](https://github.com/axolotl-ai-cloud/axolotl/tree/cc83a1c12e2d2010345806702d8ad3f794fad7f6).
The configuration adapts its Qwen3.5 example, with BF16 LoRA, SDPA, and sample
packing disabled for the ARM64 baseline. Upstream requires additional FLA
kernels for packed Qwen3.5 sequences.

Upstream pins `zstandard==0.22.0`, whose isolated build pulled cffi 1.16.0 and
failed on this Python 3.13 ARM64 image. The recipe explicitly overrides it to
`zstandard==0.25.0`, which installed successfully. This exception is local to
the trainer environment. Axolotl is Apache-2.0 and also installs the explicitly
named `axolotl-contribs-lgpl==0.0.7` training dependency; retain that dependency
in the license inventory rather than describing the entire stack as permissive.

## Measured data and token parity

The reproduction uses the original 273 train records, including their original
multiplicity. Validation contains 45 distinct tasks after excluding training
overlap and repeated validation inputs. No benchmark or test data is read by
`training/axolotl/prepare.py` or the token comparison.

Initial chat-template preprocessing yielded identical input tokens but different
loss masks: 22,982 Unsloth supervised tokens versus 22,163 Axolotl tokens, a
difference of three tokens per training row. The initial failure report is
`training/axolotl/out/token-parity-before-alignment.json`.

The configuration now uses Axolotl's documented
[pre-tokenized dataset format](https://github.com/axolotl-ai-cloud/axolotl/blob/cc83a1c12e2d2010345806702d8ad3f794fad7f6/docs/dataset-formats/tokenized.qmd).
Tokenization and masks are exported with the original Unsloth preprocessing
function, while training remains Axolotl's independent trainer and starts from
the original base weights. Actual Axolotl preprocessing then produced:

| Observation | Measured result |
| --- | --- |
| Training records | 273 |
| Input sequences identical, including multiplicity | true |
| Supervised labels identical, including multiplicity | true |
| Supervised tokens in each trainer | 22,982 |

Evidence: `training/axolotl/out/token-parity-aligned.json`. The comparison loads
the actual prepared Arrow dataset. A matching YAML declaration alone is not
accepted as token-parity evidence.

## Reproduction and continuation

`sft-4b.yaml` and `sft-edge.yaml` define reproduction mode: the original pinned
base, no adapter parent, no checkpoint resume, and automatic resume disabled.
The prepared training directory can be mounted alone; the benchmark directory
does not need to be exposed to the training container.

Before starting training, record the resolved image ID, command, configuration
hash, tokenized-data hashes, base revision, and tokenizer fingerprints in a run
manifest. For a reproduction, parent checkpoint must be null. This run-manifest
gate and actual GPU training remain pending.

Continuation must explicitly name a validated parent checkpoint and use a new
output directory. Match its model revision, tokenizer, target-module names,
LoRA rank/alpha, and dataset hashes; retain hashes of its adapter, optimizer,
scheduler, RNG state, and trainer state. Then use Axolotl's explicit
`--resume-from-checkpoint` option. Resuming checkpoint-50 to step 100 is a
concrete restart test; merely loading a finished checkpoint-100 with a
100-step budget does not demonstrate further training.

Loading an Unsloth adapter into Axolotl remains unverified. Do not silently
substitute adapter-only loading for a full optimizer/RNG resume or describe a
continuation as an independent reproduction.
