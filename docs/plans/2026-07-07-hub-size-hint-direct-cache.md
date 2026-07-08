# Hub catalog repeated direct size-hint cache

## Goal

Reduce repeated direct model-size hint parsing overhead in the Hub catalog path by caching the pure direct-card and direct-explicit text parsers for repeated Hub metadata strings.

## Scope

This Python-only slice is limited to `services/mlx-worker-python/worker/model_ops/hub_catalog.py` and focused Hub catalog tests. It does not change accepted size-hint syntax or Hub API behavior.

## Registered probe

The affected path is already covered by the PR-scoped `hub-catalog-size-hint-regex-precompile` probe in `infra/perf/pr_scoped_probes.json`. The probe watches the Hub catalog module, focused tests, PR-scoped performance tests, and `scripts/hub_catalog_size_hint_probe.py`, and includes focused `test_command`, `coverage_command`, and `probe_command` entries.

## Validation plan

- Run the registered focused Hub catalog test command.
- Run the registered changed-scope coverage command.
- Run `scripts/hub_catalog_size_hint_probe.py` before and after the change on Linux and compare `elapsed_ms_mean`.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95% for the touched scope.
- The registered probe shows lower `elapsed_ms_mean` without changing the parsed hint count or compatibility count.
