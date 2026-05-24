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
It validates the schema contract, but it does not materialize every referenced
workspace root under the fixture directory.

## Workspace Preflight Receipt

Workspace preflight is the U1.1.2 runtime validation layer on top of the
manifest schema validator. It does not change the protobuf schema and does not
modify existing workspaces. The Python entry point is
`worker.productization.workspace_manifest.preflight_workspace`; the CLI wrapper
is `scripts/workspace_manifest_preflight.py`.

Preflight returns stable JSON with:

- `schema_version`: `melix.workspace_preflight_receipt.v1`
- `status`: `ready` or `blocked`
- `workspace_manifest_schema_version`
- `project_id`
- `manifest_path`
- `checks`
- `metrics`

Each check is designed for CLI, Desktop, and report consumers to explain the
failure without reading raw logs. A check contains:

- `code`
- `status`
- `title`
- `detail`
- `recovery_hint`
- `items`

The U1.1.2 check codes are:

| Code | Meaning |
|---|---|
| `WORKSPACE_SCHEMA_CURRENT` | The manifest schema version is current. |
| `WORKSPACE_SCHEMA_STALE` | The manifest schema version is not supported by this Melix build. |
| `WORKSPACE_ROOT_EXISTS` | All path-backed artifact roots exist on disk. |
| `WORKSPACE_ROOT_MISSING` | A path-backed artifact root is missing. |
| `WORKSPACE_ARTIFACT_ROOTS_KNOWN` | All artifacts reference declared roots. |
| `WORKSPACE_ARTIFACT_ROOT_UNKNOWN` | An artifact references an undeclared root id. |
| `WORKSPACE_PATHS_SAFE` | Manifest root and artifact paths are safe relative paths. |
| `WORKSPACE_PATH_UNSAFE` | A manifest root or artifact path is absolute, escapes via `..`, uses backslashes, uses a Windows drive or UNC path, or otherwise violates safe relative path rules. |
| `WORKSPACE_ARTIFACTS_MANAGED` | Files under the Melix workspace root are represented by manifest artifacts. |
| `WORKSPACE_UNMANAGED_ARTIFACT` | A file under the Melix workspace root is not represented by manifest artifacts. |
| `WORKSPACE_MIGRATION_VALIDATED` | The workspace does not require migration. |
| `WORKSPACE_MIGRATION_REQUIRED` | The workspace needs an explicit future migration path; preflight will not mutate it. |
| `WORKSPACE_MANIFEST_INVALID` | Schema validation failed for errors outside the typed preflight categories. |

Preflight ignores `workspace-manifest.json` and the selected receipt output path
when scanning for unmanaged workspace files.

## Migration Validation

Existing workspaces whose manifest schema version differs from
`melix.workspace_manifest.v1` have an explicit non-migration path in U1.1.2:
preflight returns `WORKSPACE_SCHEMA_STALE` and
`WORKSPACE_MIGRATION_REQUIRED`, sets `status` to `blocked`, and includes a
recovery hint to open the workspace with a compatible Melix build or run a
future explicit migration command. The preflight command never edits the
manifest or workspace artifacts.

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

The preflight receipt probe is:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python \
  python scripts/workspace_manifest_preflight.py \
    --manifest services/mlx-worker-python/fixtures/workspace/m-courtyard-smoke.dev.v1/workspace-manifest.json \
    --output .runtime/workspace-preflight-receipt.json
```

It records:

- `preflight_latency_ms`
- `missing_root_count`
- `stale_schema_count`
- `unsafe_path_count`
- `unmanaged_artifact_count`
- `migration_validation_latency_ms`

Running preflight directly against the checked-in schema fixture returns
`blocked` until the referenced artifact roots and files are materialized in a
real workspace directory. That blocked receipt is still machine-readable and can
be attached to reports.
