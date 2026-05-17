# Hub Catalog Direct Size Hint Integer Fast Path

## Scope

This Python performance slice targets the direct `cardData.model_size` parsing path in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

## Change

Fast-path common integer direct size hints such as `128 MB`, `4 GB`, and `512 KB` before falling back to the existing whitespace-split and float parser. This keeps decimal values, lowercase units, extra whitespace, and invalid strings on the existing general parser while avoiding list allocation and float conversion for the common integer uppercase-unit card metadata shape.

## Local verification plan

Run the registered focused test command, changed-scope coverage command, and registered local probe on Linux before opening the PR. Hosted PR-scoped performance CI remains the merge gate for the registered probe report.
