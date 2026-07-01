# Export target manifest retention direct checks

This Python-only performance slice is limited to retention-policy validation in
`worker.productization.export_target_manifest`.

## Registered probe

The affected path is covered by the existing `runtime-export-manifest-validation`
registered PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/export_target_manifest.py`
- `services/mlx-worker-python/tests/test_export_target_manifest_contract.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/export_target_manifest_metrics_report.py`
- `scripts/runtime_export_manifest_validation_probe.py`

## Slice

`_validate_retention_policy()` previously allocated an `expected_decisions`
dictionary on every manifest validation, then iterated it only to compare six
fixed fields. This slice replaces that per-call dictionary with module-level
enum/name bindings and direct fixed field comparisons. Validation semantics and
error strings remain unchanged.

## Verification plan

Run the registered focused tests, changed-scope coverage, and registered probe
locally on Linux before opening the PR. GitHub Actions PR-scoped performance is
the merge gate for the registered probe report.

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_export_target_manifest_contract.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_export_manifest_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_export_manifest_validation_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_export_target_manifest_contract.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_export_manifest_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_export_manifest_validation_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/export_target_manifest.py services/mlx-worker-python/tests/test_export_target_manifest_contract.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/export_target_manifest_metrics_report.py scripts/runtime_export_manifest_validation_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id runtime-export-manifest-validation --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/runtime_export_manifest_validation_probe.json
```

## Expected performance signal

The expected directional improvement is lower validation latency and peak
allocation during repeated manifest validation, with unchanged schema errors and
fixture coverage.
