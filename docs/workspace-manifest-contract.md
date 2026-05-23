# Melix Workspace Manifest Contract

## Purpose

The workspace manifest is the schema-backed contract for a Melix project
workspace. It joins project identity, artifact roots, workspace artifacts,
provenance references, schema version, and redaction policy in one
machine-readable `workspace-manifest.json`.

The authoritative schema lives at
`packages/protocol/schema/workspace/v1/workspace_manifest.proto`. Generated
Swift and Python outputs under `packages/protocol/swift` and
`packages/protocol/python` are versioned artifacts and must be regenerated with
`make proto` after schema changes.

## File Name And Schema Version

Workspace manifests use:

- file name: `workspace-manifest.json`
- schema version: `melix.workspace_manifest.v1`
- protobuf package: `melix.workspace.v1`

## Required Sections

Every workspace manifest must include:

- `schema_version`: the manifest contract version.
- `project`: stable project identity, display name, owner, and timestamps.
- `artifact_roots`: named storage roots for workspace, jobs, runtime, or
  external artifact locations.
- `artifacts`: typed artifact entries with root id, relative path, optional
  artifact schema version, media type, byte size, digest, and provenance refs.
- `provenance`: named source references for imports, dataset generation,
  training, evaluation, export, reports, or evidence.
- `redaction_policy`: policy id, mode, absolute-path handling, operator
  identity handling, and field-level redaction rules.

## Artifact Types

The v1 contract represents these workspace artifact categories:

| Artifact type | Intended content |
|---|---|
| `WORKSPACE_ARTIFACT_TYPE_RAW_INPUTS` | Operator-imported raw documents, rows, images, logs, or local files before cleaning. |
| `WORKSPACE_ARTIFACT_TYPE_CLEANED_DATA` | Deduplicated, masked, segmented, or normalized intermediate data. |
| `WORKSPACE_ARTIFACT_TYPE_DATASET_VERSION` | Versioned training, evaluation, or benchmark dataset package manifests and sample roots. |
| `WORKSPACE_ARTIFACT_TYPE_ADAPTER` | LoRA, QLoRA, DoRA, preference, or component-scoped adapter package manifests and weights. |
| `WORKSPACE_ARTIFACT_TYPE_LOG` | Training, evaluation, export, or runtime logs that are kept as workspace evidence. |
| `WORKSPACE_ARTIFACT_TYPE_EXPORT` | Adapter-only, merged model, runtime target, or future GGUF/Ollama/MLX export manifests. |
| `WORKSPACE_ARTIFACT_TYPE_REPORT` | Operator-facing or machine-readable benchmark, evaluation, training, or export reports. |
| `WORKSPACE_ARTIFACT_TYPE_EVIDENCE_BUNDLE` | Release, compare, diagnostics, or run evidence bundles that support claims. |

Artifact paths inside the manifest are relative to a named `artifact_roots`
entry. Exported summaries must not require absolute local paths.

## Redaction Policy

The redaction policy is part of the manifest because workspace artifacts may
refer to local files, operator identity, prompts, responses, dataset rows,
credentials, proxy settings, or certificates. The validation summary must
return the policy id and redaction mode in machine-readable form so CLI,
Desktop, reports, and release gates can decide whether a manifest is safe to
display or export.

For local training and evaluation workspaces, use
`REDACTION_MODE_LOCAL_PATHS_AND_SECRETS` unless a stricter downstream policy is
defined. This mode keeps workspace artifact paths relative and requires
credentials, absolute host paths, operator identity, prompts, responses, and
dataset rows to be redacted or omitted from exported summaries.

## Validation Summary

The Python validator in
`worker.productization.workspace_manifest.validate_workspace_manifest_file`
parses the JSON manifest through the generated protobuf schema and returns
`WorkspaceManifestValidationReport`.

The report includes:

- `ok`
- `schema_version`
- `project_id`
- `redaction_policy_id`
- `redaction_mode`
- `fixture_count`
- `schema_error_count`
- `manifest_byte_size`
- `manifest_validation_latency_ms`
- `errors`

The checked-in fixture at
`services/mlx-worker-python/fixtures/workspace/m-courtyard-smoke.dev.v1/workspace-manifest.json`
is the development-time contract example for the U1.1.1 slice.

## Metrics

The schema-only validation probe is:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python scripts/workspace_manifest_metrics_report.py
```

It records manifest validation latency, fixture count, schema error count, and
manifest byte size. Later preflight and migration work must add runtime checks
without changing this schema contract unless a new schema version is introduced.
