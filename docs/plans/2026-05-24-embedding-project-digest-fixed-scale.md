# Embedding project digest fixed-scale performance slice

## Scope

This Python-only performance slice targets `DeterministicEmbeddingBackend._project_digest` in `services/mlx-worker-python/worker/runtime/embedding_backends.py`.

The affected path is covered by the registered PR-scoped performance probe `deterministic-embedding-project-digest-allocation` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for the implementation, embedding runtime tests, PR-scoped performance tests, and `scripts/deterministic_embedding_project_digest_probe.py`.

## Optimization

The digest projection always unpacks a SHA-256 digest into exactly eight little-endian `uint32` values. This slice keeps the projection semantics unchanged while switching the eight-value normalization setup to a fixed-scale list comprehension. The change avoids the per-value append loop and repeated division in the digest hot path, then reuses the same normalized base tiling behavior for arbitrary embedding dimensions.

## Verification plan

1. Run the registered focused test command for `deterministic-embedding-project-digest-allocation` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe locally against `origin/main` and this branch with `scripts/pr_scoped_performance_run.py --probe-id deterministic-embedding-project-digest-allocation`.
4. Use the PR-scoped performance workflow as the merge gate for the registered CI probe report.

## Metrics

Primary metric: `elapsed_ms_mean` from `deterministic-embedding-project-digest-allocation` (lower is better). Secondary metric: `peak_bytes_mean` should not regress materially because output vector materialization is unchanged.
