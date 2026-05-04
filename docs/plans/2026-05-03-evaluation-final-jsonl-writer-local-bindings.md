# Evaluation Final-Result JSONL Writer Local Bindings

## Goal

Reduce final-result evaluation dataset materialization overhead by avoiding repeated attribute lookups inside the per-row JSONL writer loop, while preserving the exact JSONL bytes emitted today.

## Linux-Only Constraint

This slice only touches the Python worker final-result materialization path and its PR-scoped performance probe, so it can be locally verified on Linux.

## Touched Files

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `docs/plans/2026-05-03-evaluation-final-jsonl-writer-local-bindings.md`

## Existing Probe Coverage

The affected path is already covered by registered PR-scoped probe `evaluation-final-result-materialization-streaming` in `infra/perf/pr_scoped_probes.json`. The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries and measures:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `sample_count`

## Optimization Slice

`_write_jsonl_rows()` now binds `json.dumps` and `handle.write` to local variables before the row loop. This keeps the wire-format and empty-input newline contract unchanged while reducing repeated global and attribute lookups across large materialized evaluation datasets.

## Success Metrics

- Focused tests for `evaluation_final_result.py` pass.
- Changed-scope coverage for `evaluation_final_result.py` and its tests is at least 95%.
- Registered local probe reports lower `elapsed_ms_mean` or an explainable neutral variance, with no semantic regression.

## Verification Commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/evaluation_final_result.py services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 .runtime/eval_final_probe.py
```
