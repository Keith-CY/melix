# Serving diagnostics event line local bindings

## Scope

This Python-only performance slice is limited to the empty-attribute serving diagnostics JSONL fast path in `services/mlx-worker-python/worker/productization/serving_diagnostics.py`.

The affected path is already covered by the registered PR-scoped performance probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/serving_diagnostics_queue_probe.py`

## Optimization point

`_empty_attribute_event_json_line()` is called once per retained debug event during JSONL serialization. Keep output bytes unchanged while reducing repeated attribute lookup and float formatting overhead in the hand-built JSON line:

- bind `event.phase`, `event.request_id`, and `event.status` to locals before building the line;
- use literal JSON strings for the common debug-event `decode` phase and `completed` status while retaining the existing string encoder fallback for all other values;
- use the normal float string form for already-finite `float` values, matching CPython's shortest round-trippable formatting used by `repr()` for these values.

No queue retention behavior, dropped-event accounting, manifest layout, or diagnostics eligibility semantics change in this slice.

## Verification plan

Run the registered focused commands locally on Linux before opening the PR. This slice also scopes the registered probe command to `MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=20` so both base and head measurements use a less noisy sample count while the script-level default and smoke-test override remain unchanged.

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_serving_diagnostics_queue_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_serving_diagnostics_queue_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/serving_diagnostics.py services/mlx-worker-python/tests/test_serving_diagnostics.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/serving_diagnostics_queue_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python bash -c 'export MELIX_SERVING_DIAGNOSTICS_QUEUE_SAMPLES=20; SCRIPT="scripts/serving_diagnostics_queue_probe.py"; if [ -f "$SCRIPT" ]; then python3 "$SCRIPT"; else for CANDIDATE in "../head/$SCRIPT" "${GITHUB_WORKSPACE:-}/head/$SCRIPT"; do if [ -f "$CANDIDATE" ]; then python3 "$CANDIDATE"; exit $?; fi; done; echo "missing probe script fallback for $SCRIPT" >&2; exit 2; fi'
```

Use the PR-scoped performance workflow as the hosted merge gate after push.
