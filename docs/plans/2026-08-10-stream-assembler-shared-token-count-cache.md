# Stream Assembler Shared Token Count Cache Slice

## Scope

This Python-only performance slice is limited to the stream assembler token-count
estimator in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.
It keeps token-count semantics identical while routing the estimator through the
shared deterministic `worker.runtime.token_counting.whitespace_token_count`
helper instead of the local `len(text.split())` implementation.

## Registered probe

The affected path is covered by the existing PR-scoped probe
`stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`.
The registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries and watches `stream_assembler.py`, focused stream
assembler tests, PR-scoped performance tests, and
`scripts/stream_assembler_token_bytes_probe.py`.

## Expected effect

Repeated token-count annotation workloads can reuse the shared LRU cache and the
allocation-free scanner used by adjacent deterministic runtimes. The expected
primary metric is lower or neutral `delta_token_count_new_ms_mean` and
`token_count_annotation_ms_mean` in the registered probe while preserving
`generated_token_count_mean` and delta-token checksums.

## Verification plan

1. Run the registered focused test command for
   `stream-assembler-token-byte-fast-decode`.
2. Run the registered changed-scope coverage command and keep touched scope at or
   above 95%.
3. Run the registered local Linux probe by comparing `origin/main` against this
   branch with `scripts/pr_scoped_performance_run.py`.
4. Use GitHub Actions PR-scoped performance as the merge gate after PR creation.