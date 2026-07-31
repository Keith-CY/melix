# Hub catalog repo-id x guard

## Scope

This Python-only performance slice is limited to Hub catalog MLX compatibility
repo-id detection in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-size-hint-regex-precompile` in
`infra/perf/pr_scoped_probes.json`. The probe watches the Hub catalog module,
focused Hub catalog tests, PR-scoped performance tests, and
`scripts/hub_catalog_size_hint_probe.py`, with focused `test_command`,
`coverage_command`, and `probe_command` entries. Its compatibility sub-metric
exercises `_payload_is_mlx_compatible(...)` across common payload shapes.

## Optimization

`_repo_id_contains_mlx(...)` now returns early for repo IDs that contain neither
`x` nor `X` after the exact lowercase `"mlx"` check misses. This preserves
case-insensitive `MLX` matches while avoiding an avoidable `.lower()` allocation
for common plain repo IDs such as `plain/model` in the compatibility scan.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. The PR-scoped performance workflow remains
the merge gate for the registered probe report.
