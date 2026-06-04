# Stream assembler hidden-channel strip cache

## Scope

This Python-only performance slice targets hidden Harmony pipe-channel handling in
`services/mlx-worker-python/worker/runtime/stream_assembler.py`.

`RequestStreamAssembler._hidden_pipe_channel_deltas()` checked `hidden.strip()`
twice per hidden channel: once for the empty-thinking metric and once before
emitting or suppressing hidden reasoning. This slice preserves behavior while
materializing that boolean once per call.

## Registered Probe

The affected path is already covered by the registered PR-scoped performance
probe `stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the stream assembler path, its focused tests, and the
probe script.

## Implementation Plan

1. Reuse the existing hidden Harmony channel tests and registered probe coverage.
2. Cache the `hidden.strip()` truthiness in `_hidden_pipe_channel_deltas()` so
   hidden-channel processing avoids the duplicate strip allocation.
3. Run the registered focused tests, changed-scope coverage, and registered
   probe locally on Linux.
4. Use PR-scoped performance CI as the registered validation source before merge.

## Baseline

Local Linux baseline before implementation:

```json
{"channel_name_calls_mean": 13.0, "channel_name_checksum": 86.0, "chunk_count": 1200.0, "elapsed_ms_mean": 3.675401327200234, "harmony_channel_count": 13.0, "raw_char_count": 14810.0, "sample_count": 8.0, "tool_call_count": 10.0}
```

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_parser_mode_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_parser_mode_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/stream_assembler.py services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/stream_assembler_parser_mode_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/stream_assembler_parser_mode_probe.py
```
