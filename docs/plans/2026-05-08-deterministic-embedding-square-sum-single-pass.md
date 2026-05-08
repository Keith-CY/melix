# Deterministic Embedding Projection Square-Sum Single Pass

## Goal

Reduce per-vector temporary allocation in deterministic embedding digest projection while preserving the exact deterministic vector values and normalization behavior.

## Linux-only constraint

This is a Python worker-runtime slice. It is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- `docs/plans/2026-05-08-deterministic-embedding-square-sum-single-pass.md`

## Optimization hypothesis

`DeterministicEmbeddingBackend._project_digest()` already expands the normalized digest base vector with list multiplication, but it still builds a second `squared_values` list solely to compute the L2 normalization denominator. The digest base has only eight float values, yet this path is called once per embedding row and the temporary list allocation repeats for every vector.

Accumulate the base squared sum while building `base_values`, then reuse that scalar for the full-repeat contribution and only rescan the short remainder. This removes one temporary list allocation per projected vector and preserves the legacy output ordering, rounding, and zero-dimension behavior.

## Registered performance probe

The affected path is covered by `deterministic-embedding-project-digest-allocation` in `infra/perf/pr_scoped_probes.json` with focused `test_command`, `coverage_command`, and `probe_command` entries.

Metrics:

- `elapsed_ms_mean` — lower is better
- `peak_bytes_mean` — lower is better
- `dimensions`, `vector_count`, and checksum provide behavior context

## Verification commands

- Focused pytest for embedding runtime and PR-scoped probe selection/smoke tests
- Changed-scope coverage for touched Python/tests with at least 95% automated coverage
- Local registered probe run before and after the implementation
- `git diff --check`
