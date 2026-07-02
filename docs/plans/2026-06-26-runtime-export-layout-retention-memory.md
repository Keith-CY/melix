# Runtime Export Layout Retention In-Memory Metrics Slice

## Context

`build_layout_metrics_report()` materializes each runtime export target layout and already builds the dry-run retention report for each manifest. The metrics aggregator then re-read the just-written retention JSON from disk to compute aggregate counts. That preserved behavior but added avoidable JSON decode and filesystem read work on the registered runtime export layout retention hot path.

## Slice

Keep the public `materialize_export_target_layout()` API unchanged, but route `build_layout_metrics_report()` through an internal helper that returns both the export report and the dry-run retention report produced during materialization. Dry-run and `cleanup="none"` metrics can then aggregate from the in-memory retention payload instead of calling `Path.read_text()` and `json.loads()` on the generated report.

## Registered Probe Coverage

The affected path is covered by the registered PR-scoped probe `runtime-export-layout-retention` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for:

- `services/mlx-worker-python/worker/productization/export_target_layout.py`
- `services/mlx-worker-python/tests/test_export_target_layout_retention.py`
- `scripts/runtime_export_layout_retention_probe.py`

## Verification Plan

- Add a regression guard to `test_layout_metrics_report_reuses_materialized_dry_run_retention_report` that fails if dry-run metrics use `Path.read_text()` to reload retention reports.
- Run the registered focused test command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux.
- Run the registered probe command locally on Linux and compare against `origin/main`.
- Use GitHub Actions PR-scoped performance validation as the merge gate.

## Expected Outcome

Runtime export layout retention metrics should preserve the same aggregate counts while reducing dry-run report aggregation overhead by avoiding redundant retention report read/decode work.
