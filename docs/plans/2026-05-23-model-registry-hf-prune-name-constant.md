# Model registry HF prune name constant

## Goal

Reduce per-directory allocation in `WorkerModelCatalog._scan_registry_root_tree_with_hf_repos(...)` by hoisting the Hugging Face cache prune-name membership set out of the hot traversal loop.

## Scope

This Python-only slice is limited to `services/mlx-worker-python/worker/model_registry/catalog.py`. It preserves the existing behavior that only `snapshots` and `refs` directory names trigger `_is_hf_cache_pruned_subtree(...)`, while normal plain-local model directories continue to skip that relative-probe call.

## Registered probe

The affected path is already covered by the registered PR-scoped probe `model-registry-plain-local-manifest-stat-elision` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries covering the model-registry catalog path, focused tests, and `scripts/pr_scoped_performance` integration.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.
