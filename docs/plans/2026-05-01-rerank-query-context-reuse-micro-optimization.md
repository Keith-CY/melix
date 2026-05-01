# Deterministic rerank query-context reuse micro-optimization

## Goal

Eliminate per-document reconstruction of query-derived `list(...)` and `set(...)` objects in the deterministic rerank family adapters while preserving score semantics exactly.

## Linux-only constraint

This cron run executes on Linux, so the slice must stay inside the Python worker and use Linux-verifiable evidence only. No macOS-only validation is required for this change.

## Touched files

- `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`

## Performance probe

Use the existing PR-scoped performance probe `deterministic-rerank-query-context-reuse`.

Probe command:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
uv run --project services/mlx-worker-python python3 -c \
"import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_deterministic_rerank_query_context_reuse as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
```

## Success metrics

- Preserve existing rerank scores and ordering for supported families.
- Preserve `query_context_builds_mean == 1.0`.
- Preserve `tokenize_calls_mean == 2049.0` for the synthetic probe workload.
- Improve `elapsed_ms_mean` relative to `origin/main`.
- Achieve at least 95% changed-scope automated coverage for the touched executable files before commit.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_rerank_runtime.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_rerank_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_deterministic_rerank_probe

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_rerank_runtime.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_rerank_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_deterministic_rerank_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py \
  services/mlx-worker-python/worker/runtime/rerank_backends.py \
  services/mlx-worker-python/worker/productization/pr_scoped_performance.py \
  services/mlx-worker-python/tests/test_rerank_runtime.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
uv run --project services/mlx-worker-python python3 -c \
"import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_deterministic_rerank_query_context_reuse as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"

git diff --check
```