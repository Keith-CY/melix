# Hub catalog cardData get cache

## Scope

This Python-only performance slice is limited to Hub catalog summary/card record
construction in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.
It preserves existing Hub metadata semantics while avoiding repeated `dict.get`
lookups for the `cardData` payload and frequently reused payload/card accessors
inside the per-record hot path.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-tag-normalization-single-pass` in
`infra/perf/pr_scoped_probes.json`.

The registry entry already exposes focused `test_command`, `coverage_command`,
and `probe_command` entries for `hub_catalog.py`, `test_hub_catalog.py`,
`test_pr_scoped_performance.py`, and `scripts/hub_catalog_tag_normalization_probe.py`.
This slice keeps the registered probe definition stable and relies on that probe
locally and in CI for performance validation.

## Plan

1. Add a focused regression test proving `_summary_record()` reads `cardData`
   once while preserving summary resolution.
2. Cache `payload.get`, the raw `cardData` value, and `card_data.get` in
   `_summary_record()` so repeated per-record metadata extraction avoids extra
   attribute lookup and duplicate `cardData` reads.
3. Thread the already-normalized `cardData` mapping through local-fit artifact
   estimation so the size-hint fallback does not re-read `cardData` during
   summary construction.
4. Cache the raw `cardData` value in `_card_record()` so card construction also
   avoids duplicate `cardData` reads.
5. Run the focused Hub catalog tests, changed-scope coverage, and the registered
   `hub-catalog-tag-normalization-single-pass` probe locally on Linux.
6. Use GitHub Actions and the registered PR-scoped performance report as the
   merge gate.

## Verification

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_hub_catalog_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_hub_catalog_tag_normalization_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/hub_catalog.py services/mlx-worker-python/tests/test_hub_catalog.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/hub_catalog_tag_normalization_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/hub_catalog_tag_normalization_probe.py
```
