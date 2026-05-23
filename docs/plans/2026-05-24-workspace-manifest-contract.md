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
