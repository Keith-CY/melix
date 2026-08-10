# Stream Assembler Token Weight Single-Pass Slice

## Scope

This Python-only performance slice is limited to the stream assembler token-count
annotation path in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.
It preserves token-count distribution semantics while computing estimated delta
weights and their total in one pass instead of materializing weights and then
summing them in a second pass.

## Registered probe

The affected path is covered by the existing PR-scoped probe
`stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches `stream_assembler.py`, focused stream
assembler tests, PR-scoped performance tests, and
`scripts/stream_assembler_token_bytes_probe.py`.

## Expected effect

Repeated token-count annotation workloads avoid one full Python iteration over
the delta-weight list. The expected primary metric is lower or neutral
`token_count_annotation_ms_mean` in the registered probe while preserving
`generated_token_count_mean`, `token_count_annotation_checksum`, and the
delta-token-count metrics.

## Verification plan

1. Run the registered focused test command for
   `stream-assembler-token-byte-fast-decode`.
2. Run the registered changed-scope coverage command and keep touched scope at or
   above 95%.
3. Run the registered local Linux probe by comparing `origin/main` against this
   branch with `scripts/pr_scoped_performance_run.py`.
4. Use GitHub Actions PR-scoped performance as the merge gate after PR creation.
