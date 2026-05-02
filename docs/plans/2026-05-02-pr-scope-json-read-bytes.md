# PR-scoped Scope Changed-files JSON Read Bytes Slice

## Goal

Reduce JSON input loading overhead in `scripts/pr_scoped_performance_scope.py`, the script that reads the changed-files payload before selecting PR-scoped performance probes.

## Scope

- `scripts/pr_scoped_performance_scope.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Linux Constraint

This slice is Python-only and locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe. It does not validate Swift runtime effects locally.

## Optimization Hypothesis

The scope CLI currently loads the changed-files JSON via `Path.read_text(encoding="utf-8")` before `json.loads`. Switching to `Path.read_bytes()` lets Python's JSON decoder consume bytes directly and avoids an intermediate text decode/allocation on large changed-file payloads while preserving the same JSON-list validation and string coercion in `main()`.

## Registered Probe

- Probe ID: `pr-scoped-performance-scope-json-read-bytes`
- Workload: create a synthetic changed-files JSON payload with 5,000 file paths and repeatedly call `load_changed_files()`.
- Metrics:
  - `elapsed_ms_mean` lower is better
  - `elapsed_ms_min` lower is better
  - `changed_file_count` and `sample_count` informational

## Success Metrics

- Focused tests prove the scope CLI loader uses binary JSON reads and the registry selects the new probe for `scripts/pr_scoped_performance_scope.py`.
- Changed-scope coverage for the touched script/test scope remains at or above 95%.
- Local registered probe improves versus the pre-change baseline.
- PR-scoped performance CI completes successfully before merge.

## Verification Commands

```text
python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_pr_scoped_scope_script_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_cli_loads_changed_files_with_binary_json_read services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_cli_scripts_smoke services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_pr_scoped_scope_script_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_cli_loads_changed_files_with_binary_json_read services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_cli_scripts_smoke services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/pr_scoped_performance_scope.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id pr-scoped-performance-scope-json-read-bytes --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/pr_scope_json_read_bytes_probe.json
git diff --check
```
