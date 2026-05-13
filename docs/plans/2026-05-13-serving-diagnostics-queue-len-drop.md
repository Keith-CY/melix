# Serving diagnostics queue length-based drop accounting

## Goal

Reduce append-path overhead in `BoundedServingDiagnosticsEventQueue` by deriving drop decisions from the bounded deque length instead of maintaining a separate retained-event counter.

## Scope

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- Registered PR-scoped probe: `serving-diagnostics-debug-queue-bounds`

## Current behavior

The diagnostics queue keeps a bounded `deque(maxlen=...)`, a retained counter, and a dropped counter. The retained counter increments until capacity, then append increments dropped count while the bounded deque evicts the oldest event. This is correct, but the retained counter duplicates state already available through `len(self._events)`.

## Planned change

Use `len(self._events) >= self._max_events` while holding the queue lock to determine whether the incoming event will drop an existing retained event. Remove the redundant retained counter from the append path. Public behavior remains unchanged:

- `append()` returns `True` for retained-without-drop events and `False` when capacity was already full.
- `snapshot().events` retains the newest bounded events in order.
- `snapshot().dropped_count` reports the number of over-capacity appends.

## Verification

Use the existing registered PR-scoped performance probe in `infra/perf/pr_scoped_probes.json`:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/serving_diagnostics_queue_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/serving_diagnostics_queue_probe.py
```

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- Local Linux probe shows a stable lower `elapsed_ms_mean` versus the `origin/main` baseline for the same workload, or the slice is rejected.
- Hosted PR-scoped performance CI runs the registered probe successfully before merge.
