# Stream Assembler Unseen Delta Local Binding Plan

## Goal

Reduce Python attribute lookups in the stream assembler cumulative-fragment hot path by binding `_raw_seen` once inside `RequestStreamAssembler._unseen_delta` before the monotonic-prefix check and delta slice.

## Scope

This Python-only slice is limited to `services/mlx-worker-python/worker/runtime/stream_assembler.py`. It does not change parser behavior, emitted deltas, metrics, or supported stream formats.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `stream-assembler-parser-mode-cache` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

The probe feeds cumulative fragments through a tool-enabled assembler, so every fragment exercises `_unseen_delta` before parser draining.

## Verification

1. Run the registered focused test command for `stream-assembler-parser-mode-cache`.
2. Run the registered changed-scope coverage command and confirm touched-scope coverage remains at least 95%.
3. Run the registered probe locally on Linux before and after the change, using repeated samples, and compare `elapsed_ms_mean` while preserving `tool_call_count`.
4. Run `git diff --check` before commit.

## Success metrics

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- Local registered probe is directionally faster or neutral while preserving the same tool-call count.
- CI PR-scoped performance workflow completes successfully before merge.
