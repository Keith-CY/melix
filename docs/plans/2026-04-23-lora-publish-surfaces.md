# LoRA Module 5 — Artifact export, publish, and distribution surfaces (issue #16)

## Context

Issue [#16](https://github.com/Keith-CY/melix/issues/16) tracks Module 5 from `docs/plans/2026-04-16-lora-capability-modules-and-commit-plan.md`: treat adapter-only artifacts, merged artifacts, and published remote artifacts as first-class product outputs across worker, registry, and CLI surfaces.

Most of the pipeline split already landed before this PR:

- `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py` already branches on `adapter_export` vs `merged_export`, validates the source descriptor per kind, stages adapter bundles distinctly, and tags `distribution_contract` + `parent_lineage` on the upload manifest.
- `services/mlx-worker-python/worker/model_ops/job_registry.py` already back-references publish state onto `adapters[*]` and `derived_models[*]` rows (`published_repo`, `publish_backend`, `publish_artifact_kind`, `publish_parent_lineage`, `published_state`).
- `docs/runbooks/phase-8-lora-adapter-workflow.md` already has an "Adapter-only export vs. merged publish" section with examples.

This PR closes the remaining operator-visible gaps.

## Scope

**In (one PR, three commit slices):**

### Slice 5.1 — `publishes` section in the registry snapshot

Add `_publish_registry()` to `ModelOpsJobRegistry` and emit a top-level `publishes: [...]` array alongside `adapters` / `derived_models` / `experiment_groups`. Each entry carries:

- identity: `job_id`, `status`, `receipt_path`
- target: `target_repo`, `published_url`, `published_ref`, `published_files`, `publish_backend`
- kind: `export_artifact_kind`, `source_artifact_kind`, `distribution_contract`
- lineage: `source_job_id`, `source_artifact_path`, `source_manifest_path`, `source_model`, `adapter_name`, `derived_model_id`, `activation_mode`, `parent_lineage` (raw)
- timing: `upload_duration_ms`

Two pytest cases in `test_maintenance_service.py`:

- `test_job_registry_snapshot_emits_publishes_section_for_adapter_and_merged_uploads` — asserts adapter + merged lineage fields survive the round trip; unrelated uploads stay out.
- `test_job_registry_snapshot_emits_empty_publishes_when_no_completed_uploads` — in-flight uploads don't leak.

### Slice 5.2 — CLI `lora publish` infers export kind + explicit `--export-kind`

Before this PR, `lora publish --manifest-path PATH` silently hardcoded `export_kind = merged_export`. Operators publishing an adapter via `--manifest-path adapter.json` got a confusing worker error ("merged export requires a fused derived-model") instead of a clear adapter publish.

Changes:

- New `--export-kind (adapter|merged)` flag on `lora publish`. Honored when provided.
- When `--manifest-path` is passed without `--export-kind`, read the manifest and infer from `schema_version` / `artifact_kind` / `activation_mode`:
  - `schema_version == "melix.lora_adapter_package.v1"` or `artifact_kind == "adapter"` → `adapter_export`
  - `schema_version == "melix.derived_text_model.v1"` or `activation_mode == "fused_derived_model"` → `merged_export`
  - `artifact_kind == "converted_model_bundle"` / `"quantized_model_bundle"` → `merged_export`
  - Otherwise refuse and tell the operator to pass `--export-kind` explicitly.
- Mismatched overrides (`--export-kind merged` with `--adapter-path`, or `--export-kind adapter` with `--merged-model-path`) are rejected.
- The codec round trip now emits `--export-kind merged` for the `--manifest-path` case so parse-back doesn't require a file on disk.

### Slice 5.3 — CLI `lora publishes list` / `show --job-id ID`

Parallel to the `lora experiments` pair from Module 3:

- `melix lora publishes list [--model-id MODEL_ID] [--json]` — fixed-width `JOB_ID / KIND / TARGET_REPO / SOURCE_JOB / ADAPTER/DERIVED` table, reading the new `publishes` snapshot section.
- `melix lora publishes show --job-id JOB_ID [--model-id MODEL_ID] [--json]` — detail view with export kind, distribution contract, target URL, source lineage (artifact + manifest paths, source job, adapter name / derived model id, activation mode), published files, and receipt path.

Text show output reuses the plain-string format (no raw `\t` characters) consistent with the `experiments show` rendering from PR #55.

**Out:**

- Proto schema changes — publishes ride on the JSON `registry_snapshot` response.
- Publish-to-local export path — current scope is remote publish only. A future "export without publish" slice (local artifact staging) would extend the same code shape but is not needed yet.
- Menubar surface for publishes — existing adapter / derived-model cards already show publish state via bundled fields. A dedicated publishes card is a follow-up once operators ask for it.

## Design notes

### Registry field pickers

`_publish_registry` reads `published_repo` with fallback to `target_repo` / `ext.target_repo`, and `upload_backend` with fallback to `publish_backend`. This matches the same field-picker logic the adapter and derived-model sections already use, so old-format manifests from pre-module upload receipts keep working.

### Adapter-via-`--manifest-path`

Previously impossible — `--manifest-path` auto-mapped to merged. Now `--manifest-path adapter.json` routes through the adapter publish path and the worker stages the adapter bundle as usual. This is the "publish this specific adapter manifest" ergonomic.

### Explicit `--export-kind` escape hatch

Manifest inference can fail on hand-written test fixtures or pre-module manifests without a `schema_version`. The `--export-kind` flag is an unambiguous way to force a decision; we emit a `usage` error listing both values when inference fails.

## Critical files

```
services/mlx-worker-python/worker/model_ops/job_registry.py           (+~80 lines)
services/mlx-worker-python/tests/test_maintenance_service.py          (+~125 lines)
Sources/MelixCLICore/MelixCLI.swift                                   (+~300 lines)
Sources/MelixCLICore/MelixCLICommandCodec.swift                       (+~10 lines)
Tests/MelixCLITests/MelixCLIParserTests.swift                         (+~150 lines)
Tests/MelixCLITests/MelixCLIRunnerTests.swift                         (+~170 lines)
docs/runbooks/phase-8-lora-adapter-workflow.md                        (+~25 lines)
docs/plans/2026-04-23-lora-publish-surfaces.md                        (this file)
```

## Verification

1. `PYTHONPATH=... pytest services/mlx-worker-python/tests/test_maintenance_service.py -q` — full suite 103 / 103 (added two new cases).
2. `swift test --filter "MelixCLIParserTests|MelixCLIRunnerTests"` — full suite 185 / 185 (added 13 new cases: 7 parser + 5 runner + 1 codec round-trip fix).
3. `make proto-check` — clean; no proto changes.

## Risks

- **Manifest inference false positives.** A hand-edited manifest that sets `artifact_kind: "adapter"` but actually points at a merged directory would still route through adapter publish. Worker-side validation (`_resolve_export_artifact_kind`) already catches the descriptor mismatch and errors with "Adapter export requires an adapter artifact_path." — so the failure mode is a clear error, not silent corruption.
- **`publishes` array unbounded growth.** Every completed upload job adds one entry. In practice `snapshot()` also emits the entire `jobs` array, which has the same cardinality, so publish history is not the dominant size. If it becomes so, `_publish_registry` can gain a recency cutoff or pagination hint.
- **Backward compatibility with manifest-path → merged default.** Callers relying on the old implicit routing break visibly (clean error message, not silent misbehavior). The codec round-trip was updated to emit `--export-kind merged` so existing `MelixCLICommand` → args → parse flows stay consistent.
