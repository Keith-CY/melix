# Serving diagnostics event-index literal cache

## Goal

Reduce JSONL serialization overhead in the serving diagnostics debug queue path by caching ASCII byte literals for repeated integer event indexes.

## Scope

This slice is Python-only under `services/mlx-worker-python` and can be verified locally on Linux. It touches:

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`

## Registered probe

The affected path is covered by the existing PR-scoped registered probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`. The probe defines focused `test_command`, `coverage_command`, and `probe_command` entries and reports append, serialization, retained/dropped count, checksum, and serialized-byte metrics.

## Optimization hypothesis

`_empty_attribute_event_json_line_bytes()` serializes retained queue event indexes with `str(event_index).encode("ascii")` for every JSONL row. The registered probe keeps the same retained event indexes across repeated samples, so caching the integer-to-ASCII bytes conversion should reduce repeated allocation and conversion work while preserving byte-for-byte JSON output.

## Verification plan

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_serving_diagnostics.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_serving_diagnostics.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/productization/serving_diagnostics.py \
  services/mlx-worker-python/tests/test_serving_diagnostics.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/serving_diagnostics_queue_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=20 uv run --project services/mlx-worker-python python3 scripts/serving_diagnostics_queue_probe.py
```

## Success criteria

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- Local registered probe preserves `serialization_checksum`, `retained_count`, `dropped_count`, and `serialized_bytes` while improving or staying within noise for `serialization_elapsed_ms_mean`.
- Hosted PR-scoped performance CI completes `serving-diagnostics-debug-queue-bounds` successfully before merge.
