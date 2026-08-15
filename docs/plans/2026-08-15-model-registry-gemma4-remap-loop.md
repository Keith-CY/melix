# Model Registry Gemma4 Remap Loop

## Scope

This Python-only performance slice is limited to Gemma4 vision-weight remap
recognition in `services/mlx-worker-python/worker/model_registry/catalog.py`.

The hot path now uses an explicit loop in
`_has_gemma4_vision_weight_remap_tensor()` instead of allocating a generator for
`any()`. The helper also accepts a pre-lowercased tensor name so callers that
already normalize the name can avoid repeated lowercase work while preserving the
existing prefix fast path.

## Registered Probe

The affected file is already covered by the registered PR-scoped performance
probes in `infra/perf/pr_scoped_probes.json`, including:

- `model-registry-plain-local-manifest-stat-elision`
- `model-registry-readme-source-fastpath`

Both entries include focused `test_command`, `coverage_command`, and
`probe_command` fields and watch:

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_artifact_embedding_catalog_contract.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Verification Plan

Run the new focused regression test, the registered model-registry focused test
command, changed-scope coverage, `git diff --check`, and the registered
model-registry probe locally on Linux before opening the PR. GitHub Actions
PR-scoped performance remains the merge gate for the registered probe report.
