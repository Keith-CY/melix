# Upload receipt remote-ref tail parsing

## Goal

Reduce memory pressure when `HuggingFacePublishBackend.publish(...)` extracts the final remote reference from verbose `hf upload` stdout.

## Linux-only constraint

This is a Python worker path and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic stdout parsing probe.

## Touched files

- `services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe definition

Measure extraction of the last nonblank line from a large synthetic stdout string. Compare the previous `reversed(stdout.splitlines())` approach with the new backward newline search helper.

Success metrics:

- Preserve the exact selected remote reference.
- Lower elapsed time and traced peak allocation for large stdout.
- Keep changed-scope coverage at or above 95%.

## Verification commands

- Focused pytest for the upload receipt tests touched by this slice.
- Coverage JSON plus `scripts/changed_scope_coverage.py` for touched Python files.
- Local synthetic tail-parse probe.
- `git diff --check`.

## PR-scoped performance CI

The existing `upload-receipt-published-files-scandir` scoped probe already watches the touched upload receipt file and test file. Its focused test and coverage commands are updated to include the new tail-parse regression tests so hosted head verification covers the new executable lines.
