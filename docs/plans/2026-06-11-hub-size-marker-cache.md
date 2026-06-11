# Hub catalog MLX tag atom type gate

## Scope

This Python-only performance slice is limited to the Hub catalog MLX tag
compatibility path in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
The registry entry watches the Hub catalog module, focused tests, the PR-scoped
performance tests, and `scripts/hub_catalog_size_hint_probe.py`; it also includes
focused `test_command`, `coverage_command`, and `probe_command` entries.

## Change

When `_tag_payload_contains_mlx(...)` scans list payloads, it now gates the
existing exact/atom checks with `isinstance(item, str)` before comparing tag
values. This preserves exact three-character MLX semantics and the existing
short-circuit for `"MLX"`/`"mlx"` while skipping unnecessary string comparisons
for non-string tag values.

## Verification plan

- Run the registered focused test command for `hub-catalog-size-hint-regex-precompile`.
- Run the registered changed-scope coverage command and require at least 95% coverage.
- Run the registered probe locally on Linux against `origin/main` and the slice, then compare `payload_compatibility_elapsed_ms_mean`.
- Use the PR-scoped performance workflow as the CI merge gate.

## Linux boundary

This slice changes Python code and is locally verifiable on Linux. No Swift
runtime performance claims are made.
