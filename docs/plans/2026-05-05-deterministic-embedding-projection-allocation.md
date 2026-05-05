# Deterministic Embedding Projection Allocation Probe

## Goal

Reduce avoidable temporary list allocation in the deterministic embedding projection helper while preserving the exact emitted embedding values.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and is verifiable on Linux with focused pytest, changed-scope coverage, and an explicit local performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `scripts/deterministic_embedding_project_digest_probe.py`
- `infra/perf/pr_scoped_probes.json`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization

`DeterministicEmbeddingBackend._project_digest(...)` currently builds a full repeated `values` list and then builds the final normalized output list. For larger deterministic embedding dimensions, the repeated intermediate list duplicates the final output size.

Compute the repeated-pattern L2 norm from the eight digest-derived base values, then emit the normalized output directly from the base pattern. This preserves ordering and rounding semantics while avoiding the full pre-normalization vector materialization.

## Performance probe

Register `deterministic-embedding-project-digest-allocation` as a `command_json` PR-scoped probe.

Metrics:

- `elapsed_ms_mean` — lower is better, warned on >5% regression.
- `peak_bytes_mean` — lower is better, warned on >5% regression.
- `vector_count` and `dimensions` — workload guard metrics.

Success means equivalent vector shape/output semantics with materially lower peak traced memory for a large deterministic projection workload.

## Verification commands

- Focused pytest for embedding runtime tests and probe registry coverage.
- Changed-scope coverage via `scripts/changed_scope_coverage.py`, requiring >=95% changed executable coverage.
- Local base-vs-head probe through `scripts/pr_scoped_performance_run.py` for `deterministic-embedding-project-digest-allocation`.
- `git diff --check`.
