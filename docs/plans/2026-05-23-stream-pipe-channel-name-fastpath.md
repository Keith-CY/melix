# Stream pipe-channel name fast path

## Scope

This Python performance slice is limited to Harmony-style pipe-channel header
parsing in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.
It keeps stream assembly behavior unchanged while reducing work in
`RequestStreamAssembler._pipe_channel_name()`.

## Optimization hypothesis

Pipe-channel headers may contain metadata after the channel token, for example
`<|channel>analysis metadata`. The previous helper lowercased the full stripped
header and then split it, which allocated/lowercased metadata that is never used
for channel dispatch. Scanning to the first whitespace and lowercasing only the
channel token should preserve behavior while reducing string work on channel
boundaries.

## Registered probe

Affected path coverage is already registered under PR-scoped probe
`stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`. The
entry includes focused `test_command`, `coverage_command`, and `probe_command`
fields for:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/stream_assembler_parser_mode_probe.py`

The probe reports `elapsed_ms_mean`, `channel_name_calls_mean`, and stream
parser correctness counters. Local Linux verification uses that registered probe;
CI remains the source of truth for the PR-scoped performance report.

## Verification plan

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_parser_mode_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_parser_mode_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/stream_assembler.py services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/stream_assembler_parser_mode_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/stream_assembler_parser_mode_probe.py
```
