# PowerCoder handoff — 21 October 2026

Snapshot: **10:46 AEDT (UTC+11)**. Branch: `chore/powercoder-recovery`.
Implementation HEAD: `a279d7b` (r3 driver); `8442962` ran r2.
Earlier revisions of this handoff: `b1a7b44`, `bb2a90c` (both describe a live
pipeline that no longer runs).

## Objective and honest completion status

The user requested committing local work, completing the full 306-task comparison
of Qwen3.5-4B base against its original Unsloth student, demonstrating at least a
**10 percentage-point domain pass@1 improvement**, downloading Granite 4.2 8B,
training it on the same dataset, and evaluating/comparing its base and student.
The detailed original request/audit is local to this host at
`/home/brianh/.codex/attachments/573df69a-e50a-4716-b01e-1e68b2cd83bc/pasted-text-1.txt`.
The goal record is `.pi/goals/active_goal_2026102108123965_mvh6j65n-98gogh.md`
(revision 4: contracts rewritten to match the real output files, auto-continue off).

**The experiment is incomplete. r3 is running supervised** (see "Live r3 run").
At 10:01 AEDT, on user
instruction, the r2 pipeline was stopped as unsupervised: driver PID `987032`,
Qwen base evaluator PID `954658`, its MCP child and `uv` wrappers (SIGTERM), then
`podman stop powercoder-qwen-base-domain-r1` (stopped, **not removed**). Granite
training and all other evaluations never started. Only Granite download and
llama-swap serving are done. Do not claim GRPO, the Windows audit, or the full G5
gate is complete on the strength of earlier goal records: the paused goal
`mvg58a4q-t1fzwh` marks M08/M09 `complete` with `evidence` fields that merely
restate their contracts.

### Partial r2 evidence (preserved, not a result)

`training/unsloth/out/agent-domain-r2/base/results.jsonl`: **31/306** results,
0 strict passes, 0 numerical passes, 1 tool-evidence pass, 11 empty answers. No
`summary.json`. This is **not a representative sample**: tasks run in subfamily
order, so the 31 are 26 `pf-report` + 5 `pf-load-scale-fit`, with no line-rating
or dispatch fits. The empty answers are a lead worth inspecting after a complete
run (e.g. whether reasoning exhausts the 2048-token response budget); do not change
the budget mid-benchmark to chase it. The driver journal
`pipeline-scorecards.jsonl` ends at `adopt_base`; it records no stop event because
the driver was killed. This section is the record of that stop.

Measured r2 throughput: 31 tasks in ~94 minutes (≈3 min/task), so one 306-task
run takes ≈15 h; four runs plus Granite training is roughly 2–3 days of GPU time,
and Granite 8B will be slower than the 4B.

## Why it stopped: memory, not slowness

GB10 memory is unified (121 GB shared by CPU and GPU). At 10:00 AEDT, 118 GB was in
use: the Qwen base vLLM (13 GB GPU), the then-persistent llama-swap Granite vLLM
(26 GB), and llama-swap's `qwen3.8-flash-next` llama-server loading. At **10:02:16**
the kernel's global OOM-killer killed that llama-server (pid 1026915), and pi's
requests through llama-swap returned HTTP 500 (`upstream command exited
prematurely`). Measured afterwards in isolation: `qwen3.8-flash-next` alone takes
≈96 GB used, leaving ≈21 GB available. At the time neither `training/run_comparison.py` nor
`training/granite/train.py` checked available memory before allocating (the
driver now does), so Granite
training (≥16.8 GB of weights alone) and a 0.22-fraction Granite eval backend
(≈26 GB) would very likely have been OOM-killed while flash-next was resident.

## llama-swap changes (applied 10:05–10:10 AEDT)

1. **Granite backend is on demand.** `configs/powercoder/llama-swap/granite42-vllm.container`
   no longer has `[Install] WantedBy=llama-swap.service`; the installed copy
   `~/.config/containers/systemd/granite42-vllm.container` matches it. It still
   stops with the gateway (`PartOf`). Start it only when needed:
   `systemctl --user start granite42-vllm.service`. Until then, `granite-4.2-8b`
   requests through the gateway fail its `/health` check. It is currently inactive.
2. **Idle unload.** `~/.config/llama-swap/config.yaml` gained `globalTTL: 600`
   (backup `config.yaml.bak-ttl-20261021`). Before, `/running` reported `"ttl":0`
   (never unload). The existing `unloadTimeout: 60` key is not an idle timeout.
   After restart `/running` reports `ttl: 600` for `qwen3.8-flash-next`.
3. `llama-swap.service` restarted; a real `qwen3.8-flash-next` chat returned
   HTTP 200 `ready` (cold load ≈80 s). `granite42-vllm.service` exited 137 when
   stopped (SIGKILL after stop timeout) and was `reset-failed` to inactive.
   The unrelated `llama-vllm-27b.service` remains inactive; leave it so.

Persistent proxy backends (`llama-vllm-27b`, `granite42-vllm`) are systemd units
that `globalTTL` cannot unload; they must be stopped explicitly before
memory-heavy PowerCoder stages.

## Live r3 run — observe before taking action

The r2 driver could only *adopt* an externally started base evaluator, so there
was never one supervising owner. Fixed in `d649e3d` + `a279d7b`:

- The driver serves and evaluates the Qwen base itself (same weights snapshot,
  image ID, budgets and evaluator command as r2).
- Before each vLLM serve and before Granite training it waits up to an hour for
  `MemAvailable` ≥ stage floor + 8 GiB margin (`memory_wait` / `memory_admitted`
  / `memory_refused`); pytest `training/test_run_comparison.py`.
- `scripts/launch_powercoder_comparison.sh` runs it as transient unit
  **`powercoder-agent-domain-r3`**; `systemctl --user stop` stops containers
  (ExecStop), then the driver and evaluator. No restart policy.
- First launch (10:33) died in 0.4 s: the readiness poll got
  `httpx.ReadError 104` from rootless port forwarding, which `serve()` did not
  tolerate. This was latent in r2, which never reached `serve()`, and would have
  killed it at the student stage. Evidence kept at
  `training/unsloth/out/agent-domain-r3-attempt1-readiness-reset/`.
- Relaunched 10:36:48. Base memory admitted with 127 GB available (the gateway's
  flash-next had TTL-unloaded), server ready, evaluator running.

```bash
systemctl --user status powercoder-agent-domain-r3
journalctl --user -u powercoder-agent-domain-r3 -f
tail -3 training/unsloth/out/agent-domain-r3/pipeline.jsonl
wc -l training/unsloth/out/agent-domain-r3/base/results.jsonl
```

Stop only with `systemctl --user stop powercoder-agent-domain-r3`; do not kill
PIDs by hand. Never relaunch into an existing root; the driver refuses it.

### Reproducibility finding (r3 task 1 vs r2 task 1)

Same task, same weights, temperature 0: the trajectories are identical through
the first two model turns and tool calls. They differ only in the solver
response's wall-clock `execution_time_s` (1.2655 vs 1.1948 s), which the MCP
tool returns to the model. That perturbs the prompt; on the next turn r2 called
`run_study_trial` while r3 spent all 2048 response tokens reasoning
(`finish_reason: length`), so the evaluator recorded `incomplete_generation`
with an empty answer. Consequences, for the user to decide (not changed
mid-run):

- Single-attempt greedy pass@1 is **not reproducible** between runs; paired
  base/student deltas carry this run-to-run noise on top of model differences.
- The 2048-token response budget is binding for Qwen3.5's reasoning; this is the
  observed mechanism behind r2's empty answers.

## Sequence and acceptance evidence (unchanged design)

`training/run_comparison.py` requires complete, consistent 306-task outputs
before advancing:

1. Finish Qwen base, stop its owned backend, evaluate the original Unsloth merged
   student into `student/`, then generate paired strict and numerical comparisons.
2. Verify the pinned Granite download; train Granite for 100 steps on the same
   273 training examples; independently reload its saved adapter and merge it.
3. Evaluate Granite base and student into `granite-base/` and `granite-student/`,
   then compare Granite with its base and with both Qwen variants.

Strict comparison files: `qwen-comparison.json`, `granite-comparison.json`,
`granite-vs-qwen-base.json`, `granite-vs-qwen-student.json`. Numerical
counterparts: `qwen-numerical-comparison.json`, `granite-numerical-comparison.json`,
`granite-vs-qwen-base-numerical.json`, `granite-vs-qwen-student-numerical.json`.
`compare_agents.py` reports pass@1 with paired uncertainty; it does **not** report
latency or peak memory, which the goal's Granite comparison asks for.

Before declaring success, verify all four complete 306-task runs, their task/input
hashes and equal budgets, raw attempt journals, final summaries, paired reports,
and actual Granite training/reload/merge receipts. Report the measured gain and
uncertainty. **At least 10 percentage points is a requirement to assess, not a
result to assume.** If the experiment misses it, report that and scope further
work without changing the completed benchmark retrospectively.

The strict agent metric requires matching real tool/study evidence as well as a
correct final answer. The separate `solver-verified-domain-v1` numerical metric in
`powercoder/inference/domain_scorecard.py` regrades saved terminal answers with
fresh physical solves; it issues no new model attempts and gives no feedback to
models. Report both metrics distinctly. Numerical success does not establish zero
fabrication or full G5; `g5_met` remains false without the remaining
general-Python/critical-fabrication suites. Smoke receipt (one example, not a
benchmark): `agent-domain-r2/numerical-grader-smoke.json`. Base attempts include
invalid tool requests; preserve those as model failures. Do not alter prompts,
tool schemas, scoring criteria, or generation budgets mid-run.

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
  `training/unsloth/out/agent-domain-r2/qwen-student-integrity.json`.
- Granite: `ibm-granite/granite-4.2-8b`, Apache-2.0, revision
  `b3791992239dce12d0038f1f54a8adb7b02d59ab`.
  Download: `training/unsloth/out/granite-4.2-8b-base`, four shards totaling
  16,761,102,336 weight bytes; all shard hashes matched pinned metadata.
  Receipt: `training/unsloth/out/granite42-download-verified.json`.
- Granite training implementation: `training/granite/train.py`; configuration:
  `training/unsloth/config.granite42.yaml`; guide: `training/granite/README.md`.
  Real Transformers/PEFT CUDA training, not Unsloth model patches. Same 273 rows
  and Qwen hyperparameters: 100 steps, BF16, LoRA rank 32/alpha 64, all-linear,
  dropout 0, effective batch 4, warmup 10, learning rate 2e-5, seed 42, sequence
  length 1024, AdamW 8-bit, cosine, weight decay 0.01. All 273 native Granite
  tokenizations passed supervision checks; maximum 281 tokens. Training has
  **not run**. Expected output: `training/unsloth/out/granite42-sft-r1/`
  (`granite42-8b-lora/`, `merged-bf16/`, `train_log.json`, `preflight.json`,
  `hash_manifest.json`); the script refuses existing output and verifies source
  shards before allocating GPU.
- vLLM image ID
  `d53cb735dd1822378c352da65b4ef1580c9764df7aed4bc8805c6c26f6b827de`
  (`localhost/vllm-lmcache:gb10`, vLLM 0.31.0). Training image ID
  `74feb3e2e84cfde5d1d2d21c34213d60114d7eb7a80bb1f9352ff2dda15c00ff`
  (`localhost/unsloth-gb10-eval:local`). Qwen eval backends use GPU memory
  fraction 0.12; Granite uses 0.22, BF16, context 16384, one sequence, eager
  execution (0.12 was insufficient for its weights).

Models, datasets, training outputs, and raw evaluation artifacts are intentionally
gitignored. A fresh clone alone cannot resume this experiment; these paths are
local to this host. Preserve historical failed/partial diagnostics, including
`agent-domain-r1/`, `agent-domain-r2/` and `eval306-r1-raw/`.

## Granite through llama-swap

Endpoint `http://127.0.0.1:8000/v1`; model ID `granite-4.2-8b`, alias
`ibm-granite/granite-4.2-8b`. Source files and guide: `configs/powercoder/llama-swap/`;
registry entry: `configs/powercoder/models.yaml`. Installed:
`~/.config/llama-swap/config.yaml` (backups `config.yaml.bak-granite42-20261021`,
`config.yaml.bak-ttl-20261021`) and
`~/.config/containers/systemd/granite42-vllm.container` (unit
`granite42-vllm.service`, container `llama-vllm-granite42`, private port 18102 in
the gateway's network namespace, pinned local weights/image, offline). Now on
demand — see "llama-swap changes" above.

Verified earlier the same morning, while the backend was persistent: real chat
returned “Granite is ready.”; an alias request produced a parsed `echo` tool call
with `{"message":"ready"}`. These verify serving/tool parsing, not domain accuracy.
Receipts: `training/unsloth/out/granite42-llama-swap-smoke.json` and
`granite42-llama-swap-tool-smoke.json`.

## Committed implementation and validation

- `bbad284`: complete held-out agent evaluator, integrity checks, pinned Granite
  experiment; durable raw attempts and explicit failure outcomes.
- `c416703`: sequential driver and verified Granite training lineage.
- `d3b9b7b`: Granite llama-swap deployment and verification.
- `8442962`: separate solver-verified numerical scorecard and scheduled reports.

Last recorded relevant checks: **24 passed in 8.17 seconds**:

```bash
uv run --offline --no-sync python -m pytest \
  powercoder/inference/test_domain_scorecard.py \
  powercoder/inference/test_compare_agents.py \
  powercoder/inference/test_evaluate_agent.py \
  training/unsloth/test_evaluation.py \
  tests/integration/test_canonical_mcp_transport.py -q
```

These include a real AC solve on an explicitly named small fixture and actual MCP
stdio transport. They validate implementation, not student improvement. Granite
training and the full sequential pipeline have never completed an end-to-end run.

Next action: let r3 advance and audit each completed stage from
`pipeline.jsonl`. Raise the reproducibility finding with the user before any
benchmark change; a change means a new run root, not editing r3. Follow `AGENTS.md`,
`docs/VISION.md`, and `docs/DEFINITION_OF_DONE.md`; use `uv`, preserve real
evidence, and report exact tool/host environment mismatches without silently
routing around them.
