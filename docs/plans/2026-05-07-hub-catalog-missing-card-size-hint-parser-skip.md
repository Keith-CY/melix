# Hub Catalog Missing Card Size-Hint Parser Skip

## Goal

Avoid calling the Hub catalog size-hint parser for payloads whose `cardData.model_size` field is missing or empty. The previous empty-text guard avoided regex searches, but the hot empty-card path still paid an avoidable helper call before checking description/readme text.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-Only Constraint

This slice is Python-only and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

## Registered Performance Probe

Registered probe: `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.

The probe has focused `test_command`, `coverage_command`, and `probe_command` entries. This slice updates the command-json probe script so both base and head measure `_size_hint_bytes(...)` with a deterministic mix of empty card data, direct `cardData.model_size`, explicit README hints, and non-model-size description text. It reports:

- `elapsed_ms_mean` (lower is better)
- `size_hint_calls_mean` (lower is better)
- `peak_bytes_mean` (informational via existing report output)

## Implementation Plan

1. Preserve the direct card model-size behavior for non-empty text.
2. Skip `_size_hint_from_text(..., allow_bare=True)` when `cardData.model_size` normalizes to an empty string.
3. Keep the existing description/readme fallback path unchanged.
4. Add regression coverage proving the empty-card path does not invoke the parser while README fallback still does.
5. Run focused pytest, changed-scope coverage, the registered local probe, and `git diff --check` before PR creation.

## Success Metrics

- Focused Hub catalog and PR-scoped performance tests pass.
- Changed-scope coverage for touched executable Python files is at least 95%.
- Local registered probe shows `size_hint_calls_mean` decreases versus `origin/main` with no behavior drift.
- CI PR-scoped performance report is the merge gate after the PR is opened.
