# Stream channel-name manual scan

## Scope

This Python-only performance slice is limited to Harmony pipe-channel header parsing in `RequestStreamAssembler._pipe_channel_name()`.

The affected path is already covered by the registered PR-scoped probe `stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `channel_name_calls_mean`, and channel checksum metrics.

## Change

Replace `header.split(None, 1)` with a bounded manual first-token scan. This preserves the existing semantics for leading whitespace, whitespace-delimited metadata, mixed-case channel names, and blank headers while avoiding a temporary list allocation and preserving only the channel-name slice for lowercasing.

## Verification Plan

Run locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_parser_mode_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_stream_assembler_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_stream_assembler_parser_mode_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/stream_assembler.py services/mlx-worker-python/tests/test_stream_assembler.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/stream_assembler_parser_mode_probe.py
MELIX_STREAM_ASSEMBLER_PARSER_MODE_SAMPLES=512 PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/stream_assembler_parser_mode_probe.py
```

Use the GitHub PR-scoped performance workflow as the registered probe merge gate after opening the PR.

## Success Criteria

- Focused stream assembler tests pass.
- Changed-scope coverage for the touched scope is at least 95%.
- Registered local probe shows directionally lower `elapsed_ms_mean` without changing `channel_name_calls_mean` or `channel_name_checksum`.
