# Upload Receipt Publish Scan Reuse

## Goal

Avoid redundant filesystem scans in the Python upload receipt publish path by reusing the file list already computed during publish-source preparation.

## Scope

- `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`

## Linux Constraint

This slice is limited to Python worker code that is locally verifiable on Linux. It does not touch Swift, macOS-only runtime behavior, or generated artifacts.

## Hypothesis

`UploadReceiptPipeline._prepare_publish_source()` already computes `published_files` for directory-based publishes, but `HuggingFacePublishBackend.publish()` rescans the same tree after the CLI upload finishes. Reusing the precomputed list should preserve behavior while reducing repeated directory traversal and temporary `Path` allocations.

## Implementation Plan

1. Add a way for `HuggingFacePublishBackend.publish()` to accept an optional precomputed `published_files` list.
2. Thread `PreparedPublishSource.published_files` through `UploadReceiptPipeline.run()` into the publish backend.
3. Preserve current fallback behavior when no precomputed list is supplied.
4. Add regression tests that prove the backend can reuse a provided file list without rescanning and that pipeline behavior remains unchanged.

## TDD Plan

1. Add a failing test for `HuggingFacePublishBackend.publish()` proving a provided `published_files` list is returned without calling `Path.rglob()`.
2. Run the targeted pytest selection and verify the new test fails for the expected reason.
3. Implement the minimal code to pass.
4. Re-run the targeted pytest selection and then the focused coverage command.

## Performance Probe

Use a synthetic large directory tree and compare:

- baseline: directory upload path that computes `published_files` via a second post-upload scan
- candidate: reuse the precomputed file list from `_prepare_publish_source()`

Probe outputs:

- mean wall time over repeated runs
- relative improvement ratio
- identical published file counts

## Success Metrics

- Focused tests pass.
- Changed executable scope coverage is at least 95%.
- The performance probe shows a measurable reduction in repeated publish-path wall time for large directory trees.
- `git diff --check` passes.
