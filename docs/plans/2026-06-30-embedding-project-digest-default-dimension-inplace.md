# Embedding Project Digest Default Dimension In-place Normalization

This Python-only performance slice is limited to deterministic embedding digest
projection in `services/mlx-worker-python/worker/runtime/embedding_backends.py`.
It preserves the deterministic projection values while reducing temporary list
allocation on the default eight-dimensional path.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`deterministic-embedding-project-digest-allocation` in
`infra/perf/pr_scoped_probes.json`. The registry already includes focused
`test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_embedding_project_digest_probe.py`

## Slice plan

1. Keep the expanded-dimension digest projection behavior unchanged.
2. For the default `dimensions == 8` path, normalize the base digest vector in
   place and return it instead of allocating a second normalized list.
3. Verify value parity with the existing embedding runtime tests.
4. Run changed-scope coverage and the registered PR-scoped performance probe on
   Linux before opening the PR. GitHub Actions remains the merge gate for the
   registered probe report.

## Metrics

The local probe compares `origin/main` with this branch using
`scripts/pr_scoped_performance_run.py` and reports:

- `default_dimension_elapsed_ms_mean`
- `default_dimension_peak_bytes_mean`
- expanded-dimension `elapsed_ms_mean`
- expanded-dimension `peak_bytes_mean`

The expected directional gain is lower default-dimension peak allocation with no
behavioral change.
