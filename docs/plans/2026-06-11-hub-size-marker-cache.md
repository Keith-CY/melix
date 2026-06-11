# Hub catalog size-hint marker cache

## Scope

This Python-only performance slice is limited to the Hub catalog size-hint path in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
The registry entry watches the Hub catalog module, focused tests, the PR-scoped
performance tests, and `scripts/hub_catalog_size_hint_probe.py`; it also includes
focused `test_command`, `coverage_command`, and `probe_command` entries.

## Change

When the size-hint parser must inspect `description`, `readme`, and
`cardData.description`, reuse each `_may_contain_model_marker(...)` result as the
parser walks the fields. The loop stops once a valid size hint is found, keeps
behavior identical, and avoids a second marker scan for fields that proceed to
regex parsing.

## Verification plan

- Run the registered focused test command for `hub-catalog-size-hint-regex-precompile`.
- Run the registered changed-scope coverage command and require at least 95% coverage.
- Run the registered probe locally on Linux against `origin/main` and the slice, then compare `elapsed_ms_mean`.
- Use the PR-scoped performance workflow as the CI merge gate.

## Linux boundary

This slice changes Python code and is locally verifiable on Linux. No Swift
runtime performance claims are made.
