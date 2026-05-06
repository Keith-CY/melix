# Stream Assembler Duplicate Call-ID Short-Circuit

## Goal

Reduce redundant work in the Python worker stream assembler when a model replays a tool call fragment with the same model-provided call ID.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python`, so it can be validated on Linux with focused pytest, changed-scope coverage, and a local command-json performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-06-stream-assembler-duplicate-call-id-short-circuit.md`

## Optimization

`RequestStreamAssembler._tool_delta(...)` currently canonicalizes `arguments` with `json.dumps(..., sort_keys=True, separators=(",", ":"))` before checking whether a model-provided `id`/`call_id` has already been emitted. For duplicate call-ID replays, the argument serialization is wasted because the duplicate is discarded.

Change the model-provided call-ID path to check `_emitted_tool_keys` before serializing arguments. Preserve the legacy call-ID-less path because it still needs canonical argument JSON for content-based dedupe.

## Performance probe definition

Update the registered `stream-assembler-parser-mode-cache` PR-scoped probe so the command-json workload includes repeated duplicate model-provided call IDs with large argument payloads.

Metrics:

- `elapsed_ms_mean`: lower is better.
- `json_dumps_calls_mean`: lower is better; expected to drop for duplicate call-ID replay.
- `duplicate_tool_delta_count`: must remain equal to the duplicate replay count.

## Success metrics

- Focused pytest passes.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Local probe reports lower elapsed time and fewer argument serialization calls on the optimized branch against `origin/main`.
- `git diff --check` is clean.
