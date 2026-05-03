# PR-scoped Performance Report Result Loading Optimization

## Scope

This slice targets `scripts/pr_scoped_performance_report.py` result loading only.
It keeps the existing `os.scandir` discovery and stable filename ordering, but
parses each JSON result from binary file contents with `json.loads()` instead of
wrapping each file in a text decoder and calling `json.load()`.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe
`pr-scoped-performance-report-results-scandir` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for the report
loader, probe script, and PR-scoped performance tests.

## Verification Plan

This slice is Python-only and locally verifiable on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_performance_report_results_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_results_loader_uses_scandir_and_binary_json_reads services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_performance_report_results_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_cli_scripts_smoke
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_performance_report_results_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_report_results_loader_uses_scandir_and_binary_json_reads services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_performance_report_results_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_cli_scripts_smoke
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/pr_scoped_performance_report.py scripts/pr_scoped_performance_report_results_probe.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id pr-scoped-performance-report-results-scandir --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/pr_report_results_probe.json
```

## Success Criteria

- The loader keeps deterministic sorted result ordering and ignores non-JSON files.
- The focused test proves the loader does not regress to `Path.glob` or `json.load`.
- Changed-scope coverage remains at least 95%.
- The registered probe reports a lower `elapsed_ms_mean` on the optimized head.
