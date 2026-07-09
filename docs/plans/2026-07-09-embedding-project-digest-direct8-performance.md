# Embedding Project Digest Direct 8-Dimension Normalization Performance

## Context

The deterministic embedding project-digest probe covers `services/mlx-worker-python/worker/runtime/embedding_backends.py` through the registered PR-scoped probe `deterministic-embedding-project-digest-allocation`. The probe measures both expanded vectors and the default eight-dimensional projection hot path.

## Slice

This slice keeps the existing projection semantics and changes only the eight-dimensional normalization loop in `DeterministicEmbeddingBackend._project_digest`.

## Plan

1. Preserve legacy projection parity with the existing embedding runtime tests.
2. Replace the `enumerate` mutation loop for the fixed eight-value vector with direct slot assignments, avoiding iterator/tuple churn while still reusing the existing `base_values` list.
3. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux.
4. Use the PR-scoped performance CI report as the registered probe validation before merge.

## Metrics

Baseline local probe on Linux before the code change:

- `elapsed_ms_mean`: 19.093115 ms
- `default_dimension_elapsed_ms_mean`: 121.791777 ms
- `peak_bytes_mean`: 74840.888889 bytes
- `default_dimension_peak_bytes_mean`: 989.333333 bytes

Post-change local registered probe on Linux:

- `elapsed_ms_mean`: 17.643934 ms
- `default_dimension_elapsed_ms_mean`: 111.710206 ms
- `peak_bytes_mean`: 74840.888889 bytes
- `default_dimension_peak_bytes_mean`: 933.333333 bytes

Local probe deltas:

- `elapsed_ms_mean`: -1.449181 ms (-7.590%)
- `default_dimension_elapsed_ms_mean`: -10.081571 ms (-8.278%)
- `peak_bytes_mean`: unchanged
- `default_dimension_peak_bytes_mean`: -56 bytes (-5.660%)

## Verification

- Focused embedding/runtime tests from the registered probe.
- Changed-scope coverage from the registered probe.
- `scripts/deterministic_embedding_project_digest_probe.py` via the registered probe command.
