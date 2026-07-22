# Stream assembler token compression cache slice

This Python performance slice is limited to `worker.runtime.stream_assembler.RequestStreamAssembler._compress_delta_token_counts`.

## Scope

The stream assembler assigns token counts across multiple emitted deltas when a runtime fragment covers more than one logical delta. Repeated stream shapes can call the compression helper with the same weight vector and target token count many times during streaming or probe workloads.

This slice preserves the existing compression semantics while memoizing the pure compression result by `(weights, token_count)`. The public helper still returns a mutable `list[int]` so callers cannot mutate the cached tuple.

## Registered probe

The affected path is covered by the registered PR-scoped probe `stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`.

The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries. Its `token_count_compression_ms_mean` metric repeatedly calls `_compress_delta_token_counts` with the same 192-delta weight shape, so it directly measures this slice. The probe also gates token-byte decoding and token-count annotation metrics to catch collateral regressions in the same registered stream assembler path.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate after the PR is opened.

## Expected metrics

The primary expected metric is a lower `token_count_compression_ms_mean`. `elapsed_ms_mean`, `delta_token_count_new_ms_mean`, and `token_count_annotation_ms_mean` should remain stable because this slice does not change token-byte decoding or whitespace token estimation behavior.
