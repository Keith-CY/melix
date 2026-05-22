# Runtime utils function cache-target fast path

## Scope

This Python-only performance slice is limited to `worker.runtime.runtime_utils._callable_cache_target()` and the hot `callable_accepts_kwarg()` path used for repeated generation/runtime capability checks.

## Registered Probe

The affected path is already covered by the PR-scoped probe `runtime-utils-kwarg-signature-cache` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean` (lower is better)
- `inspect_signature_calls_mean` (lower is better)

## Implementation Plan

1. Preserve bound-method normalization and non-introspectable callable fallback behavior.
2. Add a plain-Python function fast path before bound-method attribute probing so the common repeated function case skips two attribute lookups per call.
3. Slot the cached signature record to reduce per-cache-entry object overhead while preserving the frozen dataclass API.
4. Add focused regression coverage for the plain-function cache target and slotted signature record behavior.
5. Run the registered focused tests, changed-scope coverage, and local registered probe on Linux before opening the PR. CI PR-scoped performance remains the merge gate for base-vs-head probe validation.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_runtime_utils.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_utils_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_utils_kwarg_cache_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_runtime_utils.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_utils_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_utils_kwarg_cache_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/runtime_utils.py services/mlx-worker-python/tests/test_runtime_utils.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/runtime_utils_kwarg_cache_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/runtime_utils_kwarg_cache_probe.py
```
