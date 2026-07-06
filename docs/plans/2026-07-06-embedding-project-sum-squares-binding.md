# Deterministic embedding sum-squares binding

## Scope

This Python-only performance slice targets deterministic embedding projection in
`services/mlx-worker-python/worker/runtime/embedding_backends.py`.

The affected path is covered by the registered PR-scoped performance probe
`deterministic-embedding-project-digest-allocation` in
`infra/perf/pr_scoped_probes.json`. The registry entry already provides focused
`test_command`, `coverage_command`, and `probe_command` entries for the embedding
runtime tests, changed-scope coverage, and digest projection probe.

## Optimization

`DeterministicEmbeddingBackend._project_digest(...)` already binds common runtime
helpers such as `sha256`, `sqrt`, and `round` through default arguments. This
slice extends that pattern to `_sum_squares_8`, avoiding a global lookup for each
projection while preserving the existing default-dimension normalization loop and
expanded-dimension behavior.

No embedding vector values, dimensions, checksums, or zero-norm fallback behavior
change.

## Verification plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered `deterministic-embedding-project-digest-allocation` probe
   locally against `origin/main` and this branch.
4. Use GitHub Actions PR-scoped performance as the final registered probe merge
   gate.

## Verification boundary

This is a Python-only slice and is locally verifiable on Linux. The PR-scoped CI
probe report remains the required merge gate before merging.
