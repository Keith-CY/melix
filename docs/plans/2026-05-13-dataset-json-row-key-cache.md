# Dataset JSON Row Key Cache

## Scope

This Python-only performance slice keeps dataset preview behavior unchanged while avoiding a per-object temporary `{ "rows", "data" }` set allocation in the limited JSON preview scanner.

Touched paths:

- `services/mlx-worker-python/worker/dataset_registry/catalog.py`
- `services/mlx-worker-python/tests/test_dataset_registry.py`
- `infra/perf/pr_scoped_probes.json`

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `dataset-registry-preview-limit-short-circuit` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` values for the dataset preview limit path.

This slice extends the focused test and coverage commands to include the row-key cache regression test.

## Optimization

Hoist the JSON wrapper row-array keys into a module-level `frozenset` and reuse it when scanning wrapper objects for `rows` or `data` arrays. This preserves the existing accepted keys and incremental decode behavior while reducing repeated allocation during limited JSON previews with wrapper metadata.

## Verification Plan

Run locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q <registered focused dataset preview tests>
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q <registered focused dataset preview tests> && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/dataset_registry/catalog.py services/mlx-worker-python/tests/test_dataset_registry.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/dataset_registry_preview_limit_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/dataset_registry_preview_limit_probe.py
```

GitHub Actions PR-scoped performance remains the merge gate for the registered probe result.

## Acceptance

- Focused dataset registry preview tests pass.
- Changed-scope coverage remains at or above 95% for touched executable Python lines.
- The registered local probe is non-regressive or improved for `elapsed_ms_mean`.
- PR-scoped performance CI completes `dataset-registry-preview-limit-short-circuit` successfully.
