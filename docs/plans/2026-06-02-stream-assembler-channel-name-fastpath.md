# Stream Assembler Channel Name Fast Path

## Scope

This Python performance slice is limited to Harmony pipe-channel header parsing in
`services/mlx-worker-python/worker/runtime/stream_assembler.py`.

The parser repeatedly extracts lowercase channel names such as `analysis` and
`final` from headers like `analysis metadata\n` in streamed model output. The
optimization keeps the existing fallback for whitespace-padded or mixed-case
headers, while adding a direct lowercase fast path for the common registered
probe workload.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`.
That registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` values and watches:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/stream_assembler_parser_mode_probe.py`

## Verification Plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. Use the GitHub Actions PR-scoped performance
workflow as the final registered probe validation before merge.

## Success Criteria

- Behavior parity for mixed-case, whitespace-padded, exact lowercase, and
  lowercase-with-metadata channel headers.
- Changed-scope coverage remains at least 95%.
- `stream_assembler_parser_mode_probe.py` reports lower mean elapsed time on the
  optimized branch than the local baseline samples.
