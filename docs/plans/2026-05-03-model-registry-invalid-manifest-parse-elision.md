# Model Registry Invalid-Depth Manifest Parse Elision

## Goal

Avoid parsing registry `manifest.json` files whose relative directory depth can never produce a valid Melix registry identity.

## Scope

- `services/mlx-worker-python/worker/model_registry/catalog.py`
- `services/mlx-worker-python/tests/test_model_registry_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Linux Constraint

This is a Python-only optimization slice that must be verified locally on Linux with focused pytest, changed-scope coverage, and an explicit local performance probe.

## Optimization Hypothesis

`WorkerModelCatalog._scan_registry_root_tree_with_hf_repos()` intentionally reports directories containing `manifest.json` even when they sit at relative depths that cannot map to a valid registry identity.
Later, `_refresh_registry_models_from_roots()` still parses those manifests before `_apply_registry_identity_metadata()` rejects them.
Skipping the parse step for invalid-depth manifest paths should preserve behavior while reducing redundant JSON loads in noisy registry trees.

## Probe Definition

Update the existing model-registry scoped performance probe so it seeds:
- valid plain-local config+weights directories
- invalid-depth manifest directories that should never become accepted registry models

Track at least:
- `elapsed_ms_mean`
- `manifest_parse_calls_mean`
- existing guard-rail metrics proving accepted plain-local discovery still works

## Success Metric

- `manifest_parse_calls_mean` decreases for the synthetic invalid-depth manifest workload
- local focused tests pass
- changed-scope coverage is at least 95%
- the scoped probe remains selected for `worker/model_registry/catalog.py`

## Verification Commands

- Focused pytest for touched catalog/probe tests
- Focused coverage command from the scoped probe registry
- Local scoped probe execution for the model-registry catalog probe
- `git diff --check`
