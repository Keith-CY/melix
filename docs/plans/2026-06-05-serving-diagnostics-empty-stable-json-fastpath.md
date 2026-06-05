# Serving diagnostics empty stable JSON fast path

## Scope

This Python-only performance slice targets the serving diagnostics bundle writer
in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.
The synthetic debug queue probe repeatedly serializes empty `invocation`,
`effective_config`, and `model_refs` mappings while writing diagnostics bundles.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The registry entry already defines focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/serving_diagnostics_queue_probe.py`

## Optimization point

`_stable_json_object()` previously entered the sorted item-comprehension path
even for empty mappings. This slice adds an empty-mapping fast path so diagnostics
bundle serialization avoids unnecessary `items()` lookup, `sorted()` setup, and
comprehension allocation for empty metadata sections while preserving the exact
JSON output.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered
serving diagnostics queue probe locally on Linux before opening the PR. The PR
scoped performance workflow must also report the registered probe successfully
before merge.