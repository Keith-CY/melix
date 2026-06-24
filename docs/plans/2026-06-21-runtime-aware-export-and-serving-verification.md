# Runtime-Aware Export And Serving Verification Plan

## Goal

Define the Melix M3 runtime-aware export and serving verification contract for
issue #1504 so exported adapters and fused models have target-specific
manifests, retention policy, smoke checks, diagnostics, waiver semantics, and
serving evidence before a target can be reported as export-complete.

## Architecture

Export planning starts from Melix adapter and derived-model provenance, then
materializes one target directory per runtime target under the owning project
workspace. The Python worker owns export materialization, artifact accounting,
smoke execution, diagnostic parsing, and evidence writing because it already
owns model-ops job execution. The Swift control plane, CLI, and Desktop consume
the same target manifests and export evidence; they do not infer export success
from local files, subprocess exit codes, or ad hoc logs.

M3 is split into two plan issues and four executable unit issues:

- #1505 / P3.1 defines the multi-target export contract.
- #1506 / U3.1.1 defines export target manifests for Melix, Ollama, GGUF, and
  MLX-compatible runtimes.
- #1507 / U3.1.2 implements export artifact layout and retention policy.
- #1508 / P3.2 defines post-export smoke and diagnostics.
- #1509 / U3.2.1 adds bounded load and generation smoke checks.
- #1510 / U3.2.2 adds export failure diagnostics from runtime logs.

## Existing Anchors

- `docs/reference-scans/m-courtyard-lessons.md` identifies multi-target export,
  post-export smoke tests, export failure diagnostics, and serving exported
  artifacts as the M3 improvement direction.
- `docs/plans/2026-05-24-m-courtyard-improvement-roadmap.md` maps #1504 through
  #1510 into the M3 milestone, plan, and unit hierarchy.
- `docs/workspace-manifest-contract.md` already defines
  `WORKSPACE_ARTIFACT_TYPE_EXPORT`, `WORKSPACE_ARTIFACT_TYPE_LOG`, and
  `WORKSPACE_ARTIFACT_TYPE_EVIDENCE_BUNDLE`.
- `docs/runbooks/phase-8-lora-adapter-workflow.md` defines current adapter
  manifests, activation manifests, and manual serving verification expectations.
- `docs/evidence-telemetry-report-contract.md` defines evidence-mode probe
  timelines, redaction expectations, `artifact_write`, `export_write`,
  `model_load`, `adapter_load`, and serving diagnostics bundle boundaries.
- `services/mlx-worker-python/worker/productization/benchmark_export.py`
  currently exports benchmark and evaluation bundles; it is not the source of
  truth for target-specific model export success.
- `packages/protocol/schema/worker/v1/maintenance.proto` exposes
  `ExportResults` for current model-ops result export. M3 target export may add
  new schema fields or a new operation only when a unit issue proves that the
  existing model-ops operation shape cannot carry the contract cleanly.

## Non-Goals

- Do not copy code, assets, or implementation structure from the reference
  project.
- Do not mark a target successful because files exist, a conversion command
  returned zero, or a bundle was copied.
- Do not make Desktop or CLI parse runtime logs independently from the shared
  diagnostic parser.
- Do not require network publication, Hugging Face upload, or remote registry
  mutation to prove local export success.
- Do not delete or rewrite source adapter, dataset, training, or activation
  evidence during export cleanup.
- Do not expose absolute local paths, credentials, prompts, dataset rows, raw
  generation text beyond bounded previews, or private tokens in exported
  summaries.

## P3.1 Multi-Target Export Contract

P3.1 defines the stable target manifest, export plan, artifact layout, retention
policy, and report metrics before the executable units implement them.

### Export Target Manifest

Each target directory contains `export-target-manifest.json` with schema
`melix.export_target_manifest.v1`. The manifest must include:

- `schema_version`
- `export_id`
- `target_id`
- `target_type`
- `target_runtime`
- `target_runtime_version`
- `workspace_project_id`
- `workspace_manifest_path`
- `source_adapter_manifest_path`
- `source_derived_model_manifest_path`
- `source_training_dataset_manifest_path`
- `base_model_id`
- `base_model_revision`
- `adapter_id`
- `adapter_snapshot`
- `activation_mode`
- `quantization`
- `generated_files`
- `required_files`
- `intermediate_files`
- `runtime_requirements`
- `verification_policy`
- `verification_status`
- `waiver`
- `retention_policy`
- `diagnostic_policy`
- `evidence`
- `metrics`

Every `generated_files`, `required_files`, and `intermediate_files` row must
include:

- `path`: relative to the target directory or a named workspace artifact root
- `role`
- `media_type`
- `byte_size`
- `sha256`
- `retention_class`
- `source_provenance`
- `redaction_class`

Required `target_type` values are `melix_managed`, `ollama`, `gguf`, and
`mlx_runtime`. Unknown target types are rejected until a governing plan extends
the target matrix.

### Target Policies

`melix_managed` targets produce Melix-managed adapter or fused derived-model
artifacts usable by Melix sessions. Their smoke policy requires manifest
inspection, local catalog resolvability, load through the selected Melix
runtime path, and one bounded generation when the target is generation-capable.

`ollama` targets produce an Ollama-compatible model directory or model
registration bundle. Their smoke policy requires metadata inspection, runtime
binary/path preflight, load or registration check, and one bounded generation
with timeout.

`gguf` targets produce a GGUF file plus metadata and provenance for compatible
local runtimes. Their smoke policy requires header/metadata inspection,
file-size and digest verification, optional load smoke through a configured
compatible runtime, and an explicit waiver when no compatible runtime is
available.

`mlx_runtime` targets produce an MLX-compatible local model or adapter bundle
for `mlx-lm` or Melix MLX workers. Their smoke policy requires MLX metadata
inspection, local path preflight, runtime load, and one bounded generation with
timeout.

### Target Matrix And Unit Boundaries

P3.1 fixes the export target matrix before implementation starts. The first
schema-backed implementation slice must support exactly these targets:

`melix_managed`

- Produced artifact: Melix-managed adapter package or fused derived-model
  artifact.
- Runtime policy: resolvable by the Melix catalog and loadable through the
  selected Melix runtime path.
- #1506 responsibility: represent source adapter, derived model identity, base
  model, quantization, required files, runtime requirements, and verification
  policy without Melix-only side channels.
- #1507 responsibility: store target files under
  `targets/melix_managed/<target-id>/artifacts/`, retain manifests, evidence,
  required runtime artifacts, and classify temporary fusion outputs as cleanable
  after verification or waiver.

`ollama`

- Produced artifact: Ollama-compatible model directory, blob set, or
  registration bundle.
- Runtime policy: prove runtime binary/path readiness and either load or
  register the target before bounded generation.
- #1506 responsibility: represent Modelfile or equivalent registration inputs,
  generated blobs, base model linkage, runtime requirements, and verification
  policy without reading Ollama state as the source of truth.
- #1507 responsibility: store generated runtime files, logs, and registration
  evidence under `targets/ollama/<target-id>/`; keep manifests and smoke
  evidence while classifying transient import/cache files as cleanable.

`gguf`

- Produced artifact: GGUF file plus metadata and provenance for compatible
  local runtimes.
- Runtime policy: verify header, digest, byte size, and metadata. Load or
  generation smoke may be waived only when no compatible local runtime is
  configured.
- #1506 responsibility: represent GGUF metadata, quantization, source
  provenance, required file digest, compatible runtime requirements, and the
  explicit waiver policy for unavailable local runtimes.
- #1507 responsibility: store the GGUF artifact under
  `targets/gguf/<target-id>/artifacts/`; retain the GGUF file and evidence, and
  classify conversion scratch files as cleanable.

`mlx_runtime`

- Produced artifact: MLX-compatible local model or adapter bundle for `mlx-lm`
  or Melix MLX workers.
- Runtime policy: pass local path preflight, MLX metadata inspection, runtime
  load, and bounded generation.
- #1506 responsibility: represent MLX config, tokenizer, weight files, adapter
  or fused mode, base model linkage, runtime requirements, and verification
  policy.
- #1507 responsibility: store MLX bundle files under
  `targets/mlx_runtime/<target-id>/artifacts/`; retain runtime-required files and
  evidence while marking conversion intermediates and temporary logs according to
  the retention report.

The #1506 unit owns the checked-in schema, fixtures, validator, and manifest
metrics for this matrix. The #1507 unit owns materializing the directory layout,
retention report, cleanup dry-run/apply behavior, and byte-accounting metrics.
Neither unit may introduce a fifth target type or a target-specific side
channel without updating this plan first.

### Export Plan Receipt

Before materializing artifacts, export planning writes
`export-plan-receipt.json` with schema `melix.export_plan_receipt.v1`. It must
include:

- `schema_version`
- `export_id`
- `source_artifacts`
- `requested_targets`
- `resolved_targets`
- `blocked_targets`
- `target_policies`
- `estimated_artifact_bytes`
- `estimated_intermediate_bytes`
- `workspace_manifest_path`
- `operator_failures`
- `metrics`

Required planning metrics:

- `export_planning_latency_ms`
- `target_count`
- `blocked_target_count`
- `estimated_artifact_bytes`
- `estimated_intermediate_bytes`
- `manifest_validation_latency_ms`

Planning may block individual targets without blocking all targets. The final
export report must preserve both successful and blocked target rows.

### Artifact Layout

M3 export artifacts are rooted under the workspace export artifact root when a
workspace manifest is provided. The default layout is:

```text
exports/
  <export-id>/
    export-plan-receipt.json
    export-report.json
    targets/
      <target-type>/
        <target-id>/
          export-target-manifest.json
          artifacts/
          intermediates/
          logs/
          smoke/
            smoke-receipt.json
            generation-preview.txt
          diagnostics/
            diagnostics-receipt.json
            redacted-log-excerpt.txt
    retention/
      retention-report.json
```

The target directory is the only authority for target-relative generated file
paths. Workspace manifests may link those files as
`WORKSPACE_ARTIFACT_TYPE_EXPORT`, logs as `WORKSPACE_ARTIFACT_TYPE_LOG`, and
smoke or diagnostic receipts as `WORKSPACE_ARTIFACT_TYPE_EVIDENCE_BUNDLE`.

### Retention Policy

Retention decisions use schema `melix.export_retention_report.v1`. Every file
discovered under an export target must receive exactly one retention row with:

- `path`
- `target_id`
- `retention_class`: `required`, `evidence`, `runtime_log`, `intermediate`,
  `cache`, or `temporary`
- `decision`: `retain`, `cleanable`, `delete_after_success`, or
  `delete_after_ttl`
- `byte_size`
- `sha256`
- `reason`
- `safe_to_delete`

Retention classes have these default decisions:

| Retention class | Default decision | Condition / notes |
|---|---|---|
| `required` | `retain` | Always retained. |
| `evidence` | `retain` | Always retained. |
| `runtime_log` | `delete_after_ttl` | After diagnostics complete. |
| `intermediate` | `cleanable` | After target verification passes or is explicitly waived. |
| `cache` | `cleanable` | After the target manifest records source provenance and digest. |
| `temporary` | `delete_after_success` | After target verification passes or is explicitly waived. |

Cleanup must preserve target manifests, export reports, smoke receipts,
diagnostic receipts, redacted evidence excerpts, and required runtime artifacts.
Cleanup must never remove source adapter manifests, training manifests, dataset
version manifests, workspace manifests, or release compare evidence.

Required retention metrics:

- `artifact_byte_size`
- `required_byte_size`
- `evidence_byte_size`
- `cleanable_byte_size`
- `retention_decision_count`
- `retention_scan_latency_ms`

### P3.1 Acceptance Closure For #1505

#1505 is the plan-level contract for P3.1. It is complete when this document is
the governing plan for the multi-target export contract and the executable
units can proceed without inventing schema, layout, retention, or metric
semantics during implementation.

Acceptance mapping:

| #1505 acceptance criterion | Governing section in this plan |
|---|---|
| The plan defines an export target manifest schema and target-specific policy. | `Export Target Manifest`, `Target Policies`, and `Target Matrix And Unit Boundaries`. |
| The plan defines artifact layout and retention behavior before implementation. | `Artifact Layout` and `Retention Policy`. |
| The unit issues cover both manifest definition and artifact layout. | `Target Matrix And Unit Boundaries`, `Verification Plan`, and `Delivery Order` assign schema/fixtures to #1506 and layout/retention to #1507. |
| The plan records export planning, artifact size, and retention metrics. | `Export Plan Receipt`, `Retention Policy`, and `Performance Probes And Metrics`. |

This #1505 slice is documentation-only. It does not change protobuf schemas,
fixtures, worker code, CLI commands, or Desktop surfaces. Runtime metrics for
this slice are therefore `N/A`; the required measurement points are specified
above and must become executable probes in #1506 and #1507 before code changes
land.

## P3.2 Post-Export Smoke And Diagnostics

P3.2 defines how export completion is proven for each target and how failures
become typed operator diagnostics.

### P3.2 Target Smoke Matrix

P3.2 consumes the target directories and retention contract produced by #1507.
Each target smoke runner reads the target manifest, writes evidence only under
the target-local `smoke/` and `diagnostics/` directories, and updates the
export report from those receipts. The runner must not infer success from
runtime cache state, ad hoc stdout, or files outside the target directory.

| Target type | Metadata check | Load check | Generation check | Waiver boundary |
|---|---|---|---|---|
| `melix_managed` | Validate manifest, required file digests, activation mode, quantization, and catalog-resolvable target identity. | Load through the selected Melix runtime path or model catalog without mutating source adapter evidence. | Required when the target is generation-capable; use a synthetic prompt, fixed token cap, timeout, and preview byte cap. | `metadata_only_target` only for metadata-only exports; runtime failures require diagnostics before waiver. |
| `ollama` | Validate generated model metadata, registration inputs, required blobs, runtime binary/path preflight, and target-local log path. | Prove load or registration through the configured local Ollama runtime with bounded timeout. | Required after load or registration succeeds. | `runtime_not_installed`, `runtime_incompatible_host`, `known_runtime_bug`, or `operator_manual_verification` with replacement evidence. |
| `gguf` | Validate GGUF header, declared metadata, byte size, digest, quantization, and compatible runtime requirements. | Required when a compatible local runtime is configured; otherwise the load check is `waived`. | Required only when the configured compatible runtime supports generation. | No-compatible-runtime cases may use `runtime_not_installed` or `runtime_incompatible_host`; digest, header, and metadata failures are never waivable. |
| `mlx_runtime` | Validate MLX config, tokenizer, weight inventory, adapter or fused mode, runtime path, and required file digests. | Load with `mlx-lm` or the selected Melix MLX worker path using a bounded timeout. | Required for generation-capable targets with the same fixed prompt, token cap, timeout, and preview byte cap as Melix-managed targets. | `runtime_not_installed`, `runtime_incompatible_host`, `known_runtime_bug`, or `operator_manual_verification` with replacement evidence. |

The first implementation slice for #1509 should use a policy id such as
`bounded-local-v1`. The policy owns default timeout values, preview byte caps,
token caps, and the synthetic prompt fixture. The plan intentionally does not
standardize those numeric defaults in the planning slice; #1509 must pick
conservative defaults, test them, and record them in the receipt.

Smoke status is target-local:

- `passed`: metadata, required file digest, required load, and required
  generation checks passed.
- `failed`: one required check ran and failed with a typed failure or linked
  diagnostics receipt.
- `blocked`: a required check could not start because an earlier materialization
  or preflight requirement failed.
- `waived`: an allowed waiver records the skipped checks, reason, operator
  identity, replacement evidence, expiry, and follow-up issue when applicable.

### Smoke Receipt

Each target writes `smoke/smoke-receipt.json` with schema
`melix.export_smoke_receipt.v1`. It must include:

- `schema_version`
- `export_id`
- `target_id`
- `target_type`
- `policy_id`
- `status`: `passed`, `failed`, `blocked`, or `waived`
- `metadata_check`
- `load_check`
- `generation_check`
- `timeout_policy`
- `output_preview`
- `diagnostics_receipt_path`
- `operator_failures`
- `metrics`

Each `metadata_check`, `load_check`, and `generation_check` entry must include
`status`, `started_at`, `ended_at`, `duration_ms`, `timeout_ms`,
`failure_code`, `failure_message`, `evidence_path`, and `diagnostics_receipt_path`
when diagnostics are applicable. The receipt records target-relative paths only.

The metadata check is required for every target. The load check is required for
`melix_managed`, `ollama`, and `mlx_runtime` targets. The generation check is
required for generation-capable `melix_managed`, `ollama`, and `mlx_runtime`
targets. GGUF generation may be waived only when no compatible local runtime is
configured, and the waiver must record the missing runtime capability.

Bounded generation checks must use a repository-owned prompt fixture or a
synthetic non-private prompt, a fixed token limit, a timeout, and a preview byte
limit. The preview is diagnostic evidence only; it is not an evaluation score.
`output_preview` records byte count, content type, truncation status, digest,
and the target-relative `smoke/generation-preview.txt` path; it must not contain
full prompt text, full generated text, credentials, dataset rows, or private
operator input.

Required smoke metrics:

- `metadata_check_latency_ms`
- `load_smoke_latency_ms`
- `generation_smoke_latency_ms`
- `output_preview_byte_count`
- `timeout_count`
- `waiver_count`

### Completion Semantics

An export report uses schema `melix.runtime_export_report.v1` and has overall
status `completed` only when every requested target is in one of these terminal
states:

- `verified`: target manifest is valid, required files exist with matching
  digests, smoke policy passed, and retention report is written.
- `waived`: target manifest is valid, required files exist with matching
  digests, smoke policy did not pass or could not run, and an explicit waiver
  is recorded.
- `blocked`: target was requested but export planning or materialization failed
  with typed operator failures. Blocked targets prevent overall `completed`
  status unless the operator requested partial export semantics and the report
  records `partial_completion_allowed=true`.

The report must not use `completed` for a target when smoke evidence is missing,
when digest checks are absent, when a runtime log parser is still pending after
a failure, or when a waiver has no reason and operator identity.

Every export report target row must attach:

- `target_manifest_path`
- `retention_report_path`
- `smoke_receipt_path`
- `diagnostics_receipt_path` when present
- `verification_terminal_state`
- `verification_blocker_code`
- `waiver_id` when a waiver is used

The export report may summarize sensitive paths for operators, but the
machine-readable evidence paths remain target-relative so workspace exports do
not leak absolute host paths.

### Waiver Contract

Waivers use schema `melix.export_verification_waiver.v1` and must include:

- `waiver_id`
- `target_id`
- `target_type`
- `waived_checks`
- `reason`
- `operator_id`
- `created_at`
- `expires_at`
- `risk_level`: `low`, `medium`, or `high`
- `replacement_evidence`
- `follow_up_issue`

Allowed first-slice waiver reasons are:

- `runtime_not_installed`
- `runtime_incompatible_host`
- `metadata_only_target`
- `known_runtime_bug`
- `operator_manual_verification`

Waivers are not allowed for missing required files, digest mismatch, unsafe
paths, unsupported target type, missing source provenance, or missing target
manifest.

### Diagnostics Receipt

Failure diagnostics write `diagnostics/diagnostics-receipt.json` with schema
`melix.export_diagnostics_receipt.v1`. It must include:

- `schema_version`
- `export_id`
- `target_id`
- `target_type`
- `parser_policy_id`
- `status`: `matched`, `unknown`, or `not_applicable`
- `diagnoses`
- `redaction_summary`
- `bounded_log_excerpt_path`
- `operator_remedies`
- `metrics`

The diagnostics parser consumes target-local runtime logs, bounded subprocess
stderr/stdout captures, and smoke failure messages. It writes one receipt per
target and must finish before a failed smoke receipt can become a terminal
export-report row. CLI and Desktop render remedies from this receipt; they do
not parse raw logs independently.

Required diagnosis codes for #1510:

- `runtime_load_failed`
- `unsupported_architecture`
- `duplicate_tensor_name`
- `missing_blob`
- `missing_binary`
- `invalid_runtime_path`
- `runtime_timeout`
- `permission_denied`
- `insufficient_memory`
- `unknown_failure`

Each diagnosis row must include `code`, `severity`, `matched_pattern_id`,
`operator_message`, `remediation`, and a redacted evidence pointer. Unknown
failures preserve bounded redacted excerpts for later parser expansion.

### Log Redaction And Evidence Bounds

Runtime log diagnostics use the workspace redaction policy and the target
manifest redaction classes. The parser must redact or omit:

- absolute host paths, replacing them with target-relative evidence pointers
  when the path is under the target directory;
- credentials, bearer tokens, API keys, proxy secrets, certificate contents, and
  shell environment values that can carry secrets;
- full prompts, full generations, dataset rows, private prompt templates, and
  operator-entered free text beyond bounded previews;
- user identity strings when they are not required to explain the failure.

Unknown failures preserve `diagnostics/redacted-log-excerpt.txt` with byte and
line caps chosen by #1510. The receipt records `excerpt_byte_count`,
`excerpt_line_count`, `truncated`, `redaction_count`,
`redacted_absolute_path_count`, `redacted_secret_count`, and
`redacted_prompt_or_response_count`. Raw logs can remain in the target-local
`logs/` directory according to retention policy, but exported summaries and
operator-facing evidence use only redacted excerpts.

Required diagnostic metrics:

- `diagnostic_parser_coverage`
- `parsed_failure_count`
- `unknown_failure_count`
- `redaction_count`
- `diagnostic_latency_ms`

## Operator Surfaces

CLI, Desktop, and reports must render export state from the same report and
receipt files. Planned CLI shape:

```bash
melix export plan \
  --workspace-manifest path/to/workspace-manifest.json \
  --adapter-manifest path/to/train_lora.adapter.json \
  --derived-model-manifest path/to/activate_adapter.derived_model.json \
  --target melix_managed \
  --target ollama \
  --target gguf \
  --target mlx_runtime \
  --output exports/support-chat-v1/export-plan-receipt.json \
  --json
```

```bash
melix export run \
  --plan exports/support-chat-v1/export-plan-receipt.json \
  --output-root exports/support-chat-v1 \
  --smoke-policy bounded-local-v1 \
  --json
```

```bash
melix export diagnose \
  --target-manifest path/to/export-target-manifest.json \
  --log exports/support-chat-v1/targets/ollama/support-chat-ollama/logs/runtime.log \
  --output path/to/diagnostics-receipt.json \
  --json
```

Desktop should show per-target status, required/evidence/cleanable byte counts,
smoke status, waived checks, and typed remedies. It must not hide blocked
targets behind a single successful export banner.

## Evidence And Source-Of-Truth Rules

- `export-target-manifest.json` is the source of truth for target identity,
  generated files, runtime requirements, verification policy, and target-local
  evidence paths.
- `export-report.json` is the source of truth for overall export status and
  per-target terminal state.
- `smoke-receipt.json` is the source of truth for load and generation smoke
  outcomes.
- `diagnostics-receipt.json` is the source of truth for typed runtime failure
  diagnosis.
- `retention-report.json` is the source of truth for cleanup decisions and byte
  accounting.
- `workspace-manifest.json` indexes the artifacts for workspace consumers but
  does not replace the target manifest or receipts.

Markdown summaries, Desktop cards, and CSV exports are derived views.

## Performance Probes And Metrics

M3 units must add or reuse PR-scoped probes before implementation lands. Probe
IDs should be scoped to the changed unit:

| Unit | Probe direction |
|---|---|
| #1505 | Documentation-only planning slice; runtime metrics are `N/A`, with measurement points specified for the executable units. |
| #1506 | Manifest validation latency, fixture count, schema error count, manifest byte size. |
| #1507 | Layout materialization latency, retained bytes, cleanable bytes, deleted file count, retention decision count. |
| #1509 | Load smoke latency, generation latency, preview bytes, timeout count, waiver count. |
| #1510 | Diagnostic parser coverage, unknown failure count, redaction count, latency. |

Candidate PR-scoped probe names:

- `runtime-export-manifest-validation`
- `runtime-export-layout-retention`
- `runtime-export-smoke-policy`
- `runtime-export-diagnostic-parser`

Each executable unit must include a `test_command`, `coverage_command`, and
`probe_command` in `infra/perf/pr_scoped_probes.json` when it touches code. A
documentation-only slice may record `N/A` metrics with the reason.

## Verification Plan

### #1506 Manifest Unit

- Python schema/fixture tests for all four target types.
- Manifest validator tests for missing target type, unsafe paths, missing
  required file digest, unsupported target runtime, and unknown side-channel
  fields.
- Swift decoder tests only if CLI or Desktop consumes a new typed schema.
- Coverage command must include the manifest validator, fixtures, and PR-scoped
  probe registration tests.

#1506 implementation lands the manifest contract as a generated protobuf schema
under `packages/protocol/schema/workspace/v1/`, with versioned Python and Swift
outputs regenerated by `make proto`. The Python worker owns the first validator
and fixture metrics report under `worker.productization` because export
materialization is worker-owned; CLI and Desktop consumption remains follow-up
work unless a later unit needs new operator surfaces. Checked-in fixtures must
cover `melix_managed`, `ollama`, `gguf`, and `mlx_runtime` without `ext` fields
or target-specific side-channel keys. The registered PR-scoped probe for this
unit is `runtime-export-manifest-validation`, measuring validation latency,
fixture count, schema error count, and manifest byte size.

### #1507 Layout And Retention Unit

- Python export layout tests proving one directory per target and source
  adapter.
- Retention tests for required artifacts, evidence receipts, runtime logs,
  intermediates, caches, and temporary files.
- Cleanup dry-run and apply tests proving required files and evidence survive.
- Metrics tests for retained and cleanable byte counts.

#1507 implementation lands the worker-owned layout and retention module
described in
[`2026-06-24-export-artifact-layout-retention.md`](2026-06-24-export-artifact-layout-retention.md).
The registered PR-scoped probe for this unit is
`runtime-export-layout-retention`, measuring layout materialization latency,
target count, retained bytes, cleanable bytes, deleted file count, and retention
decision count. This unit does not run real conversion or post-export smoke;
it consumes valid target manifests and produces the layout, export report,
retention report, cleanup dry-run, and cleanup apply behavior that later smoke
and diagnostics units use.

### #1509 Smoke Unit

- Smoke policy tests for Melix-managed, Ollama, GGUF, and MLX runtime targets.
- Smoke receipt fixture tests for `passed`, `failed`, `blocked`, and `waived`
  terminal states.
- Timeout tests proving bounded generation cannot hang export completion.
- Waiver tests proving allowed waivers are recorded and disallowed waivers are
  rejected.
- Export-report gating tests proving targets cannot be marked verified without
  manifest validation, digest checks, smoke receipt, retention report, and
  diagnostics when a smoke failure occurs.
- CLI/Desktop decoder tests proving smoke status and preview metadata render
  from the shared receipt.

#1509 implementation lands the worker-owned smoke policy runner and receipt
fixtures for the four target types. The registered PR-scoped probe for this
unit is `runtime-export-smoke-policy`, measuring metadata check latency, load
smoke latency, generation smoke latency, output preview byte count, timeout
count, and waiver count. This unit may add CLI or Desktop decoding only when it
is needed to prove that operator surfaces consume the shared receipt instead of
raw logs or ad hoc status strings.

### #1510 Diagnostics Unit

- Parser fixture tests for each required diagnosis code.
- Redaction tests for absolute paths, tokens, credentials, and unbounded log
  excerpts.
- Unknown failure tests proving bounded excerpts are preserved.
- Export-report attachment tests proving diagnostics receipts are linked to
  failed smoke receipts and target rows.
- CLI/Desktop tests proving typed remedies and redacted evidence pointers are
  shown from the shared receipt.

#1510 implementation lands the worker-owned diagnostic parser, redaction
fixtures, and receipt writer. The registered PR-scoped probe for this unit is
`runtime-export-diagnostic-parser`, measuring parser coverage, parsed failure
count, unknown failure count, redaction count, and diagnostic latency. This unit
does not add new export target types or change retention cleanup semantics.

### P3.2 Acceptance Closure For #1508

#1508 is complete when this document is the governing contract for post-export
smoke and diagnostics and the executable units can proceed without inventing
target-specific smoke, waiver, diagnostic, redaction, or probe semantics during
implementation.

Acceptance mapping:

| #1508 acceptance criterion | Governing section in this plan |
|---|---|
| The plan defines target-specific load and generation smoke policies. | `P3.2 Target Smoke Matrix`, `Smoke Receipt`, and `#1509 Smoke Unit`. |
| The plan defines runtime log diagnostics and redaction rules. | `Diagnostics Receipt`, `Log Redaction And Evidence Bounds`, and `#1510 Diagnostics Unit`. |
| The unit issues cover both smoke checks and diagnostic parsers. | `P3.2 Target Smoke Matrix`, `Verification Plan`, and `Delivery Order` assign smoke checks to #1509 and diagnostics to #1510. |
| The plan records smoke-test latency and diagnostic parser coverage metrics. | `Smoke Receipt`, `Diagnostics Receipt`, and `Performance Probes And Metrics`. |

This #1508 slice is documentation-only. It does not change protobuf schemas,
fixtures, worker code, CLI commands, or Desktop surfaces. Runtime metrics for
this slice are therefore `N/A`; the required measurement points are specified
above and must become executable probes in #1509 and #1510 before code changes
land.

## Delivery Order

1. Land #1506 with target manifests, fixtures, and validation metrics.
2. Land #1507 with layout, retention report, cleanup dry-run, and byte
   accounting.
3. Land #1509 with smoke policies and completion gating.
4. Land #1510 with diagnostic parsers, redaction, and operator remedies.
5. Add the serve-exported-artifact shortcut only after a verified target can be
   selected from `export-report.json` without inspecting raw filesystem state.

## Acceptance Checklist For #1504

- Multi-target export and post-export diagnostic plans are linked from the M3
  roadmap and this document.
- The implementation units define probes for export duration, artifact size,
  smoke-test load latency, generation latency, and diagnostic parser coverage.
- Export completion semantics require target verification or an explicit
  recorded waiver.
- Child issues preserve Melix evidence and report source-of-truth rules through
  target manifests, export reports, smoke receipts, diagnostic receipts,
  retention reports, and workspace manifest links.
