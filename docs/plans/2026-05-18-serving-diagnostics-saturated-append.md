# Serving diagnostics saturated append fast path

## Scope

This Python-only performance slice targets `BoundedServingDiagnosticsEventQueue.append(...)`
in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.
The affected path is covered by the registered PR-scoped performance probe
`serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`,
including focused `test_command`, `coverage_command`, and `probe_command` entries.

## Hypothesis

The debug diagnostics queue spends most probe iterations after the deque reaches
capacity. Checking the saturated branch before appending lets the hot full-queue
path skip retained-count arithmetic and the saturation assignment while
preserving the same deque append/drop semantics and `False` return value for
dropped events.

## Verification

Run the registered focused tests, changed-scope coverage, and local Linux probe:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/serving_diagnostics_queue_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=20 uv run --project services/mlx-worker-python python3 scripts/serving_diagnostics_queue_probe.py
```

The PR-scoped performance workflow remains the merge gate for the registered CI
probe result.

## Acceptance

- Queue behavior remains unchanged for retained events, dropped events, snapshots,
  and serialized diagnostics bundles.
- Changed-scope coverage for touched Python scope is at least 95%.
- The registered local probe shows a clear or neutral improvement in
  `elapsed_ms_mean`; CI must complete the same registered probe before merge.
