# Hub catalog repo-id lowercase guard performance slice

## Scope

This Python-only performance slice is limited to Hub catalog MLX repo-id detection in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
That probe watches the Hub catalog module, focused Hub tests, PR-scoped
performance tests, and `scripts/hub_catalog_size_hint_probe.py`; it defines
focused `test_command`, `coverage_command`, and `probe_command` entries.

## Change

`_repo_id_contains_mlx(...)` now avoids allocating `repo_id.lower()` for plain
lowercase repository ids that do not contain `mlx`. It keeps the existing fast
path for lowercase `mlx` matches and still falls back to a lowercase copy when an
uppercase `M`, `L`, or `X` means a mixed-case `MLX` match is possible.

## Verification plan

- Run the registered focused test command for `hub-catalog-size-hint-regex-precompile`.
- Run the registered changed-scope coverage command and require at least 95% coverage.
- Run the registered probe locally on Linux against `origin/main` and this slice,
  then compare `payload_compatibility_elapsed_ms_mean`.
- Use the PR-scoped performance workflow as the CI merge gate.

## Linux boundary

This slice changes Python code and is locally verifiable on Linux. No Swift
runtime performance claims are made.
