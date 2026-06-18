# Embedding Cycle Replay Extension Loop Performance Slice

## Scope

This Python-only performance slice is limited to the repeated-cycle branch in
`DeterministicEmbeddingRuntime.embed_inputs(...)`. The path handles large
embedding batches where the ordered input cycle is repeated multiple times and
must still return distinct vector lists for each output position.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`deterministic-embedding-duplicate-input-cache` in
`infra/perf/pr_scoped_probes.json`. The entry already includes focused
`test_command`, `coverage_command`, and `probe_command` values for Linux CI.
This slice extends that registered probe with `peak_bytes_mean` so the replay
path's allocation behavior is measured alongside elapsed time and backend call
count.

## Optimization

The prior repeated-cycle branch built all replayed vector copies in an
intermediate list comprehension before extending the response vector list. This
slice appends those defensive copies directly from a nested loop, preserving the
same output order and object isolation while avoiding the temporary replay list.

## Verification plan

1. Add a regression test for repeated-cycle replay that proves the backend only
   embeds the first cycle and all repeated outputs remain distinct mutable lists.
2. Run the registered focused test command for
   `deterministic-embedding-duplicate-input-cache` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally on Linux and compare with the pre-change
   baseline.
5. Use PR-scoped performance CI as the merge gate.

## Success metrics

- Focused tests pass.
- Changed-scope coverage for touched paths is at least 95%.
- Registered probe reports lower `peak_bytes_mean` and no increase in
  `embed_text_calls_mean`; `elapsed_ms_mean` is tracked as a secondary
  lower-is-better metric.
- CI PR-scoped performance report completes without regressions.
