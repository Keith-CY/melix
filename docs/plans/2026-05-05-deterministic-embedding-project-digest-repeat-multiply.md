# Deterministic Embedding Projection Repeat Multiply

## Goal

Reduce Python-level list growth overhead in deterministic embedding digest projection without changing the deterministic vector values or normalization contract.

## Linux-only constraint

This is a Python worker-runtime slice. It is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `scripts/deterministic_embedding_project_digest_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization hypothesis

`DeterministicEmbeddingBackend._project_digest()` computes the normalized digest base vector once and then appends it into the output vector with a Python loop that calls `list.extend()` once per digest repeat. Large embedding dimensions such as 4096 produce hundreds of Python-level list-growth operations for every projected vector.

Use CPython's list multiplication for full digest repeats and one remainder append so the repeated-vector expansion runs in optimized list machinery while preserving exact output ordering and rounded values.

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
