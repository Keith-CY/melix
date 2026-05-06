# Changed-scope coverage diff byte dispatch

## Goal

Reduce per-line parser overhead in `scripts/changed_scope_coverage.py` by replacing the hot-path diff header and hunk range regex calls with literal prefix/search dispatch while preserving unified-diff semantics.

## Linux-only constraint

This slice is Python-only and locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered parser micro-probe.

## Touched files

- `infra/perf/pr_scoped_probes.json`
- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`
- `docs/plans/2026-05-05-changed-scope-coverage-byte-dispatch.md`

## Registered performance probe

The existing `changed-scope-coverage-diff-parser` PR-scoped probe covers `scripts/changed_scope_coverage.py` and already provides focused `test_command`, `coverage_command`, and `probe_command` entries in `infra/perf/pr_scoped_probes.json`.

The probe builds a deterministic synthetic multi-file diff, repeatedly calls `_parse_changed_lines(...)`, and reports:

- `elapsed_ms_mean` (lower is better)
- `elapsed_ms_min` (lower is better)
- `line_count`, `file_count`, and `changed_line_count` guard-rail metrics

## Success metrics

- Focused parser tests pass.
- Changed-scope coverage for touched executable lines is at least 95%.
- Local parser probe reports a clear improvement over the `origin/main` baseline with stable guard-rail counts.
- The registered scoped probe is selected when `scripts/changed_scope_coverage.py` changes.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py tests/test_changed_scope_coverage.py scripts/changed_scope_coverage_parse_probe.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/changed_scope_coverage_parse_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --probe changed-scope-coverage-diff-parser --base-ref origin/main --head-ref HEAD --output /tmp/changed-scope-coverage-diff-parser.json
```
