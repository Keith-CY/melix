# Stream Assembler Channel Name Cache Performance Slice

This Python-only performance slice is limited to `worker.runtime.stream_assembler.RequestStreamAssembler._pipe_channel_name()`.

## Scope

The stream assembler repeatedly normalizes Harmony-style pipe channel headers while draining streamed chunks. The parser-mode workload commonly repeats a small set of headers such as `analysis metadata` and `final metadata` across many samples, so this slice memoizes channel-name normalization with a small bounded cache.

No stream parsing behavior changes: whitespace trimming, first-token extraction, lowercase normalization, legacy hidden-channel handling, visible channels, and unknown-channel accounting remain unchanged.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/stream_assembler_parser_mode_probe.py`

## Verification Plan

1. Capture the local Linux registered-probe baseline on `origin/main`.
2. Add a focused regression test proving repeated header normalization uses the cache while preserving normalized output.
3. Apply the bounded `lru_cache` to `_pipe_channel_name()`.
4. Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate before merging.