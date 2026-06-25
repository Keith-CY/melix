# Model registry metadata MLX precheck slice

## Scope

This Python-only performance slice is limited to `worker.model_registry.catalog._metadata_text_has_mlx_signal(...)`, which is called while scanning model metadata text from README/config/model-index files.

## Registered probe

The affected path is covered by the registered PR-scoped probe `model-registry-readme-source-fastpath` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries covering `services/mlx-worker-python/worker/model_registry/catalog.py`, the model registry tests, and `scripts/model_registry_readme_source_probe.py`.

## Optimization

Add a negative fast path that returns immediately when the metadata prefix has no `mlx` substring. Every existing positive signal checked by `_metadata_text_has_mlx_signal(...)` contains `mlx`, so this preserves behavior while avoiding several substring scans for common non-MLX metadata files.

## Verification plan

1. Run the registered focused pytest command for `model-registry-readme-source-fastpath` locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux and verify changed-scope coverage stays above 95%.
3. Run the registered PR-scoped performance probe locally against `origin/main` and this branch.
4. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Expected performance signal

The primary expected signal is lower `new_elapsed_ms_mean` in `model-registry-readme-source-fastpath`, especially for negative metadata scans where no `mlx` signal is present. Peak bytes should stay flat or decrease slightly.
