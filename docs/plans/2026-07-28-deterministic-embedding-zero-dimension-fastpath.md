# Deterministic embedding zero-dimension digest fast path

## Scope

This Python performance slice is limited to `worker.runtime.embedding_backends.DeterministicEmbeddingBackend._project_digest(...)` when callers request zero or negative embedding dimensions. The behavior remains the historical empty vector result, but the helper now returns before hashing and unpacking the digest.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `deterministic-embedding-project-digest-allocation` in `infra/perf/pr_scoped_probes.json`. This slice extends the existing probe with zero-dimension metrics:

- `zero_dimension_elapsed_ms_mean`
- `zero_dimension_peak_bytes_mean`

The existing 4097-dimension and default 8-dimension metrics stay in place to guard the common projection paths.

## Verification Plan

1. Add focused regression coverage that proves zero and negative dimensions do not invoke the digest projection dependency.
2. Run the registered probe tests and changed-scope coverage locally on Linux.
3. Run the registered probe locally and compare zero-dimension metrics against the pre-change baseline.
4. Let GitHub Actions run the registered PR-scoped performance workflow before merge.

## Expected Impact

The zero-dimension path avoids one SHA-256 digest, digest unpacking, normalization setup, and expanded projection dispatch per call. Non-zero dimension behavior and metrics should remain within normal noise because the early return is bypassed.
