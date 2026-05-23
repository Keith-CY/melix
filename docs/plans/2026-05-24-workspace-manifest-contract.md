# Workspace Manifest Contract Implementation Plan

## Goal

Define the Melix workspace manifest contract for issue #1492 / U1.1.1 so project identity, artifact roots, artifact types, provenance references, schema version, and redaction policy have a schema-backed source of truth.

## Architecture

The authoritative interface is a new `workspace/v1/workspace_manifest.proto` schema under `packages/protocol/schema`. Generated Swift and Python artifacts are regenerated through `make proto`; the Python worker owns the smallest validation helper and metrics probe for fixture validation. Documentation links the contract from the current LoRA and benchmark/evaluation artifact paths without adding preflight or migration behavior reserved for #1493.

## Steps

1. Add a failing Python fixture validation test that imports the generated workspace protocol, validates a checked-in fixture manifest, and asserts the machine-readable summary contains schema version, redaction policy, validation latency, fixture count, schema error count, and manifest byte size.
2. Add a fixture `workspace-manifest.json` covering raw inputs, cleaned data, dataset versions, adapters, logs, exports, reports, and evidence bundles.
3. Add the `workspace/v1/workspace_manifest.proto` schema and wire it into `scripts/proto_gen.sh`.
4. Regenerate protocol artifacts with `make proto`.
5. Implement the minimal Python validator and metrics report script needed by the fixture test.
6. Add a canonical workspace manifest contract doc, link it from `docs/README.md`, and reference it from the LoRA and benchmark/evaluation docs where they consume workspace artifacts.
7. Run focused tests, proto generation/checks, and the manifest metrics report.

## Metrics

The scoped metrics report for this schema-only slice is the manifest validation report. It records `manifest_validation_latency_ms`, `fixture_count`, `schema_error_count`, and `manifest_byte_size` for the checked-in fixture.

## U1.1.2 Workspace Preflight Slice

Issue #1493 builds on the v1 manifest validator without changing the protobuf
schema. The implementation adds a Python preflight receipt that dataset
preparation, training admission, CLI, Desktop, and reports can consume before
launching later workflow steps.

### Goal

Return typed operator-facing preflight results for existing workspace manifests:
missing roots, stale manifest schema versions, unmanaged artifacts, unsafe
paths, and manifest artifact references that cannot be resolved to known roots.

### Non-Goals

- Do not implement dataset ingest, training queue admission, or export cleanup.
- Do not mutate workspace manifests as part of migration validation.
- Do not introduce a new protobuf schema unless the JSON receipt proves
  insufficient for follow-on consumers.

### Receipt Contract

The preflight receipt uses schema version
`melix.workspace_preflight_receipt.v1` and stable JSON keys:

- `status`: `ready` when all blocking checks pass, otherwise `blocked`.
- `checks`: one entry per typed check, each with `code`, `status`, `title`,
  `detail`, `recovery_hint`, and `items`.
- `metrics`: `preflight_latency_ms`, `missing_root_count`,
  `stale_schema_count`, `unsafe_path_count`, `unmanaged_artifact_count`, and
  `migration_validation_latency_ms`.

The CLI script writes this receipt to stdout and, when requested, to an output
path that can be attached to report bundles. Operators must be able to explain a
blocked result from the receipt fields alone without raw logs.

### Migration Validation

Existing workspaces with a manifest schema version other than
`melix.workspace_manifest.v1` are not migrated automatically. Preflight returns
`WORKSPACE_SCHEMA_STALE` with a recovery hint that instructs the operator to
open the workspace with a compatible Melix build or run a future explicit
migration command. This is the safe non-migration path for U1.1.2.
