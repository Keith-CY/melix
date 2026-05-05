# Changed-scope coverage diff regex precompile

## Goal

Reduce redundant regex work in `scripts/changed_scope_coverage.py` when parsing large unified diffs for changed-scope coverage reports.

## Linux-only constraint

This slice is Python-only and locally verifiable on Linux with focused pytest, changed-scope coverage, and an explicit parser micro-probe.

## Touched files

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Performance probe

Register `changed-scope-coverage-diff-parser` in the PR-scoped performance registry. The probe builds a deterministic synthetic multi-file diff, repeatedly calls `_parse_changed_lines(...)`, and reports:

- `elapsed_ms_mean` (lower is better)
- `line_count` and `changed_line_count` guard-rail metrics

## Success metrics

- Focused tests pass.
- Changed-scope coverage for touched executable lines is at least 95%.
- Local parser probe reports concrete elapsed time and stable guard-rail counts.
- The registered scoped probe is selected when `scripts/changed_scope_coverage.py` changes.

## Verification commands

```bash
python -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
coverage run -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && coverage json -o coverage.json && python scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py tests/test_changed_scope_coverage.py scripts/changed_scope_coverage_parse_probe.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
python scripts/changed_scope_coverage_parse_probe.py
python scripts/pr_scoped_performance_run.py --probe changed-scope-coverage-diff-parser --base-ref origin/main --head-ref HEAD --output /tmp/changed-scope-coverage-diff-parser.json
```
