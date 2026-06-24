# Runtime Export Target Manifest

## Purpose

The export target manifest is the schema-backed contract for materializing a
trained Melix adapter into a runtime-specific target. It is used when a local
workspace needs to represent Melix managed artifacts, Ollama, GGUF, and
MLX-compatible runtime exports without target-specific side channels.

The authoritative schema lives at
`packages/protocol/schema/workspace/v1/export_target_manifest.proto`. Generated
Swift and Python outputs under `packages/protocol/swift` and
`packages/protocol/python` are versioned artifacts and must be regenerated with
`make proto` after schema changes.

## File Name And Schema Version

Export target manifests use:

- file name: `export-target-manifest.json`
- schema version: `melix.export_target_manifest.v1`
- protobuf package: `melix.workspace.v1`

## Target Matrix

Each manifest records one target type and the runtime that can consume the
generated files.

| Target type | Runtime name | Required representation |
|---|---|---|
| `EXPORT_TARGET_TYPE_MELIX_MANAGED` | `melix` | Melix-local adapter or derived-model artifacts under the workspace export root. |
| `EXPORT_TARGET_TYPE_OLLAMA` | `ollama` | Ollama model metadata plus generated model package files. |
| `EXPORT_TARGET_TYPE_GGUF` | `gguf` | GGUF artifact files and an explicit verification waiver when local load is not possible. |
| `EXPORT_TARGET_TYPE_MLX_RUNTIME` | `mlx-lm` or `melix-mlx` | MLX-compatible runtime files with load-check requirements. |

Do not add target-specific JSON keys such as `ollama_state`, `gguf_options`, or
`mlx_sidecar`. Any target-specific information that operators or runtimes need
must fit inside the typed protobuf fields: target identity, source provenance,
quantization, generated files, runtime requirements, verification policy,
retention, evidence, or metrics.

## Required Sections

Every export target manifest must include:

- `schema_version`: the manifest contract version.
- `export_id` and `target_id`: stable identifiers for this export and target.
- `target_type`, `target_runtime`, and optional `target_runtime_version`.
- `workspace_project_id` and `workspace_manifest_path`.
- source references for adapter, derived model, and training dataset manifests.
- `base_model_id`, optional `base_model_revision`, `adapter_id`, and
  `adapter_snapshot`.
- `activation_mode`: whether the target is metadata-only, adapter-backed, a
  fused derived model, or a runtime registration.
- `quantization`: quantization format, bit width, group size, and source.
- `generated_files`, `required_files`, and optional `intermediate_files`.
- `runtime_requirements`: required runtime, binary, capabilities, and minimum
  resource requirements.
- `verification_policy`, `verification_status`, and optional waiver.
- `retention_policy`, `diagnostics_policy`, `evidence`, and `metrics`.

All paths inside the manifest must be relative POSIX-style paths. Absolute
paths, parent-directory traversal, duplicate separators, and Windows path
separators are invalid.

## File Rows

File rows are the durable inventory for the target. Every file row must include
a relative path, role, media type, SHA-256 digest, byte size, retention class,
source provenance, and redaction class.

Use these lists consistently:

- `generated_files`: files produced by export materialization.
- `required_files`: source manifests and inputs required to reason about the
  export.
- `intermediate_files`: logs, temporary plans, or diagnostic files that should
  remain inspectable but are not direct runtime inputs.

The aggregate counts and byte totals in `metrics` must match the file lists.

## Verification

Validate the checked-in fixture set:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python3 scripts/export_target_manifest_metrics_report.py \
  --output .runtime/export-target-manifest-validation.json
```

Run the PR-scoped performance probe:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python3 scripts/runtime_export_manifest_validation_probe.py
```

The probe reports validation latency, fixture count, schema error count,
manifest byte size, and generated file count. `schema_error_count` must remain
zero for the checked-in fixture set.

## Operator Inspection

Operators should inspect a manifest in this order:

1. Confirm `schema_version`, `target_type`, and `target_runtime`.
2. Confirm source provenance points back to the workspace, adapter, derived
   model, and training dataset manifests.
3. Review `quantization` and `runtime_requirements` before attempting local
   load or registration.
4. Review `verification_status` and any `verification_waiver`.
5. Use `generated_files` as the runtime-facing inventory.
6. Use `metrics` and the validation report as the machine-readable summary.

If a target cannot be represented without side channels, treat that as a schema
gap. Do not ship ad hoc manifest keys.

## Layout And Retention

The #1507 layout implementation consumes valid export target manifests and
materializes target directories under:

```text
exports/adapters/<adapter-id>/<adapter-snapshot>/<export-id>/targets/<target-type>/<target-id>/
```

The target directory contains the manifest, `artifacts/`, `intermediates/`,
`logs/`, `smoke/`, `diagnostics/`, and `retention/retention-report.json`.
Manifest file paths stay relative to this target directory.

Retention reports classify every file row before cleanup:

- required artifacts and evidence are retained;
- intermediates, caches, and temporary files are cleanable only after target
  verification has passed or been explicitly waived;
- runtime logs are retained until the manifest retention TTL expires.

Run the layout and retention report over the checked-in fixtures:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python3 scripts/export_target_layout_retention_report.py \
  --output .runtime/export-target-layout-retention.json
```

Run the PR-scoped performance probe:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python3 scripts/runtime_export_layout_retention_probe.py
```

The probe reports layout materialization latency, target count, retained bytes,
cleanable bytes, deleted file count, and retention decision count.

## Post-Export Smoke And Diagnostics

The #1508 plan defines the target-local evidence contract consumed by the
#1509 smoke runner and #1510 diagnostic parser. After #1507 materializes a
target directory, export verification writes:

- `smoke/smoke-receipt.json`: metadata, load, and generation check outcomes.
- `smoke/generation-preview.txt`: bounded diagnostic preview for generation
  capable targets.
- `diagnostics/diagnostics-receipt.json`: typed runtime failure diagnoses and
  operator remedies.
- `diagnostics/redacted-log-excerpt.txt`: bounded, redacted excerpts for
  matched or unknown runtime failures.

Every smoke and diagnostic evidence path is relative to the target directory.
Operator summaries may display friendly labels, but exported reports must not
depend on absolute host paths.

The first smoke policy matrix covers these targets:

| Target type | Required smoke policy |
|---|---|
| `EXPORT_TARGET_TYPE_MELIX_MANAGED` | Manifest and digest inspection, Melix catalog/runtime load, and bounded generation when the target is generation-capable. |
| `EXPORT_TARGET_TYPE_OLLAMA` | Generated metadata inspection, runtime binary/path preflight, local load or registration, and bounded generation. |
| `EXPORT_TARGET_TYPE_GGUF` | GGUF header, metadata, byte-size, and digest inspection; local load and generation only when a compatible runtime is configured. |
| `EXPORT_TARGET_TYPE_MLX_RUNTIME` | MLX config, tokenizer, weight inventory, runtime path preflight, bounded load, and bounded generation. |

Waivers are allowed only for configured runtime unavailability, incompatible
hosts, metadata-only targets, known runtime bugs, or operator manual
verification with replacement evidence. Waivers are not allowed for unsafe
paths, missing required files, digest mismatches, unsupported target types,
missing source provenance, or a missing target manifest.

Diagnostic receipts cover common runtime failures such as load failure,
unsupported architecture, duplicate tensor names, missing blobs, missing
binaries, invalid runtime paths, timeout, permission denial, insufficient
memory, and unknown failures. CLI, Desktop, Markdown summaries, and CSV exports
must render typed remedies from `diagnostics-receipt.json`; they must not parse
raw runtime logs independently.

Redaction follows the workspace manifest policy and the target manifest
redaction classes. Exported summaries and operator-facing evidence must omit or
redact credentials, bearer tokens, API keys, proxy secrets, certificates,
absolute host paths, full prompts, full responses, dataset rows, private prompt
templates, and unnecessary user identity strings.
