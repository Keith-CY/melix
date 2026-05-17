# Serving diagnostics duration literal cache

## Scope

This Python-only performance slice is limited to the serving diagnostics empty-attribute JSONL fast path in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

## Registered probe

The affected path is covered by the existing PR-scoped registered probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`. The probe already defines focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/serving_diagnostics_queue_probe.py`

## Optimization

Cache the ASCII bytes literal for repeated finite `duration_ms` float values while constructing the optimized empty-attribute event JSONL line. Serving diagnostics debug queues commonly emit repeated small duration values in synthetic and batched debug traces, so avoiding repeated `str(duration_ms).encode("ascii")` work reduces serialization overhead without changing the JSON payload.

## Behavior preservation

- The fast path still applies only to events with the shared empty-attributes sentinel, exact `int` event indexes, exact `float` finite durations, and JSON-safe strings.
- Non-empty attributes and non-exact numeric types still fall back to the stable dictionary encoder path.
- Serialized JSONL bytes remain byte-for-byte compatible for covered events.

## Verification plan

Run the focused local Linux checks before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/serving_diagnostics_queue_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=20 uv run --project services/mlx-worker-python python3 scripts/serving_diagnostics_queue_probe.py
```

The GitHub PR-scoped performance workflow remains the source of registered probe validation before merge.
