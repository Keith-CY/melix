# Embedding project digest default-dimension fast path

## Scope

This Python-only performance slice is limited to `worker.runtime.embedding_backends.DeterministicEmbeddingBackend._project_digest` and its local expanded-projection helper.
The deterministic embedding projection hashes every input seed before expanding the digest into a normalized vector; default 8-dimension embeddings should skip the generic repeat/remainder expansion path after the first digest block is normalized while preserving the same zero-norm guard as the generic path.

## Registered probe

The affected path is covered by the registered PR-scoped probe `deterministic-embedding-project-digest-allocation` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values and runs `scripts/deterministic_embedding_project_digest_probe.py`.

## Plan

1. Preserve deterministic projection values for all supported dimensions.
2. Add a direct `dimensions == 8` path that returns the normalized first digest block without running the generic repeat/remainder expansion path.
3. Move the generic repeat/remainder expansion into a local helper so non-default dimensions keep the original hot-path shape while the default path can return early.
4. Increase the registered probe sample count outside pytest smoke runs so the sub-second digest microbenchmark is less sensitive to one-sample scheduler noise.
5. Verify the zero-norm contract inside the registered project-digest probe, then run focused embedding tests, changed-scope coverage, and the registered probe locally on Linux.
6. Use PR-scoped performance CI as the merge gate.

## Success metrics

Success is measured by the registered probe's `elapsed_ms_mean` and `default_dimension_elapsed_ms_mean` moving lower without changing checksum values. Behavior parity is measured by `test_project_digest_preserves_legacy_projection_values` and the existing embedding runtime tests.
