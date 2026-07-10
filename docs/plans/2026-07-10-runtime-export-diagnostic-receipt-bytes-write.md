# Runtime export diagnostic receipt byte write slice

## Scope

This Python-only performance slice is limited to `worker.productization.export_target_diagnostics` receipt emission and diagnosis evidence-path construction. It keeps runtime export diagnostic behavior unchanged while reducing hot-loop overhead in the registered parser probe.

## Registered probe

The affected path is covered by the registered PR-scoped probe `runtime-export-diagnostic-parser` in `infra/perf/pr_scoped_probes.json`. The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/export_target_diagnostics.py`
- `services/mlx-worker-python/tests/test_export_target_diagnostics.py`
- `services/mlx-worker-python/tests/test_export_target_smoke_policy.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_export_diagnostic_parser_probe.py`

## Implementation plan

1. Preserve diagnostic receipt JSON bytes exactly, including sorted/indented JSON and trailing newline.
2. Avoid the extra text-write wrapper in the diagnostic receipt writer by encoding the JSON payload once and writing bytes directly.
3. Bind the line-number string conversion used by `_diagnoses_from_excerpt` evidence-path construction inside the hot diagnosis loop.
4. Run focused parser tests, changed-scope coverage, and the registered local probe on Linux.

## Success criteria

- Focused parser tests pass.
- Changed-scope coverage for the affected Python scope remains at or above 95%.
- The registered local probe preserves `diagnostic_parser_coverage=1.0` and shows a lower `elapsed_ms_mean` direction against the synced `origin/main` baseline.
- GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
