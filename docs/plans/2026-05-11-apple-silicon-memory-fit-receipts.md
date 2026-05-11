# Apple Silicon Memory Fit Receipts

## Scope

This slice implements the first operator-facing unified-memory fit surface for
issue #638. It stays on the existing Hub model-card contract and does not add
new protobuf fields.

The implemented surface is:

- `melix estimate import <repo-id>` and `melix estimate import --repo-id <repo-id>`
- JSON and text fit receipts for Hugging Face import candidates
- optional `melix bench run --repo-id <repo-id> --preflight-fit-check`
- `--allow-memory-risk` override for benchmark runs whose Hub estimate is
  `heavy` or `blocked`
- benchmark job parameter annotations that persist the fit receipt summary in
  the existing benchmark artifact path

Training and eval fit checks remain follow-up work for #638 because they need
task-specific activation, optimizer, dataset-cache, and KV-cache estimators.

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

## Probes And Metrics

Every estimate receipt carries a `probe` object with:

- `name`: `cli.memory_fit.<target_kind>`
- `hub_card_elapsed_ms`
- `receipt_elapsed_ms`

Benchmark preflight stores stable memory-fit fields in benchmark parameters so
the artifact export path can be inspected without re-running Hub discovery:

- `memory_fit_schema_version`
- `memory_fit_target_kind`
- `memory_fit_repo_id`
- `memory_fit_status`
- `memory_fit_estimated_active_memory_bytes`
- `memory_fit_estimated_disk_usage_bytes`
- `memory_fit_total_unified_memory_bytes`
- `memory_fit_safety_threshold_fraction`
- `memory_fit_receipt_json`

Success metrics for this slice:

- estimate JSON includes assumptions and unknown fields
- estimate text includes fit status, total memory, active memory estimate, disk
  estimate, reasons, and override guidance
- unsafe benchmark preflight blocks before `runBench` unless
  `--allow-memory-risk` is set
- override benchmark preflight forwards the fit receipt summary into
  `ControlPlaneBenchRequest.parameters`

## Verification

Run focused Swift parser and runner tests for:

- estimate import parsing and command-codec support
- estimate import JSON/text rendering
- benchmark preflight blocking behavior
- benchmark preflight override parameter persistence

Run changed-scope coverage for touched Swift CLI files when coverage tooling is
available. If the local Swift coverage command is not available in this
environment, report it explicitly in the PR evidence.
