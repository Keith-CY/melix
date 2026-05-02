# Deterministic Rerank Tie-Breaker Prefix Slice

## Goal

Reduce deterministic rerank scoring overhead by reusing the query-side bytes for the stable tie-breaker hash across all documents in a `score_documents` call.

## Scope

- `services/mlx-worker-python/worker/runtime/rerank_backends.py`
- `services/mlx-worker-python/tests/test_rerank_runtime.py`
- `infra/perf/pr_scoped_probes.json` registered probe `deterministic-rerank-query-context-reuse`

## Linux Constraint

This slice is Python-only and locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Optimization Hypothesis

The deterministic rerank runtime already builds one query context per `score_documents` call. The tie-breaker hash currently encodes `query + NUL + document` for every scored document. Storing the encoded `query + NUL` prefix in the query context preserves deterministic scores while avoiding repeated query-prefix formatting and encoding for each document.

## Registered Probe

- Probe ID: `deterministic-rerank-query-context-reuse`
- Workload: score 2,048 deterministic rerank documents across repeated iterations with a reused query context.
- Metrics:
  - `elapsed_ms_mean` lower is better
  - `query_context_builds_mean` lower is better
  - `tokenize_calls_mean` lower is better

## Success Metrics

- Focused tests prove query context behavior and tie-breaker semantics remain unchanged.
- Changed-scope coverage for touched rerank runtime files and tests remains at or above 95%.
- Local registered probe improves versus the pre-change baseline without increasing query-context builds or tokenize calls.
- PR-scoped performance CI selects and completes the registered probe for this path.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_rerank_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_deterministic_rerank_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_deterministic_rerank_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_deterministic_rerank_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/deterministic_rerank_runtime.py services/mlx-worker-python/worker/runtime/rerank_backends.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_rerank_runtime.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id deterministic-rerank-query-context-reuse --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/rerank_prefix_probe.json
git diff --check
```
