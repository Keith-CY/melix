# Deterministic Embedding Single-Cycle Copy Binding

## Slice

This Python-only performance slice keeps the deterministic embedding repeated
single-input cycle behavior unchanged while reducing per-replayed-vector method
lookup overhead. The affected production path is
`services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`.

## Registered probe

The path is already covered by the registered PR-scoped performance probe
`deterministic-embedding-duplicate-input-cache` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` fields and reports the
single-cycle metrics:

- `single_cycle_elapsed_ms_mean`
- `single_cycle_peak_bytes_mean`
- `single_cycle_embed_text_calls_mean`

## Implementation plan

1. Bind `vector.copy` once in the `cycle_length == 1` replay branch before the
   generator extends the vector list.
2. Preserve unique list objects for replayed vectors so callers cannot mutate a
   shared vector accidentally.
3. Run the registered focused tests, changed-scope coverage, and registered
   probe locally on Linux before pushing. GitHub Actions PR-scoped performance
   remains the merge gate.

## Verification plan

- Focused pytest for deterministic embedding and PR-scoped registry coverage.
- Changed-scope coverage for the deterministic embedding runtime, focused tests,
  registry tests, and probe script.
- Local registered probe comparison against the pre-change baseline.