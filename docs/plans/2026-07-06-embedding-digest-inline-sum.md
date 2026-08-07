# Deterministic embedding digest inline square sum

## Scope

This Python-only performance slice targets deterministic embedding projection in
`services/mlx-worker-python/worker/runtime/embedding_backends.py`.

The affected path is covered by the registered PR-scoped performance probe
`deterministic-embedding-project-digest-allocation` in
`infra/perf/pr_scoped_probes.json`. The registry entry has focused
`test_command`, `coverage_command`, and `probe_command` entries that exercise the
embedding runtime behavior, changed-scope coverage, and digest projection metrics.

## Optimization

`DeterministicEmbeddingBackend._project_digest(...)` always projects eight
SHA-256 digest lanes before either returning the default 8-dimensional vector or
expanding those lanes to larger dimensions. This slice replaces the repeated
`sum(value * value for value in base_values)` generator path with an explicit
8-lane square-sum helper while preserving the existing in-place normalization
shape for the default-dimension path.

The generated vector values, allocation profile, and zero-norm fallback remain
unchanged.

## Verification plan

1. Run the focused embedding parity tests and registered probe smoke tests from
   the probe registry.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered `deterministic_embedding_project_digest_probe.py` probe
   locally before and after the change and compare both default-dimension and
   expanded-dimension metrics.
4. Use GitHub Actions PR-scoped performance as the final registered probe merge
   gate.

## Verification boundary

This is a Python-only slice and is locally verifiable on Linux. The PR-scoped CI
probe report remains the required merge gate before merging.
