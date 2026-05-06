# Stream assembler reversed prefix cache slice

## Scope

This performance slice is limited to the Python request stream assembler structural-tag partial suffix path in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.

The implementation caches the reversed structural prefix tuples selected at assembler initialization so `_partial_structural_tag_suffix()` can resolve the longest held suffix without allocating a `reversed(...)` iterator on every hot-path call.

## Registered probe

The affected path is covered by the registered PR-scoped probe `stream-assembler-structural-prefix-cache` in `infra/perf/pr_scoped_probes.json`.

This slice extends that probe to report `partial_suffix_elapsed_ms_mean`, which directly times repeated `_partial_structural_tag_suffix()` resolution for a buffer ending in a held `<tool` prefix. The existing focused `test_command`, `coverage_command`, and `probe_command` remain the validation source for this path.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_stream_assembler.py::test_structural_tag_prefixes_are_cached_per_parser_mode services/mlx-worker-python/tests/test_stream_assembler.py::test_partial_structural_tag_suffix_checks_all_prefixes_in_one_endswith_call services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_structural_prefix_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_stream_assembler.py::test_structural_tag_prefixes_are_cached_per_parser_mode services/mlx-worker-python/tests/test_stream_assembler.py::test_partial_structural_tag_suffix_checks_all_prefixes_in_one_endswith_call services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_structural_prefix_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/stream_assembler.py services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/stream_assembler_structural_prefix_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/stream_assembler_structural_prefix_probe.py
```

## Expected metric direction

`partial_suffix_elapsed_ms_mean` is expected to decrease because the per-call reversed-prefix iterator allocation is removed. `elapsed_ms_mean` and `peak_bytes_mean` remain guardrail metrics for the existing broad structural-prefix probe loop.
