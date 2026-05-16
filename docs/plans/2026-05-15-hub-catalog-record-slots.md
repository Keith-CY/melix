# Hub catalog record slots performance slice

## Scope

This Python-only performance slice is limited to Hub catalog result record objects. It keeps search/card response fields, dataclass immutability, and downstream access semantics unchanged while reducing per-record allocation overhead.

Affected implementation path:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`

Affected test and probe paths:

- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_tag_normalization_probe.py`
- `scripts/hub_catalog_size_hint_probe.py`

## Registered Probe

The affected path is covered by existing PR-scoped probes in `infra/perf/pr_scoped_probes.json`; the focused local verification uses `hub-catalog-tag-normalization-single-pass` because that registered probe watches `hub_catalog.py`, includes focused `test_command`, `coverage_command`, and `probe_command` entries, and constructs Hub catalog summary records over a synthetic model payload set.

## Optimization

`HubModelSummaryRecord`, `HubSearchPage`, and `HubModelCardRecord` now use frozen slotted dataclasses. This removes the per-instance `__dict__` allocation for catalog result containers while preserving field access, constructor signatures, and frozen behavior.

## Verification Plan

Run the registered focused local commands on Linux before pushing:

1. Focused pytest for Hub catalog behavior and registered probe selection.
2. Changed-scope coverage via the registered `coverage_command`.
3. The registered `hub-catalog-tag-normalization-single-pass` probe on `origin/main` and on this branch, using repeated samples.

The registered PR-scoped performance CI report remains the merge gate.
