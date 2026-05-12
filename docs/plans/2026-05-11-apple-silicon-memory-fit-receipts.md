# Apple Silicon Memory Fit Receipts

## Scope

This slice implements the operator-facing unified-memory fit surface for issue
#638. It stays on the existing Hub model-card contract and does not add new
protobuf fields.

The implemented surface is:

- `melix estimate import <repo-id>` and `melix estimate import --repo-id <repo-id>`
- `melix estimate benchmark <repo-id>` and `melix estimate benchmark --repo-id <repo-id>`
- `melix estimate eval <repo-id>` and `melix estimate eval --repo-id <repo-id>`
- `melix estimate train <repo-id>` and `melix estimate train --model <repo-id>`
- JSON and text fit receipts for Hugging Face import, benchmark, eval, and
  training candidates
- optional `melix bench run --repo-id <repo-id> --preflight-fit-check`
- optional `melix eval run --repo-id <repo-id> --preflight-fit-check`
- optional `melix lora train --model-id <repo-id> --preflight-fit-check`
- `--allow-memory-risk` override for benchmark, eval, and training runs whose
  Hub estimate is `heavy` or `blocked`
- benchmark job parameter annotations, eval request parameters, and LoRA model
  operation extensions that persist the fit receipt summary in existing
  artifact paths

Task-specific activation, optimizer, dataset-cache, adapter, KV-cache, and
judge-memory estimators are recorded as explicit `unknown_fields` until Melix
has runtime estimators for those components.

## Design

The CLI receipt reuses the Hub card local-fit evidence already produced by the
Python model-ops worker:

- `estimated_resident_bytes` becomes `estimated_active_memory_bytes`
- `estimated_artifact_bytes` becomes `estimated_disk_usage_bytes`
- `local_fit_status` becomes the receipt `fit_status`
- `local_fit_reasons` become actionable receipt reasons

The Swift CLI adds the local Mac `ProcessInfo.processInfo.physicalMemory` value
as `total_unified_memory_bytes`. Melix is a macOS Apple Silicon application, so
this slice treats that value as the unified-memory capacity and does not
implement fallback collectors for other platforms.

The CLI also probes free disk capacity near the managed model root and reports
it as `available_disk_bytes` with a derived `disk_fit_status`. Disk fit uses the
Hub artifact-size estimate plus local free-space evidence; task-specific output
growth remains an unknown until run-specific artifact estimators exist.

Each receipt also includes `target_inputs` for CLI inputs that materially shape
the run, such as context length, dataset URI, LoRA adapter path, batch size, and
sample size. Target-specific assumptions and `unknown_fields` keep the receipt
honest when the Hub card estimate cannot model additional run memory.

## Probes And Metrics

Every estimate receipt carries a `probe` object with:

- `name`: `cli.memory_fit.<target_kind>`
- `hub_card_elapsed_ms`
- `receipt_elapsed_ms`

Benchmark, eval, and LoRA training preflight store stable memory-fit fields in
artifact parameters so exported results can be inspected without re-running Hub
discovery:

- `memory_fit_schema_version`
- `memory_fit_target_kind`
- `memory_fit_repo_id`
- `memory_fit_status`
- `memory_fit_estimated_active_memory_bytes`
- `memory_fit_estimated_disk_usage_bytes`
- `memory_fit_available_disk_bytes`
- `memory_fit_disk_status`
- `memory_fit_total_unified_memory_bytes`
- `memory_fit_safety_threshold_fraction`
- `memory_fit_unknown_fields`
- `memory_fit_receipt_json`

Success metrics for this slice:

- estimate JSON includes assumptions and unknown fields
- estimate text includes fit status, total memory, active memory estimate, disk
  estimate, reasons, and override guidance
- unsafe benchmark preflight blocks before `runBench` unless
  `--allow-memory-risk` is set
- unsafe eval preflight blocks before scheduling the eval job unless
  `--allow-memory-risk` is set
- unsafe LoRA training preflight blocks before scheduling the model operation
  unless `--allow-memory-risk` is set
- override benchmark preflight forwards the fit receipt summary into
  `ControlPlaneBenchRequest.parameters`
- override eval preflight forwards the fit receipt summary into eval request
  parameters
- override LoRA training preflight forwards the fit receipt summary into the
  model operation extension payload

## Verification

Run focused Swift parser and runner tests for:

- estimate import, benchmark, eval, and train parsing and command-codec support
- estimate import JSON/text rendering and target-specific JSON unknown fields
- benchmark preflight blocking behavior
- benchmark preflight override parameter persistence
- eval preflight blocking behavior
- eval preflight override parameter persistence
- LoRA training preflight blocking behavior
- LoRA training preflight override extension persistence

Run changed-scope coverage for touched Swift CLI files when coverage tooling is
available. If the local Swift coverage command is not available in this
environment, report it explicitly in the PR evidence.
