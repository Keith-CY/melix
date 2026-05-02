# Phase8 Metrics Closure Audit Reuse Plan

## Goal
Avoid duplicate closure-audit work in `scripts/phase8_metrics_report.py` by reusing the closure-audit evidence already embedded in the release-gate report, while preserving current report output and adding PR-scoped proof.

## Linux-only constraint
This slice targets Python-only reporting and PR-scoped performance wiring that can be verified locally on Linux. No macOS runtime execution is required for the implementation proof.

## Touched files
- `scripts/phase8_metrics_report.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_phase8_runtime_probes.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Implementation task
1. Update `scripts/phase8_metrics_report.py` to reuse `release_gate_report["m9"]["closure_audit"]` when present and only fall back to `build_closure_audit(repo_root).to_dict()` if that nested evidence is absent.
2. Add/adjust focused tests to prove the report reuses the embedded closure audit and does not call the fallback builder when the release-gate payload already contains the evidence.
3. Register a PR-scoped performance probe that measures the phase8 metrics path and reports at least `elapsed_ms_mean`, `closure_audit_calls_mean`, and `sample_count`, with a base-compatible `command_json` probe command.

## Success metrics
- Functional: `phase8_metrics_report.main()` still emits the same closure-audit metrics payload.
- Redundant-work reduction: local explicit probe reports `closure_audit_calls_mean` dropping from 2.0 on `origin/main` to 1.0 on the branch.
- Coverage: changed executable scope remains at or above 95%.

## Verification commands
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_phase8_runtime_probes.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_phase8_metrics_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_phase8_runtime_probes.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_phase8_metrics_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/phase8_metrics_report.py services/mlx-worker-python/tests/test_phase8_runtime_probes.py services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- Explicit local probe command from the registered PR-scoped probe entry to compare `origin/main` vs head.
- `git diff --check`
