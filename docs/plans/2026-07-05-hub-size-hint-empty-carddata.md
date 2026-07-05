# Hub catalog empty cardData size-hint fast path

## Scope

This Python-only performance slice is limited to `worker.model_ops.hub_catalog._size_hint_bytes()`.
It preserves Hub model size-hint behavior while avoiding the `cardData.description` lookup when
`cardData` is empty and no direct `cardData.model_size` hint exists.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches the Hub catalog module, focused tests, and
`scripts/hub_catalog_size_hint_probe.py`.

## Verification Plan

- Run the registered focused Hub catalog and PR-scoped performance tests locally on Linux.
- Run changed-scope coverage for the affected module/test/probe paths and require at least 95% coverage.
- Run the registered probe locally on Linux against `origin/main` and this branch via
  `scripts/pr_scoped_performance_run.py`.
- Use GitHub Actions PR-scoped performance as the merge gate after opening the PR.

## Acceptance

Accept the slice only if the focused tests and changed-scope coverage pass and the registered probe
shows a non-regressing or improved `elapsed_ms_mean` for the Hub size-hint workload.
