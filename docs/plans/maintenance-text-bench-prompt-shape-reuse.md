# Maintenance text benchmark prompt-shape reuse

## Goal

Avoid shaping the same text benchmark prompt twice for every measured sample. The matrix-level text benchmark path already expands each suite case to the requested context length once per `(case, context_length)` pair before iterating repeats; the sample measurement helper should be able to consume that shaped prompt directly.

## Scope

- `services/mlx-worker-python/worker/engine/maintenance_core.py`
- `services/mlx-worker-python/tests/test_maintenance_service.py`

## Linux verification plan

- Focused pytest for the existing maintenance prompt-shape scoped test node.
- Changed-scope coverage with `scripts/changed_scope_coverage.py` for the touched executable files.
- Local performance/structure probe comparing `origin/main` and head by counting `_shape_benchmark_prompt(...)` invocations across repeated text benchmark samples.

## Scoped CI probe

The touched files are already watched by the registered `maintenance-prompt-shape-vector-repeat` PR-scoped performance probe. Its focused command includes `test_benchmark_helper_parsers_cover_invalid_and_boundary_inputs`, which now covers the prompt-reuse path.

## Success metric

For one case, one context length, and three repeats, `_shape_benchmark_prompt(...)` should run once instead of once per repeat plus the initial shape pass, while preserving benchmark row output.
