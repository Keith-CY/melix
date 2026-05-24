# Embedding Project Digest Remainder Loop Slice

Date: 2026-05-24

## Scope

This Python-only performance slice is limited to the remainder normalization path
inside `DeterministicEmbeddingBackend._project_digest` in
`services/mlx-worker-python/worker/runtime/embedding_backends.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`deterministic-embedding-project-digest-allocation` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/embedding_backends.py`
- `services/mlx-worker-python/tests/test_embedding_runtime.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/deterministic_embedding_project_digest_probe.py`

## Optimization

The digest projection always has an eight-element `base_values` vector and uses a
remainder branch for dimensions that are not exact multiples of eight. This slice
replaces the temporary `base_values[:remainder]` slice with an index loop over the
existing eight-element list. It keeps the same L2 normalization arithmetic and
output vector values while avoiding a small temporary list allocation on the
remainder path.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered
probe locally on Linux. Compare the registered probe against `origin/main` before
opening the PR, then use the PR-scoped performance workflow as the hosted merge
gate.
