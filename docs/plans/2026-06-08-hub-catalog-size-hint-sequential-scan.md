# Hub catalog size-hint sequential text scan

## Scope

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._size_hint_bytes(...)`, specifically the fallback path that scans multiple Hub metadata text fields for explicit `Model size` hints.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. The probe watches `services/mlx-worker-python/worker/model_ops/hub_catalog.py`, `services/mlx-worker-python/tests/test_hub_catalog.py`, `services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and `scripts/hub_catalog_size_hint_probe.py`, and it already includes focused `test_command`, `coverage_command`, and `probe_command` entries.

## Plan

When description, README, and card-description text are all present, the current fallback allocates a joined string before calling `_size_hint_from_text(...)`. Most Hub payloads place the complete explicit size hint within one field, so scan each candidate field in order first and return the first matching hint. Keep a final joined-text fallback only for unusual boundary-spanning text so behavior remains compatible.

The probe payload will include a multi-field README hint case so the registered performance report directly exercises the common sequential-scan path.

## Verification

Run the registered focused hub-catalog tests, changed-scope coverage, and the registered hub-catalog size-hint probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the merge and final metrics gate.
