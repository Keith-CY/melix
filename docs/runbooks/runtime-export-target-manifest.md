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
