# Retrieval lookup payload eight-item copy fast path

## Scope

This Python-only performance slice is limited to lookup payload copying in
`worker.runtime.retrieval_context._copy_payload_value`.

The registered `retrieval-context-projection-fastpath` probe now includes
common eight-item metadata lists and tuples in its lookup-copy workload. The
runtime change adds explicit eight-item list and tuple copy branches before the
existing seven-item specializations, preserving deep-copy isolation for nested
payload values while avoiding the generic comprehension/generator path for this
shape.

## Probe registration

The affected path is already covered by the registered PR-scoped performance
probe `retrieval-context-projection-fastpath` in
`infra/perf/pr_scoped_probes.json`. This slice updates that registration's
`watch_globs` to include this plan and uses the existing focused
`test_command`, `coverage_command`, and `probe_command` entries.

## Verification plan

Run the registered focused commands locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_retrieval_lookup_payload_copy_preserves_scalar_and_none_values services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_retrieval_context.py::test_retrieval_lookup_payload_copy_preserves_scalar_and_none_values services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_retrieval_context_projection_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/retrieval_context.py services/mlx-worker-python/tests/test_retrieval_context.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/retrieval_context_projection_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_RETRIEVAL_CONTEXT_PROJECTION_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/retrieval_context_projection_probe.py
```

GitHub Actions PR-scoped performance remains the final registered-probe merge
gate.

## Acceptance criteria

- Focused retrieval-context and PR-scoped performance tests pass.
- Changed-scope coverage for touched Python files remains at least 95%.
- The local registered probe shows neutral-to-improved lookup-copy metrics.
- The PR-scoped performance workflow completes successfully before merge.
