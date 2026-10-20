# PowerCoder handoff — 21 October 2026

Snapshot: **09:38:44 AEDT (UTC+11)**. Branch: `chore/powercoder-recovery`.
Implementation HEAD: `8442962f67739eb3e439e6d8f5030bece3c3746c`.
The evaluation and its sequential driver remain running. Writing this handoff did
not pause, stop, or restart them.

## Objective and honest completion status

The user requested committing local work, completing the full 306-task comparison
of Qwen3.5-4B base against its original Unsloth student, demonstrating at least a
**10 percentage-point domain pass@1 improvement**, downloading Granite 4.2 8B,
training it on the same dataset, and evaluating/comparing its base and student.
The detailed original request/audit is local at
`/home/brianh/.codex/attachments/573df69a-e50a-4716-b01e-1e68b2cd83bc/pasted-text-1.txt`.

**The experiment is incomplete.** At this snapshot, the Qwen base has completed
**27/306 tasks**. Qwen student evaluation, Granite training, and both Granite
evaluations remain queued. No complete comparison or required improvement has
been demonstrated. Scripts, parser tests, and checkpoint existence are not model
performance evidence. Do not claim GRPO, the Windows audit, or the full G5 gate
is complete based on prior milestone/commit titles.

Two additional user requests were handled:

- Only this one Git worktree was registered; it was clean before this handoff.
  Ignored datasets, checkpoints, and evaluation journals are substantial local
  artifacts and do not appear in ordinary Git status.
- Downloaded Granite was integrated into the local llama-swap service and passed
  real chat and tool-selection smoke checks. Both services remain active.

## Live work — observe before taking action

| Component | Identity | State at snapshot |
| --- | --- | --- |
| Qwen base evaluator | PID `954658`, Linux start ticks `7853761`, exec session `51587` | Live, 27 results |
| Sequential comparison driver | PID `987032`, start ticks `8013726`, exec session `46886` | Live, waiting for base |
| Base vLLM backend | `powercoder-qwen-base-domain-r1`, `http://127.0.0.1:8101` | Adopted by driver |
| Authoritative driver journal | `training/unsloth/out/agent-domain-r2/pipeline-scorecards.jsonl` | Last event `adopt_base` |

The backend's name contains `r1`; the current evaluation output is **r2**.
Individual requests can take minutes at roughly 19 tokens/second. An unchanged
result count, expired observation session, or polling timeout does not establish
that work stopped. Verify PID **and start ticks**, actual process state, backend
logs, and the durable journal before intervening. Do not start a second driver,
overwrite output, or restart the evaluator simply because observation is slow.

Read-only inspection, from the repository root:

```bash
uv run --offline --no-sync python - <<'PY'
import json
from pathlib import Path
from training.run_comparison import process_state

root = Path("training/unsloth/out/agent-domain-r2")
events = [json.loads(line) for line in
          (root / "pipeline-scorecards.jsonl").read_text().splitlines()]
print("base:", process_state(954658))
print("driver:", process_state(events[0]["payload"]["pid"]))
print("completed:", len((root / "base/results.jsonl").read_text().splitlines()))
print("last event:", events[-1])
PY
podman logs --tail 10 powercoder-qwen-base-domain-r1
```

The driver command is:

```text
.venv/bin/python -m training.run_comparison --root training/unsloth/out/agent-domain-r2 --base-pid 954658 --base-container powercoder-qwen-base-domain-r1 --download-container powercoder-granite42-download-r1 --journal-name pipeline-scorecards.jsonl
```

This command documents the existing process; **do not run another copy**.
Earlier waiting drivers were deliberately replaced without restarting the base
evaluator to correct Granite GPU allocation and schedule numerical scorecards.
Their `pipeline.jsonl` and `pipeline-granite-memory.jsonl` remain historical
evidence. `pipeline-scorecards.jsonl` is current.

## Automatic sequence and acceptance evidence

`training/run_comparison.py` checks process identity and complete, consistent
306-task outputs before advancing. It will:

1. Finish Qwen base, stop its owned backend, evaluate the original Unsloth merged
   student into `student/`, then generate paired strict and numerical comparisons.
2. Verify the pinned Granite download; train Granite for 100 steps on the same
   273 training examples; independently reload its saved adapter and merge it.
3. Evaluate Granite base and student into `granite-base/` and `granite-student/`,
   then compare Granite with its base and with both Qwen variants.

All evaluation directories are under `training/unsloth/out/agent-domain-r2/`.
Expected strict comparison files are `qwen-comparison.json`,
`granite-comparison.json`, `granite-vs-qwen-base.json`, and
`granite-vs-qwen-student.json`. Numerical counterparts are
`qwen-numerical-comparison.json`, `granite-numerical-comparison.json`,
`granite-vs-qwen-base-numerical.json`, and
`granite-vs-qwen-student-numerical.json`.

Before declaring success, verify all four complete 306-task runs, their task/input
hashes and equal budgets, raw attempt journals, final summaries, paired reports,
and actual Granite training/reload/merge receipts. Report the measured gain and
uncertainty. **At least 10 percentage points is a requirement to assess, not a
result to assume.** If the experiment misses it, report that and scope further
work without changing the completed benchmark retrospectively.

The original strict agent metric requires matching real tool/study evidence as
well as a correct final answer. The separate `solver-verified-domain-v1`
numerical metric in `powercoder/inference/domain_scorecard.py` regrades saved
terminal answers with fresh physical solves. It issues no new model attempts
and gives no feedback to models. Report both metrics distinctly. Numerical
success does not establish zero fabrication or full G5; `g5_met` remains false
without the remaining general-Python/critical-fabrication suites.

The first saved report passed a numerical smoke check but failed strict tool
evidence. Receipt: `agent-domain-r2/numerical-grader-smoke.json` beneath the
output root. This single example is not a completed benchmark. Base attempts
include invalid tool requests; preserve those as model failures. Do not alter
prompts, tool schemas, scoring criteria, or generation budgets mid-run.

## Inputs, checkpoints, and training lineage

- Held-out tasks:
  `benchmarks/power-agent-bench-lite/results/domain-held-out-20261020/examples.jsonl`.
  SHA256 `f2523a141ca1f3160617647b595e2b3a7cfbd16c8bded70caf0a4430fed29bca`.
  Counts: 26 reports, 120 load-scale fits, 120 line-rating fits, 40 dispatch fits.
  Independent prompts/concrete inputs were audited against all original 500
  examples; this is not a held-out-topology/template experiment.
- Excluded original source: `powercoder/datasets/smoke/examples.jsonl`, SHA256
  `bb035acdd5760cab5338dec03893c69bed0590793f108805da34c02acc7f00b5`.
  Training split: `powercoder/datasets/smoke/splits/train.jsonl` (273 rows).
- Fixed evaluation budgets: one greedy attempt, temperature 0, at most 12 model
  turns, 24 tool calls, 2048 tokens per response, and 600-second HTTP timeout.
  Actual canonical MCP stdio calls and fresh study solves are recorded in
  `ex_*.jsonl`; results accumulate in `results.jsonl`.
- Qwen base revision: `Qwen/Qwen3.5-4B` at
  `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`.
  Use the **original Unsloth** student in
  `training/unsloth/out/merged-bf16`, with adapter in `qwen3.5-4b-lora`.
  Do not substitute the separate Axolotl reproduction.
  Adapter SHA256: `d749dd82e787625e5a217c8092eec06603a58c69236ff3cbf5a9385f64cde319`.
  Merged weights SHA256: `84a4ab6d5f39b17c38b4046444ec708d230ea642d5191a510beccaa3e0bee20f`.
  Thirteen adapter/merged files were rechecked without mismatches; receipt:
  `agent-domain-r2/qwen-student-integrity.json` beneath the output root.
- Granite: `ibm-granite/granite-4.2-8b`, Apache-2.0, revision
  `b3791992239dce12d0038f1f54a8adb7b02d59ab`.
  Download: `training/unsloth/out/granite-4.2-8b-base`, four shards totaling
  16,761,102,336 weight bytes. Download container
  `powercoder-granite42-download-r1` exited 0; all shard hashes matched pinned
  metadata. Receipt: `training/unsloth/out/granite42-download-verified.json`.
- Granite training implementation: `training/granite/train.py`; configuration:
  `training/unsloth/config.granite42.yaml`; guide: `training/granite/README.md`.
  This uses real Transformers/PEFT CUDA training, not Unsloth model patches.
  Same 273 rows and Qwen hyperparameters: 100 steps, BF16, LoRA rank 32/alpha 64,
  all-linear, dropout 0, effective batch 4, warmup 10, learning rate 2e-5,
  seed 42, sequence length 1024, AdamW 8-bit, cosine, weight decay 0.01.
  All 273 native Granite tokenizations passed supervision checks; maximum 281
  tokens. Training itself has **not yet run**.
  Expected output: `training/unsloth/out/granite42-sft-r1/`, including
  `granite42-8b-lora/`, `merged-bf16/`, `train_log.json`, `preflight.json`, and
  `hash_manifest.json`. The script refuses existing output and verifies source
  shards before allocating GPU.
- vLLM image ID:
  `d53cb735dd1822378c352da65b4ef1580c9764df7aed4bc8805c6c26f6b827de`
  (`localhost/vllm-lmcache:gb10`, vLLM 0.31.0).
  Training image ID:
  `74feb3e2e84cfde5d1d2d21c34213d60114d7eb7a80bb1f9352ff2dda15c00ff`
  (`localhost/unsloth-gb10-eval:local`).
  Granite inference uses GPU memory fraction 0.22, BF16, context 16384, one
  sequence, eager execution; 0.12 was insufficient for its weights.

Models, datasets, training outputs, and raw evaluation artifacts are intentionally
gitignored. A fresh clone alone cannot resume this experiment; these paths are
local to this host. Preserve historical failed/partial diagnostics, including
`agent-domain-r1/` and `eval306-r1-raw/`; neither is the current experiment.

## Granite through llama-swap — complete

Endpoint: **`http://127.0.0.1:8000/v1`**. Model ID: **`granite-4.2-8b`**;
alias: `ibm-granite/granite-4.2-8b`.

Source files and deployment guide are in
`configs/powercoder/llama-swap/`; registry entry is in
`configs/powercoder/models.yaml`. Installed configuration:

- `~/.config/llama-swap/config.yaml`; backup
  `config.yaml.bak-granite42-20261021` in the same directory.
- `~/.config/containers/systemd/granite42-vllm.container`;
  unit `granite42-vllm.service`, container `llama-vllm-granite42`.
- Backend shares the `llama-swap` container network namespace on private port
  18102 and uses the pinned local Granite weights/image offline.
  It is tied to `llama-swap.service`. Both units were verified active at this
  snapshot. Do not start the unrelated inactive `llama-vllm-27b.service`.

Real chat returned “Granite is ready.” A real alias request produced a parsed
`echo` tool call with `{"message":"ready"}`. These verify serving/tool parsing,
not domain accuracy. Receipts: `training/unsloth/out/granite42-llama-swap-smoke.json`
and `granite42-llama-swap-tool-smoke.json`. Installed/source config parity passed.
The backend is persistent: unloading the gateway placeholder does not evict
Granite weights. Leave these services available for the user.

## Committed implementation and validation

- `bbad284`: complete held-out agent evaluator, integrity checks, pinned Granite
  experiment; durable raw attempts and explicit failure outcomes.
- `c416703`: sequential driver and verified Granite training lineage.
- `d3b9b7b`: Granite llama-swap deployment and verification.
- `8442962`: separate solver-verified numerical scorecard and scheduled reports.

Latest relevant checks: **24 passed in 8.17 seconds**:

```bash
uv run --offline --no-sync python -m pytest \
  powercoder/inference/test_domain_scorecard.py \
  powercoder/inference/test_compare_agents.py \
  powercoder/inference/test_evaluate_agent.py \
  training/unsloth/test_evaluation.py \
  tests/integration/test_canonical_mcp_transport.py -q
```

These include a real AC solve on an explicitly named small fixture and actual
MCP stdio transport. They validate implementation, not student improvement.
Granite training and the full sequential pipeline have not yet completed an
end-to-end run.

Next action: inspect the live process identities and current journal, let the
existing pipeline advance, and audit each completed stage. If it exits with an
error, inspect the exact durable stage/log before changing anything. Follow
`AGENTS.md`, `docs/VISION.md`, and `docs/DEFINITION_OF_DONE.md`; use `uv`, preserve
real evidence, and report exact tool/host environment mismatches without silently
routing around them.
