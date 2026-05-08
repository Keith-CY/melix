# Hub Catalog Size Hint Marker Guard

## Goal

Reduce avoidable regex work in `worker.model_ops.hub_catalog._size_hint_from_text`
for explicit size-hint scans that cannot match because the text does not contain a
`model` marker.

## Scope

This is a Python-only performance slice. It keeps the existing direct
`cardData.model_size` bare-size behavior unchanged, and it does not change Hub
API fetching, local-fit scoring, sibling size accounting, or quantization tag
normalization.

## Registered Probe

The affected path is covered by the existing PR-scoped performance probe:

- `hub-catalog-size-hint-regex-precompile`
  - `test_command`: focused `test_hub_catalog.py` coverage plus probe registry tests
  - `coverage_command`: focused coverage plus changed-scope coverage for the touched paths
  - `probe_command`: `scripts/hub_catalog_size_hint_probe.py`

## Change

For single-source `description`, `readme`, and card description fields,
`_size_hint_bytes` now skips `_size_hint_from_text` when the candidate text cannot
contain a case-insensitive `model` marker because it lacks an `mo`/`MO` prefix.
The explicit regex still owns final matching, including unusual mixed-case
`model size` spellings, so the guard preserves behavior while reducing helper and
regex calls for common description strings that mention a byte unit without being
a model-size hint.

## Verification Commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_hub_catalog.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q \
  services/mlx-worker-python/tests/test_hub_catalog.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_size_hint_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json \
  services/mlx-worker-python/worker/model_ops/hub_catalog.py \
  services/mlx-worker-python/tests/test_hub_catalog.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py \
  scripts/hub_catalog_size_hint_probe.py

PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_HUB_CATALOG_SIZE_HINT_REPO_ROOT="$PWD" \
  uv run --project services/mlx-worker-python python3 scripts/hub_catalog_size_hint_probe.py
```

## Success Criteria

- Focused tests pass.
- Changed-scope coverage is at least 95 percent.
- The registered local probe reports lower `elapsed_ms_mean` while preserving
  `size_hint_calls_mean` and output checksum.
