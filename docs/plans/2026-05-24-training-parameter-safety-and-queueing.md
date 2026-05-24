# Training Parameter Safety And Queueing Plan

## Goal

Define the Melix P2.1 training safety contract for issue #1498 so local LoRA
training attempts are checked before worker launch and admitted through a
durable local queue before they consume Apple Silicon resources.

## Architecture

The Python worker remains the source of truth for trainability because it owns
model metadata interpretation, dataset package loading, adapter capability
resolution, and training execution. Swift CLI and Desktop surfaces consume
stable JSON receipts and stores; they do not reimplement model-family or
memory-fit rules.

P2.1 is split into two executable units:

- #1499 / U2.1.1 adds trainability guardrails for unsupported configurations.
- #1500 / U2.1.2 adds durable local training queue admission and status.

## Existing Anchors

- `services/mlx-worker-python/worker/model_ops/training_config.py` already
  normalizes adapter families, LoRA targets, training modes, quantized base
  support, dataset contracts, chunk sizes, and derived trainer settings.
- `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
  already resolves dataset sample counts before launching the training runner,
  which makes it the worker-side gate for no-launch failures.
- `Sources/MelixCLICore/MelixCLICommandCodec.swift` already carries
  `--preflight-fit-check` and `--allow-memory-risk` through LoRA workflows.
- `Sources/MelixCLICore/LoraTrainingJobStore.swift` already persists Desktop
  LoRA training jobs under `MELIX_HOME`.
- `docs/runbooks/phase-8-lora-adapter-workflow.md` documents the current LoRA
  training operator flow.

## Non-Goals

- Do not introduce a remote scheduler, cloud training queue, or multi-host
  resource allocator in P2.1.
- Do not make the Desktop app a second implementation of trainability rules.
- Do not launch a worker process when preflight or queue admission fails.
- Do not relax existing training-config validation to admit a run that the
  current worker cannot execute.
- Do not share queue state through the default `~/.melix` home when the
  operator has configured a worktree-local `MELIX_HOME`.

## U2.1.1 Trainability Guardrails

The trainability receipt schema is `melix.trainability_preflight.v1`. The
receipt must include:

- `schema_version`
- `status`: `ready` or `blocked`
- `model_id`
- `model_family`
- `dataset_format`
- `training_mode`
- `sample_count`
- `validation_sample_count`
- `checks`
- `operator_errors`
- `metrics`

Each check row must include:

- `code`
- `status`: `passed`, `blocked`, or `warning`
- `severity`
- `operator_message`
- `remediation`
- `details`

Required guardrail codes are:

- `unsupported_training_mode`
- `unsupported_full_finetune_quantized_base`
- `unsupported_model_family`
- `unsupported_lora_target_module`
- `unsafe_quantized_lora_target`
- `insufficient_training_samples`
- `sequence_length_exceeds_model_context`
- `training_memory_fit_failed`
- `invalid_dataset_package`

The Python worker should classify these guardrails before
`LoRATrainingRunner.train(...)` is called. Existing
`ModelOperationError` values from training-config normalization should be
wrapped into the receipt instead of being converted into unstructured log
strings.

The CLI and Desktop operator surfaces must show the same guardrail result by
reading the trainability receipt. When a guardrail is attached to a training
attempt, the run evidence must include a redacted path to the receipt and the
typed operator errors.

For local queue-backed training attempts, `melix jobs show --json` must attach
the trainability receipt as `trainability_preflight` when
`preflight_receipt_path` points to a `melix.trainability_preflight.v1` receipt.
The text renderer and Desktop job detail surface must show the receipt path,
blocking check code/message, and remediation so the operator does not need to
open raw logs to understand why a run is blocked.

Metrics:

- `preflight_latency_ms`
- `memory_estimate_latency_ms`
- `unsupported_configuration_count`
- `remediation_classification_count`
- `sample_count`
- `validation_sample_count`

Verification:

- Python unit tests for ready, unsupported target, quantized full fine-tuning,
  insufficient samples, sequence length, and memory-fit failures.
- Python pipeline test proving a blocked preflight writes evidence and does not
  invoke the training runner.
- Swift parser/codec tests for any CLI preflight options added in this unit.
- Desktop decoder tests proving the same receipt renders typed operator
  messages without shelling out to a second implementation.

## U2.1.2 Durable Local Queue Admission And Status

The local queue document schema is `melix.local_training_queue.v1`. The queue
is rooted under `MELIX_HOME` so parallel worktrees can keep independent
operator state when configured by the agent entry point.

The queue document must include:

- `schema_version`
- `queue_id`
- `updated_at`
- `jobs`
- `metrics`

Each job row must include:

- `job_id`
- `project_id`
- `workspace_manifest_path`
- `model_id`
- `dataset_id`
- `dataset_version_id`
- `adapter_name`
- `training_mode`
- `resource_class`
- `status`: `queued`, `running`, `cancel_requested`, `canceled`,
  `failed`, or `succeeded`
- `created_at`
- `updated_at`
- `preflight_receipt_path`
- `run_directory`
- `operator_errors`
- `recovery_policy`

Queue admission must be durable before any worker launch. Local Apple Silicon
training remains exclusive unless a later scheduler explicitly marks a resource
class as shareable. Cancellation and recovery transitions must also persist
before the CLI or Desktop reports them.

Queue operator errors may include `remediation`. Older queue documents without
that field must continue to decode with an empty remediation string. When a
known trainability guardrail is marked failed without an explicit remediation,
the store may fill the default guardrail remediation so CLI and Desktop expose a
single operator-facing recovery path.

Required queue error codes are:

- `training_queue_busy`
- `training_queue_job_not_found`
- `training_queue_state_invalid`
- `training_queue_restore_failed`
- `training_queue_cancel_failed`
- `training_queue_admission_failed`

Metrics:

- `queue_admission_latency_ms`
- `queue_restore_latency_ms`
- `queued_job_count`
- `running_job_count`
- `cancellation_latency_ms`
- `admission_refusal_count`

Verification:

- Swift store tests for queue round-trip, restore, exclusive admission,
  cancellation persistence, and malformed document handling.
- CLI parser/runner tests for queue status and admission surfaces.
- Desktop state and detail rendering tests proving queued and running jobs
  survive app reconstruction from the same `MELIX_HOME` and expose recovery
  policy, trainability preflight, and remediation fields.
- Python pipeline test proving queue admission failure prevents worker launch
  when the CLI attaches a queue token to the run.

Implementation slice:

- Add a Swift `LocalTrainingQueueStore` under `MelixCLICore` rooted at
  `MELIX_HOME/state/local-training-queue.json`.
- Make `melix lora train` persist an admitted queue row before invoking
  `train_lora`; if another non-terminal exclusive training job is present,
  return `training_queue_busy` before calling the worker.
- Project queue rows into the existing `melix jobs list/show/cancel` surfaces
  without changing the public `melix.job_summary.v1`,
  `melix.job_status.v1`, or `melix.job_cancel_result.v1` schemas.
- Project queue recovery policy, failure remediation, and attached
  trainability preflight receipts into CLI text/JSON and Desktop job detail
  views.
- Mark admitted rows `running` before worker launch and transition them to
  `succeeded` or `failed` after the synchronous operation returns.

## Delivery Order

1. Implement the trainability receipt and worker-side no-launch guardrails.
2. Add CLI and Desktop decoding for the shared trainability receipt.
3. Implement the durable queue store and exclusive local admission.
4. Wire queue status into CLI and Desktop views.
5. Update the LoRA runbook after both unit issues have executable evidence.
