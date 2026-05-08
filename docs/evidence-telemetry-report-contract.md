# Melix Evidence, Telemetry, And Report Contract

## Purpose

This specification defines the canonical source of truth for Melix run evidence,
stage probes, Apple Silicon telemetry, reports, and release evidence gates.

The design is best-path only:

- Melix targets macOS on Apple Silicon.
- Hardware telemetry implementation is Apple Silicon/macOS only.
- Telemetry uses a single implementation path with no alternate collectors.
- Melix does not implement a public leaderboard or community submission API.
- New evidence and report consumers read the current schema only.
- New evidence and report artifacts do not carry legacy export aliases.
- Logs, Markdown, CSV, and UI state are not sources of truth.

## Source Of Truth

`report.json` is the machine-readable source of truth for report verification,
release gates, and desktop report views.

Each report is derived from one or more run evidence artifacts. Each run
evidence artifact contains:

- run identity
- target, runtime, adapter, and dataset identity
- domain result payloads
- probe timeline
- Apple Silicon telemetry summary
- linked raw artifacts
- failure and fallback state

Markdown and CSV exports are derived views. They must never become the only
place where a metric, gate result, probe, or telemetry value exists.

## Run Evidence Envelope

Every benchmark, evaluation, event-extraction, and adapter/runtime check writes
an evidence envelope.

Required identity fields:

- `run_id`
- `schema_version`
- `melix_commit`
- `git_branch`
- `dirty_worktree`
- `run_kind`
- `started_at`
- `ended_at`
- `duration_ms`
- `status`
- `command`
- `artifact_root`

Required target and input fields:

- `target_model_id`
- `hf_repo_id`
- `task_kind`
- `model_snapshot`
- `adapter_id`
- `adapter_snapshot`
- `runtime_kind`
- `runtime_config`
- `dataset_ref`
- `dataset_revision`
- `suite_id`
- `sample_count`
- `input_digest`
- `prompt_template_digest`
- `generation_config`

Required diagnostic fields:

- `metrics`
- `probe_timeline`
- `telemetry_summary`
- `artifacts`
- `failure_summary`
- `fallback_summary`

## Probe Timeline

Every material stage records a structured probe. A missing probe is a verifier
failure for new evidence. Implementations must not infer zero duration from a
missing probe.

Required probe fields:

- `run_id`
- `trace_id`
- `span_id`
- `parent_span_id`
- `component`
- `phase`
- `started_at_monotonic_ms`
- `duration_ms`
- `status`
- `error_stage`
- `error_code`
- `attributes`

Allowed `component` values:

- `cli`
- `control_plane`
- `worker`
- `runtime`
- `adapter`
- `cache`
- `telemetry`
- `report`

Initial canonical phases:

- `cli_parse`
- `request_normalize`
- `target_resolve`
- `dataset_materialize`
- `sample_select`
- `prompt_render`
- `queue_wait`
- `worker_dispatch`
- `runtime_prepare`
- `model_load`
- `adapter_resolve`
- `adapter_load`
- `cache_lookup`
- `cache_restore`
- `prefill`
- `decode`
- `stream_assemble`
- `row_execute`
- `score_compute`
- `aggregate_result`
- `hardware_sample`
- `process_sample`
- `power_sample`
- `artifact_write`
- `report_generate`
- `export_write`
- `fallback_enter`
- `fallback_exit`

Probe attributes must be small structured JSON values. They must not contain
full prompts, responses, dataset rows, private credentials, or operator secrets.

Fan-out stages that can emit thousands of rows, such as evaluation samples, must
not expand every row into full per-sample probes. They must write aggregate
summary probes for the full population and may add only a bounded representative
sample set for slowest top-N, failed, skipped, and fallback samples. The bound
must be configurable at runtime, and reports must treat aggregate summary probes
as the source of count and duration metrics while using representative samples
only for diagnosis.

## Apple Silicon Telemetry

Melix hardware telemetry is scoped to macOS on Apple Silicon.

The collector records:

- CPU utilization
- P-core and E-core utilization
- GPU utilization
- GPU frequency
- GPU power
- CPU power
- ANE power
- DRAM power
- system power
- memory used and total
- thermal state
- process CPU and memory attribution

Each run records:

- telemetry time-series artifact path
- average and peak CPU utilization
- average and peak GPU utilization
- average and peak GPU frequency
- average and peak CPU power
- average and peak GPU power
- average and peak ANE power
- average and peak DRAM power
- average and peak system power
- watts per output token
- peak process memory
- average process CPU percent
- thermal events
- telemetry failures

Telemetry sampling runs off the hot path. Benchmark and evaluation execution
read only cached telemetry samples.

If IOReport or IORegistry sampling fails during a Melix run, the run records a
telemetry failure probe and report entry. Implementations must not synthesize
zero-watt or zero-duration values for missing telemetry.

## Process Attribution

Reports include process attribution for Melix and model runtimes.

Required process fields:

- `pid`
- `name`
- `role`
- `port`
- `bundle_prefix`
- `peak_memory_bytes`
- `avg_cpu_percent`
- `sample_count`

Required process groups:

- `primary_runtime_process`
- `control_plane_process`
- `worker_processes`
- `external_provider_processes`
- `process_tree_summary`

Attribution uses port, pid, process tree, and bundle prefix data so operators
can separate Melix control-plane cost, worker cost, runtime cost, and external
provider cost.

## Report Contents

Every report has these sections.

### Report Identity

- `report_id`
- `schema_version`
- `generated_at`
- `generator_name`
- `generator_version`
- `melix_commit`
- `git_branch`
- `dirty_worktree`
- `source_evidence_ids`
- `report_kind`

### Run Summary

- `run_id`
- `trace_id`
- `run_kind`
- `status`
- `started_at`
- `ended_at`
- `duration_ms`
- `command`
- `operator`
- `artifact_root`
- `failure_summary`
- `fallback_summary`

### Target And Input

- `target_model_id`
- `hf_repo_id`
- `task_kind`
- `model_snapshot`
- `adapter_id`
- `adapter_snapshot`
- `runtime_kind`
- `runtime_config`
- `dataset_ref`
- `dataset_revision`
- `suite_id`
- `sample_count`
- `input_digest`
- `prompt_template_digest`
- `generation_config`

### Result Metrics

Serving benchmark reports include:

- `prefill_tokens_per_second`
- `decode_tokens_per_second`
- `output_tokens_per_second`
- `ttft_ms`
- `request_p50_ms`
- `request_p95_ms`
- `tokens_in`
- `tokens_out`
- `peak_memory_bytes`
- `cache_hit_rate`
- `speculative_acceptance_rate`
- `dflash_rollback_count`

Evaluation reports include:

- `score`
- `pass_count`
- `fail_count`
- `error_count`
- `accuracy`
- `precision`
- `recall`
- `f1`
- `category_breakdown`
- `sample_failures`

Event-extraction reports include:

- `dialogue_count`
- `event_count`
- `valid_json_rate`
- `schema_valid_rate`
- `field_accuracy`
- `missing_event_count`
- `extra_event_count`
- `parse_error_count`

Adapter/runtime reports include:

- `adapter_load_ms`
- `adapter_activate_ms`
- `adapter_memory_bytes`
- `runtime_prepare_ms`
- `model_load_ms`
- `fallback_count`

### Probe Timeline Summary

- `probe_count`
- `slowest_phases`
- `phase_breakdown`
- `component_breakdown`
- `failed_phases`
- `skipped_phases`
- `fallback_phases`

Each phase summary includes:

- `phase`
- `component`
- `count`
- `total_duration_ms`
- `mean_duration_ms`
- `p95_duration_ms`
- `max_duration_ms`
- `status_counts`

### Apple Silicon Hardware Telemetry

- hardware identity banner
- average and peak utilization
- average and peak power
- average and peak GPU frequency
- watts per output token
- peak process memory
- process CPU summary
- thermal events
- telemetry failures
- telemetry time-series artifact links

### Process Attribution

- process list
- primary runtime process
- control-plane process
- worker processes
- external provider processes
- process tree summary

### Comparison Results

Comparison and release-gate reports include:

- `baseline_report_id`
- `current_report_id`
- `comparison_dimensions`
- `metric_deltas`
- `probe_deltas`
- `telemetry_deltas`
- `regressions`
- `improvements`
- `unchanged`
- `comparison_validity`

Each delta includes:

- `metric`
- `baseline`
- `current`
- `delta`
- `delta_percent`
- `direction`
- `gate_policy`
- `result`

### Gate Result

Release-gate and PR-evidence reports include:

- `overall_result`
- `gate_results`
- `informational_results`
- `known_gaps`
- `blocking_failures`
- `required_evidence_present`
- `required_probe_phases_present`
- `required_telemetry_present`

### Artifacts

- `evidence_json_path`
- `report_json_path`
- `markdown_report_path`
- `csv_export_paths`
- `probe_timeline_path`
- `telemetry_jsonl_path`
- `raw_output_paths`
- `logs_path`
- `screenshots_path`
- `coverage_path`

### Known Gaps And Notes

- `known_gaps`
- `instrumentation_gaps`
- `operator_notes`
- `non_blocking_warnings`

## Markdown And CSV Views

Markdown reports include:

- title and report identity
- hardware banner
- run summary table
- result metrics table
- gate summary
- probe summary
- telemetry summary
- comparison table
- known gaps
- artifact links

CSV exports are split by table:

- `runs.csv`
- `metrics.csv`
- `probe_phases.csv`
- `telemetry_summary.csv`
- `processes.csv`
- `gate_results.csv`
- `comparison_deltas.csv`

CSV exports do not preserve nested report structure.

## Verifier Requirements

The report verifier checks:

- report identity is complete
- source evidence exists
- run identity is complete
- target and input identity are complete
- required metrics exist
- required probe phases exist
- Apple Silicon telemetry summary exists
- telemetry failures are explicit
- gate policy is complete
- artifact links are resolvable
- missing telemetry or probes are not encoded as zero values

Reports that fail these checks cannot satisfy PR or release evidence.
