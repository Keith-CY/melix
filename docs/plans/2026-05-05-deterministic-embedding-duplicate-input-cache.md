# Deterministic Embedding Duplicate Input Cache

## Goal

Reduce redundant deterministic embedding work when a single embedding request contains repeated input strings.

## Linux-only constraint

This is a Python worker-runtime slice. It can be validated on Linux with focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/deterministic_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Optimization hypothesis

`DeterministicEmbeddingRuntime.embed_inputs()` currently embeds every input position independently. For duplicate strings inside the same request, it repeats the same family/backend embedding work even though backend, family, and dimensions are fixed for that call.

Add a request-local cache keyed by the raw input text so duplicate positions reuse the already-computed vector while preserving input ordering and output values.

## Performance probe

Register `deterministic-embedding-duplicate-input-cache` in the PR-scoped performance registry.

The probe will run a synthetic request with many duplicate input strings, measure:

- `elapsed_ms_mean` — lower is better
- `embed_text_calls_mean` — lower is better
- `unique_input_count` / `input_count` — behavior context

Success means the branch keeps identical output cardinality/checksum while reducing repeated embed calls to the unique input count and improving elapsed time on the duplicate-heavy workload.

## Verification commands

- Focused pytest for embedding runtime and PR-scoped probe selection/smoke tests
- Changed-scope coverage for touched Python/tests with at least 95% automated coverage
- Local registered probe run through `scripts/pr_scoped_performance_run.py`
- `git diff --check`
