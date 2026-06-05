# Embedding project digest SHA binding

## Scope

This Python-only performance slice is limited to `worker.runtime.embedding_backends.DeterministicEmbeddingBackend._project_digest`.
The deterministic embedding projection hashes every input seed before expanding the digest into a normalized vector; repeated embeddings should avoid avoidable module attribute lookup overhead on that hot path.

## Registered probe

The affected path is covered by the registered PR-scoped probe `deterministic-embedding-project-digest-allocation` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and runs `scripts/deterministic_embedding_project_digest_probe.py`.

## Plan

1. Preserve deterministic projection values for all supported dimensions.
2. Bind the SHA-256 constructor at module load and reuse the binding inside `_project_digest`.
3. Verify with focused embedding tests, changed-scope coverage, and the registered probe locally on Linux.
4. Use PR-scoped performance CI as the merge gate.

## Success metrics

Success is measured by the registered probe's `elapsed_ms_mean` and `default_dimension_elapsed_ms_mean` moving lower without changing checksum values. Behavior parity is measured by `test_project_digest_preserves_legacy_projection_values` and the existing embedding runtime tests.
