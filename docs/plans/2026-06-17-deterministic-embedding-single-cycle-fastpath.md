# Deterministic embedding single-cycle replay fast path

## Scope

This Python performance slice is limited to `DeterministicEmbeddingRuntime.embed_inputs()` in `services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`.
It preserves duplicate-input cache behavior and vector isolation while avoiding the repeated generator setup used when a large embedding request is the same input repeated many times.

## Registered probe

The affected path is covered by the registered PR-scoped probe `deterministic-embedding-duplicate-input-cache` in `infra/perf/pr_scoped_probes.json`.
The registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries. This slice extends the probe metrics with a `single_cycle_*` scenario so the registered probe validates the all-duplicate request shape that exercises the new fast path.

## Implementation plan

1. Keep the existing cycle detection contract unchanged.
2. Add a narrow `cycle_length == 1` branch that embeds the repeated text once, appends the original vector once, and appends copies for the remaining positions.
3. Add regression coverage proving all returned vectors remain isolated and the backend is called once.
4. Run the registered focused tests, changed-scope coverage, and the registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the final registered CI probe gate before merge.

## Expected outcome

The common single repeated input path should reduce `single_cycle_elapsed_ms_mean` and keep `single_cycle_embed_text_calls_mean == 1.0` without changing results for larger repeated cycles or non-cyclic duplicate inputs.
