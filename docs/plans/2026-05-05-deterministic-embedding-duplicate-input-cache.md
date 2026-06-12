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

`DeterministicEmbeddingRuntime.embed_inputs()` caches duplicate input vectors for a request, but the cache currently stores a tuple copy and then converts it back to a list for every emitted position. That keeps aliasing safe but adds an avoidable tuple allocation for each unique input and a generic list-constructor copy for each output.

Store the canonical cached vector as the list returned by the embedding family, emit the first occurrence directly, and emit `vector.copy()` for duplicate response positions. This preserves output ordering, values, and per-position list independence while removing the unique-input tuple roundtrip and first-occurrence response copy from duplicate-heavy requests.

## Performance probe

Register `deterministic-embedding-duplicate-input-cache` in the PR-scoped performance registry.

The probe will run a synthetic request with many duplicate input strings, measure:

- `elapsed_ms_mean` — lower is better
- `embed_text_calls_mean` — lower is better
- `unique_input_count` / `input_count` — behavior context

Success means the branch keeps identical output cardinality/checksum while reducing repeated embed calls to the unique input count and improving elapsed time on the duplicate-heavy workload.

## 2026-05-09 Follow-up Slice

This follow-up keeps the existing request-local duplicate-vector cache and only
binds the hot-loop cache lookup, append, and embedding-family callables before
iterating over inputs. The change preserves vector ordering, duplicate-copy
semantics, and the existing registered probe while reducing repeated attribute
lookups in duplicate-heavy deterministic embedding requests.

## Verification commands

- Focused pytest for embedding runtime and PR-scoped probe selection/smoke tests
- Changed-scope coverage for touched Python/tests with at least 95% automated coverage
- Local registered probe run through `scripts/pr_scoped_performance_run.py`
- `git diff --check`

## 2026-06-12 Cycle Copy Extension Slice

This follow-up keeps the same registered probe and narrows only the repeated-cycle
materialization path in `DeterministicEmbeddingRuntime.embed_inputs()`. Once the
first cycle's vectors are embedded, each repeated cycle is now extended from a
generator of `vector.copy()` results instead of appending one copied vector at a
time in Python. The slice preserves per-position list independence and duplicate
embedding-call elision while reducing hot-loop append overhead on cycle-shaped
duplicate requests.
