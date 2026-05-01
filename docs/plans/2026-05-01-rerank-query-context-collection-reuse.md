# Rerank Query Context Collection Reuse

## Scope

This slice keeps the existing deterministic rerank semantics and narrows the hot path inside `worker/runtime/rerank_backends.py`. The default Jina v3 and causal-lm rerank families already build one `RerankQueryContext` per request; this slice reuses the context's immutable tuple/frozenset collections directly while scoring each document instead of rebuilding per-document list/set copies.

## Registered probe

The affected path is covered by the existing PR-scoped probe `deterministic-rerank-query-context-reuse` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` for focused rerank runtime tests and probe selection/dispatch tests.
- `coverage_command` for changed-scope coverage across rerank runtime/backends, PR-scoped performance support, and focused tests.
- `probe_command` that measures repeated deterministic rerank scoring for 2,048 documents and reports elapsed time plus context-build/tokenize counters.

## Verification plan

Run the registered focused command set locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_rerank_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_deterministic_rerank_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_rerank_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_deterministic_rerank_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py services/mlx-worker-python/worker/runtime/rerank_backends.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 /tmp/run_rerank_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
